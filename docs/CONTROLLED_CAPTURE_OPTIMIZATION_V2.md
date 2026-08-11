# Kontrollü spot-spray capture optimizasyonu V2

Durum: **READY_FOR_MANAGER_VALIDATION**

Kanıt ve fiyat kontrol tarihi: **2026-08-11**

## Dondurma kararı

PoC için optimum başlangıç, bir adet `0,5 m` swath sınıfında kapalı
görüş modülüdür:

- `Basler a2A2464-77ucPRO` renkli global-shutter kamera;
- `Basler C23-0824-5M-P` 8 mm sınıfı, 2/3 inç, C-mount lens;
- merkezlenmiş native `2048×2048` ROI, ofset `(200, 0)`, dijital resize yok;
- ölçülmüş `474–484 mm` yer FOV'u, nominal `480 mm`;
- lens birimine göre ayarlanıp kilitlenen `520–590 mm` mekanik çalışma
  mesafesi; nominal katalog lensinde `555,61 mm`;
- `f/5,6`, yer düzleminden `55 mm` yukarıdaki düzleme fokus, `170 µs`
  sabit pozlama ve `15 Hz` baseline hardware trigger;
- dört diffuse LED bölgesi, kamera `ExposureActive` sinyalinden izole
  sürücüyle `150 µs` nominal strobe;
- `2×2` native `1024` core karo, her yönde `64 px` halo, modele `1152`
  girdi; dış `64 px` halka aksiyon için daima `abstain`;
- mevcut RTX 3090 üzerinde **yalnız bir kamera / 15 Hz** kanıtlı hesap
  baseline'ı.

Ucuz alternatif `a2A2464-77ucBAS` aynı sensör ve optik sözleşmeyi korur,
fakat kamera gücünü yalnız USB'den alır. Sadece gerçek host portunda brownout,
EMI, frame-loss ve iki saatlik termal test geçerse kullanılır. `90 USD`
tasarruf için saha tipi `12–24 VDC` kamera beslemesini kaybetmek varsayılan
seçim değildir.

Bu karar birden fazla kamerayı tek RTX 3090'a yüklemez. Genişlik, tek sürekli
mat hood/skirt uzatılıp içine en fazla `430 mm` merkez aralıklı tam
kamera–light–trigger bay'leri eklenerek büyütülür; her bay ayrı USB3 root ve
ayrı kanıtlanmış accelerator kapasitesi ister.

## V1 denetimi ve kapatılan eksik kanıt

[V1 sözleşmesi](SPOT_SPRAY_DEPLOY_SOZLESMESI_V1.md) doğru sistemi tarif
ediyordu: kapalı RGB, global shutter, native karolar, `64 px` halo ve kontrollü
strobe. Ancak `12,5–16 mm` lens aralığı, belirli bir satın alınabilir sensörle
FOV'a bağlanmamıştı; kamera adedi, dokuz-bölge garantisi, DOF, USB yükü,
strobe elektrik zarfı ve iki kamera hesap sonucu sayısal değildi.

V2'nin en değerli yeni kanıtı, kamera–lens–FOV–çalışma mesafesi–hareket–FPS
zincirini aynı türetimde kapatmasıdır. Lens üreticisi gerçek tasarım odak
uzaklığını `8,06 mm ±%5` verir; bu nedenle her lensi katalogdaki tek bir
`550 mm` mesafeye takmak karar-tam değildir. V2, kamera yüksekliğini ölçülen
FOV'a ayarlar, sonra mesafe/fokus/irisi kilitler. `520–590 mm` kızak, tüm
katalog odak toleransında hedef FOV için gereken `521,33–588,19 mm` aralığı
kapsar.

Makine-okunur karar [V2 YAML](../configs/deploy/spot_spray_capture_optimization_v2.yaml),
yeniden üretilebilir hesap [V2 JSON](results/controlled_capture_optimization_v2.json),
türetici [Python scripti](../scripts/derive_spot_spray_capture_optimization_v2.py)
ve kapılar [test dosyasında](../tests/test_derive_spot_spray_capture_optimization_v2.py)
birbirine bağlıdır.

## Satın alınabilir kamera ve lens kısa listesi

