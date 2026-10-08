"""DWAR named fishing: visible mouse, measured durations, manual challenge handoff."""
from __future__ import annotations

import argparse
from dataclasses import asdict
import fcntl
import json
import logging
from logging.handlers import RotatingFileHandler
import math
import os
from pathlib import Path
import queue
import shutil
import signal
import sys
import time

import cv2
import numpy as np
from PIL import Image

from config import (ROOT, POLL_INTERVAL, SELECT_TIMEOUT, HARVEST_START_TIMEOUT,
                    HARVEST_TIMEOUT, TARGET_RETRY_SECONDS, NO_FISH_ALERT_SECONDS,
                    MAX_REJECTIONS_PER_VIEW, TRANSIENT_BLOCK_FRAMES,
                    RESUME_FAST_SECONDS, REACQUIRE_ATTEMPTS,
                    REACQUIRE_RETRY_DELAY, AUTO_PANEL_PROBE_INTERVAL,
                    WARNING_CLOSE_INTERVAL, WARNING_CLOSE_LIMIT,
                    WARNING_CLOSE_WINDOW, LOG_MAX_BYTES, LOG_BACKUPS,
                    FOCUS_ALERT_AFTER_SECONDS, FOCUS_ALERT_REPEAT_SECONDS)
from screen_detector import ScreenDetector
from sound_alert import SoundAlert
from state import HarvestTracker, ResumeGate, StopRequested
from fish_catalog import BY_ID,CATALOG,COLORS,DEFAULT_IDS,resolve_name,resolve_name_for_colors,resolve_requested
from timing_store import TimingStore
from profession import ProfessionController
from metrics import METRICS

RUNTIME = ROOT / 'runtime'
LOG = logging.getLogger('dwar')


def bot_log_handler(path=None):
    """bot.log tek dosyada büyümesin; aşıldığında yedeğe kayar."""
    return RotatingFileHandler(path or RUNTIME / 'bot.log',
                               maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS)


def rotate_log(path, max_bytes=LOG_MAX_BYTES, backups=LOG_BACKUPS):
    """Bir günlük dosyasını eklemeden önce sınırla; yedek sayısını koru."""
    if backups < 1 or not path.exists():
        return False
    try:
        if path.stat().st_size < max_bytes:
            return False
    except OSError:
        return False
    oldest = path.with_name(f'{path.name}.{backups}')
    if oldest.exists():
        oldest.unlink()
    for index in range(backups - 1, 0, -1):
        source = path.with_name(f'{path.name}.{index}')
        if source.exists():
            source.replace(path.with_name(f'{path.name}.{index + 1}'))
    path.replace(path.with_name(f'{path.name}.1'))
    return True


