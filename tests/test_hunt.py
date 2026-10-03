from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import queue

import numpy as np
from PIL import Image
import pytest

import main
from hunt import HuntBot
from hunt_catalog import KNOWN, match_species, parse_label, resolve_requested
from hunt_vision import HuntVision
from screen_detector import Layout, Observation, ScreenDetector

FIXTURES = Path(__file__).parent / 'fixtures'


def frame(name):
    return np.array(Image.open(FIXTURES / name).convert('RGB'))


@pytest.fixture(scope='module')
def detector():
    d = ScreenDetector(grabber=None)
    yield d
    d.close()


@pytest.fixture(scope='module')
def vision(detector):
    return HuntVision(detector)


# ------------------------------------------------------------------ katalog
def test_label_parsing_handles_ocr_noise():
    assert parse_label('krogan[4]') == ('krogan', 4)
    assert parse_label('makharetli fitsilya[4)}') == ('makharetli fitsilya', 4)
    assert parse_label('| krogan [ 12 ]') == ('krogan', 12)
    assert parse_label('kro') == ('kro', None)


def test_fuzzy_species_match_tolerates_ocr_errors_but_not_other_names():
    assert match_species('makharetli fitsilya', KNOWN).id == 'maharetli_fitsilya'
    assert match_species('kragan', KNOWN).id == 'krogan'
    assert match_species('kirpi', KNOWN) is None


def test_header_info_icon_noise_still_matches_the_species():
    """Üst kutudaki ⓘ simgesi 'od' diye okunur; ad yine tanınmalı."""
    assert match_species('krogan od', KNOWN).id == 'krogan'
    assert match_species('maharetli fitsilya od', KNOWN).id == 'maharetli_fitsilya'
    # Gürültü yanlış türe kaymamalı.
    assert match_species('krogan od', KNOWN).id != 'maharetli_fitsilya'


def test_equal_scores_prefer_the_more_specific_name():
    """'krogan muhafizi' havuzdaysa 'krogan' onun yerine seçilmemeli."""
    from hunt_catalog import Species
    pool = KNOWN + (Species('krogan_muhafizi', 'Krogan Muhafızı'),)
    assert match_species('krogan muhafizi', pool).id == 'krogan_muhafizi'
    assert match_species('krogan', pool).id == 'krogan'
    assert match_species('krogan od', pool).id == 'krogan'


def test_requested_creatures_accept_unknown_names_and_all():
    species, everything = resolve_requested(['krogan'])
    assert [s.id for s in species] == ['krogan'] and not everything
    species, everything = resolve_requested(['Yeni Canavar'])
    assert species[0].id == 'yeni_canavar'
    assert resolve_requested(['all'])[1] is True
    assert len(resolve_requested(None)[0]) == len(KNOWN)


# ------------------------------------------------------------- görüntü tanıma
def read_all(detector, vision, f):
    layout = detector.detect_layout(f)
    accept = lambda name: match_species(name, KNOWN) is not None
    return [vision.read_label(f, s, accept=accept) for s in vision.find_labels(f, layout)]


def test_every_creature_on_the_hunting_map_is_found_and_read(detector, vision):
    creatures = read_all(detector, vision, frame('hunt-map.png'))
    assert len(creatures) == 12
    for c in creatures:
        expected = 'krogan' if c.color == 'yesil' else 'maharetli_fitsilya'
        assert match_species(c.name, KNOWN).id == expected and c.level == 4
    assert sum(c.color == 'yesil' for c in creatures) == 4


def test_selection_ring_is_not_mistaken_for_a_creature_label(detector, vision):
    creatures = read_all(detector, vision, frame('hunt-selected.png'))
    assert len(creatures) == 11


def test_bear_map_labels_found_beside_bright_grass(detector, vision):
    """Ayı haritasının çimeni eski renk bandına giriyor (148 bin piksel) ve
    Yaslı Phadd etiketleri hue 18 ile eski ton sınırının altındaydı; iki sorun
    birden botun 'yaratık yok' demesine yol açıyordu."""
    f = frame('hunt-bears-map.png')
    layout = detector.detect_layout(f)
    assert layout is not None
    found = vision.find_labels(f, layout)
    assert len(found) == 5
    yasli = [t for t in found if t.width >= 90]
    phadd = [t for t in found if t.width <= 75]
    assert len(yasli) == 3 and len(phadd) == 2
    assert all(t.color == 'sari' for t in found)


