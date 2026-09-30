"""Yaratık avı (Avlan): yaratığı seç -> saldır -> sonuç ekranından haritaya dön.

Balıkçılıkla aynı güvenlik katmanını kullanır: görünür fare, her girdiden önce
taze ekranla doğrulama, F8/F9, odak kontrolü, uyarı kapatma ve Bot Koruması
çıktığında durup kullanıcıyı bekleme. Koruma ekranı asla aşılmaz.
"""
from __future__ import annotations

from dataclasses import replace
import math
import time

import cv2
import numpy as np

from config import (POLL_INTERVAL, SELECT_TIMEOUT, TARGET_RETRY_SECONDS, NO_FISH_ALERT_SECONDS,
                    TRANSIENT_BLOCK_FRAMES, RESUME_FAST_SECONDS, WARNING_CLOSE_INTERVAL,
                    HUNT_SPRITE_DY, HUNT_CLICK_DY_FALLBACKS, HUNT_ENGAGE_TIMEOUT,
                    HUNT_FIGHT_TIMEOUT, HUNT_RETURN_RETRY, HUNT_RETURN_CLICK_LIMIT,
                    HUNT_SELECT_FAILURES_BEFORE_PAUSE, HUNT_AVOID_SECONDS)
from hunt_catalog import KNOWN, match_species, name_score, resolve_requested
from hunt_vision import HuntVision
from main import FishingBot
from metrics import METRICS


