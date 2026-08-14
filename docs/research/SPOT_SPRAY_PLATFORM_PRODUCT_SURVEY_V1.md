# Spot-spray platform ve ürün mimarisi survey V1

Durum: **PRE_REAL — ARCHITECTURE_SELECTED_HOST_PENDING**

Karar tarihi: **2026-08-14**

Dış kaynak erişim tarihi: **2026-08-14**

Planner dayanağı:
[part-spot-spray-platform-product-adaptive-plan.md](../plans/part-spot-spray-platform-product-adaptive-plan.md)

> Bu belge satın alma, imalat, kontrollü veri toplama, dry-marker, kimyasal
> püskürtme, saha performansı veya otonomi yetkisi vermez. Exact traktör,
> boom, tarla, yıllık kullanım ve işletme maliyeti sağlanmadığı için fiziksel
> host **çözülmemiştir**. Hiçbir boş değer sıfır sayılmamıştır.

## 1. Karar

### Proof baseline

İlk bir-bay proof için **manuel sürülen traktörün arka üç-nokta askısında
rijit proof toolbar + taşıyıcıdan bağımsız çıkarılabilir bay cassette** seçildi.

Bay cassette kamera/hood ile müdahale datumunu aynı lokal rijit frame üzerinde
tutar. Zemin takibi bu frame ile traktör adaptörü arasında pasif
paralelogram/dikey kızak ve gauge wheel ile yapılır. Bir lokal, ground-contact
quadrature encoder baseline travel kaynağıdır. Traktör GPS'i, display speed'i
ve host-arrival timestamp kontrol otoritesi değildir.

Bu seçim bir **Codex mühendislik çıkarımıdır**; fiziksel ölçüm sonucu değildir.
Nedeni, bir kamera/15 Hz dondurulmuş proof'u yeni şasi, tahrik, direksiyon,
fren, yol lojistiği veya otonomi kapsamı açmadan taşıyan en küçük geri
döndürülebilir topoloji olmasıdır.

### Scale-up baseline

Çok-bay ölçek için tercih **exact-host-qualified existing-boom retrofit**tir.
Her kamera ve müdahale datumunu booma ayrı ayrı bağlamak yasaktır; boom,
tekrarlanan lokal ground-following bay cassette'leri taşır. Exact boomun lokal
yük/moment, fold/deploy tekrar edilebilirliği, kablo, güç, compute ve TCO
kapılarından biri eksikse aday qualified değildir.

Bu koşulları sağlayan boom bulunmazsa dondurulmuş fallback, aynı cassette'leri
taşıyan **manuel traktörle çekilen dedicated trailed modular carrier**dır.
Bir-bay A–E ve ikinci bağımsız compute kanıtından sonra iki-bay arka toolbar
yalnız replication bridge olabilir; geniş ürün sonucu değildir.

### Challenger'lar

- **Ön üç-nokta:** yalnız arka konum wheel-track/canopy disturbance,
  visibility, clearance, registration, güç veya güvenlik kapısını exact hostta
  geçemezse açılır.
- **Standalone self-propelled:** kapalıdır. Ancak bütün traktör/boom/trailer
  yolları maddi access/compaction/host kapısında kalır, owner utilization
  sağlanır, manuel kontrol edilebilir sourced base bulunur ve otonomi tasarrufu
  yazmadan beş-yıllık TCO en iyi eligible alternatifi en az %20 geçerse ayrı
  safety/drive part'ı olarak yeniden açılır.

~~~text
ONE-BAY PROOF
manual tractor
    └── rear 3-point adapter + rigid proof bar
          └── passive ground-following interface + gauge wheel encoder
                └── removable local bay cassette
                      ├── frozen camera / hood / light interface
                      ├── local compute / power / USB root
                      └── fixed intervention datum (chemical disabled)

SCALE AFTER ONE-BAY A–E
exact available boom passes every hard gate?
    ├── yes → repeated local cassettes on qualified existing boom
    └── no  → dedicated trailed modular carrier
~~~

## 2. Kanıt sınırı ve yöntem

Karar ağırlıklı skorla verilmedi. Sıra şöyledir:

1. frozen interface hard gates;
2. exact-host structural ve operational eligibility;
3. kaynak eksiksizliği;
4. aynı senaryoda beş-yıllık TCO aralığı;
5. entegrasyon karmaşıklığı ve geri döndürülebilirlik;
6. ±%10 TCO bağında daha az yeni şasi/safety joint'i olan deterministik seçim.

Her dış sayı şu sınıflardan biriyle etiketlenir:

- **repo_frozen:** bu deponun hash-kilitli kontratı;
- **manufacturer_primary:** exact vendor ürün sayfası/manual/brochure;
- **primary_study:** hakemli çalışma veya kurumsal araştırma kaydı;
- **standard_or_regulation:** ISO veya resmî mevzuat sayfası;
- **engineering_calculation:** kaynak girdilerden yeniden hesap;
- **engineering_screen:** quote öncesi geniş aralık; satın alma/TCO gerçeği değil;
- **vendor_outcome:** vendor'ın kendi koşullu sonuç iddiası; bizim metriğimiz değil.

Vendor recognition, hit-rate, placement, kill, chemical-saving, ha/h ve ROI
birbirine veya bizim instance-segmentation P/R/F1, crop-hit ve deposition
kapılarımıza dönüştürülmedi.

## 3. Değiştirilmeyen upstream kontrat