def test_label_gate_is_loose_but_header_gate_is_strict():
    """Harita etiketi gürültülü okunur (gevşek kapı); kesin karar büyük yazılı
    üst bilgi kutusunun sıkı eşiğindedir. 'Phadd Ayisi' ile 'Yasli Phadd
    Ayisi' (0.785) bu sayede karışmaz."""
    from config import HUNT_LABEL_MATCH_RATIO, HUNT_NAME_MATCH_RATIO
    from hunt_catalog import Species, match_species
    flangariyl = (Species('flangariyl', 'Flangariyl Korr Yavrusu'),)
    assert match_species('flungyuriy kore yavrusul', flangariyl, HUNT_LABEL_MATCH_RATIO)
    yasli = (Species('yasli', 'Yasli Phadd Ayisi'),)
    assert match_species('phadd ayisi', yasli, HUNT_LABEL_MATCH_RATIO)   # kapıdan geçer
    assert match_species('phadd ayisi', yasli, HUNT_NAME_MATCH_RATIO) is None  # üst bilgi engeller


def test_lagoon_map_labels_of_any_color_are_found(detector, vision):
    """Koyu lagün haritası: etiketler hue 60 yeşil ve S 139 altın — renk
    bantlarının hiçbirine uymuyordu. Kontrast ağı rengi önemsiz kılar; her
    yeni harita için renk raporu gerekmez."""
    f = frame('hunt-lagoon-map.png')
    layout = detector.detect_layout(f)
    assert layout is not None
    found = vision.find_labels(f, layout)
    assert len(found) >= 4
    readable = [vision.read_label(f, t, accept=lambda name: True) for t in found]
    names = [r.name for r in readable if r.name]
    assert any('yavrusu' in n.replace('yavrusul', 'yavrusu') for n in names)
    assert all(r.level == 9 for r in readable if r.name)


def test_scorpion_map_red_labels_are_found_and_read(detector, vision):
    """Kral Akrep haritasının etiketleri parlak kırmızıdır (hue ~6, S 255) ve
    seçim halkası da kırmızıdır; eski sarı/yeşil bandı hiç etiket görmüyordu."""
    f = frame('hunt-scorpions-map.png')
    layout = detector.detect_layout(f)
    assert layout is not None
    found = vision.find_labels(f, layout)
    assert len(found) >= 6
    assert all(t.color == 'kirmizi' for t in found)
    readable = [vision.read_label(f, t, accept=lambda name: True) for t in found]
    names = [r.name for r in readable]
    assert sum('kral akrep' in n for n in names) >= 4
    assert any('buyuk akrep' in n for n in names if n)
    # Kırmızı seçim halkası (~1097, 470) etiket adayı sanılmamalı.
    assert not [t for t in found if abs(t.x - 1097) <= 12 and abs(t.y - 470) <= 12]


def test_click_point_lands_on_the_creature_sprite(detector, vision):
    f = frame('hunt-selected.png')
    layout = detector.detect_layout(f)
    krogan = next(s for s in vision.find_labels(f, layout) if 1000 < s.label_x < 1050 and 395 < s.label_y < 415)
    # Gerçek halkanın merkezi (1028, 368); tahmin birkaç piksel içinde olmalı.
    assert abs(krogan.x - 1028) <= 4 and abs(krogan.y - 368) <= 4


def test_selected_creature_shows_ring_and_attack_button(detector, vision):
    f = frame('hunt-selected.png')
    layout = detector.detect_layout(f)
    assert vision.ring_near(f, layout, 1028, 368)[0]
    assert vision.attack_button(f, layout) is not None
    assert 'krogan' in vision.selected_name(f, layout)


def test_no_ring_or_attack_button_on_unselected_map(detector, vision):
    f = frame('hunt-map.png')
    layout = detector.detect_layout(f)
    assert vision.attack_button(f, layout) is None
    for x, y in [(1432, 278), (1585, 468), (1011, 593)]:
        assert not vision.ring_near(f, layout, x, y)[0]


def test_neighbour_of_selected_creature_is_not_reported_selected(detector, vision):
    f = frame('hunt-selected.png')
    layout = detector.detect_layout(f)
    assert not vision.ring_near(f, layout, 995, 414)[0]


def test_fishing_screens_never_look_like_an_attack_button(detector, vision):
    for name in ('green-selected.png', 'purple-selected.png', 'green-map.png', 'warning-tool-missing.png'):
        f = frame(name)
        assert vision.attack_button(f, detector.detect_layout(f)) is None, name


def test_result_window_ava_button_is_found_only_there(vision):
    x, y = vision.result_button(frame('hunt-result.png'))
    assert abs(x - 1093) <= 3 and abs(y - 54) <= 3
    assert vision.result_button(frame('hunt-fight.png')) is None
    assert vision.result_button(frame('hunt-map.png')) is None


def test_fight_and_result_screens_have_no_map_layout(detector):
    assert detector.detect_layout(frame('hunt-fight.png')) is None
    assert detector.detect_layout(frame('hunt-result.png')) is None


