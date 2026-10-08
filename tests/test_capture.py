from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

import time

import main
from main import FishingBot
from screen_detector import ScreenDetector
from x11grab import covers_screen, bgra_to_rgb


class FakeGrabber:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    def grab(self):
        self.calls += 1
        return self.result


def test_bgra_to_rgb_swaps_the_channels_xwayland_gives_us():
    # one row: B,G,R,A for red then for blue
    data = bytes([0, 0, 255, 255, 255, 0, 0, 255])
    frame = bgra_to_rgb(data, 2, 1)
    assert frame.tolist() == [[[255, 0, 0], [0, 0, 255]]]


def test_bgra_to_rgb_rejects_a_truncated_image():
    with pytest.raises(ValueError):
        bgra_to_rgb(b"\x00" * 63, 4, 4)


def test_only_a_full_screen_window_replaces_the_screenshot():
    assert covers_screen((0, 0, 1920, 1080), (1920, 1080))
    assert covers_screen((2, 2, 1920, 1080), (1920, 1080))
    # maximized under a top panel and a plain window both keep spectacle
    assert not covers_screen((0, 40, 1920, 1040), (1920, 1080))
    assert not covers_screen((300, 200, 1280, 720), (1920, 1080))


def test_capture_returns_the_window_and_records_its_region(monkeypatch):
    window = np.full((1080, 1920, 3), 7, np.uint8)
    detector = ScreenDetector(grabber=FakeGrabber((window, (0, 0, 1920, 1080))))
    monkeypatch.setattr(detector, "_capture_spectacle",
                        lambda: pytest.fail("X11 karesi varken spectacle çalışmamalı"))
    frame = detector.capture()
    assert frame is window
    assert detector.capture_rect == (0, 0, 1920, 1080)
    detector.close()


def test_focus_lost_for_ten_minutes_raises_the_alarm(monkeypatch, tmp_path):
    detector = ScreenDetector(grabber=FakeGrabber(None))
    detector._capture_portal = lambda: None
    detector._capture_spectacle = lambda: np.zeros((1080, 1920, 3), np.uint8)
    bot = _bot(monkeypatch, tmp_path, detector)
    # Mock masaüstünde commands gerçek kuyruk olmalı; yoksa control_guard
    # sonsuz döngüye girer (RAM şişmesi bu testten geliyordu).
    import queue as _queue
    active = {'game': False}
    desktop = SimpleNamespace(commands=_queue.Queue(),
                              is_game_active=lambda: active['game'],
                              state={'app': 'zcode', 'title': 'ZCode',
                                     'geometry': [0, 0, 1920, 1080], 'screens': 1})
    bot.desktop = desktop
    bot.focus_lost_since = time.monotonic() - 601.0
    bot.next_focus_alert = time.monotonic() - 1.0
    bot.sound = Mock()
    bot.tick()
    bot.sound.play_once.assert_called_once()
    # vade yenilendi: ikinci tik alarma tekrar girmez
    bot.tick()
    assert bot.sound.play_once.call_count == 1
    # oyun dönerse sayaçlar sıfırlanır
    active['game'] = True
    bot.tick()
    assert bot.focus_lost_since is None


def test_capture_falls_back_to_portal_then_screenshot_when_window_is_gone(monkeypatch):
    """X11 yolu yokken sıra: portal (~0.18 sn) → spectacle (~0.4 sn). Portal
    başarısızsa spectacle aynen kullanılır; ikisi de yoksa hata yükselir."""
    portal_frame = np.full((1080, 1920, 3), 7, np.uint8)
    detector = ScreenDetector(grabber=FakeGrabber(None))
    monkeypatch.setattr(detector, "_capture_portal", lambda: portal_frame)
    assert detector.capture() is portal_frame
    assert detector.capture_rect == (0, 0, 1920, 1080)

    spectacle = np.zeros((1080, 1920, 3), np.uint8)
    monkeypatch.setattr(detector, "_capture_portal", lambda: None)
    monkeypatch.setattr(detector, "_capture_spectacle", lambda: spectacle)
    assert detector.capture() is spectacle
    assert detector.capture_rect is None
    detector.close()


def test_portal_failure_never_breaks_capture(monkeypatch):
    detector = ScreenDetector(grabber=FakeGrabber(None))
    def boom():
        raise InterruptedError('Portal yanıt vermedi.')
    monkeypatch.setattr(detector, "_capture_portal", boom)
    spectacle = np.ones((1080, 1920, 3), np.uint8)
    monkeypatch.setattr(detector, "_capture_spectacle", lambda: spectacle)
    assert detector.capture() is spectacle
    detector.close()


def _bot(monkeypatch, tmp_path, detector):
    monkeypatch.setattr(main, 'RUNTIME', tmp_path)
    desktop = Mock()
    desktop.state = {'geometry': [0, 0, 1920, 1080], 'screens': 1}
    return FishingBot(desktop, detector, Mock(), Mock(),
                      SimpleNamespace(dry_run=False, no_scroll=False))


def test_pixel_to_desktop_uses_the_captured_region(monkeypatch, tmp_path):
    detector = Mock()
    detector.capture_rect = (60, 40, 960, 540)
    bot = _bot(monkeypatch, tmp_path, detector)
    frame = np.zeros((540, 960, 3), np.uint8)
    assert bot.pixel_to_desktop((480, 270), frame) == (540, 310)
    assert bot.desktop_scale(frame) == 1.0


def test_pixel_to_desktop_without_a_region_uses_the_whole_screen(monkeypatch, tmp_path):
    detector = Mock()
    detector.capture_rect = None
    bot = _bot(monkeypatch, tmp_path, detector)
    frame = np.zeros((1080, 1920, 3), np.uint8)
    assert bot.pixel_to_desktop((400, 500), frame) == (400, 500)
    assert bot.desktop_scale(frame) == 1.0


class _Geom:
    width = 800
    height = 600


class _FakeWindow:
    def get_attributes(self):
        from types import SimpleNamespace
        return SimpleNamespace(map_state=2)  # IsViewable

    def get_geometry(self):
        return _Geom()

    def get_image(self, *args):
        w, h = _Geom.width, _Geom.height
        data = bytearray(w * h * 4)
        for i in range(w * h):
            data[i * 4] = 255        # B
            data[i * 4 + 2] = 40     # R
            data[i * 4 + 3] = 255    # A
        from types import SimpleNamespace
        return SimpleNamespace(data=bytes(data))


def test_partial_window_is_grabbed_when_fullscreen_is_off(monkeypatch):
    """Kullanıcı oyun penceresini boyutlandırdığında X11 yolu 'tam ekran
    değil' deyip her karede spectacle'a (~0.4 sn) düşüyordu; kısmi pencere
    artık capture_rect ile yakalanır."""
    from types import SimpleNamespace
    from x11grab import X11Grabber
    grabber = X11Grabber(fullscreen_only=False)
    fake = _FakeWindow()
    monkeypatch.setattr(grabber, '_locate', lambda: fake)
    monkeypatch.setattr(grabber, '_origin', lambda window: (10, 20))
    out = grabber.grab()
    assert out is not None
    frame, rect = out
    assert rect == (10, 20, 800, 600)
    assert frame.shape == (600, 800, 3)


def test_fullscreen_only_grabber_still_rejects_partial_windows(monkeypatch):
    from types import SimpleNamespace
    from x11grab import X11Grabber
    grabber = X11Grabber(fullscreen_only=True)
    fake = _FakeWindow()
    monkeypatch.setattr(grabber, '_locate', lambda: fake)
    monkeypatch.setattr(grabber, '_covers_screen', lambda rect: False)
    assert grabber.grab() is None
