# Ejderhalar Mirası — Balıkçılık kontrolü

Chrome, Chromium veya Brave'deki Avlan ekranını görüntüden okuyup gerçek fareyle çalışan Python botu. Renk veya balık adıyla çoklu seçim yapar, hareketli halkaları yeniden bulur, nehirde kaydırarak arar ve süreleri türlere göre kaydeder.

## Başlatma

```bash
cd /home/meliheeren/Masaüstü/dwar_fishing_bot
./run.sh
```

Bu komut artık **kontrol panelini açar**. Terminale Markdown işaretleri veya dizin sonuna virgül eklemeyin.

1. Chrome, Chromium veya Brave'de **Avlan** ekranını açın. Oyundaki renk filtrelerinde istediğiniz balıklar görünür olsun.
2. **Renge göre** seçeneğiyle birden fazla renk veya **Balık adına göre** seçeneğiyle tablodaki türleri işaretleyin. Arama kutusu alternatif isimleri de tanır.
3. İsterseniz **Ustalığım** alanını doldurun. Daha yüksek ustalık isteyen türler atlanır. **Belirtilmedi** bu sınırı uygulamaz.
4. **Toplamayı başlat** düğmesine basın. Panel varsayılan olarak küçülür ve oyun öne gelir.

- **F8:** duraklat / devam et. **F9:** botu durdur.
- Panelden de kontrol edebilir veya seçimleri değiştirip yeniden başlatabilirsiniz.
- **Paneli kapatmak toplama sürecini de durdurur.** Yeniden `./run.sh` çalıştırmak açık paneli gösterir; ikinci bot açmaz.
- Başka pencereye veya sekmeye geçildiğinde fare bekler. Oyuna dönüldüğünde ekran doğrulanıp devam edilir.
- Fareyi sol üst köşeye götürmek fare işlemini keser. Kalıcı duraklatma için F8 kullanın.
- Döngü ve dakika sınırlarında **Sınırsız**, sınır uygulanmadığı anlamına gelir.

Meslek seçenekleri panelin solundadır:

- **Kıymığı gider ve oltayı tak** (varsayılan açık) ile kıymık uyarısında üst menüdeki gerçek karakter çantası açılır. Bot önce Orman Kalbi İksiri için `Kullanmak` ve ardından ilgili onay penceresindeki `Uygula` düğmesine basar; iksir sayısındaki azalmayı doğruladıktan sonra oltayı takar. Bu onay penceresi yeni kıymık hatası sayılmaz. Sadece alet eksikse önce olta takılır; kıymık uyarısı çıkarsa iksir aşamasına geçilir. Sağdaki Savaş Sırt Çantası kullanılmaz. Kutucuğu kapatmak `--no-auto-splinter` gönderir.
- İksir onayı diske kaydedilir; kesinti sonrasında gönderilmiş `Uygula` komutu tekrar gönderilmez. Kullanım doğrulanınca kayıt temizlenir ve sonraki gerçek kıymık olayı yeniden işlenebilir. Çantadan çıkış konum ekranına götürürse üstteki Avlan düğmesi kullanılır.
- **Enerji dolunca otomatik topla** açıkken enerji her başlangıçta yeniden okunur. Normal avlanmada artış tahmin edilir; on tamamlanma veya 180 saniye sonra ve tahmin doluluğa ulaştığında ekrandan doğrulanır. Tam doluluk iki okumada doğrulanınca seçilen balığın `Topla` düğmesine basılır. Oyun toplamayı kendisi tekrarlar; bot `Durdur` düğmesini ve ilerleme sayacını izler, gri düğmelere basmaz. Enerji tükendiğinde pencere kapanır ve normal avlanmaya dönülür.
- Enerji seçimi normal av hedeflerinden bağımsızdır. Panelde enerji döngüsü ve haritada arama açıktır; kayıtlı seçimlerinizi değiştirebilirsiniz. Otomatik toplamada enerji alanı son doğrulanan okumayı gösterir.
- **F9 veya çalışma sınırı**, oyun önde ve otomatik toplama penceresi görünürken oyundaki `Durdur` düğmesine de basar. Bot dururken oyun başka sekmedeyse bu düğmeye erişemez; oyundaki toplamayı kendiniz durdurun. **F8** botun fare işlemlerini duraklatır; oyunun daha önce başlatılmış işlemi devam edebilir.

Bu bilgisayarda KDE Wayland, tek monitör, 1920×1080 ve Chrome/Brave %100 yakınlaştırma ile sınandı. Oyunun filtreleriyle gizlenmiş kaynakları göremez.

