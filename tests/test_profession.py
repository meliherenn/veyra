from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
import queue
import time
import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import pytest
import subprocess
import main
from config import ROOT
from energy_store import EnergyStore
from metrics import METRICS
from profession import ProfessionController
from profession_vision import ProfessionVision, Box, Word, parse_energy, recovery_reason
from screen_detector import ScreenDetector, Observation, Layout

def test_energy_survives_restart_but_requires_fresh_confirmation(tmp_path):
    path=tmp_path/'energy.json';store=EnergyStore(path)
    assert store.value is None and store.needs_sync()
    store.sync(98,100);store.manual_completed();store.manual_completed()
    assert store.value==100 and store.estimated and store.needs_sync()
    restarted=EnergyStore(path)
    assert restarted.value==100 and restarted.estimated
    restarted.sync(73,100)
    assert restarted.value==73 and restarted.pending==0 and not restarted.estimated

@pytest.mark.parametrize('text,expected', [('Enerji: 20 / 100',(20,100)),('Enerji: 0/100',(0,100)),
    ('Enerji: 101 / 100',None),('408/408',None),('Enerji: 3/0',None)])
def test_energy_parsing(text,expected):
    assert parse_energy(text)==expected

def test_unknown_failure_never_claims_splinter():
    assert recovery_reason('Gerekli alete sahip değilsiniz!')=='tool'
    assert recovery_reason('Elinize kıymık battı')=='splinter'
    assert recovery_reason('Yaralısınız ve çalışamıyorsunuz.') == 'splinter'
    assert recovery_reason('Yeterli ustalığınız yok') is None
    assert recovery_reason('Toplama başlamadı') is None
    assert recovery_reason('Otomatik toplama devam ederken elle kaynak toplamak mümkün değil') == 'auto'


def test_recovery_reason_strict_tool_detection_and_negative_cases():
    # Noisy real OCR positives
    assert recovery_reason('Gerekli alete sahip değilsiniz!') == 'tool'
    assert recovery_reason('gereldi alete sahip degilsinid') == 'tool'
    assert recovery_reason('gere:i alete sahip degilimid') == 'tool'
    assert recovery_reason('geriki alete sahip degiiiiid') == 'tool'
    assert recovery_reason('Oltayı takınız') == 'tool'
    assert recovery_reason('Aletiniz yok') == 'tool'

    # Strict negative cases (must NEVER trigger tool)
    assert recovery_reason('Bu eşyaya sahip değilsiniz!') is None
    assert recovery_reason('Yeterli ustalığa sahip değilsiniz!') is None
    assert recovery_reason('Bu yeteneğe sahip değilsiniz.') is None
    assert recovery_reason('Gerekli seviyeye sahip değilsiniz.') is None
    assert recovery_reason('Gerekli enerjiye sahip değilsiniz!') == 'energy'



def test_cropped_tool_alert_is_read_and_closed(vision):
    alert = picture('tool-alert.png')
    found = vision.known_alert(alert)
    assert found and found[0] == 'tool' and found[1]


def test_inventory_tabs_have_geometry_fallback_on_live_capture(vision):
    # The fixture is intentionally a tight inventory crop without the tabs;
    # the fallback is exercised with the captured live inventory when present.
    live = Path(__file__).parents[1] / 'runtime' / 'inventory-before.png'
    if not live.exists():
        pytest.skip('live inventory capture is not available')
    image = np.array(Image.open(live).convert('RGB'))
    for label in ('Efektler', 'Eşyalar'):
        hit = vision.inventory_tab(image, label)
        assert hit and hit.y < vision.inventory(image).y


def test_main_inventory_is_selected_instead_of_combat_bag(vision):
    image=picture('navigation.png')
    hit=vision.bag_button(image)
    assert hit and hit.center==(660,120)
    image[:,:1500]=0
    assert vision.bag_button(image) is None
    assert vision.bag_button(picture('navigation-hover.png')).center==(660,120)
    assert vision.hunt_button(picture('navigation.png')).center==(855,120)

def test_inventory_return_uses_hunt_button_from_location_screen(bot):
    import time
    p=bot.profession;p.state='RETURN'
    p.vision.auto_panel.return_value=None;p.vision.inventory.return_value=None
    p.click=Mock(return_value=True)
    p.handle(bot.detector.capture(),Observation(None,blocked='Avlan haritası görünmüyor'),time.monotonic())
    p.click.assert_called_once_with(bot.detector.capture.return_value,p.vision.hunt_button,
                                   'Üst menüden Avlan ekranına dönülüyor.')
    assert not bot.manual_pause and p.state=='RETURN'

def test_splinter_during_equipment_recovery_switches_to_potion(bot):
    p=bot.profession;p.state='EQUIP_CONFIRM'
    assert p.request_recovery('splinter')
    assert p.state=='POTION_OPEN'
    p.state='POTION_CONFIRM'
    assert p.request_recovery('tool') and p.state=='POTION_CONFIRM'


