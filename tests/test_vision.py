from pathlib import Path
import cv2
import numpy as np
from PIL import Image
import pytest
from screen_detector import ScreenDetector, Fish, Layout

FIXTURES = Path(__file__).parent / 'fixtures'


@pytest.fixture
def detector():
    d = ScreenDetector()
    yield d
    d.close()


def frame(name):
    return np.array(Image.open(FIXTURES / name).convert('RGB'))


def test_green_targets_stay_in_river_and_include_isolated_rings(detector):
    f = frame('green-map.png')
    obs = detector.observe(f)
    assert obs.clear
    assert 1508 <= obs.layout.right <= 1522
    fish = detector.find_fish_ripples(f, obs.layout)
    for expected in [(200,96), (180,136), (169,498), (250,411)]:
        assert any(np.hypot(t.x-expected[0], t.y-expected[1]) < 13 for t in fish), expected
    assert all(50 < t.x < 300 for t in fish)
    assert detector.find_yakala_button(f, obs.layout) is None


def test_shifted_map_produces_shifted_targets(detector):
    f = frame('green-map.png')
    shifted = np.zeros((f.shape[0]+130, f.shape[1]+260, 3),dtype=np.uint8)
    shifted[80:80+f.shape[0],130:130+f.shape[1]] = f
    targets = detector.find_fish_ripples(shifted)
    assert any(np.hypot(t.x-330,t.y-176)<13 for t in targets)
    assert all(t.y >= 130 for t in targets)


def test_scrolling_changes_target_positions(detector):
    before = detector.find_fish_ripples(frame('green-selected.png'))
    after = detector.find_fish_ripples(frame('scrolled.png'))
    assert before and after
    assert {(f.x,f.y) for f in before} != {(f.x,f.y) for f in after}


def test_yakala_returns_round_action_icon_not_text_label(detector):
    f=frame('green-selected.png')
    l=detector.detect_layout(f)
    button=detector.find_yakala_button(f,l)
    # Measured in the live browser: icon (597,214), cropped by (180,175).
    assert button is not None and np.hypot(button[0]-417,button[1]-39)<5
    assert 'kadife' in detector.selected_fish_name(f,l)


def test_actual_protection_blocks_actions(detector):
    obs=detector.observe(frame('protection.png'))
    assert obs.protection and not obs.clear


def test_protection_does_not_depend_on_colored_puzzle_piece(detector):
    f=frame('protection.png')
    f[340:440,600:750] = (70,45,29)  # Hide the bright puzzle piece, retain heading.
    assert detector.observe(f).protection


def test_ocr_fallback_detects_protection_without_templates(detector):
    detector.templates=[]
    assert detector.observe(frame('protection.png')).protection


def test_harvesting_and_other_dialog_are_distinguished(detector):
    progress=detector.observe(frame('harvesting.png'))
    assert progress.harvesting and not progress.protection and not progress.clear
    unknown=detector.observe(frame('other-dialog.png'))
    assert unknown.blocked and not unknown.harvesting and not unknown.clear


def test_non_game_screen_is_not_actionable(detector):
    assert not detector.observe(np.full((600,1000,3),35,np.uint8)).clear

def test_valid_map_without_visible_water_can_be_scrolled(detector,monkeypatch):
    monkeypatch.setattr(detector,'water_mask',lambda crop:np.zeros(crop.shape[:2],np.uint8))
    f=frame('green-map.png')
    assert detector.observe(f).clear
    assert detector.find_fish_ripples(f)==[]


def test_green_filter_rejects_purple_and_purple_filter_finds_it(detector):
    f=frame('green-map.png')
    r,g,b=f.astype(np.int16).transpose(2,0,1)
    green=(g>110)&(g>r+40)&(g>b+25)
    f[green]=(170,50,230)
    assert not detector.find_fish_ripples(f,target_color='yesil')
    purple=detector.find_fish_ripples(f,target_color='mor')
    assert purple and all(fish.color=='mor' for fish in purple)


