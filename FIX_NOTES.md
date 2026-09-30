# Hareketli hedef düzeltmesi

Bu sürümde son tıklama güvenliği kaldırılmadı; hareketli balık için yeniden hedefleme yapacak şekilde değiştirildi.

- İmleç ilk hedefe giderken balık hareket ederse son ekran kontrolü aynı renkli balığı önceki konumunun yakınında yeniden bulur.
- Güncel merkez bulunduğunda fare kısa bir düzeltme hareketi yapar ve yeni merkeze tıklar.
- Düzeltmeden sonra ikinci bir ekran görüntüsü alınmaz; böylece aynı yarış koşulu tekrar oluşturulmaz.
- Hough halka algılaması animasyonun bir karesinde hedefi kaçırırsa küçük bir lokal renk/su bölgesi fallback'i kullanılır.
- Güvenlik/freshness kontrolü geçici olarak başarısız olursa hedef artık 120 saniyelik `avoid` listesine eklenmez.
- Yanlış tür, seçim zaman aşımı ve toplamanın başlamaması gibi gerçek başarısızlıklar mevcut blacklist davranışını korur.
- `pytest.ini` ile `backups`, `.venv`, `runtime` ve cache klasörleri test keşfinden çıkarıldı.

Yeni yeniden-yakalama mesafesi `config.py` içindeki `TARGET_REACQUIRE_DISTANCE = 48.0` ile ayarlanır. Bu değer bilinçli olarak sınırlıdır; daha uzaktaki aynı renkli başka bir balığın yanlışlıkla hedeflenmesini öncelikle engeller.

## v2 - Ay Sazanı / gri renk düzeltmesi
- `Ay Sazanı` katalogda zaten `beyaz` (Beyaz/Gri) renk grubundaydı.
- Renge göre seçimde OCR artık kısa balık adlarında gereksiz yere katı davranmıyor.
- `Ay Sazan`, `Ay Sazan Balığı`, `Ay Sazani Baligi` OCR varyantları eklendi.
- Normal isim çözümü başarısız olursa yalnızca seçili renk grubundaki türler arasında temkinli ikinci çözümleme yapılıyor.
- Belirsiz `Sazan` gibi tek kelimelik sonuçlar yine kabul edilmiyor.
- Gri modda `Ay Sazanı` ve `Felionlu Çamça` için ayrı test eklendi.
- Çekirdek test sonucu: 70/70 geçti.

## v3 - Meslek döngüsü ve eski avlanma akışı
- Meslek denetleyicisi başlangıçta çantaya dokunmuyor; enerji veya kıymık seçeneği etkin olsa bile eski Avlan döngüsü hemen çalışıyor.
- Yavaş/bozuk ek OCR artık botu düşürmüyor. Çanta, sağ araç çubuğundaki görsel Çanta düğmesiyle; sekmeler ve `Geri dön` yerel envanter geometrisiyle doğrulanıyor.
- İmleç göreli hareketi hedefe ulaşamazsa işlem güvenli biçimde iptal edilip taze ekranla yeniden deneniyor; bot `RuntimeError` ile kapanmıyor.
- Otomatik toplama sırasında çıkan elle kaynak toplama uyarısı kapatılıp avlanma yeniden deneniyor.
- Doğrulama: 103 test geçti; `./run.sh --doctor` bağımlılıkları ve `ydotoold` soketini doğruladı.

## v4 - Ölçüm, güven ve yakalama (Faz 0-5)

Öncelik sırası otonomi, güvenilirlik, hız, CPU. Bu sürümde davranış değişikliği değil, gözlem ve maliyet azaltma var; tıklama/kaydırma yolları aynı kaldı.