def test_tool_alert_without_button_template_uses_the_dialog_close_button(bot):
    p=bot.profession;p.state='IDLE'
    p.energy_enabled=False;p.recovery_enabled=True
    # Gövde metninden kurulan sınıfta şablon düğme eşleşmiyor.
    p.vision.known_alert.return_value=None
    p.vision.matches.return_value=[]
    bot.detector.detect_layout.return_value=Layout(193,238,1713,764)
    bot.detector.find_close_button.return_value=(953,499)
    p.click=Mock(side_effect=lambda frame,finder,message,**kw: finder(frame) is not None)
    frame=np.zeros((1080,1920,3),np.uint8)
    assert p.dismiss_alert(frame,'tool')
    assert p.state=='EQUIP_OPEN'
    assert p.click.call_count==1
    # Tıklama yolu kutu bekler; detector merkezi (953,499) kutunun ortası olmalı.
    assert tuple(p.click.call_args[0][1](frame).center)==(953,499)


def test_tool_alert_still_returns_false_when_no_close_button_is_visible(bot):
    p=bot.profession;p.state='IDLE'
    p.energy_enabled=False;p.recovery_enabled=True
    p.vision.known_alert.return_value=None
    p.vision.matches.return_value=[]
    bot.detector.find_close_button.return_value=None
    p.click=Mock(return_value=True)
    assert p.dismiss_alert(np.zeros((1080,1920,3),np.uint8),'tool') is False
    p.click.assert_not_called()


def test_tool_alert_close_button_survives_the_click_time_recheck(bot):
    """Canlıda görülen hata: detector merkezi (x, y) döndürür, tıklama kutu bekler."""
    p=bot.profession;p.state='IDLE'
    p.energy_enabled=False;p.recovery_enabled=True
    p.vision.known_alert.return_value=None
    p.vision.matches.return_value=[]
    bot.detector.detect_layout.return_value=Layout(193,238,1713,764)
    bot.detector.find_close_button.return_value=(953,499)
    bot.detector.capture.return_value=np.zeros((1080,1920,3),np.uint8)
    bot.detector.check_bot_protection.return_value=(False,None)
    bot.detector.capture_rect.return_value=(0,0,1920,1080)
    seen={}
    def press(x,y,before_click=None):
        seen['at']=(x,y)
        seen['guard']=before_click() if before_click else None
    bot.mouse.click=Mock(side_effect=press)
    assert p.dismiss_alert(np.zeros((1080,1920,3),np.uint8),'tool')
    assert seen['guard'] is not None
    assert seen['guard']==(953,499)


def test_inventory_return_button_is_localized(vision):
    live = Path(__file__).parents[1] / 'runtime' / 'inventory-before.png'
    if not live.exists():
        pytest.skip('live inventory screenshot is not available')
    image = np.array(Image.open(live).convert('RGB'))
    button = vision.close_inventory(image)
    assert button and button.x > image.shape[1] * .8 and button.y < vision.inventory(image).y


def test_recovery_controller_starts_idle_and_does_not_touch_inventory(tmp_path):
    detector = Mock()
    bot = SimpleNamespace(detector=detector, args=SimpleNamespace(
        energy_cycle=False, auto_splinter=True, auto_fish_id='elmas_som', dry_run=False),
        notice=Mock(),gate=SimpleNamespace(latched=False))
    from profession import ProfessionController
    controller = ProfessionController(bot, tmp_path)
    assert controller.state == 'IDLE'
    controller.vision = Mock()
    controller.vision.known_alert.return_value = None
    obs = Observation(Layout(193,238,1713,764))
    assert controller.handle(np.zeros((600,1000,3), np.uint8), obs, 0) is False
    controller.vision.known_alert.assert_not_called()


def test_old_fishing_loop_still_selects_a_ring_when_recovery_is_enabled(bot):
    bot.profession.energy_enabled = False
    bot.profession.recovery_enabled = True
    bot.profession.enabled = True
    bot.profession.state = 'IDLE'
    bot.detector.find_fish_ripples.return_value = [type('Ring', (), {
        'x': 400, 'y': 500, 'radius': 18, 'score': 100, 'color': 'yesil'})()]
    bot.tick()
    bot.mouse.click.assert_called_once()
    assert bot.phase == 'SELECTING'


