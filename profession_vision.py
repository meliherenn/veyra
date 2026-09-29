"""Visible controls for the inventory and profession window; no game/network API."""
from dataclasses import dataclass
from difflib import SequenceMatcher
from collections import Counter
import csv
import hashlib
import io
import re
import subprocess
import os

import cv2
import numpy as np
from PIL import Image

from config import ROOT, OCR_TIMEOUT
from fish_catalog import name_key, resolve_name
from metrics import METRICS

# Scales tried by matches(); the half-resolution pre-check must try the same
# relative scales or it would reject a panel rendered at another zoom level.
MATCH_SCALES = (1., .9, 1.1, .8, 1.25)
# Half-resolution rejection test run before the full title match. On a clean
# map the downscaled title scores far below this, so the expensive multi-scale
# match is skipped; anything at or above it falls through to matches(), which
# stays the only authority on whether the panel is open.
PANEL_FAST_SCALE = 0.5
PANEL_FAST_REJECT = 0.60


@dataclass(frozen=True)
class Box:
    x: int
    y: int
    w: int
    h: int

    @property
    def center(self):
        return self.x + self.w // 2, self.y + self.h // 2

    def crop(self, frame):
        return frame[max(0, self.y):max(0, self.y + self.h),
                     max(0, self.x):max(0, self.x + self.w)]


@dataclass(frozen=True)
class Word:
    text: str
    box: Box


@dataclass(frozen=True)
class AutoRow:
    fish_id: str
    button: Box
    seconds: int


@dataclass(frozen=True)
class ActiveCollection:
    fish_id: str | None
    button: Box
    progress: int | None
    total: int | None


def parse_energy(text):
    match = re.search(r'enerji\s*[:;]?\s*(\d{1,4})\s*[/|]\s*(\d{1,4})', name_key_energy(text))
    if match:
        value, maximum = map(int, match.groups())
        if 0 <= value <= maximum <= 10000 and maximum:
            return value, maximum
    return None


def name_key_energy(text):
    from screen_detector import normalized
    return normalized(text)


def recovery_reason(text):
    key = name_key(text)
    if 'kurtulabilirsiniz' in key or ('iksir' in key and 'onayla' in key):
        return None
    if any(k in key for k in ('kiymik', 'kymik', 'kiym', 'yarali', 'calisamiyor')):
        return 'splinter'
    if 'enerji' in key and any(word in key for word in ('yetersiz', 'yeterli', 'kalmadi', 'yok', 'sahip', 'gerekli')):
        return 'energy'
    if any(neg in key for neg in ('ustalik', 'ustalig', 'yetenek', 'seviye', 'esyaya', 'esya')):
        return None
    if 'otomatik toplama' in key and 'kaynak' in key:
        return 'auto'

    words = key.split()
    has_tool_word = any(w.startswith(('alet', 'aiet', 'olta', 'alta')) or 'alet' in w or 'olta' in w for w in words)
    if not has_tool_word:
        return None

    if any(phrase in key for phrase in ('gerekli alet', 'oltayi tak', 'olta tak', 'aletiniz yok', 'alete sahip', 'oltaniz yok')):
        return 'tool'

    has_gerek = any(w.startswith(('gerek', 'gerel', 'gerik', 'gere')) for w in words)
    has_sahip = any(w.startswith('sahip') for w in words)
    has_degil = any(w.startswith(('degil', 'degii')) for w in words)
    if has_gerek or has_sahip or has_degil:
        return 'tool'

    if any(SequenceMatcher(None, 'gerekli alete sahip degilsiniz', part).ratio() >= 0.75
           for part in [key] + [' '.join(words[i:i+4]) for i in range(max(1, len(words)-3))]):
        return 'tool'
    return None