## Balıklar ve süreler

Gönderilen 20 meslek satırı **18 tür** altında toplandı. İnsanlar / Magmarlar aynı isim altında seçilir. Alacakaranlık Balığı, ödül ekranındaki **Alacakaranlık İncibalığı** adıyla da tanınır. Logdaki `alacakaranlik baliggi <i>` okuması artık doğru türle eşleşir.

| Gönderilen ekrandaki türler | Renk | Ekrandaki süre |
|---|---|---:|
| Ay Sazanı, Felionlu Çamça, Mağara Balığı, Aynalı Taş Sazanı | Beyaz / gri | 5 sn |
| Alacakaranlık, Gümüş Kadife, Kara Havuz | Yeşil | 9 sn |
| Elmas Som, Kömür rengi turna | Mavi | 12 sn |
| Kırmızı Şabut | Mor | 24 sn |
| Gök Mavisi Somon, Altın Pullu Orkinos | Mor | 26 sn |

Diğer türlerin süreleri ölçülene kadar boş kalır. Billur Mersin'in mor rengi canlı Avlan ekranında ayrıca doğrulandı; yeterli ustalık olmadığı için süresi ölçülemedi.

**Ekrandaki süre**, gönderdiğiniz Otomatik Toplama ekranının değeridir. **Ölçülen ort.**, botun Avlan ekranında gördüğü toplama penceresinin açık kalma süresidir. Bunlar farklı olabilir: ilk yeşil balık denemeleri yaklaşık 11–13 saniye sürdü.

Her türün son 40 geçerli gözlemi ayrı tutulur. Ortalama tabloda, medyan kalan süre tahmininde kullanılır. Örnek sayısı tüm geçerli ölçümleri sayar. Ortalama hücresinin üzerine gelince son, en kısa ve en uzun süre görünür. Yeniden başlatınca veriler korunur.

Bot sabit süre uyumak yerine toplama penceresinin kapanışını izler. Pencere kapandıktan sonraki doğrulama beklemesi ölçüme eklenmez. Odak kaybı, duraklatma veya korumayla kesilen denemeler ve iki saniyeden büyük kapanış gözlem aralıkları kaydedilmez. Ölçümler ekran yakalama aralığı kadar belirsizlik içerir; sunucunun kesin zamanlayıcısı değildir.

## Hareketli balıklar ve kaydırma

Harita sınırları ve halkalar her aramada bulunur. Fare hareketinden sonra, tıklamadan hemen önce yeni ekran alınır; kaybolan veya yer değiştiren hedefe tıklanmaz. Seçili balık adı tüm katalogla karşılaştırılır; sadece seçtiğiniz türe benzetilmez.

Halka animasyonunun merkezinde oluşan küçük farklar, halkanın içindeki tıklamayı iptal ettirmez. Yakındaki başka bir tam halka seçilmeden önce mevcut hedefin kısmen görünen halkası da kontrol edilir. Fareyi sizin taşımanız için uygulanan denetim değişmez.

Balık seçildikten sonra geçici ekran/OCR hatasında aynı seçim yeniden okunur. Okunamayan isim hemen yanlış balık sayılmaz; üç başarısız eylem doğrulaması veya seçim zaman aşımı sonrasında yeniden arama yapılır. Tanınan farklı türler ise seçiminize göre atlanır. Toplama izlenirken tek bir okuma hatası toplama durumunu sıfırlamaz.

Uygun hedef kalmazsa haritanın içinde fare tekerleğiyle kaydırır. Görüntü değişmediğinde yön değiştirir. Kaydırmadan önce haritanın suyunun dikeyde uzanıp uzanmadığı ölçülür: bazı haritalarda deniz yalnızca genişliği boyunca bir şerittir ve aşağı/yukarı kaydırmak suyu görüşten çıkarır — bu durumda kaydırma yapılmaz, görünür alan taranmaya devam eder. Aynı yanlış türlerde takılmamak için geçici atlama listesi ve ret sınırı vardır. Toplama sırasında kaydırılmaz.

Oyunda **yakala** yazısı etikettir; **yanındaki yuvarlak balık simgesi** eylemi başlatır. Bot etiketi ve balığı doğrulayıp simgeye tıklar.

## Koruma ve oyun uyarıları

Bot Koruması / Güvenlik Doğrulaması görüldüğünde fare ve kaydırma durur, sesli alarm başlar. **Doğrulamayı kullanıcı tamamlar.** Normal oyun ekranı en az üç gözlemde ve en az üç saniye boyunca geri geldiğinde devam eder.

