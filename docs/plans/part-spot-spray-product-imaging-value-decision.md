Status: READY
Planner depth: 0
Parent plan: (root plan)

Kontrollü Spot-Spray Ürün Görüntüleme Donanımı Değer Kararı
Amaç

Mevcut pre-real optik/hood araştırmasını, bir adet fiziksel proof modülüyle çürütülebilecek, düşük maliyetli ve fail-closed bir üretim-adayı görüntüleme mimarisine çevirmek.

Bu planın çıktısı:

minimum görüntüleme-uygun müdahale boyutu;

kamera–lens–FOV–çözünürlük–pozlama–hız sözleşmesi;

tek veya çok kamera ölçekleme kararı;

hood, aydınlatma ve işlevsel rugged muhafaza sözleşmesi;

baseline ve challenger satın alma sınırı;

fiziksel A/B sırası;

hangi sonuçta mimarinin dondurulacağı, geri alınacağı veya yeniden planlanacağıdır.

Odaklı handoff, karar tabanını tar-m_projesi, main, dfd4fad4c5675cd1d23b484ce465d1616460c095 olarak tanımlar. 

tarım-projesi-part-spot-spray-p…

Kapsam dışı

Model eğitimi, fine-tune tarifi veya model kodu.

Yeni inference, tracking ya da evaluator implementasyonu.

Nozul seçimi, kimyasal doz, deposition veya crop-injury eşiği.

Kimyasal ateşleme onayı.

Tam araç mekanik tasarımı.

Sertifikalı IP, EMC, titreşim veya ürün güvenliği belgelendirmesi.

Vendor “recognition”, “placement”, “application accuracy” veya “hit-rate” değerlerini precision, recall ya da F1 ile eşitlemek.

Birincil darboğaz

Birincil darboğaz kamera katalog seçimi değildir; exact proof modülünden henüz hash-bound fiziksel A–E PASS bulunmamasıdır.

Mevcut durum PRE_REAL_NOT_READY olarak korunur:

fiziksel A–E rig kabul sonucu yoktur;

exact target-rig gerçek veri manifesti yoktur;

downstream gerçek track-action performansı ölçülmemiştir;

sentetik ve dış-domain sonuçların gerçek GO ağırlığı 0dır;

chemical fire, bu parçanın sonucu ne olursa olsun kapalıdır.

Bu nedenle ilk para ve mühendislik adımı, ikinci kamera veya daha pahalı sensör araştırması değil, tek baseline modülünün A–E fiziksel kanıtıdır.

Kanıt hiyerarşisi

Kararlar aşağıdaki sırayla alınacaktır. Üst sıradaki kanıt alt sıradakini geçersiz kılar.

Exact fiziksel A–E receipt

Aynı kamera, lens, pencere, hood, ışık, host, USB kökü, güç yolu, trigger profili ve RTX 3090 hattı.

evidence_kind: physical_bench.

Ölçüm artifact’ları mevcut ve SHA-256 ile doğrulanmış.

Kontrollü RGB veri toplamaya izin verebilecek tek donanım kanıtı.

Aynı rig ve aynı sahnede eşlenmiş fiziksel A/B

Yalnız önceden tanımlı tek değişken değiştirilir.

Mutlak A–E kapıları her iki kolda da korunur.

Challenger yalnız baseline’a göre gözlenebilir ve tekrar edilebilir üstünlük gösterirse yükseltilir.

Aynı frozen capture profile’dan gerçek target-rig track-action sonucu

Donanımın ürün değerini doğrulayan downstream kanıt.

Bu planda üretilmez; donanım dondurulduktan sonraki bağımlılıktır.

Model başarısızlığı tek başına kamera challenger satın alma gerekçesi değildir.

Mevcut V2 türetimi ve RTX 3090 compute ölçümü

Fiziksel proof için başlangıç mimarisini belirler.

Fiziksel A–E ölçümünün yerine geçmez.

Üretici teknik dokümanı ve güncel tedarikçi teklifi

Kimlik, arayüz, shutter, piksel, güç, lens uyumu, fiyat ve bulunabilirlik için kullanılabilir.

Saha F1, küçük ot başarısı veya ürün GO kanıtı değildir.

Pre-real, sentetik, dış-domain, rakip/literatür ve vendor marketing

Yön ve challenger hipotezi üretir.

Gerçek GO ağırlığı 0dır.

Minimum ot boyutu, recognition ve spray footprint aynı metrikmiş gibi karşılaştırılmaz.

Gerçekler ve çıkarımlar
Kaynaklarla desteklenen gerçekler

Seçili V2 proof mimarisi bir adet hooded, fixed-light, global-shutter RGB modüldür.

Baseline kamera Basler a2A2464-77ucPRO, lens Basler C23-0824-5M-P 8 mm sınıfıdır.

Native sensör 2448×2048; kullanılan merkez ROI 2048×2048, ofset (200, 0)dır.

Ölçülmesi gereken yer FOV’u 474–484 mm, nominal değer 480 mmdir.

Çalışma mesafesi lens birimine göre 520–590 mm aralığında ayarlanır; katalogdaki tek bir nominal mesafe kabul edilmez.

Baseline f/5,6, yerden 55 mm yukarıya fokus, 170 µs exposure ve 15 Hz hardware trigger’dır.

20 mm span için optik witness ≥82 px; 10 mm span için ≥41 pxdir.