class ProfessionVision:
    def __init__(self, detector):
        self.detector = detector
        self.templates = {}
        self.variants = {}
        self.cache = {}
        for name in ('potion', 'potion-apply', 'potion-cancel', 'item-use', 'item-equip', 'rod', 'menu-toggle', 'menu-toggle-closed', 'menu-toggle-hover', 'menu-entry', 'title', 'hunt', 'hunt-hover', 'inventory', 'inventory-hover', 'close', 'collect', 'capacity', 'alert-ok', 'alert-kapat'):
            path = ROOT / 'assets' / f'profession-{name}.png'
            if path.exists():
                self.templates[name] = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
            # A newer item model needs its own artwork: profession-<name>_2.png.
            extra = [cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
                     for p in sorted((ROOT / 'assets').glob(f'profession-{name}_*.png'))]
            extra = [image for image in extra if image is not None]
            if extra:
                self.variants[name] = extra

    def matches(self, frame, name, region=None, threshold=.89, brightness_range=(.72, 1.35)):
        sources = [image for image in [self.templates.get(name), *self.variants.get(name, ())] if image is not None]
        if not sources:
            return []
        region = region or Box(0, 0, frame.shape[1], frame.shape[0])
        cropped = region.crop(frame)
        if not cropped.size:
            return []
        gray = cv2.cvtColor(cropped, cv2.COLOR_RGB2GRAY)
        hits = []
        min_b, max_b = brightness_range
        for source in sources:
            for scale in MATCH_SCALES:
                pattern = cv2.resize(source, None, fx=scale, fy=scale)
                h, w = pattern.shape
                if h > gray.shape[0] or w > gray.shape[1]:
                    continue
                scores = cv2.matchTemplate(gray, pattern, cv2.TM_CCOEFF_NORMED)
                for _ in range(12):
                    _, score, _, (x, y) = cv2.minMaxLoc(scores)
                    if score < threshold:
                        break
                    box = Box(region.x + x, region.y + y, w, h)
                    brightness = float(gray[y:y+h, x:x+w].mean()) / max(1, float(pattern.mean()))
                    if min_b <= brightness <= max_b and all(np.linalg.norm(np.subtract(box.center, b.center)) > min(w, h) for _, b in hits):
                        hits.append((score, box))
                    scores[max(0, y-h//2):y+h//2+1, max(0, x-w//2):x+w//2+1] = 0
        return [box for _, box in sorted(hits, key=lambda h: -h[0])]

    def words(self, frame, region=None):
        region = region or Box(0, 0, frame.shape[1], frame.shape[0])
        crop = region.crop(frame)
        if not crop.size:
            return []
        key = (region, hashlib.blake2b(crop.tobytes(), digest_size=12).digest())
        # The key contains the exact crop pixels, so a hit never goes stale.
        cached = self.cache.pop(key, None)
        if cached is not None:
            self.cache[key] = cached
            METRICS.bump('ocr_tsv_cache_hit')
            return cached
        METRICS.bump('ocr_tsv_calls')
        with METRICS.span('ocr_tsv'):
            path = self.detector.path / 'profession-ocr.png'
            Image.fromarray(crop).resize((crop.shape[1]*2, crop.shape[0]*2)).save(path)
            try:
                result = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'tur+eng', '--psm', '11', 'tsv'],
                                        check=True, capture_output=True, text=True, timeout=OCR_TIMEOUT * 2,
                                        env=dict(os.environ,OMP_THREAD_LIMIT='1'))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                # Profession OCR is supplementary.  The main detector has its own
                # bounded OCR and must keep the old fishing workflow alive when this
                # optional scan is slow or unavailable.
                self.cache[key] = []
                self._trim_cache()
                return []
            words = []
            for row in csv.DictReader(io.StringIO(result.stdout), delimiter='\t', quoting=csv.QUOTE_NONE):
                if row.get('text') and float(row['conf']) >= 20:
                    box = Box(region.x + int(row['left'])//2, region.y + int(row['top'])//2,
                              max(1, int(row['width'])//2), max(1, int(row['height'])//2))
                    words.append(Word(name_key_energy(row['text']), box))
        self.cache[key] = words
        self._trim_cache()
        return words

    def _trim_cache(self):
        # Vuruş yolunda pop + yeniden ekleme yapılır; ilk anahtar en eskidir.
        # dict.popitem() keyword almaz (screen_detector'daki aynı hata gibi).
        while len(self.cache) > 32:
            self.cache.pop(next(iter(self.cache)))

    def badge_number(self, frame, region):
        """Yığın rozetindeki rakam.

        Rozet koyu zemin üzerine beyaz, 8–10 piksel yüksekliğinde rakamdır.
        Genel `words()` (psm 11) bu boyutta ya boş ya da komşu slottan gürültü
        döndürür. Ham görüntüde okunamazsa rozet ikili görüntüye çevrilip
        tekrar denenir (düşük eşik rakamı erozyona uğratıp yanlış sonuç
        verebildiği için tek bir eşik kullanılır). İkisi de boşsa kanıt
        sayılmaz ve tüketim rozet pikselinden aranır.
        """
        crop = region.crop(frame)
        if not crop.size:
            return None
        key = ('badge', region, hashlib.blake2b(crop.tobytes(), digest_size=12).digest())
        cached = self.cache.pop(key, None)
        if cached is not None:
            self.cache[key] = cached
            METRICS.bump('ocr_tsv_cache_hit')
            return None if cached is False else cached
        METRICS.bump('badge_ocr_calls')
        path = self.detector.path / 'profession-badge.png'
        gray = crop.astype(np.int16).mean(axis=2)
        variants = [(Image.fromarray(crop), Image.LANCZOS, psm) for psm in ('7', '8')]
        binary = Image.fromarray(((gray > 150) * 255).astype(np.uint8))
        variants += [(binary, Image.NEAREST, psm) for psm in ('7', '8')]
        value = None
        for image, resample, psm in variants:
            image.resize((crop.shape[1] * 4, crop.shape[0] * 4), resample).save(path)
            try:
                with METRICS.span('badge_ocr'):
                    out = subprocess.run(['tesseract', str(path), 'stdout', '-l', 'eng', '--psm', psm,
                                          '-c', 'tessedit_char_whitelist=0123456789'],
                                         check=True, capture_output=True, text=True, timeout=OCR_TIMEOUT,
                                         env=dict(os.environ, OMP_THREAD_LIMIT='1'))
            except (subprocess.TimeoutExpired, subprocess.CalledProcessError, OSError):
                continue
            # Komşu slottan sızan ikinci rakam ('1 5' -> 15) tüketim kanıtı
            # olamaz; yalnız tek başına bir sayı okunduğunda kabul edilir.
            tokens = out.stdout.split()
            if len(tokens) == 1 and tokens[0].isdigit():
                value = int(tokens[0])
                break
        self.cache[key] = value if value is not None else False
        self._trim_cache()
        return value

    def text_button(self, frame, label, region=None):
        wanted = name_key(label).split()
        words = self.words(frame, region)
        for word in words:
            if name_key(word.text) != wanted[0]:
                continue
            line = sorted((w for w in words if abs(w.box.center[1] - word.box.center[1]) < 8
                           and w.box.x >= word.box.x), key=lambda w: w.box.x)
            if [name_key(w.text) for w in line[:len(wanted)]] == wanted:
                last = line[len(wanted)-1].box
                return Box(word.box.x, word.box.y, last.x + last.w - word.box.x, max(word.box.h, last.h))
        return None

    def auto_panel(self, frame):
        with METRICS.span('auto_panel'):
            return self._auto_panel(frame)

    def _title_likely(self, frame):
        """Half-resolution rejection test run before the full title match.

        The full five-scale match over a 1920x1080 frame is the most
        expensive step of observe(); on a clean map it never fires. Matching
        the same scales on a half-size copy costs a fraction of that and
        rejects that case immediately. A score at or above PANEL_FAST_REJECT
        does not decide anything: it only stops the shortcut so the exact
        matcher below can decide.
        """
        template = self.templates.get('title')
        if template is None:
            return True
        gray = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
        small = cv2.resize(gray, None, fx=PANEL_FAST_SCALE, fy=PANEL_FAST_SCALE,
                           interpolation=cv2.INTER_AREA)
        for scale in MATCH_SCALES:
            pattern = cv2.resize(template, None, fx=PANEL_FAST_SCALE*scale,
                                 fy=PANEL_FAST_SCALE*scale)
            h, w = pattern.shape
            if h > small.shape[0] or w > small.shape[1]:
                return True
            _, best, _, _ = cv2.minMaxLoc(
                cv2.matchTemplate(small, pattern, cv2.TM_CCOEFF_NORMED))
            if best >= PANEL_FAST_REJECT:
                return True
        return False

    def _auto_panel(self, frame):
        if not self._title_likely(frame):
            METRICS.bump('auto_panel_fast_reject')
            return None
        hits = self.matches(frame, 'title', threshold=.86)
        if not hits:
            return None
        title = hits[0]
        scale = title.w / 119
        x, y = round(title.x - 310*scale), round(title.y - 2*scale)
        return Box(max(0, x), max(0, y), min(round(742*scale), frame.shape[1]-max(0, x)),
                   min(round(475*scale), frame.shape[0]-max(0, y)))

    def energy(self, frame, panel):
        # The player HUD has a different 'Enerji'; only read inside this modal.
        crop = Box(panel.x + int(panel.w*.60), panel.y+int(panel.h*.045),
                   int(panel.w*.36), int(panel.h*.06))
        return parse_energy(self.detector.ocr(crop.crop(frame), psm=7, scale=3, label='energy'))

    def rows(self, frame, panel):
        region = Box(panel.x+15, panel.y+24, panel.w-42, panel.h-40)
        words = self.words(frame, region)
        buttons = self.matches(frame, 'collect', region, threshold=.86)
        rows = []
        for button in buttons:
            # Disabled buttons share the same shape. Only the red enabled
            # button may start a new collection.
            pixels=button.crop(frame).astype(np.int16)
            if not pixels.size or np.mean((pixels[:,:,0]>90)&(pixels[:,:,0]>pixels[:,:,1]*1.6)) < .20:
                continue
            name_words = sorted((w for w in words if w.box.x < panel.x+panel.w*.42
                                 and abs(w.box.center[1]-(button.center[1]-10)) < 20), key=lambda w:w.box.x)
            fish = resolve_name(' '.join(w.text for w in name_words))
            if fish:
                duration_words = [w.text for w in words if panel.x+panel.w*.42 < w.box.x < panel.x+panel.w*.6
                                  and abs(w.box.center[1]-button.center[1]) < 23]
                duration = re.search(r'\b(\d{1,3})\b', ' '.join(duration_words))
                rows.append(AutoRow(fish.id, button, int(duration[1]) if duration else int(fish.base_seconds or 30)))
        return sorted(rows, key=lambda row: row.button.y)

    def active_collection(self, frame, panel):
        """Read the visible Durdur button, including the progress above it."""
        region=Box(panel.x+15,panel.y+24,panel.w-42,panel.h-40)
        button=self.text_button(frame,'Durdur',region)
        scale=panel.w/742
        if button is None:
            # The pointer may cover the Durdur letters. A running row is also
            # distinguishable by its one red action and multiple grey actions.
            disabled=0
            for hit in self.matches(frame,'collect',region,threshold=.60):
                pixels=hit.crop(frame).astype(np.int16)
                if pixels.size and np.mean((pixels[:,:,0]>90)&(pixels[:,:,0]>pixels[:,:,1]*1.6))<.10:
                    disabled+=1
            if disabled<2:return None
            area=region.crop(frame).astype(np.int16)
            red=((area[:,:,0]>100)&(area[:,:,0]>area[:,:,1]*2)&(area[:,:,1]<85)).astype(np.uint8)
            red=cv2.morphologyEx(red,cv2.MORPH_CLOSE,np.ones((3,15),np.uint8))
            _,_,stats,_=cv2.connectedComponentsWithStats(red)
            candidates=[]
            for x,y,w,h,pixels in stats[1:]:
                if 35*scale<w<95*scale and 8*scale<h<32*scale and panel.w*.68<region.x+x-panel.x<panel.w*.83:
                    candidates.append(Box(int(region.x+x),int(region.y+y),int(w),int(h)))
            if len(candidates)!=1:return None
            button=candidates[0]
        name=Box(panel.x+round(55*scale),button.y-round(26*scale),
                 round(240*scale),round(46*scale))
        name_words=sorted((word for word in self.words(frame,region)
                           if word.box.x<panel.x+panel.w*.42
                           and abs(word.box.center[1]-(button.center[1]-10))<20),key=lambda word:word.box.x)
        fish=resolve_name(' '.join(word.text for word in name_words))
        progress_box=Box(panel.x+round(446*scale),button.center[1]-round(37*scale),
                         round(245*scale),round(24*scale))
        text=self.detector.ocr(progress_box.crop(frame),psm=7,scale=3,label='progress')
        match=re.search(r'(\d+)\s*/\s*(\d+)',text)
        progress,total=map(int,match.groups()) if match else (None,None)
        if total is not None and not (0<=progress<=total<=300):progress,total=None,None
        return ActiveCollection(fish.id if fish else None,button,progress,total)

    def inventory(self, frame):
        height,width=frame.shape[:2]
        region=(Box(int(width*.18),int(height*.12),int(width*.42),int(height*.20))
                if width>=1500 and height>=800 else Box(0,0,width,int(height*.78)))
        hits = self.matches(frame, 'capacity', region, threshold=.85)
        capacity = hits[0] if hits else self.text_button(frame, 'Kapasite', region)
        if not capacity:
            return None
        return Box(max(0, capacity.x-15), capacity.y+20, frame.shape[1]-max(0, capacity.x-15)-20,
                   max(1, int(frame.shape[0]*.77)-capacity.y-20))

    def inventory_tab(self, frame, label):
        """Return a tab hit even when the tiny tab text is hard to OCR.

        The game renders the inventory tabs immediately above the capacity row.
        On a full game screenshot the text is only a few pixels high and OCR
        often returns fragments (for example ``esvaler`` for ``Eşyalar``).  The
        capacity template gives us a stable local coordinate system, so use a
        narrow OCR pass first and a conservative geometry fallback second.
        """
        inventory = self.inventory(frame)
        if inventory is None or label not in ('Efektler', 'Eşyalar'):
            return None
        # Keep OCR local; doing this over the complete 1920px screenshot can
        # exceed the optional profession OCR timeout.
        tab_region = Box(inventory.x + int(inventory.w*.14),
                         max(0, inventory.y - 66),
                         int(inventory.w*.34), min(58, inventory.y))
        hit = self.text_button(frame, label, tab_region)
        if hit:
            return hit
        words = self.words(frame, tab_region)
        for w in words:
            k = name_key(w.text)
            if (label == 'Efektler' and any(sub in k for sub in ('efekt', 'fekt', 'tekil'))) or \
               (label == 'Eşyalar' and any(sub in k for sub in ('esya', 'esy', 'esval', 'syal'))):
                return w.box

        # Relative positions are stable across the game's browser scales: the
        # two tabs are roughly 22.2% and 27.7% into the inventory panel.
        scale = max(.55, min(1.6, inventory.w / 1453))
        offset = .222 if label == 'Efektler' else .277
        width = round(72 * scale)
        height = round(27 * scale)
        x = round(inventory.x + inventory.w * offset - width/2)
        y = max(0, inventory.y - round(60 * scale))
        return Box(max(0, x), y, width, height)

    def bag_button(self, frame):
        """Only the main character inventory; the side bag is a combat bag."""
        height, width = frame.shape[:2]
        region=Box(int(width*.18),0,int(width*.42),int(height*.23))
        hits=(self.matches(frame,'inventory',region,threshold=.85,brightness_range=(.60, 1.40))
              or self.matches(frame,'inventory-hover',region,threshold=.85))
        return hits[0] if hits else None

    def close_inventory(self, frame):
        """Locate the inventory's top-right ``Geri dön`` button."""
        inventory = self.inventory(frame)
        if inventory is None:
            return None
        scale = max(.55, min(1.6, inventory.w / 1453))
        region = Box(inventory.x + int(inventory.w*.80),
                     max(0, inventory.y - round(105*scale)),
                     max(1, int(inventory.w*.20)), min(round(100*scale), inventory.y))
        hit = self.text_button(frame, 'Geri dön', region)
        if hit:
            return hit
        hits = self.matches(frame, 'close', region, threshold=.84)
        if hits:
            return min(hits, key=lambda box: abs(box.x-(inventory.x+inventory.w-round(145*scale))))
        # The button is a fixed part of the inventory chrome.  This fallback is
        # only offered after the capacity template confirmed that this panel is
        # open, so it cannot click a random map location.
        return Box(inventory.x + inventory.w - round(172*scale),
                   max(0, inventory.y - round(90*scale)),
                   round(70*scale), round(28*scale))

    def hunt_button(self,frame):
        height,width=frame.shape[:2]
        region=Box(int(width*.18),0,int(width*.42),int(height*.23))
        hits=self.matches(frame,'hunt',region,threshold=.85) or self.matches(frame,'hunt-hover',region,threshold=.85)
        return hits[0] if hits else None

    def known_alert(self, frame):
        # Browser alert screenshots used by tests are tightly cropped, while a
        # live capture includes the whole desktop.  Search the central game
        # area first and fall back to the complete top portion for small crops.
        width, height = frame.shape[1], frame.shape[0]
        search=Box(0,0,width,height if width<900 else int(height*.78))
        buttons=self.matches(frame,'alert-ok',search)+self.matches(frame,'alert-kapat',search)
        regions=[]
        for button in buttons:
            # Read the actual message above its close button. Chat history and
            # inventory descriptions must not start a recovery operation.
            x=max(0,button.x-420);y=max(0,button.y-210)
            regions.append(Box(x,y,min(width-x,button.w+530),button.y+button.h-y+8))
        for region in regions:
            words = self.words(frame, region)
            text = ' '.join(w.text for w in words)
            reason = recovery_reason(text)
            if not reason:
                continue
            close = (self.text_button(frame, 'Tamam', region) or
                     self.text_button(frame, 'OK', region) or
                     self.text_button(frame, 'kapat', region) or
                     self.text_button(frame, 'Kapat', region))
            if close is None:
                hits = self.matches(frame, 'alert-ok', region) or self.matches(frame, 'alert-kapat', region)
                close = hits[0] if hits else None
            if close is not None:
                return (reason, close, text)
        return None

    def potion_confirmation(self, frame):
        """Return Apply only for the game's healing-potion confirmation."""
        for button in self.matches(frame,'potion-apply',threshold=.86):
            scale=button.w/90
            region=Box(max(0,button.x-round(190*scale)),max(0,button.y-round(120*scale)),
                       round(480*scale),round(192*scale))
            if not self.matches(frame,'potion-cancel',region,threshold=.86):continue
            text=' '.join(word.text for word in self.words(frame,region))
            key=name_key(text)
            if 'iksir' in key and 'kullanmak' in key and 'onayla' in key and 'kiym' in key:
                return button
        return None