@pytest.mark.parametrize('color,rgb',[
    ('beyaz',(215,220,225)),('mavi',(20,185,255)),
    ('mor',(145,30,235)),('kirmizi',(240,35,30)),('sari',(240,190,35)),
])
def test_each_color_finds_rings_without_selecting_the_river(detector,color,rgb):
    f=frame('green-map.png')
    r,g,b=f.astype(np.int16).transpose(2,0,1)
    mask=(g>110)&(g>r+40)&(g>b+25)
    f[mask]=rgb
    targets=detector.find_fish_ripples(f,target_color=color)
    assert any(np.hypot(t.x-200,t.y-96)<13 for t in targets)
    assert all(50<t.x<300 and t.color==color for t in targets)


def test_real_purple_text_is_not_misclassified_as_blue(detector):
    from fish_catalog import resolve_name
    f=frame('purple-selected.png');layout=detector.detect_layout(f)
    assert detector.selected_fish_color(f,layout)=='mor'
    assert resolve_name(detector.selected_fish_name(f,layout)).id=='billur_mersin'
    targets=detector.find_fish_ripples(f,layout,target_color='mor')
    assert targets and all(fish.color=='mor' for fish in targets)
    assert not detector.find_fish_ripples(f,layout,target_color='mavi')


def test_mastery_error_is_blocked_and_not_recorded_as_collection(detector):
    obs=detector.observe(frame('mastery-error.png'))
    assert obs.blocked and 'ustalık' in obs.blocked
    assert not obs.clear and not obs.harvesting
    # Ustalık uyarısı panelde düzeltilecek; bot kendiliğinden kapatmaz.
    assert obs.close_button is None


def test_gone_object_warning_exposes_its_close_button(detector):
    f=frame('warning-object-gone.png')
    obs=detector.observe(f)
    assert obs.blocked and obs.blocked.startswith('Oyun uyarısı')
    assert not obs.clear
    # Kapat düğmesi bu karede kırmızı bileşen olarak (893,491)-(1014,508).
    assert (893,491) <= obs.close_button <= (1014,508)
    # Tıklamadan hemen önceki yeniden okuma aynı düğmeyi bulabilmeli.
    assert detector.find_close_button(f,obs.layout)==obs.close_button


def test_missing_tool_warning_is_read_from_the_body_not_the_title(detector):
    from profession_vision import recovery_reason
    f = frame('warning-tool-missing.png')
    obs = detector.observe(f)
    # Başlık OCR'i sarı üstünden "——" okuyor; sınıf gövde metninden kuruluyor.
    assert obs.blocked and obs.blocked.startswith('Oyun uyarısı')
    assert 'alete sahip' in obs.blocked
    assert recovery_reason(obs.blocked) == 'tool'
    # kapat düğmesi bu karede (953, 499) merkezinde.
    assert (888,487) <= obs.close_button <= (1020,512)
    assert detector.find_close_button(f,obs.layout)==obs.close_button


def test_clean_or_unknown_screens_never_offer_a_close_button(detector):
    for name in ('green-map.png','other-dialog.png'):
        f=frame(name)
        obs=detector.observe(f)
        assert obs.close_button is None, name
        assert detector.find_close_button(f,obs.layout) is None, name


def test_failed_capture_never_reuses_previous_screenshot(monkeypatch):
    import subprocess
    # Screenshot path only: the fast X11 path never reads this file.
    detector=ScreenDetector(grabber=None)
    image=detector.path/'screen.png'
    Image.fromarray(frame('green-map.png')).save(image)
    real_run=subprocess.run
    # Only the screenshot command fails; unrelated platform probes still run.
    def fail(cmd,*a,**kw):
        if cmd and cmd[0]=='spectacle':
            raise subprocess.TimeoutExpired('spectacle',5)
        return real_run(cmd,*a,**kw)
    monkeypatch.setattr(subprocess,'run',fail)
    monkeypatch.setattr(detector,'_capture_portal',lambda: None)
    with pytest.raises(subprocess.TimeoutExpired):detector.capture()
    assert not image.exists()
    detector.close()

def test_ocr_timeout_is_retryable_without_returning_stale_text(detector,monkeypatch):
    import subprocess
    def timeout(*args,**kwargs):raise subprocess.TimeoutExpired('tesseract',4)
    monkeypatch.setattr(subprocess,'run',timeout)
    with pytest.raises(InterruptedError,match='yeniden kontrol'):
        detector.ocr(frame('green-map.png'))