| Arayüz | Dondurulmuş değer | Platform sonucu |
|---|---:|---|
| Proof camera count | 1 | İlk carrier tam bir aktif bay taşır |
| Action-safe swath | ≥444,375 mm | Wheel, skirt ve yapı bu alanı kapatamaz |
| Multi-bay center pitch | ≤430 mm | Cassette datumları bunu mekanik olarak sınırlar |
| Calibrated overlap | ≥10 mm | Nominal boom width bunun yerine geçmez |
| Hood plan | tek bayda ≥600×600 mm | Bare-camera taşıyıcı kabul edilmez |
| Hız | 0–1,0 m/s; testler 0,5 ve 1,0 m/s | Gear/transmission iki hızı stabil tutmalı |
| Pozlama / acquisition | 170 µs; hard min 12, baseline 15 Hz | 20 Hz ve ikinci kamera kapalıdır |
| Kamera yolu | dedicated USB3 root, locking cable ≤3 m | Lokal/distributed compute gerekir |
| Capture module power | ≤60 W average, compute hariç | Host supply ayrı ölçülür |
| Measured GPU reference | RTX 3090, 350 W board; 750 W system PSU reference | Bunlar whole-vehicle draw değildir |
| Encoder | ≤1 mm/count; scale error ≤1 mm/m | Display/GPS actuation schedule etmez |
| Trigger–encoder | p95 ≤100 µs; max ≤250 µs | Aynı hardware event ve real-time clock |
| Encoder stale | >5 ms → no-fire | Ağ/host timestamp fallback yok |
| Homography | p95 ≤1 mm; max ≤2 mm | Carrier deflection calibrationı bozamaz |
| Daily registration drift | >2 mm → no-fire | Fold/mount state kimliğe bağlıdır |
| Camera–intervention offset | fiziksel ölçüm; CAD varsayımı yasak | İki datum aynı lokal cassette'te kalır |
| Dry-marker error | p95 ≤5 mm; max ≤10 mm | Bugün ölçülmemiş; READY üretmez |
| Safety | E-stop strobe ve valve-enable'ı hard-cut; watchdog no-fire | Host faultları actuation enable bırakamaz |
| Chemical state | disabled | Existing sprayer donanımı readiness devretmez |

Kaynak kimlikleri:

| Repo kaynağı | SHA-256 |
|---|---|
| [Ürün görüntüleme kararı](../SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md) | c4b7ee5d77fb897576c322a35ab820d882986a096eff225a5364f354b2d0269f |
| [Capture optimization V2](../../configs/deploy/spot_spray_capture_optimization_v2.yaml) | f9fd1cbed95118b4606199e9b67b317c07384e2cb063b60a00e5466848f657e9 |
| [Rig acceptance runbook](../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md) | 9b73fb34741d8862f27abc4aab30e42268fadb2ad05233d3b201f098fb1acb78 |
| [Compute summary](../results/spot_spray_deploy_compute_summary_v1.json) | b03898f35891e304631bfb410089aefdea7f4c5e339f4a9ccef27dc947d28804 |
| [Halo compute summary](../results/spot_spray_deploy_compute_halo_summary_v1.json) | 945c1e43ed9e672d58cc44a57a6a046f202bb285a43b9f385751e297e22de4e7 |
| [Integrated contract release](../SPOT_SPRAY_INTEGRATED_CONTRACT_RELEASE_V1.md) | ad867317332dc2421188bad5903b47e6c0deeb08912243103d74e1ead5d426ad |

Bu kaynakların taşıyıcı-relevant ortak base commit'i
509aeef8189dfa50dbcba973e871b0d41febe239'dur.

## 4. Topoloji karşılaştırması

| Topoloji | Crop erişimi / zemin | Tracking–nozzle geometri | Hız / swath ve compute | Güç / servis / transport | Ek safety kapsamı | Karar |
|---|---|---|---|---|---|---|
| Arka 3-point tek-bay toolbar | Lane wheel-track dışında seçilmeli; gauge wheel lokal height sağlar; traktörün hedefi önce ezmesi/örtmesi exact-host gate'idir | En az joint: kamera ve müdahale aynı cassette; rigid local +X | 444,375 mm; yalnız 0–1 m/s, 1 kamera/15 Hz | Mevcut traktör hizmeti kullanılabilir; lift/transport lock gerekir | Manuel sürüş; hitch lift/reverse no-fire | **Proof seçildi; host pending** |
| Ön 3-point tek-bay | Hedefi lastikten önce görür; fakat front hitch, ballast, visibility ve frontal hazard ekler | Lokal cassette korunursa iyi; daha uzun güç/data route riski | Aynı tek-bay kontrat; hız avantajı yok | Front service ve transport envelope exact-host bağımlı | Front collision/visibility risk assessment | Trigger-only challenger |
| Existing-boom retrofit | Geniş ürün için crop clearance/terrain-follow avantajı olabilir; boom flex/fold risktir | Her bay lokal camera–datum frame ve ground-follow ister; global boom transform yeterli değil | En iyi reuse ölçeği; her bay ≤430 mm ve ayrı compute/USB kanıtı | Fold, harness, removal, host downtime; exact local load rating zorunlu | Fold/deploy state, hard stop, calibration identity | **Scale tercih; conditional** |
| Rear 3-point iki-bay toolbar | Dar/orta sıra proof'u; hitch moment hızla büyür | Rigid iki lokal cassette; overlap fiziksel gate | 874,375 mm; ikinci compute kapalı olduğu için bugün blocked | Tek hostta kolay servis; mass/CG yeniden hesap | Bay-local isolation + shared E-stop | A–E sonrası bridge |
| Dedicated trailed modular | Chassis/section height tasarlanabilir; drawbar yaw, roll, headland ve soil traffic ekler | Lokal section frame + trailer encoder; articulation tek rigid transform sayılamaz | 4–8 bay mümkün ama compute/power ayrıca büyür | Axle, drawbar, brake, lights, fold, storage ve road transport yeni | Trailer deploy/articulation interlocks | **No-boom fallback** |
| Standalone self-propelled | Daha düşük tekil mass mümkün; fakat compaction mass/contact pressure/traffic/neme bağlıdır | Lokal geometri iyi olabilir; drive control artık sistemin parçasıdır | Düşük hız proof'a uyar, work-rate ve lojistik utilization'a hassas | Yeni propulsion, steering, braking, energy, recovery, service ve field transport | ISO 18497 sınıfı autonomy scope açılabilir | Closed challenger |