def test_slow_optional_ocr_is_nonfatal(vision, monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired('tesseract', 8)
    monkeypatch.setattr(subprocess, 'run', timeout)
    assert vision.words(np.zeros((80,120,3), np.uint8)) == []

@pytest.fixture
def vision():
    detector=ScreenDetector()
    yield ProfessionVision(detector)
    detector.close()

def picture(name):
    return np.array(Image.open(Path(__file__).parent/'fixtures'/name).convert('RGB'))

def test_real_menu_reads_profession_energy_and_correct_rows(vision):
    frame=picture('auto-top.png');panel=vision.auto_panel(frame)
    assert panel and vision.energy(frame,panel)==(20,100)
    rows=vision.rows(frame,panel)
    assert rows[0].fish_id=='ay_sazani' and rows[0].seconds==5
    assert rows[0].button.center==(572,102)
    assert rows[-1].fish_id=='alacakaranlik'

def test_scrolled_screenshot_identifies_blue_fish(vision):
    rows=vision.rows(picture('auto-bottom.png'),Box(0,0,742,475))
    elmas=next(row for row in rows if row.fish_id=='elmas_som')
    assert elmas.seconds==12 and elmas.button.center==(568,230)

def test_reference_items_and_inventory_are_detected(vision):
    effects=picture('inventory-effects.png');tools=picture('inventory-tools.png')
    assert len(vision.matches(effects,'potion'))==5
    assert len(vision.matches(tools,'rod'))==1
    assert vision.inventory(effects) and vision.inventory(tools)
    assert not vision.matches(tools,'potion')
    assert not vision.matches((tools*.45).astype('uint8'),'rod')

def test_new_rod_model_is_detected_in_the_bag(vision):
    # The fixture still carries the Ahşap Ok cell at (661,21,38,39); it must
    # never be reported as a rod again, while the Efsanevi Olta at (829,20) is.
    frame=picture('inventory-rod-new.png')
    assert [(b.x,b.y,b.w,b.h) for b in vision.matches(frame,'rod')]==[(829,20,56,56)]

def test_new_rod_variant_is_what_finds_the_new_rod(vision):
    frame=picture('inventory-rod-new.png')
    variants=vision.variants.pop('rod',[])
    try:
        assert not vision.matches(frame,'rod')
    finally:
        if variants:
            vision.variants['rod']=variants

def test_new_rod_template_never_matches_the_equipped_weapon_slot(vision):
    frame=picture('inventory-rod-new.png')
    assert not vision.matches(frame,'rod',Box(15,6,372,439),threshold=.85)

def test_rod_equipped_is_seen_on_the_doll_while_the_spare_stays_in_the_bag(vision):
    frame=picture('inventory-rod-equipped.png')
    inventory=vision.inventory(frame)
    assert inventory and inventory.x>=100
    doll=Box(75,inventory.y,inventory.x-75,max(1,inventory.h))
    assert [(b.x,b.y,b.w,b.h) for b in vision.matches(frame,'rod',doll,threshold=.85)]==[(106,159,58,56)]
    assert [(b.x,b.y,b.w,b.h) for b in vision.matches(frame,'rod',inventory)]==[(889,85,56,56)]


def _panel_before_shortcut(vision, frame):
    """auto_panel with the half-resolution shortcut removed: full match decides."""
    hits = vision.matches(frame, 'title', threshold=.86)
    if not hits:
        return None
    title = hits[0]
    scale = title.w / 119
    x, y = round(title.x - 310*scale), round(title.y - 2*scale)
    return Box(max(0, x), max(0, y), min(round(742*scale), frame.shape[1]-max(0, x)),
               min(round(475*scale), frame.shape[0]-max(0, y)))

def test_panel_shortcut_never_changes_the_answer(vision):
    for path in sorted((Path(__file__).parent/'fixtures').glob('*.png')):
        frame = picture(path.name)
        assert vision.auto_panel(frame) == _panel_before_shortcut(vision, frame), path.name

def test_panel_shortcut_rejects_a_clean_map(vision):
    before = METRICS.counts['auto_panel_fast_reject']
    assert vision.auto_panel(picture('navigation.png')) is None
    assert vision.auto_panel(picture('green-map.png')) is None
    assert METRICS.counts['auto_panel_fast_reject'] == before + 2

@pytest.mark.parametrize('scale',[.8,1.,1.1,1.25])
@pytest.mark.parametrize('brightness',[.75,1.,1.3])
def test_panel_shortcut_never_misses_a_real_panel(vision,scale,brightness):
    frame = picture('green-map.png').copy()
    template = cv2.imread(str(ROOT/'assets'/'profession-title.png'),cv2.IMREAD_GRAYSCALE)
    pattern = cv2.resize(template,None,fx=scale,fy=scale)
    painted = np.clip(cv2.cvtColor(pattern,cv2.COLOR_GRAY2RGB)*brightness,0,255).astype('uint8')
    x, y = 700, 300
    frame[y:y+pattern.shape[0], x:x+pattern.shape[1]] = painted
    panel = vision.auto_panel(frame)
    assert panel is not None, (scale, brightness)
    assert panel.x <= x <= panel.x + panel.w and panel.y <= y <= panel.y + panel.h

@pytest.fixture
def bot(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'RUNTIME',tmp_path)
    desktop=SimpleNamespace(commands=queue.Queue(),is_game_active=lambda:True,
                            state={'geometry':[0,0,1920,1080],'screens':1})
    detector=Mock();detector.capture.return_value=np.zeros((1080,1920,3),np.uint8)
    detector.observe.return_value=Observation(Layout(193,238,1713,764))
    args=SimpleNamespace(dry_run=False,no_scroll=False,energy_cycle=True,auto_splinter=True,auto_fish_id='elmas_som')
    b=main.FishingBot(desktop,detector,Mock(),Mock(),args)
    b.profession.vision=Mock()
    b.profession.vision.known_alert.return_value=None
    b.profession.vision.potion_confirmation.return_value=None
    b.profession.vision.active_collection.return_value=None
    b.profession.vision.auto_panel.return_value=Box(590,250,742,475)
    return b

def test_full_energy_starts_selected_automatic_cycle(bot):
    p=bot.profession;p.state='AUTO_READ';p.vision.energy.return_value=(100,100)
    bot.tick()
    assert p.state=='AUTO_READ'
    bot.tick()
    assert p.state=='AUTO_FIND' and p.energy.spend_active
    assert p.auto_fish_id=='elmas_som'

def test_partial_energy_returns_to_hunt(bot):
    p=bot.profession;p.state='AUTO_READ';p.vision.energy.return_value=(20,100)
    bot.tick()
    assert p.state=='AUTO_CLOSE' and not p.energy.spend_active


def test_profession_modal_is_not_blocked_by_missing_map_observation(bot):
    p=bot.profession;p.state='AUTO_READ';p.vision.energy.return_value=(20,100)
    blocked = Observation(None, blocked='Avlan haritası görünmüyor veya ekran değişti.')
    assert p.handle(np.zeros((1080,1920,3), np.uint8), blocked, 1.0)
    assert p.state == 'AUTO_CLOSE'

def test_auto_completion_requires_observed_energy_decrease(bot):
    p=bot.profession;p.state='AUTO_VERIFY';p.auto_before=100;p.vision.energy.return_value=(100,100)
    bot.tick()
    assert bot.manual_pause and p.auto_cycles==0
    bot.mouse.click.assert_not_called()

def test_depleted_energy_ends_cycle_and_returns_to_farming(bot):
    p=bot.profession;p.state='AUTO_VERIFY';p.auto_before=1;p.energy.spend_active=True
    p.vision.energy.return_value=(0,100)
    bot.tick()
    assert p.auto_cycles==1 and p.state=='AUTO_CLOSE' and not p.energy.spend_active

def test_protection_preempts_inventory_and_energy_actions(bot):
    bot.detector.observe.return_value=Observation(None,protection=True,blocked='Bot koruması')
    bot.tick()
    bot.mouse.click.assert_not_called();bot.mouse.scroll.assert_not_called()
    assert bot.gate.latched

def test_dry_run_cannot_use_inventory_or_auto_collect(bot):
    bot.args.dry_run=True;bot.detector.find_fish_ripples.return_value=[]
    bot.tick()
    bot.mouse.click.assert_not_called();bot.mouse.scroll.assert_not_called()

def test_potion_attempt_survives_restart_and_pause(bot):
    p=bot.profession;p.record_potion(True);p.state='POTION_CONFIRM'
    bot.desktop.commands.put('pause');bot.tick()
    assert p.state=='POTION_CONFIRM' and p.potion_attempted
    from profession import ProfessionController
    restarted=ProfessionController(bot,p.journal.parent)
    assert restarted.potion_attempted
    p.manual_completed()
    assert not p.potion_attempted

def test_parser_keeps_manual_and_energy_fish_separate():
    args=main.parse_args(['--fish','ay_sazani','--energy-cycle','--auto-fish','komur_turna','--auto-splinter'])
    assert args.target_ids==('ay_sazani',) and args.auto_fish_id=='komur_turna'
    assert args.energy_cycle and args.auto_splinter


def test_kurtarma_yolu_varyilan_acik_kapatilabilir(tmp_path):
    """Kıymıkta önce iksir, sonra olta: bayrak verilmeden de açık olmalı."""
    def controller(**extra):
        bot=SimpleNamespace(detector=Mock(),notice=Mock(),
                            gate=SimpleNamespace(latched=False),
                            args=SimpleNamespace(energy_cycle=False,auto_fish_id='elmas_som',
                                                 dry_run=False,**extra))
        from profession import ProfessionController
        return ProfessionController(bot,tmp_path)
    assert controller().recovery_enabled is True
    assert controller().enabled is True
    assert controller(auto_splinter=True).recovery_enabled is True
    assert controller(auto_splinter=False).recovery_enabled is False
    assert main.parse_args(['--fish','ay_sazani']).auto_splinter is True
    assert main.parse_args(['--fish','ay_sazani','--auto-splinter']).auto_splinter is True
    assert main.parse_args(['--fish','ay_sazani','--no-auto-splinter']).auto_splinter is False

def test_running_auto_is_detected_with_pointer_over_stop(vision):
    frame=picture('auto-running.png')
    panel=Box(0,0,742,475)
    active=vision.active_collection(frame,panel)
    assert active.fish_id=='elmas_som'
    assert (active.progress,active.total)==(1,12)
    assert vision.rows(frame,panel)==[]

def test_partial_saved_energy_is_rechecked_at_start(tmp_path):
    store=EnergyStore(tmp_path/'energy.json');store.sync(42,100)
    assert not store.needs_sync()
    assert EnergyStore(store.path).needs_sync()
    store.last_sync-=181
    assert store.needs_sync()

def test_running_collection_is_never_clicked_again(bot):
    from profession_vision import ActiveCollection
    p=bot.profession;p.state='AUTO_WAIT';p.progress_at=100
    p.last_progress=11
    p.vision.active_collection.return_value=ActiveCollection('elmas_som',Box(10,10,60,20),1,12)
    p.handle(bot.detector.capture(),Observation(None,auto_collect=True),110)
    assert p.state=='AUTO_WAIT' and p.auto_cycles==1 and bot.cycles==1
    assert p.progress_at==110
    bot.mouse.click.assert_not_called()

def test_running_collection_respects_resume_gate(bot):
    bot.gate.block()
    p=bot.profession;p.state='AUTO_FIND'
    p.handle(bot.detector.capture(),Observation(None,auto_collect=True),100)
    assert bot.gate.latched
    bot.mouse.click.assert_not_called()
    bot.mouse.scroll.assert_not_called()

def test_unreadable_running_collection_pauses_instead_of_hanging(bot):
    p=bot.profession;p.state='AUTO_WAIT';p.progress_at=0;p.auto_started=0
    p.vision.rows.return_value=[]
    p.handle(bot.detector.capture(),Observation(None,auto_collect=True),100)
    assert bot.manual_pause
    bot.mouse.click.assert_not_called()

def test_dry_run_stop_does_not_touch_existing_game_collection(bot):
    bot.args.dry_run=True
    assert not bot.profession.stop_automatic()
    bot.mouse.click.assert_not_called()

def test_empty_energy_closes_modal_then_resumes_manual_search(bot):
    import time
    p=bot.profession;p.state='AUTO_VERIFY';p.auto_before=1;p.energy.spend_active=True
    p.vision.energy.return_value=(0,100)
    p.vision.inventory.return_value=None
    frame=bot.detector.capture();obs=Observation(Layout(193,238,1713,764))
    p.handle(frame,obs,time.monotonic())
    assert p.state=='AUTO_CLOSE' and not p.energy.spend_active
    p.close_auto=Mock(return_value=True)
    p.handle(frame,obs,time.monotonic())
    p.close_auto.assert_called_once()
    p.vision.auto_panel.return_value=None
    p.handle(frame,obs,time.monotonic())
    assert p.state=='RETURN'
    p.handle(frame,obs,time.monotonic())
    assert p.state=='IDLE' and bot.phase=='SEARCH' and bot.gate.latched


def test_ocr_variants_for_tool_recovery():
    assert recovery_reason('Gerekli alete sahip değilsiniz!') == 'tool'
    assert recovery_reason('gereldi alete sahip degilsinid') == 'tool'
    assert recovery_reason('gere:i alete sahip degilimid') == 'tool'
    assert recovery_reason('geriki alete sahip degiiiiid .') == 'tool'
    assert recovery_reason('Oyun uyarısı: gereldi alete sahip degilsinid') == 'tool'
    assert recovery_reason('Elinize kıymık battı') == 'splinter'
    assert recovery_reason('Elinize kiymik batti') == 'splinter'
    assert recovery_reason('ho_ne artik mevcut degil!') is None
    assert recovery_reason('Yeterli ustalığınız yok.') is None
    assert recovery_reason('Otomatik toplama devam ederken elle kaynak toplamak mümkün değil') == 'auto'


def test_tool_recovery_does_not_consume_potion_without_injury(bot):
    p = bot.profession
    p.state = 'IDLE'
    assert p.request_recovery('tool')
    assert p.state == 'EQUIP_OPEN'
    p.state = 'IDLE'
    assert p.request_recovery('splinter')
    assert p.state == 'POTION_OPEN'


def test_potion_confirm_transitions_to_equip_tab(bot):
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 3
    p.potion_applied = True
    p.since = 1000000000.0
    p.vision.auto_panel.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    p.vision.matches.return_value = [Box(410, 210, 40, 40), Box(460, 210, 40, 40)]
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    p.handle_inventory(frame)
    assert p.state == 'EQUIP_TAB'
    assert p.recoveries == 1


def test_side_bag_template_matches_combat_bag_on_navigation():
    import cv2
    from config import ROOT
    path = ROOT / 'assets' / 'profession-bag.png'
    template = cv2.imread(str(path), cv2.IMREAD_GRAYSCALE)
    assert template is not None
    nav = picture('navigation.png')
    gray = cv2.cvtColor(nav, cv2.COLOR_RGB2GRAY)
    score = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))[1]
    assert score > 0.85


