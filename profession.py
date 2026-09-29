"""Interruptible inventory recovery and profession-energy state machine."""
import json
import time

import numpy as np

from config import ENERGY_READ_REOPENS, POTION_VERIFY_SECONDS, POTION_VERIFY_READS, POTION_ACCEPT_SECONDS
from energy_store import EnergyStore
from fish_catalog import BY_ID
from metrics import METRICS
from profession_vision import Box, ProfessionVision, recovery_reason


class ProfessionController:
    def __init__(self, bot, runtime):
        self.bot = bot
        self.vision = ProfessionVision(bot.detector)
        self.energy = EnergyStore(runtime / 'energy.json')
        self.journal = runtime / 'recovery.json'
        self.energy_enabled = bool(getattr(bot.args, 'energy_cycle', False))
        # Kurtarma varsayılan olarak açıktır: kıymıkta önce iksir, sonra olta
        # takılır. --no-auto-splinter ile kapatılabilir.
        self.recovery_enabled = bool(getattr(bot.args, 'auto_splinter', True))
        self.enabled = self.energy_enabled or self.recovery_enabled
        self.auto_fish_id = getattr(bot.args, 'auto_fish_id', 'elmas_som')
        # Do not touch the inventory at startup.  The original fishing loop can
        # run immediately; equipment recovery is entered only after the game
        # visibly reports that the tool is missing or a splinter was detected.
        self.state = 'IDLE'
        self.after_equip = 'AUTO_OPEN' if self.energy_enabled else 'RETURN'
        self.since = time.monotonic()
        self.last_action = 0
        self.scans = 0
        self.bag_reopens = 0
        self.energy_reopens = 0
        self.potion_reads = 0
        self.potion_unverified = False
        self.potion_box = None
        self.potion_stack = None
        self.potion_badge_px = None
        self.auto_cycles = 0
        self.recoveries = 0
        self.auto_before = None
        self.auto_seconds = 0
        self.auto_started = 0
        self.potion_count = None
        self.potion_attempted = False
        self.potion_applied = False
        self.retry_recovery = False
        self.full_reading = None
        self.full_count = 0
        self.last_progress = None
        self.progress_at = time.monotonic()
        self.auto_progress = None
        self.auto_total = None
        self.auto_seen = False
        try:
            saved=json.loads(self.journal.read_text())
            self.potion_attempted = saved.get('pending') is True
            self.potion_applied = self.potion_attempted and saved.get('stage')!='opened'
            self.potion_count = saved.get('count')
            # Yeniden başlatmada slot ve yığın da geri yüklenir; yoksa doğrulama
            # yalnız çanta sayımına kalır ve bot F8'e takılabilir.
            box = saved.get('box')
            if isinstance(box, list) and len(box) == 4:
                self.potion_box = Box(*box)
                self.potion_stack = saved.get('stack')
            if self.potion_attempted:self.state='POTION_CONFIRM'
        except (OSError, ValueError, AttributeError):
            pass

    def transition(self, state, message=None):
        self.state = state
        if state=='AUTO_READ':
            self.full_reading=None
            self.full_count=0
        if state=='POTION_CONFIRM':
            self.potion_reads = 0
            self.potion_unverified = False
        self.since = time.monotonic()
        self.scans = 0
        self.bag_reopens = 0
        if message:
            self.bot.notice(message)

    def fail(self, message, frame):
        self.bot.manual_pause = True
        self.bot.block(message + ' Kontrol ettikten sonra F8 ile devam edebilirsiniz.', frame)

    def record_potion(self, pending, stage='submitted'):
        self.potion_attempted = pending
        self.potion_applied = pending and stage=='submitted'
        payload = {'pending': pending, 'stage':stage,'count':self.potion_count,'time': time.time()}
        # Kayıtlar yalnız JSON güvenli değerler tutar; sahte (test) kontroller
        # box/stack alanlarını doldurmasa da yazma işlemi kırılmamalı.
        if isinstance(self.potion_box, Box):
            payload['box'] = [self.potion_box.x, self.potion_box.y, self.potion_box.w, self.potion_box.h]
        if isinstance(self.potion_stack, int):
            payload['stack'] = self.potion_stack
        temp = self.journal.with_suffix('.tmp')
        temp.write_text(json.dumps(payload))
        temp.replace(self.journal)

    def manual_completed(self):
        if self.energy_enabled:
            self.energy.manual_completed()
        if self.potion_attempted:
            self.record_potion(False)
        self.retry_recovery = False

    def request_sync(self):
        if self.state == 'IDLE' and self.energy_enabled:
            self.transition('AUTO_OPEN', 'Meslek enerjisi ekrandan doğrulanıyor.')

    def request_recovery(self, reason):
        if not self.recovery_enabled or reason not in ('splinter', 'tool'):
            return False
        # Preserve this stage across focus loss, pause, and an interrupted input.
        if self.state.startswith('POTION'):
            return True
        if self.state.startswith('EQUIP') and reason == 'tool':
            return True
        self.after_equip = 'AUTO_OPEN' if self.energy_enabled else 'RETURN'
        self.transition('POTION_OPEN' if reason=='splinter' else 'EQUIP_OPEN',
                        'Kıymık algılandı; Orman Kalbi İksiri aranıyor.' if reason == 'splinter'
                        else 'Olta takılı değil; çantadaki olta takılacak.')
        return True

    def click(self, frame, finder, message, hover_label=None, before_submit=None):
        box = finder(frame)
        if box is None:
            return False
        def guard():
            self.bot.control_guard()
            if not self.bot.desktop.is_game_active():
                raise InterruptedError('Oyun odakta değil; meslek işlemi bekliyor.')
            fresh = self.bot.detector.capture()
            protected, reason = self.bot.detector.check_bot_protection(fresh)
            if protected:
                self.bot.block(reason or 'Bot koruması.', fresh)
                raise InterruptedError('Bot koruması; meslek işlemi durdu.')
            current = None
            if hover_label:
                cell = Box(box.x-8, box.y-8, box.w+16, box.h+25)
                action_name='item-use' if hover_label=='Kullan' else 'item-equip'
                actions=self.vision.matches(fresh,action_name,cell,threshold=.86)
                current=actions[0] if actions else None
                labels=('Kullanmak','Kullan') if hover_label=='Kullan' else (hover_label,)
                for label in labels:
                    if current is not None:break
                    current=self.vision.text_button(fresh,label,cell)
                    if current is not None:break
            if current is None:
                current=finder(fresh)
                # Hover can cover this item and expose a different identical
                # potion elsewhere. Never switch item mid-confirmation.
                if hover_label and current is not None and (
                    abs(current.center[0]-box.center[0])>box.w//2 or
                    abs(current.center[1]-box.center[1])>box.h//2):
                    current=None
            if current is None:
                raise InterruptedError('Meslek düğmesi son kontrolde görünmedi; yeniden okunacak.')
            if before_submit:
                before_submit()
            return self.bot.pixel_to_desktop(current.center, fresh)
        self.bot.mouse.click(*self.bot.pixel_to_desktop(box.center, frame), before_click=guard)
        self.last_action = time.monotonic()
        self.bot.notice(message)
        return True

    def text(self, frame, label, message=None):
        return self.click(frame, lambda f: self.vision.text_button(f, label), message or f'{label} açılıyor.')

    def icon(self, frame, name, message):
        def find(f):
            if name=='menu-toggle':
                region=Box(0,0,int(f.shape[1]*.12),int(f.shape[0]*.25))
                hits=[]
                for variant in ('menu-toggle','menu-toggle-closed','menu-toggle-hover'):
                    hits=self.vision.matches(f,variant,region,threshold=.85)
                    if hits:break
            else:
                hits = self.vision.matches(f, name)
            return hits[0] if hits else None
        return self.click(frame, find, message)

    def close_auto(self, frame):
        def find(f):
            panel = self.vision.auto_panel(f)
            if panel is None:
                return None
            scale = panel.w / 742
            return Box(round(panel.x+panel.w-20*scale), panel.y, round(18*scale), round(18*scale))
        return self.click(frame, find, 'Meslek penceresi kapatılıyor.')

    def scroll_auto(self, frame, direction):
        panel = self.vision.auto_panel(frame)
        if panel is None:
            return False
        def guard():
            self.bot.control_guard()
            fresh = self.bot.detector.capture()
            current = self.vision.auto_panel(fresh)
            if self.bot.detector.check_bot_protection(fresh)[0] or current != panel:
                raise InterruptedError('Meslek penceresi değişti; kaydırma iptal edildi.')
        point = (panel.x+panel.w-42, panel.y+panel.h//2)
        self.bot.mouse.scroll(*self.bot.pixel_to_desktop(point, frame), direction, before_scroll=guard)
        self.last_action = time.monotonic()
        self.scans += 1
        return True

    def inventory_item(self, frame, name):
        region = self.vision.inventory(frame)
        if region is None:
            return None
        matches = self.vision.matches(frame, name, region)
        return min(matches, key=lambda b:(b.y, b.x)) if matches else None

    @staticmethod
    def badge_region(frame, box):
        """Yığın rozetini slottaki koyu dikdörtgenden bulur.

        Rozet ikon kutusunun alt-soluna, kısmen dışına taşar; eski sabit alt
        bant hem komşu slotun rakamını kapsıyordu hem ikonun karanlık
        kenarından gürültü alıyordu. Rozet kutusu koyu zeminden aranır.
        """
        if not box or frame is None:
            return None
        band = Box(max(0, box.x - 8), max(0, box.y + box.h - 12), box.w + 8, 20)
        crop = band.crop(frame)
        if crop.size == 0:
            return None
        dark = crop.astype(np.int16).mean(axis=2) < 130
        cols = np.flatnonzero(dark.mean(axis=0) > 0.35)
        rows = np.flatnonzero(dark.mean(axis=1) > 0.35)
        if cols.size and rows.size:
            return Box(band.x + int(cols[0]), band.y + int(rows[0]),
                       int(cols[-1] - cols[0] + 1), int(rows[-1] - rows[0] + 1))
        # Rozet yok (adet 1 olan eşya): bölge de yok sayılır ki slottaki
        # ikon gölgesi okunup uydurma bir adet sayısı çıkmasın.
        return None

    def stack_number(self, frame, box):
        """Quantity badge of one inventory slot, or None when unreadable."""
        region = self.badge_region(frame, box)
        if region is None:
            return None
        return self.vision.badge_number(frame, region)

    def badge_pixels(self, frame, box):
        """Rozetin ham pikselleri; rakam OCR'da okunamazsa kanıt olarak."""
        region = self.badge_region(frame, box)
        if region is None:
            return None
        crop = region.crop(frame)
        return crop.tobytes() if crop.size else None

    @staticmethod
    def badge_changed(before, after):
        """Rozet değiştiyse yığından bir adet tüketilmiştir.

        Farklı uzunluk, rozet kutusunun genişliğinin (rakam sayısının)
        değiştiği anlamına gelir; bu da tüketimdir.
        """
        if not before or not after:
            return False
        if len(before) != len(after):
            return True
        delta = np.abs(np.frombuffer(before, np.uint8).astype(np.int16) -
                       np.frombuffer(after, np.uint8).astype(np.int16))
        return float(delta.mean()) > 8

    def rod_equipped(self, frame):
        inventory = self.vision.inventory(frame)
        if inventory is None or inventory.x < 100:
            return False
        # Character equipment is left of the inventory, never inside the bag.
        region = Box(75, inventory.y, inventory.x-75, max(1, inventory.h))
        return bool(self.vision.matches(frame, 'rod', region, threshold=.85))

    def dismiss_alert(self, frame, hinted_reason=None):
        # ScreenDetector already OCRs modal text for most full-screen alerts.
        # Reuse that reason instead of starting a second, slower OCR pass; a
        # visual button match below still verifies the actual close input.
        alert = None if hinted_reason else self.vision.known_alert(frame)
        reason = alert[0] if alert else hinted_reason
        if reason in ('splinter', 'tool', 'energy', 'auto'):
            close = alert[1] if alert else None
            if reason in ('splinter', 'tool'):
                if not self.recovery_enabled:
                    return False
                if reason == 'splinter' and self.potion_attempted:
                    self.fail('İksir denemesinden sonra kıymık devam ediyor; ikinci iksir kullanılmadı.', frame)
                    return True
                self.request_recovery(reason)
            elif reason == 'energy' and self.energy_enabled:
                self.energy.spend_active = False
                self.energy.save()
                self.transition('AUTO_FINISH')
            elif reason == 'auto':
                self.bot.notice('Otomatik toplama uyarısı kapatılıyor; avlanma yeniden denenecek.')
            else:
                return False
            def find(f):
                current = None if hinted_reason else self.vision.known_alert(f)
                if current and current[0] == reason and current[1]:
                    return current[1]
                # Some browser captures contain the message text but the
                # button OCR is too small.  The supplied button template is a
                # safer fallback than clicking an arbitrary dialog location.
                hits = self.vision.matches(f, 'alert-ok') or self.vision.matches(f, 'alert-kapat')
                if hits:
                    return hits[0]
                if hinted_reason:
                    detected = self.vision.known_alert(f)
                    if detected and detected[0] == reason:
                        return detected[1]
                    # Sınıf gövde metninden kurulduysa şablon düğme
                    # eşleşmeyebilir ("Gerekli alete sahip değilsiniz!"
                    # uyarısında olduğu gibi). Aynı diyaloğun kırmızı başlık
                    # altındaki kapat düğmesi detector ile yeniden bulunur;
                    # boşsa tıklama gönderilmez. Detector merkezi (x, y)
                    # döndürür, tıklama yolu ise kutu bekler.
                    layout = self.bot.detector.detect_layout(f)
                    point = self.bot.detector.find_close_button(f, layout) if layout else None
                    if point:
                        return Box(point[0]-8, point[1]-8, 16, 16)
                return None
            if close is None:
                close = find(frame)
            if close is None:
                return False
            self.click(frame, lambda f: find(f), 'Tanınan oyun uyarısı kapatılıyor.')
            return True
        return False

    def handle(self, frame, obs, now):
        if not self.enabled or self.bot.args.dry_run:
            return False
        if obs.protection:
            return False
        panel = self.vision.auto_panel(frame) if self.energy_enabled or self.state != 'IDLE' else None
        confirmation=(self.vision.potion_confirmation(frame)
                      if self.state=='POTION_CONFIRM' else None)
        if self.state == 'IDLE' and panel and self.energy_enabled:
            self.transition('AUTO_READ')
        # Honour the same three-frame resume gate in inventory/automatic mode.
        # Focus loss or CAPTCHA cannot skip straight into a modal click.
        if self.bot.gate.latched:
            expected=panel or confirmation or obs.clear or obs.harvesting
            if not expected and self.state.startswith(('POTION','EQUIP','RETURN')):
                expected=self.vision.inventory(frame) is not None
            if not expected:return False
            if not self.bot.gate.update(True,now):return True
            self.bot.sound.stop_alarm_loop()
            self.since=now
            self.progress_at=now
        if confirmation:
            self.bot.phase='PROFESSION'
            return self.handle_inventory(frame)
        if obs.blocked:
            # OCR is best-effort here.  A missing/slow OCR result must fall back
            # to the normal screen-wait path, never terminate the fishing bot.
            try:
                hinted = recovery_reason(obs.blocked or '')
                if self.dismiss_alert(frame, hinted):
                    return True
            except Exception as exc:
                # StopRequested/InterruptedError are control-flow signals from
                # the shared mouse guard and must reach the main loop.
                if isinstance(exc, InterruptedError) or exc.__class__.__name__ == 'StopRequested':
                    raise
                self.bot.notice(f'Meslek uyarısı okunamadı; ekran bekleniyor ({type(exc).__name__}).')
            # The base detector quite correctly reports the map as missing
            # while the profession window or inventory is open.  Those modal
            # screens belong to this controller, so let the current profession
            # state continue instead of handing them to the fishing gate.  An
            # IDLE controller still waits on unknown screens as before.
            if self.state == 'IDLE':
                return False
            expected_modal = (
                self.state.endswith('_OPEN') or
                self.state in ('AUTO_OPEN', 'AUTO_CLOSE', 'RETURN') or
                self.vision.auto_panel(frame) is not None or
                self.vision.inventory(frame) is not None
            )
            if not expected_modal:
                return False
        if self.state == 'IDLE':
            reason = recovery_reason(obs.blocked or '')
            if reason and self.request_recovery(reason):
                return True
            if self.energy_enabled and self.bot.phase == 'SEARCH' and obs.clear and self.energy.needs_sync():
                self.request_sync()
            else:
                return False
        self.bot.phase = 'PROFESSION'
        if now - self.last_action < .8:
            return True
        if self.state != 'AUTO_WAIT' and now - self.since > max(90, self.auto_seconds + 45):
            self.fail(f'Meslek adımı tamamlanamadı: {self.state}.', frame)
            return True
        if self.state.startswith(('POTION', 'EQUIP')):
            return self.handle_inventory(frame)
        panel = panel or self.vision.auto_panel(frame)
        if self.state == 'AUTO_OPEN':
            if panel:
                self.transition('AUTO_READ')
            elif self.icon(frame, 'menu-entry', 'Otomatik toplama menüsü açılıyor.'):
                pass
            else:
                self.icon(frame, 'menu-toggle', 'Karakterin meslek menüsü açılıyor.')
        elif self.state in ('AUTO_READ', 'AUTO_VERIFY', 'AUTO_FINISH'):
            if panel is None:
                self.transition('AUTO_OPEN')
                return True
            active=self.vision.active_collection(frame,panel)
            if active:
                self.auto_seen=True
                self.auto_before=self.energy.value
                self.auto_started=now
                self.progress_at=now
                self.transition('AUTO_WAIT','Devam eden otomatik toplama izleniyor.')
                return True
            reading = self.vision.energy(frame, panel)
            if reading is None:
                # Four blind scrolls must not end the whole recovery: reopen
                # the profession window a bounded number of times first.
                scrolled = self.scroll_auto(frame, 'up')
                if scrolled and self.scans < 4:
                    return True
                if self.energy_reopens >= ENERGY_READ_REOPENS:
                    METRICS.bump('energy_read_failed')
                    self.fail('Meslek enerjisi okunamadı.', frame)
                    return True
                self.energy_reopens += 1
                METRICS.bump('energy_read_retry')
                self.transition('AUTO_CLOSE',
                                'Meslek enerjisi okunamadı; pencere yeniden açılacak.')
                return True
            if self.energy_reopens:
                METRICS.bump('energy_read_recovered')
            self.energy_reopens = 0
            self.energy.sync(*reading)
            if self.state == 'AUTO_VERIFY':
                if reading[0] != 0 and (self.auto_before is None or reading[0] >= self.auto_before):
                    self.fail('Otomatik toplamada enerji tüketimi doğrulanamadı; tekrar tıklanmadı.', frame)
                    return True
                self.auto_cycles += 1
                self.bot.cycles += 1
                self.bot.notice(f'{BY_ID[self.auto_fish_id].name}: otomatik toplama doğrulandı. Enerji {reading[0]}/{reading[1]}.')
            if self.state == 'AUTO_FINISH' or reading[0] == 0:
                self.energy.spend_active = False
                self.energy.save()
                self.transition('AUTO_CLOSE')
            elif self.energy.spend_active or reading[0] == reading[1]:
                if not self.energy.spend_active:
                    self.full_count=self.full_count+1 if self.full_reading==reading else 1
                    self.full_reading=reading
                    if self.full_count<2:return True
                self.energy.spend_active = True
                self.energy.save()
                self.transition('AUTO_FIND', f'Enerji {reading[0]}/{reading[1]}; {BY_ID[self.auto_fish_id].name} otomatik toplanacak.')
            else:
                self.full_reading=None
                self.full_count=0
                self.transition('AUTO_CLOSE', f'Enerji {reading[0]}/{reading[1]}; normal avlanmayla biriktirilecek.')
        elif self.state == 'AUTO_FIND':
            if panel is None:
                self.fail('Otomatik toplama penceresi kapandı.', frame)
                return True
            if self.vision.active_collection(frame,panel):
                self.auto_seen=True
                self.progress_at=now
                self.transition('AUTO_WAIT')
                return True
            def find(f):
                p = self.vision.auto_panel(f)
                if p is None:
                    return None
                rows = [r for r in self.vision.rows(f, p) if r.fish_id == self.auto_fish_id]
                return rows[0].button if rows else None
            rows = [r for r in self.vision.rows(frame, panel) if r.fish_id == self.auto_fish_id]
            if rows:
                self.auto_before = self.energy.value
                self.auto_seconds = rows[0].seconds
                if self.click(frame, find, f'{BY_ID[self.auto_fish_id].name}: otomatik toplama başlatılıyor.'):
                    self.auto_started = time.monotonic()
                    self.progress_at=self.auto_started
                    self.auto_seen=False
                    self.last_progress=None
                    self.transition('AUTO_WAIT')
            elif self.scans >= 6:
                self.fail(f'{BY_ID[self.auto_fish_id].name} için Topla düğmesi bulunamadı.', frame)
            else:
                self.scroll_auto(frame, 'down')
        elif self.state == 'AUTO_WAIT':
            # The game repeats gathering itself. Durdur is the authoritative
            # running signal; elapsed base_seconds alone never ends the job.
            active=self.vision.active_collection(frame,panel) if panel else None
            if active:
                self.auto_seen=True
                self.auto_progress,self.auto_total=active.progress,active.total
                if active.progress is not None:
                    if self.last_progress is not None and active.progress<self.last_progress:
                        self.auto_cycles+=1
                        self.bot.cycles+=1
                        self.bot.notice(f'{BY_ID[self.auto_fish_id].name}: otomatik döngü {self.auto_cycles}; toplama sürüyor.')
                    if active.progress != self.last_progress:self.progress_at=now
                    self.last_progress=active.progress
                if now-self.progress_at>max(90,self.auto_seconds*3):
                    self.fail('Otomatik toplama ilerlemesi uzun süredir değişmiyor.',frame)
            elif panel and now-self.auto_started>max(8,self.auto_seconds+2):
                rows=self.vision.rows(frame,panel)
                if rows:
                    self.transition('AUTO_VERIFY')
                    self.scroll_auto(frame,'up')
            if not active and now-self.progress_at>90 and self.state=='AUTO_WAIT':
                self.fail('Otomatik toplama durumu okunamadı.',frame)
        elif self.state == 'AUTO_CLOSE':
            if panel:
                self.close_auto(frame)
            else:
                self.transition('RETURN')
        elif self.state == 'RETURN':
            inventory = self.vision.inventory(frame)
            if inventory:
                self.click(frame, lambda f: self.vision.close_inventory(f),
                           'Çanta kapatılıyor.')
            elif panel:
                self.close_auto(frame)
            elif obs.clear:
                self.transition('IDLE', 'Avlan ekranı doğrulandı; enerji biriktirmeye devam ediliyor.')
                self.bot.reset_target(now, blacklist=False)
                self.bot.failures = 0
                self.bot.avoid.clear()
                self.bot.gate.block()
            else:
                self.click(frame,self.vision.hunt_button,'Üst menüden Avlan ekranına dönülüyor.')
        return True

    def stop_automatic(self):
        """Best-effort visible cancellation on F9/limit; never act off-screen."""
        try:
            return self._stop_automatic_visible()
        except Exception as exc:
            self.bot.notice(f'Otomatik toplamanın durduğu doğrulanamadı; oyundaki Durdur düğmesini kontrol edin ({exc}).')
            return False

    def _stop_automatic_visible(self):
        if not self.energy_enabled or self.bot.args.dry_run:return False
        if not self.bot.desktop.is_game_active():
            if self.state=='AUTO_WAIT':
                self.bot.notice('Bot durdu; oyun önde olmadığı için oyundaki otomatik toplamayı kendiniz durdurun.')
            return False
        frame=self.bot.detector.capture()
        if self.bot.detector.check_bot_protection(frame)[0]:return False
        panel=self.vision.auto_panel(frame)
        active=self.vision.active_collection(frame,panel) if panel else None
        if not active:return False
        # StopRequested has already been handled. Retain focus/cursor checks
        # and a fresh protection check for this one cancellation input.
        saved_guard=self.bot.mouse.guard
        def guard():
            fresh=self.bot.detector.capture()
            if self.bot.detector.check_bot_protection(fresh)[0]:
                raise InterruptedError('Koruma açık; otomatik toplama düğmesine dokunulmadı.')
            current_panel=self.vision.auto_panel(fresh)
            current=self.vision.active_collection(fresh,current_panel) if current_panel else None
            if not current:raise InterruptedError('Durdur düğmesi değişti.')
            return self.bot.pixel_to_desktop(current.button.center,fresh)
        try:
            self.bot.mouse.guard=lambda:None
            self.bot.mouse.click(*self.bot.pixel_to_desktop(active.button.center,frame),before_click=guard)
            for _ in range(3):
                time.sleep(.35)
                if not self.bot.desktop.is_game_active():break
                fresh=self.bot.detector.capture()
                panel=self.vision.auto_panel(fresh)
                if panel and not self.vision.active_collection(fresh,panel) and self.vision.rows(fresh,panel):
                    self.bot.notice('Oyundaki otomatik toplamanın durduğu doğrulandı.')
                    return True
            self.bot.notice('Durdur gönderildi; oyunun toplama durumunu kontrol edin.')
            return False
        finally:self.bot.mouse.guard=saved_guard

    def handle_inventory(self, frame):
        if self.vision.auto_panel(frame):
            self.close_auto(frame)
            return True
        inventory = self.vision.inventory(frame)
        if self.state.endswith('_OPEN'):
            if inventory:
                # A previous click can leave a browser tooltip over the exact
                # item we need.  Move away before the next screenshot so the
                # rod/potion template sees the complete icon.
                self.clear_hover(frame, inventory)
                self.transition(self.state.replace('_OPEN', '_TAB'))
            else:
                self.click(frame, self.vision.bag_button, 'Üst menüdeki karakter çantası açılıyor.')
        elif self.state == 'POTION_TAB':
            if self.potion_attempted:
                self.fail('Önceki iksir denemesi doğrulanmamış; yeni iksir kullanılmadı.', frame)
            elif self.inventory_item(frame, 'potion'):
                self.transition('POTION_USE')
            else:
                self.click(frame, lambda f: self.vision.inventory_tab(f, 'Efektler'),
                           'İksir sekmesi açılıyor.')
        elif self.state == 'POTION_USE':
            item = self.inventory_item(frame, 'potion')
            self.potion_count = len(self.vision.matches(frame, 'potion', inventory)) if inventory else 0
            # A stacked potion keeps its icon after one use, so the icon count
            # alone cannot prove consumption. Remember the slot and its badge.
            self.potion_box = item
            self.potion_stack = self.stack_number(frame, item)
            self.potion_badge_px = self.badge_pixels(frame, item)
            if not self.potion_count:
                self.fail('Çantada Orman Kalbi İksiri bulunamadı.', frame)
                return True
            # Persist BEFORE the consumable input. A crash must not consume twice.
            if self.click(frame, lambda f:self.inventory_item(f, 'potion'), 'Orman Kalbi İksiri kullanılıyor.',
                          hover_label='Kullan', before_submit=lambda:self.record_potion(True,'opened')):
                self.transition('POTION_CONFIRM')
                self.clear_hover(frame, inventory)
        elif self.state == 'POTION_CONFIRM':
            confirmation=self.vision.potion_confirmation(frame)
            if confirmation:
                if not self.potion_applied:
                    self.click(frame,self.vision.potion_confirmation,'İksir için Uygula onayı veriliyor.',
                               before_submit=lambda:self.record_potion(True,'submitted'))
                elif time.monotonic()-self.since>20:
                    self.fail('İksir onayı kapanmadı; ikinci kez uygulanmadı.',frame)
                return True
            if not inventory:
                # Oyun onay kapandıktan sonra çantayı kapatabilir. Kanıt ancak
                # çanta okunabilirken toplanabilir; kanıt penceresi boyunca
                # çanta yeniden açılır, açılmazsa eski güvenlik duraklatması.
                if time.monotonic() - self.since > POTION_VERIFY_SECONDS:
                    self.fail('İksirin kullanıldığı doğrulanamadı; ikinci iksir kullanılmadı.', frame)
                    return True
                if time.monotonic() - self.last_action > 1.0:
                    self.click(frame, self.vision.bag_button,
                               'Doğrulama için çanta yeniden açılıyor.')
                return True
            count = len(self.vision.matches(frame, 'potion', inventory)) if inventory else None
            if count is not None:
                self.potion_reads += 1
            consumed = False
            evidence = None
            if count is not None and self.potion_count is not None and count < self.potion_count:
                consumed, evidence = True, 'sayı'
            elif self.potion_box is not None:
                stack = self.stack_number(frame, self.potion_box)
                if stack is not None and self.potion_stack is not None and stack < self.potion_stack:
                    METRICS.bump('potion_evidence_stack')
                    consumed, evidence = True, 'rozet'
                elif self.badge_changed(self.potion_badge_px,
                                        self.badge_pixels(frame, self.potion_box)):
                    # Tesseract bu 8 piksel rakamı her karede okuyamayabilir;
                    # rozetin kendisi değiştiyse yığından bir adet gitmiştir.
                    METRICS.bump('potion_evidence_pixels')
                    consumed, evidence = True, 'rozet pikseli'
            elapsed = time.monotonic() - self.since
            if consumed and self.potion_applied:
                self.recoveries += 1
                self.record_potion(False)
                self.transition('EQUIP_TAB', f'İksir kullanımı doğrulandı ({evidence}); olta yeniden takılıyor.')
            elif (self.potion_applied and elapsed > POTION_ACCEPT_SECONDS and self.potion_reads
                    and inventory and self.vision.known_alert(frame) is None):
                # Onay penceresi kapandı, çanta okunuyor ve ekranda uyarı yok:
                # oyun iksiri tüketmiştir. Kanıt toplanamasa bile devam edilir;
                # yoksa bot burada durup kullanıcının F8 ile sürdürmesini beklerdi.
                METRICS.bump('potion_evidence_dialog')
                self.recoveries += 1
                self.record_potion(False)
                self.transition('EQUIP_TAB', 'İksir onayı kapandı; tüketim kabul edildi, olta yeniden takılıyor.')
            elif elapsed > POTION_VERIFY_SECONDS and (
                    self.potion_reads or elapsed > POTION_VERIFY_SECONDS * 2):
                self.fail('İksirin kullanıldığı doğrulanamadı; ikinci iksir kullanılmadı.', frame)
        elif self.state == 'EQUIP_TAB':
            if self.rod_equipped(frame):
                self.transition(self.after_equip, 'Olta karakterin üzerinde doğrulandı.')
            elif inventory is None:
                # İksirden sonra oyun çantayı kapatmış olabilir; olmadan ne
                # olta ne sekme bulunur, bot burada sonsuza kadar dönerdi.
                if time.monotonic() - self.last_action > 1.0:
                    self.bag_reopens += 1
                    if self.bag_reopens > 6:
                        self.fail('Çanta açılamadı; olta takılamadı.', frame)
                    else:
                        self.click(frame, self.vision.bag_button, 'Olta takmak için çanta açılıyor.')
            elif self.inventory_item(frame, 'rod'):
                self.transition('EQUIP_USE')
            else:
                self.click(frame, lambda f: self.vision.inventory_tab(f, 'Eşyalar'),
                           'Eşya sekmesi açılıyor.')
        elif self.state == 'EQUIP_USE':
            if self.click(frame, lambda f:self.inventory_item(f, 'rod'), 'Çantadaki olta takılıyor.', hover_label='Giymek'):
                self.transition('EQUIP_CONFIRM')
                self.clear_hover(frame, inventory)
        elif self.state == 'EQUIP_CONFIRM':
            if self.rod_equipped(frame):
                self.transition(self.after_equip, 'Olta takıldı; meslek döngüsüne dönülüyor.')
            elif time.monotonic() - self.since > 12:
                self.fail('Oltanın takıldığı doğrulanamadı.', frame)
        return True

    def clear_hover(self, frame, inventory):
        if inventory:
            self.bot.mouse.move_to(*self.bot.pixel_to_desktop((inventory.x+90, inventory.y-10), frame))
