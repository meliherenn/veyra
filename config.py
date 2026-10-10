"""Balık botunun ekran ve zamanlama ayarları (KDE Wayland)."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent
YDOTOOL_SOCKET = os.environ.get(
    "YDOTOOL_SOCKET", str(Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / ".ydotool_socket")
)
CAPTURE_TIMEOUT = 5
OCR_TIMEOUT = 4
POLL_INTERVAL = 0.15
RESUME_CLEAR_FRAMES = 3
RESUME_CLEAR_SECONDS = 3.0
SELECT_TIMEOUT = 8.0
HARVEST_START_TIMEOUT = 5.0
HARVEST_TIMEOUT = 90.0
TARGET_RETRY_SECONDS = 120.0
TARGET_REACQUIRE_DISTANCE = 48.0
# Bir adayin kabul edilmesi icin maskede gereken minimum piksel sayisi.
# Ayni deger bos maske kontrolunde de kullanilir: maskede bundan az piksel
# varsa Hough ne bulursa bulsun aday elenirdi, o yuzden arama yapilmaz.
FISH_MASK_MIN_PIXELS = 30
MAX_REJECTIONS_PER_VIEW = 5
NO_FISH_ALERT_SECONDS = 60.0
ALARM_REPEAT_SECONDS = 3.0
MOUSE_TOLERANCE = 2.5
SCROLL_NOTCHES = 12
PROTECTION_TEMPLATE_THRESHOLD = 0.80

# Geçici ekran değişikliği: tek karelik bir tespit hatası toplamayı ve
# süreyi sıfırlamaz. Bu kadar ardışık kötü kareden sonra gerçek block.
TRANSIENT_BLOCK_FRAMES = 3
# Blok sonrası devam eşiği (sn). Koruma/odak için RESUME_CLEAR_SECONDS,
# harita-kayıp gibi geçici durumlar için daha kısa.
RESUME_FAST_SECONDS = 1.2
# Enerji okunamazsa pencereyi en fazla kaç kez kapat-aç ile yeniden dene.
ENERGY_READ_REOPENS = 2
# İksir tüketimi doğrulama penceresi ve asgari okuma sayısı.
POTION_VERIFY_SECONDS = 20.0
POTION_VERIFY_READS = 2
# Onay penceresi kapandıktan, çanta okunduktan ve ekranda uyarı kalmadıktan
# sonra tüketim kanıtı (sayı/rozet) toplanamasa bile bu süre sonunda tüketim
# kabul edilir. Kıymıkta ilacı içip duraklayıp kullanıcının F8 ile sürdürmesini
# beklememek için.
POTION_ACCEPT_SECONDS = 6.0
# Tıklamadan hemen önce balığın kaybolması durumunda taze kare ile tekrar
# yerini bul. Yeniden tarama hata turundan çok daha ucuz.
# Halka animasyonu görünmez kalma süresi probe_reacquire.py ile ölçüldü:
# yeniden görülme p50 0.27 sn, en uzun 0.53-1.35 sn. Eski 0.12 sn'lik bekleme
# bu boşluğun içinde kaldığı için ikinci deneme de genelde aynı boşluğa denk
# geliyordu. 0.30 sn x 3 deneme ile seyahat 0.60 sn koşulunda koruma hata
# oranı %8.6'dan %1.7'ye indi (bkz. VERIFICATION.md).
REACQUIRE_ATTEMPTS = 3
REACQUIRE_RETRY_DELAY = 0.30

# Oyunun "Nesne artık mevcut değil" gibi hata modalları botu engeller ve
# ekranda bir kapat düğmesi gösterir. Düğme bulunursa bot kendisi kapatır;
# bu kadar sık tekrar ediyorsa asıl sorun çözülmemiş demektir ve pencere
# kapatmak yerine alarm verilir. Pencere içinde kalınan sürece kadar kaç
# kapatma denemesine izin verilir ve iki deneme arasındaki asgari aralık.
WARNING_CLOSE_INTERVAL = 1.0
WARNING_CLOSE_LIMIT = 6
WARNING_CLOSE_WINDOW = 60.0

# Koruma (CAPTCHA) şablonu: önce düşük çözünürlükte ekarte et, eşik altındaki
# temiz ekranlarda tam çözünürlüklü eşleşmeyi hiç çalıştırma.
# (Sadece hız etkisi: tam eşleşme her zaman son sözü söyler.)
# Kalibrasyon (0.4 ölçekte, ~150 canlı kare + 19 fixture + koruma kareleri):
# temiz ekran puanı ekran durumuna göre 0.54-0.755, koruma kareleri 0.969-1.0;
# 0.3 ölçekte ayrım kayboluyor. Eşik 0.75 denenip reddedildi: canlı negatifler
# 0.742-0.750'ye çıkıp tam geçişe düşüyor, o kare 500+ ms'ye mal oluyordu.
# 0.5 ölçeğe göre çift taraflı CPU ölçümü: hızlı blok 88.8 -> 52.9 ms (1.68x),
# tam fonksiyon 76.5 -> 50.0 ms (1.53x); canlı ortalama 61.0 -> 40.2 ms.
PROTECTION_FAST_SCALE = 0.4
PROTECTION_FAST_REJECT = 0.85
# Meslek paneli taraması: panel açıkken her karede, kapalıyken bu kadar sıklıkta.
AUTO_PANEL_PROBE_INTERVAL = 2.0

# Günlükler sınırsız büyümesin: tek dosya en fazla bu kadar, üstünde yedek
# dosyaya kayar ve en eskisi silinir (bot.log ve console.log için ortak).
LOG_MAX_BYTES = 2 * 1024 * 1024
LOG_BACKUPS = 3

# ---------------------------------------------------------------------------
# Yaratık avı (Avlan). Ölçümler 1520 px genişliğindeki harita yerleşimine göre;
# koddaki her boyut layout.width/1520 ile ölçeklenir.
# ---------------------------------------------------------------------------
# Yaratığın gövdesi, adının yazıldığı etiketin yaklaşık bu kadar piksel üstünde
# (gerçek ekranda ölçüldü: etiket merkezi - halka merkezi = 37-38 px).
HUNT_SPRITE_DY = -37
# Seçim doğrulanamazsa sırayla denenen tıklama kaymaları (etikete göre, px).
HUNT_CLICK_DY_FALLBACKS = (-37, -30, -44, 0)
# Etiket yazısı halkadan daha parlaktır (V≈251, halka V≈221). Halkanın alt yayı
# etiket sanılmasın diye alt sınır yüksek tutulur. 248 aynı zamanda ayırt edici
# parlak çimenden ayırır: bazı haritaların çimeni hue 22-45, S≥200 bandına girer
# (148 bin piksel!) ve dev yapışık bölgeler boyut filtresine takılıyordu; etiket
# yazısı V≈251-254 olduğu için 248 üstü yalnız yazıyı bırakır.
HUNT_LABEL_MIN_V = 248
HUNT_LABEL_MIN_S = 200
# Oyun penceresi odağı kaybettiğinde bot güvenlik gereği bekler. Kullanıcı
# uzaktayken bunun fark edilmesi için bu kadar süre sonra alarm verilir ve
# her tekrarda bir kez daha çalınır.
FOCUS_ALERT_AFTER_SECONDS = 600.0
FOCUS_ALERT_REPEAT_SECONDS = 600.0
# Odak kaybında önce oyun penceresi kendiliğinden öne getirilir. Kısa
# nezaket süresi bilerek yapılan geçişleri (panele bakmak, F8 sonrası)
# çekmemek için; ardından bu aralıkla yeniden denenir. Ekran kilitliyse
# başarısız kalır ve alarm akışı devreye girer.
FOCUS_REFOCUS_AFTER = 12.0
FOCUS_REFOCUS_INTERVAL = 10.0
# Odak geri almanın art arda başarısız/etkisiz kalabileceği deneme sayısı
# (kilitli ekran). Sonrasında deneme bırakılır, alarm akışı devreye girer.
FOCUS_REFOCUS_MAX_STREAK = 5
# Ekran bu kadar süre AYNI nedenle bloklu kaldıysa (kapatılamayan oyun
# hatası penceresi, dönmeyen harita vb.) alarm verilir ve 10 dk'da bir
# tekrarlanır. 72 dakikalık sessiz bekleme bu yüzden eklendi.
SCREEN_STUCK_ALERT_AFTER = 300.0
# ENGAGED dövüşte block() beklemeleri dövüş saatini durdurur (kullanıcı
# koruması); sınırsız olması bilinmeyen ekranda asla zaman aşımı vermemeye
# yol açtı. Dövüş başına tazmin edilebilen en çok bekleme süresi.
HUNT_FIGHT_BLOCK_BUDGET = 90.0

# Renkten bağımsız etiket tespiti: her haritanın etiket rengi farklı
# (altın, kırmızı, hue 60 limon yeşili...). Etiket yazısı parlak (V>=200),
# doygun (S>=80) ve KÖTÜ zeminine göre kontrastlıdır (V - bulanık V >= 60);
# parlak-üzerine-parlak öğeler (çimen, çiçek) kontrast eşiğiyle elenir.
HUNT_TEXT_MIN_V = 200
HUNT_TEXT_MIN_S = 80
HUNT_TEXT_CONTRAST = 60

# Kırmızı etiketli haritalar (Kral Akrep): yazı hue ~6, S 255, koyu zeminde
# V 180-250. Arka plan V≈149 olduğundan V>=160 güvenli; seçim halkası (hue 6,
# S 255) boyut filtresiyle elenir (halka yüksekliği etiketten çok büyük).
HUNT_RED_LABEL_HUES = ((0, 10), (172, 180))
HUNT_RED_LABEL_MIN_S = 180
HUNT_RED_LABEL_MIN_V = 160
# Saldır düğmesi şablonu (renkli eşleşme): yanlışlar <=0.63, doğru simge ~1.0.
HUNT_ATTACK_TEMPLATE_THRESHOLD = 0.80
# Üst bilgi kutusu (büyük yazı, temiz OCR) için sıkı eşik: asıl doğrulama
# buradadır. 'Phadd Ayisi' ile 'Yasli Phadd Ayisi' (0.785) burada ayrışır.
HUNT_NAME_MATCH_RATIO = 0.82
# Harita etiketi (küçük yazı, gürültülü OCR: 'flungyuriy kore yavrusul' gibi)
# yalnızca ön filtre olduğu için daha gevşek eşik kullanılır; kesin karar
# üst bilgi kutusunun sıkı eşiğiyle verilir.
HUNT_LABEL_MATCH_RATIO = 0.75
# Saldır tıklamasından sonra harita hâlâ görünüyorsa saldırı başlamamış sayılır.
HUNT_ENGAGE_TIMEOUT = 6.0
# Seçim tıklamasından sonra bu süre içinde saldırı düğmesi hiç görünmezse
# tıklama işlememiştir: 8 sn'lik tam timeout beklenmeden hedef yenilenir.
HUNT_SELECT_FAST_FAIL = 3.5
# Dövüş süresi sınırı artık canlılık tabanlıdır: kare değiştikçe (can barları,
# animasyon, hasar yazıları) bekleme yenilenir; 9 yaratıklık provokasyonlu
# dövüşler 3+ dakika sürdüğü için sabit 90 sn erken kesiyordu.
# - HUNT_FIGHT_TIMEOUT: asgari bekleme (bu süreden önce asla kesilmez).
# - Kare HUNT_FIGHT_STATIC_SECONDS boyunca hiç değişmezse dövüş takılmış
#   sayılır ve erken durulur.
# - HUNT_FIGHT_MAX_SECONDS: ne olursa olsun kesin üst sınır.
HUNT_FIGHT_TIMEOUT = 90.0
HUNT_FIGHT_STATIC_SECONDS = 30.0
HUNT_FIGHT_MAX_SECONDS = 600.0
HUNT_FIGHT_SIGMA = 1.5
# "Ava" düğmesine basıldıktan sonra harita dönmezse tıklamayı tekrarlama aralığı.
HUNT_RETURN_RETRY = 2.5
HUNT_RETURN_CLICK_LIMIT = 3
# Art arda bu kadar seçim başarısızlığında bot alarm verip durur.
HUNT_SELECT_FAILURES_BEFORE_PAUSE = 4
# Seçilemeyen / saldırısı başlamayan yaratık bu süre yeniden denenmez.
HUNT_AVOID_SECONDS = 25.0

# Dövüş içi eylem düğmeleri (otomatik savaş / binek / provokasyon). Şablonlar
# iki gerçek çekimde de aynı ölçekte doğrulandı: canlı skorlar 0.94-1.0,
# yanlış pozitifler için boşluk bu yüzden geniş; eşik bilerek yüksek.
HUNT_FIGHT_BUTTON_THRESHOLD = 0.90
# Provokasyon tıklamasından sonra çağırma çubuğunun çıkmasını bekleme süresi.
HUNT_PROVOKE_BAR_TIMEOUT = 6.0
# Her çağırma tıklaması arasındaki asgari bekleme. Oyun tıklamayı anında
# işliyor (kullanıcı: elle tık tık tık yaptığımda sayaç hemen artıyor);
# eski 0.30 sn + 0.35 sn'lik yoklama darboğazdı. Koruma/odak/slot
# doğrulaması her tıklamada aynen çalışır, yalnız ölü bekleme kalkar.
HUNT_SUMMON_CLICK_PAUSE = 0.10
# Çağırma slotu: sayaç "kullanilan/limit" yazar; tıklama sonrası sayaç
# pikselleri değişmezse (jeton bitti / sınır doldu) o slotta durulur.
HUNT_SUMMON_MAX_PER_SLOT = 20
# Dövüş araç çubuğu dövüşle birlikte animasyonla gelir; ilk karede
# görünmeyebilir. Eylemlerden önce bu süre kadar aranır.
HUNT_TOOLBAR_WAIT_SECONDS = 6.0
# Odağı kaybedilen onay penceresi için dövüş boyunca en fazla kaç yeniden
# Uygula denemesi yapılır (her deneme arası ~1 sn bakılır).
HUNT_CONFIRM_RETRIES = 4
