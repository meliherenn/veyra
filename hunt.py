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
from PIL import Image

from config import (POLL_INTERVAL, SELECT_TIMEOUT, TARGET_RETRY_SECONDS, NO_FISH_ALERT_SECONDS,
                    TRANSIENT_BLOCK_FRAMES, RESUME_FAST_SECONDS, WARNING_CLOSE_INTERVAL,
                    HUNT_SPRITE_DY, HUNT_CLICK_DY_FALLBACKS, HUNT_ENGAGE_TIMEOUT,
                    HUNT_FIGHT_TIMEOUT, HUNT_RETURN_RETRY, HUNT_RETURN_CLICK_LIMIT,
                    HUNT_SELECT_FAILURES_BEFORE_PAUSE, HUNT_AVOID_SECONDS,
                    HUNT_PROVOKE_BAR_TIMEOUT, HUNT_SUMMON_CLICK_PAUSE,
                    HUNT_FIGHT_SETTLE_SECONDS, HUNT_SUMMON_MAX_PER_SLOT,
                    HUNT_CONFIRM_RETRIES, HUNT_LABEL_MATCH_RATIO)
import config as _cfg
from hunt_catalog import KNOWN, match_species, name_score, remember_seen, resolve_requested
from hunt_vision import HuntVision
import main
from main import FishingBot
from metrics import METRICS


