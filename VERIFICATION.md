# Doğrulama — 23 Eylül 2026

Güncel çalışma kopyası: `/home/meliheeren/Masaüstü/dwar_fishing_bot`.

## Sonuçlar

- Son balık seçimi ve isim okuma düzeltmesinden sonra `.venv/bin/python -m pytest -q`: **140 geçti** (25,06 saniye).
- `./run.sh --doctor`: Python paketleri, ekran yakalama, OCR, fare aracı ve ydotoold soketi uygun.
- Alarm denemesi ses oynatıcıya başarıyla gönderildi.
- Panel görüntüsü incelendi; çalışma düğmeleri ayar kaydırmasından bağımsız, sürekli görünür.

## Gerçek oyunda denenen akış

13:52–13:53 aralığında ekran ve gerçek işletim sistemi faresiyle:

1. Meslek enerjisi 99/100 okundu; pencere kapatıldı.
2. Hareketli beyaz halka seçildi; Felionlu Çamça adı doğrulandı ve normal toplama tamamlandı. Ölçüm 8,47 saniye.
3. Meslek menüsü tekrar açıldı; 100/100 enerji doğrulandı.
4. Liste kaydırıldı, seçili Elmas Som Balığı için otomatik toplama başlatıldı.
5. İlerleme sayacından iki otomatik döngü gözlendi; çalışan toplamaya yeniden Topla gönderilmedi.
6. Üç toplam döngü sınırında Durdur gönderildi. Ayrı ekran okumasında çalışan düğme kaybolmuş, Topla düğmeleri yeniden etkinleşmişti.

13:57–13:58 aralığındaki ikinci deneme eski başlatma yoluyla yapıldı. Karakter menüsü kapalıyken açıldı, enerji yeniden 97/100 okundu, yarım kalan enerji harcama aşaması sürdürüldü. Bir otomatik döngü sonrasında yeni durdurma doğrulaması oyundaki toplamayı durdurduğunu kaydetti.

## Test kapsamı ve sınırları

Enerjinin sıfıra inmesinden sonra pencereyi kapatma ve normal avlanmaya dönüş otomatik durum geçişi testinde doğrulandı. Yaklaşık 100 otomatik döngü gerektiren tam enerji tüketimi bu canlı denemede beklenmedi.

Koruma algılama ve tıklama öncesi koruma çıkması kayıtlı görüntü ve davranış testleriyle kontrol edildi. Bu denemede canlı koruma ekranı çıkmadı; hiçbir doğrulama çözülmedi.

Görsel otomasyon oyunun arayüzüne, açık pencereye ve ekran ölçeğine bağlıdır. Son kontroller tek ekran 1920×1080, KDE Wayland ve Chrome ile yapıldı. F8 bot girdilerini duraklatır; daha önce başlatılmış oyun işlemi sürebilir. F9 görünür otomatik toplama penceresindeki Durdur düğmesine erişebilirse oyundaki toplamayı da durdurur.

Önceki kaynak dosyalarının yedeği: `backups/20260922-before-completion/`.

## Antigravity sonrası inceleme

Son değişikliklerin Masaüstü kopyasına yapıldığı doğrulandı. Eski scratch klasörünün başlatıcısı bu kopyaya yönlendiriyor. Değişiklik öncesi kurtarma kodu ve testler `backups/20260922-antigravity-review/` içinde saklandı.

- Gerçek çanta ve Avlan düğmelerinin normal/üzerine gelinmiş görünümleri eklendi. Görsel doğrulama başarısızken yalnızca imleç konumuna güvenen alternatif kaldırıldı.
- `runtime/last-pause.png` gerçek bir iksir **onay** penceresiydi. Kıymık hatası olarak sınıflandırılması düzeltildi; Kullanmak → Uygula → tüketimi doğrula → olta → Avlan akışı ayrıldı.
- Sadece alet eksikliği bildirildiğinde iksir kullanılmaz; önce olta denenir. Takma sırasında kıymık uyarısı çıkarsa iksir aşamasına geçilir.
- Gönderilen iksir onayı kalıcı kayda alınır, yeniden başlatmada tekrar gönderilmez. Doğrulanan tüketim kaydı temizler.
- Beyaz halkalarda mezar taşlarını eleyen daha sıkı su kontrolü eklendi. Diğer renklerin önceki hedefleri regresyon testleriyle korundu.
- OCR zaman aşımı tıklamayı iptal edip yeni görüntüyle tekrar denemeye döner. Ekran yakalama istemcileri tek sıra halinde çalışır.

Canlı oyunda üstteki gerçek çanta açıldı ve takılı olta doğrulandı. İksirin Kullanmak düğmesiyle açılan onayda Uygula tespit edildi, yanlış hata oluşmadı. Kıymık bulunmadığı için test İptal ile sonlandırıldı: öncesinde ve sonrasında **3 iksir** vardı. Bu oturumda yeni bir kıymık oluşturulmadı; gerçek tüketim ve yeniden takma, görsel fixture ve durum geçişi testleriyle doğrulandı.

İncelenen mevcut günlükte 16:42–16:49 arasında 25 enerji tüketilerek 0'a inildiği, Avlan'a dönülüp Felionlu Çamça toplandığı ve enerjinin 1'e çıktığı kayıtlıdır. Bu, önceki çalışmanın günlüğünden doğrulandı.

22 Eylül 19:12–19:15 denemesinde başlangıçta nehir görünmezken 17 kaydırmayla balık bulundu; iki toplama tamamlandı, üçüncü toplama süre sınırında sürüyordu. 19:24–19:27 tarihli sonraki günlükte beş deneme ve beş tamamlanan toplama bulunuyor. 23 Eylül başlangıcında Brave penceresi ve yer değiştiren harita sınırları doğru algılandı. Sistem bağımlılık kontrolü yeniden geçti.

23 Eylül 02:39–02:41 son canlı denemesi Brave Origin'de yapıldı. Meslek enerjisi 22/100 yeniden okundu; iki Felionlu Çamça ve bir Ay Sazanı döngüsü tamamlandı. Hareket eden hedef yeniden tarandı. Sonuç: **3 deneme, 3 tamamlanan döngü**, çalışma sınırında temiz çıkış. Kontrol paneli hazır bırakıldı; arka planda toplama işçisi çalışmıyor.

## Balık seçimi regresyonu — 23 Eylül 02:49–03:04

### Sorunun gerçek oyunda yeniden üretilmesi

02:49–02:50 başlangıç denemesinde gerçek fare girdileri kaydedildi. Küçük halka merkezi farkları 2,5 piksel sınırını aştığında son kontrol fareyi tekrar hareket ettiriyor; üç düzeltmeden sonra tıklamayı iptal ediyordu. Kısmen görünen halka yerine yakınındaki tam halka seçildiğinde hedef ileri geri değişiyordu. Ayrıca ana döngüdeki her geçici okuma kesintisi seçimi ve devam eden toplama durumunu sıfırlıyordu.

### Düzeltmeler