Mevcut RTX 3090 için yalnız bir kamera / 15 Hz baseline desteklenmektedir.

20 Hz ve iki kamera aynı RTX 3090 üzerinde kanıtlanmış değildir.

PRO kamera dış 12–24 VDC güç yolunu destekler; BAS yalnız USB’den beslenir.

Kamu fiyat kanıtında PRO 709 USD, BAS 619 USD, FLIR challenger en az 1.304 USDdir; bunlar landed quote değildir.

PRO’nun BAS’a göre mevcut 90 USD primi, mevcut tam modül alt toplamına göre küçük kalmaktadır.

Fiziksel A–E kontrollü veri toplamayı; A–F yalnız kimyasal içermeyen dry-marker readiness’ı açabilir.

Eksik, null veya not_measured değer PASS sayılmaz.

Bu planın karar çıkarımları

İlk ürün proof’u için en ucuz kanıtlanabilir güvenli seçim, en ucuz kamera gövdesi değil; tek PRO tabanlı tam modüldür.

İlk müdahale servis sınıfı 20 mm canopy span olmalıdır.

10 mm, optik kalite witness’ıdır; ürün müdahale vaadi değildir.

20 mm altı bitkiler capture ve annotation kapsamına alınabilir fakat ilk servis sözleşmesinde abstain/no-fire kalır.

İkinci kamera, daha pahalı sensör veya daha geniş swath, fiziksel tek-modül kanıtından önce değer üretmez.

Baseline A–E geçerse ve belirli bir challenger tetikleyicisi oluşmazsa ek kamera A/B’si yapılmadan karar kapanmalıdır.

Dondurulan kararlar
1. Minimum müdahale sınıfı

İlk ürün proof’u için minimum görüntüleme-uygun weed track:

class_name: weed;

canopy_span_mm >= 20.0;

en az bir gözlemde visible_fraction >= 0.70;

o gözlem partial == false;

track değerlendirme paydasına prediction görülmeden girer.

Boyut anlamı:

canopy_span_mm, kalibre edilmiş gerçek görüntü manifestindeki fiziksel etikettir.

Predicted mask alanı veya confidence ile yeniden tanımlanmaz.

Herhangi bir uygun gözlem track’i paydaya kalıcı olarak dahil eder.

Servis bantları:

Fiziksel canopy span	İlk karar
<10 mm	Araştırma/capture; müdahale vaadi yok
10–<20 mm	Optik olarak görünürlük hedefi; ilk ürün proof’unda abstain
>=20 mm ve görünürlük koşulları sağlanmış	İlk müdahale-uygun servis sınıfı

20 mm müşteri-facing performans iddiası, gerçek target-rig track-action kapıları geçene kadar provisional kalır.

2. Baseline optik ve capture mimarisi

Tek proof bay:

Kamera: Basler a2A2464-77ucPRO, order 109779.

Lens: Basler C23-0824-5M-P, order 2200000568.

Sensör: renkli, fabrika IR-cut, global shutter.

Native ROI: 2048×2048, centered offset (200, 0).

Dijital full-frame downscale veya kör upscale: yasak.

Optik eksen: nadir.

Ölçülmüş ground FOV: 474–484 mm.

Nominal ground FOV: 480 mm.

Çalışma mesafesi: birim bazında 520–590 mm içinde ayarlanıp kaydedilir.

Fokus: yer düzleminden 55 mm yukarıdaki düzleme.

Test düzlemleri: 0 / 55 / 110 mm.

Aperture: f/5,6.

Exposure: 170 µs.

Baseline acquisition: 15 Hz.

Hardware trigger zorunlu.

Preferred transport: Bayer10 packed.

Dedicated USB3 root controller zorunlu.

Locking cable uzunluğu <=3 m.

Kamera gücü baseline’da dış 12–24 VDC.

Optik ilişki:

Local GSD her dokuz bölge ve her üç düzlemde <=0.243902 mm/px olmalıdır.

20 mm / 0.243902 mm/px = 82 px.

10 mm / 0.243902 mm/px = 41 px.

1.0 m/s × 170 µs = 0.17 mm fiziksel smear.

Maksimum izinli local GSD’de bu yaklaşık 0.697 pxdir ve 0.75 px blur kapısının altındadır.

Katalog hesabı yalnız prescreen’dir; measured nine-region geometry ve MTF sonucu otoritedir.

3. Native tiling ve güvenli görüntü alanı

2×2 tile grid.

Her tile 1024 px native core.

Her yönde 64 px halo.

Model girdi rasterı 1152.

İç seam’lerde komşu native sensör pikselleri kullanılır.

Dış 64 px halka compute için pad edilebilir fakat aksiyon için daima abstaindir.

Full-frame dijital resize yasaktır.

Minimum action-safe along-track uzunluk 444.375 mmdir.

1.0 m/s ve 12 Hzte bu uzunluk teorik olarak beşten fazla capture fırsatı verir; fiziksel E kapısı yine gerçek geçerli gözlem sayısını ölçer.

4. Kamera sayısı ve ölçekleme

İlk proof:

Kamera sayısı 1.

Yaklaşık 0.5 m swath sınıfı.

Mevcut RTX 3090 üzerinde 15 Hz.

Genişlik ölçekleme:

Tek continuous matte hood içinde tam kamera–light–trigger bay’leri tekrarlanır.