# --------------------------------------------------- dövüş içi eylem düğmeleri
def test_fight_toolbar_buttons_found_in_both_captures(vision):
    """Sol araç çubuğu (provokasyon/binek/otomatik savaş) iki gerçek çekimde de
    aynı piksel ölçeğindedir: konumlar ve dikey aralık birebir tutar. Çizili
    fotoğraf (hunt-fight-toolbar) çizimler şablonu bozduğu için yalnızca
    konum referansıdır, eşleşme testine girmez."""
    for name in ('hunt-provoke-dialog.png', 'hunt-fight.png'):
        f = frame(name)
        provoke = vision.fight_button(f, 'provoke')
        mount = vision.fight_button(f, 'mount')
        auto = vision.fight_button(f, 'auto')
        assert provoke and mount and auto, name
        assert abs(provoke[0] - mount[0]) <= 3 and abs(mount[0] - auto[0]) <= 3, name
        assert abs((mount[1] - provoke[1]) - 97) <= 3, name
        assert abs((auto[1] - mount[1]) - 47) <= 3, name


def test_map_screens_do_not_show_fight_buttons(vision):
    for name in ('hunt-map.png', 'green-map.png', 'white-pond.png'):
        f = frame(name)
        assert vision.fight_button(f, 'provoke') is None, name
        assert vision.fight_button(f, 'auto') is None, name


def test_summon_bar_lists_only_unlocked_slots_in_order(vision):
    f = frame('hunt-provoke-dialog.png')
    slots, locks = vision.summon_slots(f)
    assert len(locks) == 3
    assert len(slots) == 2
    xs = [s[0] for s in slots]
    assert xs[0] < xs[1] < locks[0][0]
    # Tıklama noktası kart gövdesine düşer (gerçek slot merkezleri ~397/475, 535).
    assert abs(slots[0][0] - 397) <= 6 and abs(slots[0][1] - 535) <= 6
    assert abs(slots[1][0] - 475) <= 6


def test_counter_mask_reacts_to_digit_changes(vision):
    f = frame('hunt-provoke-dialog.png')
    slots, _locks = vision.summon_slots(f)
    box = slots[0][2]
    before = vision.counter_mask(f, box)
    assert before is not None and before.any()
    # Sayaç ilerlediğinde rakam pikselleri değişir; kaydırılmış kutu bunu temsil eder.
    shifted = vision.counter_mask(f, (box[0] + 2, box[1], box[2], box[3]))
    assert not (before == shifted).all()


def test_summon_slots_without_locks_use_the_busiest_counter_row(vision):
    """Tüm slotlar açıldığında ekranda kilit olmaz; sayaç grubu en kalabalık
    y satırından bulunur, altta tek başına duran 'jeton' yazısı alınmaz."""
    f = np.zeros((1080, 1920, 3), np.uint8)
    teal = (0, 200, 200)
    for x in (100, 210, 320):          # üç slot sayacı aynı satırda
        f[790:800, x:x + 26] = teal
    f[830:840, 150:180] = teal         # altta tek '1500' benzeri yazı
    slots, locks = vision.summon_slots(f)
    assert locks == []
    assert len(slots) == 3
    xs = [s[0] for s in slots]
    assert xs == sorted(xs) and xs[0] < xs[1] < xs[2]
    for slot in slots:
        assert abs(slot[1] - (795 - 27)) <= 3


def test_mount_flag_reaches_the_bot():
    """CLI --mount → HuntBot.mount_summon (isim uyuşmazlığı bineği sessizce
    kapatıyordu; binek hiç denenmiyordu)."""
    args = main.parse_args(['--hunt', '--mount', '--provoke', '--auto-battle'])
    assert args.mount is True
    bot = HuntBot(SimpleNamespace(commands=__import__('queue').Queue(), is_game_active=lambda: True,
                                state={'geometry': [0, 0, 1920, 1080], 'screens': 1}),
                  Mock(), Mock(), Mock(), args)
    assert bot.mount_summon is True and bot.provoke is True and bot.auto_battle is True


def test_live_summon_bar_slots_and_locks_are_found(vision):
    """Canlı 1920 çekimi: sayaç rakamları tam parlak camgöbeğidir (4,254,254);
    eski maske sınırı onları kaçırıp 'çubuk açılmadı' dedirtiyordu."""
    f = frame('hunt-live-bar.png')
    slots, locks = vision.summon_slots(f)
    assert len(locks) == 3
    assert len(slots) == 2
    assert [s[0] for s in slots] == sorted(s[0] for s in slots)
    assert slots[0][0] < locks[0][0]
    for slot in slots:
        assert abs(slot[1] - locks[0][1]) <= 3  # tıklama noktası kart gövdesinde
    # Araç çubuğu bu çekimde daha aşağıdadır; üç düğme yine aynı sütunda.
    provoke = vision.fight_button(f, 'provoke')
    mount = vision.fight_button(f, 'mount')
    assert provoke and mount and provoke[0] == mount[0]