- Halka büyüklüğüne göre sınırlı bir iç alan kabul ediliyor; küçük animasyon farkları tıklamayı iptal etmiyor. Kullanıcının fareyi taşımasına ilişkin 2,5 piksel kontrolü korunuyor.
- Yakındaki başka bir tam halka seçilmeden önce mevcut hedefin yerel halka parçaları karşılaştırılıyor. Ardışık kontroller en son doğrulanan konumu izliyor.
- Geçici ekran/OCR hatası seçilmiş balığı veya izlenen toplamayı düşürmüyor. Seçim doğrulaması üç kesintide başarısızsa yeniden arama yapılıyor; okunamayan isim için süre sınırı var.
- Canlı görüntüdeki `aysazam@` okuması Ay Sazanı ile eşleştirildi. İsim modunda yalnızca bu tür seçiliyse kabul ediliyor; eşleşme eşiği genel olarak gevşetilmedi.

### Son doğrulama koşuları

| Koşu | Ayarlar | Başlatılan / tamamlanan |
|---|---|---:|
| 02:52:53–02:58:24 | Beyaz/gri; enerji döngüsü, Elmas Som ve kıymık kurtarma açık | 12 / 12 |
| 02:59:55–03:02:13 | Yalnızca Felionlu Çamça; duraklat/devam | 4 / 4 |
| 03:03:23–03:04:21 | Yalnızca Ay Sazanı; son isim düzeltmesi | 3 / 3 |

Toplam **19 doğrulanan toplama**. İlk koşuda 7 Ay Sazanı ve 5 Felionlu Çamça vardı. Enerji ilk okumada 28/100, sekiz toplama sonrasındaki gerçek ekran okumasında 36/100 çıktı. Meslek kontrolünden sonra Avlan'a dönüldü.

Felionlu koşusunda 03:01:58'de gerçek OCR zaman aşımı oluştu. 03:01:50'de seçilmiş balık korunarak 03:02:02'de Yakala gönderildi; araya başka halka tıklaması girmedi ve toplama tamamlandı. Duraklatma durumunda beş saniye boyunca **sıfır gerçek tıklama** kaydedildi; devam komutundan sonra üç saniyelik ekran doğrulaması uygulandı.

Üç koşunun girdileri ayrıca günlük üzerinden kontrol edildi: toplama başlatıldıktan bitiş doğrulanana kadar yeni fare tıklaması veya halka seçimi yok. Çalışmalar döngü sınırında temiz çıktı. Tanınamayan halka görüntüsünde tıklama iptali hâlâ uygulanır; isim modunda okunamayan veya seçilmeyen tür atlanabilir.

Kayıtlar: `runtime/live-probe/color-12-cycles.log`, `name-4-cycles.log`, `ay-sazani-3-cycles.log`, `pause-check.txt`, `results.json`. Teşhis girdileri yalnızca test süreçlerinde etkinleştirildi; normal başlatıcı ek test kaydı üretmez. Değişiklik öncesi yedek: `backups/20260923-fishing-regression/`.

Bu son koşulda canlı koruma veya kıymık oluşmadı, enerji 100'e ulaşmadı. Bu yolların önceki canlı/görüntü/durum testi kapsamı yukarıda belirtilmiştir; 19 toplama bunların yeniden canlı sınandığı anlamına gelmez.

## Faz 0-5 doğrulaması — 28 Eylül 2026

### Test ve araç

- `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests`: **177 geçti** (14,87 saniye). Yeni eklenen testler günlük döndürme (6), otomatik panel kısayolu (14) ve koruma/kaçırma regresyonlarıdır.
- `--doctor`: Python paketleri, ekran yakalama, OCR, fare aracı, `ydotoold` soketi ve Xlib satırı raporlanıyor.
- Çalışma ortamı: KDE Wayland (KWin 6.7.5), PipeWire 1.6.9, oyun Chromium penceresi XWayland'de `0x3200004` başlığıyla 1920×1080 tam ekran.

### X11 yakalama (Faz 4-C)

50 karelik canlı ölçümde `capture_x11 = 51`, `capture_spectacle = 0`, `capture_rect = (0, 0, 1920, 1080)`:

| | spectacle (eski) | X11 (yeni) |
|---|---:|---:|
| ortalama | ~370-430 ms | **20,44 ms** |
| medyan / p95 / maksimum | - | 19,82 / 26,71 / 31,26 ms |

- Aynı anda alınan spectacle karesiyle piksel karşılaştırması: `%97,3` piksel ±6/255, ortalama mutlak fark 1,42, korelasyon 0,9999 → döndürme/kanal farkı yok.
- `pixel_to_desktop` özdeşliği köşe ve merkez koordinatlarında sağlandı; `desktop_scale = 1,0`. Örnek `capture_rect = (60, 40, 960, 540)` provasında `(480, 270) → (540, 310)` beklenen çıktı.

### Otonomi doğrulaması: girdisiz canlı koşu

Sahte `ydotool` gölgesi (`/tmp/opencode/fakebin`) PATH'e eklenerek komutların sisteme ulaşması engellendi ve çağrı günlüğü tutuldu. `main.py --dry-run --max-seconds 45`, iki kez, gerçek oyun ekranında:

| ölçüm | 1. koşu | 2. koşu |
|---|---:|---:|
| tick / saniye | 169 / 3,57 | 179 / **3,84** |
| tick ort. (maks.) | 118,1 ms (280,1) | **102,1 ms (154,1)** |
| capture ort. | 18,7 ms | 21,2 ms |
| observe ort. (maks.) | 70,6 ms (206,5) | **55,2 ms (82,9)** |
| protection_template | 24,3 ms | 25,1 ms |
| auto_panel | 149,6 ms (22 çağrı) | **23,3 ms (23 çağrı)** |

- Her iki koşuda da **sistem'e gönderilen girdi 0**: sahte `ydotool` günlüğü boş, metriklerde `input_calls` yok, kapanış özeti `Toplama denemesi: 0 | tamamlanan döngü: 0 | kaydırma: 0`.
- `capture_x11` tik sayısıyla eşit, `capture_spectacle` hiç artmadı; Traceback, koruma, blok ve kesinti olayı yok; çıkış kodu 0.
- Kapsanan yollar: `main.py` `dry_run` dönüşü kaydırmadan önce, `click` dalları tıklamadan önce, `profession.handle` ilk satırda `False`, `focus_game` hiç çağırmıyor.

### Otomatik panel kısayolu

- 19 fixture üzerinde yarı-çözünürlüklü eleme öncesi/sonrası sonuç **birebir aynı** (`_panel_before_shortcut` referansı ile).
- 1920×1080 temiz kare (`navigation.png`): 143,6 ms → **21,3 ms**; canlı koşuda 23 panel taramasının tamamı `auto_panel_fast_reject` ile geçti.
- Gerçek panel hiçbir ölçekte/beyazlıkta kaçmadı: `profession-title.png` temiz haritaya 0,8–1,25 ölçek ve 0,75–1,3 beyazlıkta yapıştırıldığında 12 kombinasyonun 12'sinde de panel bulundu. Temiz harita örneklerinde yarım-ölçek puanı 0,43–0,51, gerçek panelde 0,999; eşik 0,60 iki yönde de boşluk bırakıyor.

### Günlük analizi (`runtime/bot.log`, 23.396 satır)