# Dövüş beklenirken (girdi gönderilmeyen) tam observe() bu aralıkla çalışır; arada
# yalnızca koruma şablonu + sonuç düğmesi bakılır.
HUNT_FIGHT_IDLE_OBSERVE = getattr(_cfg, 'HUNT_FIGHT_IDLE_OBSERVE', 1.5)
# 'Otomatik savaş' sonrası onay penceresini bekleme süresi (binek için varsayılan 2 sn kalır).
HUNT_AUTO_CONFIRM_WINDOW = getattr(_cfg, 'HUNT_AUTO_CONFIRM_WINDOW', 0.9)
# Çağırma tıklamalarında OCR'lı koruma taraması en fazla bu sıklıkta çalışır. 0 = her
# tıklamada (bugünkü, en sıkı davranış). Şablon kontrolü HER ZAMAN her tıklamada yapılır.
HUNT_SUMMON_OCR_INTERVAL = getattr(_cfg, 'HUNT_SUMMON_OCR_INTERVAL', 0.0)


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
        # Dövüş içi eylemler: provokasyonla yaratık çağırma, binek, otomatik savaş.
        self.provoke = bool(getattr(args, 'provoke', False))
        self.mount_summon = bool(getattr(args, 'mount', False))
        self.auto_battle = bool(getattr(args, 'auto_battle', False))
        self.provoke_counts = [int(n) for n in (getattr(args, 'provoke_counts', None) or [])]
        self.fight_actions_done = False
        self.confirm_retries = 0
        self.last_confirm_check = 0.0
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
        self._fight_block_start = None
        self.last_full_observe = 0.0
        self.last_wait_notice = 0.0
        self.actions_done_at = 0.0
        self._last_ocr_check = 0.0

    # ------------------------------------------------------------ yardımcılar
    def block(self, reason, frame=None, alarm=True, seconds=None):
        """Dövüş sırasındaki odak/ekran beklemesi dövüş durumunu silmesin.

        FishingBot.block() fazı SEARCH'e çekiyordu; dövüş ortasında bu, dövüş
        zaman aşımını, onay yeniden denemelerini ve 'Dövüş sürüyor' izlemesini
        kapatıyordu (logda dakikalarca 'Avlan haritası görünmüyor' döngüsü).
        """
        keep = self.phase if self.phase in ('ENGAGED', 'RETURNING') else None
        super().block(reason, frame, alarm, seconds)
        if keep is not None:
            self.phase = keep
            if self._fight_block_start is None:
                self._fight_block_start = time.monotonic()

    def protection_check(self, frame, ocr_interval=0.0):
        """Koruma kontrolü: şablon her zaman, OCR yedeği ocr_interval ile sınırlı."""
        if self.detector.protection_template(frame):
            return True, 'Bot koruması başlığı ekranda görüldü.'
        now = time.monotonic()
        if ocr_interval and now - self._last_ocr_check < ocr_interval:
            METRICS.bump('protection_ocr_skipped')
            return False, None
        self._last_ocr_check = now
        return self.detector.check_bot_protection(frame, False)

    def fight_idle(self, frame, now):
        """Dövüş beklenirken (girdi YOK) ucuz kare kontrolü. True: kare ele alındı."""
        if self.detector.protection_template(frame):
            self.block('Bot koruması; doğrulamayı siz tamamlayın.', frame)
            return True
        button = self.vision.result_button(frame, self.scale_hint)
        if button:
            self.finish_fight(frame, button, now)
            return True
        waited = now - self.engaged_at
        if waited > HUNT_FIGHT_TIMEOUT:
            return False                      # zaman aşımını tam yol yönetir
        if now - self.last_wait_notice >= 4.0:
            self.last_wait_notice = now
            self.notice(f'Dövüş sürüyor ({waited:.0f} sn); sonuç ekranı bekleniyor.')
        METRICS.bump('fight_idle_fast')
        return True

    @property
    def click_dy(self):
        return HUNT_CLICK_DY_FALLBACKS[self.dy_index % len(HUNT_CLICK_DY_FALLBACKS)]

    def click_point(self, target, layout):
        """Gövdeye tıklanacak kare koordinatı (etiket + geçerli kayma)."""
        scale = self.vision.scale(layout)
        return (target.label_x, round(target.label_y + self.click_dy*scale))

    def classify(self, frame, sighting):
        """Etiketi oku ve türü çöz. Dönüş: (görülen, tür veya None).

        Harita etiketi küçük ve gürültülü okunur ('flungyuriy kore yavrusul');
        bu yüzden burada gevşek eşik kullanılır. Kesin karar, saldırıdan
        hemen önceki üst bilgi kutusu doğrulamasının sıkı eşiğindedir.
        """
        seen = self.vision.read_label(
            frame, sighting,
            accept=lambda name: match_species(name, self.pool, HUNT_LABEL_MATCH_RATIO) is not None)
        species = match_species(seen.name, self.pool, HUNT_LABEL_MATCH_RATIO) if seen.name else None
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
            # Onay popup'ı oyundan AYRI bir pencere olarak odağı alabilir;
            # dövüş içi eylemlerden sonra bekleyen onayı burada yönet.
            if (self.phase == 'ENGAGED' and self.fight_actions_done
                    and self.confirm_retries < HUNT_CONFIRM_RETRIES
                    and time.monotonic() - self.last_confirm_check >= 1.0):
                self.last_confirm_check = time.monotonic()
                self.desktop.allow_action_popup = True
                try:
                    fresh = self.detector.capture_screen()
                    if self.vision.confirm_apply_button(fresh):
                        self.confirm_retries += 1
                        self.notice('Bekleyen eylem onayı görüldü; Uygula deneniyor.')
                        self.confirm_pending_action(1.5)
                        return
                except InterruptedError as error:
                    self.notice(f'Onay verilemedi: {error}')
                    return
                finally:
                    self.desktop.allow_action_popup = False
            METRICS.bump('focus_wait')
            self.blocked_frames = 0
            state = self.desktop.state
            self.block('Oyun önde değil; fare bekliyor. Oyuna dönünce devam edecek. '
                       f'(aktif: {str(state.get("app", ""))[:20]} / {str(state.get("title", ""))[:40]})',
                       alarm=False)
            return
        frame = self.detector.capture()
        now = time.monotonic()
        # Dövüş beklerken girdi gönderilmez: her karede tam observe() (büyük bölgede OCR dahil)
        # yerine ucuz kontrol; tam kontrol HUNT_FIGHT_IDLE_OBSERVE aralığıyla sürer.
        if (self.phase == 'ENGAGED' and self.fight_actions_done
                and now - self.last_full_observe < HUNT_FIGHT_IDLE_OBSERVE
                and self.fight_idle(frame, now)):
            return
        self.last_full_observe = now
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
            if self._fight_block_start is not None:
                # Bekleme/koruma süresi dövüş zaman aşımına sayılmaz.
                self.engaged_at += now - self._fight_block_start
                self._fight_block_start = None
            waited = now - self.engaged_at
            if waited > HUNT_FIGHT_TIMEOUT:
                METRICS.bump('fight_timeout')
                self.manual_pause = True
                self.block(f'Dövüş {HUNT_FIGHT_TIMEOUT:.0f} sn içinde bitmedi. '
                           'Ekranı kontrol edip F8 ile devam edin.', frame)
                return
            if not self.fight_actions_done and (self.provoke or self.mount_summon
                                                or self.auto_battle):
                self.fight_actions_done = True
                if self.args.dry_run:
                    self.notice('Önizleme: dövüş eylemleri (provokasyon/binek/otomatik '
                                'savaş) dry-run\'da kullanılmıyor.')
                else:
                    self.perform_fight_actions()
                    return
            elif self.fight_actions_done and self.confirm_retries < HUNT_CONFIRM_RETRIES \
                    and now - self.last_confirm_check >= 3.0 and now - self.actions_done_at < 30.0:
                # Onay penceresi açıkken odağı kaybolduysa Uygula yarım kalmıştır;
                # dövüş boyunca yeniden denenir.
                self.last_confirm_check = now
                self.desktop.allow_action_popup = True
                try:
                    fresh = self.detector.capture_screen()
                    if self.vision.confirm_apply_button(fresh):
                        self.confirm_retries += 1
                        self.notice('Bekleyen eylem onayı görüldü; Uygula deneniyor.')
                        self.confirm_pending_action(1.5)
                finally:
                    self.desktop.allow_action_popup = False
            self.notice(f'Dövüş sürüyor ({waited:.0f} sn); sonuç ekranı bekleniyor.')
            return
        # Dövüş dışında harita görünmüyor: kullanıcı başka bir ekrana geçmiş olabilir.
        if self.off_map_frames < TRANSIENT_BLOCK_FRAMES:
            METRICS.bump('frames_transient')
            return
        self.block(obs.blocked or 'Avlan haritası görünmüyor.', frame,
                   alarm=False, seconds=RESUME_FAST_SECONDS)

    # -------------------------------------------------------- dövüş içi eylemler
    def neutral_move(self, like_frame, anchor=None):
        """İmleci okumayı karıştırmayacak boş bir noktaya alır. anchor verilirse
        (çağırma çubuğu) sadece biraz yukarısına gider: uzun yolculuk yavaş."""
        h, w = like_frame.shape[:2]
        target = (anchor[0], max(80, anchor[1] - 170)) if anchor else (w//2, h//3)
        try:
            self.mouse.move_to(*self.pixel_to_desktop(target, like_frame))
        except (InterruptedError, ValueError):
            pass

    def capture_parked(self, like_frame, anchor=None):
        self.neutral_move(like_frame, anchor)
        return self.detector.capture()

    def fight_guard(self, kind, point):
        """Dövüş düğmesi tıklamasından hemen önce: koruma, odak ve hâlâ dövüş
        ekranındayız. Düğme şablonu burada yeniden okunmaz: imleç düğmenin
        üstüne gelince oyunun vurgusu şablon skorunu düşürüyor ve tıklama
        boşuna iptal oluyordu. Nokta, tıklamadan hemen önceki karede
        doğrulanmıştır; dövüş arayüzü düğmeleri kendiliğinden kaydırmaz."""
        self.control_guard()
        if not self.desktop.is_game_active():
            raise InterruptedError('Oyun odaktan çıktı; dövüş eylemi iptal edildi.')
        fresh = self.detector.capture()
        protected, reason = self.detector.check_bot_protection(fresh)
        if protected:
            self.block(reason or 'Bot koruması.', fresh)
            raise InterruptedError('Bot koruması; dövüş eylemi iptal edildi.')
        if self.detector.detect_layout(fresh) is not None or self.vision.result_button(fresh, self.scale_hint):
            raise InterruptedError(f'Dövüş ekranı değişti; {kind} düğmesine basılmadı.')
        self.control_guard()

    def summon_guard(self, point, frame=None, bar_open=False):
        """Çağırma tıklamasından önce: dur/pause, koruma, dövüş sürüyor, çubuk açık.

        Döngü zaten taze kareyle slotu yeniden bulduğu için burada ikinci bir
        yakalama/detection zinciri çalışmaz (her tıklamayı ~1 sn yavaşlatıyordu);
        koruma taraması eldeki kareyle yapılır.
        """
        self.control_guard()
        if frame is None:
            frame = self.detector.capture()
        with METRICS.span('summon_guard'):
            protected, reason = self.protection_check(frame, HUNT_SUMMON_OCR_INTERVAL)
            if protected:
                self.block(reason or 'Bot koruması.', frame)
                raise InterruptedError('Bot koruması; çağırma iptal edildi.')
            if self.vision.result_button(frame, self.scale_hint):
                raise InterruptedError('Dövüş çağırma bitmeden bitti; çağırma durduruldu.')
            if self.detector.detect_layout(frame) is not None:
                raise InterruptedError('Haritaya dönüldü; çağırma durduruldu.')
            if not bar_open:
                # Döngü aynı karede slotu zaten doğruladıysa ikinci şablon taraması gereksiz.
                slots, locks = self.vision.summon_slots(frame)
                if not slots and not locks:
                    raise InterruptedError('Çağırma çubuğu kapandı; çağırma durduruldu.')
        self.control_guard()

    def click_fight_button(self, frame, kind, message):
        """Dövüş içi düğmeye koruma ile bas; düğme yoksa haber verip geç."""
        button = self.vision.fight_button(frame, kind)
        if not button:
            self.notice(f'{kind} düğmesi ekranda görünmüyor; atlandı.')
            return False
        self.mouse.click(*self.pixel_to_desktop(button, frame),
                         before_click=lambda: self.fight_guard(kind, button))
        METRICS.bump(f'fight_{kind}')
        self.notice(message)
        return True

    def confirm_guard(self, point, threshold=0.70):
        """Onay tıklamasından hemen önce: koruma/odak; pencere hâlâ açık mı?

        Düğme şablonu noktanın çevresinde, şablondan büyük bir pencerede
        aranır (dar bölge OpenCV assertion'ı ile botu düşürüyordu). İmleç
        düğmenin üstündeyken vurgu skoru düşürebildiği için eşik düşüktür.
        """
        self.control_guard()
        if not self.desktop.is_game_active():
            raise InterruptedError('Oyun odaktan çıktı; onay verilmedi.')
        fresh = self.detector.capture_screen()
        protected, reason = self.detector.check_bot_protection(fresh)
        if protected:
            self.block(reason or 'Bot koruması.', fresh)
            raise InterruptedError('Bot koruması; onay verilmedi.')
        if self.vision.apply_template is None:
            return
        th, tw = self.vision.apply_template.shape[:2]
        x0, x1 = max(0, point[0] - tw), min(fresh.shape[1], point[0] + tw)
        y0, y1 = max(0, point[1] - th), min(fresh.shape[0], point[1] + th)
        region = fresh[y0:y1, x0:x1]
        if region.shape[0] < th or region.shape[1] < tw:
            raise InterruptedError('Onay penceresi son kontrolde görünmedi.')
        try:
            score = float(cv2.matchTemplate(region, self.vision.apply_template,
                                            cv2.TM_CCOEFF_NORMED).max())
        except cv2.error as exc:
            raise InterruptedError('Onay penceresi okunamadı; yeniden denenecek.') from exc
        if score < threshold:
            raise InterruptedError('Onay penceresi son kontrolde görünmedi.')

    def confirm_pending_action(self, window=2.0):
        """Eylem onay penceresi ('...onaylayın') açıldıysa Uygula'ya basar.

        Onay, oyunun ÜSTÜNE açılan AYRI bir tarayıcı penceresidir: kare tam
        ekrandan alınır ve popup aktifken fare izni kapsamlı açılır. 'Verildi'
        ancak pencerenin kapandığı görülerek söylenir; Uygula tıklaması
        kayıtsız kalırsa (İptal ile karışma, odak kaybı) pencere süresi
        içinde yeniden denenir.
        """
        deadline = time.monotonic() + window
        clicked = False
        self.desktop.allow_action_popup = True
        try:
            while time.monotonic() < deadline:
                fresh = self.detector.capture_screen()
                button = self.vision.confirm_apply_button(fresh)
                if button is None:
                    if clicked:
                        METRICS.bump('confirm_apply')
                        self.notice('Eylem onayı Uygula ile verildi.')
                        return True
                    time.sleep(0.25)
                    continue
                self.mouse.click(*self.pixel_to_desktop(button, fresh),
                                 before_click=lambda p=button: self.confirm_guard(p))
                clicked = True
                time.sleep(0.3)
        finally:
            self.desktop.allow_action_popup = False
        if clicked:
            self.notice('Onay penceresi kapanmadı; bekleyen onay yeniden denenir.')
        return False

    def _enabled_fight_kinds(self):
        return [kind for kind, enabled in (('provoke', self.provoke),
                                           ('auto', self.auto_battle),
                                           ('mount', self.mount_summon)) if enabled]

    def perform_fight_actions(self):
        """Dövüş başladıktan sonra bir kez: provokasyon -> oto savaş -> binek."""
        self.actions_done_at = time.monotonic()
        time.sleep(HUNT_FIGHT_SETTLE_SECONDS)
        frame = self.detector.capture()
        kinds = self._enabled_fight_kinds()
        # Araç çubuğu dövüşle birlikte animasyonla gelir; ilk karede
        # görünmeyebilir (provoke 'görünmüyor' sanılıp kalıcı atlanmıştı).
        deadline = time.monotonic() + _cfg.HUNT_TOOLBAR_WAIT_SECONDS
        while kinds and time.monotonic() < deadline and not all(
                self.vision.fight_button(frame, k) is not None for k in kinds):
            time.sleep(0.4)
            frame = self.detector.capture()
        if kinds and not any(self.vision.fight_button(frame, k) for k in kinds):
            self.notice('Dövüş araç çubuğu görünmedi; dövüş eylemleri atlandı.')
            return
        if self.provoke:
            try:
                self.run_provoke(frame)
            except InterruptedError as error:
                self.notice(f'Provokasyon yarıda kaldı: {error}')
        frame = self.capture_parked(frame)
        if self.auto_battle:
            if self.click_fight_button(frame, 'auto', 'Otomatik savaş açılıyor.'):
                self.confirm_pending_action(HUNT_AUTO_CONFIRM_WINDOW)
            frame = self.capture_parked(frame)
        if self.mount_summon:
            if self.click_fight_button(frame, 'mount', 'Binek çağırılıyor.'):
                self.confirm_pending_action(3.5)
        self.actions_done_at = time.monotonic()

    def _await_slot(self, anchor_x, seconds=1.5):
        """Çubuk animasyon geçişinde kaybolduğunda slotun geri gelmesini bekler."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(0.3)
            fresh = self.detector.capture()
            current, _locks = self.vision.summon_slots(fresh)
            slot = next((s for s in current if abs(s[0] - anchor_x) <= 10), None)
            if slot is not None:
                return slot, fresh
        return None, None

    def _await_counter_change(self, anchor_x, previous_mask, seconds=1.6):
        """Tıklamanın işlenmesini bekler: sayaç değişirse yeni maskayı, değişmezse None döner."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            time.sleep(0.35)
            fresh = self.detector.capture()
            current, _locks = self.vision.summon_slots(fresh)
            slot = next((s for s in current if abs(s[0] - anchor_x) <= 10), None)
            if slot is None:
                continue
            mask = self.vision.counter_mask(fresh, slot[2])
            if mask is not None and not np.array_equal(mask, previous_mask):
                return mask
        return None

    def _summon_slot(self, anchor_x, wanted):
        """Tek slotta `wanted` adet çağır; işlenen tıklama sayısını döner.

        None: çubuk kapandı (çağrı akışından tamamen çıkılmalı). Her tıklamadan
        önce slot yeniden doğrulanır; tıklama sonrası sayacın değişmesi
        ~1.6 sn'ye kadar beklenir — 0.30 sn'lik aralık oyunun işleme
        süresine yetmeyebiliyor (1/7, 1/7, 2/7 olayı).
        """
        previous_mask = None
        summoned = 0
        while summoned < wanted:
            with METRICS.span('summon_capture'):
                fresh = self.detector.capture()
                current, _locks = self.vision.summon_slots(fresh)
            slot = next((s for s in current if abs(s[0] - anchor_x) <= 10), None)
            if slot is None:
                slot, fresh = self._await_slot(anchor_x)
                if slot is None:
                    self.notice('Çağırma çubuğu kapandı; kalan çağrılar atlandı.')
                    return None
            mask = self.vision.counter_mask(fresh, slot[2])
            if previous_mask is not None and mask is not None and np.array_equal(mask, previous_mask):
                changed = self._await_counter_change(anchor_x, previous_mask)
                if changed is None:
                    self.notice(f'Sayaç değişmedi ({summoned} çağrı işledi); jeton bitmiş '
                                'ya da sınır dolmuş olabilir. Kalan çağrılar atlandı.')
                    break
                mask = changed
            with METRICS.span('summon_click'):
                self.mouse.click(*self.pixel_to_desktop((slot[0], slot[1]), fresh),
                                 before_click=lambda p=(slot[0], slot[1]), f=fresh:
                                 self.summon_guard(p, f, bar_open=True))
            summoned += 1
            previous_mask = mask
            METRICS.bump('summon')
            time.sleep(HUNT_SUMMON_CLICK_PAUSE)
        return summoned

    def run_provoke(self, frame):
        """Provokasyonu aç, çubuk oturana kadar bekle, slot sırasına göre çağır.

        Çubuk animasyonla açılır: sayaçlar teker teker belirir ('1 slot' sanıp
        diğerlerini atlamamak için) slot sayısı 1.2 sn artmadığında çubuk
        'oturmuş' sayılır. Çağrılar bittikten sonra çubuk bir kez daha taranır;
        geç beliren slotlar da çağrılır. Tanı için çubuğun ilk karesi
        runtime/last-provoke.png içine kaydedilir.
        """
        if not self.click_fight_button(frame, 'provoke',
                                       'Provokasyon açılıyor; çağırma çubuğu bekleniyor.'):
            return
        deadline = time.monotonic() + HUNT_PROVOKE_BAR_TIMEOUT
        slots = []
        while time.monotonic() < deadline:
            fresh = self.detector.capture()
            slots, _locks = self.vision.summon_slots(fresh)
            if slots:
                break
            time.sleep(0.5)
        if not slots:
            self.notice('Çağırma çubuğu açılmadı; provokasyon atlandı. '
                        'Son kare runtime/last-provoke.png içine kaydedildi.')
            try:
                Image.fromarray(fresh).save(main.RUNTIME / 'last-provoke.png')
            except (OSError, ValueError):
                pass
            return
        last_growth = time.monotonic()
        last_count = len(slots)
        stable_deadline = time.monotonic() + 4.0
        while time.monotonic() < stable_deadline:
            time.sleep(0.35)
            fresh = self.detector.capture()
            current, _locks = self.vision.summon_slots(fresh)
            if len(current) > last_count:
                last_count = len(current)
                last_growth = time.monotonic()
                slots = current
            elif current:
                slots = current
            if time.monotonic() - last_growth >= 1.2:
                break
        slots.sort(key=lambda s: s[0])
        counts = self.provoke_counts
        self.notice(f'Çağırma çubuğu açık: {len(slots)} slot @ '
                    + ','.join(str(s[0]) for s in slots) + '. Sıra: '
                    + ', '.join(str(counts[i] if i < len(counts) else 0)
                                for i in range(len(slots))) + '.')
        try:
            Image.fromarray(fresh).save(main.RUNTIME / 'last-provoke.png')
        except (OSError, ValueError):
            pass
        visited = []
        for index, slot in enumerate(slots):
            wanted = counts[index] if index < len(counts) else 0
            wanted = max(0, min(wanted, HUNT_SUMMON_MAX_PER_SLOT))
            visited.append(slot[0])
            if not wanted:
                continue
            got = self._summon_slot(slot[0], wanted)
            if got is None:
                return
            if got:
                self.notice(f'{index + 1}. slottan {got} yaratık çağrıldı.')
        # Geç beliren slotlar: çağrılar bittikten sonra çubuğu yeniden tara.
        fresh = self.detector.capture()
        current, _locks = self.vision.summon_slots(fresh)
        late = [s for s in current if all(abs(s[0] - ax) > 15 for ax in visited)]
        ordered = sorted(current, key=lambda s: s[0])
        for slot in late:
            index = ordered.index(slot)
            wanted = counts[index] if index < len(counts) else 0
            wanted = max(0, min(wanted, HUNT_SUMMON_MAX_PER_SLOT))
            visited.append(slot[0])
            if not wanted:
                continue
            got = self._summon_slot(slot[0], wanted)
            if got is None:
                return
            if got:
                self.notice(f'{index + 1}. slottan {got} yaratık çağrıldı.')

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
                self.fight_actions_done = False
                self.confirm_retries = 0
                self.last_confirm_check = 0.0
                self.last_full_observe = 0.0
                self._fight_block_start = None
                self.note_selection_success()
                if self.target.name and self.target.species_id is None:
                    if remember_seen(main.RUNTIME / 'creatures.json', self.target.name):
                        self.notice(f'Yeni yaratık panelin listesine eklendi: {self.target.name.title()}.')
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
                    visible_creatures=self.last_labels, current_name=self.current_name,
                    provoke=self.provoke, mount=self.mount_summon, auto_battle=self.auto_battle,
                    provoke_counts=self.provoke_counts)
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
