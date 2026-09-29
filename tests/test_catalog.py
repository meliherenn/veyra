import pytest
from fish_catalog import BY_ID,CATALOG,resolve_name,resolve_name_for_colors,resolve_requested


@pytest.mark.parametrize('text,expected',[
    ('alacakaranlik baliggi <i>','alacakaranlik'),
    ('Alacakaranlık İncibalığı','alacakaranlik'),
    ('GÜMÜŞ KADİFE BALIĞI','gumus_kadife'),
    ('Kırmızı Şabut Balığı Magmarlar','kirmizi_sabut'),
    ('Elmas Som Balığı','elmas_som'),
    ('Kömür rengi turna balığı','komur_turna'),
    ('aysazam@','ay_sazani'),
])
def test_names_aliases_and_reported_ocr_error(text,expected):
    assert resolve_name(text).id==expected


@pytest.mark.parametrize('text',['','balığı','Gümüş','Gordt','seçim yok','Elmas'])
def test_partial_or_unrelated_text_cannot_select_a_fish(text):
    assert resolve_name(text) is None


def test_faction_duplicates_share_one_species():
    assert len(CATALOG)==18
    assert resolve_requested(['Kırmızı Şabut Balığı İnsanlar','kirmizi_sabut'])==('kirmizi_sabut',)


def test_displayed_durations_do_not_invent_unknown_values():
    assert (BY_ID['ay_sazani'].color,BY_ID['ay_sazani'].base_seconds)==('beyaz',5)
    assert BY_ID['alacakaranlik'].base_seconds==9
    assert BY_ID['elmas_som'].base_seconds==12
    assert BY_ID['kirmizi_sabut'].base_seconds==24
    assert BY_ID['gok_mavisi_somon'].base_seconds==26
    assert BY_ID['gumus_yengec'].base_seconds is None
    assert BY_ID['altin_habus'].color is None


def test_unknown_requested_species_is_an_error():
    with pytest.raises(ValueError):resolve_requested(['kırmızı'])


def test_gray_color_context_recovers_short_ay_sazani_ocr_error():
    assert resolve_name('Ay Sazam').id=='ay_sazani'
    assert resolve_name_for_colors('Ay Sazam',('beyaz',)).id=='ay_sazani'
    assert resolve_name_for_colors('Sazan',('beyaz',)) is None
    assert resolve_name_for_colors('gordt',('beyaz',)) is None
