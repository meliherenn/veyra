"""Image-only game recognition. No browser DOM, network calls or game scripts."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import tempfile
import unicodedata
import hashlib
import time
import os
import fcntl

import cv2
import numpy as np
from PIL import Image

from config import (CAPTURE_TIMEOUT, OCR_TIMEOUT, PROTECTION_TEMPLATE_THRESHOLD,
                    PROTECTION_FAST_SCALE, PROTECTION_FAST_REJECT,
                    AUTO_PANEL_PROBE_INTERVAL, ROOT, TARGET_REACQUIRE_DISTANCE,
                    FISH_MASK_MIN_PIXELS)
from metrics import METRICS

try:
    from x11grab import X11Grabber
except ImportError:          # python-xlib is optional; spectacle still works
    X11Grabber = None

_DEFAULT_GRABBER = object()


def normalized(text):
    text = text.lower().replace("ı", "i")
    return " ".join("".join(c for c in unicodedata.normalize("NFKD", text)
                            if not unicodedata.combining(c)).split())


@dataclass(frozen=True)
class Layout:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self):
        return self.right - self.left

    def crop(self, frame):
        return frame[self.top + 3:self.bottom - 3, self.left + 3:self.right - 18]

    def header(self, frame, start, end, above=42, below=4):
        scale = self.width / 1520
        x1, x2 = int(self.left + start*self.width), int(self.left + end*self.width)
        y1, y2 = max(0, round(self.top-above*scale)), max(0, round(self.top-below*scale))
        return frame[y1:y2, x1:x2], (x1, y1)


@dataclass(frozen=True)
class Fish:
    x: int
    y: int
    radius: int
    score: float
    color: str = 'yesil'


@dataclass
class Observation:
    layout: Layout | None
    protection: bool = False
    harvesting: bool = False
    blocked: str | None = None
    auto_collect: bool = False
    # Engelleyen oyun uyarısı için kapat düğmesinin kare koordinatı; yalnızca
    # kapatılabilir bir uyarı penceresi görülürse dolu.
    close_button: tuple[int, int] | None = None

    @property
    def clear(self):
        return self.layout is not None and not (self.protection or self.harvesting or self.blocked or self.auto_collect)


class ScreenDetector:
    def __init__(self, grabber=_DEFAULT_GRABBER):
        self.temp = tempfile.TemporaryDirectory(prefix="dwar-fishing-")
        self.path = Path(self.temp.name)
        self._ocr_cache = {}
        # Screen region the current frame covers, in desktop coordinates.
        # None means the whole screen (the spectacle path).
        self.capture_rect = None
        # Reading the Xwayland window is ~4 ms against ~500 ms for spectacle,
        # and it never opens a dialog. A grabber of None forces the slow path.
        if grabber is _DEFAULT_GRABBER:
            self.grabber = X11Grabber() if X11Grabber else None
        else:
            self.grabber = grabber
        self.harvest_templates = []
        self.templates = []
        for p in sorted((ROOT / "assets").glob("protection-*.png")):
            template = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if template is not None:
                for scale in (0.75, 0.90, 1.0, 1.10, 1.25):
                    self.templates.append(cv2.resize(template, None, fx=scale, fy=scale))
        # Half-resolution copies used only to rule a clean screen out cheaply.
        self.fast_templates = [cv2.resize(t, None, fx=PROTECTION_FAST_SCALE, fy=PROTECTION_FAST_SCALE,
                                          interpolation=cv2.INTER_AREA)
                               for t in self.templates if min(t.shape) >= 6]
        self.auto_panel_interval = 0.0
        self._auto_panel_seen = None
        self._auto_panel_next = 0.0
        p = ROOT / 'assets' / 'harvest-title.png'
        if p.exists():
            template = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
            if template is not None:
                for scale in (.9, 1.0, 1.1):
                    self.harvest_templates.append(cv2.resize(template,None,fx=scale,fy=scale))

    def capture(self):
        with METRICS.span('capture'):
            grabbed = self.grabber.grab() if self.grabber is not None else None
            if grabbed is not None:
                METRICS.bump('capture_x11')
                frame, self.capture_rect = grabbed
            else:
                METRICS.bump('capture_spectacle')
                frame, self.capture_rect = self._capture_spectacle(), None
        if frame.shape[0] < 200 or frame.shape[1] < 400:
            raise RuntimeError("Ekran görüntüsü boyutu geçersiz; tıklama yapılmadı.")
        return frame

    def _capture_spectacle(self):
        path = self.path / "screen.png"
        # Spectacle is single-instance. Serialize local capture clients and
        # allow its asynchronous file write to finish before opening the PNG.
        lock_path=Path(tempfile.gettempdir())/f'dwar-capture-{os.getuid()}.lock'
        with lock_path.open('a') as lock:
            fcntl.flock(lock,fcntl.LOCK_EX)
            path.unlink(missing_ok=True)
            subprocess.run(["spectacle", "-b", "-n", "-f", "-o", str(path)],
                           capture_output=True, check=True, timeout=CAPTURE_TIMEOUT)
            deadline=time.monotonic()+1.5
            while not path.exists() and time.monotonic()<deadline:time.sleep(.05)
            try:
                with Image.open(path) as image:
                    return np.array(image.convert("RGB"))
            except OSError as exc:
                raise InterruptedError('Yeni ekran görüntüsü hazır değil; tıklamadan tekrar denenecek.') from exc

    def ocr(self, frame, psm=6, scale=2, label=None):
        if frame.size == 0:
            return ""
        key = (frame.shape, psm, scale, hashlib.blake2b(frame.tobytes(),digest_size=12).digest())
        # The key is the exact pixel content, so a hit is always valid no
        # matter how old it is.  A time-to-live here only forced repeated
        # ~0.4 s tesseract runs on a frame that had not changed at all.
        cached = self._ocr_cache.pop(key, None)
        if cached is not None:
            self._ocr_cache[key] = cached
            METRICS.bump('ocr_cache_hit')
            return cached[1]
        METRICS.bump('ocr_calls')
        if label:
            METRICS.bump(f'ocr_{label}')   # maliyetin hangi cagri noktasindan geldigini gosterir
        with METRICS.span('ocr'):
            im = Image.fromarray(frame)
            if scale != 1:
                im = im.resize((im.width*scale, im.height*scale))
            path = self.path / "ocr.png"
            im.save(path)
            try:
                # --oem 1 (LSTM tek basina): eski motor+kalitim birlesimi ~2 kat
                # yavas; 15 kirpida anlam metni ayni kaldi, sure 320 -> 175 ms.
                # Ayni oturumda calissin ki terminal Ctrl+C tesseract'i oldurup
                # temiz durusu "Bot hata nedeniyle durdu" yapmasin: Python kendi
                # SIGINT isleyicisiyle durur, OCR ise tamamlanir.
                result = subprocess.run(["tesseract", str(path), "stdout", "-l", "tur+eng",
                                         "--psm", str(psm), "--oem", "1"], capture_output=True, text=True,
                                        check=True, timeout=OCR_TIMEOUT,
                                        env=dict(os.environ,OMP_THREAD_LIMIT='1'),
                                        start_new_session=True)
            except subprocess.TimeoutExpired as exc:
                raise InterruptedError('Ekran yazısı zamanında okunamadı; tıklamadan yeniden kontrol edilecek.') from exc
            text = normalized(result.stdout)
        self._ocr_cache[key] = (time.monotonic(),text)
        # Vurus yolunda pop + yeniden ekleme oldugundan ilk anahtar en eskidir
        # (LRU benzeri). dict.popitem() keyword almaz; eskisini Boyle buduyoruz.
        while len(self._ocr_cache) > 64:
            self._ocr_cache.pop(next(iter(self._ocr_cache)))
        return text

    def detect_layout(self, frame):
        # The thin upper border is stable across map scrolling and Chrome banners.
        top_mask = cv2.inRange(frame,(242,242,156),(255,255,182)) // 255
        bottom_mask = cv2.inRange(frame,(242,219,156),(255,245,182)) // 255
        width = frame.shape[1]
        minimum = min(600, int(width*0.45))
        for top in np.where(top_mask.sum(axis=1) > minimum)[0]:
            spans = cv2.morphologyEx(top_mask[top:top+1], cv2.MORPH_CLOSE,
                                     np.ones((1, 150), np.uint8))
            n, _, stats, _ = cv2.connectedComponentsWithStats(spans, connectivity=8)
            for x, _, w, _, area in stats[1:n]:
                if area < minimum:
                    continue
                actual_x = np.where(top_mask[top, x:x+w])[0]
                if len(actual_x) < minimum:
                    continue
                x, w = int(x + actual_x[0]), int(actual_x[-1] - actual_x[0] + 1)
                bottom_rows = np.where(bottom_mask[:, x:x+w].sum(axis=1) > w*0.80)[0]
                bottom_rows = bottom_rows[bottom_rows > top + 120]
                if len(bottom_rows):
                    bottom = int(bottom_rows[0])
                    return Layout(int(x), int(top), int(x+w), bottom)
        return None

    def protection_template(self, frame):
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame[int(h*.15):int(h*.88), int(w*.18):int(w*.82)], cv2.COLOR_RGB2GRAY)
        found = False
        with METRICS.span('protection_template'):
            # A clean screen scores far below the fast threshold on every known
            # negative, so the expensive full-resolution pass is skipped ~95%
            # of the time. Anything ambiguous still gets the authoritative pass.
            small = cv2.resize(gray, None, fx=PROTECTION_FAST_SCALE, fy=PROTECTION_FAST_SCALE,
                               interpolation=cv2.INTER_AREA)
            best = -1.0
            for template in self.fast_templates:
                if template.shape[0] <= small.shape[0] and template.shape[1] <= small.shape[1]:
                    score = cv2.minMaxLoc(cv2.matchTemplate(small, template, cv2.TM_CCOEFF_NORMED))[1]
                    if score > best:
                        best = score
            if best < PROTECTION_FAST_REJECT:
                METRICS.bump('protection_shortcut')
            else:
                for template in self.templates:
                    if template.shape[0] <= gray.shape[0] and template.shape[1] <= gray.shape[1]:
                        score = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))[1]
                        if score >= PROTECTION_TEMPLATE_THRESHOLD:
                            found = True
                            break
        return found

    @staticmethod
    def protection_text(text):
        text = normalized(text)
        return any(phrase in text for phrase in
                   ("bot koruma", "guvenlik dogrula", "yapboz", "captcha", "yeni puzzle"))

    def check_bot_protection(self, frame, protection=None):
        if protection is None:
            protection = self.protection_template(frame)
        if protection:
            return True, "Bot koruması başlığı ekranda görüldü."
        h, w = frame.shape[:2]
        text = self.ocr(frame[int(h*.23):int(h*.82), int(w*.25):int(w*.75)], psm=11, scale=1,
                        label='protection')
        result = self.protection_text(text)
        return result, "Bot koruması yazısı algılandı." if result else None

    @staticmethod
    def water_mask(crop):
        r, g, b = crop.astype(np.int16).transpose(2, 0, 1)
        return ((b > r + 12) & (b > 65) & (b > g*.85)).astype(np.uint8)

    def fishing_water(self,crop,color):
        water=self.water_mask(crop)
        if color=='beyaz':
            # White stone edges need stronger water evidence than vivid rings.
            _,g,b=crop.astype(np.int16).transpose(2,0,1)
            water=water & (b>g+12).astype(np.uint8)
        return water

    @staticmethod
    def _fish_color_masks(crop, colors=None):
        r, g, b = crop.astype(np.int16).transpose(2, 0, 1)
        formulas = {
            'yesil': lambda: (g>110)&(g>r+40)&(g>b+25)&(b>20),
            'beyaz': lambda: (r>150)&(g>160)&(b>170)&(abs(r-g)<60)&(abs(g-b)<60),
            'mavi': lambda: (b>185)&(b>r+100)&(g>135)&(g>r+65),
            'mor': lambda: (b>125)&(b>g+25)&(r>70)&(r>g+15),
            'kirmizi': lambda: (r>150)&(r>g+60)&(r>b+30),
            'sari': lambda: (r>165)&(g>145)&(b<130)&(r>b+55),
        }
        # Tek renk seciliyken bes renk hesaplamanin anlami yok; formuller
        # birbirinden bagimsiz, o yuzden sonuc piksel piksel ayni kaliyor.
        if colors is None:
            wanted = formulas
        else:
            wanted = {c: formulas[c] for c in ((colors,) if isinstance(colors, str) else colors)}
        return {color: mask() for color, mask in wanted.items()}

    def find_fish_ripples(self, frame, layout=None, target_color="all"):
        if target_color not in ('all','yesil','beyaz','mavi','mor','kirmizi','sari'):
            raise ValueError('Halka rengi tanınmadı.')
        with METRICS.span('ripples'):
            return self._find_fish_ripples(frame, layout, target_color)

    def _find_fish_ripples(self, frame, layout, target_color):
        layout = layout or self.detect_layout(frame)
        if layout is None:
            return []
        crop = layout.crop(frame)
        scale = layout.width / 1520
        masks = self._fish_color_masks(crop, None if target_color == 'all' else target_color)
        found = []
        for color,color_mask in masks.items():
            if target_color not in ('all',color):
                continue
            water=self.fishing_water(crop,color)
            near_water=cv2.dilate(water,np.ones((9,9),np.uint8))>0
            mask=(color_mask & near_water).astype(np.uint8)*255
            # Kabul kriteri adayin kendisinde de FISH_MASK_MIN_PIXELS piksel
            # istiyor ve aday her zaman maske icinde kaliyor; maskede o degerden
            # az piksel varsa Hough ne bulursa bulsun elenirdi. Bos maske
            # aramamak ~49 ms kazandiriyor (olculen deger).
            if np.count_nonzero(mask) < FISH_MASK_MIN_PIXELS:
                continue
            circles=cv2.HoughCircles(cv2.GaussianBlur(mask,(3,3),0),cv2.HOUGH_GRADIENT,
                                    dp=1,minDist=max(12,round(22*scale)),param1=60,param2=9,
                                    minRadius=max(5,round(7*scale)),maxRadius=max(10,round(24*scale)))
            if circles is None:
                continue
            for x,y,radius in np.rint(circles[0]).astype(int):
                margin=max(10,radius)
                if x-margin<0 or y-margin<0 or x+margin>=crop.shape[1] or y+margin>=crop.shape[0]:
                    continue
                water_ratio=float(water[y-margin:y+margin+1,x-margin:x+margin+1].mean())
                pixels=int(np.count_nonzero(mask[y-margin:y+margin+1,x-margin:x+margin+1]))
                if water_ratio>.55 and pixels>=FISH_MASK_MIN_PIXELS:
                    found.append(Fish(int(x+layout.left+3),int(y+layout.top+3),int(radius),water_ratio*pixels,color))
        unique=[]
        for fish in sorted(found,key=lambda f:f.score,reverse=True):
            if not any(np.hypot(fish.x-f.x,fish.y-f.y)<12 for f in unique):
                unique.append(fish)
        return unique

    def reacquire_fish(self, frame, layout, target, max_distance=TARGET_REACQUIRE_DISTANCE):
        """Find the same moving fish near its previous position.

        The normal Hough detector is tried first.  If the animated ring is between
        Hough-friendly frames, a small same-colour ROI is used as a conservative
        fallback.  This method never changes fish colour and never searches the
        whole map for an unrelated replacement target.
        """
        if layout is None or target.color not in ('yesil','beyaz','mavi','mor','kirmizi','sari'):
            return None
        scale = max(.5, layout.width / 1520)
        limit = max(24.0, float(max_distance) * scale)

        same_color = self.find_fish_ripples(frame, layout, target_color=target.color)
        nearby = [fish for fish in same_color if np.hypot(fish.x-target.x, fish.y-target.y) <= limit]
        closest = min(nearby, key=lambda fish: np.hypot(fish.x-target.x, fish.y-target.y)) if nearby else None
        if closest and np.hypot(closest.x-target.x, closest.y-target.y) <= max(6, target.radius*.6):
            return closest

        crop = layout.crop(frame)
        if crop.size == 0:
            return None
        origin_x, origin_y = layout.left + 3, layout.top + 3
        cx, cy = target.x-origin_x, target.y-origin_y
        pad = int(round(limit + max(18, target.radius*1.6)))
        x1, x2 = max(0, cx-pad), min(crop.shape[1], cx+pad+1)
        y1, y2 = max(0, cy-pad), min(crop.shape[0], cy+pad+1)
        if x2-x1 < 12 or y2-y1 < 12:
            return None

        roi = crop[y1:y2, x1:x2]
        color_mask = self._fish_color_masks(roi, target.color)[target.color]
        water = self.fishing_water(roi,target.color)
        near_water = cv2.dilate(water, np.ones((9,9),np.uint8)) > 0
        mask = (color_mask & near_water).astype(np.uint8) * 255
        # Connect short animated ring arcs without joining distant fish.
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5,5))
        connected = cv2.dilate(cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel), kernel, iterations=1)
        count, labels, stats, centroids = cv2.connectedComponentsWithStats(connected, connectivity=8)
        # A full circle nearby can be a different fish while the selected
        # ring is between animation frames. Compare local arc evidence before
        # substituting that circle, rather than always preferring Hough.
        candidates=[]
        if closest:
            distance=float(np.hypot(closest.x-target.x,closest.y-target.y))
            candidates.append((distance,-closest.score,closest))
        for label in range(1,count):
            x,y,w,h,area = stats[label]
            if area < 22 or w > 70*scale or h > 70*scale:
                continue
            component = labels == label
            raw = (mask > 0) & component
            pixels = int(raw.sum())
            if pixels < 18:
                continue
            yy,xx = np.nonzero(raw)
            if not len(xx):
                continue
            local_x=float(np.median(xx)); local_y=float(np.median(yy))
            full_x=origin_x+x1+local_x; full_y=origin_y+y1+local_y
            distance=float(np.hypot(full_x-target.x,full_y-target.y))
            if distance > limit:
                continue
            radius=max(6,int(round(max(w,h)/2)))
            score=float(pixels)/(1.0+distance)
            candidates.append((distance,-score,Fish(round(full_x),round(full_y),radius,score,target.color)))
        if not candidates:
            return None
        candidates.sort(key=lambda item:(item[0],item[1]))
        return candidates[0][2]

    def find_yakala_button(self, frame, layout=None):
        layout = layout or self.detect_layout(frame)
        if not layout:
            return None
        crop, (x, y) = layout.header(frame, .315, .360, above=24, below=11)
        text = self.ocr(crop, psm=7, scale=3, label='yakala')
        if re.search(r"\byakala\b", text):
            # 'yakala' is a label. The adjacent round fish icon performs the action.
            return round(layout.left + layout.width*.265), round(layout.top - 24*layout.width/1520)
        return None

    def selected_fish_name(self, frame, layout):
        crop, _ = layout.header(frame, .581, .670, above=32, below=20)
        return self.ocr(crop, psm=7, scale=4, label='name')

    def selected_fish_color(self,frame,layout):
        crop,_=layout.header(frame,.635,.675,above=16,below=6)
        if not crop.size:return None
        r,g,b=crop.astype(np.int16).transpose(2,0,1)
        masks={
            'yesil':(g>100)&(g>r+45)&(g>b+35),
            'mavi':(b>140)&(r<b*.30)&(b>g+20),
            'mor':(b>110)&(r>b*.30)&(g<100)&(r>g+25)&(b>g+35),
            'kirmizi':(r>150)&(g<80)&(b<100),
            'sari':(r>190)&(g>=80)&(g<170)&(b<85)&(r>g+55),
            'beyaz':(r>160)&(g>160)&(b>160)&(abs(r-g)<22)&(abs(g-b)<22),
        }
        counts=sorted(((int(mask.sum()),color) for color,mask in masks.items()),reverse=True)
        return counts[0][1] if counts[0][0]>=8 else None

    def _panels(self, frame, layout):
        region, _origin = self._modal_region(frame, layout)
        if self.harvest_templates:
            gray=cv2.cvtColor(region,cv2.COLOR_RGB2GRAY)
            for template in self.harvest_templates:
                if all(a<=b for a,b in zip(template.shape,gray.shape)):
                    score=cv2.minMaxLoc(cv2.matchTemplate(gray,template,cv2.TM_CCOEFF_NORMED))[1]
                    if score>=.86:
                        return True,None,None
        r, g, b = region.astype(np.int16).transpose(2, 0, 1)
        red = ((r > 95) & (g < 65) & (b < 70) & (r > g*2)).astype(np.uint8)
        red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, 21), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(red)
        for x, y, pw, ph, area in stats[1:n]:
            if pw >= 180 and ph >= 8 and area >= 800:
                title = self.ocr(region[max(0,y-2):min(region.shape[0],y+ph+3),
                                        x+int(pw*.32):x+int(pw*.68)], psm=7, scale=3,
                                 label='panel_title')
                if "toplama" in title:
                    return True, None, None
                text_height=round(29*layout.width/1520)
                body=self.ocr(region[y+ph+3:min(region.shape[0],y+ph+text_height),
                                     x+int(pw*.06):x+int(pw*.94)],psm=7,scale=3,
                              label='panel_body')
                if 'ustalig' in body or 'ustalig' in title:
                    return False,'Yeterli ustalığınız yok. Panelde ustalık sınırını veya hedefleri değiştirin.',None
                # Uyarı geçicidir ve oyunun kendi düğmesiyle kapatılabilir;
                # ustalık uyarısı ise kullanıcının paneli değiştirmesini bekler.
                # Sarı üstündeki başlık OCR'i güvenilmez olduğu için ("——" diye
                # okunuyor) gövde başlık 'hata' olmasa da her zaman okunur:
                # eksik alet uyarısı ("Gerekli alete sahip değilsiniz!") ancak
                # böyle tanınıp olta takma akışına girebiliyor.
                if body or 'hata' in title:
                    return False,f'Oyun uyarısı: {(body or title)[:140]}',self.find_close_button(frame, layout)
                return False, f"Beklenmeyen oyun penceresi: {title[:100] or 'başlık okunamadı'}", None
        brown = ((r > 45) & (r < 145) & (g > 24) & (g < 110) & (b > 15)
                 & (b < 80) & (r > g*1.3) & (g > b*1.25)).astype(np.uint8)
        n, _, stats, _ = cv2.connectedComponentsWithStats(brown)
        if any(pw > 240 and ph > 120 and area > 14000 for x, y, pw, ph, area in stats[1:n]):
            return False, "Ekranda tanınmayan bir pencere var.", None
        return False, None, None

    @staticmethod
    def _modal_region(frame, layout):
        """_panels'in baktığı bölge ve başlangıcının kare koordinatları."""
        crop = layout.crop(frame)
        h, w = crop.shape[:2]
        x1, x2 = int(w*.20), int(w*.85)
        return crop[30:h-15, x1:x2], (layout.left + 3 + x1, layout.top + 33)

    def find_close_button(self, frame, layout):
        """Engelleyen oyun uyarısı penceresinin kapat düğmesinin merkezi.

        Hata modalları kırmızı başlık çubuğunun altında kırmızı bir düğme
        gösterir. Kutu kırmızı bileşen olarak ölçülür; gövde metni aynı
        renkte olsa da satır yüksekliği ve konumuyla ayrılır. Bulunamazsa
        dokunulmaz: kör bir konuma tıklamak yerine yeniden denenir.
        """
        if layout is None:
            return None
        region, origin = self._modal_region(frame, layout)
        for x, y, pw, ph, _area in self._red_bars(region):
            close = self._close_button(region, origin, x, y, pw, ph, layout)
            if close:
                return close
        return None

    SEA_BAND_MAX = 0.45
    SEA_DENSE = 0.20

    def sea_extends_vertically(self, frame, layout):
        """Haritanın suyu dikeyde uzanıyorsa tekerlek kaydırmak anlamlıdır.

        Bazı haritalarda deniz yalnızca genişliği boyunca bir şerittir; yukarı
        veya aşağı kaydırmak suyu görüşten çıkarır ve boşuna zaman harcanır.
        Bir satır ancak çoğunlukla suysa deniz satırı sayılır (kıyı köpüğü ya
        da dağınık su pikselleri şeridi olduğundan sanılmaz) ve en uzun sürekli
        deniz şeridi haritanın yarısından kısaysa dikey kaydırma yapılmaz.
        Su hiç okunamazsa ya da deniz satırı bulunamazsa (ör. çok dar bir
        nehir) kaydırma engellenmez: mevcut davranış korunur.
        """
        if layout is None:
            return True
        crop = layout.crop(frame)
        if crop.size == 0:
            return True
        r, g, b = crop.astype(np.int16).transpose(2, 0, 1)
        water = (b > 90) & (b > r + 25) & (b > g + 10)
        if water.mean() < 0.01:
            return True
        dense = np.flatnonzero(water.mean(axis=1) > self.SEA_DENSE)
        if dense.size == 0:
            return True
        runs = np.split(dense, np.flatnonzero(np.diff(dense) > 1) + 1)
        band = max(len(run) for run in runs)
        return bool(band >= self.SEA_BAND_MAX * crop.shape[0])

    @staticmethod
    def _red_bars(region):
        """Başlık çubuğu gibi görünen yatay kırmızı bileşenler."""
        r, g, b = region.astype(np.int16).transpose(2, 0, 1)
        red = ((r > 95) & (g < 65) & (b < 70) & (r > g*2)).astype(np.uint8)
        red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, 21), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(red)
        return [s for s in stats[1:n] if s[2] >= 180 and s[3] >= 8 and s[4] >= 800]

    @staticmethod
    def _close_button(region, origin, x, y, pw, ph, layout):
        """Başlık çubuğunun altındaki kapat düğmesinin kare koordinatı."""
        scale = layout.width / 1520
        y0 = y + ph + int(15*scale)
        y1 = min(region.shape[0], y + ph + int(95*scale))
        if y0 >= y1:
            return None
        search = region[y0:y1, x:min(region.shape[1], x+pw)]
        if not search.size:
            return None
        r, g, b = search.astype(np.int16).transpose(2, 0, 1)
        red = ((r > 95) & (g < 65) & (b < 70) & (r > g*2)).astype(np.uint8)
        red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, 21), np.uint8))
        n, _, stats, _ = cv2.connectedComponentsWithStats(red)
        # Gövde satırı 11 px, kapat düğmesi 17 px yüksekliğinde ölçülüyor;
        # 14 px alt sınırı ikisini ayırıyor.
        best = None
        for bx, by, bw, bh, area in stats[1:n]:
            if bh >= 14*scale and bw >= 60*scale and area >= 400 and (
                    best is None or area > best[4]):
                best = (bx, by, bw, bh, area)
        if best is None:
            return None
        bx, by, bw, bh, _ = best
        return (int(origin[0] + x + bx + bw//2), int(origin[1] + y0 + by + bh//2))


    def observe(self, frame):
        with METRICS.span('observe'):
            return self._observe(frame)

    def auto_panel_probe(self, frame, force=False):
        """Profession-panel check, rate-limited while no panel is visible.

        This is the most expensive step of observe() on a clean screen. A
        panel that is already open must still be seen on every frame, so the
        interval only applies once the panel has been ruled out. Input guards
        always call with force=True, so a click can never be issued while the
        panel is covering the map.
        """
        now = time.monotonic()
        if not force and self._auto_panel_seen is None and now < self._auto_panel_next:
            METRICS.bump('auto_panel_skipped')
            return False
        if not hasattr(self, 'profession_vision'):
            from profession_vision import ProfessionVision
            self.profession_vision = ProfessionVision(self)
        panel = self.profession_vision.auto_panel(frame)
        self._auto_panel_seen = panel
        self._auto_panel_next = now + (0.0 if panel is not None else self.auto_panel_interval)
        return panel is not None

    def _observe(self, frame):
        protection = self.protection_template(frame)
        if protection:
            return Observation(None, protection=True, blocked="Bot koruması; kullanıcı bekleniyor.")
        layout = self.detect_layout(frame)
        # Recognize this modal before the generic Toplama detector; it can run
        # continuously and must never be counted as one manual harvest.
        if self.auto_panel_probe(frame):
            protected,reason=self.check_bot_protection(frame, protection)
            return Observation(layout,protection=protected,blocked=reason,auto_collect=not protected)
        if layout is None:
            protection, reason = self.check_bot_protection(frame, protection)
            return Observation(None, protection=protection,
                               blocked=reason or "Avlan haritası görünmüyor veya ekran değişti.")
        harvesting, blocked, close = self._panels(frame, layout)
        if blocked:
            protection, reason = self.check_bot_protection(frame, protection)
            return Observation(layout, protection=protection, blocked=reason or blocked,
                               close_button=close)
        # A validated map can show only land after scrolling. Its protection
        # heading and modal checks above still run before the search may scroll.
        return Observation(layout, harvesting=harvesting)

    def close(self):
        self.temp.cleanup()