| Sıra | Kamera | Native sensör / shutter | Full-frame hız | Lens / arayüz | 2026-08-11 kamu fiyatı | Karar |
|---:|---|---|---:|---|---:|---|
| 1 | Basler `a2A2464-77ucPRO`, sipariş `109779` | `2448×2048`, OG05C BSI, 2/3 inç, `3,45 µm`, global, renk + fabrika IR-cut | `71,8 fps` varsayılan; link limiti kapalı `77,7 fps` | `C23-0824-5M-P`; USB3 Vision 5 Gbit/s, C-mount, hardware trigger, USB veya `12–24 VDC` | `709 USD`, lead-time/quote | **Baseline** |
| 2 | Basler `a2A2464-77ucBAS`, sipariş `109777` | PRO ile aynı raster, sensör, piksel ve shutter | `71,8 / 77,7 fps` | Aynı lens ve USB3; kamera gücü yalnız USB | `619 USD`, lead-time/quote | **Düşük maliyet fallback** |
| 3 | Teledyne FLIR `BFS-U3-51S5C-C` | `2448×2048`, Sony IMX250, 2/3 inç, `3,45 µm`, global, renk | BayerRG8 `73`, BayerRG10p `49`, BayerRG12p `37 fps` | Aynı 2/3 inç C-mount lens; USB3 Vision, hardware trigger | `1.304–1.557,78 USD`; tedarikçiye göre siparişe açık veya stokta | Tedarik/SNR challenger |

