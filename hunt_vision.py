"""Yaratık avı için görüntü tanıma. Yalnızca ekran görüntüsü; DOM/ağ yok."""
from __future__ import annotations

from dataclasses import dataclass, replace
import hashlib
import re

import cv2
import numpy as np

from config import (ROOT, HUNT_SPRITE_DY, HUNT_LABEL_MIN_V, HUNT_LABEL_MIN_S,
                    HUNT_ATTACK_TEMPLATE_THRESHOLD)
from hunt_catalog import parse_label
from metrics import METRICS

# Etiket renkleri: sarı (Maharetli Fitsilya) ve limon yeşili (Krogan). Ton
# aralığı ikisini de kapsar; yeni bir renk görülürse burası genişletilir.
HUE_LO, HUE_HI = 22, 45
YELLOW_MAX_HUE = 35


@dataclass(frozen=True)
class Sighting:
    """Haritada görülen bir yaratık. x,y: tıklama noktası (gövde tahmini)."""
    x: int
    y: int
    label_x: int
    label_y: int
    width: int
    height: int
    color: str
    name: str = ''
    level: int | None = None
    species_id: str = ''
    # FishingBot.reset_target Fish gibi radius bekler.
    radius: int = 14


class HuntVision:
    def __init__(self, detector):
        self.detector = detector
        self._label_cache = {}
        self.attack_template = None
        path = ROOT / 'assets' / 'hunt-attack-icon.png'
        if path.exists():
            template = cv2.imread(str(path), cv2.IMREAD_COLOR)
            if template is not None:
                self.attack_template = cv2.cvtColor(template, cv2.COLOR_BGR2RGB)

    # ------------------------------------------------------------------ harita
    @staticmethod
    def scale(layout):
        return layout.width / 1520

    def find_labels(self, frame, layout):
        """Haritadaki yaratık etiketleri (ad okunmadan), yukarıdan aşağı."""
        with METRICS.span('hunt_labels'):
            return self._find_labels(frame, layout)

    def _find_labels(self, frame, layout):
        crop = layout.crop(frame)
        if crop.size == 0:
            return []
        s = self.scale(layout)
        ox, oy = layout.left + 3, layout.top + 3
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        mask = cv2.inRange(hsv, (HUE_LO, HUNT_LABEL_MIN_S, HUNT_LABEL_MIN_V), (HUE_HI, 255, 255))
        if not mask.any():
            return []
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(3, round(9*s)), 3))
        closed = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
        count, _, stats, _ = cv2.connectedComponentsWithStats(closed, connectivity=8)
        found = []
        for i in range(1, count):
            x, y, w, h, area = (int(v) for v in stats[i])
            if not (28*s <= w <= 220*s and 6*s <= h <= 19*s and area >= 70*s*s):
                continue
            # Haritanın kenarında yarım kalmış etiket tıklanacak yeri belirsiz kılar.
            if x < 2 or y < 2 or x + w > crop.shape[1] - 2 or y + h > crop.shape[0] - 2:
                continue
            cx, cy = x + w//2 + ox, y + h//2 + oy
            sprite_y = round(cy + HUNT_SPRITE_DY*s)
            if sprite_y < layout.top + 8:
                continue
            hues = hsv[y:y+h, x:x+w][mask[y:y+h, x:x+w] > 0][:, 0]
            color = 'sari' if float(np.median(hues)) < YELLOW_MAX_HUE else 'yesil'
            found.append(Sighting(cx, sprite_y, cx, cy, w, h, color))
        return sorted(found, key=lambda t: (t.label_y, t.label_x))

    # (min doygunluk, min parlaklık, büyütme, tesseract psm). Yüksek doygunluk çim
    # rengini eler; ilk varyant çoğu etiketi tek seferde doğru okur.
    OCR_VARIANTS = ((180, 120, 6, 7), (180, 150, 5, 7), (120, 150, 5, 7), (180, 120, 4, 8))

    def _label_crop(self, frame, sighting):
        x0, x1 = sighting.label_x - sighting.width//2 - 6, sighting.label_x + sighting.width//2 + 8
        y0, y1 = sighting.label_y - sighting.height//2 - 4, sighting.label_y + sighting.height//2 + 5
        return frame[max(0, y0):y1, max(0, x0):x1]

    def read_label(self, frame, sighting, accept=None):
        """Etiketi OCR ile oku (ad + seviye).

        Etiketler küçük ve çim üstünde olduğundan tek bir ön işleme yetmez: makul
        bir okuma (seviye var ve accept(ad) doğru) çıkana kadar varyantlar denenir.
        Sonuç, etiketin yazı maskesine göre önbelleğe alınır.
        """
        crop = self._label_crop(frame, sighting)
        if crop.size == 0:
            return sighting
        hsv = cv2.cvtColor(crop, cv2.COLOR_RGB2HSV)
        primary = cv2.inRange(hsv, (HUE_LO, 180, 120), (HUE_HI, 255, 255))
        key = (primary.shape, hashlib.blake2b(primary.tobytes(), digest_size=12).digest())
        cached = self._label_cache.get(key)
        if cached is None:
            cached = self._read_variants(hsv, accept)
            if len(self._label_cache) >= 256:
                self._label_cache.pop(next(iter(self._label_cache)))
            self._label_cache[key] = cached
        name, level = cached
        return replace(sighting, name=name, level=level)

    def _read_variants(self, hsv, accept):
        fallback = None
        for smin, vmin, scale, psm in self.OCR_VARIANTS:
            mask = cv2.inRange(hsv, (HUE_LO, smin, vmin), (HUE_HI, 255, 255))
            if not mask.any():
                continue
            clean = cv2.resize(255 - mask, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
            clean = cv2.copyMakeBorder(clean, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
            name, level = parse_label(self.detector.ocr(clean, psm=psm, scale=1, label='creature'))
            if level is None or len(name) < 3:
                continue
            if accept is None or accept(name):
                return name, level
            fallback = fallback or (name, level)
        return fallback or ('', None)

    def reacquire(self, frame, layout, target, max_distance=42):
        """Aynı yaratığı hedefin eski yakınında yeniden bul (yavaş gezinirler)."""
        s = self.scale(layout)
        limit = max(20.0, max_distance*s)
        best = None
        for candidate in self.find_labels(frame, layout):
            if candidate.color != target.color or abs(candidate.width - target.width) > 4*s:
                continue
            distance = float(np.hypot(candidate.label_x - target.label_x,
                                      candidate.label_y - target.label_y))
            if distance <= limit and (best is None or distance < best[0]):
                best = (distance, candidate)
        if best is None:
            return None
        # Ad/seviye ilk okumadan taşınır: yalnızca konum yenilenir.
        return replace(best[1], name=target.name, level=target.level, species_id=target.species_id)

    # ------------------------------------------------------ seçim ve saldırı
    @staticmethod
    def _ring_mask(region):
        r, g, b = region.astype(np.int16).transpose(2, 0, 1)
        return (r >= 135) & (r <= 175) & (g >= 205) & (g <= 238) & (b <= 25) & (g - r >= 45)

    def ring_near(self, frame, layout, x, y):
        """Seçili yaratığın yeşil halkası (x, y) civarında mı? -> (var mı, merkez)."""
        s = self.scale(layout)
        half = round(45*s)
        y1, x1 = max(0, y - half), max(0, x - half)
        region = frame[y1:y + half + 1, x1:x + half + 1]
        if region.size == 0:
            return False, None
        ys, xs = np.nonzero(self._ring_mask(region))
        if len(xs) < 120*s*s:
            return False, None
        center = (float(xs.mean()) + x1, float(ys.mean()) + y1)
        ok = np.hypot(center[0] - x, center[1] - y) <= 14*s
        return bool(ok), (round(center[0]), round(center[1]))

    def attack_button(self, frame, layout):
        """Sol üstteki 'saldır' düğmesi görünüyorsa tıklama noktası, yoksa None.

        Düğme balıktaki 'yakala' ile aynı yuvada durur; simgesi şablonla ayırt edilir.
        """
        if layout is None or self.attack_template is None:
            return None
        s = self.scale(layout)
        cx, cy = round(layout.left + layout.width*.265), round(layout.top - 24*s)
        template = self.attack_template
        if abs(s - 1) > .01:
            template = cv2.resize(template, None, fx=s, fy=s, interpolation=cv2.INTER_AREA)
        pad = round(template.shape[0]/2 + 14*s)
        roi = frame[max(0, cy - pad):cy + pad, max(0, cx - pad):cx + pad]
        if roi.shape[0] < template.shape[0] or roi.shape[1] < template.shape[1]:
            return None
        score = float(cv2.minMaxLoc(cv2.matchTemplate(roi, template, cv2.TM_CCOEFF_NORMED))[1])
        return (cx, cy) if score >= HUNT_ATTACK_TEMPLATE_THRESHOLD else None

    def selected_name(self, frame, layout):
        """Üst orta bilgi kutusundaki seçili yaratığın adı (OCR, normalize)."""
        return self.detector.selected_fish_name(frame, layout)

    # -------------------------------------------------------------- sonuç ekranı
    @staticmethod
    def _red_bars(frame, s):
        r, g, b = frame.astype(np.int16).transpose(2, 0, 1)
        red = ((r > 95) & (g < 65) & (b < 70) & (r > g*2)).astype(np.uint8)
        red = cv2.morphologyEx(red, cv2.MORPH_CLOSE, np.ones((3, max(3, round(21*s))), np.uint8))
        count, _, stats, _ = cv2.connectedComponentsWithStats(red)
        return [tuple(int(v) for v in st) for st in stats[1:count]
                if 140*s <= st[2] <= 260*s and 12*s <= st[3] <= 30*s and st[4] >= 600*s*s]

    def result_button(self, frame, scale=1.0):
        """Dövüş sonu 'İstatistikler' penceresindeki 'Ava' düğmesinin merkezi.

        Pencerede üst üste aynı yükseklikte üç kırmızı düğme vardır
        (Konuma / Sırt çantasına / Ava). Sağdaki olan 'Ava' ayrıca OCR ile doğrulanır.
        """
        bars = sorted(self._red_bars(frame, scale), key=lambda b: (b[1], b[0]))
        for i, first in enumerate(bars):
            row = [b for b in bars if abs(b[1] - first[1]) <= 3*scale]
            if row[0] is not first or len(row) != 3:
                continue
            if max(b[2] for b in row) - min(b[2] for b in row) > 10*scale:
                continue
            x, y, w, h, _ = row[-1]
            text = self.detector.ocr(frame[y:y + h, x:x + w], psm=7, scale=3, label='result')
            if re.search(r'\bava\b', text):
                return (x + w//2, y + h//2)
        return None