def test_confirm_apply_clicks_the_dialog_button(mocked):
    """Binek çağırma 'Eylem ... onaylayın' penceresi açar; Uygula'ya basılır.
    Pencere ayrı bir popup olduğu için kare tam ekrandan alınır."""
    bot = mocked
    bot.args.dry_run = False
    bot.detector.capture_screen.return_value = np.zeros((1080, 1920, 3), np.uint8)
    bot.detector.protection_template.return_value = False
    apply_point = (960, 540)
    bot.vision.confirm_apply_button.side_effect = [apply_point, None]
    bot.detector.check_bot_protection.return_value = (False, '')
    assert bot.confirm_pending_action(window=1.0) is True
    assert bot.desktop.allow_action_popup is False  # akış sonunda izin kapanır
    assert bot.mouse.click.call_count == 1
    assert bot.mouse.click.call_args.args[:2] == main_module_pixel(bot, apply_point)
    # Pencere hiç çıkmazsa False döner, tıklama gitmez.
    bot.mouse.reset_mock()
    bot.vision.confirm_apply_button.side_effect = None
    bot.vision.confirm_apply_button.return_value = None
    assert bot.confirm_pending_action(window=0.4) is False
    bot.mouse.click.assert_not_called()


def main_module_pixel(bot, point):
    return bot.pixel_to_desktop(point, bot.detector.capture_screen.return_value)


# --------------------------------------------------- sahte oyun (uçtan uca)
class FakeGame:
    """Gerçek ekran görüntülerinden kurulan küçük oyun: harita -> seçim -> dövüş -> sonuç."""
    SIZE = (1072, 1878)

    def __init__(self, detector):
        self.detector = detector
        self.map = frame('hunt-map.png')
        self.selected_src = frame('hunt-selected.png')
        self.layout = detector.detect_layout(self.map)
        self.src_layout = detector.detect_layout(self.selected_src)
        fight = frame('hunt-fight.png')
        self.fight = np.zeros((*self.SIZE, 3), np.uint8)
        self.fight[:fight.shape[0], :] = fight[:, :self.SIZE[1]]
        result = frame('hunt-result.png')
        self.result = np.zeros((*self.SIZE, 3), np.uint8)
        self.result[200:200 + result.shape[0], 60:60 + result.shape[1]] = result
        self.state = 'map'
        self.center = None
        self.fight_frames = 0
        self.fight_length = 3
        self.clicks = []
        self.vision = HuntVision(detector)
        labels = self.vision.find_labels(self.map, self.layout)
        self.creatures = {(s.x, s.y): s.color for s in labels}

    @property
    def attack_slot(self):
        return (round(self.layout.left + self.layout.width*.265), self.layout.top - 24)

    @property
    def ava(self):
        return (60 + 1093, 200 + 54)

    def capture(self):
        if self.state == 'map':
            return self.map.copy()
        if self.state == 'selected':
            return self.selected_frame()
        if self.state == 'fight':
            self.fight_frames += 1
            if self.fight_frames >= self.fight_length:
                self.state = 'result'
            return self.fight.copy()
        return self.result.copy()

    def selected_frame(self):
        out = self.map.copy()
        sl, dl = self.src_layout, self.layout
        # Üst bilgi bandı (saldır düğmesi + seçili yaratık adı).
        band = self.selected_src[sl.top - 60:sl.top - 2, sl.left + 330:sl.left + 1100]
        out[dl.top - 60:dl.top - 2, dl.left + 330:dl.left + 1100] = band
        # Yalnızca halka pikselleri, tıklanan yaratığın üstüne.
        cx, cy = self.center
        patch = self.selected_src[368 - 40:368 + 41, 1028 - 40:1028 + 41]
        mask = HuntVision._ring_mask(patch)
        target = out[cy - 40:cy + 41, cx - 40:cx + 41]
        target[mask] = patch[mask]
        return out

    def click(self, x, y):
        self.clicks.append((self.state, x, y))
        if self.state == 'map':
            for (sx, sy), color in self.creatures.items():
                if abs(x - sx) <= 12 and abs(y - sy) <= 12:
                    self.state, self.center = 'selected', (sx, sy)
        elif self.state == 'selected':
            if abs(x - self.attack_slot[0]) <= 8 and abs(y - self.attack_slot[1]) <= 8:
                self.state, self.fight_frames = 'fight', 0
        elif self.state == 'result':
            if abs(x - self.ava[0]) <= 10 and abs(y - self.ava[1]) <= 10:
                self.state = 'map'


