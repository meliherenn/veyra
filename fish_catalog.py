"""Fish names transcribed from the user's profession list; no invented durations."""
from dataclasses import dataclass,replace
from difflib import SequenceMatcher
import re
import unicodedata


def name_key(text):
    text=str(text).lower().replace('ı','i')
    text=''.join(c for c in unicodedata.normalize('NFKD',text) if not unicodedata.combining(c))
    return ' '.join(re.findall(r'[a-z0-9]+',text))


@dataclass(frozen=True)
class FishSpec:
    id: str
    name: str
    mastery: int
    aliases: tuple[str,...] = ()
    variants: str = ''
    color: str | None = None
    base_seconds: float | None = None


CATALOG=(
    FishSpec('billur_mersin','Billur Mersin Balığı',150,
             ('Billur Mersin Balığı İnsanlar','Billur Mersin Balığı Magmarlar'),'İnsanlar / Magmarlar'),
    FishSpec('altin_habus','Altın Habus',120),
    FishSpec('siyah_zargana','Siyah Zargana Balığı',120),
    FishSpec('gok_mavisi_somon','Gök Mavisi Somon Balığı',120),
    FishSpec('altin_pullu_orkinos','Altın Pullu Orkinos',120),
    FishSpec('kirmizi_sabut','Kırmızı Şabut Balığı',90,
             ('Kırmızı Şabut Balığı İnsanlar','Kırmızı Şabut Balığı Magmarlar'),'İnsanlar / Magmarlar'),
    FishSpec('kral_yengec','Kral Yengeç',90),
    FishSpec('elmas_som','Elmas Som Balığı',60),
    FishSpec('komur_turna','Kömür rengi turna balığı',60),
    FishSpec('gumus_yengec','Gümüş Yengeç',60),
    FishSpec('alacakaranlik','Alacakaranlık Balığı',30,('Alacakaranlık İncibalığı',)),
    FishSpec('gumus_kadife','Gümüş Kadife Balığı',30),
    FishSpec('ates_capak','Ateş Çapak Balığı',30),
    FishSpec('kara_havuz','Kara Havuz Balığı',30),
    # Live header OCR merges the words and reads the final nı as m: aysazam@.
    FishSpec('ay_sazani','Ay Sazanı',0,('Ay Sazan','Ay Sazan Balığı','Ay Sazani Baligi','Ay Sazam')),
    FishSpec('felionlu_camca','Felionlu Çamça',0),
    FishSpec('magara_baligi','Mağara Balığı',0),
    FishSpec('aynali_tas_sazani','Aynalı Taş Sazanı',0),
)
COLORS={'beyaz':'Beyaz / Gri','yesil':'Yeşil','mavi':'Mavi','mor':'Mor',
        'kirmizi':'Kırmızı','sari':'Sarı / Turuncu'}
# Only values visible in the two user-supplied collection-time screenshots.
SOURCE_DATA={
    'ay_sazani':('beyaz',5),'felionlu_camca':('beyaz',5),
    'magara_baligi':('beyaz',5),'aynali_tas_sazani':('beyaz',5),
    'alacakaranlik':('yesil',9),'gumus_kadife':('yesil',9),'kara_havuz':('yesil',9),'ates_capak':('yesil',9),
    'elmas_som':('mavi',12),'komur_turna':('mavi',12),
    'kirmizi_sabut':('mor',24),'gok_mavisi_somon':('mor',26),'altin_pullu_orkinos':('mor',26),
}
CATALOG=tuple(replace(f,color=SOURCE_DATA[f.id][0],base_seconds=SOURCE_DATA[f.id][1])
              if f.id in SOURCE_DATA else f for f in CATALOG)
# Verified in the live hunt screen; its duration remains unknown (mastery error).
CATALOG=tuple(replace(f,color='mor') if f.id=='billur_mersin' else f for f in CATALOG)
BY_ID={fish.id:fish for fish in CATALOG}
DEFAULT_IDS=('gumus_kadife',)


def _rank_names(text, candidates):
    key=name_key(text)
    if not key:return []
    scores=[]
    for fish in candidates:
        best=0.0
        for alias in (fish.name,*fish.aliases):
            expected=name_key(alias)
            if re.search(r'(?<!\w)'+re.escape(expected)+r'(?!\w)',key):
                best=1.0;break
            words=key.split();count=len(expected.split())
            for length in (count,max(1,count-1),count+1):
                for start in range(max(0,len(words)-length+1)):
                    candidate=' '.join(words[start:start+length])
                    score=SequenceMatcher(None,candidate,expected).ratio()
                    best=max(best,score)
        scores.append((best,fish.id))
    scores.sort(reverse=True)
    return scores


def resolve_name_for_colors(text, colors):
    """Resolve OCR text with a cautious fallback limited to selected colors.

    Color mode accepts every species of the chosen ring color. Short names such
    as Ay Sazanı are more vulnerable to a one-character OCR error, so after the
    normal strict resolver fails we compare only species that can belong to the
    selected colors. Ambiguous/partial text is still rejected.
    """
    strict=resolve_name(text)
    colors=set(colors or ())
    if strict is not None:
        return strict if strict.color in colors else None
    candidates=[fish for fish in CATALOG if fish.color in colors]
    scores=_rank_names(text,candidates)
    if not scores:return None
    second=scores[1][0] if len(scores)>1 else 0.0
    if scores[0][0]>=.80 and scores[0][0]-second>=.05:
        return BY_ID[scores[0][1]]
    return None


def resolve_name(text):
    """Resolve against the entire catalog, never just the user's allowed subset.

    Token windows tolerate OCR decorations and a small spelling error. An
    ambiguous name is rejected rather than mapped to the chosen target.
    """
    scores=_rank_names(text,CATALOG)
    if not scores:return None
    second=scores[1][0] if len(scores)>1 else 0.0
    if scores[0][0]>=.86 and scores[0][0]-second>=.075:
        return BY_ID[scores[0][1]]
    return None


def resolve_requested(values):
    result=[]
    for value in values:
        if value in ('all','tümü','tumu'):
            return tuple(BY_ID)
        fish=BY_ID.get(value) or resolve_name(value)
        if fish is None:raise ValueError(f'Balık adı tanınmadı: {value}. --list-fish ile listeyi görebilirsiniz.')
        if fish.id not in result:result.append(fish.id)
    if not result:raise ValueError('En az bir balık seçin.')
    return tuple(result)