class FishingBot:
    def __init__(self, desktop, detector, mouse, sound, args):
        self.desktop, self.detector, self.mouse, self.sound = desktop, detector, mouse, sound
        self.args = args
        self.selected_ids = tuple(getattr(args,'target_ids',DEFAULT_IDS))
        self.mastery = getattr(args,'mastery',None)
        self.selected_colors = tuple(getattr(args,'colors',None) or ())
        self.selection_mode = 'color' if self.selected_colors else 'name'
        self.timings = TimingStore(RUNTIME/'timings.json')
        self.pending_fish_id = None
        self.active_fish_id = None
        self.last_measurement = None
        self.rejections = 0
        self.selection_interruptions = 0
        self.current_name = ''
        self.current_color = None
        self.phase = 'SEARCH'
        self.manual_pause = False
        self.stopping = False
        self.gate = ResumeGate()
        self.tracker = HarvestTracker()
        self.target = None
        self.target_origin = None
        self.avoid = []
        self.since = time.monotonic()
        self.attempts = self.cycles = self.scrolls = self.failures = 0
        self.empty_frames = 0
        self.blocked_frames = 0
        self.warning_close_at = 0.0
        self.warning_closes = []
        self.scroll_direction = 'down'
        self.scroll_before = None
        self.last_scroll = 0
        self.sea_skip_notice = False
        self.focus_lost_since = None
        self.next_focus_alert = FOCUS_ALERT_AFTER_SECONDS
        self.last_fish = time.monotonic()
        self.last_notice = ''
        self.last_notice_time = 0
        self.mouse.guard = self.control_guard
        self.profession = ProfessionController(self, RUNTIME)

    def notice(self, text):
        if text != self.last_notice or time.monotonic()-self.last_notice_time > 30:
            LOG.info(text)
            self.last_notice, self.last_notice_time = text, time.monotonic()

    def control_guard(self):
        while True:
            try:
                command = self.desktop.commands.get_nowait()
            except queue.Empty:
                break
            if command == 'stop':
                self.stopping = True
            elif command in ('pause', 'toggle'):
                self.manual_pause = not self.manual_pause if command == 'toggle' else True
                self.phase = 'SEARCH'
                self.gate.block()
                self.tracker = HarvestTracker()
                self.active_fish_id = self.pending_fish_id = None
                self.sound.stop_alarm_loop()
            elif command == 'resume':
                self.manual_pause = False
                self.gate.block()
                self.phase = 'SEARCH'
                self.tracker = HarvestTracker()
                self.active_fish_id = self.pending_fish_id = None
                self.sound.stop_alarm_loop()
        if self.stopping:
            raise StopRequested()
        if self.manual_pause:
            raise InterruptedError('Elle duraklatıldı. Devam: F8. Durdur: F9.')

    def capture_rect(self):
        """Screen region the last captured frame covers, in desktop coordinates."""
        # Read from __dict__ so a mocked detector (which answers any attribute)
        # still behaves like the screenshot path: the whole screen.
        rect = getattr(self.detector, '__dict__', {}).get('capture_rect')
        return self.desktop.state['geometry'] if rect is None else rect

    def desktop_scale(self, frame):
        """Desktop pixels per frame pixel."""
        return self.capture_rect()[2] / frame.shape[1]

    def pixel_to_desktop(self, point, frame):
        x, y, width, height = self.capture_rect()
        if self.desktop.state['screens'] != 1:
            raise RuntimeError('Bu sürüm tek ekranla çalışır; çoklu ekranda tıklama yapılmadı.')
        return (round(x+point[0]*width/frame.shape[1]), round(y+point[1]*height/frame.shape[0]))

    def block(self, reason, frame=None, alarm=True, seconds=None):
        new = not self.gate.latched
        self.gate.block(seconds)
        self.notice(reason)
        if alarm:
            self.sound.start_alarm_loop()
        if not new:
            # Already latched: keep the existing invalid state instead of
            # discarding a harvest measurement again on every following frame.
            return
        METRICS.bump('block')
        self.phase = 'SEARCH'
        self.tracker = HarvestTracker()
        self.active_fish_id = self.pending_fish_id = None
        if frame is not None:
            # Local diagnostic only, never uploaded. Overwrites one bounded file.
            Image.fromarray(frame).save(RUNTIME / 'last-pause.png')

    def dismiss_warning(self, frame, obs):
        """Engelleyen oyun uyarısının kapat düğmesine bas.

        True: bu kare ele alındı (tıklama yapıldı ya da pes edilip block).
        False: henüz deneme sırası değil; ekran gözlemine normal yoldan devam.
        """
        now = time.monotonic()
        self.warning_closes = [t for t in self.warning_closes if now - t < WARNING_CLOSE_WINDOW]
        if len(self.warning_closes) >= WARNING_CLOSE_LIMIT:
            # Ekran hiç temizlenmiyor: kapatmaya devam etmek sorunu gizler.
            self.warning_closes.clear()
            self.block('Oyun uyarısı kapatılamadı; ekranı kontrol edip F8 ile devam edin.', frame)
            return True
        if self.args.dry_run or now - self.warning_close_at < WARNING_CLOSE_INTERVAL:
            return False

        def guard():
            self.control_guard()
            if not self.desktop.is_game_active():
                raise InterruptedError('Oyun odakta değil; uyarı bekliyor.')
            fresh = self.detector.capture()
            protected, reason = self.detector.check_bot_protection(fresh)
            if protected:
                self.block(reason or 'Bot koruması.', fresh)
                raise InterruptedError('Bot koruması; uyarı kapatılmadı.')
            # Modal kaymış ya da çoktan kapanmış olabilir: girdi ancak
            # düğme aynı karede hâlâ yerindeyse gönderilir.
            current = self.detector.find_close_button(fresh, obs.layout)
            if current is None:
                raise InterruptedError('Uyarı penceresi son kontrolde görünmedi; yeniden okunacak.')
            return self.pixel_to_desktop(current, fresh)

        self.warning_close_at = now
        self.mouse.click(*self.pixel_to_desktop(obs.close_button, frame), before_click=guard)
        self.warning_closes.append(now)
        METRICS.bump('warning_close')
        self.notice('Oyun uyarısı kapatılıyor; arama sürecek.')
        return True

    @staticmethod
    def layout_same(a, b):
        return a is not None and b is not None and all(
            abs(x-y) <= 5 for x, y in zip(asdict(a).values(), asdict(b).values())
        )

    def fresh_guard(self, expected_layout, target=None, action=None):
        """Revalidate the visible game immediately before an OS input.

        For a fish click, return a corrected desktop coordinate if the same
        coloured fish moved slightly while the cursor was travelling.
        """
        self.control_guard()
        if not self.desktop.is_game_active():
            raise InterruptedError('Oyun odaktan çıktı; işlem iptal edildi.')
        frame = self.detector.capture()
        # Normal polling rate-limits the profession-panel probe; an input must
        # always re-check it against the very frame it is about to click on.
        self.detector.auto_panel_probe(frame, force=True)
        obs = self.detector.observe(frame)

        def revalidate():
            if not obs.clear:
                if obs.protection or obs.blocked:
                    self.block(obs.blocked or 'Bot koruması.', frame)
                METRICS.bump('guard_not_clear')
                raise InterruptedError('Ekran değişti; işlem iptal edildi.')
            if not self.layout_same(obs.layout, expected_layout):
                METRICS.bump('guard_layout_changed')
                raise InterruptedError('Harita yeri değişti; yeniden taranacak.')

        revalidate()
        corrected = None
        if target:
            fresh = None
            for attempt in range(REACQUIRE_ATTEMPTS):
                if attempt:
                    # The cursor travelled while the ring animated. One fresh
                    # frame is far cheaper than throwing the click away.
                    METRICS.bump('reacquire_retry')
                    time.sleep(REACQUIRE_RETRY_DELAY)
                    frame = self.detector.capture()
                    obs = self.detector.observe(frame)
                    revalidate()
                fresh = self.detector.reacquire_fish(frame, obs.layout, self.target or target)
                if fresh is not None:
                    break
            if fresh is None:
                METRICS.bump('reacquire_fail')
                raise InterruptedError('Balık son kontrolde yeniden bulunamadı; kara listeye alınmadan yeniden taranacak.')
            self.target = fresh
            corrected = self.pixel_to_desktop((fresh.x, fresh.y), frame)
        if action:
            button = self.detector.find_yakala_button(frame, obs.layout)
            name = self.detector.selected_fish_name(frame, obs.layout)
            fish = self.allowed_fish(name,self.detector.selected_fish_color(frame,obs.layout))
            if not button or math.dist(button, action) > 5 or fish is None or fish.id != self.pending_fish_id:
                METRICS.bump('guard_action_mismatch')
                raise InterruptedError('Seçilen balık adı / Yakala eylemi yeniden doğrulanamadı.')
        self.control_guard()
        return corrected

    def allowed_fish(self,name,observed_color=None):
        if self.selection_mode=='color':
            fish=resolve_name_for_colors(name,self.selected_colors)
            # Species whose catalog color is not yet known may still be accepted
            # when the currently visible selection color is explicitly chosen.
            if fish is None:
                strict=resolve_name(name)
                if strict is not None and strict.color is None and observed_color in self.selected_colors:
                    fish=strict
            if fish is None:return None
            if self.mastery is not None and fish.mastery>self.mastery:return None
            return fish
        fish=resolve_name(name)
        if fish is None:return None
        if self.mastery is not None and fish.mastery>self.mastery:return None
        return fish if fish.id in self.selected_ids else None

    def find_targets(self,frame,layout):
        colors=self.selected_colors
        if not colors:
            known={BY_ID[fish_id].color for fish_id in self.selected_ids}
            if None not in known:
                colors=tuple(known)
        color=colors[0] if len(colors)==1 else 'all'
        targets=self.detector.find_fish_ripples(frame,layout,target_color=color)
        return [f for f in targets if not colors or f.color in colors]

    def reset_target(self, now, blacklist=True):
        if blacklist:
            # Tıklama koruması hedefi reacquire ile başka bir halkaya
            # kaydırabilir: oyun oraya basar ama aday listesindeki ilk halka
            # hâlâ görünür kalır ve hemen yeniden seçilir. İkisi de elensin.
            points = [p for p in ((self.target.x, self.target.y) if self.target else None,
                                  self.target_origin) if p]
            for x, y in points:
                if not any(math.hypot(x-a, y-b) < 24 for a, b, _t in self.avoid):
                    self.avoid.append((x, y, now))
        self.target = None
        self.target_origin = None
        self.pending_fish_id = None
        self.phase = 'SEARCH'
        self.empty_frames = 0
        self.selection_interruptions = 0

    def handle_interruption(self, error):
        METRICS.bump('interrupted')
        self.notice(str(error))
        # No new mouse input was sent. A failed screenshot/OCR read must not
        # discard an already selected fish or a collection being tracked.
        # Focus, protection and pause paths invalidate their own state.
        if self.phase == 'SELECTING':
            self.selection_interruptions += 1
            if self.selection_interruptions >= 3:
                self.notice('Seçim üç okumada doğrulanamadı; hedef yeniden aranacak.')
                self.reset_target(time.monotonic(), blacklist=False)

    @staticmethod
    def map_signature(frame, layout):
        return cv2.resize(cv2.cvtColor(layout.crop(frame), cv2.COLOR_RGB2GRAY), (160, 60)).astype(float)

    def tick(self):
        try:
            self.control_guard()
        except InterruptedError as e:
            self.notice(str(e))
            return
        if not self.desktop.is_game_active():
            # Güvenlik gereği odak yokken tıklanmaz; kullanıcı uzaktayken
            # durumu fark edebilsin diye 10 dakikada bir alarm verilir.
            METRICS.bump('focus_wait')
            self.blocked_frames = 0
            state = self.desktop.state
            suffix = f' (aktif: {str(state.get("app", ""))[:24]} / {str(state.get("title", ""))[:40]})'
            now = time.monotonic()
            if self.focus_lost_since is None:
                self.focus_lost_since = now
                self.next_focus_alert = now + FOCUS_ALERT_AFTER_SECONDS
            elif now >= self.next_focus_alert:
                self.sound.play_once()
                self.next_focus_alert = now + FOCUS_ALERT_REPEAT_SECONDS
                self.notice(f'Oyun {int((now - self.focus_lost_since) / 60)} dakikadır '
                            'önede değil; alarm verildi.')
            self.block('Oyun önde değil; fare bekliyor. Oyuna dönünce devam edecek.' + suffix,
                       alarm=False)
            return
        self.focus_lost_since = None
        self.next_focus_alert = time.monotonic() + FOCUS_ALERT_AFTER_SECONDS
        frame = self.detector.capture()
        frame_time = time.monotonic()
        obs = self.detector.observe(frame)
        now = time.monotonic()
        if obs.blocked:
            self.blocked_frames += 1
        else:
            self.blocked_frames = 0
        if obs.protection:
            self.block(obs.blocked or 'Bot koruması; doğrulamayı siz tamamlayın.', frame)
            return
        if self.profession.handle(frame, obs, now):
            return
        if obs.blocked:
            METRICS.bump('frames_blocked')
            if obs.close_button:
                if self.dismiss_warning(frame, obs):
                    return
                # Daha önceki kapatma denemesinin sonucu bekleniyor: düğme
                # hâlâ ordaysa ikinci bir tıklama gidecek, block değil.
                if time.monotonic() - self.warning_close_at < WARNING_CLOSE_INTERVAL:
                    METRICS.bump('warning_wait')
                    return
            transient = 'haritası görünmüyor' in (obs.blocked or '')
            if transient:
                METRICS.bump('frames_layout_lost')
            if self.blocked_frames < TRANSIENT_BLOCK_FRAMES:
                # A single misread must not discard an in-progress harvest.
                METRICS.bump('frames_transient')
                return
            self.block(obs.blocked, frame,
                       seconds=RESUME_FAST_SECONDS if transient else None)
            return
        latched = self.gate.latched
        if not self.gate.update(obs.clear or obs.harvesting, now):
            METRICS.bump('frames_screen_wait')
            self.notice('Oyun ekranı geri geldi; kararlı görüntü bekleniyor.')
            return
        if latched:
            self.sound.stop_alarm_loop()
            self.notice('Ekran doğrulandı; devam ediliyor.')
        if obs.harvesting:
            if self.tracker.started_at is None:
                self.active_fish_id = self.pending_fish_id
                label=BY_ID[self.active_fish_id].name if self.active_fish_id else 'Mevcut toplama'
                estimate=self.timings.estimate(self.active_fish_id)
                self.notice(f'{label}: toplama başladı. '+
                            (f'Beklenen süre {estimate:.1f} sn; ekran izleniyor.' if estimate else 'İlk süre ölçülüyor.'))
            self.phase = 'HARVESTING'
            self.tracker.update(True, False, frame_time)
            if now-self.tracker.started_at > HARVEST_TIMEOUT:
                METRICS.bump('harvest_timeout')
                self.manual_pause = True
                self.block('Toplama zaman aşımı. Ekranı kontrol edip F8 ile devam edin.', frame)
            return
        if self.phase == 'HARVESTING':
            if self.tracker.update(False, obs.clear, frame_time):
                self.cycles += 1
                METRICS.bump('cycle_done')
                if self.active_fish_id:
                    self.profession.manual_completed()
                self.failures = 0
                self.rejections = 0
                duration=self.tracker.measured_seconds
                if self.active_fish_id and duration is not None and self.tracker.uncertainty <= 2:
                    self.timings.record(self.active_fish_id,duration,self.tracker.uncertainty,self.current_color)
                    self.last_measurement={'fish_id':self.active_fish_id,'seconds':round(duration,2)}
                    self.notice(f'{BY_ID[self.active_fish_id].name}: {duration:.2f} sn ölçüldü. Döngü: {self.cycles}.')
                else:
                    self.notice(f'Toplama penceresi kapandı. Tamamlanan döngü: {self.cycles}.')
                self.tracker = HarvestTracker()
                self.active_fish_id = None
                self.reset_target(now)
            return
        if self.phase == 'WAIT_START':
            if now-self.since > HARVEST_START_TIMEOUT:
                METRICS.bump('harvest_start_timeout')
                self.failures += 1
                self.notice('Toplama başlamadı; bu hedef atlanıyor.')
                self.reset_target(now)
                if self.failures >= 3:
                    # Open the inventory once to re-check the tool. An unknown
                    # failure alone never authorizes consuming a potion.
                    if self.profession.recovery_enabled and not self.profession.retry_recovery:
                        self.profession.retry_recovery = True
                        self.profession.request_recovery('tool')
                        return
                    self.manual_pause = True
                    self.block('Üç denemede toplama başlamadı. Ekranı kontrol edip F8 ile devam edin.', frame)
            return
        if self.phase == 'SELECTING':
            button = self.detector.find_yakala_button(frame, obs.layout)
            if button:
                name = self.detector.selected_fish_name(frame, obs.layout)
                self.current_name = name
                self.current_color = self.detector.selected_fish_color(frame,obs.layout)
                fish = self.allowed_fish(name,self.current_color)
                if fish:
                    self.current_name=fish.name
                    self.current_color=fish.color or self.current_color
                    self.pending_fish_id = fish.id
                    self.mouse.click(*self.pixel_to_desktop(button, frame),
                                     before_click=lambda: self.fresh_guard(obs.layout, action=button))
                    self.attempts += 1
                    self.phase, self.since = 'WAIT_START', time.monotonic()
                    self.notice(f'{fish.name} doğrulandı; toplama başlatılıyor ({self.attempts}).')
                    return
                recognized=resolve_name(name) if name else None
                if recognized and now-self.since > 1:
                    reason=(f'{recognized.mastery} ustalık gerekiyor; sınırınız {self.mastery}.'
                            if recognized and self.mastery is not None and recognized.mastery>self.mastery
                            else 'Seçtiğiniz türler aranıyor.')
                    self.notice(f'Bu hedef atlandı: {recognized.name if recognized else name[:70]}. {reason}')
                    self.rejections += 1
                    self.reset_target(now)
                    return
            if now-self.since > SELECT_TIMEOUT:
                METRICS.bump('select_timeout')
                self.notice('Balık seçimi doğrulanamadı; yeni hedef aranıyor.')
                self.rejections += 1
                self.reset_target(now)
            return
        if self.scroll_before is not None:
            current = self.map_signature(frame, obs.layout)
            change = float(np.mean(abs(current-self.scroll_before)))
            if change < 5:
                self.scroll_direction = 'up' if self.scroll_direction == 'down' else 'down'
                self.notice('Kaydırma sınırına ulaşıldı; arama yönü değişti.')
            else:
                self.notice('Harita kaydı; balıkların yeni konumları taranıyor.')
            self.avoid.clear()
            self.scroll_before = None
            self.rejections = 0
        fishes = self.find_targets(frame, obs.layout)
        self.avoid = [(x,y,t) for x,y,t in self.avoid if now-t < TARGET_RETRY_SECONDS]
        candidates = [f for f in fishes if not any(math.hypot(f.x-x,f.y-y) < 24 for x,y,t in self.avoid)]
        if self.rejections >= MAX_REJECTIONS_PER_VIEW and not self.args.no_scroll:
            candidates = []
            self.empty_frames = max(self.empty_frames,2)
        if self.args.dry_run:
            self.notice(f'Önizleme: {len(fishes)} balık halkası. Fare kullanılmıyor.')
            return
        if candidates:
            self.target = candidates[0]
            target = self.target
            # Reacquire bu halkayı kaydırabilir; kara liste ilk halkayı da
            # kapsasın diye seçilen aday ayrıca saklanır.
            self.target_origin = (target.x, target.y)
            self.mouse.click(*self.pixel_to_desktop((target.x,target.y),frame),
                             before_click=lambda: self.fresh_guard(obs.layout, target=target),
                             target_tolerance=max(4, min(9, target.radius*.5))*
                             self.desktop_scale(frame))
            self.selection_interruptions = 0
            self.phase, self.since = 'SELECTING', time.monotonic()
            self.last_fish = now
            self.empty_frames = 0
            self.sea_skip_notice = False
            self.notice(f'Halka seçildi: ({target.x}, {target.y}). Balık adı okunuyor.')
            return
        self.empty_frames += 1
        if not self.args.no_scroll and self.empty_frames >= 3 and now-self.last_scroll >= 2:
            layout = obs.layout
            if not self.detector.sea_extends_vertically(frame, layout):
                if not self.sea_skip_notice:
                    self.sea_skip_notice = True
                    self.notice('Deniz yalnızca genişliğe uzanıyor; dikey kaydırma '
                                'boşuna, görünür alan taranmaya devam ediyor.')
            else:
                p = (layout.right-50, (layout.top+layout.bottom)//2)
                self.mouse.scroll(*self.pixel_to_desktop(p,frame), self.scroll_direction,
                                  before_scroll=lambda: self.fresh_guard(layout))
                self.scroll_before = self.map_signature(frame,layout)
                self.last_scroll = time.monotonic()
                self.scrolls += 1
                self.empty_frames = 0
                self.notice(f'Yeni balık aranıyor; harita {"aşağı" if self.scroll_direction == "down" else "yukarı"} kaydırıldı.')
        if now-self.last_fish > NO_FISH_ALERT_SECONDS:
            self.sound.play_once()
            self.notice('Arama sürüyor; seçtiğiniz türlerden henüz balık bulunamadı.')
            self.last_fish = now

    def status_data(self, running=True):
        return dict(pid=os.getpid(), running=running, phase=self.phase,
                    paused=self.manual_pause, protection_or_screen_wait=self.gate.latched,
                    attempts=self.attempts, completed_cycles=self.cycles, scrolls=self.scrolls,
                    message=self.last_notice, updated_at=time.strftime('%Y-%m-%d %H:%M:%S'),
                    target_ids=self.selected_ids,current_name=self.current_name,mastery=self.mastery,
                    selection_mode=self.selection_mode,colors=self.selected_colors,
                    active_fish_id=self.active_fish_id,last_measurement=self.last_measurement,
                    elapsed_seconds=round(time.monotonic()-self.tracker.started_at,1) if self.tracker.started_at else None,
                    expected_seconds=self.timings.estimate(self.active_fish_id),
                    energy=self.profession.energy.snapshot(),
                    profession_phase=self.profession.state,
                    energy_cycle=self.profession.energy_enabled,
                    auto_fish_id=self.profession.auto_fish_id,
                    auto_cycles=self.profession.auto_cycles,
                    auto_progress=self.profession.auto_progress,
                    auto_total=self.profession.auto_total,
                    splinter_recoveries=self.profession.recoveries)

    def status(self, running=True):
        data = self.status_data(running)
        path = RUNTIME / 'status.tmp'
        path.write_text(json.dumps(data,ensure_ascii=False,indent=2))
        path.replace(RUNTIME / 'status.json')


def read_status():
    path = RUNTIME / 'status.json'
    if not path.exists():
        return {'running':False}
    try:
        data = json.loads(path.read_text())
    except (ValueError,OSError):
        return {'running':False}
    pid = data.get('pid')
    try:
        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
        alive = os.fsencode(str(ROOT/'main.py')) in cmdline
    except OSError:
        alive = False
    data['process_alive'] = bool(alive)
    data['running'] = bool(alive and data.get('running'))
    return data


def remote_command(command):
    data=read_status()
    if command == 'status':
        print(json.dumps(data,ensure_ascii=False,indent=2))
        return 0
    if not data['running']:
        print('Bot çalışmıyor.')
        return 1
    os.kill(data['pid'], {'stop':signal.SIGTERM, 'pause':signal.SIGUSR1, 'resume':signal.SIGUSR2}[command])
    print(f'Komut gönderildi: {command}')
    return 0


def parse_args(argv=None):
    p = argparse.ArgumentParser(description='Renk veya balık adına göre toplama. F8: duraklat/devam; F9: durdur.')
    p.add_argument('color', nargs='?', choices=['yesil','yeşil','1'], default=None)
    selection=p.add_mutually_exclusive_group()
    selection.add_argument('--fish',nargs='+',help='Bir veya birden fazla balık adı ya da kimliği')
    selection.add_argument('--colors',nargs='+',choices=list(COLORS),help='Bir veya birden fazla halka rengi')
    p.add_argument('--list-fish',action='store_true',help='İsimle seçilebilen balıkları listele')
    p.add_argument('--hunt',action='store_true',help='Balık yerine Avlan yaratık avı modunu çalıştır')
    p.add_argument('--creatures',nargs='+',help='Avlanacak yaratık adları ya da "all" (varsayılan: bilinen yaratıklar)')
    p.add_argument('--min-level',type=int,help='Bu seviyenin altındaki yaratıklara saldırma')
    p.add_argument('--max-level',type=int,help='Bu seviyenin üstündeki yaratıklara saldırma')
    p.add_argument('--list-creatures',action='store_true',help='Bilinen yaratıkları listele')
    p.add_argument('--auto-battle',action='store_true',help='Dövüş başlayınca otomatik savaş düğmesine bas')
    p.add_argument('--mount',action='store_true',help='Dövüş başlayınca binek çağır')
    p.add_argument('--provoke',action='store_true',help='Dövüş başlayınca provokasyonla yaratık çağır')
    p.add_argument('--provoke-counts',default='',help='Slot başına çağırma adedi, soldan sağa: "3,2" gibi')
    p.add_argument('--gui',action='store_true',help='Balık seçimi ve kontrol penceresini aç')
    p.add_argument('--dry-run', action='store_true', help='Sadece ekranı incele; fareyi kullanma')
    p.add_argument('--no-scroll', action='store_true', help='Haritada otomatik kaydırmayı kapat')
    p.add_argument('--no-focus', action='store_true', help='Başlangıçta oyun penceresini öne getirme')
    p.add_argument('--max-cycles', type=int, default=0, help='Bu kadar toplama döngüsünden sonra dur; 0=sınırsız')
    p.add_argument('--mastery',type=int,help='Meslek ustalığınız; daha yüksek ustalık isteyen balıkları atla')
    p.add_argument('--energy-cycle', action='store_true', help='Enerji dolunca meslek menüsünden otomatik topla')
    p.add_argument('--auto-fish', default='elmas_som', help='Enerjiyle otomatik toplanacak balık; normal --fish seçiminden bağımsız')
    p.add_argument('--auto-splinter', action='store_true', default=True,
                   help='Kıymıkta Orman Kalbi İksiri kullan, oltayı yeniden tak (varsayılan açık)')
    p.add_argument('--no-auto-splinter', action='store_false', dest='auto_splinter',
                   help='Kıymık/olta kurtarmasını kapat')
    p.add_argument('--max-seconds', type=float, default=0, help='Bu süreden sonra dur; 0=sınırsız')
    p.add_argument('--inspect', type=Path, help='Bir görüntüyü çevrimdışı analiz et')
    p.add_argument('--output', type=Path, help='İşaretli önizlemeyi PNG olarak kaydet')
    p.add_argument('--test-alarm', action='store_true')
    p.add_argument('--doctor', action='store_true', help='Yerel bağımlılıkları kontrol et')
    group = p.add_mutually_exclusive_group()
    for name in ('stop','pause','resume','status'):
        group.add_argument('--'+name, action='store_true')
    args = p.parse_args(argv)
    if not args.fish and not args.colors:
        args.colors=['yesil']
    if args.max_cycles < 0 or args.max_seconds < 0:
        p.error('Sınırlar negatif olamaz.')
    if args.mastery is not None and args.mastery<0:
        p.error('Ustalık negatif olamaz.')
    if (args.min_level is not None and args.min_level<0) or (args.max_level is not None and args.max_level<0):
        p.error('Seviye sınırı negatif olamaz.')
    if args.min_level is not None and args.max_level is not None and args.min_level>args.max_level:
        p.error('--min-level, --max-level değerinden büyük olamaz.')
    try:
        args.provoke_counts = [int(part) for part in args.provoke_counts.split(',') if part.strip()]
    except ValueError:
        p.error('--provoke-counts virgülle ayrılmış sayılar olmalı: "3,2" gibi.')
    if any(n < 0 or n > 99 for n in args.provoke_counts):
        p.error('--provoke-counts adetleri 0-99 arasında olmalı.')
    if args.provoke_counts and not args.provoke:
        p.error('--provoke-counts için --provoke gerekiyor.')
    if len(args.provoke_counts) > 5:
        p.error('En fazla 5 çağırma slotu vardır.')
    try:
        args.target_ids=resolve_requested(args.fish or DEFAULT_IDS)
        automatic = resolve_requested([args.auto_fish])
        if len(automatic) != 1:
            raise ValueError('Otomatik toplama için tek bir balık seçin.')
        args.auto_fish_id = automatic[0]
        if args.energy_cycle and args.mastery is not None and BY_ID[args.auto_fish_id].mastery > args.mastery:
            raise ValueError('Otomatik toplama hedefinin ustalığı belirttiğiniz sınırdan yüksek.')
    except ValueError as e:
        p.error(str(e))
    return args


def main(argv=None):
    effective_argv = sys.argv[1:] if argv is None else argv
    if not effective_argv or '--gui' in effective_argv:
        from gui import run_gui
        return run_gui()
    args = parse_args(argv)
    if args.list_fish:
        for fish in CATALOG:
            print(f'{fish.mastery:3}  {fish.name:<30} {fish.id}')
        return 0
    if args.list_creatures:
        from hunt_catalog import KNOWN
        for species in KNOWN:
            print(f'{species.name:<24} {species.id}')
        return 0
    for command in ('stop','pause','resume','status'):
        if getattr(args,command):
            return remote_command(command)
    if args.doctor:
        import importlib.util
        import subprocess
        failures = []
        for package in ('cv2','numpy','PIL','dbus','gi','PySide6'):
            ok = importlib.util.find_spec(package) is not None
            print(f'{package}: {"OK" if ok else "EKSİK"}')
            if not ok: failures.append(package)
        # Optional: without it every frame costs a ~0.4 s screenshot.
        fast = importlib.util.find_spec('Xlib') is not None
        print(f"Xlib (hızlı ekran yakalama): {'OK' if fast else 'yok - spectacle ile devam'}")
        for executable in ('spectacle','tesseract','ydotool'):
            ok = shutil.which(executable)
            print(f'{executable}: {ok or "EKSİK"}')
            if not ok: failures.append(executable)
        from config import YDOTOOL_SOCKET
        socket_ok = os.path.exists(YDOTOOL_SOCKET)
        print(f'ydotoold soketi: {"OK" if socket_ok else "EKSİK"}')
        if not socket_ok: failures.append('ydotoold')
        try:
            unit = subprocess.run(['systemctl', '--user', 'is-active', 'ydotool.service'],
                                  capture_output=True, text=True, timeout=3).stdout.strip()
        except Exception:
            unit = ''
        unit = unit or 'bilinmiyor'
        print(f'ydotool.service: {"OK" if unit == "active" else unit}')
        if unit not in ('active', 'bilinmiyor'):
            failures.append('ydotool.service')
        return bool(failures)
    if args.test_alarm:
        ok = SoundAlert().play_once()
        print('Alarm sesi oynatıcıya gönderildi.' if ok else 'Alarm oynatılamadı.')
        return not ok
    detector = ScreenDetector()
    # The profession panel only ever opens for the automatic energy cycle. With
    # it off, a rare probe is enough to notice one opened by hand, and every
    # input still forces a fresh check before it is issued.
    if not getattr(args, 'energy_cycle', False):
        detector.auto_panel_interval = AUTO_PANEL_PROBE_INTERVAL
    if args.inspect:
        try:
            frame = np.array(Image.open(args.inspect).convert('RGB'))
            if args.hunt:
                from hunt import inspect_image
                print(json.dumps(inspect_image(detector,frame,args.output),ensure_ascii=False,indent=2))
                return 0
            obs = detector.observe(frame)
            fishes = detector.find_fish_ripples(frame,obs.layout) if obs.clear else []
            print(json.dumps(dict(observation=asdict(obs),fish=[asdict(f) for f in fishes]),ensure_ascii=False,indent=2))
            if args.output:
                for i,f in enumerate(fishes,1):
                    cv2.circle(frame,(f.x,f.y),f.radius+4,(255,70,70),2)
                    cv2.putText(frame,str(i),(f.x+10,f.y-10),cv2.FONT_HERSHEY_SIMPLEX,.55,(255,255,255),1)
                args.output.parent.mkdir(parents=True,exist_ok=True)
                Image.fromarray(frame).save(args.output)
            return 0
        finally:
            detector.close()
    RUNTIME.mkdir(mode=0o700, exist_ok=True)
    lock = (RUNTIME/'bot.lock').open('w')
    try:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        print('Bot zaten çalışıyor. Durum: ./run.sh --status')
        detector.close()
        lock.close()
        return 1
    logging.basicConfig(level=logging.INFO,format='%(asctime)s %(message)s',datefmt='%H:%M:%S',
                        handlers=[logging.StreamHandler(),bot_log_handler()])
    from desktop import Desktop
    from mouse_control import MouseController
    sound = SoundAlert()
    bot = None
    try:
        with Desktop() as desktop:
            if not args.no_focus and not args.dry_run:
                desktop.focus_game()
            mouse = MouseController(desktop)
            if args.hunt:
                from hunt import HuntBot
                bot = HuntBot(desktop,detector,mouse,sound,args)
            else:
                bot = FishingBot(desktop,detector,mouse,sound,args)
            for sig,command in ((signal.SIGTERM,'stop'),(signal.SIGINT,'stop'),
                                (signal.SIGUSR1,'pause'),(signal.SIGUSR2,'resume')):
                signal.signal(sig,lambda signum,frame,c=command: desktop.commands.put(c))
            if args.hunt:
                fight_options='+'.join(label for flag,label in (
                    (args.provoke,'provokasyon'),(args.mount,'binek'),(args.auto_battle,'oto-savaş')) if flag)
                LOG.info('Yaratık avı: %s | seviye %s-%s | dövüş: %s | F8: duraklat/devam | F9: durdur | kaydırma: %s',
                         'tümü' if bot.allow_all else ', '.join(s.name for s in bot.species),
                         bot.min_level if bot.min_level is not None else '*',
                         bot.max_level if bot.max_level is not None else '*',
                         fight_options or 'yok',not args.no_scroll)
            else:
                LOG.info('Hedefler: %s | F8: duraklat/devam | F9: durdur | kaydırma: %s',
                         ', '.join(COLORS[i] for i in bot.selected_colors) if bot.selected_colors else
                         ', '.join(BY_ID[i].name for i in bot.selected_ids),not args.no_scroll)
            bot.status()
            start = time.monotonic()
            while True:
                if args.max_seconds and time.monotonic()-start >= args.max_seconds:
                    bot.profession.stop_automatic()
                    break
                if args.max_cycles and bot.cycles >= args.max_cycles:
                    bot.profession.stop_automatic()
                    break
                try:
                    METRICS.bump('tick')
                    with METRICS.span('tick'):
                        bot.tick()
                except StopRequested:
                    bot.profession.stop_automatic()
                    raise
                except InterruptedError as e:
                    bot.handle_interruption(e)
                bot.status()
                METRICS.save(RUNTIME/'metrics.json', min_interval=5.0)
                time.sleep(POLL_INTERVAL)
    except StopRequested:
        LOG.info('Durdurma komutu alındı.')
    except KeyboardInterrupt:
        LOG.info('Kullanıcı durdurdu.')
    except Exception as exc:
        if bot is not None and bot.stopping:
            # Ctrl+C terminalin sinyalini alt süreçlere de verir; durdurma
            # kuyruktayken gelen başka bir kesinti hata süsü vermemeli.
            LOG.info('Durdurma sırasında beklenmeyen kesinti (%s); fare işlemleri sona erdi.',
                     type(exc).__name__)
        else:
            LOG.exception('Bot hata nedeniyle durdu. Fare işlemleri sona erdi.')
            sound.play_once()
            return 1
    finally:
        sound.stop_alarm_loop()
        METRICS.save(RUNTIME/'metrics.json', force=True)
        if bot:
            bot.status(running=False)
            LOG.info('Bitti. %s denemesi: %d | tamamlanan döngü: %d | kaydırma: %d',
                     'Saldırı' if args.hunt else 'Toplama',bot.attempts,bot.cycles,bot.scrolls)
        detector.close()
        lock.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