def test_tesseract_runs_in_its_own_session(detector,monkeypatch):
    """Terminal Ctrl+C tesseract'ı öldürmemeli; Python kendi SIGINT
    işleyicisiyle temiz durur, OCR çağrısı tamamlanır. Aynı oturumda
    çalışsaydı CalledProcessError traceback'i "bot hata" süsü veriyordu."""
    import subprocess
    seen={}
    def fake_run(cmd,**kwargs):
        seen['kwargs']=kwargs
        seen['cmd']=cmd
        return subprocess.CompletedProcess(cmd,0,stdout='',stderr='')
    monkeypatch.setattr(subprocess,'run',fake_run)
    detector.ocr(frame('green-map.png'))
    assert seen['cmd'][0]=='tesseract'
    assert seen['kwargs'].get('start_new_session') is True


def test_reacquire_fish_keeps_same_target_when_ring_is_visible(detector):
    f=frame('green-map.png');layout=detector.detect_layout(f)
    target=min(detector.find_fish_ripples(f,layout,target_color='yesil'),
               key=lambda fish:np.hypot(fish.x-200,fish.y-96))
    fresh=detector.reacquire_fish(f,layout,target)
    assert fresh is not None
    assert fresh.color=='yesil'
    assert np.hypot(fresh.x-target.x,fresh.y-target.y)<5


def test_reacquire_fish_has_local_color_fallback_when_hough_misses(detector,monkeypatch):
    f=frame('green-map.png');layout=detector.detect_layout(f)
    target=min(detector.find_fish_ripples(f,layout,target_color='yesil'),
               key=lambda fish:np.hypot(fish.x-200,fish.y-96))
    monkeypatch.setattr(detector,'find_fish_ripples',lambda *a,**kw:[])
    fresh=detector.reacquire_fish(f,layout,target)
    assert fresh is not None
    assert fresh.color=='yesil'
    assert np.hypot(fresh.x-target.x,fresh.y-target.y)<16


def test_reacquire_fish_never_substitutes_distant_same_color_target(detector):
    f=frame('green-map.png');layout=detector.detect_layout(f)
    target=Fish(650,550,18,100,'yesil')
    assert detector.reacquire_fish(f,layout,target,max_distance=30) is None

def test_white_fish_ignore_gravestones_outside_pond(detector):
    targets=detector.find_fish_ripples(frame('white-pond.png'),target_color='beyaz')
    assert len(targets)>8
    for point in [(326,562),(388,552),(1064,540)]:
        assert all(np.hypot(f.x-point[0],f.y-point[1])>30 for f in targets)


def test_partial_ring_is_not_replaced_by_neighbouring_full_circle(detector,monkeypatch):
    f=frame('green-map.png');layout=detector.detect_layout(f)
    target=min(detector.find_fish_ripples(f,layout,target_color='yesil'),
               key=lambda fish:np.hypot(fish.x-200,fish.y-96))
    neighbour=Fish(target.x+32,target.y,18,200,'yesil')
    monkeypatch.setattr(detector,'find_fish_ripples',lambda *a,**kw:[neighbour])
    fresh=detector.reacquire_fish(f,layout,target)
    assert fresh is not None and fresh!=neighbour
    assert np.hypot(fresh.x-target.x,fresh.y-target.y)<16


def test_live_short_fish_header_resolves_in_name_mode(detector):
    from fish_catalog import resolve_name
    text=detector.ocr(frame('ay-sazani-header.png'),psm=7,scale=4)
    assert resolve_name(text).id=='ay_sazani'


def test_ocr_cache_overflow_is_pruned_without_crashing(detector):
    """Uyari/panel ekraninda her tik farkli piksel uretir; 64 girdiyi asan
    onbellek sessizce budanmali (dict.popitem(last=False) patliyordu)."""
    for i in range(70):
        detector._ocr_cache[(('overflow', i), 7, 3, bytes([i % 256]) * 12)] = (0.0, 'x')
    detector.ocr(frame('ay-sazani-header.png'), psm=7, scale=1)
    assert len(detector._ocr_cache) <= 64