Kamera merkez aralığı <=430 mm.

Kalibre güvenli swath overlap >=10 mm.

Her kamera ayrı USB3 root controller kullanır.

Her kamera için bağımsız kanıtlanmış accelerator kapasitesi gerekir.

Trigger’lar senkron olabilir; kanıtlanmamış compute bütçesi ortak kabul edilmez.

İkinci kamera satın alma koşulları:

Tek baseline bay fiziksel A–E PASS olmalıdır.

Ürün swath ihtiyacı tek bay ile karşılanamıyor olmalıdır.

Çok-bay end-to-end compute ve transport ayrı benchmark ile geçmelidir.

Her bay ve overlap strip D ve E kapılarını ayrı geçmelidir.

Bu dört koşuldan önce ikinci kamera alınmaz.

5. Hood, ışık ve işlevsel rugged muhafaza

Baseline ışık:

Dört bağımsız current-limited geniş spektrum beyaz LED quadrant.

Lens çevresinde simetrik.

Opal diffuser üzerinden kapalı ground volume’a ışık.

CCT hedefi 4500–5500 K.

CRI >=90.

Kamera ExposureActive sinyalinden isolated driver.

Nominal strobe pulse 150 µs.

İzin verilen pulse 150–170 µs.

Trigger-to-light jitter p95 <=5 µs.

Pulse-width error <=5%.

24 V bus.

Programmable peak current 0–10 A.

Peak electrical ceiling 240 W; işletme setpoint’i değildir.

Light branch average power <=20 W.

Compute hariç complete capture module average power <=60 W.

Pulse anında bus droop <=5%.

Baseline hood/muhafaza:

Minimum iç plan 600×600 mm.

Rigid top ve walls.

Ground ile gökyüzü arasında doğrudan görüş hattı yok.

İç yüzey düşük yansıtmalı matte black.

İki kat flexible matte EPDM veya coated-fabric skirt.

Katman uzunluğu 100–150 mm.

Stagger overlap 30–50 mm.

Çalışma ground clearance 0–20 mm.

Terrain compliance için overlapping slit ve inner labyrinth.

Breakaway ve no-entanglement testi zorunlu.

İki aşamalı labyrinth.

Baffle depth >=50 mm.

Kablo geçişleri rear-facing, gasketed S-path.

Replaceable AR-coated optical glass.

Pencere kalınlığı 2–3 mm.

Pencere tilt’i 3–5°.

Pencere sealed, cleanable ve calibration sırasında installed olmalıdır.

Focus ve iris witness mark ile kilitlenir.

Camera/light/controller dalları fused olmalıdır.

Güç SELV/LPS olmalıdır.

Overtemperature veya hood-open halinde sistem fail-closed kalmalıdır.

Bu aşamada IP rating iddiası yapılmaz. Bu, kontrollü proof için işlevsel rugged muhafazadır. Yağmur, basınçlı yıkama, yoğun toz, taş darbesi veya titreşim için sertifikalı ürün gereksinimi gelirse ayrı environmental contract gerekir.

6. Görüntü kalitesi kapıları

Aynı fixed camera controls ile, dokuz bölgenin her birinde:

dark-corrected strobe_off / strobe_on luma ratio <=0.10;

nine-region luma_min / luma_max >=0.75;

frame mean luma 40–205 8-bit eşdeğeri;

fully clipped white fraction <=0.002;

fully clipped black fraction <=0.001;

18% gray temporal SNR >=20 dB.

Optik:

10 mm span >=41 px;

20 mm span >=82 px;

MTF50 >=0.15 cycles/px;

intrinsic reprojection RMS <=0.30 px;

intrinsic reprojection p95 <=0.50 px;

distortion model geçerli;

tüm 9 × 3 = 27 region/plane hücresi ayrı geçer;

ortalama ile zayıf bölge gizlenemez.

7. Fail-closed davranış

Aşağıdakilerden herhangi birinde görüntüleme modülü geçerli müdahale girdisi üretmez:

frame counter gap veya duplicate;

invalid camera timestamp;

stale encoder;

calibration invalid;

working distance/FOV/focus/iris profile drift;

frame drop;

overtemperature;

hood open;

trigger/light timing violation;

required deadline’in kaçırılması;

outer abstain ring içindeki aday;

profile kimliği veya hash uyuşmazlığı.

Eksik ölçüm PASS değildir. Synthetic fixture fiziksel PASS değildir.

Frozen ve provisional ayrımı
Fiziksel proof için frozen

Tek kamera / tek bay.

PRO kamera ve C23 lens.

Global shutter.

Native 2048² ROI.

474–484 mm FOV.

520–590 mm ayarlanabilir çalışma mesafesi.

f/5,6, 55 mm fokus düzlemi.

170 µs.

15 Hz.

20 mm ilk eligible weed sınıfı.

Dört quadrant diffuse strobe.

Kapalı matte hood, çift skirt, labyrinth ve installed AR window.

Dedicated USB3 root ve dış 12–24 VDC.

Dokuz bölge / üç düzlem kapıları.

A–E physical receipt olmadan controlled capture yok.

Fiziksel ölçümle belirlenecek provisional

Exact strobe peak current.

Exact diffuser part/material.

Exact LED parça üreticisi.

Exact lux ve optical energy.

Exact working distance within 520–590 mm.

Exact manual white-balance gains.

Exact gain dB.