def make_sim_bot(tmp_path, monkeypatch, detector, creatures=('krogan',), **args):
    monkeypatch.setattr(main, 'RUNTIME', tmp_path)
    game = FakeGame(detector)
    monkeypatch.setattr(detector, 'capture', game.capture)
    monkeypatch.setattr(detector, 'auto_panel_probe', lambda frame, force=False: False)
    monkeypatch.setattr(detector, 'capture_rect', None, raising=False)
    desktop = SimpleNamespace(commands=queue.Queue(), is_game_active=lambda: True,
                              state={'geometry': [0, 0, 1878, 1072], 'screens': 1})

    class Mouse:
        guard = None

        def click(self, x, y, before_click=None, target_tolerance=2.5):
            if before_click:
                before_click()
            game.click(x, y)

        scroll = Mock()

    sound = Mock()
    ns = SimpleNamespace(dry_run=False, no_scroll=False, creatures=list(creatures), min_level=None, max_level=None,
                         **args)
    bot = HuntBot(desktop, detector, Mouse(), sound, ns)
    return bot, game


def run_until(bot, done, limit=60):
    for _ in range(limit):
        bot.tick()
        if done():
            return True
    return False


def test_full_hunt_cycle_selects_attacks_fights_and_returns(tmp_path, monkeypatch, detector):
    bot, game = make_sim_bot(tmp_path, monkeypatch, detector)
    assert run_until(bot, lambda: bot.cycles == 1)
    states = [s for s, _x, _y in game.clicks]
    # yaratık -> saldır -> Ava; haritaya dönünce aynı tick'te sıradaki yaratığa geçilir.
    assert states[:3] == ['map', 'selected', 'result']
    assert states[3:] in ([], ['map'])
    assert bot.fights == 1 and bot.attempts == 1
    # İlk tıklama gerçekten bir Krogan'ın gövdesine gitti; Maharetli'ye hiç tıklanmadı.
    first = game.clicks[0]
    assert game.creatures[min(game.creatures, key=lambda p: abs(p[0]-first[1]) + abs(p[1]-first[2]))] == 'yesil'
    bot.sound.start_alarm_loop.assert_not_called()


def test_only_selected_species_are_ever_clicked(tmp_path, monkeypatch, detector):
    bot, game = make_sim_bot(tmp_path, monkeypatch, detector, creatures=('maharetli fitsilya',))
    assert run_until(bot, lambda: bot.attempts >= 1 or game.state != 'map', limit=40)
    x, y = game.clicks[0][1:]
    nearest = min(game.creatures, key=lambda p: abs(p[0]-x) + abs(p[1]-y))
    # Seçilen tür Maharetli (sarı): Krogan (yeşil) hedeflenmemeli. Sahte oyunun
    # üst bilgisi "Krogan" gösterdiği için saldırı da onaylanmamalı.
    assert game.creatures[nearest] == 'sari'
    run_until(bot, lambda: False, limit=8)
    assert 'fight' not in [s for s, _x, _y in game.clicks] and game.state != 'fight'
    assert bot.attempts == 0


def test_level_limits_skip_every_creature(tmp_path, monkeypatch, detector):
    bot, game = make_sim_bot(tmp_path, monkeypatch, detector, creatures=('all',))
    bot.max_level = 3
    for _ in range(4):
        bot.tick()
    assert game.clicks == [] and bot.phase == 'SEARCH'


def test_scroll_only_when_nothing_matches(tmp_path, monkeypatch, detector):
    bot, game = make_sim_bot(tmp_path, monkeypatch, detector, creatures=('kirpi',))
    bot.tick(); bot.tick()
    bot.mouse.scroll.assert_not_called()
    bot.tick(); bot.tick()
    bot.mouse.scroll.assert_called_once()
    assert game.clicks == []


# --------------------------------------------------- güvenlik davranışları
@pytest.fixture
def mocked(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'RUNTIME', tmp_path)
    desktop = SimpleNamespace(commands=queue.Queue(), is_game_active=lambda: True,
                              state={'geometry': [0, 0, 1920, 1080], 'screens': 1})
    detector = Mock()
    detector.capture.return_value = np.zeros((1080, 1920, 3), np.uint8)
    detector.observe.return_value = Observation(Layout(193, 238, 1713, 764))
    mouse, sound = Mock(), Mock()
    args = SimpleNamespace(dry_run=False, no_scroll=False, creatures=['krogan'], min_level=None, max_level=None)
    bot = HuntBot(desktop, detector, mouse, sound, args)
    bot.vision = Mock()
    bot.vision.scale.return_value = 1.0
    bot.vision.result_button.return_value = None
    return bot