def test_recovery_timeout_stops_infinite_retries(bot):
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.since = 0.0
    p.potion_count = 2
    p.vision.auto_panel.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    p.vision.matches.return_value = [Box(410, 210, 40, 40), Box(460, 210, 40, 40)]
    frame = np.zeros((600, 1000, 3), dtype=np.uint8)
    p.handle_inventory(frame)
    assert bot.manual_pause
    assert bot.sound.start_alarm_loop.called


def test_alert_kapat_template_is_loaded(vision):
    assert 'alert-kapat' in vision.templates
    assert vision.templates['alert-kapat'] is not None


def test_inventory_tabs_geometry_centers(vision):
    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    vision.inventory = Mock(return_value=Box(447, 261, 1453, 570))
    vision.words = Mock(return_value=[])
    tab_efekt = vision.inventory_tab(frame, 'Efektler')
    tab_esya = vision.inventory_tab(frame, 'Eşyalar')
    assert tab_efekt is not None and abs(tab_efekt.center[0] - 770) < 5
    assert tab_esya is not None and abs(tab_esya.center[0] - 850) < 5


def test_full_end_to_end_recovery_pipeline(bot):
    from unittest.mock import ANY
    p = bot.profession
    p.state = 'IDLE'
    p.energy_enabled = False
    p.recovery_enabled = True
    p.after_equip = 'RETURN'

    frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
    now = 1000.0

    # 1. Alert arrives: "Gerekli alete sahip değilsiniz!"
    obs = Observation(None, blocked='Gerekli alete sahip değilsiniz!')
    p.dismiss_alert = Mock(return_value=True)
    assert p.handle(frame, obs, now)
    p.dismiss_alert.assert_called_once()
    assert p.request_recovery('splinter')
    assert p.state == 'POTION_OPEN'

    # 2. POTION_OPEN: bag is clicked, opening inventory
    p.vision.auto_panel = Mock(return_value=None)
    p.vision.inventory = Mock(return_value=None)
    p.vision.bag_button = Mock(return_value=Box(641, 100, 39, 41))
    p.click = Mock(return_value=True)
    p.handle_inventory(frame)
    p.click.assert_called_with(frame, p.vision.bag_button, 'Üst menüdeki karakter çantası açılıyor.')

    # 3. Inventory opens -> transition to POTION_TAB
    inv_box = Box(447, 261, 1453, 570)
    p.vision.inventory = Mock(return_value=inv_box)
    p.handle_inventory(frame)
    assert p.state == 'POTION_TAB'

    # 4. POTION_TAB: Efektler tab clicked
    p.inventory_item = Mock(return_value=None)
    p.handle_inventory(frame)
    assert p.state == 'POTION_TAB'

    # 4b. Potion appears in Efektler -> transition to POTION_USE
    potion_box = Box(524, 277, 43, 47)
    p.inventory_item = Mock(return_value=potion_box)
    p.handle_inventory(frame)
    assert p.state == 'POTION_USE'

    # 5. POTION_USE: Potion clicked -> transition to POTION_CONFIRM
    p.vision.matches = Mock(return_value=[potion_box, Box(648, 277, 43, 47)])
    p.vision.words = Mock(return_value=[])
    def mock_click(frame, finder, message, hover_label=None, before_submit=None, allow_cursor_reacquire=False):
        if before_submit:
            before_submit()
        return True
    p.click = Mock(side_effect=mock_click)
    p.handle_inventory(frame)
    assert p.state == 'POTION_CONFIRM'
    assert p.potion_attempted is True

    # The game requires a separate Apply after selecting the potion.
    p.vision.potion_confirmation.return_value=Box(915,552,90,32)
    p.handle_inventory(frame)
    assert p.potion_applied
    p.vision.potion_confirmation.return_value=None

    # 6. POTION_CONFIRM: Count decreases from 2 to 1 -> transitions to EQUIP_TAB
    p.vision.matches = Mock(return_value=[potion_box])
    p.handle_inventory(frame)
    assert p.state == 'EQUIP_TAB'
    assert p.recoveries == 1

    # 7. EQUIP_TAB: Eşyalar tab clicked
    p.rod_equipped = Mock(return_value=False)
    p.inventory_item = Mock(return_value=None)
    p.handle_inventory(frame)
    assert p.state == 'EQUIP_TAB'

    # 7b. Rod appears in Eşyalar -> transition to EQUIP_USE
    rod_box = Box(770, 280, 49, 44)
    p.inventory_item = Mock(return_value=rod_box)
    p.handle_inventory(frame)
    assert p.state == 'EQUIP_USE'

    # 8. EQUIP_USE: Rod clicked -> transition to EQUIP_CONFIRM
    p.handle_inventory(frame)
    assert p.state == 'EQUIP_CONFIRM'

    # 9. EQUIP_CONFIRM: Rod is verified equipped on character doll -> transitions to RETURN
    p.rod_equipped = Mock(return_value=True)
    p.handle_inventory(frame)
    assert p.state == 'RETURN'

    # 10. RETURN: Inventory is closed via Geri dön
    p.vision.close_inventory = Mock(return_value=Box(1738, 182, 44, 8))
    p.handle(frame, Observation(None), now + 1)

    # 11. Return to Avlan fishing map (obs.clear = True) -> transitions to IDLE
    p.vision.inventory = Mock(return_value=None)
    clear_obs = Observation(Layout(195, 238, 1713, 764))
    p.handle(frame, clear_obs, now + 2)
    assert p.state == 'IDLE'

