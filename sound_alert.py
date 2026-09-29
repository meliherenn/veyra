"""A bounded, non-overlapping audible alarm that stops promptly."""
from __future__ import annotations

import math
import shutil
import struct
import subprocess
import threading
import wave

from config import ALARM_REPEAT_SECONDS, ROOT


class SoundAlert:
    def __init__(self):
        self.sound_file = ROOT / 'assets' / 'alarm.wav'
        self.sound_file.parent.mkdir(exist_ok=True)
        if not self.sound_file.exists():
            rate = 22050
            samples = []
            for i in range(int(rate*.75)):
                t = i/rate
                frequency = 880 if (int(t/.15) % 2) == 0 else 660
                envelope = min(1, t/.02, (.75-t)/.02)
                samples.append(struct.pack('<h', int(11000*envelope*math.sin(2*math.pi*frequency*t))))
            with wave.open(str(self.sound_file), 'wb') as wav:
                wav.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
                wav.writeframes(b''.join(samples))
        self.player_cmd = next((shutil.which(p) for p in ('paplay', 'pw-play', 'aplay') if shutil.which(p)), None)
        self.stop_event = threading.Event()
        self.thread = None
        self.process = None
        self._lock = threading.Lock()

    def play_once(self):
        if not self.player_cmd:
            print('\a[SES HATASI] paplay / pw-play / aplay bulunamadı.', flush=True)
            return False
        with self._lock:
            try:
                self.process = subprocess.Popen([self.player_cmd, str(self.sound_file)],
                                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return self.process.wait(timeout=3) == 0
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=1)
                return False
            except OSError:
                print('\a[SES HATASI] Alarm oynatılamadı.', flush=True)
                return False
            finally:
                self.process = None

    def start_alarm_loop(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()

        def loop():
            while not self.stop_event.is_set():
                if not self.play_once():
                    print('\a[SES HATASI] Ses çıkışını kontrol edin.', flush=True)
                self.stop_event.wait(ALARM_REPEAT_SECONDS)
        self.thread = threading.Thread(target=loop, name='dwar-alarm', daemon=True)
        self.thread.start()

    def stop_alarm_loop(self):
        self.stop_event.set()
        process = self.process
        if process and process.poll() is None:
            try:
                process.terminate()
            except ProcessLookupError:
                pass
        if self.thread:
            self.thread.join(timeout=1)
