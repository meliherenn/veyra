"""Read the game window straight out of Xwayland: no portal, no dialog, no file.

The browser that hosts the game is an X client (Xwayland), so the pixels are
already in the X server and can be pulled with a single round-trip instead of
going through spectacle (~0.5 s per frame, single-instance, writes a PNG).
When the window is not there - Wayland-native browser, game closed - the caller
simply falls back to the screenshot path.
"""
from __future__ import annotations

import re
import time

import cv2
import numpy as np
from Xlib import X, display
from Xlib.error import XError

TITLE_PATTERN = re.compile(r"ejderhalar", re.I)
# After a miss (no window, transient X error) the next attempt is deferred so a
# Wayland-native setup does not pay for a full window search on every frame.
RETRY_SECONDS = 2.0
# The rest of the bot (templates, click mapping) is written for a frame that
# covers the screen, so a windowed browser keeps the screenshot path.
FULLSCREEN_TOLERANCE = 4


def bgra_to_rgb(data: bytes, width: int, height: int) -> np.ndarray:
    """Xwayland ZPixmap rows are B,G,R,A; the bot works in RGB."""
    if width <= 0 or height <= 0 or len(data) < width * height * 4:
        raise ValueError(f"invalid x11 image {width}x{height} from {len(data)} bytes")
    stride = len(data) // height
    bytes_pp = stride // width if stride % width == 0 else 4
    if bytes_pp < 3 or stride < width * bytes_pp:
        raise ValueError(f"unsupported x11 layout: {width}px wide, stride {stride}")
    rows = np.frombuffer(data, dtype=np.uint8).reshape(height, stride)
    pixels = rows[:, :width * bytes_pp].reshape(height, width, bytes_pp)
    # cv2 tek geciste (SIMD) dondurur; numpy'in negatif-ekli kopyasi ~12x yavas
    # (6.4 -> 0.5 ms) ve piksel piksel ayni sonucu veriyor.
    return cv2.cvtColor(np.ascontiguousarray(pixels),
                        cv2.COLOR_BGRA2RGB if bytes_pp == 4 else cv2.COLOR_BGR2RGB)


def covers_screen(rect, screen, slack=FULLSCREEN_TOLERANCE):
    """True when the window occupies the whole screen within `slack` pixels."""
    x, y, width, height = rect
    screen_width, screen_height = screen
    return (abs(x) <= slack and abs(y) <= slack
            and x + width >= screen_width - slack
            and y + height >= screen_height - slack)


class X11Grabber:
    def __init__(self, pattern=TITLE_PATTERN, fullscreen_only=True):
        self.pattern = re.compile(pattern, re.I) if isinstance(pattern, str) else pattern
        self.fullscreen_only = fullscreen_only
        self._display = None
        self._window = None
        self._missed_at = 0.0

    def close(self):
        if self._display is not None:
            try:
                self._display.close()
            except Exception:
                pass
            self._display = None
        self._window = None

    def grab(self):
        """Return (frame, (x, y, w, h)) in screen coordinates, or None."""
        if (self._window is None and self._missed_at
                and time.monotonic() - self._missed_at < RETRY_SECONDS):
            return None
        try:
            return self._grab()
        except Exception:
            # Anything unexpected (stale window, odd X error, import problem)
            # means "no fast path this frame": the screenshot path still works.
            self._window = None
            self._missed_at = time.monotonic()
            return None

    def _connect(self):
        if self._display is None:
            self._display = display.Display()
        return self._display

    def _grab(self):
        window = self._window if self._window is not None and self._alive() else self._locate()
        if window is None:
            self._missed_at = time.monotonic()
            return None
        geom = window.get_geometry()
        if geom.width < 400 or geom.height < 200:
            self._window = None
            self._missed_at = time.monotonic()
            return None
        rect = self._origin(window) + (geom.width, geom.height)
        if self.fullscreen_only and not self._covers_screen(rect):
            self._window = None
            self._missed_at = time.monotonic()
            return None
        image = window.get_image(0, 0, geom.width, geom.height, X.ZPixmap, 0xffffffff)
        frame = bgra_to_rgb(bytes(image.data), geom.width, geom.height)
        return frame, rect

    def _covers_screen(self, rect):
        screen = self._connect().screen().root.get_geometry()
        return covers_screen(rect, (screen.width, screen.height))

    def _alive(self):
        return self._window.get_attributes().map_state == X.IsViewable

    def _locate(self):
        """Largest mapped top level window whose title names the game."""
        conn = self._connect()
        best, best_area = None, 0
        for window in conn.screen().root.query_tree().children:
            try:
                if window.get_attributes().map_state != X.IsViewable:
                    continue
                title = self._title(window)
            except XError:
                continue
            if not title or not self.pattern.search(title):
                continue
            geom = window.get_geometry()
            area = geom.width * geom.height
            if area > best_area:
                best, best_area = window, area
        self._window = best
        return best

    def _title(self, window):
        conn = self._display
        try:
            prop = window.get_property(conn.intern_atom("_NET_WM_NAME"),
                                        conn.intern_atom("UTF8_STRING"), 0, 1024)
            if prop and prop.value:
                return bytes(prop.value).decode("utf-8", "replace").rstrip("\x00")
        except XError:
            pass
        try:
            return window.get_wm_name()
        except XError:
            return None

    def _origin(self, window):
        conn = self._display
        try:
            point = conn.screen().root.translate_coords(window, 0, 0)
            return int(point.x), int(point.y)
        except XError:
            geom = window.get_geometry()
            return int(geom.x), int(geom.y)