- **Halka yeniden-yakalama iptalleri (1.010):** 4.825 başarılı halka seçimi, 4.498 doğrulanan toplama var; deneme başına iptal oranı %17,3. İptalin hemen ardından gelen olay 1.010 kez 993'ünde yeni seçim (orta değer 1 satır), üç-kesintiyle hedefi atma **0** kez. Yani koruma çalışıyor, kayıp bir sonraki tikte kapanıyor: kod değişikliği gerekmedi.
- **"Avlan haritası görünmüyor" (358 satır):** 168 bölüm, orta değer 6 saniye; ≥20 saniyelik 31 bölüm toplam sürenin çoğunu oluşturuyor (6.509 sn) ve bunlar odağı kaybetme/pencere değişimiyle örtüşüyor. Gündüz canlı koşuların ikisinde de 45 saniye boyunca **0** kez görüldü.
- **Enerji/iksin:** iksir doğrulanamadı 10, meslek enerjisi okunamadı 3; ikisi de güvenli tarafta (ikinci iksir gönderilmiyor, girdi yok). Enerji döngüsü tercihen kapalı olduğundan bu yollar bu koşularda çalışmadı.
- **"Oyun önde değil" (446):** kullanıcı penceresi ön planda değil; bekleme davranışı kasıtlı.

### Reacquire korumasının teşhisi — `probe_reacquire.py`

Günlükteki 1.010 "Balık son kontrolde yeniden bulunamadı" iptalinin nedenini kareyle kanıtlamak için tıklamayan, kaydırmayan ve yazmayan bir sonda eklendi (`probe_reacquire.py`). Halka hafızada seçiliyor, gerçek fare yolculuğu kadar bekleniyor (0,30 ve 0,60 sn; `mouse._move_to` adım başına en çok 85 piksel ve adım başına 0,015 sn uyku ile uyumlu), ardından `fresh_guard`'ın yaptığı denemelerin aynısı çalıştırılıyor. Her koşulda gölgelenmiş `ydotool` günlüğü boş kaldı.

| koşu | deneme × bekleme | bölüm | hata | oran |
|---|---|---:|---:|---:|
| eski (toplam) | 2 × 0,12 sn | 272 | 22 | **%8,1** |
| yeni (toplam) | 3 × 0,30 sn | 462 | 20 | **%4,3** |
| 120 sn, seyahat 0,60 | 2 × 0,12 sn | 118 | 11 | %9,3 |
| 120 sn, seyahat 0,60 | 3 × 0,30 sn | 111 | 6 | %5,4 |

- Koruma anındaki sınıf dağılımı tüm koşullarda aynı: `halka_yok` (aynı renkli halka hiç görünmüyor) baskın, **`kayma` (halka var ama kabul yarıçapı dışında) sıfır** → sorun sıkı yarıçap değil, halkanın kaybolması.
- Takip (1,2–1,4 sn): hataların büyük bölümü `animasyon` — halka **aynı konumda** geri geliyor (yeniden görülme p50 0,27–0,28 sn, en uzun 1,36 sn). Az sayıda `hareket`/`kayip` örneğinde de koruma tıklamayı doğru biçimde iptal etti.
- Kare kanıtı: `runtime/reacquire-probe/cmp-old/fail-00-select.png` hedef halkayı işaretli gösterir; `fail-00-guard.png` aynı bölgede halkanın tamamen kaybolduğunu (yalnız yeşil animasyonların kaldığını) gösterir.
- Başarılı korumalarda kayma p50 2–4,5 piksel, p90 ~11 piksel; kabul eşiği ort. ~11 piksel. Yani kayma normal sınırlarda; iptal eden durum kayma değil, halkanın yok olması.
- Sonuç: 1.010 iptalin nedeni **balığın hareketi değil, halka animasyonunun boşluğu**. Koruma davranışı doğru (eski konuma tıklamıyor), asıl kusur, ikinci denemenin 0,12 sn'lik beklemeyle boşluğun içinde kalmasıydı.
- Kod: `config.py` `REACQUIRE_ATTEMPTS = 3`, `REACQUIRE_RETRY_DELAY = 0.30`. Test: **177 geçti**. Ölçüm aracının kullanımı `probe_reacquire.py` başlığında.

### Canlı doğrulama koşusu — 28 Eylül 22:41–22:51

Kayıtlı tercihlerle (`--colors beyaz --no-scroll`, enerji/kıymık kapalı) gerçek oyunda **600 sn**, girdi açık, `--max-seconds 600` ile sınırlı çalıştırıldı. Kapanış: `Toplama denemesi: 26 | tamamlanan döngü: 24 | kaydırma: 0`, `Traceback: 0`.

| ölçüm | değer |
|---|---:|
| halka tıklama denemesi | 44 |
| koruma iptali ("yeniden bulunamadı") | **0 → %0** (üst sınır ~%7) |
| koruma içi yeniden deneme (`reacquire_retry`) | 4 (hepsi kurtardı) |
| "Hedef hareket ediyor" (düzeltme döngüsü) | 1 |
| Yakala tıklaması / tamamlanan döngü | 26 / 24 |
| hedef atlandı (yanlış tür) | 17 |
| harita görünmüyor / bot koruması / kesinti | 0 / 0 / 0 |
| `click` / `move` / `input_calls` | 70 / 86 / 433 |

- Tarihsel günlükteki %17,3'lük iptal oranı **karışık sürüm verisi** (eski `reacquire_fish` yollarını da kapsıyor). Güncel kodda ilk deneme 4 kez boş döndü, üç denemeli yeni zamanlama hepsini kurtardı; tek iptal "Hedef hareket ediyor" düzeltme yolundan geldi ve o da kasıtlı.
- Odak kaybı: `focus_wait` 2.276 tikin 1.023'ü (%45) — 22:43:54–22:47:03 arasındaki ortam kaynaklı pencere değişimi; kalan 7 dakika kesintisiz. Bot bu süre boyunca hiç tıklamadı.
- Oyun açıkken maliyet artıyor (boş ekran koşusuyla karşılaştırma): capture 21 → **52 ms**, observe 55 → **110 ms**, `protection_template` 25 → **61 ms**, `auto_panel` 23 → **56 ms** (yaklaşık 2× — oyun CPU yükü). `protection_template` tek başına 81,8 sn ile duvar süresinin %13,6'sı; sıradaki hız hedefi burası.
- `auto_panel_fast_reject` 256/257: panel kısayolu gerçek döngüde de çalışıyor. `capture_x11` = tik sayısı kadar, spectacle hiç kullanılmadı.

### Koruma şablonunun hızlı aşaması — 28 Eylül 23:29

Önceki koşuda `protection_template` tek başına 81,8 sn ile duvar süresinin %13,6'sıydı ve hız hedefi olarak işaretlenmişti. Hızlı aşama (önce küçük ölçekte ekarte et) yeniden kalibre edildi.

**Kalibrasyon** (`PROTECTION_FAST_SCALE`, `PROTECTION_FAST_REJECT`):

| veri | 0.5 ölçekte | 0.4 ölçekte |
|---|---:|---:|
| temiz ekran, canlı (~150 kare) | 0.536–0.660 | 0.540–0.755 |
| temiz ekran, fixture (19 adet) | ≤0.580 | ≤0.755 |
| koruma kareleri | 0.801–1.0 | 0.969–1.0 |
| 10 eşleşme + resize (sabit kare, CPU) | 88,8 ms | 52,9 ms |