def test_real_potion_confirmation_is_not_an_injury_error(vision):
    frame=picture('potion-confirm.png')
    button=vision.potion_confirmation(frame)
    assert button and button.center==(240,138)
    assert vision.known_alert(frame) is None
    assert recovery_reason('Bunun sayesinde kıymıklardan kurtulabilirsiniz. İyileştirici İksir Kullanmak eylemini onaylayın') is None

def test_potion_confirmation_preempts_generic_error_handling(bot):
    p=bot.profession;p.state='POTION_CONFIRM';p.potion_count=4
    p.record_potion(True,'opened')
    p.vision.potion_confirmation.return_value=Box(915,552,90,32)
    p.dismiss_alert=Mock()
    def click(frame,finder,message,before_submit=None,**kwargs):
        if before_submit:before_submit()
        return True
    p.click=Mock(side_effect=click)
    p.vision.auto_panel.return_value=None
    frame=bot.detector.capture()
    p.handle(frame,Observation(None,blocked='Kıymıklardan kurtulabilirsiniz'),100)
    assert p.potion_applied and not bot.manual_pause
    p.dismiss_alert.assert_not_called()
    p.handle(frame,Observation(None,blocked='Kıymıklardan kurtulabilirsiniz'),101)
    p.click.assert_called_once()