Exact thermal interface ve fan/heatsink yerleşimi.

Exact fabrication material ve kalınlıklar.

Landed BOM fiyatı ve teslim süresi.

Bu değerler yalnız mevcut üst sınırlar ve image-space gates içinde seçilir.

Challenger kanıtı olmadan provisional veya kapalı

20 Hz.

İkinci kamera.

Tek RTX 3090 üzerinde multi-camera.

BAS USB-only cost-down.

FLIR vendor-diverse kamera.

Cross-polarization.

20 mm altı müdahale.

Daha geniş FOV.

Daha düşük exposure.

Sertifikalı IP veya vibration rating.

Production quantity satın alma.

Kimyasal ateşleme.

Seçenek matrisi
Seçenek	Beklenen değer	Ana risk	Satın alma kararı
1× Basler PRO + C23, kapalı diffuse-strobe modül	Frozen geometri, external power, locking I/O, en düşük entegrasyon belirsizliği	Henüz fiziksel A–E yok	Seçili baseline; bir adet proof set alınır
Basler BAS + aynı lens	Aynı sensör, ROI, shutter ve optik; kamera gövdesinde 90 USD düşüş	USB data ve power aynı hatta; brownout/EMI/host bağımlılığı	İlk proof için alınmaz; yalnız koşullu cost-down fallback
FLIR BFS-U3-51S5C-C + aynı lens sınıfı	Vendor çeşitliliği ve farklı sensör	En az 1.84× kamera fiyatı; kanıtlanmış ürün faydası yok	İlk proof için alınmaz; yalnız supply veya camera-intrinsic failure trigger’ı
2 kamera / tek RTX 3090	Daha geniş swath	Compute p95 ve USB yolu kanıtlanmamış	Reddedildi; yeni multi-module E2E kanıtına kadar kapalı
20 Hz baseline	Daha sık gözlem	Mevcut one-module p95 yalnız 15 Hz için destekli	Challenger; 15 Hz PASS sonrasında test edilir
Daha geniş FOV / aynı raster	Daha geniş swath, daha az kamera	20 mm piksel span ve off-axis kalite düşer	Reddedildi; yeni optik ve gerçek action kanıtı olmadan açılmaz
Dijital upscale/downscale	Donanım değiştirmeden raster değişimi	Gerçek optik detay üretmez; önceki gerçek-domain sonuçta zarar gördü	Reddedildi
Rolling shutter / tüketici kamera	Daha düşük kamera fiyatı olabilir	Hareket geometrisi, hardware trigger, locking I/O ve determinism kaybı	Reddedildi
Ambient-only veya açık hood	Daha düşük ışık/muhafaza maliyeti	Güneş/gölge değişkenliği, kısa exposure’da SNR ve glare	Reddedildi
Cross-polarization her zaman açık	Islak glare azalabilir	Işık kaybı, SNR/thermal yükü	Varsayılan kapalı; yalnız paired wet-glare PASS ile
Vendor minimum-recognition boyutuna göre tasarım	Daha küçük boyut iddiası	P/R/F1, crop hit ve spray footprint karşılaştırılamaz	Karar kanıtı olarak reddedildi
Satın alma sınırı
İlk satın alma paketi

Owner onayı ve güncel teklif sonrasında en fazla:

1× Basler a2A2464-77ucPRO;

1× Basler C23-0824-5M-P;

tek bay için locking USB3 ve I/O cable;

tek bay için external 12–24 VDC camera power yolu;

tek bay için isolated trigger/strobe driver;

dört quadrant LED/diffuser proof seti;

bir adjustable hood/skirt/window prototype;

gerekli calibration target ve thermal/electrical ölçüm elemanları.

Tedarikçi quote ve lead time, 2026-08-11 sonrasına ait olmalıdır. Kamu liste fiyatı satın alma fiyatı sayılmaz.

İlk satın almada yasak

İkinci PRO kamera.

BAS yedek/challenger.

FLIR challenger.

İkinci accelerator.

Production-quantity hood veya custom enclosure.

Production-quantity polarizer.

Production boom-width replication.

BAS satın alma trigger’ı

BAS yalnız şu iki durumdan birinde değerlendirilebilir:

PRO, proof takvimini karşılayacak şekilde tedarik edilemiyordur; veya

Tek baseline A–E PASS sonrasında onaylanmış üretim miktarındaki toplam landed tasarruf, bir BAS doğrulama birimi ve tekrar test maliyetini açıkça aşıyordur.

BAS kullanılırsa:

exact host, powered USB root, cable ve power topology frozen olur;

B transport/trigger/thermal baştan geçilir;

C–E aynı fiziksel unit üzerinde tekrarlanır;

host veya USB root değişirse kanıt geçersiz olur;

bir adet missing/duplicate frame, brownout, EMI kaynaklı disconnect veya thermal/frame-loss sonucu BAS’ı reddeder.

FLIR satın alma trigger’ı

FLIR yalnız şu durumlardan birinde alınabilir:

Basler PRO ve lens uyumlu Basler yolu proof takvimini bloke edecek şekilde tedarik edilemiyordur; veya

PRO baseline, bir adet bounded remediation sonrasında camera-intrinsic SNR, sensor artifact veya transport güvenilirlik kapısını geçememiştir ve hata hood, light, lens, window, host veya cable ile açıklanamamıştır.