- **Eşik ilk 0.75 denenip reddedildi**: canlı negatifler bir ekran durumunda 0,742–0,750 çıkıp tam geçişe (10 tam çözünürlüklü eşleşme) düşüyor, bu da o kareye 500+ ms'ye mal oluyordu. 0.85, negatiflerde ≥0,095, koruma karelerinde ≥0,119 boşluk bırakıyor; kaçırma durumunda da tam geçiş çalışıp doğru kararı verir (yalnızca yavaşlar).
- 0.3 ölçekte ayrım kayboluyor (temiz 0,771 ≥ koruma 0,813); o yüzden taban 0.4.

**Ölçüm (çift taraflı, aynı kare, CPU süresi, 15 çift):** `protection_template` **76,5 → 50,0 ms (1,53×)**, 15/15 çiftte yeni kazandı. Tek başına hızlı blok 88,8 → 52,9 ms.
- Ölçüm tuzağı: `protection_template` ölçeği modül genelinden okur; iki ayrı `ScreenDetector` ile A/B yaparken küresel değişken çağrıdan önce **her** koşul için kurulmazsa her iki koşul da son atanan ölçekle çalışır ve sonuç yanlış çıkar (ilk denemelerde bu yüzden "fark yok" görünmüştü).

**Canlı doğrulama (`--dry-run`, 90 sn, girdi yok — gölgeli ydotool günlüğü boş):**

| ölçüm | 0.5 / 0.62 (eski) | 0.4 / 0.85 (yeni) |
|---|---:|---:|
| `protection_template` ortalaması | 61,0 ms | **40,2 ms** |
| kısayol oranı | — | **204/204 = %100** |
| tik/sn (aynı ortam, ~2× farklı yük) | 2,66 | 2,29 |

Test: **177 geçti**. `test_protection_shortcut_matches_full_scale_everywhere` her fixture'ta hızlı kararın tam kararla aynı olmasını zorunlu tutuyor; `test_actual_protection_blocks_actions` koruma karelerinin kaçmadığını doğruluyor.

### Hız optimizasyonları: maskeler, Hough, BGRA — 28 Eylül 23:39–23:50

Bileşen ölçümü (CPU süresi, canlı kareler) üç masrafı gösterdi ve üçü de eşdeğerlik kanıtıyla düzeltildi:

| kalem | önce | sonra | eşdeğerlik gerekçesi |
|---|---:|---:|---|
| `x11grab.bgra_to_rgb` | 6,41 ms | **0,51 ms** | `cv2.cvtColor(BGRA2RGB)`, 10 karede piksel piksel `array_equal` |
| `_fish_color_masks` | 12,07 ms (6 renk) | **2,54 ms** (1 renk) | formüller birbirinden bağımsız; tek renkli seçimde beşi hiç kullanılmıyordu |
| `HoughCircles` (maske <30 piksel) | 49,3 ms | **atlanıyor** | kabul kriteri zaten `FISH_MASK_MIN_PIXELS = 30` istiyor ve aday her zaman maske içinde; boş maske aransa da sonuç elenirdi |

- `FISH_MASK_MIN_PIXELS` `config.py`'ye taşındı; hem erken çıkış hem kabul kriteri aynı sabiti okuyor (ikisinin kayması imkânsız).
- 25 canlı karenin 25'inde beyaz maske 0 pikseldi → Hough boşuna koşuyordu. Halkalı karede (834 piksel, 7 balık) erken çıkış tetiklenmedi, tespit aynen çalıştı.
- Test: **177 geçti** (kanal dönüşü testi dahil).

**Yeniden başlatma:** canlı bot 23:35:59–23:47:59 arası eski kodla **49 döngü / 0 hata** ile çalıştı, SIGTERM ile temiz kapatıldı (`Durdurma komutu alındı`), 23:48:08'de yeni kodla yeniden başladı (PID 338574, `--colors beyaz --no-scroll`). İlk 2 dakika (451 tik):

| metrik | yeniden başlatma öncesi (eski kod, load ~2) | sonrası |
|---|---:|---:|
| tik/sn | 4,25 | **5,16** |
| `capture` | 25,2 ms | **12,6 ms** |
| `ripples` | 29,3 ms | **17,6 ms** |
| `protection_template` (kısayol %100) | 14,6 ms | 14,5 ms |
| `observe` / `tick` | 33,5 / 69,0 ms | 44,6 / 68,8 ms |

- Yeniden başlatma sonrasının logsunda `Traceback`, "Bot hata nedeniyle durdu" yok; `reacquire_retry: 1` (kurtaran tek deneme), `block: 2` (geçici kareler) normal.

### OCR maliyeti: `--oem 1` — 29 Eylül 00:08