def test_potion_submission_survives_restart_without_second_apply(bot):
    from profession import ProfessionController
    p=bot.profession;p.potion_count=4;p.record_potion(True,'submitted')
    restarted=ProfessionController(bot,p.journal.parent)
    assert restarted.state=='POTION_CONFIRM'
    assert restarted.potion_applied and restarted.potion_count==4


def test_unreadable_energy_reopens_the_window_instead_of_failing(bot):
    from config import ENERGY_READ_REOPENS
    p = bot.profession
    p.state = 'AUTO_READ'
    p.vision.energy.return_value = None
    for _ in range(3):
        p.last_action = 0          # the 0.8 s action limiter must not mask the loop
        bot.tick()
        assert p.state == 'AUTO_READ'
        assert not bot.manual_pause
    p.last_action = 0
    bot.tick()
    assert p.state == 'AUTO_CLOSE'
    assert p.energy_reopens == 1
    assert not bot.manual_pause
    assert ENERGY_READ_REOPENS >= 1


def test_energy_reopen_attempts_are_bounded(bot):
    from config import ENERGY_READ_REOPENS
    p = bot.profession
    p.state = 'AUTO_READ'
    p.energy_reopens = ENERGY_READ_REOPENS
    p.scans = 4                      # four blind scrolls already failed
    p.vision.energy.return_value = None
    p.last_action = 0
    bot.tick()
    assert bot.manual_pause
    assert p.energy_reopens == ENERGY_READ_REOPENS


