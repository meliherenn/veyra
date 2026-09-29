from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

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


def test_capture_falls_back_to_the_screenshot_when_the_window_is_gone(monkeypatch):
    screenshot = np.zeros((1080, 1920, 3), np.uint8)
    detector = ScreenDetector(grabber=FakeGrabber(None))
    monkeypatch.setattr(detector, "_capture_spectacle", lambda: screenshot)
    assert detector.capture() is screenshot
    assert detector.capture_rect is None
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