def test_protection_stops_everything_even_during_a_fight(mocked):
    mocked.phase = 'ENGAGED'
    mocked.detector.observe.return_value = Observation(None, protection=True, blocked='Bot koruması')
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    mocked.mouse.scroll.assert_not_called()
    mocked.sound.start_alarm_loop.assert_called_once()
    assert mocked.gate.latched


def test_protection_appearing_after_fight_never_clicks_ava(mocked):
    mocked.detector.observe.return_value = Observation(None, blocked='Avlan haritası görünmüyor')
    mocked.vision.result_button.return_value = (1000, 300)
    mocked.detector.check_bot_protection.return_value = (True, 'Bot koruması yazısı algılandı.')

    def click(*args, before_click, **kwargs):
        before_click()
        pytest.fail('Koruma varken tıklanmamalı')
    mocked.mouse.click.side_effect = click
    with pytest.raises(InterruptedError):
        mocked.tick()
    assert mocked.gate.latched


def test_attack_never_clicked_when_header_name_differs(mocked):
    target = SimpleNamespace(x=400, y=400, label_x=400, label_y=437, width=50, height=9, color='yesil',
                             name='krogan', level=4, species_id='krogan', radius=14)
    mocked.target, mocked.phase, mocked.since = target, 'SELECTING', 0
    mocked.vision.attack_button.return_value = (600, 214)
    mocked.vision.selected_name.return_value = 'maharetli fitsilya'
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    assert mocked.attempts == 0 and mocked.phase == 'SEARCH'
    assert len(mocked.avoid) == 1


def test_unreadable_header_waits_instead_of_attacking(mocked):
    target = SimpleNamespace(x=400, y=400, label_x=400, label_y=437, width=50, height=9, color='yesil',
                             name='krogan', level=4, species_id='krogan', radius=14)
    mocked.target, mocked.phase = target, 'SELECTING'
    mocked.since = main.time.monotonic()
    mocked.vision.attack_button.return_value = (600, 214)
    mocked.vision.selected_name.return_value = ''
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    assert mocked.phase == 'SELECTING'


def test_all_mode_adopts_the_header_name_for_unreadable_labels(mocked):
    """'all' modunda etiketi okunmayan hedef, üst kutudaki adla saldırıya onaylanır."""
    from hunt_vision import Sighting
    target = Sighting(x=400, y=400, label_x=400, label_y=437, width=50, height=9, color='yesil')
    mocked.target, mocked.phase, mocked.since = target, 'SELECTING', 0
    mocked.allow_all = True
    mocked.vision.attack_button.return_value = (600, 214)
    mocked.vision.selected_name.return_value = 'orman devi'
    mocked.tick()
    mocked.mouse.click.assert_called_once()
    assert mocked.attempts == 1 and mocked.phase == 'ENGAGED'
    assert mocked.target.name == 'orman devi'


def test_selection_timeouts_rotate_click_offset_and_finally_pause(mocked):
    from config import HUNT_CLICK_DY_FALLBACKS, HUNT_SELECT_FAILURES_BEFORE_PAUSE
    target = SimpleNamespace(x=400, y=400, label_x=400, label_y=437, width=50, height=9, color='yesil',
                             name='krogan', level=4, species_id='krogan', radius=14)
    mocked.vision.attack_button.return_value = None
    offsets = []
    for _ in range(HUNT_SELECT_FAILURES_BEFORE_PAUSE):
        mocked.target, mocked.phase, mocked.since = target, 'SELECTING', 0
        offsets.append(mocked.click_dy)
        mocked.tick()
    assert offsets[:2] == list(HUNT_CLICK_DY_FALLBACKS[:2])
    assert mocked.manual_pause and mocked.gate.latched


def test_stuck_fight_pauses_with_alarm_instead_of_guessing(mocked):
    mocked.detector.observe.return_value = Observation(None, blocked='Avlan haritası görünmüyor')
    mocked.phase, mocked.engaged_at = 'ENGAGED', main.time.monotonic() - 1000
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    assert mocked.manual_pause and mocked.gate.latched
    mocked.sound.start_alarm_loop.assert_called_once()


def test_fight_in_progress_just_waits(mocked):
    mocked.detector.observe.return_value = Observation(None, blocked='Avlan haritası görünmüyor')
    mocked.phase, mocked.engaged_at = 'ENGAGED', main.time.monotonic()
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    assert not mocked.gate.latched and mocked.phase == 'ENGAGED'


def test_result_window_is_handled_even_after_pause_or_restart(mocked):
    """Bot sonuç penceresi açıkken başlatılırsa da 'Ava' ile temiz döner."""
    mocked.detector.observe.return_value = Observation(None, blocked='Avlan haritası görünmüyor')
    mocked.vision.result_button.return_value = (1093, 254)
    mocked.tick()
    mocked.mouse.click.assert_called_once()
    assert mocked.phase == 'RETURNING' and mocked.fights == 1