class HuntBot(FishingBot):
    mode = 'hunt'

    def __init__(self, desktop, detector, mouse, sound, args):
        super().__init__(desktop, detector, mouse, sound, args)
        self.vision = HuntVision(detector)
        self.species, self.allow_all = resolve_requested(getattr(args, 'creatures', None))
        # Bilinen ama seçilmemiş yaratıklar "bilinmeyen" sayılmasın diye havuz
        # seçilenler + bilinenlerdir.
        self.pool = tuple(dict.fromkeys(self.species + KNOWN))
        self.species_ids = {s.id for s in self.species}
        self.min_level = getattr(args, 'min_level', None)
        self.max_level = getattr(args, 'max_level', None)
        self.fights = 0
        self.select_failures = 0
        self.dy_index = 0
        self.engaged_at = 0.0
        self.return_clicks = 0
        self.off_map_frames = 0
        self.off_map_since = None
        self.last_point = None
        self.last_labels = 0
        self.current_name = ''
        self.scale_hint = 1.0

    # ------------------------------------------------------------ yardımcılar
    @property
    def click_dy(self):
        return HUNT_CLICK_DY_FALLBACKS[self.dy_index % len(HUNT_CLICK_DY_FALLBACKS)]

    def click_point(self, target, layout):
        """Gövdeye tıklanacak kare koordinatı (etiket + geçerli kayma)."""
        scale = self.vision.scale(layout)
        return (target.label_x, round(target.label_y + self.click_dy*scale))

    def classify(self, frame, sighting):
        """Etiketi oku ve türü çöz. Dönüş: (görülen, tür veya None)."""
        seen = self.vision.read_label(frame, sighting,
                                      accept=lambda name: match_species(name, self.pool) is not None)
        species = match_species(seen.name, self.pool) if seen.name else None
        if species:
            seen = replace(seen, species_id=species.id)
        return seen, species

    def wanted(self, seen, species):
        """(kabul, sebep). Seçili tür ve seviye sınırları."""
        if species is not None:
            if not self.allow_all and species.id not in self.species_ids:
                return False, 'seçili değil'
        elif not self.allow_all:
            return False, 'tanınmadı' if not seen.name else 'seçili değil'
        if seen.level is not None:
            if self.min_level is not None and seen.level < self.min_level:
                return False, f'seviye {seen.level} < {self.min_level}'
            if self.max_level is not None and seen.level > self.max_level:
                return False, f'seviye {seen.level} > {self.max_level}'
        return True, ''

    def header_verdict(self, header):
        """Üst bilgi kutusundaki ad hedefle örtüşüyor mu? True/False/None(okunamadı)."""
        text = (header or '').strip()
        if not text:
            return None
        target = self.target
        if target is None:
            return False
        if target.species_id:
            found = match_species(text, self.pool)
            return found is not None and found.id == target.species_id
        return name_score(text, target.name) >= 0.7

    def reset_hunt_target(self, now, blacklist=True):
        self.reset_target(now, blacklist=blacklist)

    def note_selection_success(self):
        self.select_failures = 0

    def note_selection_failure(self, frame, now, why):
        self.select_failures += 1
        METRICS.bump('hunt_select_fail')
        self.dy_index += 1
        self.notice(f'{why} Başarısız seçim: {self.select_failures}. Tıklama noktası değiştirilip yeni hedef aranacak.')
        self.reset_hunt_target(now)
        if self.select_failures >= HUNT_SELECT_FAILURES_BEFORE_PAUSE:
            self.select_failures = 0
            self.manual_pause = True
            self.block('Yaratık art arda seçilemedi. Ekranı kontrol edip F8 ile devam edin.', frame)

    # --------------------------------------------------------------- korumalar
    def hunt_guard(self, expected_layout, target=None, action=None):
        """Bir girdiden hemen önce taze ekranı yeniden doğrula.

        target: yaratığa tıklanacaksa yeniden bulunup düzeltilmiş masaüstü noktası döner.
        action: 'saldır' düğmesine tıklanacaksa düğmenin ve adın hâlâ doğru olduğu görülür.
        """
        self.control_guard()
        if not self.desktop.is_game_active():
            raise InterruptedError('Oyun odaktan çıktı; işlem iptal edildi.')
        frame = self.detector.capture()
        self.detector.auto_panel_probe(frame, force=True)
        obs = self.detector.observe(frame)
        if not obs.clear:
            if obs.protection or obs.blocked:
                self.block(obs.blocked or 'Bot koruması.', frame)
            METRICS.bump('guard_not_clear')
            raise InterruptedError('Ekran değişti; işlem iptal edildi.')
        if not self.layout_same(obs.layout, expected_layout):
            METRICS.bump('guard_layout_changed')
            raise InterruptedError('Harita yeri değişti; yeniden taranacak.')
        corrected = None
        if target is not None:
            fresh = self.vision.reacquire(frame, obs.layout, target)
            if fresh is None:
                METRICS.bump('reacquire_fail')
                raise InterruptedError('Yaratık son kontrolde bulunamadı; yeniden taranacak.')
            self.target = fresh
            corrected = self.pixel_to_desktop(self.click_point(fresh, obs.layout), frame)
        if action is not None:
            button = self.vision.attack_button(frame, obs.layout)
            if not button or math.dist(button, action) > 5:
                METRICS.bump('guard_action_mismatch')
                raise InterruptedError('Saldır düğmesi son kontrolde doğrulanamadı.')
            if self.header_verdict(self.vision.selected_name(frame, obs.layout)) is not True:
                METRICS.bump('guard_action_mismatch')
                raise InterruptedError('Seçili yaratığın adı son kontrolde doğrulanamadı.')
        self.control_guard()
        return corrected

    def result_guard(self, button):
        self.control_guard()
        if not self.desktop.is_game_active():
            raise InterruptedError('Oyun odaktan çıktı; sonuç ekranı kapatılmadı.')
        fresh = self.detector.capture()
        protected, reason = self.detector.check_bot_protection(fresh)
        if protected:
            self.block(reason or 'Bot koruması.', fresh)
            raise InterruptedError('Bot koruması; sonuç ekranı kapatılmadı.')
        current = self.vision.result_button(fresh)
        if current is None or math.dist(current, button) > 5:
            raise InterruptedError('Sonuç düğmesi son kontrolde görünmedi; yeniden okunacak.')
        self.control_guard()
        return None

    # -------------------------------------------------------------------- döngü
    def tick(self):
        try:
            self.control_guard()
        except InterruptedError as error:
            self.notice(str(error))
            return
        if not self.desktop.is_game_active():
            METRICS.bump('focus_wait')
            self.blocked_frames = 0
            self.block('Oyun önde değil; fare bekliyor. Oyuna dönünce devam edecek.', alarm=False)
            return
        frame = self.detector.capture()
        obs = self.detector.observe(frame)
        now = time.monotonic()
        if obs.layout is not None:
            self.scale_hint = obs.layout.width / 1520
        # 1) Bot Koruması her şeyden önce.
        if obs.protection:
            self.block(obs.blocked or 'Bot koruması; doğrulamayı siz tamamlayın.', frame)
            return
        # 2) Dövüş sonu penceresi: harita yokken ya da dövüşten dönerken aranır.
        if obs.layout is None or self.phase in ('ENGAGED', 'RETURNING'):
            button = self.vision.result_button(frame, self.scale_hint)
            if button:
                self.finish_fight(frame, button, now)
                return
        # 3) Harita yok: dövüş sürüyor ya da beklenmeyen ekran.
        if obs.layout is None:
            self.off_map(frame, obs, now)
            return
        self.off_map_frames, self.off_map_since = 0, None
        # 4) Haritada engelleyen oyun uyarısı.
        if obs.blocked:
            self.blocked_frames += 1
            METRICS.bump('frames_blocked')
            if obs.close_button:
                if self.dismiss_warning(frame, obs):
                    return
                if time.monotonic() - self.warning_close_at < WARNING_CLOSE_INTERVAL:
                    METRICS.bump('warning_wait')
                    return
            if self.blocked_frames < TRANSIENT_BLOCK_FRAMES:
                METRICS.bump('frames_transient')
                return
            self.block(obs.blocked, frame)
            return
        self.blocked_frames = 0
        latched = self.gate.latched
        if not self.gate.update(obs.clear, now):
            METRICS.bump('frames_screen_wait')
            self.notice('Oyun ekranı geri geldi; kararlı görüntü bekleniyor.')
            return
        if latched:
            self.sound.stop_alarm_loop()
            self.notice('Ekran doğrulandı; devam ediliyor.')
        if not obs.clear:
            return
        if self.phase == 'RETURNING':
            self.cycles += 1
            self.return_clicks = 0
            METRICS.bump('cycle_done')
            self.phase = 'SEARCH'
            self.notice(f'Dövüş tamamlandı, haritaya dönüldü. Tamamlanan: {self.cycles}.')
        if self.phase == 'ENGAGED':
            if now - self.engaged_at > HUNT_ENGAGE_TIMEOUT:
                METRICS.bump('hunt_engage_timeout')
                self.note_selection_failure(frame, now, 'Saldırı başlamadı.')
            return
        if self.phase == 'SELECTING':
            self.selecting(frame, obs, now)
            return
        self.search(frame, obs, now)

    def off_map(self, frame, obs, now):
        self.off_map_frames += 1
        if self.off_map_since is None:
            self.off_map_since = now
        if self.phase == 'ENGAGED':
            waited = now - self.engaged_at
            if waited > HUNT_FIGHT_TIMEOUT:
                METRICS.bump('fight_timeout')
                self.manual_pause = True
                self.block(f'Dövüş {HUNT_FIGHT_TIMEOUT:.0f} sn içinde bitmedi. '
                           'Ekranı kontrol edip F8 ile devam edin.', frame)
                return
            self.notice(f'Dövüş sürüyor ({waited:.0f} sn); sonuç ekranı bekleniyor.')
            return
        # Dövüş dışında harita görünmüyor: kullanıcı başka bir ekrana geçmiş olabilir.
        if self.off_map_frames < TRANSIENT_BLOCK_FRAMES:
            METRICS.bump('frames_transient')
            return
        self.block(obs.blocked or 'Avlan haritası görünmüyor.', frame,
                   alarm=False, seconds=RESUME_FAST_SECONDS)

    def finish_fight(self, frame, button, now):
        if self.args.dry_run:
            self.notice('Önizleme: dövüş sonu penceresi görüldü. Fare kullanılmıyor.')
            return
        if self.phase == 'RETURNING' and now - self.since < HUNT_RETURN_RETRY:
            return
        if self.return_clicks >= HUNT_RETURN_CLICK_LIMIT:
            self.return_clicks = 0
            self.manual_pause = True
            self.block('Sonuç penceresi "Ava" ile kapatılamadı. Ekranı kontrol edip F8 ile devam edin.', frame)
            return
        if self.return_clicks == 0:
            self.fights += 1
        self.mouse.click(*self.pixel_to_desktop(button, frame),
                         before_click=lambda: self.result_guard(button))
        self.return_clicks += 1
        self.phase, self.since = 'RETURNING', time.monotonic()
        self.notice(f'Dövüş bitti ({self.fights}); "Ava" ile haritaya dönülüyor.')

    def selecting(self, frame, obs, now):
        layout = obs.layout
        button = self.vision.attack_button(frame, layout)
        if button:
            header = self.vision.selected_name(frame, layout)
            self.current_name = header
            if self.allow_all and self.target is not None and not self.target.name and header:
                # 'all' modunda her yaratık kabul edilir; etiketi okunmayan
                # hedefin adı üst bilgi kutusundan taşınır, aksi halde aynı
                # yaratık tıkla-atla döngüsüne takılır.
                self.target = replace(self.target, name=header.split('[')[0].strip())
            verdict = self.header_verdict(header)
            if verdict is True:
                self.mouse.click(*self.pixel_to_desktop(button, frame),
                                 before_click=lambda: self.hunt_guard(layout, action=button))
                self.attempts += 1
                self.phase, self.since = 'ENGAGED', time.monotonic()
                self.engaged_at = self.since
                self.note_selection_success()
                self.notice(f'{self.target.name.title()} [{self.target.level}] doğrulandı; saldırılıyor ({self.attempts}).')
                return
            if verdict is False and now - self.since > 1:
                self.notice(f'Bu hedef atlandı: {header[:60]}. Ad seçilen yaratıkla örtüşmüyor.')
                self.reset_hunt_target(now)
                return
        if now - self.since > SELECT_TIMEOUT:
            METRICS.bump('select_timeout')
            self.note_selection_failure(frame, now, 'Yaratık seçimi doğrulanamadı.')

    def search(self, frame, obs, now):
        layout = obs.layout
        if self.scroll_before is not None:
            change = float(np.mean(abs(self.map_signature(frame, layout) - self.scroll_before)))
            if change < 5:
                self.scroll_direction = 'up' if self.scroll_direction == 'down' else 'down'
                self.notice('Kaydırma sınırına ulaşıldı; arama yönü değişti.')
            else:
                self.notice('Harita kaydı; yaratıkların yeni konumları taranıyor.')
            self.avoid.clear()
            self.scroll_before = None
        self.avoid = [(x, y, t) for x, y, t in self.avoid if now - t < min(TARGET_RETRY_SECONDS, HUNT_AVOID_SECONDS)]
        labels = self.vision.find_labels(frame, layout)
        self.last_labels = len(labels)
        free = [s for s in labels if not any(math.hypot(s.x - x, s.y - y) < 24 for x, y, _t in self.avoid)]
        origin = self.last_point or ((layout.left + layout.right)//2, (layout.top + layout.bottom)//2)
        free.sort(key=lambda s: math.hypot(s.x - origin[0], s.y - origin[1]))
        chosen, skipped = None, []
        for sighting in free:
            seen, species = self.classify(frame, sighting)
            good, why = self.wanted(seen, species)
            if good:
                chosen = seen
                break
            skipped.append(f'{seen.name or "?"}[{seen.level}]: {why}')
        if self.args.dry_run:
            self.notice(f'Önizleme: {len(labels)} yaratık; '
                        + (f'hedef {chosen.name}[{chosen.level}]' if chosen else 'uygun hedef yok')
                        + (f' (atlanan: {"; ".join(skipped[:3])})' if skipped else '') + '. Fare kullanılmıyor.')
            return
        if chosen:
            self.target = chosen
            self.target_origin = (chosen.x, chosen.y)
            self.last_point = (chosen.x, chosen.y)
            target = chosen
            scale = self.desktop_scale(frame)
            self.mouse.click(*self.pixel_to_desktop(self.click_point(target, layout), frame),
                             before_click=lambda: self.hunt_guard(layout, target=target),
                             target_tolerance=max(4, 9*self.vision.scale(layout))*scale)
            self.phase, self.since = 'SELECTING', time.monotonic()
            self.last_fish = now
            self.empty_frames = 0
            self.notice(f'{chosen.name.title()} [{chosen.level}] seçildi: ({chosen.label_x}, {chosen.label_y}). '
                        'Saldır düğmesi bekleniyor.')
            return
        self.empty_frames += 1
        if skipped and self.empty_frames == 1:
            self.notice('Görünen yaratıklar atlandı: ' + '; '.join(skipped[:4]))
        if not self.args.no_scroll and self.empty_frames >= 3 and now - self.last_scroll >= 2:
            p = (layout.right - 50, (layout.top + layout.bottom)//2)
            self.mouse.scroll(*self.pixel_to_desktop(p, frame), self.scroll_direction,
                              before_scroll=lambda: self.hunt_guard(layout))
            self.scroll_before = self.map_signature(frame, layout)
            self.last_scroll = time.monotonic()
            self.scrolls += 1
            self.empty_frames = 0
            self.notice(f'Uygun yaratık aranıyor; harita {"aşağı" if self.scroll_direction == "down" else "yukarı"} kaydırıldı.')
        if now - self.last_fish > NO_FISH_ALERT_SECONDS:
            self.sound.play_once()
            self.notice('Arama sürüyor; seçtiğiniz yaratıklardan henüz bulunamadı.')
            self.last_fish = now

    # ------------------------------------------------------------------ durum
    def status_data(self, running=True):
        data = super().status_data(running)
        data.update(mode='hunt', fights=self.fights, creatures=[s.name for s in self.species],
                    allow_all=self.allow_all, min_level=self.min_level, max_level=self.max_level,
                    visible_creatures=self.last_labels, current_name=self.current_name)
        return data


def inspect_image(detector, frame, output=None):
    """Bir ekran görüntüsünü çevrimdışı çöz: yaratıklar, seçim, düğmeler."""
    import cv2 as _cv2
    vision = HuntVision(detector)
    obs = detector.observe(frame)
    report = dict(layout=None, clear=obs.clear, blocked=obs.blocked, creatures=[],
                  attack_button=None, result_button=None)
    if obs.layout is not None:
        report['layout'] = [obs.layout.left, obs.layout.top, obs.layout.right, obs.layout.bottom]
        pool = tuple(KNOWN)
        for sighting in vision.find_labels(frame, obs.layout):
            seen = vision.read_label(frame, sighting, accept=lambda name: match_species(name, pool) is not None)
            species = match_species(seen.name, pool) if seen.name else None
            report['creatures'].append(dict(name=seen.name, level=seen.level, species=species.id if species else None,
                                            color=seen.color, label=[seen.label_x, seen.label_y],
                                            click=[seen.x, seen.y]))
        report['attack_button'] = vision.attack_button(frame, obs.layout)
    scale = 1.0 if obs.layout is None else obs.layout.width / 1520
    report['result_button'] = vision.result_button(frame, scale)
    if output is not None:
        canvas = frame.copy()
        for c in report['creatures']:
            _cv2.circle(canvas, tuple(c['click']), 16, (255, 70, 70), 2)
            _cv2.putText(canvas, f"{c['name']}[{c['level']}]", (c['click'][0] - 40, c['click'][1] - 22),
                         _cv2.FONT_HERSHEY_SIMPLEX, .5, (255, 255, 255), 1)
        if report['result_button']:
            _cv2.circle(canvas, tuple(report['result_button']), 14, (70, 255, 70), 2)
        from PIL import Image
        output.parent.mkdir(parents=True, exist_ok=True)
        Image.fromarray(canvas).save(output)
    return report