FLIR alınırsa full A–E yeni unit üzerinde baştan geçer. Daha yüksek fiyat veya farklı sensör adı tek başına challenger gerekçesi değildir.

Aşamalı fiziksel A/B planı

A/B sırası, en az yeni donanımla en çok belirsizliği kapatacak şekilde uygulanır.

Faz 0 — Identity ve satın alma dondurma

Baseline satın alınmadan önce:

exact camera order number;

color/IR-cut state;

exact lens order number;

power variant;

cable;

host;

USB root;

quote;

lead time;

return/acceptance window

tek identity receipt’te dondurulur.

Bu fazda challenger kamera satın alınmaz.

Faz 1 — Baseline A–E

Önce exact V2 baseline tek başına çalıştırılır.

Başarı sonucu:

FROZEN_FOR_CONTROLLED_CAPTURE_CANDIDATE.

Başarısızlık sonucu:

hata sınıflandırılır;

yalnız bir bounded remediation yapılır;

aynı kapı tekrar edilir;

ikinci başarısızlıkta core architecture REPLAN_REQUIRED olur veya koşullu challenger trigger’ı açılır.

Faz 2 — Satın alımsız/az maliyetli challenger’lar

Yalnız baseline ilgili mutlak kapıyı geçtikten sonra:

15 Hz → 20 Hz

Aynı kamera, ROI, exposure, tile, model, tracking ve transfer.

Promotion için end-to-end p95 <=50 ms, zero deadline miss ve zero frame drop.

Başarısızsa 15 Hz baseline korunur; yeni compute satın alınmaz.

Polarization OFF → crossed polarization ON

Aynı wet-leaf/wet-soil sahne.

Aynı exposure ve hood.

ON yalnız saturated-glare area’yı >=50% azaltır ve tüm luma, SNR, uniformity, clipping, thermal ve exposure kapılarını korursa yükseltilir.

Aksi durumda OFF frozen kalır.

Strobe operating-point search

0–10 A elektrik zarfında en düşük geçen current aranır.

Amaç en düşük thermal/power yükünde tüm image gates’i geçmektir.

Ortalama veya tek merkez bölgeyle seçim yapılmaz.

Hiçbir setpoint tüm kapıları aynı anda geçmezse current artırarak ceiling aşılmaz; light/hood architecture başarısız sayılır.

Faz 3 — Koşullu kamera challenger

BAS veya FLIR A/B’si yalnız tanımlı satın alma trigger’ı gerçekleşirse yapılır.

Aynı lens sınıfı, measured FOV, ROI, exposure, hood, light ve sahne korunur.

Camera-specific karşılaştırma için validation sahneleri ve ölçüm sırası eşlenir.

Challenger, mutlak A–E kapılarını geçmeden fiyat/SNR üstünlüğüyle seçilemez.

İki challenger aynı anda satın alınmaz veya denenmez.

Faz 4 — Donanım dondurma ve capture handoff

Bir camera/light/hood profile seçildiğinde:

unique rig_id;

camera_id;

capture_profile_id;

strobe_profile_id;

working distance;

exposure;

gain;

manual white balance;

pixel format;

window;

focus/iris witness state;

host/USB root;

component identities

hash-bound olarak dondurulur.

Bu profile bağlı fiziksel A–E PASS olmadan gerçek target-rig capture READY olamaz.

Ordered implementation ledger
Paket 1 — Karar ve source identity kilidi

 - [ ] configs/deploy/spot_spray_capture_optimization_v2.yaml kaynağını SHA-256 f9fd1cbed95118b4606199e9b67b317c07384e2cb063b60a00e5466848f657e9 ile pinle.

 - [ ] docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md kaynağını SHA-256 c5eb80d8eb074b36463906a4dee993776d2415ae1e41ad50a988c8592e8ed7aa ile pinle.

 - [ ] Rig acceptance exact-byte contract kimliğini a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c olarak doğrula.

 - [ ] Canonical policy kimliğini c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21 olarak doğrula.

 - [ ] Evaluator kimliğini 596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2 olarak doğrula.

 - [ ] Baseline mimariyi 1× PRO + C23 + external power + native 2048² + 480 mm class FOV + 170 µs + 15 Hz + enclosed diffuse strobe olarak decision register’a geçir.

 - [ ] Minimum ilk service class’ı 20 mm canopy span / visible_fraction >=0.70 / non-partial olarak geçir.

 - [ ] 10 mm sınıfını yalnız optical witness olarak işaretle.

 - [ ] Acceptance: hiçbir source hash, camera identity, size threshold veya baseline parametresi belirsiz kalmaz.

Paket 2 — Quote ve tek-unit procurement

 - [ ] PRO kamera, C23 lens, locking cable ve external power için 2026-08-11 sonrası quote ve lead time al.

 - [ ] Quote’a tax, shipping, tariff, local stock ve döviz varsayımlarını ayrı kaydet.

 - [ ] Exact order number, color sensor, IR-cut ve power variant’ı doğrula.

 - [ ] Yalnız bir proof camera/lens seti için owner approval kaydet.

 - [ ] BAS, FLIR, ikinci kamera ve production quantity satın alımını bloke et.

 - [ ] Acceptance: Stage A receipt exact purchased identity ve güncel supplier evidence içerir.