- **Faz 0 (ölçüm):** `metrics.py` sayaç ve zaman aralıkları (`span`, `bump`, `snapshot`, `save`) eklendi; `runtime/metrics.json` beş saniyede bir yazılır. `bench.py` çevrimdışı temel ölçüm, `main.py` `--doctor` bağımlılık listesine Xlib satırını ekledi.
- **Faz 1 (güven):** `block()` aynı bekleme içinde ikinci kez çağrılsa bile ikinci kez beklemez; geçici karelerde `TRANSIENT_BLOCK_FRAMES = 3` ve `RESUME_FAST_SECONDS = 1.2` uygulanır. Enerji okunamazsa iki kez kapat-aç (`ENERGY_READ_REOPENS`), iksir kullanımı `POTION_VERIFY_SECONDS = 20` boyunca doğrulanana kadar ikinci iksir gönderilmez.
- **Faz 2 (güven):** `fresh_guard` her çağrıda `revalidate()` ile ekranı yeniden doğrular; `REACQUIRE_ATTEMPTS = 2` ve yeniden-yakalama gecikmesi `REACQUIRE_RETRY_DELAY` ile sınırlıdır. Yanlış-pozitif eşikleri korundu. Meslek OCR önbelleği içerik özetine göre (salt süre yerine) yenilenir.
- **Faz 3 (hız):** Koruma başlığı iki aşamalı oldu (`PROTECTION_FAST_SCALE = 0.5`, `PROTECTION_FAST_REJECT = 0.62` — değerler sonradan 0.4 / 0.85'e kalibre edildi); `check_bot_protection` çift çağrısı kaldırıldı. Panel taraması `AUTO_PANEL_PROBE_INTERVAL = 2.0` ile sınırlı.
- **Faz 4-A:** Konsol/çerçeve optimizasyonu ölçüldü, getirisi düşük bulundu ve uygulanmadı.
- **Faz 4-C (hız):** Yeni `x11grab.py` ile Chromium penceresi X11 üzerinden doğrudan yakalanır (`X11Grabber`). `screen_detector.capture()` önce X11'i dener, olmazsa spectacle'a düşer; `capture_rect` ve `desktop_scale` sayesinde koordinat dönüşümü yakalama alanına göre ölçeklenir. `python-xlib` `requirements.txt` ve `--doctor` listesine eklendi.
- **Faz 5 (disk):** `bot.log` `RotatingFileHandler` ile 2 MiB / 3 yedek sınırına takıldı; `gui.py` konsolu her başlatmadan önce aynı kuralla döndürür (`LOG_MAX_BYTES`, `LOG_BACKUPS`).
- **Otomatik panel kısayolu:** `profession_vision._title_likely` yarı çözünürlükte aynı beş ölçekle bakıp temiz haritayı hemen eleyer; eşik üstü hiçbir karar vermez, tam eşleşmeye bırakır. 19 fixture'da sonuç değişmedi, gerçek panel hiçbir ölçekte/beyazlıkta kaçmadı.
- **Koruma yeniden-yakalama (teşhis + ayar):** yeni `probe_reacquire.py` tıklamadan, gerçek koruma yolunu taklit ederek halkayı izledi. Koruma anında halka çoğunlukla hiç görünmüyor, 0,27–1,4 sn sonra **aynı yerde** geri geliyor; merkez kayması (aynı renkli halkanın kabul yarıçapı dışında durması) hiç görülmedi. Eski 0,12 sn'lik ikinci deneme bu boşluğun içinde kaldığı için boşuna dönüyordu. `REACQUIRE_ATTEMPTS` 2 → 3, `REACQUIRE_RETRY_DELAY` 0,12 → 0,30 yapıldı; aynı koşulda koruma hata oranı %8,1'den %4,3'e indi.
- **Canlı doğrulama:** gerçek oyunda 600 sn koşu (beyaz/gri, kaydırma kapalı): 44 halka denemesinde **0 koruma iptali** (tarihsel %17,3'e karşı), 4 yeniden denemenin hepsi kurtardı, 24 tamamlanan döngü, 0 hata. Oyun CPU yükü altında görüntü adımları ~2× yavaşlıyor; `protection_template` duvar süresinin %13,6'sı ile en büyük tek maliyet (aşağıdaki madde ile azaltıldı).
- **Koruma hızlı aşama kalibrasyonu (hız):** `PROTECTION_FAST_SCALE` 0.5 → 0.4, `PROTECTION_FAST_REJECT` 0.62 → 0.85. Ölçüm: temiz ekran 0.54–0.755, koruma kareleri ≥0.969; 0.3 ölçekte ayrım kayboluyor. Eşik 0.75 denenip reddedildi çünkü canlı negatifler 0,742–0,750'ye çıkıp tam geçişe düşüyor ve o kare 500+ ms'ye mal oluyordu. Çift taraflı CPU ölçümü (aynı kare, 15 çift) 76,5 → 50,0 ms (**1,53×**), canlı ortalama 61,0 → 40,2 ms, kısayol oranı %100. Ölçüm tuzağı: ölçek modül genelinden okunduğu için iki koşullu A/B'de küresel değişken her çağrıdan önce kurulmalı, yoksa iki koşul da son ölçekle çalışır.

Doğrulama: **177 test geçti.** Ayrıntı ve canlı ölçüm `VERIFICATION.md` içinde.
- **Hız: maske/Hough/BGRA (23:39-23:50):** `_fish_color_masks(crop, colors)` seçili rengi tek başına hesaplıyor (12,1 → 2,5 ms); kabul kriterindeki `30` `FISH_MASK_MIN_PIXELS` sabitine taşındı ve maske o değerin altındaysa `HoughCircles` hiç çalışmıyor (49,3 ms kazanç, sonuç elenmek zorunda olduğu için birebir aynı); `x11grab.bgra_to_rgb` artık `cv2.cvtColor(BGRA2RGB)` (6,41 → 0,51 ms, piksel eşitliği doğrulandı). Test 177 geçti; canlıda tik/sn 4,25 → 5,16, `capture` 25,2 → 12,6 ms.
- **OCR hız (29 Eylül):** tesseract çağrısına `--oem 1` (sadece LSTM) eklendi — balık adı 320 → ~190 ms, koruma metni 846 → 206 ms; 15 kırpıda anlam metni aynı kaldı (test 177 geçti). `ocr(..., label=...)` ile çağrıcı başına sayaç eklendi (`ocr_name` vb.). Ölçek 1→4 süreyi etkilemediği için sadece doğruluk kaldıracı olarak kullanılmaya devam ediyor.
- **OCR önbellek taşması düzeltmesi (29 Eylül 00:16):** `screen_detector.ocr` önbelleği 64 girişe dolunca `dict.popitem(last=False)` `TypeError` veriyor ve bot "Bot hata nedeniyle durdu" ile kapanıyordu. Tetikleyici: uyarı/panel ekranında her tikte koruma-OCR, animasyon nedeniyle her kare farklı önbellek girdisi (`ocr_calls: 65`, `ocr_protection: 58`). `self._ocr_cache.pop(next(iter(self._ocr_cache)))` ile insertion-order (recency) budama yapıldı; `test_ocr_cache_overflow_is_pruned_without_crashing` eklendi.
- **Uyarı penceresini botun kapatması (29 Eylül 00:44):** `_panels` "Oyun uyarısı" dalı `Observation.close_button` döndürüyor; `ScreenDetector.find_close_button()` başlık çubuğunun altındaki kırmızı bileşenle (121×17 px) düğmeyi buluyor, gövde satırı (11 px) 14 px eşiğiyle eleniyor. `FishingBot.dismiss_warning()` 1 sn aralıkla, tıklama öncesi koruma + düğme yeniden doğrulamasıyla tıklıyor; 60 sn'de 6 denemede pes edip alarm veriyor, `dry_run` tıklamıyor, düğme yoksa kör tıklama yapmıyor. Ustalık uyarısı kasıtlı olarak kapatılmıyor. Canlı: eski kod 18 dakika kilitli kalıyordu, yeni kod ilk karede kapattı (`warning_close: 1`, `frames_blocked: 1`) ve 40 sn'de 4 döngü tamamladı.

- **Kara listenin kapsamı (29 Eylül):** `reset_target` yalnızca `self.target`'ı karalıyordu; oysa tıklama koruması reacquire ile hedefi başka bir halkaya kaydırabiliyor ve kara listeye o nokta giriyordu — aday listesindeki ilk halka hiç elenmiyordu (canlıda aynı yere üç üst üste tıklama görüldü). `target_origin` ile seçilen ilk halka da ekleniyor, ikisi de 24 px yarıçapında 120 sn boyunca eleniyor.

Doğrulama: **186 test geçti.** Ayrıntı `VERIFICATION.md` içinde.

## v5 - Olta tanımama ve KWin yardımcı güvenilirliği (29 Eylül)

- **Olta şablonları düzeltildi.** Eşyalar sekmesindeki kırmızı zeminli Efsanevi Olta artık `assets/profession-rod_2.png` (58×56, konum 830,275) ile tanınıyor; mor zeminli ikinci olta `profession-rod_3.png` (56×56, 889,275); çantada **takılı** olan olta bebek yuvasında `profession-rod_doll.png` (58×56, 106,349). `profession_vision.matches()` artık `profession-{ad}_*.png` varyantlarının tamamını dener, bu yüzden tek bir yanlış "olta" şablonu tüm akışı kilitlemiyor.
- **Varyantlar birbirinden ayrılıyor (canlı ölçümler):** kırmızı ↔ mor olta çapraz skoru 0,189 (aynı şablon kullanılamaz); bebek yuvasındaki olta bebek şablonuyla **1,000**, kırmızı olta şablonuyla 0,852 (0,89 eşiğinin altında → bebek şablonu şart), kırmızı olta baltada 0,028, ok/balta hücrelerinde yanlış pozitif yok. Kare genelinde hatalar: `[(889,275,56,56),(106,349,58,56)]` — aranan kırmızı olta `(830,275)` çantada.
- **`rod_equipped` artık doğru.** Bebek şablonu sayesinde "olta takılı" ile "olta çantada" ayrılıyor; `tests/fixtures/inventory-rod-equipped.png` yeni fixture, `inventory-rod-new.png` beklentisi `[(829,20,56,56)]` olarak güncellendi.
- **Olta takma akışı yalnızca `--auto-splinter` ile tetiklenir** (`profession.request_recovery`); canlı uçtan uca denemede bayrak şart.
- **KWin yardımcı başlatma güvenilir hale getirildi.** `Desktop._start_helper()`: betik yüklenip de ilk rapor gelmezse yardımcıyı boşaltıp yeniden yüklüyor (`REPORT_ATTEMPTS = 3`, `REPORT_TIMEOUT = 4.0`); yükleme hatası da yeniden denenir ve sonunda `RuntimeError` fırlatılır. Sinyalle ölen süreçlerin KWin'de bırakmış olduğu yardımcılıklar `runtime/kwin_scripts.json` kaydından sonraki açılışta `unloadScript` ile temizleniyor (kendi pid'imiz elenmez). `close()` içindeki boşaltma sessizleştirildi; KWin ayaktaysa ad kaybı botun kapanışını çökertmiyor.
- **Tanılama sonuçları (29 Eylül):** KWin → Python `callDBus` yolu çalışıyor; `loadScript()` döndürdüğü id birebir `/Scripting/Script{id}`; betik **kendiliğinden başlamıyor**, `run()` şart; temp JS dosyası `run()` döndükten sonra silinebilir (KWin dosyayı senkron okur — dosya yarışı elendi); imleç her hareketinde rapor tekrar gelir. Tanılama betikleri `dbus.service.BusName(...)` nesnesine referans tutmadığı için `__del__` → `release_name` ile adı anında bırakıp çağrıları kaybediyordu; `Desktop` bunu `self.bus_name` ile zaten tutuyor. KWin'de isimleri listelenemeyen 5–6 artakalan yardımcı var (adları tahmin edilemedi, zararsız; `unloadScript` ile bilinenleri temizlendi).

Doğrulama: **200 test geçti** (194 → 200; yeniden deneme/temizlik için 6 yeni `test_desktop` testi). Ayrıntı `VERIFICATION.md` içinde.

## v6 - Kurtarma daima açık ve deniz yönüne göre kaydırma (29 Eylül)

- **Kıymık/olta kurtarması varsayılan olarak açık.** Kullanıcı kararı: kıymık (battığında) olta çıktığında bot **önce Orman Kalbi İksiri içmeli, sonra oltayı takmalı** ve bu yol hep açık kalmalı. `main.parse_args` `auto_splinter=True` ile başlar, `--no-auto-splinter` kapatır; `ProfessionController.recovery_enabled` bayrak hiç verilmediğinde de `True` olur (GUI/CLI bayraksız başlatmalar da kurtarmayı alır). Panel kutucuğu yalnızca işareti kaldırıldığında `--no-auto-splinter` gönderiyor; `runtime/preferences.json` içindeki eski `auto_splinter: false` değeri `true` yapıldı.
- **Gereksiz dikey kaydırma durduruldu.** Bazı haritalarda deniz genişliği boyunca bir şerittir; aşağı/yukarı kaydırmak suyu görüşten çıkarır (canlı oturumda **319 kaydırma** ölçüldü). `ScreenDetector.sea_extends_vertically()` kaydırmadan önce görünür suyu ölçer: bir satır ancak **%20'si** suysa deniz satırı sayılır (kıyı köpüğü ve dağınık su pikselleri şeride sayılmaz), en uzun **sürekli** deniz şeridi görünür alanın **%45'inden** kısaysa dikey kaydırma yapılmaz ve bot görünür alanı taramaya devam eder (`SEA_DENSE = 0.20`, `SEA_BAND_MAX = 0.45`). Su okunamazsa ya da hiç deniz satırı bulunamazsa (ör. çok dar bir nehir) mevcut davranış korunur.
- **Canlı ölçüm (o anki harita):** 1497×520 görünür alanda deniz satırı **106/520**, hepsi üstte bir şerit halinde → kaydırma **engellendi**. Kare `.tmp/sea_crop.png` olarak kaydedildi ve görsel olarak doğrulandı: su şeridi sol üstte, halkalar onun içinde, gerisi kara. İlk sürümde uçlardaki dağınık su pikselleri şeridi olduğundan şerit 430/520 sanılıyordu; sürekli-şerit ölçümü bu hatayı kapattı.

Doğrulama: **210 test geçti** (204 → 210; deniz yönü 4, kurtarma1, panel1 yeni test). Ayrıntı `VERIFICATION.md` içinde.

## v7 - Yaratık avı eşleşme düzeltmesi ve panelde av modu (30 Eylül)

- **Saldırıyı engelleyen OCR gürültüsü düzeltildi.** Seçili yaratığın üst bilgi kutusundaki ⓘ simgesi OCR'e `od` diye karışıyordu; `krogan od` okuması 0,82 benzerlik eşiğini (0,80) geçemediği için bot seçtiği **her** yaratığı "Ad örtüşmüyor" diyerek atlıyordu. Yeni `hunt_catalog.name_score()` metnin ardışık kelime dizilerini de karşılaştırır; eşitlikte daha özgül (uzun) ad kazanır, yabancı adlar hâlâ elenir.
- **`--creatures all` modunda okunmayan etiket döngüsü kapandı.** Etiketi okunamayan hedefin adı üst bilgi kutusundan hedefe işlenir; tıkla-atla döngüsü yerine saldırı onaylanır.
- **Panele "Yaratık avı (Avlan) modu" eklendi.** Av kartında Tüm yaratıklar / bilinen türler ve en az-en çok seviye seçilir; mod açıkken balıkçılık kontrolleri kilitlenir, döngü/dakika sınırı ve kaydırma ortaktır. Tercihler `runtime/preferences.json`'da kalıcıdır; durum kartları av modunda dövüş metinlerine döner.
- Doğrulama: **250 test geçti** (2 atlanan), `--doctor` yeşil, `--hunt --dry-run` girdisiz açılıp temiz kapandı. Av modunun ilk canlı dövüş denemesi yapılmadı; önce `--hunt --dry-run` önerilir. Ayrıntı `VERIFICATION.md` içinde.

## v8 - Temiz durdurma, dövüş içi eylemler ve birleşik panel (30 Eylül)

- **Ctrl+C / F9 artık hep temiz kapanıyor.** İki kök neden çözüldü: tesseract kendi
  oturumunda çalışıyor (terminal sinyali onu öldürmüyor) ve `StopRequested` tek sınıf
  olarak `state.py`'ye taşındı — `main.py __main__` + `from main import` kopya sınıfı
  yüzünden av modunda durma isteği "Bot hata nedeniyle durdu" süsü veriyordu.
- **Dövüş içi eylemler.** Dövüş başlayınca bot bir kez: provokasyonu açıp çağırma
  çubuğundan slot sırasına göre istenen adetlerde yaratık çağırır, bineği çağırır,
  otomatik savaşı açar. Üç düğme şablonla bulunur (iki gerçek çekimde 0,94-1,0 skor);
  çağırma sayacı piksel farkıyla doğrulanır (jeton bitince slotta durur). CLI:
  `--auto-battle --mount --provoke --provoke-counts 3,2`.
- **Birleşik panel.** ÇALIŞMA MODU: Meslek / Avlan radyoları; Avlan'da özel yaratık
  ekleme (her haritada farklı türler için), seviye sınırları ve üç dövüş seçeneği
  kutusu + slot adetleri. Mod ve tüm av tercihleri kalıcı.
- **Bozuk `.venv` onarımı:** sistem Python güncellemesi venv bağını koparmıştı;
  `./setup.sh` ile yeniden kuruldu.
- Doğrulama: **261 test geçti** (2 atlanan); canlıda iki dövüş uçtan uca tamamlandı
  (seçim, iki kez ad doğrulaması, "Ava" dönüşü). Dövüş içi eylemlerin canlı denemesi
  ilk koşuda yapılacak. Ayrıntı `VERIFICATION.md` içinde.
