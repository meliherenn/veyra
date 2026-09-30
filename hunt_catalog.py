"""Yaratık adları: etiket ("Ad[seviye]") okuma ve bulanık eşleştirme."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
import re
import unicodedata

from config import HUNT_NAME_MATCH_RATIO


@dataclass(frozen=True)
class Species:
    id: str
    name: str


# Ekranda görülüp doğrulanan yaratıklar. Buradaki liste bir sınır değildir:
# --creatures ile verilen herhangi bir ad da kabul edilir.
KNOWN = (
    Species('maharetli_fitsilya', 'Maharetli Fitsilya'),
    Species('krogan', 'Krogan'),
)
ALL = 'all'


def normalize(text: str) -> str:
    text = (text or '').lower().replace('ı', 'i')
    text = ''.join(c for c in unicodedata.normalize('NFKD', text) if not unicodedata.combining(c))
    return ' '.join(re.sub(r'[^a-z0-9\[\]\(\) ]+', ' ', text).split())


def slug(name: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', normalize(name)).strip('_')


_LABEL = re.compile(r'^(?P<name>.*?)[\s\[\(\{|]*(?P<level>\d{1,3})[\]\)\}|\s]*$')


def parse_label(text: str):
    """'krogan[4]' -> ('krogan', 4). Seviye okunamazsa (ad, None)."""
    text = normalize(text)
    found = _LABEL.match(text)
    if found and found.group('name').strip():
        return found.group('name').strip(' []()'), int(found.group('level'))
    return text.strip(' []()'), None


def similarity(a: str, b: str) -> float:
    a, b = normalize(a).strip(' []()'), normalize(b).strip(' []()')
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def name_score(text: str, name: str) -> float:
    """OCR metninin türe en yüksek benzerliği.

    Seçili yaratığın üst bilgi kutusunda adın yanındaki ⓘ simgesi OCR'e
    karışır ('krogan od'); tam metin benzerliği bu gürültü yüzünden eşiği
    geçemez. Bu yüzden metnin ardışık kelime dizileri de karşılaştırılır ve
    en iyi skor döner.
    """
    words = normalize(text).strip(' []()').split()
    if not words:
        return 0.0
    best = similarity(' '.join(words), name)
    for i in range(len(words)):
        for j in range(i + 1, len(words) + 1):
            score = similarity(' '.join(words[i:j]), name)
            if score > best:
                best = score
    return best


def match_species(text: str, pool, ratio: float = HUNT_NAME_MATCH_RATIO):
    """Havuzdaki en yakın türü döndür; yeterince benzeyen yoksa None.

    Eşit skorlarda daha uzun (özgül) ad kazanır: OCR 'krogan muhafizi' okurken
    havuzdaki her iki 'krogan' türü de 1.0 almasın da gerçek hedef seçilsin.
    """
    name, _ = parse_label(text)
    best, best_key = None, (ratio, 0)
    for species in pool:
        score = name_score(name, species.name)
        key = (score, len(normalize(species.name)))
        if score >= ratio and key > best_key:
            best, best_key = species, key
    return best


def resolve_requested(values):
    """CLI/GUI değerlerinden (ad ya da kimlik) seçilen türler.

    Dönüş: (seçili türler, hepsi mi). 'all' bilinmeyen adlar dahil her yaratığı
    kabul eder. Boş liste bilinen tüm yaratıkları seçer.
    """
    values = [v for v in (values or []) if str(v).strip()]
    if not values:
        return tuple(KNOWN), False
    if any(normalize(str(v)) == ALL for v in values):
        return tuple(KNOWN), True
    chosen = []
    for value in values:
        by_id = next((s for s in KNOWN if s.id == slug(str(value))), None)
        species = by_id or match_species(str(value), KNOWN, 0.9) or Species(slug(str(value)), str(value).strip())
        if species not in chosen:
            chosen.append(species)
    return tuple(chosen), False