def test_successful_energy_read_clears_the_reopen_counter(bot):
    p = bot.profession
    p.state = 'AUTO_READ'
    p.energy_reopens = 1
    p.vision.energy.return_value = (20, 100)
    bot.tick()
    assert p.energy_reopens == 0
    assert not bot.manual_pause


def test_potion_stack_drop_is_accepted_as_consumption_evidence(bot):
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.since = time.monotonic()
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    # The icon count is unchanged: the potion was used out of a stack.
    p.vision.matches.return_value = [Box(524, 277, 43, 47)]
    p.vision.badge_number.return_value = 4
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    assert p.state == 'EQUIP_TAB'
    assert p.recoveries == 1
    assert not bot.manual_pause


def test_potion_badge_pixel_change_is_consumption_evidence(bot):
    """Rozet OCR'da okunamazsa piksellerin değişmesi kanıt sayılır."""
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.potion_badge_px = np.zeros(37 * 11 * 3, np.uint8).tobytes()
    p.badge_pixels = lambda frame, box: np.full(37 * 11 * 3, 200, np.uint8).tobytes()
    p.since = time.monotonic()
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    p.vision.matches.return_value = [Box(524, 277, 43, 47)]
    p.vision.badge_number.return_value = None
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    assert p.state == 'EQUIP_TAB' and p.recoveries == 1
    assert not bot.manual_pause


def test_unchanged_badge_does_not_fake_consumption(bot):
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.potion_badge_px = np.zeros(37 * 11 * 3, np.uint8).tobytes()
    p.badge_pixels = lambda frame, box: np.zeros(37 * 11 * 3, np.uint8).tobytes()
    p.since = time.monotonic()
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    p.vision.matches.return_value = [Box(524, 277, 43, 47)]
    p.vision.badge_number.return_value = 5
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    assert p.state == 'POTION_CONFIRM'
    assert p.recoveries == 0


def test_potion_still_consumes_no_second_bottle_when_nothing_is_readable(bot):
    """Hiçbir kanıt okunamasa bile bot durmaz: onay penceresi kapandı, çanta
    okunuyor ve uyarı yoksa tüketim kabul edilip oltaya dönülür. Kullanıcının
    F8 ile sürdürmesini beklemek yerine akış devam eder."""
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_attempted = True
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.since = 0.0
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = Box(400, 200, 800, 400)
    p.vision.matches.return_value = [Box(524, 277, 43, 47)]
    p.vision.badge_number.return_value = 5
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    assert p.state == 'EQUIP_TAB'
    assert p.recoveries == 1 and not p.potion_attempted
    assert not bot.manual_pause


def test_potion_still_fails_when_the_inventory_is_never_readable(bot):
    """Çanta hiç okunamadıysa (kanıt penceresi de yoksa) eski güvenlik durur."""
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_attempted = True
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.since = 0.0
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = None
    p.vision.matches.return_value = []
    p.vision.badge_number.return_value = None
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    assert bot.manual_pause
    assert p.potion_attempted and p.recoveries == 0


