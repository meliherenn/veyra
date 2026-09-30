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
    performed = []
    monkeypatch.setattr(bot, 'perform_fight_actions', lambda: performed.append(1))
    obs = SimpleNamespace(blocked='Avlan haritası görünmüyor', layout=None)
    bot.phase, bot.engaged_at = 'ENGAGED', main.time.monotonic()
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, main.time.monotonic())
    bot.off_map(np.zeros((10, 10, 3), np.uint8), obs, main.time.monotonic())
    assert performed == [1]


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
