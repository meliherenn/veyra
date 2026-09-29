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