Canlı oturumda `ocr` 14 çağrı × 624 ms = 8,7 sn idi (duvarın %1,9'u) ve her çağrı bir tikin ~0,6 sn'sini blokluyordu (tick maks 1044 ms).

Ölçüm (tesseract 5, gerçek kırpılar):

| deneme | süre |
|---|---:|
| boş kare, `-l tur+eng` varsayılan (`--oem 3`) | 375 ms |
| boş kare, `-l tur` | 202 ms |
| boş kare, `--oem 1` | ~160 ms |
| balık adı karesi, varsayılan | 310–346 ms |
| balık adı karesi, **`--oem 1`** | **177–196 ms** |
| koruma metni karesi (363×772, psm 11), varsayılan | 846 ms |
| koruma metni karesi, **`--oem 1`** | **206 ms** |
| ölçek 1→4 farkı (resize) | 0,1–0,3 ms — **süreyi hiç etkilemiyor** |

- **`--oem 1`** (sadece LSTM motoru) uygulandı: eski motor + kalitim birleşimi iki kat yavaştı. 15 gerçek kırpıda karşılaştırma — anlamlı metin **hepsinde aynı**, sadece sondaki sahte karakterler değişti (`yakala —` → `yakala` daha temiz). `find_yakala_button` regex'i ve alt dize kontrolleri (`toplama`, `hata`, `ustalig`, koruma kalıpları) etkilenmedi.
- `ocr(frame, psm, scale, label=...)` eklendi; sayaçlar `ocr_name`, `ocr_yakala`, `ocr_protection`, `ocr_panel_title`, `ocr_panel_body`, `ocr_energy`, `ocr_progress` — maliyetin hangi çağrı noktasından geldiğini bir sonraki koşuda gösterir.
- Test: **177 geçti** (OCR metin iddiaları içeren vision testleri dahil).
- Canlı kanıt: 00:08:47'de başlatılan bot bu kodla çalışıyor ve 1527 tikte yalnızca **5 gerçek OCR çağrısı** (420 önbellek isabeti) üretti: `ocr_name: 3`, `ocr_yakala: 2`.

### Uyarı penceresini botun kapatması — 29 Eylül 00:44

**Sorun.** Oyun "Nesne artık mevcut değil" hatasını modal olarak açıyor ve bot
bunu `Oyun uyarısı: ...` olarak doğru okuyup block'luyordu, ama ekrandaki
`kapat` düğmesine hiç dokunmuyordu. Sonuç: 00:26:30–00:44:38 arası **18 dakika
kilitli kalış** — 0 döngü, `gate` latched + alarm döngüsü, her 30 saniyede aynı
notice (`notice()` 30 sn tekrar kırpması nedeniyle log sayımları yanıltıcıdır).

**Algılama.** `_panels` kırmızı başlık çubuğunu zaten buluyordu; `hata` başlığı
+ gövde OCR'ından sonra `Observation.close_button` da döndürülüyor.
`ScreenDetector.find_close_button()` tıklama korumasında OCR'sız çalışır:
çubuğun 15–95 px altındaki alanda kırmızı bileşen aranır, gövde satırı ile
kapat düğmesi yükseklikle ayrılır. Düğme **bulunamazsa hiçbir yere
tıkılmaz** — kör konuma tıklama yok.

Ölçüm (`tests/fixtures/warning-object-gone.png`, 1920×1080, `detect_layout`
→ `Layout(195,238,1713,764)`):

| yapı | kare koordinatı | karar |
|---|---|---|
| başlık çubuğu | (761, 433) 384×20 | diyalog |
| gövde satırı | (882, 466) 141×11 | 14 px eşiğin altında → elenir |
| kapat düğmesi | (893, 491) 121×17 | **merkez (953, 499)** |

`mastery-error.png` aynı yapıyı gösteriyor (çubuk (581,253), düğme (773,320)
karede) ama ustalık uyarısı **kasıtlı olarak kapatılmıyor**: çözüm panelde,
botun tekrar tekrar kapatıp yeniden açması sorunu gizler.

**Tıklama.** `FishingBot.dismiss_warning()`: `WARNING_CLOSE_INTERVAL = 1.0`
sn aralık; `mouse.click(before_click=guard)` içinde taze kare + koruma okuması +
`find_close_button` yeniden doğrulaması yapılır, düğme kaymışsa tıklama
gönderilmez. `WARNING_CLOSE_LIMIT = 6` deneme `WARNING_CLOSE_WINDOW = 60.0`
sn içindeyse pes edilir, `block()` + alarm ile kullanıcıya gidilir. `dry_run`
asla tıklamaz. Geçici kare sayacı (`TRANSIENT_BLOCK_FRAMES`) bu bekleme
penceresinde block'a dönüşmez; ekran temizlenirse sıfırlanır.

**Test: 186 geçti** (8 yenisi: üç detector testi, beş akış testi).

**Kara listenin kapsamı da genişletildi.** Aynı koşuda dikkat çeken başka bir
detay: başarısız bir toplamadan sonra bot aynı halkayı ~5 px öteden hemen
yeniden seçiyordu. Nedeni `reset_target()`'ın yalnızca `self.target`'ı
eklemesiydi; oysa tıklama koruması `fresh_guard → reacquire` hedefi başka bir
halkaya kaydırabiliyor ve kara listeye o kaydırılmış nokta giriyordu
(aday listesindeki ilk halka hiç elenmiyordu). `target_origin` eklendi:
seçilen ilk halka **ve** reacquire sonucu ikisi de 24 px yarıçapında eleniyor.
Test `test_failed_harvest_avoids_the_ring_it_started_from` düzeltme öncesi
`avoid == [(266,377, …)]` ile kırmızıydı, sonra yeşile döndü.

**Canlı doğrulama (00:44:42, aynı argümanlarla yeniden başlatma):**

```
00:44:42 Hedefler: Ay Sazanı, Felionlu Çamça, Gümüş Kadife Balığı | ...
00:44:43 Oyun uyarısı kapatılıyor; arama sürecek.
00:44:44 Halka seçildi: (262, 385). Balık adı okunuyor.
00:44:45 Ay Sazanı: toplama başladı. Beklenen süre 10.0 sn; ekran izleniyor.
```

- İlk karede kapatıldı: 69 tikte `warning_close: 1`, `frames_blocked: 1`,
  `warning_wait: 0`, `block: 0`.
- 40 sn sonra 4 tamamlanan döngü (9,98–10,02 sn ölçümler), 5 deneme,
  **0 yeni uyarı**, `protection_or_screen_wait: false`.

## Olta tanımama düzeltmesi ve KWin yardımcı güvenilirliği — 29 Eylül 2026

### Test ve araç

`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests -p no:cacheprovider`
→ **200 geçti** (önceki 194; `test_desktop.py`'ye 6 yeni test).

Canlı KWin kontrolleri (bot kapalıyken, ekran/fareye dokunmadan):

- `Desktop()` üst üste 3 ayrı süreçte **0,011–0,013 sn** içinde açıldı, imleç ve aktif pencere raporlandı.
- Aynı süreçte 15 kez açılıp kapatma: **15/15 başarılı**, her açılışta `loadScript` yeni bir `/Scripting/Script{n}` nesnesi oluşturdu ve ilk rapor 0,0 sn'de geldi.
- Temizlik: kayıtlı (ölü) pid'lerin yardımcıları sonraki açılışta boşaltıldı (7 → 6 artakalan).

### Olta şablonu: ne değişti

Kullanıcının bulgusu: Eşyalar sekmesindeki **kırmızı zeminli Efsanevi Olta** tanınmıyordu, bot eski kahverengi `profession-rod.png` şablonuna bakıyordu.

| şablon | boyut | konum (envanter) | canlı skor |
|---|---|---|---|
| `profession-rod_2.png` (kırmızı, Efsanevi Olta) | 58×56 | (830,275) | çantada aranan hedef |
| `profession-rod_3.png` (mor zemin) | 56×56 | (889,275) | ikinci olta |
| `profession-rod_doll.png` (bebek yuvasında takılı) | 58×56 | (106,349) | bebekte **1,000** |

- Çapraz skorlar: kırmızı ↔ mor **0,189** (ayrı varyant şart); kırmızı olta → bebek yuvası **0,852** (0,89 eşiğinin altında); kırmızı olta → balta hücresi **0,028**.
- Kare genelinde (`Box(447,261,1453,570)`) bulunanlar: `[(889,275,56,56),(106,349,58,56)]`; ok/balta hücrelerinde yanlış pozitif yok; karartılmış kare ve efektler fixture'ında olta eşleşmesi yok.
- Fixture: yeni `tests/fixtures/inventory-rod-equipped.png` (balta bebekte, iki olta çantada), `inventory-rod-new.png` beklentisi `[(829,20,56,56)]`.
- Oturum içi durum: bebekte **balta** takılı, kırmızı Efsanevi Olta çantada (830,275); mor olta çantanın tamamı (sekeler + kaydırma) taranıp **hiçbir yerde bulunamadı**.

### KWin tarafı: neden "imleç/pencere bilgisi alınamıyordu"

Tanılama sırasında hem eski arıza hem de çözüm kanıtlandı:

- **Doğru arayüz ve ad:** `org.kde.kwin.Scripting` (küçük kwin) doğru; ad `local.DwarFishing.p{pid}`. Tanılama betikleri `dbus.service.BusName(...)` nesnesine referans **tutmadığı** için `BusName.__del__` → `release_name` adı anında bırakıyor ve `callDBus` hedefi kayboluyordu; referans tutulduğunda tam `Desktop` kodu raporu teslim etti (`state delivered: True`, `reached end: 1`). `Desktop` zaten `self.bus_name` ile referansı tutuyor.
- **Betik kendiliğinden çalışmıyor:** `norun` denemesi 0 rapor; `run()` çağrısı gelir gelmez rapor geliyor. Yani `_load` içindeki `run()` şart ve doğru nesneye (`/Scripting/Script{id}`, `loadScript` dönüşü ile birebir) çağrılıyor.
- **Dosya yarışı yok:** `del_after_run` (desktop.py davranışı) 6/6 anında rapor; `del_before_run` KWin'den `FileError` üretiyor → temp dosya `run()` döndükten sonra güvenle silinebilir.
- **Artakalanlar:** KWin'de isimleri listelenemeyen 5–6 yardımcı duruyor (ad tahmin edilemedi, zararsız). Kayıtlı pid'ler için temizlik eklendi.

### Eklenen güvenlik

`Desktop._start_helper()`: (1) ölü süreç yardımcılarını boşalt, (2) betiği yükle ve ilk raporu bekle, (3) rapor gelmezse boşalt-yeniden yükle — 3 deneme × 4 sn, sonra `RuntimeError`. `runtime/kwin_scripts.json` kendi pid'imize yazılır; sonraki açılışta ölü pid'ler temizlenir. `close()` boşaltma adımı artık hata yaymıyor.

### Kullanıcı manuel testi — 17:44'te tamamlandı

`setsid nohup ./run.sh --fish ay_sazani felionlu_camca gumus_kadife gok_mavisi_somon --auto-splinter` ile canlı uçtan uca test geçti: `Olta takılı değil` → çanta → Eşya sekmesi → `Çantadaki olta takılıyor` → **`Olta takıldı; meslek döngüsüne dönülüyor`** → Avlan'a dönüş → Gök Mavisi Somon **30,09 sn** (Döngü 1) ve **29,98 sn** (Döngü 2). Sıfır zaman aşımı, sıfır blok, oyun odakta; `ocr_panel_body/title = 1` (tek uyarı penceresi). İkinci (mor) olta çantada hâlâ bulunamadı — kullanıcının bildirilmesi gereken tek açık nokta.

## Kurtarma daima açık ve deniz yönüne göre kaydırma — 29 Eylül 2026 (2. tur)

`.venv/bin/python -m pytest -q tests -p no:cacheprovider`: **210 geçti** (18,96 sn; gi deprecation uyarısı hariç sessiz).

### Kıymık → iksir → oltayı takma yolu artık bayraksız

Kullanıcı kararı: *kıymıkta olta çıktığında önce ilacı içmeli, sonra oltayı takmalı; bu yol her zaman açık olabilir.*

| kontrol | sonuç |
| --- | --- |
| `main.parse_args(['--fish', ...])` | `auto_splinter is True` |
| `... --auto-splinter` | `True` |
| `... --no-auto-splinter` | `False` |
| `ProfessionController` (argümanda bayrak yok) | `recovery_enabled is True`, `enabled is True` |
| `ProfessionController(auto_splinter=False)` | `recovery_enabled is False` |
| Panel kutucuğu işaretli | komut bayrağı içermiyor (varsayılan açık) |
| Panel kutucuğu işaretli değil | komut `--no-auto-splinter` içeriyor |

Sıra canlıda 17:44'te doğrulanmıştı: iksir tüketimi doğrulanınca `İksir kullanımı doğrulandı; olta yeniden takılıyor.` → `Olta takıldı; meslek döngüsüne dönülüyor`.
`runtime/preferences.json` içindeki eski `auto_splinter: false` değeri `true` yapıldı; `--auto-splinter` verilmiş eski başlatma komutları aynen çalışır.

### Dikey kaydırma yalnızca deniz dikeyde uzanıyorsa

`ScreenDetector.sea_extends_vertically(frame, layout)`:

1. `b > 90 && b > r+25 && b > g+10` ile su maskesi (`layout.crop`).
2. Su, görünür alanın %1'inden azsa karar verilmez → kaydırmaya izin (eski davranış).
3. Bir satır ancak **%20'si** suysa deniz satırı sayılır (`SEA_DENSE`); kıyı köpüğü ve dağınık su pikselleri satırı deniz yapmaz.
4. Deniz satırlarının en uzun **sürekli** şeridi (`np.diff > 1` ile bölünür) görünür alanın **%45'inden** (`SEA_BAND_MAX`) kısaysa dikey kaydırma **yapılmaz**.
5. Hiç deniz satırı yoksa (ör. çok dar bir nehir) kaydırmaya izin.

`main.py` kaydırma kararında bunu çağırır; ilk kez engellendiğinde `Deniz yalnızca genişliğe uzanıyor; dikey kaydırma boşuna, görünür alan taranmaya devam ediyor.` günlüğe düşer ve balık bulunana dek tekrarlanmaz (`sea_skip_notice`, bulunduğunda sıfırlanır).

**Canlı ölçüm:** 1497×520 görünür alanda deniz satırı **106/520**, hepsi üst şeritte; en uzun sürekli şerit 106 (< 234) → kaydırma **engellendi**. Kare `.tmp/sea_crop.png` (görsel olarak su şeridi üstte, halkalar içinde, gerisi kara). Kararın verilmediği ilk sürümde uçlardaki dağınık pikseller yüzünden şerit 430/520 çıkmıştı; sürekli-şerit ölçümü bunu kapattı.

Birim testleri: `test_widthwise_sea_band_stops_the_pointless_vertical_scroll`, `test_lengthwise_sea_keeps_the_vertical_scroll`, `test_scattered_water_pixels_do_not_make_a_band_look_vertical`, `test_unreadable_sea_never_blocks_scrolling` (hepsi `tests/test_vision.py`), `test_kurtarma_yolu_varyilan_acik_kapatilabilir` (`tests/test_profession.py`), `test_splinter_checkbox_only_emits_a_disable_flag` (`tests/test_gui.py`).

### Açık nokta

Kaydırma, paneldeki **Nehirde otomatik kaydır** kutucuğu kapalıysa (`--no-scroll`, şu an `auto_scroll: false`) hiç çalışmaz; yukarıdaki koruma kaydırma açıkken devreye girer. İkinci (mor) olta çantada hâlâ bulunamadı.

## Yaratık avı: üst bilgi eşleşmesi düzeltmesi ve panelde av modu — 30 Eylül 2026

`QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests -p no:cacheprovider`: **250 geçti, 2 atlandı** (atlananlar daha önceki oturumlardan, ekran bağlılık testleri).

### Saldırıyı tamamen engelleyen eşleşme hatası

- Seçili yaratığın üst orta bilgi kutusunda adın yanında bir **ⓘ simgesi** var; tesseract bunu metne karıştırıp `'krogan od'` okuyor. Tam metin benzerliği 0,80 kaldığı için `header_verdict` her zaman False dönüyor, bot seçimden hemen sonra "Ad seçilen yaratıkla örtüşmüyor" deyip hedefi atlıyordu. **Canlıda hiçbir yaratığa saldırılamazdı.** Hata `tests/fixtures/hunt-selected.png` üzerinde birebir yeniden üretildi (`sim('krogan od','krogan') = 0.800 < 0.82`).
- Düzeltme: `hunt_catalog.name_score()` artık benzerliği yalnızca tam metinle değil, metnin **ardışık kelime dizileriyle** de hesaplayıp en iyiyi alır; `match_species` ve `header_verdict` bu skoru kullanır. `'krogan od'` → `'krogan'` tokeni 1,0 verir. `'kirpi'` gibi yabancı adlar hâlâ eşleşmez (en iyi token skoru ~0,5).
- Eşit skorlarda daha uzun (özgül) ad kazanır: havuzda `Krogan Muhafızı` da varken OCR `krogan muhafizi` okuyunca `krogan` onun yerine seçilmez. Regresyon testleri: `test_header_info_icon_noise_still_matches_the_species`, `test_equal_scores_prefer_the_more_specific_name`.

### `--creatures all` modunda okunmayan etiket döngüsü

- Etiketi OCR'lenemeyen yaratık 'all' modunda tıklanıyordu ama üst kutudaki ad boş hedef adıyla karşılaştırılıp doğrulama düşüyor, hedef atlanıyor; tek yaratıklı görünümlerde bu tıkla-atla döngüsü sürüyordu. Artık `allow_all` iken üst kutudaki ad hedefe işlenir ve saldırı onaylanır (`test_all_mode_adopts_the_header_name_for_unreadable_labels`). Katalog/azami seviye doğrulaması gibi güvenlik davranışları değişmedi.

### Panele av modu (gui.py)

- **Yaratık avı (Avlan) modu** kutucuğu ve AV HEDEFİ kartı eklendi: Tüm yaratıklar, bilinen tür kutucukları (Maharetli Fitsilya, Krogan), en az/en çok seviye (0 = Yok). Mod açıkken renk/balık tablosu, enerji, kıymık ve ustalık kontrolleri kilitlenir; kaydırma ile döngü/dakika sınırı her iki modda ortaktır.
- `worker_command()` av modunda `run.sh --hunt --creatures … [--min-level …] [--max-level …]` kurar; boş seçim ValueError ile başlatmayı engeller.
- Tercihler `hunt_mode`, `hunt_all`, `hunt_creatures`, `hunt_min`, `hunt_max` anahtarlarıyla `runtime/preferences.json`'a kaydedilir ve yeniden açılışta geri yüklenir.
- Durum kartları av çalışmasında "Tamamlanan dövüş" / "Saldırı denemesi" metnine döner (status.json `mode: hunt`); enerji satırı "Yaratık avında enerji kullanılmaz." gösterir; başlat düğmesi "Avı başlat" olur.
- Yeni GUI testleri: komut kurulumu (seçim/all/seviye), boş seçim hatası, balıkçılık kontrollerinin kilitlenip geri açılması ve tercih turu (restart round-trip).

### Çevrimdışı ve canlı-tegelsiz doğrulama

- Fixture analizi (`hunt.inspect_image`, `grabber=None`): `hunt-map` 12 yaratık (8 Maharetli + 4 Krogan, saldır düğmesi yok), `hunt-selected` saldır düğmesi + halka + "krogan" başlığı, `hunt-result` 'Ava' (1093, 54), `hunt-fight` harita/yok sonuç düğmesi yok.
- `./run.sh --doctor` tamamen yeşil (paketler, Xlib, spectacle, tesseract, ydotool, soket, servis).
- `./run.sh --hunt --dry-run --max-seconds 12`: odak çalınmadan, **sıfır fare girdisiyle** açıldı, "Oyun önde değil" beklemesinde kaldı, çıkış kodu 0; `runtime/status.json` `mode: hunt` ile yazıldı.

### Açık noktalar

- Av modu henüz gerçek oyunda canlı dövüşle denenmedi; tüm akış fixture + sahte oyun simülasyonuyla sınandı (seçim → saldır → dövüş → Ava). İlk canlı denemenin `--hunt --dry-run` ile başlaması önerilir.
- Kataloğa yeni yaratık eklerken `hunt_catalog.KNOWN` listesi güncellenmeli; panel kutucukları bu listeden üretilir.

## Canlı dövüş doğrulaması, Ctrl+C kapanışı, venv onarımı — 30 Eylül 2026 (2. tur)

### Canlı dövüşler (kullanıcı koşusu, 11:47)

`./run.sh --hunt --max-cycles 2`: iki saldırı, iki doğrulama (`Maharetli Fltsllya [4] doğrulandı`,
`Kragan [4] doğrulandı` — üst bilgi ⓘ gürültüsü düzeltmesinin canlı kanıtı), 1 tamamlanan
dövüş, "Ava" ile dönüş, ikinci hedefe geçiş. Akış canlıda uçtan uca çalıştı.

### Ctrl+C / F9 temiz kapanışı

- Belirti: Ctrl+C'de `CalledProcessError: tesseract died with SIGINT` + "Bot hata nedeniyle durdu".
- Kök neden 1: terminal SIGINT'i tesseract alt sürecine de veriyor; `ocr()` artık
  `start_new_session=True` ile çağırıyor (`test_tesseract_runs_in_its_own_session`).
- Kök neden 2 (asıl): `main.py` `__main__` olarak çalışırken `hunt.py`'nin `from main import`
  ile ikinci modul kopyası yaratması; `StopRequested` iki ayrı sınıf olunca av modunda
  durma isteği `except Exception`'a düşüyordu. Sınıf `state.py`'ye taşındı
  (`test_stop_command_raises_the_shared_stoprequested` sınıf kimliğini zorunlu tutar).
- Doğrulama: süreç grubuna SIGINT → `Durdurma komutu alındı.` + `Bitti.` (Traceback 0);
  `./run.sh --stop` (SIGTERM) aynı temiz yoldan çıktı. Dururken gelen başka istisna
  artık hata süsü vermez, türü tek satırda yazılır.

### Bozuk `.venv` onarımı

- Belirti: `cv2` import edilemiyordu; `sys.prefix` venv yerine `/usr` gösteriyordu.
- Neden: sistem Python güncellemesi venv'in site-packages bağını koparmış.
- `./setup.sh` (uv) ile yeniden kuruldu; `--doctor` ve tüm paket importları yeşil.
  Testler `PYTHONPATH=<venv>/site-packages` ile çalıştırıldı (geliştirme oturumu notu;
  kullanıcının kendi terminalinde normal `./run.sh` yeterli).

## Dövüş içi eylemler + birleşik panel — 30 Eylül 2026 (3. tur)

Kullanıcı istekleri: dövüşte otomatik savaş (yeşil), binek (kırmızı), provokasyon (mor)
düğmeleri; provokasyon çubuğundan slot başına kaç yaratık çağrılacağı; panelin tek
arayüz olup açılışta Meslek/Avlan seçimi sunması; her haritada farklı yaratıklar
olabildiği için tür eklenebilmesi.

### Şablonlar iki gerçek çekimden çıkarıldı

- Fotoğraflar fixture oldu: `hunt-fight-toolbar.png` (kullanıcı çizimli) ve
  `hunt-provoke-dialog.png` (temiz, çağırma çubuğu açık). Çizimler şablonu bozduğu için
  düğme şablonları **temiz ikinci çekimden** kesildi: `assets/hunt-{provoke,mount,auto}-button.png`.
- `hunt-fight.png` (eski 1920 çekimi) ile ölçek farkı olmadığı kanıtlandı: üç düğme de
  ölçek 1.0'da 0,947-0,969 skorla bulunur; dikey aralıklar (97/47 px) iki çekimde birebir.
- Çağırma çubuğu: kilitli slotlar `assets/hunt-slot-lock.png` ile (0,80+ üç eşleşme,
  merkezler tam slot merkezlerinde); açık slotlar sayacın **camgöbeği rakamlarından**
  çıkarılır (teal maskesi; iki gerçek sayacın merkezleri ±2 px tuttu). Tıklama noktası
  kart gövdesine düşer (sayaç merkezinden -10,-27).
- Sayaç OCR'ı (20x8 px rakamlar) güvenilmez çıktı; yerine **piksel-farkı doğrulaması**:
  tıklama sonrası teal maske değişmediyse jeton bitmiş/sınır dolmuş sayılır, slotta durulur.

### Yeni görüntü API'si (hunt_vision.py)

- `fight_button(frame, kind)` — provoke/mount/auto düğme merkezi; eşik 0,90
  (`HUNT_FIGHT_BUTTON_THRESHOLD`), çok ölçekli (1.0/0.9/1.1) yedek.
- `summon_slots(frame)` — (açık slotlar, kilitli merkezler), soldan sağa.
- `counter_mask(frame, box)` — sayaç değişim kıyası için teal maskesi.
- Not: `cv2.minMaxLoc` `(minVal, maxVal, …)` döndürür; ilk sürüm minVal'i skor sanıp
  hep None döndürüyordu — test bunu yakaladı, maxVal okunacak şekilde düzeltildi.

### Yeni akış (hunt.py + main.py)

- `perform_fight_actions()`: dövüş ekranı oturunca bir kez — **provokasyon → binek →
  otomatik savaş**. `fight_actions_done` her saldırıda sıfırlanır (dövüş başına tek deneme).
- `run_provoke()`: düğme → çubuk bekleme (6 sn) → slot sırasına göre
  `--provoke-counts` adetlerinde tıklama; her tıklama öncesi `summon_guard` (koruma +
  odak + sonuç penceresi yok + slot hâlâ görünür), sonrası sayaç kıyası.
- Her düğme tıklaması `fight_guard` ile taze karede yeniden doğrulanır; düğme
  görünmüyorsa haber verilip dövüş normal izlenir (asla kilitlenmez). Dövüş 90 sn
  zaman aşımı ve Bot Koruması kuralları aynen geçerli.
- CLI: `--auto-battle`, `--mount`, `--provoke`, `--provoke-counts "3,2"` (0-99, en çok
  5 slot; `--provoke` olmadan adet verilemez).

### Birleşik panel (gui.py)

- Sol üstte **ÇALIŞMA MODU: Meslek / Avlan** radyoları; Avlan seçilince başlık
  "Avlan kontrolü"ne döner, balıkçılık kontrolleri kilitlenir, av kartı açılır. Mod tercihi
  kalıcıdır (eski `hunt_mode` anahtarıyla uyumlu).
- Av kartı: **Tüm yaratıklar**, bilinen tür kutuları, **özel yaratık ekle/kaldır**
  (ad yaz → Ekle; tercihte kalıcı, komuta özgün adıyla gönderilir), en az/en çok seviye.
- **DÖVÜŞ SEÇENEKLERİ:** üç kutu (varsayılan üçü de açık) + provokasyon için 5 slot
  adedi (0 = o slot boş). Provokasyon işaretli ama tüm adetler 0 ise başlatma reddedilir.
- Stat kartları/başlat düğmesi av modunda dövüş metinlerine döner (mevcut davranış korundu).

### Testler ve doğrulama

- **261 geçti, 2 atlandı.** Yeniler: düğme konum/aralık tutarlılığı (iki temiz çekim),
  harita ekranlarında yanlış pozitif yok, çağırma slotu sırası/kilit dışlama/tıklama
  noktası, sayaç maskesi değişim hassasiyeti, `minMaxLoc` regresyonu, eylem sırası
  (provoke→çağır→binek→oto), dövüş başına tek deneme, yeni saldırının yeniden
  silahlanması, özel yaratık ekle/kaldır + komut, dövüş bayrakları + adet doğrulaması,
  tercih turu (özel tür ve adetler dahil).
- `--hunt --provoke --provoke-counts 3,2 --auto-battle --mount --dry-run` girdisiz açılıp
  temiz kapandı; panel her iki modda offscreen render ile görsel olarak doğrulandı.
- Açık nokta: dövüş içi eylemler gerçek oyunda canlı deneme bekliyor (şablonlar ve
  akış iki gerçek çekim + simülasyonla sınandı). İlk canlı denemede jeton bakiyesine
  dikkat: her çağrı jeton harcar.

## Hover düzeltmesi ve ilk canlı dövüş — 1 Ekim 2026

### Kullanıcının canlı denemesi (01:27, `--creatures all`)

- `Phadd Ayisi [5]` (katalog dışı) bulundu, iki aşamada doğrulandı, saldırıldı; dövüş
  ve sonuç ekranı akışı çalıştı. 'all' modu bilinmeyen türü doğru kabul etti.
- Dövüş içi eylemler başarısız: `provoke/auto düğmesi son kontrolde görünmedi` — fare
  düğmenin üstüne gelince **oyunun hover vurgusu** şablon skorunu 0,90 altına düşürüyor,
  `fight_guard` taze karede düğmeyi bir daha bulamayıp tıklamayı iptal ediyordu
  (kullanıcının raporu: "butonların üstüne geldi ama basmadı").

### Düzeltmeler

- `fight_guard` artık düğme şablonunu yeniden okumaz; koruma + odak + hâlâ dövüş
  ekranı (harita yok, sonuç penceresi yok) doğrular. Nokta zaten tıklamadan hemen
  önceki karede 0,90+ ile doğrulanmıştır; dövüş arayüzü düğmeleri kaydırmaz
  (`test_fight_guard_clicks_despite_hover_but_not_on_map_return`).
- `summon_guard` aynı sebeple gevşetildi: slot kartı imleç altında parlasa bile
  çubuk açıksa (slot veya kilit görünüyor) tıklanır; çubuk kapandıysa durur
  (`test_summon_guard_allows_hovered_slot_but_stops_when_bar_closes`).
- `neutral_move()`: her tıklamadan sonra imleç ekranın boş bir noktasına alınır;
  önceki düğmenin hover'ı sonraki düğmenin şablonunu/sayacını karıştırmasın.
  Çağırma döngüsünde sayaç okuması da imleç boşta iken yapılır.
- Panel: "Adetler" spinbox'ları önek yüzünden daralan kutularda okunmuyordu;
  önek kaldırıldı, kutular 46 px ortalı, başlık "Adetler (soldan sağa)".
- Başlangıç logu dövüş seçeneklerini de yazar (`dövüş: provokasyon+binek+oto-savaş`).

Test: **263 geçti** (2 atlanan). Panel iki modda offscreen render ile görsel doğrulandı
(adet kutuları net okunuyor). Dövüş içi tıklamaların hover'lı canlı sınavı bir sonraki
koşuda yapılacak.