Yetersiz ustalık ve diğer beklenmeyen oyun pencereleri de çalışmayı bekletir. Hedefleri veya ustalık sınırını panelden değiştirebilirsiniz. İlgili meslek seçeneği açıkken tanınan enerji, kıymık ve alet uyarıları işlenir; bilinmeyen uyarılar kullanıcıyı bekler. Ekran yakalama, OCR veya fare komutu başarısız olursa eski görüntüyle tıklamaz.

## Yaratık avı (Avlan)

Haritada gezinen yaratıkları bulur, seçer, saldırır ve dövüş sonu penceresinden
"Ava" ile haritaya döner. Balıkçılıktaki güvenlik katmanının hepsi geçerlidir:
görünür fare, her girdiden önce taze ekranla doğrulama, F8/F9, odak kontrolü ve
Bot Koruması çıkınca durup sizi bekleme (koruma ekranı asla aşılmaz).

```bash
./run.sh --hunt --dry-run                     # fare kullanmadan sadece ne gördüğünü yazar
./run.sh --hunt                               # bilinen tüm yaratıklar
./run.sh --hunt --creatures krogan            # yalnızca Krogan
./run.sh --hunt --creatures "Yeni Canavar"    # kataloğda olmayan bir ad da verilebilir
./run.sh --hunt --creatures all --max-level 6 # her yaratık, en fazla seviye 6
./run.sh --hunt --max-cycles 50               # 50 dövüşten sonra dur
./run.sh --hunt --inspect ekran.png --output isaretli.png   # çevrimdışı analiz
```

Panelden de avlanabilir: soldaki **ÇALIŞMA MODU**'ndan **Avlan**'ı seçin — panel
başlığı ve seçimler av arayüzüne döner. Av kartında:

- **Av hedefi:** bilinen yaratıkların kutuları; her Avlan arayüzünde farklı
  yaratıklar olabileceğinden adını yazıp **Ekle** ile yeni tür ekleyebilirsiniz
  (özel türler tercihlerde kalıcıdır, **Kaldır** ile silinir). **Tüm yaratıklar**
  işaretlenirse katalog dışı adlar da saldırılır. En az/en çok seviye sınırı
  uygulanır.
- **Dövüş seçenekleri** (üçü de işaretli gelir, tek tek kapatılabilir):
  - **Otomatik savaş (yeşil kılıçlar):** dövüş başlayınca sol araç çubuğundaki
    otomatik savaş düğmesine basar.
  - **Binek çağır (kırmızı):** dövüş başlayınca bineği savaşa sokar.
  - **Provokasyon (mor maske):** dövüş başlayınca provokasyonu açar ve alttaki
    çağırma çubuğunda **soldan sağa** slot sırasına göre yazdığınız adetlerde
    yaratık çağırır (jeton harcar). Tıklamadan önce slot ve koruma taze kareyle
    doğrulanır; sayaç rakamları değişmezse (jeton bitti / sınır doldu) o slotta
    durulur, dövüş biterse kalan çağrılar atlanır.

Dövüş içi sıra: **provokasyon → binek → otomatik savaş**; her dövüş için bir kez
denenir, düğmeler görünmezse haber verilip dövüş yine izlenir.

Akış: etiket (`Ad[seviye]`) bulunur ve OCR ile okunur -> yaratığın gövdesine tek
tıklanır -> yeşil seçim halkası, sol üstte "saldır" düğmesi ve üst bilgi
kutusundaki ad doğrulanır -> düğmeye basılır -> dövüş ekranı beklenir ->
"İstatistikler" penceresinde "Ava" düğmesine basılır -> harita döner.
Uygun yaratık kalmayınca harita aşağı/yukarı kaydırılır.

Botun yanlış yaratığa saldırmaması için ad iki kez doğrulanır (haritadaki etiket
ve seçimden sonra üst bilgi kutusu; kutudaki ⓘ simgesinin OCR gürültüsü
tolere edilir). Seçim doğrulanamazsa tıklama noktası sırayla
değiştirilir (`HUNT_CLICK_DY_FALLBACKS`); art arda 4 başarısızlıkta bot alarm
verip durur. Dövüş 90 sn içinde bitmezse de durur ve ekran görüntüsünü
`runtime/last-pause.png` dosyasına kaydeder.

## Terminal seçenekleri