def test_dry_run_never_touches_the_mouse(mocked):
    mocked.args.dry_run = True
    mocked.vision.find_labels.return_value = []
    mocked.tick()
    mocked.mouse.click.assert_not_called()
    mocked.mouse.scroll.assert_not_called()


def test_stop_command_raises_the_shared_stoprequested(mocked):
    """run.sh main.py'yi __main__ olarak çalıştırır, hunt.py ise `from main
    import` ile ikinci modul kopyası yaratır. StopRequested tek sınıf olmalı
    ki __main__'in except bloğu HuntBot'un kaldırdığı istisnayı yakalasın;
    aksi halde F9/SIGTERM/Ctrl+C "Bot hata nedeniyle durdu" süsü verirdi."""
    import state
    assert main.StopRequested is state.StopRequested
    mocked.desktop.commands.put('stop')
    with pytest.raises(main.StopRequested):
        mocked.control_guard()


# ------------------------------------------------------ dövüş içi eylemler
def test_fight_guard_clicks_despite_hover_but_not_on_map_return(mocked):
    """İmleç düğmenin üstüne gelince oyunun vurgusu şablon skorunu düşürür;
    guard şablonu yeniden okumaz, yalnızca ekran durumuna bakar. Harita
    dönünce ya da sonuç penceresi çıkınca tıklama iptal edilir."""
    bot = mocked
    bot.args.dry_run = False
    bot.detector.protection_template.return_value = False
    # Dövüş ekranı: harita yok, sonuç penceresi yok -> guard geçer.
    bot.detector.detect_layout.return_value = None
    bot.detector.observe.return_value = Observation(None)
    bot.vision.result_button.return_value = None
    bot.detector.check_bot_protection.return_value = (False, '')
    bot.fight_guard('provoke', (50, 100))
    # Harita döndüyse dövüş bitmiştir: basma.
    bot.detector.detect_layout.return_value = Layout(193, 238, 1713, 764)
    with pytest.raises(InterruptedError, match='Dövüş ekranı değişti'):
        bot.fight_guard('provoke', (50, 100))
    # Sonuç penceresi çıktıysa dövüş bitti: basma.
    bot.detector.detect_layout.return_value = None
    bot.vision.result_button.return_value = (1000, 254)
    with pytest.raises(InterruptedError, match='Dövüş ekranı değişti'):
        bot.fight_guard('auto', (50, 244))


def test_summon_guard_allows_hovered_slot_but_stops_when_bar_closes(mocked):
    bot = mocked
    bot.args.dry_run = False
    bot.detector.protection_template.return_value = False
    bot.detector.detect_layout.return_value = None
    bot.detector.observe.return_value = Observation(None)
    bot.detector.check_bot_protection.return_value = (False, '')
    bot.vision.result_button.return_value = None
    frame = np.zeros((1080, 1920, 3), np.uint8)
    # Döngü aynı karede slotu doğruladıysa (bar_open) ikinci tarama yapılmaz.
    bot.vision.summon_slots.return_value = ([], [])
    bot.summon_guard((100, 200), frame, bar_open=True)
    bot.vision.summon_slots.return_value = ([], [(300, 200)])
    bot.summon_guard((100, 200), frame)
    # Çubuk tamamen kapandı: basma.
    bot.vision.summon_slots.return_value = ([], [])
    with pytest.raises(InterruptedError, match='çubuğu kapandı'):
        bot.summon_guard((100, 200), frame)


def test_fight_actions_click_provoke_summon_mount_then_auto(mocked):
    bot = mocked
    bot.provoke = bot.mount_summon = bot.auto_battle = True
    bot.provoke_counts = [2]
    positions = {'provoke': (50, 100), 'mount': (50, 197), 'auto': (50, 244)}
    bot.vision.fight_button.side_effect = lambda frame, kind, threshold=None: positions[kind]
    slot = (100, 200, (90, 226, 20, 8))
    bot.vision.summon_slots.return_value = ([slot], [(300, 200)])
    # Sayaç hiç değişmiyor: ikinci çağrıda jeton bitmiş sayılır, slot 1 tıklamada biter.
    bot.vision.counter_mask.return_value = np.zeros((12, 24), np.uint8)
    bot.vision.confirm_apply_button.return_value = None  # onay penceresi çıkmıyor
    bot.args.dry_run = False
    bot.perform_fight_actions()
    assert bot.mouse.click.call_count == 4  # provoke + 1 çağırma + mount + auto
    xs = [call.args[0] for call in bot.mouse.click.call_args_list]
    assert xs == [50, 100, 50, 50]
    assert bot.provoke_counts == [2]