### Rear proof mekanik sınırı

- Exact hitch category, lift-rating measurement point, axle loads, ballast,
  wheel track, underbody clearance ve top-link geometry kayıtlı olmadan build
  authority yoktur.
- Kamera–müdahale frame'i operasyon sırasında articulate etmez. Pasif vertical
  compliance onun üstünde, carrier adapter tarafındadır.
- Gauge wheel ve encoder action-safe FOV dışındadır.
- Operating hard stop, sensed deployed state, mechanical transport lock,
  anti-sway ve accessible E-stop zorunludur.
- Rear bay lane'i lastik iziyle kesişirse topoloji o hostta fail olur; front
  challenger açılır.

### Boom scale sınırı

- Boom yalnız gross lift/width/transport sağlar; kamera–nozzle reference olmaz.
- Her section exact load path, hard-seated deployed state, local ground follow,
  local compute/USB zone, fold sensor ve calibration identity taşır.
- Fold joint hareketinde, hard stopta değilken veya calibration ID yanlışken
  affected bay no-fire olur.
- Komşu bay failed bay'in alanını otomatik devralmaz.
- Existing tank/pump/nozzle hattı ayrı ve disabled kalır.

### Trailed fallback sınırı

Trailer; chassis, axle, drawbar, wheel, section, fold, brake/light, guards,
power generation/conversion, encoder, E-stop, storage ve intended-jurisdiction
transport yükümlülüklerini TCO'ya ekler. Drawbar yaw ve independently
ground-following section'lar ölçülmeden tek shared homography kullanılamaz.

## 5. Compute, güç ve latency ölçek sınırı

64 px halo compute proxy'sinde tek kamera/batch-4 ölçümü:

- mean 46,063 ms;
- p95 52,680 ms;
- yaklaşık 21,709 module frame/s;
- camera acquisition, temporal tracking, controller, valve ve spray physics
  **hariçtir**.

15 Hz frame periodu 66,667 ms'dir; compute-only p95 sonrası yalnız yaklaşık
13,987 ms kalır. Bu bir end-to-end PASS değildir. İki kamerayı seri varsayan
conservative p95 105,359 ms olur ve iki kameranın 15 Hz toplam servis talebi
30 module frame/s'dir; mevcut 21,709/s proxy bunu qualify etmez.

| Bay | Safe swath (mm) | Capture ceiling (W, compute hariç) | RTX 3090 board-reference envelope | 750 W PSU reference | Bugünkü compute state |
|---:|---:|---:|---:|---:|---|
| 1 | 444,375 | ≤60 | 350 W | 750 W | 15 Hz E2E hâlâ fiziksel gate; tek desteklenen baseline |
| 2 | 874,375 | ≤120 | 700 W | 1,5 kW | Ayrı lane veya yeni benchmark olmadan blocked |
| 4 | 1.734,375 | ≤240 | 1,4 kW | 3,0 kW | Planning envelope only |
| 8 | 3.454,375 | ≤480 | 2,8 kW | 6,0 kW | Planning envelope only |

Çarpımlar ölçülmüş araç tüketimi değildir; her bay için bağımsız mevcut
donanım varsayımının güç/termal sonucunu görünür kılan konservatif planlama
zarfıdır. Yeni multi-camera benchmark bu zarfı değiştirebilir.

### Control path

~~~text
manual carrier motion
  → deployed / direction / E-stop / power-valid gates
  → one real-time hardware event
      ├── latch signed encoder position
      ├── trigger identified camera
      └── trigger strobe
  → identified compute lane and calibration
  → track/crop-veto result tied to frame + encoder
  → local measured-offset deadline scheduler
  → dry output only when every state is valid
~~~

Authoritative schedule:

~~~text
command_encoder_mm =
    capture_encoder_mm
  + measured_camera_to_intervention_offset_mm
  - speed_mm_s × measured_valve_onset_latency_s
~~~

Reverse, stop ambiguity, lift, fold, stale encoder, frame drop, calibration
mismatch, identity collision, deadline miss, brownout veya controller reboot
pending komutları iptal eder.

## 6. Swath ve geometric capacity

N bay ve p metre center pitch için:

~~~text
safe_swath_m = 0.444375 + (N - 1) × p
gross_geometry_ha_h = safe_swath_m × speed_m_s × 0.36
effective_geometry_ha_h = gross_geometry_ha_h × field_efficiency
~~~

Koşullar: N≥1, p≤0,430 m, calibrated overlap≥0,010 m ve her bay/overlap
physical gate PASS. Maximum pitchte yeniden hesap:

| Bay | Safe swath | 0,5 m/s gross | 1,0 m/s gross |
|---:|---:|---:|---:|
| 1 | 0,444375 m | 0,079988 ha/h | 0,159975 ha/h |
| 2 | 0,874375 m | 0,157388 ha/h | 0,314775 ha/h |
| 4 | 1,734375 m | 0,312188 ha/h | 0,624375 ha/h |
| 8 | 3,454375 m | 0,621788 ha/h | 1,243575 ha/h |

Bunlar turning, refill, overlap loss, abstention, setup, cleaning, downtime,
terrain, operator veya crop window içermeyen **geometri hesaplarıdır**; saha
kapasitesi iddiası değildir.

## 7. Crop access, compaction, clearance ve topography

Standalone'ın otomatik olarak toprağa daha iyi olduğu varsayılmadı. Doğru
karşılaştırma total mass yanında per-wheel load, tire/contact area, inflation,
axle distribution, pass count, controlled traffic, soil texture ve moisture
ölçer.