```bash
./run.sh --colors yesil mavi
./run.sh --fish alacakaranlik gumus_kadife
./run.sh --fish "Alacakaranlık Balığı" --mastery 30
./run.sh --fish all --mastery 60
./run.sh --colors yesil --max-cycles 3 --max-seconds 90
./run.sh --colors yesil --no-scroll
./run.sh --colors yesil --no-auto-splinter
./run.sh --colors yesil --energy-cycle --auto-fish elmas_som
./run.sh --list-fish
./run.sh --pause
./run.sh --resume
./run.sh --stop
./run.sh --status
```

Renkler: `beyaz`, `yesil`, `mavi`, `mor`, `kirmizi`, `sari`. Seçim belirtilmeyen terminal çalıştırmaları yeşili kullanır. Argümansız çalıştırma paneli açar.

`--max-cycles` gözlenen normal ve otomatik toplama döngülerini birlikte sınırlar; elde edilen balık adedini saymaz. Otomatik sayaç sarımları gözlem aralığında kaçabilir; sınır kesin bir balık kotası değildir. Pencerenin kapanması tek başına ödül miktarını doğrulamaz.

Kıymık/açık alet uyarısında çanta kurtarması **varsayılan açıktır**: bot önce Orman Kalbi İksiri içip oltayı yeniden takar. `--no-auto-splinter` bu yolu kapatır (paneldeki kutucuğu kaldırmak da aynı şeydir). `--energy-cycle`, `--auto-fish` ile seçilen balığı enerji 100 olduğunda otomatik toplar. Enerji döngüsü verilmezse bot eski Avlan döngüsünde başlar ve meslek menüsünü açmaz.

`--no-scroll` haritada otomatik kaydırmayı kapatır (paneldeki kutucuk da aynı işi yapar).

## Deneme ve kurulum

```bash
./run.sh --doctor
./run.sh --test-alarm
./run.sh --dry-run --max-seconds 15
./run.sh --inspect tests/fixtures/green-map.png --output runtime/green-detection.png
QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q tests
.venv/bin/python bench.py --runs 3
.venv/bin/python probe_reacquire.py --seconds 60
```

`./setup.sh`, sistem Python'u ve sistem D-Bus/GObject modüllerini kullanan `.venv` hazırlar. Python paketleri `requirements.txt` içindedir; testler için ayrıca pytest gerekir.

Sistem bağımlılıkları: KDE KWin, `spectacle`, Türkçe/İngilizce verileriyle `tesseract`, `ydotool`, çalışan `ydotoold`, `python-dbus`, `python-gobject` ve ses oynatıcı (`paplay`, `pw-play` veya `aplay`). Kurulum sistem servis izinlerini veya fare ivmesini değiştirmez.

## Dosyalar

`hunt.py` (yaratık avı döngüsü), `hunt_vision.py` (etiket, halka, düğme tanıma), `hunt_catalog.py` (yaratık adları).

- `gui.py`: kontrol paneli ve tek süreç yönetimi.
- `fish_catalog.py`, `timing_store.py`: türler, OCR eşleştirme, renkler, süreler.
- `screen_detector.py`: görüntüden harita, renk, isim ve pencere algılama.
- `main.py`, `state.py`: toplama ve bekleme akışı.
- `profession.py`, `profession_vision.py`, `energy_store.py`: kıymık kurtarma, meslek penceresi ve enerji döngüsü.
- `mouse_control.py`, `desktop.py`: imleç, aktif oyun penceresi ve F8/F9.
- `x11grab.py`, `metrics.py`: X11 pencere yakalama; `runtime/metrics.json` ölçüm sayaçları.
- `bench.py`, `probe_reacquire.py`: çevrimdışı benchmark ve tıklamasız koruma teşhisi (kareler `runtime/reacquire-probe/` içine yazılır).
- `runtime/preferences.json`: son seçimler; `runtime/timings.json`: gerçek ölçümler.
- `runtime/bot.log`: günlük; `runtime/console.log`: panelden başlatılan sürecin çıktısı.
- `runtime/status.json`: son durum; `runtime/last-pause.png`: son bekleme görüntüsü.
- `tests/fixtures/`: tarayıcı ve sohbet bölümleri kırpılmış test görüntüleri.
- `backups/20260910-223655/`: bu geliştirmeden önceki sürüm.

Oyun etkileşimleri ekran görüntüsü ve işletim sistemi fare girdileriyle yapılır. `desktop.py` içindeki geçici yardımcı yalnızca KDE pencere yöneticisinde çalışır; oyun sayfasına kod göndermez. Görüntüler ve kayıtlar yerel kalır.

Teknik dayanaklar: [ydotool](https://github.com/ReimuNotMoe/ydotool#notes), [KDE pencere ve imleç API'si](https://develop.kde.org/docs/plasma/kwin/api/).