def _badge_frame(digit=None, box=Box(524, 277, 43, 47)):
    """Oyunla aynı ölçülerde yapay slottan bir kare: mor slot zemini,
    koyu rozet ve beyaz rakam (çanta ekranında rozet tam bu renklerde)."""
    frame = np.full((1080, 1920, 3), (150, 110, 175), np.uint8)
    if digit is None:
        return frame
    image = Image.fromarray(frame)
    draw = ImageDraw.Draw(image)
    # Rozet kutusu slotun sol-altına taşar; oyunun canlı karesindeki konum.
    badge = Box(box.x - 6, box.y + 38, 33, 15)
    draw.rectangle([badge.x, badge.y, badge.x + badge.w - 1, badge.y + badge.h - 1],
                   fill=(110, 83, 76))
    font = ImageFont.truetype(str(Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf')), 12)
    draw.text((badge.x + 7, badge.y + 2), str(digit), font=font, fill=(255, 255, 255))
    return np.array(image)


def test_synthetic_badge_is_read_with_the_dedicated_ocr():
    box = Box(524, 277, 43, 47)
    detector = ScreenDetector(grabber=None)
    controller = ProfessionController.__new__(ProfessionController)
    controller.vision = ProfessionVision(detector)
    try:
        for digit in (4, 5, 12):
            assert controller.stack_number(_badge_frame(digit), box) == digit
        # Rozet olmayan slotta uydurma bir sayı çıkmamalı.
        assert controller.stack_number(_badge_frame(None), box) is None
        before = controller.badge_pixels(_badge_frame(4), box)
        after = controller.badge_pixels(_badge_frame(5), box)
        assert before is not None and after is not None
        assert ProfessionController.badge_changed(before, after)
        assert not ProfessionController.badge_changed(before, before)
    finally:
        detector.close()


def _live_inventory_frame():
    """Çantanın açık olduğu tek gerçek kare; masaüstü/panel karelerinde
    rozet testleri koşmaz (runtime/last-pause.png her duraklatmada değişir)."""
    live = Path(__file__).parents[1] / 'runtime' / 'last-pause.png'
    if not live.exists():
        pytest.skip('canlı çanta karesi yok')
    image = np.array(Image.open(live).convert('RGB'))
    detector = ScreenDetector(grabber=None)
    if not ProfessionVision(detector).inventory(image):
        detector.close()
        pytest.skip('son duraklatma karesi çanta görünümü değil')
    detector.close()
    return image


def test_badge_region_stays_on_the_slot_badge():
    image = _live_inventory_frame()
    box = Box(524, 277, 43, 47)
    region = ProfessionController.badge_region(image, box)
    # Rozet kutusu koyu zeminden aranır ve komşu slota taşmaz.
    assert region is not None
    assert box.x - 8 <= region.x <= box.x + box.w
    assert region.x + region.w <= box.x + box.w + 8
    assert region.y + region.h <= box.y + box.h + 8
    assert region.x <= 534 <= region.x + region.w
    assert ProfessionController.badge_region(None, box) is None
    assert ProfessionController.badge_region(image, None) is None


def test_live_badge_is_read_with_the_dedicated_ocr():
    image = _live_inventory_frame()
    box = Box(524, 277, 43, 47)
    detector = ScreenDetector(grabber=None)
    controller = ProfessionController.__new__(ProfessionController)
    controller.vision = ProfessionVision(detector)
    try:
        assert controller.stack_number(image, box) == 4
        # İlk slotta rozet yok (adet 1); komşuların rozetleri de doğru okunur.
        assert controller.stack_number(image, Box(633, 277, 43, 47)) == 4
        assert controller.stack_number(image, Box(688, 277, 43, 47)) == 5
    finally:
        detector.close()


def test_profession_ocr_cache_overflow_is_pruned_without_crashing():
    """Kıymık akışında onbellek 32 anahtarı aşınca profession_vision'daki
    dict.popitem(last=False) botu çökertiyordu (screen_detector'daki aynı hata
    gibi budanmalı)."""
    detector = ScreenDetector(grabber=None)
    vision = ProfessionVision(detector)
    try:
        for i in range(40):
            vision.cache[(('overflow', i), bytes([i % 256]) * 12)] = []
        frame = np.zeros((24, 32, 3), np.uint8)
        vision.badge_number(frame, Box(0, 0, 16, 16))
        vision.words(frame, Box(0, 0, 16, 16))
        assert len(vision.cache) <= 32
    finally:
        detector.close()


def test_potion_slot_and_stack_survive_restart(bot):
    """Yeniden başlatmada slot/yığın geri yüklenmezse doğrulama kanıtı kalmaz."""
    from profession import ProfessionController
    p = bot.profession
    p.potion_count = 1
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.record_potion(True, 'submitted')
    restarted = ProfessionController(bot, p.journal.parent)
    assert restarted.state == 'POTION_CONFIRM'
    assert restarted.potion_box == Box(524, 277, 43, 47)
    assert restarted.potion_stack == 5
    # Eski (kutusuz) kayıtlar da sorunsuz okunmalı.
    p.journal.write_text('{"pending": true, "stage": "submitted", "count": 1}')
    legacy = ProfessionController(bot, p.journal.parent)
    assert legacy.state == 'POTION_CONFIRM' and legacy.potion_box is None


def test_potion_confirm_reopens_the_bag_when_the_inventory_is_unreadable(bot):
    """Oyun onaydan sonra çantayı kapatırsa doğrulama kilitlenmesin."""
    p = bot.profession
    p.state = 'POTION_CONFIRM'
    p.potion_count = 1
    p.potion_applied = True
    p.potion_box = Box(524, 277, 43, 47)
    p.potion_stack = 5
    p.since = time.monotonic()
    p.last_action = 0
    p.vision.auto_panel.return_value = None
    p.vision.potion_confirmation.return_value = None
    p.vision.inventory.return_value = None
    p.vision.bag_button.return_value = Box(700, 40, 30, 30)
    p.click = Mock(return_value=True)
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    p.click.assert_called_once()
    assert p.state == 'POTION_CONFIRM'
    assert not bot.manual_pause


def test_equip_tab_reopens_the_bag_when_the_inventory_is_unreadable(bot):
    p = bot.profession
    p.state = 'EQUIP_TAB'
    p.last_action = 0
    p.vision.auto_panel.return_value = None
    p.vision.inventory.return_value = None
    p.vision.bag_button.return_value = Box(700, 40, 30, 30)
    p.click = Mock(return_value=True)
    p.handle_inventory(np.zeros((600, 1000, 3), dtype=np.uint8))
    p.click.assert_called_once()
    assert p.state == 'EQUIP_TAB'
    assert not bot.manual_pause