- 200 ha İsveç clay-farm simulation'ında hafif elektrikli otonom sistemin
  toplam model maliyeti 385'ten 258 EUR/ha'a düştü ve conventional senaryoda
  compaction model maliyetin %20'siydi; yazarlar compaction faydasının tek
  başına sistem değişimini gerekçelendirmediğini açıkça söyler
  ([Lagnelöv ve ark., 2023](https://doi.org/10.1016/j.atech.2022.100156),
  primary simulation).
- 2023 seeding/weeding karşılaştırmasında robotun saatlik maliyeti daha düşük
  görünürken 6 m traktör yüksek field capacity nedeniyle operation totalinde
  %46 daha düşük sonuç verdi
  ([AgriEngineering 5(1), 20](https://doi.org/10.3390/agriengineering5010020),
  senaryo çalışması). Bu sonuç spot-spray TCO değildir.
- 2026 AgBot analizi iki farmdaki 61 maize field operasyonundan model kurdu;
  simulated total ortalama 73 EUR/ha idi ve field size, route distance ile
  access logistics varyansını belirledi
  ([Jorissen & Recke, 2026](https://doi.org/10.1016/j.atech.2026.101913)).
  Slope ayrıca ölçülmedi; sonuç bizim farm'a taşınamaz.
- FarmDroid FD20 factsheet'i exact üründe standard mass 1.250 kg, extras ile
  1.800 kg ve active front wheel olmadan önerilen pitch/roll'u %8/%5, onunla
  %10/%10 verir
  ([2026 factsheet](https://farmdroid.com/wp-content/uploads/Factsheet-FD20-metricimperial-2026.pdf)).
  Bunlar bizim platform limitimiz değil, topography'nin ürün-spesifik
  doğrulanması gerektiğine örnektir.

Exact host survey şu alanları null bırakmadan ya da explicit unresolved olarak
taşır: crop/row spacing, crop height window, wheel tracks, lane width, ground
clearance, approach/departure, local slope, roll, rut, residue/canopy
occlusion, soil moisture, tire/load ve headland turning envelope.

## 8. Ticari ve araştırma sistemi audit'i

| Sistem | Platform / exact vendor fact | Mimari ders | Metrik semantiği ve sınır |
|---|---|---|---|
| John Deere See & Spray | Premium upgrade MY18–MY26 R-Series ve 400/600 sprayerlarda 90/100/120 ft steel boom ve up to 15 mph; Ultimate için ayrı resmî sayfa 36 kamera bildirir ([Premium](https://www.deere.com/en-us/products-solutions/technology-solutions/precision-upgrades/sprayer-upgrades/see-spray-premium-upgrade), [Sense & Act](https://www.deere.com/en-us/our-company/technology-and-innovation/sense-and-act), erişim 2026-08-14) | Geniş scale, host-integrated distributed vision/compute ister | Width/speed/camera count; bizim F1, safe swath veya compute kanıtı değil |
| Greeneye | Retrofit-first, boom-mounted; 24 kamera, 12 rugged GPU, 144 nozzle, 15 mph ve dual-line vendor mimarisi ([2025-04 brochure](https://greeneye.ag/wp-content/uploads/2025/04/Product-Brochure.pdf)); modüller ISOBUS-compatible ([technology page](https://greeneye.ag/technology/), erişim 2026-08-14) | Existing-sprayer retrofit ve local module deseni scale adayını destekler | 150 ms/vendor ROI/chemical-saving bizim latency/TCO metriğimiz değildir |
| Ecorobotix ARA 620 | Front tank + rear mounted 6,20 m sprayer; 156 nozzle, 6 RGB+3D module, 7,2 km/h; tractor 1.100 kg rear-at-1,2 m ve 1.000 kg front-at-0,8 m taşımalı ([official product page](https://ecorobotix.com/crop-care/ara-620-uhp-sprayer/), erişim 2026-08-14) | Dedicated mounted implementte enclosure, close sensing ve host axle/load hesabı birlikte çözülür | 6×6 cm spray spot ile minimum recognition aynı metrik değildir |
| Carbon LaserWeeder G2 600 | CAT 3 rear 3-point, front PTO generator; 3.266 kg, minimum 3.856 kg lift, 12 module, 36 camera, 240 LED ([official G2 600](https://carbonrobotics.com/laserweeder-g2-600), erişim 2026-08-14) | Module replication ve compute/power/host burden birlikte büyür | 0,61–1,21 ha/h ve up-to kill vendor performance; spray veya bizim model sonucu değil |
| Verdant SharpShooter | Tractor yaklaşık 3.000 lb lift ve 6,5 GPM hydraulic ister; modular boxes, folding gooseneck transport, up to 7 acre/h ([official FAQ](https://www.verdantrobotics.com/faqs), erişim 2026-08-14) | Local replaceable module, predictive tracking ve serviceability önemli | Placement/acre/h/ROI vendor claim; recognition P/R veya bizim TCO değil |
| ROBOTTI LR | Self-propelled implement carrier; vendor current page'i multi-purpose carrier, standard implement kullanımı, 1,2 t lift, optional PTO ve refuel öncesi up to 60 h bildirir ([official product page](https://agrointelli.com/robotti/lr/), erişim 2026-08-14) | Standard implement interface standalone utilizationı artırabilir ama yeni chassis/safety scope açar | Vendor envelope; mass, contact pressure, field logistics ve bizim cost benefit'imiz değil |
| FarmDroid FD20 | Solar standalone; 3,5 m, 950 m/h, up to 6 ha/day, 1.250–1.800 kg ([2026 factsheet](https://farmdroid.com/wp-content/uploads/Factsheet-FD20-metricimperial-2026.pdf)) | Düşük hız ve season-long field residence farklı ekonomik modeldir | Daily capacity conditions'a bağlı vendor metric; bizim swath/TCO değil |
| Naïo ORIO | Electric standalone tool carrier; retained vendor page 700 kg lift, iki track-width aralığı ve up to 9 ha/day bildirirken ürünün Naïo SAS tarafından **2026-06-15'ten beri satılmadığını ve desteklenmediğini** de açıkça bildirir ([official retained page](https://www.naio-technologies.com/en/orio-robot/), erişim 2026-08-14) | Carrier yeteneği kadar product-lifecycle ve service continuity de TCO hard gate'idir | Vendor capacity bizim work-rate değil; current no-sale/no-support durumu bu exact ürünü aday base olmaktan çıkarır |
| Robotti plant-specific sprayer study | Robotti üzerine 4×2048×1536 camera, black rubber curtain, diffuse 6500 K LED ve aynı bitkiyi üç görmeye kadar overlap ([Ruigrok ve ark., 2020](https://doi.org/10.3390/s20247262)) | Enclosure + repeat views + implement carrier deseni doğrudan ilgili | Paper'ın volunteer-potato field outcome'u bizim crop/domain veya GO sonucu değildir |

Sonuç: leading ürünlerde tek bir evrensel platform yoktur; iki tekrarlanan
desen vardır: geniş tarla için mevcut traktör/boom üzerinde distributed local
module ve specialist crop için düşük hızlı standalone carrier. Bizim frozen
bir-bay compute ve host-belirsizliği ilkini proof'ta dar rear toolbar, scale'de
qualified boom olarak destekler; standalone'ın ek safety/TCO yükünü bugün
haklı çıkarmaz.

## 9. Modüler ürün arayüzü

### Bay cassette owns

- hood/imaging support ve çalışma yüksekliği fine adjustment;
- rigid camera-to-intervention datum ve +X travel, +Y lateral, +Z up frame;
- local identity plate, bay ID, calibration/fiducial locations;
- ground-follow interface connection;
- dedicated USB-root/compute mounting zone ve ≤3 m route;
- cable strain relief ve local safety-state input.

### Carrier owns

- tractor/boom/trailer connection, gross lift ve transport;
- coarse operating height, fold/deploy ve mechanical locks;
- host power source, regulated conversion boundary ve E-stop routing;
- signed travel encoder installation;
- axle/hitch/drawbar/boom structural proof;
- operator control, guards, service access ve transport envelope.

### Other lanes own

- Sensor/light lane: camera, lens, spectrum, hood optical internals,
  diffuser/polarization.
- Intervention lane: nozzle, valve, pressure, tank, footprint, deposition,
  crop injury ve chemical enable.

Carrier inconvenience başka lane'in seçimini reopen etmez; carrier reddedilir
veya yeniden tasarlanır.

### Kalibrasyon invalidation matrisi

| Değişiklik / olay | Geçersiz olan kanıt | Yeniden açılma koşulu |
|---|---|---|
| Cassette sök-tak veya mekanik darbe | Registration identity ve daily drift | Identified mount, torque/seat check ve daily registration PASS |
| Kamera, lens, window, hood veya light support hareketi | Optical C; geometry E; downstream F | İlgili C–F kapıları yeni revision ile tekrar PASS |
| Intervention datumunun hareketi | Measured offset, E ve F | Yeni fiziksel offset + E registration + dry-marker F |
| Ground-follow joint, gauge wheel veya operating height değişimi | Height/DOF D, geometry E ve F | D–F tekrarı; CAD tahmini kabul edilmez |
| Encoder wheel/scale/mount değişimi | Scale, direction, timing ve F | ≤1 mm/count, ≤1 mm/m, timing ve F tekrar PASS |
| Boom fold stop, section hinge veya bay seat değişimi | Affected bay identity, registration ve E–F | Hard-seated deployed state + bay-local registration + E–F |
| Compute, USB root veya schedule software değişimi | Latency B ve downstream scheduling | Identified configuration ile 15 Hz E2E B ve gerekli F tekrar PASS |

### Fail-closed davranış matrisi

| Fault/state | Kapsam | Zorunlu davranış |
|---|---|---|
| E-stop, brownout veya safety-controller reset | Bütün carrier | Strobe ve actuation enable hard-cut; pending command sil |
| Lift, transport lock, fold veya deployed-state invalid | Affected carrier/section | No-fire; yeniden seat/identity olmadan arm etme |
| Reverse, direction ambiguity, encoder stale/slip | Affected carrier | No-fire ve bütün scheduled command'ları iptal et |
| Bay absent, duplicate ID veya calibration mismatch | Affected bay | Bay-local no-fire; komşu bay coverage genişletmez |
| Frame drop, compute miss veya deadline miss | Affected frame/bay | Command üretme veya uygulama yok; geç sonucu discard et |
| Camera/data/power connector loss | Affected bay | No-fire; fault latched ve operator-visible olsun |
| Watchdog veya communication timeout | Defined controlled scope | Fail-safe no-fire; host/GPS timestamp fallback kullanma |

## 10. BOM ve TCO

### Bilinen ve bilinmeyen maliyet sınırı

| Kalem | Min–max (USD) | Sınıf | Dahil / hariç |
|---|---:|---|---|
| Frozen one-bay imaging proof, mevcut RTX 3090 reuse | 3.582–7.527 | repo_frozen budgetary range; 2026-08-12 | Camera/lens/light/hood/controller/safety/host integration; tax/shipping ve yeni GPU hariç |
| Rear proof carrier structure | 4.300–14.000 | engineering_screen | Aşağıdaki structural/fabrication allowance; quote değil |
| İlk proof subtotal | **7.882–21.527** | arithmetic screen | Host acquisition/rental, operator, energy, actuator, fluid ve physical testing hariç |
| Yeni compute lane | null | unresolved quote | Multi-bayda sıfır olamaz |
| Intervention lane | null | other-lane unresolved | Nozzle/valve/pump/tank/chemical bu lane'de seçilmez |
| Exact tractor / boom / trailer | null | host unresolved | Inventory/quote gelmeden TCO kapanmaz |

Rear carrier engineering screen'in açık toplamı:

| Carrier-only kalem | Screen (USD) |
|---|---:|
| Exact-host 3-point adapter + rigid proof bar | 1.000–3.500 |
| Passive ground-follow subframe + gauge wheel/encoder bracket | 800–2.500 |
| Transport lock, deployed sensing, guards ve E-stop routing | 500–1.500 |
| Compute/power tray, connector/cable protection | 500–1.500 |
| Engineering, fabrication ve installation labor | 1.500–5.000 |
| **Toplam** | **4.300–14.000** |

Bu aralıklar quote toplama önceliği içindir; exact material, mass, jurisdiction,
labor rate veya vendor quote içermez. Upstream modüldeki encoder electronics,
SELV safety ve host-integration allowance ikinci kez sayılmamıştır.

Scale pre-screen:

~~~text
existing-boom carrier capex =
    qualified retrofit NRE [4k, 15k] engineering_screen
  + N × local carrier subframe [1.5k, 5k] engineering_screen
  + N × frozen bay allowance
  + (N - 1) × new_compute_lane_quote
  + intervention_lane_quote

trailed carrier capex =
    trailer chassis/fold/transport/power [20k, 75k] engineering_screen
  + N × local carrier subframe [1.5k, 5k] engineering_screen
  + N × frozen bay allowance
  + (N - 1) × new_compute_lane_quote
  + intervention_lane_quote
~~~

New compute ve intervention null olduğu için bunlar complete capex aralığı
değildir. Front carrier ve self-propelled için exact base/hitch/ballast/support
quote olmadan sayısal aralık verilmemiştir.

`frozen bay allowance` upstream'de host-integration payı içeren tek parça bir
bütçedir; bu pay ayrıştırılamadığı için scale formülü konservatif olabilir
ve retrofit NRE/subframe ile overlap edebilir. Quote reconciliation bu overlap'i
kalem kalem silmeden formül complete capex sayılmaz.

### TCO kontratı

~~~text
TCO(c,s,Y) =
    incremental_host_capex
  + carrier_capex
  + integration_NRE
  + external_pass_through_capex
  + Y × annual_fixed_cost
  + Y × annual_hours × hourly_variable_cost
  + Y × expected_downtime_cost
  - residual_value

life_area_ha =
    Y × annual_hours × gross_geometry_ha_h × field_efficiency

coverage_cost_per_ha = TCO / life_area_ha
~~~

Required sensitivities:

- bay count 1/2/4/8;
- speed 0,5/1,0 m/s;
- annual hours 100/500/1.000;
- field efficiency 0,50/0,70/0,85;
- owned compatible tractor; rented tractor; owned tractor+qualified boom;
  owned tractor/no boom; no suitable host;
- five years;
- every engineering inference at −%20/nominal/+%20.

Operator cost bütün senaryolarda kalır; otonomi excluded. Chemical saving,
yield, weed-control, crop-damage veya labor-removal benefit'i kredi edilmez.
Sunk owned-host capex incremental capexte sıfır olabilir, fakat host opportunity
ve running cost sıfır olamaz.

### Yalnız bounded proof capex allocation screen

Aşağıdaki tablo complete TCO değildir. Yalnız 7.882–21.527 USD proof
subtotalını 1,0 m/s, %70 field-efficiency ve beş yıla böler; operator, host,
energy, maintenance, downtime ve actuator yoktur.

| Yıllık saat | Beş-yıllık geometric area | Screen capex / ha |
|---:|---:|---:|
| 100 | 55,991 ha | 140,77–384,47 USD/ha |
| 500 | 279,956 ha | 28,15–76,89 USD/ha |
| 1.000 | 559,913 ha | 14,08–38,45 USD/ha |

0,5 m/s aynı varsayımlarda alanı yarılar ve bu screen cost/ha'yı iki katına
çıkarır. Bu tablo ürün ekonomisi veya hedef çiftlik beklentisi değildir; düşük
utilization'ın capex dilution etkisini görünür yapar.

### Break-even ve scale switch

~~~text
break_even_hours =
    (fixed_cost_A - fixed_cost_B)
  / (hourly_cost_B - hourly_cost_A)
~~~

Payda pozitif ve bütün girdiler mevcut değilse sonuç null + reason olur.
Boom ancak exact eligible ve aynı senaryoda retrofit TCO'su trailer'dan %10'dan
fazla yüksek değilse tercih edilir. Boom aralığı trailer'dan >%10 yüksekse
trailer seçilir. Aralıklar ±%10 içinde bağlıysa daha az yeni chassis,
safety-critical subsystem, irreversible NRE ve calibration-changing joint
nedeniyle eligible existing boom kazanır.

## 11. Service, maintenance ve transport

| Alan | Rear proof | Boom scale | Trailed fallback | Standalone screen |
|---|---|---|---|---|
| Günlük | Window/hood/skirt, gauge wheel, encoder, fiducial, connector; registration check | Her bay + fold hard-stop + harness + section identity | Her bay + tires/hubs/drawbar/brakes/lights | Bay + propulsion/energy/navigation/safety |
| Arıza izolasyonu | Tek bay → tüm actuation no-fire | Failed bay local no-fire; coverage genişlemez | Section local no-fire | Drive fault bütün missionı durdurur |
| Sezonluk | Remove/inspect toolbar, lock, corrosion, cable | Install/remove downtime ve recalibration TCO'da | Storage, axle/drawbar inspection | Battery/fuel, drivetrain ve remote-support dependence |
| Transport | Hitch lift + mechanical lock; road claim yok | Folded width/load ve deploy repeatability exact host | Jurisdiction brake/light/guard ve trailer route unresolved | Fieldler arası low-loader/logistics gerekir |
| Service strategy | Standard tractor service + cassette swap | Host dealer + bay spares + section calibration | Custom chassis spares + bay spares | Vendor/base-platform support kritik |

Target service KPIs ancak physical rig sonrası dondurulur: mean repair time,
bay swap time, calibration-after-swap pass rate, cleaning time, frame-drop,
connector faults, encoder drift, fold repeatability ve seasonal setup hours.

## 12. Functional safety ve mevzuat sınırı

Bu bölüm sertifikasyon veya hukuk görüşü değildir.

- [ISO 12100:2010](https://www.iso.org/standard/51528.html) risk
  assessment/reduction metodunu verir; 2022'de confirmed ve ISO sayfasında
  `to be revised` durumundadır.
- [ISO 25119-1:2018](https://www.iso.org/standard/69025.html) agricultural
  safety-related control systems için general principles verir ve mounted,
  trailed, self-propelled kapsar; current edition 2024'te confirmed.
- [ISO 4254-6:2020](https://www.iso.org/standard/70623.html) mounted,
  semi-mounted, trailed ve self-propelled sprayer safety kapsamını tanımlar;
  2026'da revision altındadır.
- [ISO 13850:2015](https://www.iso.org/standard/59970.html) emergency-stop
  design principles referansıdır; 2020'de confirmed current edition'dır.
- [ISO 11783-1:2017](https://www.iso.org/standard/57556.html) mounted,
  towed ve self-propelled implement communication network'ünü tarif eder.
  2023'te confirmed'dır; ISOBUS compatibility safety qualification veya local
  real-time actuation authority değildir.
- Otonomi yeniden açılırsa [ISO 18497-1:2024](https://www.iso.org/standard/82684.html)
  ve obstacle protection için
  [ISO 18497-2:2024](https://www.iso.org/standard/82686.html)
  ayrı safety scope oluşturur. Manuel baseline bunları claim etmez.
- EU market hedeflenirse [Regulation (EU) 2023/1230](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=LEGISSUM%3A4682019)
  genel olarak 20 Ocak 2027'den uygulanır. Target jurisdiction bugün
  unresolved olduğu için conformity route seçilmemiştir.

Minimum fail-closed state set:

carrier_operating_state_valid, transport_lock_released,
hitch_or_section_deployed, fold_state_valid, direction_valid, encoder_valid,
power_valid, estop_clear, bay_present_and_identified ve
calibration_identity_valid. Missing/false/contradictory state no-fire'dır.

## 13. Exact-host intake ve hard gates

### Eksik owner girdileri

- farm/crop/row/area ve yıllık pass sayısı;
- field size/shape/slope/access ve fieldler arası route distance;
- available/rentable tractor make/model/year/configuration;
- hitch category, exact lift point, axle ratings, ballast, wheel track,
  clearance ve stable 0,5/1,0 m/s mode;
- electrical/alternator continuous rating;
- exact boom identity, section geometry, local payload/moment, fold state,
  height control ve cable routes;
- annual operating hours, operator rate, fuel/electricity, maintenance,
  storage, insurance, downtime ve rental/ownership;
- target jurisdiction ve transport route.

Absence sonucu: **HOST_UNRESOLVED_NO_BUILD_AUTHORITY**.

### Candidate hard gates

Bir aday aşağıdakilerin herhangi birinde fail/unknown ise TCO'ya geçmez:

1. exact identity ve primary structural rating;
2. measured mass, CG, load point, operating ve transport axle/moment;
3. safe width/FOV/hood/height ve local ground-follow geometry;
4. 0,5 ve 1,0 m/s, signed direction ve encoder gates;
5. ≤3 m camera cable, dedicated USB root ve proven compute lane;
6. same-event trigger/encoder, measured offset ve deadline abort;
7. fold/lift/reverse/identity/power faults on no-fire;
8. accessible E-stop, transport lock ve deployed-state sensing;
9. dated cost/installation/downtime evidence;
10. chemical-enable path isolated and disabled.

## 14. Challenger triggers

| Geçiş | Açan exact kanıt | Açmayan şey |
|---|---|---|
| Rear → front proof | Rear host capacity yok; safe lane wheel trackte; measured optical/registration/clearance/power/safety fail | Tercih, estetik, katalog speed |
| Passive wheel encoder → radar/optical/fusion | ≤1 mm/count, ≤1 mm/m, timing, stale, direction veya repeatability fail | GPS zaten var |
| One bay → two-bay bridge | Physical A–E PASS + independent compute/new benchmark + exact mass/moment + overlap/hood PASS | İkinci kamerayı satın almak |
| Existing boom → trailer | Exact boom/load yok; fold repeatability/ground follow/cable/power fail; TCO > trailer +%10 | Nominal boom width |
| Trailer → standalone | Bütün tractor routes material fail + utilization + manual base + TCO ≥%20 better after +%20 NRE + separate safety authority | Daha hafif görünüyor, vendor autonomy claim |
| Sensor/light reopen | Yalnız sensor/light lane'in kendi measured challenger gate'i | Carrier'a sığmaması |

## 15. Source ledger

| ID | Tarih / sürüm | Sınıf | Direct source | Bu belgede kullanılan fact | Karar sınırı |
|---|---|---|---|---|---|
| R1 | 2026-08-12 | repo_frozen | [Imaging decision](../SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md) | Bir-bay, safe swath, cost range | Physical A–E yok |
| R2 | 2026-08-12 | repo_frozen | [Capture V2](../../configs/deploy/spot_spray_capture_optimization_v2.yaml) | pitch, power, timing, safety interfaces | Ürün/field claim değil |
| R3 | 2026-08-12 | repo_frozen | [Rig runbook](../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md) | A–F gates | Synthetic fixture physical PASS değil |
| R4 | 2026-08-12 | repo_frozen | [Halo compute](../results/spot_spray_deploy_compute_halo_summary_v1.json) | measured RTX timing | Camera/tracking/actuator excluded |
| R5 | 2026-08-12 | repo_frozen | [Compute summary](../results/spot_spray_deploy_compute_summary_v1.json) | compute evidence lineage ve supported state | Multi-bay qualification değil |
| R6 | 2026-08-12 | repo_frozen | [Integrated release](../SPOT_SPRAY_INTEGRATED_CONTRACT_RELEASE_V1.md) | release status ve closed claims | Physical/chemical GO değil |
| P1a | erişim 2026-08-14 | manufacturer_primary | [John Deere Premium](https://www.deere.com/en-us/products-solutions/technology-solutions/precision-upgrades/sprayer-upgrades/see-spray-premium-upgrade) | compatible model years, boom widths, speed | Vendor/product-specific |
| P1b | erişim 2026-08-14 | manufacturer_primary | [John Deere Sense & Act](https://www.deere.com/en-us/our-company/technology-and-innovation/sense-and-act) | Ultimate camera count ve edge-compute architecture | Premium ile birleştirilmez |
| P2a | 2025-04 | manufacturer_primary | [Greeneye brochure](https://greeneye.ag/wp-content/uploads/2025/04/Product-Brochure.pdf) | retrofit, camera/GPU/nozzle/speed architecture | Vendor latency/ROI ayrı metrik |
| P2b | erişim 2026-08-14 | manufacturer_primary | [Greeneye technology](https://greeneye.ag/technology/) | boom module ve ISOBUS-compatible interface | Safety/real-time qualification değil |
| P3 | erişim 2026-08-14 | manufacturer_primary | [ARA 620](https://ecorobotix.com/crop-care/ara-620-uhp-sprayer/) | mount, width, load, camera/nozzle, speed | Recognition/application claim değil |
| P4 | erişim 2026-08-14 | manufacturer_primary | [Carbon G2 600](https://carbonrobotics.com/laserweeder-g2-600) | hitch, weight, lift, modules, cameras, LEDs | Laser/vendor outcome ayrı |
| P5 | erişim 2026-08-14 | manufacturer_primary | [Verdant FAQ](https://www.verdantrobotics.com/faqs) | tractor services, module/service/transport | Vendor placement/ROI ayrı |
| P6 | erişim 2026-08-14 | manufacturer_primary | [Robotti LR](https://agrointelli.com/robotti/lr/) | multi-purpose carrier, lift, optional PTO, refuel interval envelope | Standalone screen only; mass/contact pressure unresolved |
| P7 | factsheet 2026; model 2025 v2.6 | manufacturer_primary | [FarmDroid FD20](https://farmdroid.com/wp-content/uploads/Factsheet-FD20-metricimperial-2026.pdf) | width, speed, mass, slope | Product envelope, bizim spec değil |
| P8 | status 2026-06-15; erişim 2026-08-14 | manufacturer_primary (retained/stale context) | [Naïo ORIO](https://www.naio-technologies.com/en/orio-robot/) | lift/track/capacity envelope ve explicit no-sale/no-support status | Current candidate base değil |
| S1 | 2020-12-18 | primary_study | [Ruigrok et al.](https://doi.org/10.3390/s20247262) | Robotti sprayer architecture ve system-level evaluation | Başka crop/domain |
| S2 | 2023 | primary_study (scenario) | [Ag robot economics](https://doi.org/10.3390/agriengineering5010020) | Work-rate cost tradeoff | Spot spray değil |
| S3 | 2023, vol. 4, 100156 | primary_study (simulation) | [Light autonomous tractors](https://doi.org/10.1016/j.atech.2022.100156) | Compaction/economics sensitivity | 200 ha Swedish clay simulation |
| S4 | 2026, vol. 13, 101913 | primary_study (empirical cost model) | [AgBot structural costs](https://doi.org/10.1016/j.atech.2026.101913) | 61-field logistics sensitivity | Slope/spot spray yok |
| N1 | 2010; confirmed 2022; revision active | standard_or_regulation (standard) | [ISO 12100](https://www.iso.org/standard/51528.html) | Risk method | Compliance claim değil |
| N2 | 2018; confirmed 2024; revision active | standard_or_regulation (standard) | [ISO 25119-1](https://www.iso.org/standard/69025.html) | Safety-related controls | AgPL seçilmedi |
| N3 | 2020; revision active | standard_or_regulation (standard) | [ISO 4254-6](https://www.iso.org/standard/70623.html) | Sprayer topology safety scope | Full standard audit yapılmadı |
| N4 | 2015; confirmed 2020 | standard_or_regulation (standard) | [ISO 13850](https://www.iso.org/standard/59970.html) | Emergency-stop principles | Safety function design tamamlanmadı |
| N5 | 2017; confirmed 2023 | standard_or_regulation (standard) | [ISO 11783-1](https://www.iso.org/standard/57556.html) | Implement communications scope | Safety/latency authority değil |
| N6 | 2024-07 | standard_or_regulation (standard) | [ISO 18497-1](https://www.iso.org/standard/82684.html) | Autonomous-machine replan scope | Manual baseline'a uygulanmış claim yok |
| N7 | 2024-07 | standard_or_regulation (standard) | [ISO 18497-2](https://www.iso.org/standard/82686.html) | Obstacle-protection replan scope | Manual baseline'a uygulanmış claim yok |
| L1 | 2023; applies 2027-01-20 | standard_or_regulation (regulation) | [EU 2023/1230 summary](https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=LEGISSUM%3A4682019) | EU timing/context | Jurisdiction ve conformity route unresolved |

## 16. Sonuç ve frozen handoff

Bugün en yüksek değerli buildable proof mimarisi:

**manuel traktör + arka üç-nokta rigid toolbar + bir removable,
ground-following local bay cassette**.

En doğru scale mimarisi:

**exact-qualified existing boom üzerinde tekrarlanan lokal cassette'ler**;
boom qualify olmazsa **dedicated trailed modular carrier**.

Bu kararın gücü bir host veya saha başarısı ilan etmesi değil, unknown'ları
fail-closed bırakmasıdır. Exact inventory gelmeden build/purchase yoktur.
Physical bir-bay A–E, end-to-end 15 Hz ve dry-marker F geçmeden ikinci bay veya
actuation yoktur. Deposition/crop-injury kapıları ve ayrı chemical authority
olmadan chemical enable yoktur. Otonomi bu baseline'ın parçası değildir.