Paket 3 — Tek baseline bay ve işlevsel rugged prototype

 - [ ] Adjustable 520–590 mm camera mount üret.

 - [ ] Focus ve iris için mekanik kilit ve witness mark ekle.

 - [ ] Minimum 600×600 mm matte-black rigid hood kur.

 - [ ] Çift kat skirt, overlap, labyrinth ve rear-facing gasketed cable path uygula.

 - [ ] Breakaway/no-entanglement davranışını test edilebilir yap.

 - [ ] 2–3 mm, 3–5° tilted, replaceable AR window’u installed calibration state’e dahil et.

 - [ ] Dört LED quadrant, opal diffuser ve isolated ExposureActive driver kur.

 - [ ] Camera/light/controller güç dallarını fused SELV/LPS kaynağa bağla.

 - [ ] Kamera housing ve LED plate sıcaklık ölçüm noktalarını tanımla.

 - [ ] Acceptance: assembled hardware exact identity receipt ile eşleşir ve hood-open/overtemperature fail-closed sinyali üretilebilir.

Paket 4 — Stage B: transport, trigger, power ve thermal

 - [ ] 20 Hzte en az 10,000 hardware trigger uygula.

 - [ ] Missing frame counter sayısını 0 doğrula.

 - [ ] Duplicate frame counter sayısını 0 doğrula.

 - [ ] Invalid camera timestamp sayısını 0 doğrula.

 - [ ] Stale encoder event sayısını 0 doğrula.

 - [ ] Trigger–encoder delta p95 <=100 µs, max <=250 µs doğrula.

 - [ ] Strobe jitter p95 <=5 µs doğrula.

 - [ ] Pulse-width error <=5% doğrula.

 - [ ] Bus droop <=5% doğrula.

 - [ ] 5°C ve 40°C intended endpoint coverage’da iki saatlik thermal evidence üret.

 - [ ] Camera housing <=50°C, LED plate <=60°C doğrula.

 - [ ] Frame drop ve thermal throttle event sayısını 0 doğrula.

 - [ ] Acceptance: Stage B tüm ölçümleri measured/PASS ve hash-bound artifact ile taşır; tek hata PASS’i engeller.

Paket 5 — Stage C: FOV, GSD, focus, MTF ve window

 - [ ] Exact lens biriminde camera height’ı measured 474–484 mm FOV’a ayarla.

 - [ ] Working distance’i kaydet ve 520–590 mm içinde doğrula.

 - [ ] Focus’u ground’dan 55 mm yukarıdaki düzleme ayarla; iris f/5,6.

 - [ ] Focus ve iris witness state’i kilitle.

 - [ ] Testi installed protective window ile yap.

 - [ ] 0 / 55 / 110 mm object-plane offset’lerin her birinde dokuz region ölç.

 - [ ] Tüm 27 hücrede local GSD <=0.243902 mm/px doğrula.

 - [ ] Tüm 27 hücrede 10 mm >=41 px ve 20 mm >=82 px doğrula.

 - [ ] Tüm 27 hücrede MTF50 >=0.15 cycles/px doğrula.

 - [ ] Intrinsic reprojection RMS <=0.30 px, p95 <=0.50 px doğrula.

 - [ ] Distortion model geçerliliğini doğrula.

 - [ ] Ortalama alma veya merkez ağırlığıyla zayıf hücreyi gizleme.

 - [ ] Acceptance: 27/27 hücre PASS; aksi halde optik mimari PASS değildir.

Paket 6 — Stage D: hood, strobe ve image-space gates

 - [ ] Fixed exposure, gain ve manual white balance ile intended worst ambient condition belirle.

 - [ ] Exterior lux’u ölç ve kaydet.

 - [ ] Dokuz region’da dark-corrected ambient-off/on ratio <=0.10 doğrula.

 - [ ] Nine-region luma min/max ratio >=0.75 doğrula.

 - [ ] Mean luma 40–205 doğrula.

 - [ ] White clipping <=0.002, black clipping <=0.001 doğrula.

 - [ ] 18% gray temporal SNR >=20 dB doğrula.

 - [ ] Light branch average <=20 W, complete module average <=60 W doğrula.

 - [ ] İki saatlik thermal testte image gates’in drift etmediğini doğrula.

 - [ ] Wet-leaf/wet-soil paired glare sahnesi kaydet.

 - [ ] Polarization OFF baseline’ı önce değerlendir.

 - [ ] Yalnız trigger oluşursa crossed-polarization A/B’sini çalıştır.

 - [ ] Acceptance: tek bir current setpoint tüm image, power ve thermal kapılarını aynı anda geçer; aksi halde light/hood mimarisi reddedilir.

Paket 7 — Stage E: motion, observation ve RTX 3090 compute

 - [ ] 0.5 m/s ve 1.0 m/s hareket testleri yap.

 - [ ] 170 µs exposure’da blur <=0.75 px doğrula.

 - [ ] 1.0 m/s ve 12 Hzte action-safe region içinde en az beş geçerli gözlem doğrula.

 - [ ] Tek camera / 15 Hz pipeline’da acquisition, tracking ve result transfer’i birlikte ölç.

 - [ ] End-to-end p95 <=66.6667 ms doğrula.

 - [ ] Deadline miss sayısını 0 doğrula.

 - [ ] Frame drop sayısını 0 doğrula.

 - [ ] Testin exact RTX 3090, model checkpoint ve pipeline component identity’sini kaydet.

 - [ ] Acceptance: Stage E PASS olmadan 20 Hz, ikinci kamera veya controlled capture açılmaz.