Basler'in güncel resmi dokümanı iki ace 2 modelinde `2448×2048`, OG05C,
global shutter, `3,45 µm`, USB3 ve hardware trigger'ı; PRO'da ayrıca
`12–24 VDC` beslemeyi doğrular
([PRO](https://docs.baslerweb.com/a2a2464-77ucpro),
[BAS](https://docs.baslerweb.com/a2a2464-77ucbas)). Fiyat kanıtı
[PRO 709 USD](https://graftek.com/product/a2a2464-77ucpro/) ve
[BAS 619 USD](https://graftek.com/product/a2a2464-77ucbas/) liste sayfalarıdır;
ikisi de teslim süresi için teklif ister.

FLIR'in güncel performans belgesi full rasterda format-bağımlı `73/49/37`
fps değerlerini verir
([FLIR spec](https://softwareservices.flir.com/BFS-U3-51S5/latest/Model/spec.html)).
2026-08-11 kamu fiyat kanıtı iki güncel ABD tedarikçi listelemesidir:
[DigiKey 1.304 USD](https://www.digikey.com/en/products/detail/flir-integrated-imaging-solutions-inc/BFS-U3-51S5C-C/16528406)
ürünü siparişe açık ve üretici standart teslim süresini dört hafta gösterirken,
[Edmund Optics US 1.557,78 USD](https://www.edmundoptics.com/f/PdfExport/37234)
ürünü stokta gösterir. Bulunabilirlik tedarikçiye ve zamana göre değişir; satın
alma öncesi yeniden teklif alınır.

Fiyat/azami fps oranı Basler PRO/BAS/FLIR için sırasıyla
`9,12 / 7,97 / 17,86 USD/(fps)`'dir. FLIR hesabı, challenger'ı bilerek
avantajlı değerlendirmek üzere aralığın alt sınırı olan `1.304 USD / 73 fps`
ile yapılmıştır; Basler oranları tekil liste fiyatını kullanır. Aynı alt sınırla
FLIR/PRO fiyat oranı `1.304 / 709 = 1,84`'tür. Üç kamera da aynı piksel
geometrisini ve 15 Hz ihtiyacını karşıladığı için esas ayrım fiyat ve saha beslemesidir:
PRO'nun BAS'a göre `90 USD` primi, mevcut `3.115–6.545 USD` alt toplamın
yalnız `%2,9`'udur ve kamera gücünü veri portundan ayırır.

Seçilen lens sipariş `2200000568`, C-mount, 2/3 inç image circle,
`F2,4–F16`, `5 MP`, `3,40 µm` tasarım ve fokus/iris kilit vidalarına
sahiptir. Üretici teknik sayfası `8,06 mm ±%5` nominal tasarım değerini
ve teslim edilen birimin sapabileceğini belirtir
([lens teknik dokümanı](https://docs.baslerweb.com/c23-0824-5m-p)).
2026-08-11 net liste fiyatı `136 USD` ve üretici sayfasında stokta
görünür
([lens ürün sayfası](https://www.baslerweb.com/en-us/shop/basler-lens-c23-0824-5m-p-f8mm/)).
Fiyatlar vergi, kargo, tarife, kur ve yerel stok içermez; siparişten hemen
önce teklif yenilenmelidir.

## Optik, FOV, GSD, fokus ve DOF kontratı

Aktif sensör genişliği:

```text
2048 px × 3,45 µm = 7,0656 mm
```

Katalog ön-elemesi ince-lens modeliyle yapılır:

```text
FOV = sensor_span × (working_distance - focal_length) / focal_length
working_distance = focal_length × (1 + FOV / sensor_span)
GSD = measured_FOV / 2048
```

| Ölçülmüş yer FOV'u | Nominal `8,06 mm` lens için WD | GSD | 10 mm | 20 mm |
|---:|---:|---:|---:|---:|
| `474 mm` | `548,77 mm` | `0,231445 mm/px` | `43,21 px` | `86,41 px` |
| `480 mm` | `555,61 mm` | `0,234375 mm/px` | `42,67 px` | `85,33 px` |
| `484 mm` | `560,18 mm` | `0,236328 mm/px` | `42,31 px` | `84,63 px` |

Katalog odak toleransıyla gereken toplam WD `521,33–588,19 mm`'dir; ayarlı
mekanik aralık `520–590 mm`'dir. Kurulumda operatör FOV'u hedefe getirir,
gerçek WD'yi kaydeder ve kamera yüksekliği, fokus ile irisi witness-mark ve
mekanik kilitle dondurur. Bu bağlama odak toleransını GSD belirsizliğine
çevirmek yerine fiziksel ayarla giderir.

`64 px` dış abstain sonrası aksiyon-güvenli `1920 px`, FOV zarfında
`444,375–453,750 mm`'dir. `0,5 m` ifadesi mekanik modül sınıfıdır;
iddia edilen tek-kamera güvenli swath en az `444,375 mm`'dir.

Fokus yerden `55 mm` yukarıdaki düzleme kurulur. `0–110 mm` canopy relief,
`f/5,6` ve bir piksel (`3,45 µm`) circle-of-confusion ile tüm odak/FOV
tolerans kombinasyonları analitik DOF içinde kalır. En kötü yakın DOF marjı
`6,10 mm`, uzak marj `27,79 mm`'dir. Nominal kurulumda fokus `500,61 mm`,
DOF `436,79–586,29 mm` ve toplam `149,51 mm`'dir. `550 nm`'de hesaplanan
Airy çapı `7,515 µm = 2,178 px` olduğu için katalog DOF hesabı tek başına
keskinlik kabulü değildir; aşağıdaki MTF kapısı zorunludur.

### Dokuz-bölge piksel garantisi

Görüntü merkezleri `(0,125 / 0,500 / 0,875)` olan `3×3` bölgenin her
birinde `256×256 px` pencere test edilir. Dondurulmuş WD'den yer düzlemi,
`55 mm` ve `110 mm` çıkarılarak üç obje düzlemi kurulur. **27 hücrenin
her biri ayrı geçer; ortalama ile zayıf köşe gizlenemez.**

Her hücre için:

- lokal GSD `≤0,243902439 mm/px`;
- `10 mm ≥41 px`, `20 mm ≥82 px`;
- MTF50 `≥0,15 cycle/px`;
- intrinsic reprojection RMS `≤0,30 px`, p95 `≤0,50 px`;
- replaceable koruyucu pencere takılı, fokus/iris kilitli.

Analitik zarf en kötü `10 mm = 42,31 px`, `20 mm = 84,63 px` verir.
Yine de lens birimi, pencere, montaj tilt'i, distorsiyon ve off-axis MTF ancak
27-hücre fiziksel test geçerse garanti sayılır. Geçmeyen birim/yükseklik
reddedilir; dijital upscale veya merkez bölge ortalamasıyla kapı gevşetilmez.

## Karo, kamera adedi ve ölçeklenebilir swath

`2448×2048` sensörden yatayda `200 px` ofsetli native `2048×2048` ROI
alınır. ROI dört `1024×1024` core'a ayrılır. İç seam halo'su komşu ham
sensör pikselinden gelir; tahmin core'a kırpılır ve kalibre dünya
koordinatında birleştirilir. Dış sınır hesap için reflect-pad edilebilir,
fakat dış `64 px` aksiyon için daima abstain'dir. Tam kareyi `1024`e
küçültmek yasaktır.

En kötü `444,375 mm` güvenli genişlik ve `430 mm` merkez pitch, komşu
güvenli alanlar arasında en az `14,375 mm` örtüşme bırakır. Minimum
birleşik swath ve sürekli hood iç genişliği:

| Kamera/bay | Minimum güvenli birleşik swath | Sürekli hood minimum iç genişliği |
|---:|---:|---:|
| 1 | `444,375 mm` | `600 mm` |
| 2 | `874,375 mm` | `1.030 mm` |
| 3 | `1.304,375 mm` | `1.460 mm` |

Bu geometrik ölçekleme, hesap kapasitesi iddiası değildir. Her kamera kendi
strobe, trigger, kilitli USB3 kablo ve dedicated root controller'ıyla tam bir
optik bay'dir. Rijit üst ve iki katman skirt sürekli paylaşılır; bay'ler arası
mat baffle, swath örtüşmesini kesmez ve her bay ile overlap şeridi ayrı
ambient/uniformity kapısı geçer. Tetikler ortak controller'dan senkron olabilir;
inference bütçesi ayrı kanıtlanır.

## RTX 3090 hesap kanıtı

V1 `64 px` halo sonucu aynı checkpoint ve gerçek RGB karolarda batch-4 için
ortalama `46,0631 ms`, p95 `52,6796 ms` ölçtü. Bu sırasıyla `21,709`
ortalama ve `18,983` p95 modül-fps kapasitesidir. Kamera acquisition/transport,
decode, tracking, actuator ve spray fiziği bu benchmark'ta yoktur.

| Kamera | Her kamera FPS | Karo/s | Ortalama servis kullanımı | p95 servis kullanımı | Frame-period p95 artığı | Compute-only karar |
|---:|---:|---:|---:|---:|---:|---|
| 1 | 12 | 48 | `%55,28` | `%63,22` | `30,65 ms` | geçer |
| 1 | 15 | 60 | `%69,09` | `%79,02` | `13,99 ms` | **baseline; E2E bekliyor** |
| 1 | 20 | 80 | `%92,13` | `%105,36` | `-2,68 ms` | kanıtlanmadı |
| 2 | 12 | 96 | `%110,55` | `%126,43` | `-22,03 ms` | reddet |
| 2 | 15 | 120 | `%138,19` | `%158,04` | `-38,69 ms` | reddet |
| 2 | 20 | 160 | `%184,25` | `%210,72` | `-55,36 ms` | reddet |
| 3 | 15 | 180 | `%207,28` | `%237,06` | `-91,37 ms` | reddet |

Çok-kamera satırları ölçülen tek batch-4 modül servis süresinin seri
tekrarıdır; batch-8 veya concurrent çok-kamera benchmark'ı değildir. Yeni
bir benchmark daha iyi sonuç verebilir, fakat mevcut kanıtla tek RTX 3090'ın
iki modülü taşıdığı söylenemez. Hatta tek kamera `20 Hz`, p95'te frame
periodunu aşar. Bu nedenle bir kamera `15 Hz` tek dondurulabilir baseline'dır
ve fiziksel akışta E2E p95 tekrar geçmelidir.

RTX 3090 Founders Edition referansı `350 W` kart gücü ve `750 W` sistem PSU
ister; AIB kartta üretici değeri kullanılır
([NVIDIA](https://www.nvidia.com/en-us/geforce/graphics-cards/30-series/rtx-3090/)).

## Hız, pozlama, motion blur, FPS ve track gözlemi

En kötü kabul GSD'si `0,236328 mm/px` ile:

```text
blur_px = speed_mm_s × exposure_s / GSD_mm_px
exposure_max = 0,75 px × GSD_mm_px / speed
```

| Hız | `0,75 px` için azami poz | Dondurulan `170 µs` blur |
|---:|---:|---:|
| `0,5 m/s` | `354,492 µs` | `0,360 px` |
| `1,0 m/s` | `177,246 µs` | `0,719 px` |

En kötü `444,375 mm` aksiyon-güvenli geçiş uzunluğunda, periyodik
hardware trigger ve sıfır kayıp varsayımıyla minimum tam gözlem:

| FPS | `0,5 m/s` trigger pitch / gözlem | `1,0 m/s` trigger pitch / gözlem | 5 gözlem için azami hız |
|---:|---:|---:|---:|
| 12 | `41,67 mm / 10` | `83,33 mm / 5` | `1,0665 m/s` |
| 15 | `33,33 mm / 13` | `66,67 mm / 6` | `1,3331 m/s` |
| 20 | `25,00 mm / 17` | `50,00 mm / 8` | `1,7775 m/s` |

`12 Hz` hard minimum, `15 Hz` baseline, `20 Hz` yalnız E2E p95 kapısı
sonrası hedeftir. Frame counter kaybı veya encoder/timestamp geçersizliği
gözlem sayısını sessizce düşürmez; ilgili track no-fire olur.

`2048²` ROI'nin teorik packed payload'ı:

| FPS | Bayer10p | Bayer12p |
|---:|---:|---:|
| 12 | `503,32 Mbit/s` | `603,98 Mbit/s` |
| 15 | `629,15 Mbit/s` | `754,97 Mbit/s` |
| 20 | `838,86 Mbit/s` | `1.006,63 Mbit/s` |

Bu nedenle kamera başına dedicated USB3 root, `≤3 m` screw-lock kablo ve
gerçek 10.000-trigger frame-loss testi zorunludur.

## Diffuse strobe, güç ve termal kontrat

Dört bağımsız current-limited beyaz LED bölgesi lens etrafında simetrik
yerleşir; opal diffuser ile kapalı hacme bakar. Hedef `4500–5500 K`, CRI
`≥90`'dır. Kamera `ExposureActive` çıkışı izole sürücüyü tetikler;
`150 µs` nominal pulse `170 µs` global exposure içinde tamamen kalır.
Pulse hatası `≤%5`, trigger-to-light jitter p95 `≤5 µs`, azami pulse
`170 µs`, azami hız `20 Hz`'dir. Hardware-trigger davranış kaynağı
[Basler triggered acquisition](https://docs.baslerweb.com/triggered-image-acquisition)
dokümanıdır.

Elektrik tasarım zarfı:

- `24 V`, programlanabilir `0–10 A`, `240 W` **peak tavan**; operating setpoint
  değil;
- nominal pulse başına peak enerji tavanı `0,036 J`, `170 µs` için
  `0,0408 J`;
- 20 Hz nominal duty `%0,30`, azami duty `%0,34`; tavanın 20 Hz nominal
  ortalaması `0,72 W`;
- seçilen ayarda bus droop `≤%5`; upstream pulse akımı sıfır varsayılan
  konservatif `10 A × 150 µs` ön-elemesi `1.250 µF` lokal depolama verir;
- light branch ortalama `≤20 W`; compute hariç capture modülü `≤60 W`.

Termal kabul `5–40 °C` dış ortamda 120 dakika sürer: kamera housing
`≤50 °C`, LED plate `≤60 °C`, frame drop ve thermal throttle sıfır.
Kamera üreticisinin SELV/LPS güç gereği izlenir; kamera, light, controller
dalları ayrı sigortalanır.

**Lux, optik joule, LED akımı ve renderer energy bugün dondurulmuş fiziksel
değerler değildir.** Bunlar takılı hood içinde bench değişkenidir. Akım
yalnız elektrik tavanı içinde aranır. Aşağıdaki görüntü ve termal
kapıları aynı ayarda geçemeyen light reddedilir; exposure veya blur limiti
gevşetilmez:

- dark-corrected strobe-off / strobe-on luma `≤0,10`, dokuz bölgenin her biri;
- dokuz-bölge `min/max luma ≥0,75`;
- 8-bit frame mean luma `40–205`;
- clipped white `≤0,002`, clipped black `≤0,001`;
- `%18` gray temporal SNR `≥20 dB`.

Cross-polarization varsayılan kapalıdır. Kaynak filmi + lens analyzer
`90°` challenger'ı yalnız paired wet-leaf/toprak A/B'de saturated glare
alanını `≥%50` azaltır ve aynı exposure/SNR/uniformity/termal kapıları
bozmazsa açılır. Polarizasyonun specular glare bastırma ilkesi
[Edmund Optics](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/machine-vision-filter-technology/)
kılavuzuyla uyumludur; uygulama kararı yine fiziksel A/B'dir.

## Hood, skirt, labyrinth ve pencere

- Tek kamera için en az `600×600 mm` iç planlı rijit üst/yan kabuk; iç
  yüzey mat siyah,
  yerden gökyüzüne doğrudan görüş hattı yok.
- Çok bay'de tek sürekli hood genişliği `600 + (kamera-1)×430 mm`;
  aradaki mat baffle'lar `≥14,375 mm` güvenli swath overlap'ını kapatmaz.
- İki katman `100–150 mm` mat siyah esnek EPDM veya kaplı kumaş etek;
  katmanlar `30–50 mm` şaşırtmalı bindirme, çalışma yer açıklığı
  `0–20 mm`. Kesikler iç labirenti bozmaz; breakaway/no-entanglement testi
  geçmeden bitkiye temaslı saha kullanımı yok.
- İki kademeli, en az `50 mm` baffle derinlikli labirent. Kablo girişleri
  arkaya bakan, contalı S-yoludur.
- Değiştirilebilir `2–3 mm` AR-kaplı optik cam, `3–5°` tilt, contalı ve
  temizlenebilir. Doğrudan strobe geri yansıması yok; tüm optik kalibrasyon
  pencere takılıyken yapılır.

Ambient kabulde kamera kontrolü sabit kalır. Tasarlanan en kötü dış
koşulda exterior lux kaydedilir ve her dokuz bölgede corrected off/on oranı
`≤0,10` olmalıdır. Lux kaydı olmayan ambient challenge **geçemez**; bu
kural bilinmeyen dış ışığı sahte bir sayıyla dondurmayı engeller.

## Encoder, zaman, kalibrasyon, nozzle ve safety arayüzleri

### Kamera ve zaman

- Aynı real-time controller eventi kamera trigger'ını üretir ve quadrature
  encoder'ı latch eder; host arrival timestamp kontrol için kullanılmaz.
- Encoder `≤1 mm/count`, scale error `≤1 mm/m`.
- Trigger–encoder timestamp farkı p95 `≤100 µs`, max `≤250 µs`.
- Encoder `>5 ms` stale, frame counter/timestamp geçersiz veya frame kaybı
  varsa no-fire.
- Bayer10p tercih edilir; frame counter, camera timestamp ve exact exposure,
  gain, WB, WD, strobe ayarı her frame metadata'sına girer.

### Kalibrasyon ve nozzle registration

- Intrinsic/distortion her kamera–lens–pencere montajı için; ground homography
  residual p95 `≤1 mm`, max `≤2 mm`.
- Günlük fiducial registration drift'i `>2 mm` ise no-fire.
- Kamera optik ekseni–nozzle merkezinin along-track ofseti CAD'den varsayılmaz,
  fiziksel ölçülür.
- Komut encoder konumu:

```text
capture_encoder_mm
+ measured_camera_to_nozzle_offset_mm
- speed_mm_s × measured_valve_onset_latency_s
```

- En kötü inference + transfer + controller + valve latency, kalan encoder
  mesafesine sığmıyorsa geç atış yerine abort.
- Kuru marker E2E hata p95 `≤5 mm`, max `≤10 mm`.
- Valve onset latency ve footprint su-duyarlı kâğıt veya fluorescent dye ile
  fiziksel ölçülür. No-fire mesafesi `footprint radius + p95 toplam
  registration hatası`; sayı ölçümden önce uydurulmaz.

### Compute, güç ve fail-safe

- 15 Hz E2E p95 deadline, kamera acquisition, tracking ve sonuç transferiyle
  tekrar ölçülür. Compute-only `13,99 ms` artık bu işler için kanıt değil,
  yalnız mevcut üst sınırdır.
- RTX 3090 kart/host soğutması ayrı termal soak geçer; farklı AIB kartında
  kartın kendi güç ve termal limitleri kullanılır.
- Hardware E-stop strobe ve valve-enable'ı fiziksel keser. Watchdog default
  no-fire'dır.
- Invalid timestamp/encoder/frame/calibration, overtemperature veya hood-open
  no-fire yapar.
- Kuru marker geçse bile deposition ve crop-injury kapılarından önce kimyasal
  enable yasaktır.

## Baseline BOM ve bütçe

Mevcut RTX 3090 yeniden kullanılır ve incremental maliyeti `0 USD` yazılır;
bu, GPU'nun bedelsiz veya ikinci modülü taşıdığı anlamına gelmez.

| Kalem | Minimum | Maksimum | Kanıt türü |
|---|---:|---:|---|
| Basler PRO kamera | `709` | `709` | 2026-08-11 kamu fiyatı |
| C23 lens | `136` | `136` | 2026-08-11 kamu fiyatı |
| Kilitli USB3, I/O, izole trigger kabloları | `120` | `250` | bütçe allowance |
| Dört diffuse LED, sürücü, diffuser | `450` | `1.200` | bench bekleyen allowance |
| Mat hood, skirt, pencere, mount | `400` | `1.000` | imalat allowance |
| Encoder, real-time trigger controller, I/O | `350` | `900` | allowance |
| SELV güç, safety, termal enstrümantasyon | `300` | `750` | allowance |
| Kalibrasyon hedefi ve hareket fixture'ı | `150` | `400` | allowance |
| Host entegrasyonu, cooling, dedicated USB controller | `500` | `1.200` | RTX yeniden kullanılan allowance |
| **Alt toplam** | **`3.115`** | **`6.545`** | vergi/kargo hariç |
| **%15 contingency ile** | **`3.582,25`** | **`7.526,75`** | budgetary, teklif değil |

BAS fallback alt toplamı `3.025–6.455 USD`, contingency ile
`3.478,75–7.423,25 USD`'dir. Tasarruf `90 USD`'dir. İkinci modül, yalnız
ikinci kameradan ibaret değildir: optik, light, trigger, USB ve kanıtlı
compute lane'i tekrar edilir, sürekli hood/skirt uzatılır. Allowance satırları tedarikçi teklifi değil;
A aşamasında fiyatlandırılır.

## Aşamalı bench kabul kapıları

### A — Procurement ve kimlik

- Kamera exact order number, renk sensörü, IR-cut durumu, lens, kablo ve power
  varyantı kayıt altında.
- 2026-08-11 sonrası supplier quote ve lead time yenilenmiş.
- Yanlış mono/Basic/PRO varyantı veya kilitsiz kablo kabul edilmez.

### B — Transport, trigger ve termal

- 20 Hz'de 10.000 hardware trigger: eksik/duplicate frame counter sıfır.
- Timestamp, encoder, strobe jitter ve bus droop kapıları geçer.
- `5–40 °C`, 120 dakika soak: frame drop/throttle sıfır.
- BAS kullanılacaksa powered USB brownout ve EMI challenge ayrı tekrar edilir.

### C — Optik, pencere ve kilit

- Gerçek FOV `474–484 mm`; WD kayıtlı, mount/fokus/iris kilitli.
- Takılı pencereyle 27 hücrenin her biri GSD, 10/20 mm, MTF50,
  distortion ve reprojection kapılarını geçer.
- Dış `64 px` abstain sonrası güvenli uzunluk `≥444,375 mm` doğrulanır.

### D — Light, hood ve polarization

- Ölçülmüş worst-ambient exterior lux ile off/on, uniformity, luma,
  clipping, SNR, jitter ve termal kapılar aynı ayarda geçer.
- Wet challenge paired A/B tamamlanır; polarization varsayılan kapalı kalır.
- Geçen LED current, lux, pulse ve termal durum ilk kez burada dondurulur.

### E — Motion, tracking ve E2E compute

- `0,5` ve `1,0 m/s` hareketli hedefte blur `≤0,75 px`.
- `1,0 m/s`, 12 Hz'de en az 5 güvenli-bölge gözlemi.
- Tek modül 15 Hz akışta acquisition + inference + tracking + transfer p95
  deadline geçer, kuyruk büyümez.
- 20 Hz veya ikinci kamera ancak ayrı yeni benchmark ile açılır.

### F — Registration ve güvenli aktüasyon

- Homography, encoder scale, time alignment ve kuru marker registration geçer.
- Nozzle latency/footprint fiziksel ölçülür ve no-fire yarıçapı dondurulur.
- Deposition ve crop-injury gate ayrı geçmeden kimyasal enable yok.

Gerçek veri toplama ancak A–E geçtikten ve tüm capture kontrol değerleri
versioned metadata'ya yazıldıktan sonra başlar. F kuru işaretleyiciyle veri
toplamaya paralel hazırlanabilir; kimyasal aksiyon için zorunludur.

## Eşleşen sentetik kamera, ışık ve domain-randomization zarfı

Sentetik veri release kararı vermez; real GO score ağırlığı `0`'dır.
Renderer önce tam aktif native `2048×2048` ROI'yi üretir, sonra `2×2`
core + `64 px` halo'ya ayırır. Bağımsız merkezli `1024` tile render'ı final
release için yasaktır.

| Alan | Sentetik zarf | Fiziksel bağ |
|---|---|---|
| Sensör/ROI | Fiziksel `2448×2048`; aktif `2048×2048`, ofset `(200,0)`; Bayer RGB, IR-cut, 10/12 bit | Baseline kamera |
| Odak/FOV/WD | nominal `8,06 mm`, katalog ön-zarfı `7,657–8,463 mm`; FOV `474–484 mm`; WD `520–590 mm` | Focal + FOV birlikte örneklenir, WD türetilir; bağımsız randomize edilmez |
| Fokus/DOF | Fokus `WD - 55 mm`; canopy relief `0–110 mm`; `f/5,6` | Fiziksel 27-hücre kalibrasyonu |
| Poz/hareket | `161,5–170 µs`, along-travel blur `0–0,75 px`, `12–20 Hz` | Motion gate |
| Kamera pose | roll/pitch `±1°`, yaw `±2°` | Mount toleransı; geçmeyen GSD sample reddedilir |
| Strobe | pulse `150–170 µs`, jitter p95 `0–5 µs`; off/on `0–0,10`; luma/uniformity/clipping aynı gate | Takılı hood ölçümleri |
| Optik kusur | distortion, vignetting, off-axis MTF, principal point | Yalnız installed-rig calibration covariance |
| Sensör kusuru | dark/read/shot noise, gain, color matrix, flat field, bad pixels, WB drift | Yalnız ölçülmüş rig dağılımı |
| Islak glare | challenger profil, ayrı | Fiziksel paired polarization A/B geçmeden baseline'a karışmaz |
| Split | `field_session_video_track`; adjacent frame ve cross-role asset overlap yasak | Gerçek GO leakage kontratı |

V12'den başlangıç proxy'si olarak `environment_strength 0,02–0,12`,
`sun_energy 0–0,08`, shadow `0–0,12`, artificial energy `25–65`, size
`0,45–0,90`, warmth `0,25–0,75` korunur. Bunlar **lux, joule, watt, CRI
veya CCT değildir**. Yalnız pre-calibration image-space çeşitlilik
proxy'sidir; ilk fiziksel paired capture sonrası measured distribution ile
değiştirilir. Sentetik sample'lar da aynı luma, clipping, ambient ratio,
GSD ve aksiyon maskesi kapılarından geçer.

## Manager validation için net karar sınırı

Onaylanması istenen baseline, **bir** PRO kamera + C23 lens + `520–590 mm`
ayarlı, kapalı/diffuse-strobe `0,5 m` modül ve mevcut RTX 3090'da `15 Hz`'dir.
Şu iddialar bilerek yapılmaz:

- kamu fiyatı landed quote değildir;
- katalog FOV/DOF hesabı fiziksel dokuz-bölge kabulü değildir;
- ölçülmemiş lux, optik enerji veya LED akımı dondurulmuş değer değildir;
- compute-only 15 Hz, henüz kamera+tracking E2E geçişi değildir;
- tek RTX 3090 iki kamera veya 20 Hz sürdürüyor değildir;
- kuru registration, kimyasal deposition/crop safety geçişi değildir.

Bu sınırlarla V2, gerçek veri toplamadan önce kamera/lens ve modül
mimarisini dondurmak için nicel olarak karar-tamdır; kalan belirsizlikler
uydurulmuş sayı değil, açık bench değişkeni ve fail-closed kapıdır.