def test_protection_shortcut_matches_full_scale_everywhere():
    """The half-resolution pass may only rule a screen out, never decide it."""
    import cv2
    from screen_detector import PROTECTION_TEMPLATE_THRESHOLD, PROTECTION_FAST_REJECT
    d = ScreenDetector()
    try:
        def full_scale(img):
            h, w = img.shape[:2]
            gray = cv2.cvtColor(img[int(h*.15):int(h*.88), int(w*.18):int(w*.82)], cv2.COLOR_RGB2GRAY)
            for template in d.templates:
                if template.shape[0] <= gray.shape[0] and template.shape[1] <= gray.shape[1]:
                    score = cv2.minMaxLoc(cv2.matchTemplate(gray, template, cv2.TM_CCOEFF_NORMED))[1]
                    if score >= PROTECTION_TEMPLATE_THRESHOLD:
                        return True
            return False
        checked = 0
        for path in sorted(FIXTURES.glob('*.png')):
            img = frame(path.name)
            if img.shape[0] < 200 or img.shape[1] < 400:
                continue
            assert d.protection_template(img) == full_scale(img), path.name
            checked += 1
        assert checked >= 10
        assert PROTECTION_FAST_REJECT < 1.0
    finally:
        d.close()


def test_panel_probe_is_rate_limited_until_an_input_forces_it(detector):
    from unittest.mock import Mock
    from profession_vision import Box
    detector.auto_panel_interval = 5.0
    detector.profession_vision = Mock()
    detector.profession_vision.auto_panel.return_value = None
    img = frame('navigation.png')
    assert detector.auto_panel_probe(img) is False
    assert detector.auto_panel_probe(img) is False
    assert detector.profession_vision.auto_panel.call_count == 1
    detector.auto_panel_probe(img, force=True)
    assert detector.profession_vision.auto_panel.call_count == 2
    # Once a probe actually sees a panel, it must run on every frame until
    # another probe reports the panel closed.
    detector.profession_vision.auto_panel.return_value = Box(590, 250, 742, 475)
    assert detector.auto_panel_probe(img, force=True) is True
    assert detector.auto_panel_probe(img) is True
    assert detector.auto_panel_probe(img) is True
    assert detector.profession_vision.auto_panel.call_count == 5


def sea_frame(sea_rows, height=400, width=600):
    """Karanlık arazi üzerinde mavi bir deniz şeridi olan yapay harita."""
    img = np.full((height, width, 3), 40, np.uint8)
    img[sea_rows[0]:sea_rows[1]] = (60, 80, 150)
    return img


def test_widthwise_sea_band_stops_the_pointless_vertical_scroll(detector):
    # Bazı haritalarda deniz yalnızca genişliği boyunca uzanır; aşağı/yukarı
    # kaydırmak suyu görüşten çıkarır.
    layout = Layout(0, 0, 600, 400)
    assert detector.sea_extends_vertically(sea_frame((150, 250)), layout) is False


def test_lengthwise_sea_keeps_the_vertical_scroll(detector):
    layout = Layout(0, 0, 600, 400)
    assert detector.sea_extends_vertically(sea_frame((0, 400)), layout) is True
    assert detector.sea_extends_vertically(sea_frame((40, 400)), layout) is True


def test_scattered_water_pixels_do_not_make_a_band_look_vertical(detector):
    """Canlı harita: üstte bir şerit ve altta dağınık su pikselleri."""
    img = sea_frame((0, 120), height=520, width=1497)
    rng = np.random.default_rng(7)
    stray = rng.random((520, 1497)) < 0.04
    img[stray] = (60, 80, 150)
    assert detector.sea_extends_vertically(img, Layout(0, 0, 1497, 520)) is False


def test_unreadable_sea_never_blocks_scrolling(detector):
    layout = Layout(0, 0, 600, 400)
    assert detector.sea_extends_vertically(np.full((400, 600, 3), 40, np.uint8), layout) is True
    assert detector.sea_extends_vertically(np.zeros((400, 600, 3), np.uint8), layout) is True
    assert detector.sea_extends_vertically(sea_frame((150, 250)), None) is True