Paket 8 — Minimal challenger A/B

 - [ ] 15 Hz baseline A–E PASS olmadan 20 Hz challenger çalıştırma.

 - [ ] 20 Hz challenger’da p95 <=50 ms, zero miss ve zero drop şartını uygula.

 - [ ] 20 Hz kalırsa 15 Hz profile’a rollback et.

 - [ ] Polarization OFF baseline olmadan ON challenger’ı seçme.

 - [ ] Polarization ON için glare reduction >=50% ve tüm diğer D gates PASS şartını uygula.

 - [ ] BAS veya FLIR trigger koşullarını ayrı decision record’da doğrulamadan kamera satın alma.

 - [ ] Camera challenger alınırsa full A–E’yi yeni unit için baştan çalıştır.

 - [ ] Acceptance: her challenger ya açıkça promoted ya da rejected olur; “incelemeye devam” durumu bırakılmaz.

Paket 9 — Frozen capture profile ve handoff

 - [ ] Seçilen exact camera/lens/host/power/hood/light profile’a unique capture_profile_id ver.

 - [ ] rig_id, camera_id, strobe_profile_id ve component serial/order identity’lerini bağla.

 - [ ] Working distance, FOV, focus, aperture, exposure, gain, white balance ve pixel format’ı freeze et.

 - [ ] Physical receipt’te evidence_kind: physical_bench, deployment_evidence: true, synthetic_fixture: false doğrula.

 - [ ] Her measured stage için en az bir mevcut ve SHA-256 doğrulanmış artifact bağla.

 - [ ] A–E’nin tamamını PASS olmadan controlled capture durumunu READY yapma.

 - [ ] Handoff durumunu yalnız FROZEN_FOR_CONTROLLED_CAPTURE olarak yaz; product GO veya chemical GO yazma.

 - [ ] Acceptance: downstream capture audit exact A–E result path ve SHA-256’ya bağlanabilir.

Exact validation özeti
Stage	PASS için decisive evidence
A	Exact PRO/C23 identity, external power, locking cable, dedicated USB root, güncel quote
B	10,000 trigger; zero missing/duplicate/invalid/stale/drop/throttle; timing, droop ve thermal sınırları
C	Installed window ile 27/27 hücre; FOV, GSD, 41/82 px, MTF50 ve reprojection
D	Dokuz-region ambient, uniformity, luma, clipping, SNR, power ve thermal PASS
E	0.5/1.0 m/s, <=0.75 px; >=5 gözlem; 15 Hz p95 <=66.6667 ms; zero miss/drop

Validation sonucu:

A–E PASS: FROZEN_FOR_CONTROLLED_CAPTURE.

A–D PASS, E FAIL: görüntü kalitesi kabul edilebilir fakat ürün capture pipeline’ı hazır değildir.

A–C PASS, D FAIL: açık ortam/ışık mimarisi reddedilir; kamera yükseltmesi otomatik tetiklenmez.

C FAIL: lens/FOV/focus/window mimarisi reddedilir; digital resize ile kapatılamaz.

B FAIL: transport/power/trigger mimarisi reddedilir; image score ile override edilemez.

Missing artifact veya hash mismatch: NOT_MEASURED/FAIL.

Synthetic fixture PASS: yalnız evaluator mechanics PASS; deployment evidence değildir.

Değişiklik ve yeniden doğrulama sözleşmesi
Değişiklik	Geçersiz olan minimum stage’ler
Kamera modeli, power yolu, host, USB root veya cable	A–E
Lens, mount, working distance, focus, iris veya protective window	C–E
Exposure, trigger rate veya pixel format	B–E
Hood, skirt, diffuser, LED, driver veya polarizer	D–E
Camera/light relative geometry	C–E
Tile/halo/action-safe region	C ve E; downstream capture profile
RTX 3090 pipeline veya compute scheduling	E
İkinci kamera veya camera pitch	Her bay için A–E; ayrıca overlap ve multi-module E
Sadece cosmetic exterior değişiklik	Optical path, thermal ve hood integrity etkilenmiyorsa yeniden test gerekmez; etki belirsizse D–E

Bir component değiştirilip eski receipt kullanılmaz.

Rejected alternatives

İlk proof’ta iki kamera.

Tek RTX 3090’a kanıtsız iki kamera yüklemek.

Sadece kamera gövdesi fiyatına göre BAS’ı default seçmek.

Daha pahalı olduğu için FLIR’ın otomatik daha iyi olduğunu varsaymak.

Vendor minimum recognition boyutunu ürün minimum müdahale boyutu saymak.

10 mm chart görünürlüğünü 10 mm weed F1 kanıtı saymak.

Dijital resize ile eksik optik ayrıntı üretmeye çalışmak.

Rolling shutter veya auto-exposure consumer camera.

Open hood/ambient-only capture.

Polarization’ı paired test olmadan baseline’a eklemek.

Ortalama dokuz-region skoruyla kötü köşe veya canopy plane’i gizlemek.

Physical A–E olmadan gerçek veri toplamak.

Physical A–E PASS’i kimyasal ateşleme onayı olarak sunmak.

Material riskler ve kontrolü
1. Light/hood aynı anda SNR, glare ve thermal kapılarını geçmeyebilir

Kontrol:

Önce current sweep.

Sonra diffuser/hood geometry düzeltmesi.

