"""Visible OS mouse input, corrected against KWin's actual cursor position."""
from __future__ import annotations

import math
import os
import shutil
import subprocess
import time

from config import MOUSE_TOLERANCE, SCROLL_NOTCHES, YDOTOOL_SOCKET
from metrics import METRICS


class MouseController:
    def __init__(self, desktop, guard=lambda: None):
        self.desktop = desktop
        self.guard = guard
        self.env = dict(os.environ, YDOTOOL_SOCKET=YDOTOOL_SOCKET)
        self._input_errors = 0
        if not shutil.which("ydotool") or not os.path.exists(YDOTOOL_SOCKET):
            raise RuntimeError(
                f"ydotool veya çalışan ydotoold soketi bulunamadı: {YDOTOOL_SOCKET}. "
                "Kontrol: systemctl --user status ydotool.service")

    def _run(self, *args):
        try:
            subprocess.run(["ydotool", *map(str, args)], env=self.env, check=True,
                           capture_output=True, timeout=2)
        except subprocess.CalledProcessError as exc:
            # A rejected command delivered no input. Retrying from a fresh
            # screenshot is safer than stopping the whole bot; a dead daemon
            # still fails loudly after consecutive errors.
            METRICS.bump('input_error')
            self._input_errors += 1
            if self._input_errors >= 10:
                raise RuntimeError(
                    f"ydotool komutları art arda başarısız ({self._input_errors}); "
                    f"ydotoold durumu: {YDOTOOL_SOCKET}") from exc
            raise InterruptedError('Fare komutu reddedildi; taze ekranla yeniden denenecek.') from exc
        METRICS.bump('input_calls')
        self._input_errors = 0

    def _check(self):
        self.guard()
        if not self.desktop.is_game_active():
            raise InterruptedError("Oyun penceresi odakta değil; fare durduruldu.")
        x, y = self.desktop.cursor()
        if x <= 2 and y <= 2:
            raise InterruptedError("İmleç sol üst köşede; acil duraklama.")

    def move_to(self, x, y):
        gx, gy, width, height = self.desktop.state["geometry"]
        if not (gx + 4 < x < gx + width - 4 and gy + 4 < y < gy + height - 4):
            raise ValueError("Fare hedefi ekran sınırları dışında.")
        with METRICS.span('move'):
            return self._move_to(x, y)

    def _move_to(self, x, y):
        # İlk adım kalan mesafenin TAMAMI: eskisi 85 px'lik adımlarla yürüyüp
        # buton yolculuğunu ~1.5 sn yapıyordu (kullanıcı: pat pat). İvme kazancı
        # ölçülüp sonraki adımlar ona göre düzeltilir; tıklama öncesi 2.5 px
        # tolerans kontrolü aynen korunur.
        gain = 1.0
        for _ in range(10):
            self._check()
            start = self.desktop.cursor()
            dx, dy = x - start[0], y - start[1]
            distance = math.hypot(dx, dy)
            if distance <= MOUSE_TOLERANCE:
                return
            factor = min(1.0 / gain, 1.0)
            mx, my = round(dx * factor), round(dy * factor)
            if mx == my == 0:
                if abs(dx) >= abs(dy):
                    mx = 1 if dx > 0 else -1
                else:
                    my = 1 if dy > 0 else -1
            self._run("mousemove", "-x", mx, "-y", my)
            # KWin imleç raporu genelde bu sürede gelir; rapor gecikirse kazanç
            # bir sonraki adımda öğrenilir, döngü yine de kısa sürer.
            time.sleep(0.01)
            end = self.desktop.cursor()
            actual = math.dist(start, end)
            commanded = math.hypot(mx, my)
            if actual and commanded:
                gain = min(4.0, max(0.4, actual / commanded))
        # A relative Wayland move can occasionally lose a state update while
        # KWin is busy.  Treat that as a transient safety interruption instead
        # of an uncaught bot error: the caller will take a fresh screenshot and
        # retry without sending a click to an uncertain position.
        METRICS.bump('move_failed')
        raise InterruptedError(f"İmleç hedefe ulaşamadı: hedef {(x, y)}, gerçek {self.desktop.cursor()}; tıklanmadı.")

    def click(self, x, y, before_click=None, target_tolerance=MOUSE_TOLERANCE):
        self.move_to(x, y)
        for attempt in range(3) if before_click else ():
            corrected = before_click()
            if corrected is not None:
                if not (isinstance(corrected, (tuple, list)) and len(corrected) == 2):
                    raise TypeError("before_click yalnızca (x, y) düzeltmesi veya None döndürebilir.")
                corrected = int(corrected[0]), int(corrected[1])
                # Ring animations move the detected centre by a few pixels.
                # The caller may accept a point still inside that ring. Keep
                # the separate, strict cursor check below for user movement.
                if math.dist((x,y),corrected)<=target_tolerance:break
                if attempt==2:
                    raise InterruptedError('Hedef hareket ediyor; yeni görüntüyle tekrar aranacak.')
                x, y = corrected
                self.move_to(x, y)
            else:break
        self._check()
        if math.dist(self.desktop.cursor(), (x, y)) > MOUSE_TOLERANCE:
            raise InterruptedError("İmleç kullanıcı tarafından taşındı; tıklanmadı.")
        self._run("click", "-D", 40, "0xC0")
        METRICS.bump('click')

    def scroll(self, x, y, direction, before_scroll=None):
        self.move_to(x, y)
        if before_scroll:
            before_scroll()
        self._check()
        if math.dist(self.desktop.cursor(), (x, y)) > MOUSE_TOLERANCE:
            raise InterruptedError("İmleç taşındı; kaydırma yapılmadı.")
        # Linux REL_WHEEL: positive is up, negative is down.
        self._run("mousemove", "-w", "-x", 0, "-y", -SCROLL_NOTCHES if direction == "down" else SCROLL_NOTCHES)
        METRICS.bump('scroll')