def test_fight_actions_run_once_per_fight(mocked, monkeypatch):
    bot = mocked
    bot.provoke = bot.mount_summon = bot.auto_battle = True
    bot.fight_actions_done = False
    bot.vision.confirm_apply_button.return_value = None  # bekleyen onay yok
    performed = []
    monkeypatch.setattr(bot, 'perform_fight_actions', lambda: performed.append(1))
    obs = SimpleNamespace(blocked='Avlan haritası görünmüyor', layout=None)
    bot.phase, bot.engaged_at = 'ENGAGED', main.time.monotonic()
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, main.time.monotonic())
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, main.time.monotonic())
    assert performed == [1]


def test_pending_confirm_is_retried_during_fight_wait(mocked, monkeypatch):
    """Onay popup'ı odağı aldığında bot 'oyun önde değil' bekler; bu bekleyiş
    sırasında bekleyen Uygula penceresi görünürse tıklanır."""
    bot = mocked
    bot.provoke = bot.mount_summon = bot.auto_battle = True
    bot.fight_actions_done = True
    bot.confirm_retries = 0
    bot.last_confirm_check = 0.0
    bot.phase = 'ENGAGED'
    bot.vision.confirm_apply_button.side_effect = [(960, 540)]
    bot.vision.confirm_apply_button.return_value = None
    performed = []
    monkeypatch.setattr(bot, 'confirm_pending_action', lambda window=1.5: performed.append(window))
    bot.desktop.is_game_active = lambda: False
    bot.desktop.state = {'app': 'brave', 'title': 'Eylem «Endarg Madalyonu Kullanma» - Brave',
                         'geometry': [0, 0, 1920, 1080], 'screens': 1}
    bot.tick()
    bot.tick()
    assert performed == [1.5] and bot.confirm_retries == 1


def test_fight_wait_extends_while_the_screen_keeps_changing(mocked):
    """Provokasyonlu dövüşler 3+ dakika sürer; kare değiştikçe 90 sn sınırı
    yenilenir, dövüş kesilmez."""
    bot = mocked
    now = main.time.monotonic()
    bot.phase, bot.engaged_at, bot._fight_alive_at = 'ENGAGED', now - 120, now
    obs = SimpleNamespace(blocked=None, layout=None)
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, now)
    assert not bot.manual_pause and bot.phase == 'ENGAGED'


def test_static_fight_pauses_after_the_static_window(mocked):
    """Ekran 30 sn'den uzun değişmediyse dövüş takılmıştır: erken dur ve alarm ver."""
    bot = mocked
    now = main.time.monotonic()
    bot.phase, bot.engaged_at, bot._fight_alive_at = 'ENGAGED', now - 120, now - 45
    obs = SimpleNamespace(blocked=None, layout=None)
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, now)
    assert bot.manual_pause and bot.gate.latched
    bot.sound.start_alarm_loop.assert_called_once()


def test_fight_hard_ceiling_pauses_even_while_alive(mocked):
    """Ekran canlı görünsé bile 10 dakikalık üst sınır keser."""
    bot = mocked
    now = main.time.monotonic()
    bot.phase, bot.engaged_at, bot._fight_alive_at = 'ENGAGED', now - 700, now
    obs = SimpleNamespace(blocked=None, layout=None)
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, now)
    assert bot.manual_pause and bot.gate.latched


def test_new_attack_rearms_fight_actions(mocked):
    bot = mocked
    bot.fight_actions_done = True
    target = SimpleNamespace(x=400, y=400, label_x=400, label_y=437, width=50, height=9, color='yesil',
                             name='krogan', level=4, species_id='krogan', radius=14)
    bot.target, bot.phase, bot.since = target, 'SELECTING', 0
    bot.vision.attack_button.return_value = (600, 214)
    bot.vision.selected_name.return_value = 'krogan od'
    bot.tick()
    assert bot.attempts == 1 and bot.fight_actions_done is False


def test_seen_creature_memory_ignores_catalog_noise_and_duplicates(tmp_path):
    import hunt_catalog
    path = tmp_path / 'creatures.json'
    assert hunt_catalog.remember_seen(path, 'kara orman kurdu [7]')
    assert not hunt_catalog.remember_seen(path, 'Kara Orman Kurdu')
    assert not hunt_catalog.remember_seen(path, 'ab')
    assert not hunt_catalog.remember_seen(path, 'Krogan')
    assert hunt_catalog.load_seen(path) == ['Kara Orman Kurdu']
    hunt_catalog.forget_seen(path, 'kara orman kurdu')
    assert hunt_catalog.load_seen(path) == []