Elektrik ceiling veya sıcaklık sınırı yükseltilmez.

Bir bounded remediation sonrasında yine geçmiyorsa light/hood architecture re-plan edilir.

2. 20 mm downstream başarısı donanımdan çok domain/model kaynaklı olabilir

Kontrol:

Kamera challenger yalnız paired alternate-image kanıtı varsa açılır.

Başarısız track’ler size, region, plane, blur, glare ve luma binlerinde analiz edilir.

Hata bu image factors ile ilişkisizse donanım değiştirilmez; konu model/data parçasına geri gider.

3. BAS tasarrufu saha güvenilirliğinden daha düşük değerli olabilir

Kontrol:

İlk proof PRO.

BAS yalnız production-scale economic trigger veya supply blocker ile.

Exact host ve USB lane değişirse test baştan.

4. Production environmental envelope tanımsızdır

Kontrol:

Bu plan IP veya vibration sertifikası iddia etmez.

Intended kullanım 5–40°C, kontrollü proof hood ve ölçülmüş ambient challenge ile sınırlıdır.

Rain, washdown, ağır dust veya vibration zorunlu hale gelirse ayrı ruggedization re-plan tetiklenir.

5. Tedarik ve fiyat kanıtı hızla bayatlar

Kontrol:

Public price yalnız karşılaştırmadır.

Her satın almadan hemen önce exact quote ve lead time yenilenir.

Supply blocker oluşmadan FLIR stok spekülasyonuyla alınmaz.

Rollback

Her A/B’den önce son geçen profile’ın config, component identity ve receipt hash’i korunur.

Challenger bir mutlak kapıyı kaybederse son geçen baseline’a dönülür.

20 Hz başarısızsa 15 Hz’e dönülür.

Polarization başarısızsa OFF’a dönülür.

BAS başarısızsa PRO external-power baseline’a dönülür.

Cost-down hood/light değişikliği başarısızsa son geçen physical assembly geri yüklenir.

Rollback sonrası değişiklikten etkilenen stage’ler yeniden doğrulanır; eski artifact’ların yeni profile’a taşınması yasaktır.

Stopping rules

Tek PRO baseline A–E PASS olur ve hiçbir challenger trigger’ı oluşmazsa kamera araştırması durur.

Baseline PASS sonrasında yalnız “belki daha iyi” gerekçesiyle FLIR veya ikinci kamera alınmaz.

Hiçbir strobe current setpoint tüm D kapılarını aynı anda geçmezse elektrik ceiling artırma denemesi durur; mimari re-plan edilir.

Bir bounded remediation sonrasında aynı decisive stage tekrar FAIL olursa tuning durur.

20 mm altı ürün vaadi, dedicated gerçek target-rig evidence gelene kadar açılmaz.

20 Hz p95/zero-miss kapısını geçmezse 15 Hz frozen kalır.

Tek modül A–E ve explicit swath ihtiyacı olmadan multi-camera planlanmaz.

Vendor marketing metriği comparable P/R/F1/crop-hit evidence olmadığı sürece karar skoruna girmez.

Physical A–E PASS sonrası bu parça controlled-capture handoff ile kapanır; model eğitimi veya kimyasal ürün onayına genişlemez.

Re-plan trigger’ları

Aşağıdakilerden biri oluşursa bu plan aynı mimariyi zorlamaz:

PRO veya C23 proof takviminde tedarik edilemiyor.

474–484 mm FOV, 520–590 mm içinde exact lens ile elde edilemiyor.

27 hücrenin herhangi birinde 20 mm <82 px veya MTF50 kapısı kalıcı olarak kaybediliyor.

Hiçbir light operating point D kapılarının tümünü geçmiyor.

170 µste 1.0 m/s motion blur >0.75 px.

Tek camera 15 Hz p95 veya zero-miss kapısını geçmiyor.

Ürün hızı >1.0 m/s oluyor.

Gerekli swath tek 0.5 m module’u aşıyor.

Intended sıcaklık 5–40°C dışında oluyor.

Sertifikalı ingress, washdown, dust, shock veya vibration gereksinimi geliyor.

Gerçek target-rig sonuçları, 20 mm sınıfındaki hataların region/GSD/blur/glare ile sistematik ve causal ilişkisini gösteriyor.

Nozul footprint veya crop-safety sözleşmesi minimum service size’ı 20 mmden farklı bir değere zorluyor.

Camera/lens EOL veya interface değişimi oluşuyor.

Tamamlanma kriteri

Bu plan yalnız aşağıdakilerin tamamında tamamlanmış sayılır:

Bir adet exact PRO/C23 proof module kurulmuştur.

Physical A, B, C, D ve E ayrı ayrı measured/PASStir.

Tüm artifact’lar mevcut ve SHA-256 doğrulanmıştır.

Exact capture profile dondurulmuştur.

Minimum ilk service class 20 mm olarak korunmuştur.

BAS/FLIR/20 Hz/polarization/multi-camera seçeneklerinin her biri ya tetiklenmemiş ya da açıkça promoted/rejected edilmiştir.

Controlled target-rig capture handoff’u exact A–E result hash’ine bağlanmıştır.

Status yalnız FROZEN_FOR_CONTROLLED_CAPTUREtır.

Real track-action GO, dry-marker GO ve chemical-fire GO bu plan tarafından iddia edilmemiştir.
