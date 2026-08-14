# Spot-spray sensör/optik survey V1

Durum: **FINAL — PRE_REAL_RESEARCH_ONLY**

Kanıt kontrol tarihi: **2026-08-14**

Bu survey'in sonucu: **RETAIN_RGB_BASELINE**

Terminal survey kararı: **RETAIN_RGB_BASELINE**

Bu belge kontrollü gerçek veri toplamadan önce sensör ve optik seçeneklerini
aynı görev zarfında karşılaştırır. Basler RGB kontrolü kaynağa ve yeniden
üretilmiş hesaba kilitlidir; görünür monochrome, NIR, snapshot
multispektral, RGB+thermal ve RGB+depth exact-stack desk screen'leri
tamamlanmıştır. Tüm modality satırları source-screen edilmiştir; trigger
ledger, camera-count/cost matrisi, source-tier audit'i ve terminal karar
bütünleştirilmiştir.

> Bu araştırma mevcut baseline'ı fiziksel olarak geçirmiş değildir. Satın alma
> yetkisi, fiziksel READY, controlled-capture READY, product/field GO veya
> chemical fire üretmez.

| Yetki / durum | Değer |
|---|---:|
| `purchase_authorized` | `false` |
| `physical_ready` | `false` |
| `controlled_capture_ready` | `false` |
| `field_go` | `false` |
| `product_go` | `false` |
| `chemical_go` | `false` |
| `gpu_work_performed` | `false` |

## 1. Karar ve kanıt sözleşmesi

Terminal survey sonucu yalnız `RETAIN_RGB_BASELINE`,
`BOUNDED_CHALLENGER_AB_ELIGIBLE` veya `REPLAN_REQUIRED` olabilir. Bu survey
`RETAIN_RGB_BASELINE` sonucunu yayınlar. Desk research bir challenger'ı
doğrudan baseline yapamaz;
`BOUNDED_CHALLENGER_AB_ELIGIBLE` yalnız ayrı, owner-onaylı ve eşlenmiş fiziksel
A/B'ye adaylık anlamına gelir.

Belgedeki iddia etiketleri:

- `FACT_T1`: üretici/standardın doğrudan teknik gerçeği;
- `FACT_T2`: birincil veya hakemli görev araştırması;
- `FACT_T3`: tarihli fiyat/bulunabilirlik kaydı;
- `CALC`: kaynaklı girdilerden deterministik hesap;
- `INFERENCE`: fact/calc tabanlı mühendislik yorumu;
- `HYPOTHESIS`: fiziksel veya target-rig A/B gerektiren iddia;
- `UNKNOWN`: destekleyici kanıtı bulunmayan alan.

`UNKNOWN` sıfır veya baseline değeriyle doldurulmaz. Bir adayın karar-kritik
alanı bilinmiyorsa o aday fiyat/performans kazananı olamaz.

## 2. V2 baseline source lock

Planner release base'i `509aeef8189dfa50dbcba973e871b0d41febe239`, bu
pass sırasında gözlenen shared-worktree `HEAD` ise
`54db1288b6edf7cd4c8f512d9e00ffa19537a51f` idi. Aradaki iki commit başka
lane'lerin yalnız plan dosyalarını ekledi; aşağıdaki beş baseline kaynağında
`git diff 509aeef..HEAD -- <paths>` boştu. Karar otoritesi branch adı değil,
exact dosya hash'leridir.

| Kimlik | Yol | SHA-256 | Belge kanıt tarihi | Rol |
|---|---|---|---|---|
| `L-V2-CONFIG` | [`configs/deploy/spot_spray_capture_optimization_v2.yaml`](../../configs/deploy/spot_spray_capture_optimization_v2.yaml) | `f9fd1cbed95118b4606199e9b67b317c07384e2cb063b60a00e5466848f657e9` | 2026-08-11 | Birincil frozen sayısal sözleşme |
| `L-V2-REPORT` | [`docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md`](../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md) | `c5eb80d8eb074b36463906a4dee993776d2415ae1e41ad50a988c8592e8ed7aa` | 2026-08-11 | İnsan-okunur türetim ve kaynak açıklaması |
| `L-IMAGING-DECISION` | [`docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md`](../SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md) | `c4b7ee5d77fb897576c322a35ab820d882986a096eff225a5364f354b2d0269f` | 2026-08-12 | Ürün proof karar sınırı |
| `L-RIG-RUNBOOK` | [`docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md`](../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md) | `9b73fb34741d8862f27abc4aab30e42268fadb2ad05233d3b201f098fb1acb78` | repository release | Fiziksel A–E kabul sınırı |
| `L-V2-RESULT` | [`docs/results/controlled_capture_optimization_v2.json`](../results/controlled_capture_optimization_v2.json) | `0808c68d40285ff3eba5fb3d13603bc42c12c16d9bacc4fd87470a3c26eafbc8` | 2026-08-11 | Golden karşılaştırma sonucu |

`L-V2-RESULT` kendi içinde `L-V2-CONFIG` hash'ini aynı değerle taşır ve
`baseline_analytic_checks_pass: true` bildirir. Bu survey yine de sayıları
JSON'dan kör kopyalamaz; aşağıda bağımsız formüllerle yeniden üretir.

## 3. Üretici kaynağıyla Basler kimlik doğrulaması

Basler Product Documentation Version 130, release date **2026-07-14**,
2026-08-14 tarihinde doğrudan kontrol edildi:

- `FACT_T1 C-BASLER-1`: [`a2A2464-77ucPRO`](https://docs.baslerweb.com/a2a2464-77ucpro)
  sayfası `2448×2048`, OmniVision OG05C BSI CMOS, global shutter, 2/3 inç,
  `3,45 µm`, görünür renk, varsayılan `71,8 fps` (`77,7 fps` link limiti
  kapalı), USB 3.0 nominal 5 Gbit/s, hardware trigger, C-mount ve USB veya
  `12–24 VDC` beslemeyi aynı exact model için verir. Sayfa ayrıca çıplak
  gövdeyi `IP30` olarak listeler.
- `FACT_T1 C-BASLER-2`: aynı sayfa renk modelindeki fabrika IR-cut filtresini
  doğrular; bu, RGB kontrolünün spectral state'inin “belirsiz VIS+NIR”
  olmadığını gösterir.
- `FACT_T1 C-LENS-1`: [`C23-0824-5M-P`](https://docs.baslerweb.com/c23-0824-5m-p)
  sayfası order `2200000568`, `8,06 mm ±%5`, `F2,4–F16`, 11 mm/2/3 inç image
  circle, `0,1 m–∞` focus range, C-mount, `3,40 µm` tasarım ve kilitlenebilir
  manual focus/iris verir.
- `FACT_T1 C-LENS-2`: lens yalnız **visible 400–700 nm** için belirtilmiştir.
  Bu nedenle NIR, SWIR, LWIR veya active-depth yolunda C23 transmission/focus
  uyumu varsayılamaz.
- `FACT_T1 C-TRIGGER-1`: [`Triggered Image Acquisition`](https://docs.baslerweb.com/triggered-image-acquisition)
  Version 130 dokümanı external electrical input ile hardware trigger'ı ve
  host kapasitesi aşılırsa frame drop olabileceğini açıklar. Datasheet desteği
  fiziksel sync PASS değildir; yalnız bench eligibility kanıtıdır.

Bu resmi teknik sayfalar Version 130 ve release date taşır; `checked_on`
tarihi kaynak sürümünün yerine geçmez. Kamu fiyatı bu pass'te yenilenmedi:
2026-08-11 tarihli `709 USD` kamera ve `136 USD` lens değerleri yalnız tarihsel
budgetary karşılaştırmadır, landed quote değildir.

## 4. Frozen RGB karşılaştırma kontrolü

| Alan | Frozen değer | Tür / kaynak |
|---|---|---|
| Kamera | 1× Basler `a2A2464-77ucPRO`, order `109779` | `FACT_T1`, `L-V2-CONFIG`, `C-BASLER-1` |
| Sensör | color OG05C BSI, factory IR-cut, global shutter | `FACT_T1`, `C-BASLER-1/2` |
| Raw / aktif raster | `2448×2048`; centered native `2048×2048`, offset `(200,0)` | `L-V2-CONFIG` |
| Piksel / aktif sensör span'i | `3,45 µm`; `7,0656 mm` | fact + `CALC` |
| Lens | C23-0824-5M-P, `8,06 mm ±%5`, C-mount | `FACT_T1`, `C-LENS-1` |
| İris / fokus | `f/5,6`; ground üstü 55 mm düzleme fokus | `L-V2-CONFIG` |
| Ground FOV | `474–484 mm`, nominal `480 mm` | `L-V2-CONFIG` |
| Ayarlı WD | `520–590 mm`; birim bazında ölç-fiksle | `L-V2-CONFIG` |
| Exposure / acquisition | `170 µs`; hardware trigger; `15 Hz` baseline | `L-V2-CONFIG` |
| Hareket | karşılaştırma `1,0 m/s`; blur kapısı `≤0,75 px` | `L-V2-CONFIG` |
| Yerel GSD kapısı | her 9 bölge × 3 düzlemde `≤0,243902439 mm/px` | `L-V2-CONFIG` |
| Hedef desteği | 10 mm witness `≥41 px`; 20 mm servis sınıfı `≥82 px` | `L-V2-CONFIG` |
| Aksiyon sınırı | dış `64 px` halka daima abstain | `L-V2-CONFIG` |
| Min. tek-bay güvenli swath | `444,375 mm` | `CALC`, `L-V2-RESULT` |
| Arayüz | Bayer10 packed tercihli, dedicated USB3 root/camera | `L-V2-CONFIG` |
| Compute sınırı | yalnız 1 camera / 15 Hz mevcut RTX 3090 baseline | `L-V2-CONFIG` |

Bu tablo challenger'a verilen avantajı sınırlamaz; aynı action-safe swath,
20 mm servis sınıfı, blur, trigger ve safety sınırını zorunlu kılar. Bir
auxiliary kanalın düşük çözünürlüğü RGB action raster'ıyla karıştırılmaz.

## 5. Deterministik formüller

```text
active_span_mm = active_pixels × pixel_pitch_um / 1000
GSD_mm_px = FOV_mm / independent_samples_across_FOV
target_px = target_mm / GSD_mm_px
WD_mm = focal_mm × (1 + FOV_mm / active_span_mm)       # thin-lens prescreen
smear_mm = speed_mm_s × exposure_us × 1e-6
blur_px = smear_mm / GSD_mm_px
safe_swath_mm = FOV_mm × (2048 - 2×64) / 2048
raw_payload_Mbit_s = width × height × fps × bits_per_pixel / 1e6
```

Thin-lens hesabı katalog ön-elemesidir; dokuz-bölge ölçülmüş geometri, MTF,
distorsiyon, pencere takılı fokus ve reprojection fiziksel otoritedir.

## 6. Baseline golden hesapları

### 6.1 Span, FOV, GSD, hedef desteği, WD, blur ve swath

`CALC`: `2048 × 3,45 µm = 7,0656 mm` aktif span. `1,0 m/s × 170 µs =
0,17 mm` fiziksel smear.

| Ground FOV (mm) | GSD (mm/px) | 10 mm (px) | 20 mm (px) | 8,06 mm nominal WD (mm) | 170 µs blur @1 m/s (px) | 1920 px safe swath (mm) |
|---:|---:|---:|---:|---:|---:|---:|
| 474 | 0,2314453125 | 43,206751 | 86,413502 | 548,769918 | 0,734515 | 444,375 |
| 480 | 0,2343750000 | 42,666667 | 85,333333 | 555,614348 | 0,725333 | 450,000 |
| 484 | 0,2363281250 | 42,314050 | 84,628099 | 560,177301 | 0,719339 | 453,750 |

Sonuçlar:

- `CALC/PASS`: tüm measured-FOV satırlarında 10 ve 20 mm desteği sırasıyla
  41/82 px yerel minimumların üzerindedir;
- `CALC/PASS`: en kötü blur `0,734515 px < 0,75 px`;
- `CALC/PASS`: minimum action-safe swath `444,375 mm`;
- `CALC/PASS`: `8,06 mm ±%5` ve FOV uçları birlikte örneklendiğinde gerekli
  WD zarfı `521,331423–588,186166 mm`; mekanik `520–590 mm` bunu kapsar.

Bu değerler `20 mm` için ürün performansı kanıtlamaz. Yalnız fiziksel target'ın
kaç native sensör örneğine yayıldığını gösterir; visibility, mask quality,
tracking, crop hit ve deposition ayrı kapılardır.

### 6.2 Native ROI payload

| FPS | Bayer10 packed raw (Mbit/s) | Bayer12 packed raw (Mbit/s) |
|---:|---:|---:|
| 12 | 503,31648 | 603,979776 |
| 15 | 629,14560 | 754,974720 |
| 20 | 838,86080 | 1.006,632960 |

`CALC`: Bunlar `2048²` ROI'nin yalnız raw pixel payload'ıdır; USB framing,
host contention ve margin değildir. Challenger karşılaştırmasında documented
sustained link kapasitesine karşı ayrıca `%20` headroom uygulanacaktır. Nominal
5 Gbit/s link spec'i transport/thermal Stage-B PASS yerine geçmez.

## 7. Ephemeral doğrulama receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan bağımsız Python hesapları
çalıştırıldı. Aşağıdaki alanlar frozen
`docs/results/controlled_capture_optimization_v2.json` ile `abs_tol=1e-12`
içinde karşılaştırıldı:

| Assertion | Sonuç |
|---|---|
| active span = `7,0656 mm` | PASS |
| 474/480/484 mm GSD | PASS |
| her FOV'da 10/20 mm target pixel | PASS |
| her FOV'da nominal WD | PASS |
| focal-tolerance WD envelope | PASS |
| 12/15/20 Hz Bayer10/Bayer12 payload | PASS |
| minimum safe swath = `444,375 mm` | PASS |
| max analytic blur `≤0,75 px` | PASS |
| frozen `baseline_analytic_checks_pass` | `true` |

Doğrulama herhangi bir GPU işi, kamera capture'ı veya fiziksel ölçüm yapmadı.
Sonuç **baseline arithmetic/source-lock PASS**; fiziksel A–E hâlâ ölçülmedi.

## 8. Matched challenger karşılaştırma zemini

Her exact SKU iki ayrı modda değerlendirilecektir:

1. **Mode A — drop-in:** `474–484 mm` FOV, `520–590 mm` WD, en az
   `444,375 mm` safe swath, 15 Hz, `≤170 µs`, global/snapshot timing, hardware
   trigger ve spectral-compatible lens/filter/window aynı anda sağlanır.
2. **Mode B — matched performance:** drop-in olmayan adayda
   `GSD≤0,243902439 mm/px` korunurken maksimum FOV, gerekli bay sayısı, toplam
   camera body, lens/filter/emitter/interface ve yeni hood/WD ihtiyacı
   hesaplanır. Mode B baseline değiştirme yetkisi vermez.

Replacement action kanalı 20 mm için `≥82` **independent native sample**
taşımalıdır. Demosaic, upscale veya multispectral reconstructed output bu
sayımı artırmaz. Additive stack'te safe swath kanalların calibrated common-FOV
kesişiminden hesaplanır.

## 9. Modality çalışma matrisi

Bir teknik desk-screen PASS, promotion veya satın alma anlamına gelmez. Trigger
ve fiziksel kapılar ayrı tutulur.

| Modalite | Güvenli mimari rolü | Bu pass durumu | Henüz gerekli decisive evidence |
|---|---|---|---|
| RGB | 1× Basler PRO + C23 action control | `BASELINE_SOURCE_LOCK_PASS` | Fiziksel A–E ve target-rig kanıtı |
| Visible monochrome | Olası tek-camera replacement | `CONDITIONAL_TRIGGER_CLOSED` | düşük-photon failure attribution + paired crop-safety A/B + H8 complete cost |
| NIR-only | Diagnostic; safety kanıtına kadar action replacement değil | `SCREENED_OUT_AS_ACTION_REPLACEMENT` | renk kanalını kaldırmayan safety kanıtı yok |
| RGB+NIR | RGB'yi koruyan additive spectral lane | `CONDITIONAL_H7_H8_TRIGGER_CLOSED` | measured sync/registration/CNR, ikinci root+compute, complete order identity/cost |
| Snapshot multispectral | simultaneous area-scan; görünür safety yoksa additive | `CONDITIONAL_CHALLENGER_TASK_TRIGGER_OPEN_H6_H8_PHYSICAL_CLOSED`; XIMEA mosaic backup screened out | JAI exact light/NIC/cable/calibration cost + installed 170 µs/registration/compute; fiziksel A–E |
| RGB+thermal | RGB'yi koruyan additive LWIR lane | `SCREENED_OUT`: Boson+ H2; A6751 H4/H7/H8 | measured visible-collapse + plant/soil thermal contrast trigger'ı ve hard gate'leri geçen yeni exact stack |
| RGB+depth | frozen RGB'yi koruyan auxiliary structure cue | `CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD`; Orbbec primary ve blaze backup A/B-eligible değil | owner-bound p95/valid-fraction threshold, intended-ambient physical receipt, common-FOV registration ve complete integration cost |

Thermal-only action, passive host stereo, rolling shutter, pushbroom ve
sequential filter-wheel seçenekleri plan gereği aday shortlist'ine alınmaz.

## 10. Visible monochrome screen'i

### 10.1 Exact primary ve vendor-diverse backup

`FACT_T1 MONO-PRIMARY`: Basler
[`a2A2464-77umPRO`](https://docs.baslerweb.com/a2a2464-77umpro), order
`109778`, baseline renkli gövdeyle aynı OG05C, `2448×2048`, `3,45 µm`, 2/3
inç, global shutter, C-mount ve USB3 sınıfındadır; çıktı monochrome ve çıplak
spektrumu `0,4–1,1 µm` Visible+NIR'dir. Üretici dokümanı Version 130,
2026-07-14; checked 2026-08-14. Bu nedenle gövde **filtresiz görünür mono
değildir**.

Exact görünür zincir:

- kamera: Basler `a2A2464-77umPRO`, order `109778`;
- filter: MidOpt [`SP700-25.4`](https://midopt.com/filters/sp700/), lens ile
  sensör arasına giren 25,4 mm C-mount; useful range `405–690 nm`, `400/700
  nm` %50 cut-on/cut-off, peak transmission `≥%90`; manufacturer page
  tarihsiz, checked 2026-08-14;
- lens: frozen Basler `C23-0824-5M-P`, `8,06 mm ±%5`, 11 mm image circle,
  `400–700 nm` VIS ve `3,40 µm` tasarım; aktif kare ROI diyagonali
  `9,992267 mm` olduğu için 11 mm image circle katalog ön-elemesini geçer;
- protective window adayı: Edmund Optics
  [`#37-014`](https://www.edmundoptics.com/p/50mm-dia-2mm-thick-vis-nir-coated-4-n-bk7-window/37339/),
  50 mm çap, 45 mm clear aperture, `2,00±0,20 mm`, N-BK7, VIS-NIR
  `400–1000 nm`; bu parça inherited 2–3 mm window sınıfına ve görünür banda
  uyar, fakat eğik frame/seal/vignetting ancak installed Stage C'de geçebilir.

`FACT_T1 MONO-BACKUP`: Teledyne FLIR
[`BFS-U3-51S5M-C`](https://softwareservices.flir.com/BFS-U3-51S5/latest/Model/spec.html)
Firmware `1801.0.1.0` dokümanı `2448×2048`, Sony IMX250 2/3 inç,
`3,45 µm`, global shutter, C-mount, Mono8/10/12, `73 fps`, `6 µs–30 s`,
USB3.1 ve opto-isolated input/output verir; ürün doküman ailesi 2022-11-18,
checked 2026-08-14. GPIO'nun trigger/strobe için kullanılabildiği üretici
installation dokümanında belirtilir. Aynı C23 + SP700 + #37-014 zinciri onu
da tanımlı görünür banda sınırlar.

Üreticilerin EMVA receipts'i tek bir ağırlıklı score'a çevrilmez:

| 525 nm / room-temperature metric | Basler `109778` | FLIR backup |
|---|---:|---:|
| Quantum efficiency | `%86,37 typical` | `%63,40` |
| Temporal dark/read noise | `13,3 e- typical` | `2,44 e-` |
| Saturation capacity | `26,4 ke- typical` | `10,970 ke-` |
| Maximum SNR | `44,2 dB typical` | `40,40 dB` |
| Dynamic range | `65,5 dB typical` | `71,45 dB` |

Basler commerce sayfası exact mono için 525 nm ölçüm noktasını verir; FLIR
[`EMVA 1288`](https://softwareservices.flir.com/BFS-U3-51S5/latest/EMVA/EMVA.html)
sayfası Firmware `1801.0.1.0`, 16-bit output/ISP-off ve 20°C koşulunu verir
(2022-11-18). Basler aynı `%86,37` typical QE alanını exact color baseline
commerce sayfasında da listeler. Bu nedenle QE alanından monochrome'un RGB'ye
`1,5×` instrument-signal kazancı çıkarılamaz; filter, CFA/readout, spectrum ve
scene birlikte ölçülmelidir.

| Exact aday | Camera body `FACT_T3` | Optics/window subtotal | Entegrasyon sonucu |
|---|---:|---:|---|
| Basler `109778` primary | `689 USD`, Graftek, request lead time, checked 2026-08-14 | `136 USD` tarihsel C23 + `145 USD` SP700 + `153 USD` #37-014 | `1.123 USD` camera+optics+window; cable/power-I/O/window frame/common hood-light dahil değil |
| FLIR `BFS-U3-51S5M-C` backup | `1.304 USD`, DigiKey, active/available-to-order ve 4 hafta manufacturer lead-time, checked 2026-08-14 | aynı `434 USD` | `1.738 USD` camera+optics+window; aynı eksikler ve ayrı Spinnaker integration |

Bu subtotallar landed quote veya complete proof-stack fiyatı değildir. Primary,
aynı sensor ailesi ve software/interface yolunu korurken camera+optics+window
subtotalında backup'tan `615 USD` düşüktür. Backup için görev veya teknik
kazanım bulunmadığından **Pareto-dominated backup** olarak kapanır; bu bir
tedarik kararı değildir.

### 10.2 Eşlenmiş geometri, shutter ve payload

İki mono aday da native `2048×2048` merkez ROI, `3,45 µm` pitch ve C23 ile
hesaplandığında baseline'ın Section 6 tablosunu aynen üretir: `474/480/484 mm`
FOV'da GSD sırasıyla `0,2314453125 / 0,234375 / 0,236328125 mm/px`, 10 mm
`43,206751 / 42,666667 / 42,314050 px`, 20 mm `86,413502 / 85,333333 /
84,628099 px`; safe swath minimum `444,375 mm`; nominal C23 WD
`548,769918–560,177301 mm`.

`CALC`: 170 µs ve 1 m/s varsayımı korunursa blur `0,719339–0,734515 px` ve
kapı geçer. Kamera dokümanının kısa exposure ve trigger desteği, installed
170 µs SNR/timing PASS değildir. Mono10/Mono12 packed native ROI payload'ı
15 Hz'de sırasıyla `629,1456 / 754,97472 Mbit/s`; %20 headroom ile
`754,97472 / 905,969664 Mbit/s` olur. Bir camera body, bir optical bay ve bir
dedicated USB root gerekir.

### 10.3 H1–H10 ve karar

| Kapı | Basler `109778` | FLIR backup |
|---|---|---|
| H1 identity | `PASS`: exact body/order/sensor/filter/lens/window/interface ve tarihli subtotal | `PASS`: exact body/model/sensor/filter/lens/window/interface ve tarihli subtotal |
| H2 timing | `PASS_DESK_STAGE_B_OPEN`: global, hardware trigger, >15 Hz; installed 170 µs ölçülmedi | `PASS_DESK_STAGE_B_OPEN`: global, GPIO trigger, >15 Hz, min 6 µs; installed timing ölçülmedi |
| H3 native geometry | `PASS_CALC`: 10/20 mm ve 444,375 mm | `PASS_CALC`: aynı |
| H4 optics | `PASS_PRESCREEN_STAGE_C_OPEN`: active diagonal/image circle/spectrum/min-focus uyumlu; filter+window focus/MTF/vignetting ölçülmedi | `PASS_PRESCREEN_STAGE_C_OPEN`: aynı geometry; installed optical state ölçülmedi |
| H5 spectrum | `PASS`: SP700, mixed VIS+NIR'yi 405–690 nm görünür state'e kapatır | `PASS`: aynı |
| H6 interface | `PASS_MATH_STAGE_B_OPEN`: raw+%20 nominal 5 Gbit/s altında; sustained root/cable/timestamps ölçülmedi | `PASS_MATH_INTEGRATION_OPEN`: link hesabı geçer; Spinnaker/cable/timestamps bu hostta kanıtlanmadı |
| H7 multi-sensor | `N/A`, tek replacement body | `N/A`, tek replacement body |
| H8 cost | `FAIL_PRICE_RANKING`: trigger/power cable, mount/frame ve common proof allowance'ları fiyatlı değil | `FAIL_PRICE_RANKING`: aynı, ayrıca yeni SDK integration |
| H9 task value | `PASS_TRIGGER_ONLY`: repository low-photon trigger'ı var; exact paired mono paper yok | aynı |
| H10 safety | `CONDITIONAL`: paired color-loss target-rig A/B olmadan RGB yerini alamaz | aynı |

2026-08-14 tarihli bounded primary-paper aramasında same-rig RGB sensor ile
visible-mono sensor'ı crop/weed instance/semantic segmentation için eşleyen
uygulanabilir çalışma bulunmadı. Örneğin
[`Mekhalfa ve Yacef (2021)`](https://arxiv.org/abs/2106.10581) RGB/HSV renk ve
RGB'den türetilmiş gray-level texture feature'ları kıyaslar; ayrı monochrome
camera'nın photon/SNR kazancını veya renk kaybı güvenliğini ölçmez. Bu kayıt
evrensel “kanıt yoktur” iddiası değil, bounded search sonucudur.

**Disposition:** `CONDITIONAL_TRIGGER_CLOSED`. Basler primary ancak frozen RGB
installed hood/light ile 170 µs'te Stage-D `20 dB` SNR'yi sensor-intrinsic
nedenle geçemezse, aynı SNR için exposure/light sınırını aşarsa veya paired
target-rig hata analizi hatanın renk değil photon/noise kaynaklı olduğunu
gösterirse fiziksel A/B'ye açılır. Bunların hiçbiri ölçülmedi. Monochrome
bugün baseline, purchase veya A/B komutu değildir.

## 11. NIR-only ve RGB+NIR screen'i

### 11.1 Exact spectral zincirler

Safety-preserving mimari frozen RGB action channel + synchronized NIR
auxiliary lane'dir. NIR-only aynı optik hesabı taşır fakat renk bilgisini
kaldırdığı için H10 action replacement'ı geçmez.

| Parça | 2/3 inç primary NIR lane | 1 inç backup NIR lane |
|---|---|---|
| Camera | Basler `a2A2464-77umPRO`, order `109778`, OG05C, Visible+NIR 0,4–1,1 µm, 2048² active, 3,45 µm, global, USB3/hardware trigger | Basler [`acA2040-90umNIR`](https://docs.baslerweb.com/aca2040-90umnir), order `106555`, CMV4000 NIR-enhanced, Visible+NIR 0,4–1,1 µm, 2048², 5,5 µm, 1 inç, global, 90 fps, USB3/hardware trigger; Version 130, 2026-07-14 |
| Lens | Kowa [`LM8JC10M`](https://www.kowa-lenses.com/LM8JC10M-2-3-8.5mm-10MP-C-Mount-Lens/10703), product `10703`, 2/3 inç, `8,5 mm`, 10 MP, 2,5 µm design, C-mount, min focus 0,1 m, broadband `400–1000 nm` | Kowa [`LM12HC-VIS-SW`](https://kowa-lenses.com/LM12HC-VIS-SW-1-12mm-12MP-VIS-SWIR-lens/12199), product `12199`, 1 inç, `12 mm`, 12 MP, 3,1 µm design, C-mount, min focus 0,2 m, `450–2000 nm` |
| Filter | MidOpt [`BP850-25.4`](https://midopt.com/filters/bp850/), C-mount between lens/sensor, `820–910 nm`, FWHM `160 nm`, peak `≥%90`, 840/850 nm LED compatible | aynı; 21 mm clear aperture vendor drawing'e göre 15,93 mm sensor diagonalini katalogda kapsar |
| Window | Edmund #37-014, 50 mm / clear 45 mm / 2 mm, `400–1000 nm`; coating `Ravg≤%1,25` (400–870 ve 890–1000 nm), `Rabs≤%0,25` @880 nm | aynı; lens OD 37 mm'dir, fakat 3–5° installed tilt/frame cone'u Stage C'de ölçülmelidir |
| Emitter | Smart Vision Lights [`JWL225-MD`](https://smartvisionlights.com/products/jwl225-md/) **850 nm option**, Multi-Drive continuous/OverDrive, camera-trigger control, IP65, WD 300–1500 mm | aynı |

Tüm spektral aralıklar 850 nm'de kesişir. Buna karşılık exact 850 nm sensor QE
sayısı, lens transmission yüzdesi, selected JWL lens/polarizer suffix'i,
radiant intensity/480 mm uniformity ve installed window loss'u aynı kaynaklı
sayısal zincirde tamamlanmamıştır. Bu nedenle
`∫ emitter×lens×window×filter×QE` hesabı veya `1,5× signal / 3 dB SNR`
iddiası **üretilmez**. JWL sayfası 850 nm seçeneğini verir fakat seçili
konfigürasyonun terminal order code'unu vermediği için H1 complete-stack
identity açık kalır.

### 11.2 Mode A / Mode B geometri

| NIR aday | Active span / focal | WD @474 / 480 / 484 mm FOV | Mode A | Nominal Mode B ve adet |
|---|---:|---:|---|---|
| a2A + LM8JC10M | `7,0656 / 8,5 mm` | `578,727582 / 585,945652 / 590,757699 mm` | `NOT_PROVEN_FULL_RANGE`: nominal 484 mm ucu WD 590 mm'yi 0,758 mm aşar; focal tolerance kaynaksız | 480 mm FOV, WD 585,946 mm, 450 mm safe swath, 1 bay; NIR-only 1 body, RGB+NIR 2 body |
| acA + LM12HC-VIS-SW | `11,264 / 12 mm` | `516,971591 / 523,363636 / 527,625000 mm` | `NOT_PROVEN_FULL_RANGE`: nominal 474 mm ucu WD 520 mm'nin altında; focal tolerance kaynaksız | 480 mm FOV, WD 523,364 mm, 450 mm safe swath, 1 bay; NIR-only 1 body, RGB+NIR 2 body |

Primary için WD=590 mm'de hesaplanan en büyük FOV `483,370165 mm`;
backup için WD=520 mm'de en küçük FOV `476,842667 mm`dir. Her ikisi nominal
480 mm ortak FOV'a ayarlanabilir; bu noktada GSD `0,234375 mm/px`, 10 mm
`42,666667 px`, 20 mm `85,333333 px` ve 170 µs varsayımsal blur
`0,725333 px` olur. Bu lens distortion, spectral focus shift veya installed
MTF ölçümü değildir.

`FACT_T3`, checked 2026-08-14:

| NIR sensor-lane öğeleri | Public price receipt | Cost-completeness |
|---|---:|---|
| Primary body + filter + window + emitter | `689 + 160 + 153 + 1.241 = 2.243 USD` | Kowa lens `967 EUR` ayrıca; VAT/shipping/FX hariç |
| Backup body + filter + window + emitter | `1.811 + 160 + 153 + 1.241 = 3.365 USD` | Kowa lens `3.950 EUR` ayrıca; VAT/shipping/FX hariç |

Primary camera Graftek fiyatı; BP850 Machine Vision Direct fiyatı; window ve
JWL üretici commerce fiyatıdır. Backup camera Soda Vision'da `available on
backorder`; lens Kowa üretici fiyatıdır. Cable, bracket, selected emitter
optics/polarizer, 24 V power, window frame/seal, registration target, ikinci
USB root/controller ve compute integration fiyatlanmamıştır. Para birimleri
güncel FX ile birleştirilmedi; dolayısıyla USD/mm veya stack cost ratio yoktur.
Backup, daha pahalı gövde ve çok daha pahalı lensle native 2048 örnek ve aynı
nominal swath'i verir; kaynaklı 850 nm görev üstünlüğü yoktur ve
`SCREENED_OUT_PARETO_DOMINATED` olur.

### 11.3 Payload, common FOV ve H1–H10

| 15 Hz native ROI | 10 bit raw | +%20 headroom | 12 bit raw | +%20 headroom |
|---|---:|---:|---:|---:|
| Tek NIR lane | `629,1456` | `754,97472` | `754,97472` | `905,969664` Mbit/s |
| Frozen RGB + NIR | `1.258,2912` | `1.509,94944` | `1.509,94944` | `1.811,939328` Mbit/s |

Toplam, her body'nin ayrı USB3 root kullanması şartıyla nominal linklerin
altındadır; iki stream'i aynı root'a koyma yetkisi vermez. Nominal common FOV
480 mm, common safe swath 450 mm ve toplam iki camera body'dir. Frozen compute
sözleşmesi yalnız 1 camera/15 Hz destekler; cross-camera trigger skew,
timestamp semantics, registration residual, valid common-FOV mask ve host
inference yükü ölçülmediği için H7 geçmez.

| Kapı | a2A primary RGB+NIR | acA backup RGB+NIR |
|---|---|---|
| H1 identity | `FAIL_COMPLETE_STACK_IDENTITY`: camera/lens/filter/window exact; selected emitter suffix, cable/power/mount değil | aynı; camera/lens exact |
| H2 timing | `PASS_DESK_STAGE_B_OPEN`: global, hardware trigger, >15 Hz; 170 µs photon/timing ölçülmedi | aynı |
| H3 geometry | `PASS_MODE_B_CALC`: nominal 480 mm, 10/20 mm ve one-bay swath | `PASS_MODE_B_CALC`: aynı |
| H4 optics | `PASS_PRESCREEN_STAGE_C_OPEN`; Mode A full 474–484 zarfı nominal değerle kanıtlanmadı | aynı; Mode A alt ucu nominal değerle kanıtlanmadı |
| H5 spectrum | `PASS_DEFINITION`: 850 option + BP850 + 400–1000 lens/window | `PASS_DEFINITION`: 850 option + BP850 + 450–2000 lens + 400–1000 window |
| H6 interface | `PASS_RAW_MATH / FAIL_PHYSICAL_LANE_PROOF`: ikinci dedicated root/cable/timestamps yok | aynı |
| H7 registration | `FAIL_CURRENT_PROOF`: sync/common FOV hesaplı; skew/registration/compute kanıtsız | aynı |
| H8 cost | `FAIL_PRICE_RANKING`: mixed currency ve zorunlu parçalar eksik | `FAIL_PRICE_RANKING`; ayrıca Pareto-dominated |
| H9 task value | `PASS_DIRECTIONAL_T2`, aşağıdaki iki çalışma; comparable safety kanıtı değil | aynı |
| H10 safety | NIR-only `FAIL`; RGB+NIR `CONDITIONAL` çünkü RGB korunur ama A–E bypass edilemez | aynı |

### 11.4 Tier-2 görev kanıtı ve trigger sonucu

[`WeedMap` (Sa ve diğerleri, 2018)](https://arxiv.org/abs/1808.00100),
hakemli Remote Sensing paper'ının birincil metninde aerial sugar-beet/weed
**semantic segmentation** için aynı RedEdge-M testinde şu AUC'leri verir:

| Input | Background | Crop | Weed |
|---|---:|---:|---:|
| RGB | `0,607` | `0,681` | `0,576` |
| RGB+NIR | `0,607` | `0,680` | `0,594` |
| NIR-only | `0,566` | `0,508` | `0,512` |
| En iyi 9-channel multispectral | `0,839` | `0,863` | `0,782` |

`FACT_T2`: RGB+NIR weed AUC'si RGB'den `+0,018`, crop AUC'si `-0,001`;
NIR-only üç sınıfta da RGB'den düşüktür. Büyük multispectral fark yalnız NIR
eklemesinin değil, aligned/radiometrically calibrated aerial orthomosaic ve
çoklu band/index kombinasyonunun sonucudur. Yaklaşık 1 cm GSD, 5–10 px weed,
UAV/orthomosaic ve semantic metric nedeniyle target-rig instance/track safety
kanıtı değildir.

[`Weed detection in cabbage fields using RGB and NIR images`
(2025)](https://www.sciencedirect.com/science/article/pii/S2772375525004630)
aynı shielded/flash JAI FSFE-3200T-10GE'den `2048×1536` paired RGB+NIR,
yaklaşık 50 cm WD, 30×40 cm alan ve `0,195 mm` GSD toplar. YOLOv10l detection
sonucu RGB `94,5%`, RGB+NIR `94,9% mAP@0.5`; ortalama inference `0,0794 s`den
`0,0853 s`ye, yaklaşık `%7`, yükselmiştir. `FACT_T2` yönü NIR için küçük bir
kazanımdır; fakat 75/15/10 random image split, bounding-box detection,
0,15–0,3 m/s ve 0,5–1 Hz acquisition bu proof'un field-isolated instance
segmentation/track/action güvenliğine eş değildir.

**Trigger sonucu:** literatür additive NIR'yi silmek için yeterli değildir,
ancak satın alma veya physical A/B trigger'ını da tek başına açmaz. Frozen RGB
A–E sonucu yoktur; wet-leaf/soil veya low-visible-contrast failure bin'i
gösterilmemiştir; 850 nm paired CNR ölçülmemiştir; H7/H8 fail'dir. Sonuç
`RGB+NIR = CONDITIONAL_H7_H8_TRIGGER_CLOSED`;
`NIR-only = SCREENED_OUT_AS_ACTION_REPLACEMENT`.

## 12. Pass 3 ephemeral validation receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan 13 deterministic assertion
çalıştırıldı. a2A/8,5 mm ve acA/12 mm span–WD–FOV hesapları, nominal target
sampling, safe swath, bir/iki-lane 10/12-bit payload+headroom ve dört tarihli
component subtotalı PASS verdi. Representative outputs:

```text
a2a_nir_wd_480=585.945652173913
a2a_nir_fov_at_wd590=483.370164705882
aca_nir_wd_480=523.363636363636
mono_payload10_15=629.145600000000
mono_payload12_15=754.974720000000
PASS: 13 mono/NIR geometry, sampling, payload and price-subtotal assertions
```

Bu receipt optical throughput, installed MTF, SNR, strobe uniformity, trigger
skew, transport reliability veya model utility ölçmez.

## 13. Snapshot multispectral screen'i

### 13.1 Bounded shortlist ve terminal reject'ler

Bu screen yalnız bütün bandları aynı exposure olayında alan **area-scan
snapshot** gövdeleri kapsadı. Retained liste iki exact SKU ile sınırlandı:

1. **Primary — JAI `FS-3200T-10GE-NNC`.** Üç CMOS/prizma aynı anda bir Bayer
   görünür, bir `700–800 nm` NIR1 ve bir `820–1000 nm` NIR2 görüntüsü üretir.
   Her taşıyıcı `2048×1536`'dır. Bu tek-gövde RGB+NIR+NIR mimarisi görünür
   safety kanalını koruduğu için replacement challenger olarak incelenebilir.
2. **Backup — XIMEA `MQ022HG-IM-SM5X5-7NIR2`.** Tek global-shutter
   `2048×1088` taşıyıcı üstündeki 5×5 mosaic, `665–960 nm` aralığında 24
   spectral örnek üretir. Görünür renk kanalı yoktur; bu nedenle yalnız frozen
   RGB'ye additive olabilir.

JAI kimliği ve simultane üç-stream yapısı üreticinin
[exact ürün sayfası](https://www.jai.com/products/fs-3200t-10ge-nnc/) ile
Ocak 2020 tarihli
[v1.0 kullanım kılavuzuna](https://cdn.graftek.com/system/files/16830/original/JAI_FS-3200T-10GE-NNC_Manual.pdf)
bağlıdır. XIMEA kimliği ve mosaic yapısı üreticinin
[exact ürün sayfasına](https://www.ximea.com/products/hyperspectral-imaging/xispec-hyperspectral-miniature-cameras/imec-sm-range-600-1000-usb3-hyperspectral-camera)
ve ©2025, v2.00
[xiSpec kılavuzuna](https://www.ximea.com/getattachment/9ca53218-192e-4701-bafa-3cf17375c82e/xiSpec_TechnicalManual-DWL_manual.pdf)
bağlıdır.

Terminal reject'ler:

- **Pushbroom/line-scan:** exact örnek XIMEA
  `MQ022HG-IM-LS150-VN2`'dir. Üretici
  [whitepaper'ı](https://www.ximea.com/getmedia/713d4c3c-f52d-4d9d-84df-d38ac6d3b52c/xiSpec-hyperspectral-cameras-whitepaper_V2-02.pdf)
  her band için `2048×5` satır ve tam küp için hareketle senkronize `>150`
  görüntü stitching'i tarif eder. Bu, tek exposure'lı action frame değildir;
  `TERMINAL_REJECT_SEQUENTIAL_MOTION`.
- **Sequential filter wheel/tunable-filter:** aynı sahneyi farklı zamanlarda
  örneklediği için `1 m/s` hareket ve `170 µs` eş-zaman sözleşmesini sağlayamaz;
  `TERMINAL_REJECT_SEQUENTIAL_CAPTURE`.
- XIMEA'nın görünür `SM4X4-7VIS3` satırı üretici ürün/manual band sayısı ve
  lifecycle metinleri aynı exact karar kimliğini vermediği için üçüncü aday
  olarak tutulmadı. Bu dışlama bir performans iddiası değildir.

### 13.2 Exact stack, spektrum ve native band lattice'i

| Alan | JAI primary | XIMEA backup |
|---|---|---|
| Exact gövde | `FS-3200T-10GE-NNC` | `MQ022HG-IM-SM5X5-7NIR2` |
| Sensor / shutter | 3× Sony IMX252 CMOS; global | imec CMV2K-SSM5x5-NIR; global |
| Raw taşıyıcı | her stream `2048×1536`, `3,45 µm`; aktif `7,0656×5,2992 mm` | `2048×1088`, `5,5 µm`; aktif `11,264×5,984 mm` |
| Native spectral örnek | visible BayerRG + full-raster NIR1 + full-raster NIR2 | 5×5 tekrarda 25 filter konumu; 24 spectral sample |
| Band tanımı | visible `400–670`; NIR1 `700–800`; NIR2 `820–1000 nm` | 24 merkez: `668,7, 686,8, 700,1, 711,6, 728,0, 739,2, 752,3, 767,3, 780,7, 789,4, 804,5, 815,3, 828,3, 843,4, 852,9, 865,1, 879,4, 891,6, 899,8, 912,8, 922,2, 931,9, 942,4, 951,4 nm` |
| Raw independent lattice | NIR1/NIR2'nin her biri `2048×1536`; visible carrier `2048×1536`, R ve B ayrı ayrı `1024×768`, G iki interleaved `1024×768` alt-lattice | her band için conservative `floor(2048/5)×floor(1088/5)=409×217` |
| Output / interface | BayerRG8/10/12 + Mono8/10/12; üç stream; 10GigE | 10-bit raw mosaic; USB3 Micro-B, nominal 5 Gbit/s |
| Trigger / exposure | hardware/sequence trigger, PTP; timed exposure min. `14,73 µs`; `107 fps` | hardware/software trigger, strobe/busy; `30 µs–2 s`; `170 fps` |
| Exact lens | JAI `JVS-C118-0824-C3`; `8 mm`, C-mount, 1/1.8 inç, `9 mm` image circle, `f/2,4–16`, `100 mm–∞` | Edmund #`67-714`; `16 mm`, C-mount, 2/3 inç, `425–1000 nm`, `100 mm–∞` |
| Window | Edmund #`37-014`, `400–1000 nm` VIS-NIR AR | aynı exact #`37-014` |
| Filter / calibration | üç-prizma iç band ayrımı; exact response/FWHM eğrileri yayımlanmamış | on-sensor bandpass mosaic; camera-serial calibration file ve flat-field correction zorunlu |
| Emitter | Fischer çalışması 2× `EFFI-FLEX-HSI` kullandı; exact length/window/lens/polarizer suffix'i ve target-rig quantity'si açık | exact controlled-light stack henüz seçilmedi |
| Lifecycle / tedarik | exact body için tarihli vendor listesi var; landed quote yok | aynı üretici sayfasında üstte “Active”, alt lifecycle alanında “Product is discontinued”; supply PASS yok |

Exact JAI lensi üreticinin
[prism-camera lens tablosunda](https://news.jai.com/hubfs/Blogs-News%20files/Lenses-for-JAI%20cameras.pdf)
`FS-3200T` için listelenir; mekanik/spectral ayrıntılar
[Edmund manufacturer sayfasında](https://www.edmundoptics.com/p/8mm-focal-length-prism-optimized-fixed-focal-length-lens/57133/)
doğrulanır. XIMEA kılavuzu calibrated standard lens kitlerini `16/25/35 mm`
olarak verir; retained en kısa exact lensin ayrıntıları
[Edmund #67-714 sayfasındadır](https://www.edmundoptics.com/p/16mm-c-series-vis-nir-fixed-focal-length-lens/22382/).
İki stack'in `400–1000 nm` penceresi
[Edmund #37-014](https://www.edmundoptics.com/p/50mm-dia-2mm-thick-vis-nir-coated-4-n-bk7-window/37339/)
kaynağına bağlıdır. `EFFI-FLEX-HSI` yalnız
[üretici family sayfası](https://effilux.com/product/machine-vision/barlight/effi-flex-hsi/)
ve [datasheet'i](https://www.effilux.com/docs/datasheet/DATASHEET_EFFI-FLEX-HSI.pdf)
ile family düzeyinde tanımlıdır; exact order chain olarak varsayılmamıştır.

`FACT_T1/CALC`: XIMEA kılavuzunun yaklaşık spatial resolution satırı
`409×217`, eski IMEC materialinde görülen `409×218` ile çelişir. Karar hesabı
reconstructed output veya yuvarlatılmış vendor değeri yerine raw lattice'ten
`floor` ile türetilen conservative `409×217`'yi kullanır. JAI visible stream
için demosaic sonrası `2048×1536` görüntü, her rengin native lattice'i değildir;
R/B band desteği bu nedenle açıkça yarı en örneklemesiyle raporlanır.

### 13.3 JAI matched geometry, target desteği ve payload

`CALC`: `2048×3,45 µm = 7,0656 mm` aktif yatay span. Exact `8 mm` lens için:

| Ground FOV (mm) | Gerekli WD (mm) | NIR/carrier GSD (mm/px) | 10 mm (px) | 20 mm (px) | 170 µs blur (px) | 1920 px safe swath (mm) |
|---:|---:|---:|---:|---:|---:|---:|
| 474 | 544,684783 | 0,231445313 | 43,206751 | 86,413502 | 0,734515 | 444,375 |
| 480 | 551,478261 | 0,234375000 | 42,666667 | 85,333333 | 0,725333 | 450,000 |
| 484 | 556,007246 | 0,236328125 | 42,314050 | 84,628099 | 0,719339 | 453,750 |

Bu nominal prescreen `520–590 mm` WD'ye, `≤0,243902439 mm/px` carrier/NIR
sampling kapısına, `20 mm ≥82 px` ve `≤0,75 px` blur kapısına uyar. Sonuç bir
gövde/bir optical bay ve nominalde `450 mm` action-safe swath'tır. Installed
prism-lens MTF, focal tolerance, pencere/fokus ve dokuz-bölge ölçümü fiziksel
Stage C'ye açıktır.

Raw color-band dürüstlüğü:

| JAI band/raster | FOV 480'de independent samples across | GSD (mm/sample) | 10 mm | 20 mm |
|---|---:|---:|---:|---:|
| Visible Bayer carrier | 2048 | 0,234375 | 42,666667 | 85,333333 |
| R native lattice | 1024 | 0,468750 | 21,333333 | 42,666667 |
| B native lattice | 1024 | 0,468750 | 21,333333 | 42,666667 |
| G | 2 interleaved 1024-wide phases | phase başına 0,468750 | phase başına 21,333333 | phase başına 42,666667 |
| NIR1 | 2048 | 0,234375 | 42,666667 | 85,333333 |
| NIR2 | 2048 | 0,234375 | 42,666667 | 85,333333 |

Baseline de Bayer carrier kullandığından carrier satırı action-geometry
eşlemesidir; R/B değerleri spectral-band iddiasının sınırıdır. Demosaic native
band örnek sayısını büyütmez.

Üç `2048×1536` stream, 15 Hz için interface yükü:

| Stream depth | Raw (Mbit/s) | +%20 headroom (Mbit/s) |
|---:|---:|---:|
| 8 bit | 1.132,462080 | 1.358,954496 |
| 10 bit | 1.415,577600 | 1.698,693120 |
| 12 bit | 1.698,693120 | 2.038,431744 |

Nominal 10GigE bu raw hesabı taşır; bu `CALC` sustained NIC/cable/driver,
packet-loss, üç-stream timestamp veya mevcut RTX 3090'da beş-channel 15 Hz
inference PASS değildir.

### 13.4 XIMEA geometry, bağımsız band desteği ve camera count

`CALC`: `2048×5,5 µm = 11,264 mm` taşıyıcı span. Approved/calibrated `16 mm`
lensle `480 mm` FOV için `697,818182 mm` WD gerekir; bu `590 mm` üst sınırını
aşar. Target-rig WD uçlarındaki gerçek yatay sonuç:

| WD (mm) | FOV × düşey FOV (mm) | Band GSD (`FOV/409`, mm/sample) | 10 mm (sample) | 20 mm (sample) | Safe width (mm) | Spectral bay |
|---:|---:|---:|---:|---:|---:|---:|
| 520 | 354,816 × 188,496 | 0,867521 | 11,527101 | 23,054203 | 332,640 | 2 |
| 590 | 404,096 × 214,676 | 0,988010 | 10,121357 | 20,242715 | 378,840 | 2 |

İki satır da replacement `20 mm ≥82 independent sample` kapısını büyük
farkla kaçırır. `2` bay sonucu planner formülü
`1 + ceil(max(0, 444,375-safe_width) / min(430, safe_width-10))` ile
üretilmiştir. XIMEA görünür renk vermediği için güvenli additive mimari
`1× frozen RGB + 2× XIMEA = 3 camera body` olur; bu da sampling fail'ini
iyileştirmez.

`20 mm = 82 sample` için band başına izin verilen en büyük FOV yalnız
`409×20/82 = 99,756098 mm`'dir. Bunun safe width'i `93,521341 mm`, 10 mm
overlap sonrası pitch'i `83,521341 mm` ve gereken spectral bay sayısı `6`'dır.
Bu FOV için `520–590 mm` WD'de `52,758736–59,860873 mm` focal gerekir; retained
XIMEA calibrated kitindeki en uzun lens `35 mm`'dir. Dolayısıyla
`1 RGB + 6 XIMEA = 7 body` sonucu yalnız camera-count alt sınırı
hesabıdır, buildable exact stack değildir.

Bir XIMEA raw mosaic lane'i `2048×1088×15×10 = 334,233600 Mbit/s` üretir:

| Mimari | Raw 10-bit / 15 Hz (Mbit/s) | +%20 headroom (Mbit/s) |
|---|---:|---:|
| 1 RGB + 2 XIMEA, approved 16 mm geometry | 1.297,612800 | 1.557,135360 |
| 1 RGB + 6 XIMEA, theoretical service sampling | 2.634,547200 | 3.161,456640 |

Bu toplamlar ayrı USB root'ları, synchronized triggers, serialized calibration,
flat-field/spectral correction, registration ve inference yükünü içermez.
Düşük `blur_px` değeri coarse band sampling'in sonucudur; H3 fail'ini
iyileştiren optical performans değildir.

### 13.5 Dated public cost ve completeness

| Stack | Checked-on public component kanıtı | Bilinen subtotal | Tam sıralamayı engelleyenler |
|---|---|---:|---|
| JAI, 1 bay/1 body | body `5.400 USD`; lens `1.234 USD`; window `153 USD` | `6.787 USD` | exact HSI light suffix/adet, NIC, 10GigE cable, power/trigger, calibration target/file, mount/frame/hood, landed quote |
| XIMEA approved geometry, 2 bodies + RGB | body `Get Quote`; 2×(lens `635 USD` + window `153 USD`) | `1.576 USD + 2×UNKNOWN body`; frozen RGB hariç | body/kit price ve lifecycle, exact light, multiple USB roots/cables, calibration/integration |
| XIMEA theoretical service, 6 bodies + RGB | 6×(lens + window) | `4.728 USD + 6×UNKNOWN body`; frozen RGB hariç | ayrıca exact `52,76–59,86 mm` calibrated lens zinciri yok |

JAI body fiyatı 2026-08-14 tarihli
[Machine Vision Direct listing'inden](https://machinevisiondirect.com/products/jai-fs-3200t-10ge-nnc),
lens fiyatı aynı tarihli
[B&H listing'inden](https://www.bhphotovideo.com/c/product/1894413-REG/jai_jvs_c118_0824_c3_lens_for_apex_fusion.html)
alınmıştır. Edmund'un manufacturer-commerce sayfası aynı lensi `1.295 USD`
olarak gösterir; karşılaştırma subtotalı daha düşük tarihli vendor değerini
kullanır ve bunu landed quote saymaz. XIMEA body yalnız quote'dur. Bu nedenle
hiçbir multispectral satır H8 price-performance sıralamasına giremez ve satın
alma önerisi üretmez.

### 13.6 H1–H10 hard screen ve disposition

| Gate | JAI `FS-3200T` | XIMEA `SM5X5-7NIR2` |
|---|---|---|
| H1 complete identity | `FAIL_COMPLETE_STACK_IDENTITY`: camera/lens/window/internal bands exact; light suffix/adet, NIC/cables/power/trigger/calibration/mount açık | `FAIL_SUPPLY_COMPLETE_STACK_IDENTITY`: body/lens/window/filter family exact; Active/discontinued çelişkisi, quote, light ve integration açık |
| H2 timing | `PASS_DESK_STAGE_B_OPEN`: simultaneous, global, hardware trigger, 107 fps, min. 14,73 µs; installed 170 µs photon/timing ölçülmedi | `PASS_DESK_STAGE_B_OPEN`: global, hardware trigger, 170 fps, min. 30 µs; multi-body sync ölçülmedi |
| H3 native sampling | `PASS_ACTION_CARRIER_AND_NIR_CALC`; R/B half-lattice açıkça sınırlandı | `FAIL_REPLACEMENT / AUXILIARY_THRESHOLD_MISSING`; 16 mm'de 20,2–23,1 sample, theoretical 6 bay |
| H4 optics/geometry | `PASS_PRESCREEN_STAGE_C_OPEN`; exact lens circle/focus/WD/window, installed MTF/transmission açık | `FAIL_MODE_A_AND_MATCHED_EXACT_LENS`; 16 mm WD/FOV fail, gereken 52,76–59,86 mm exact calibrated lens yok |
| H5 spectrum | `PASS_BAND_EDGES_FILTER_CURVES_OPEN`; band uçları ve VIS-NIR lens/window exact, serialized response/throughput açık | `PASS_SERIALIZED_DEFINITION`; 24 center/internal filter/lens/window exact, her gövdenin calibration file'ı zorunlu |
| H6 interface | `PASS_RAW_MATH / FAIL_CURRENT_PHYSICAL_LANE` | `PASS_ONE_LANE_MATH / FAIL_MULTI_LANE_CURRENT_PROOF` |
| H7 registration/compute | `PASS_SINGLE_BODY_ARCHITECTURE / FAIL_CURRENT_REGISTRATION_COMPUTE_PROOF` | `FAIL_CURRENT_PROOF`: RGB korunur ama 3/7 body sync, correction, registration ve compute kanıtsız |
| H8 cost | `FAIL_PRICE_RANKING`: `6.787 USD` yalnız partial | `FAIL_PRICE_RANKING`: quote-only body, ışık/kit/integration ve service lens zinciri eksik |
| H9 task value | `PASS_EXACT_T2_DIRECTIONAL`: exact-camera paired RGB kontrolü aşağıda task trigger'ını açar; action safety değil | `FAIL_PAIRED_RGB_CONTROL_FOR_THIS_STACK`: Gao çalışması yönsel classification, paired RGB yok |
| H10 safety architecture | `PASS_ARCHITECTURE / PHYSICAL_A_E_OPEN`: Bayer görünür korunur, hiçbir safety gate bypass edilmez | `FAIL_REPLACEMENT / CONDITIONAL_AUX`: NIR-only action olamaz; additive RGB korunur fakat utility threshold yok |

Disposition:

- **JAI:** `CONDITIONAL_CHALLENGER_TASK_TRIGGER_OPEN_H6_H8_PHYSICAL_CLOSED`.
  Exact-camera Tier-2 görev sinyali yeni veri A/B'sini gerekçelendirebilir;
  stack complete, interface/compute ve fiziksel A–E kapanmadan A/B-eligible
  veya satın alınabilir değildir.
- **XIMEA:** `SCREENED_OUT_H3_H4_H7_H8_H9`. Raw independent sampling,
  calibrated-lens ve body-count sonucu fiyat/performans proof challenger'ını
  kapatır. Yeni exact SKU ancak 20 mm için ≥82 independent sample, buildable
  520–590 mm lens zinciri, paired RGB task kanıtı ve complete cost getirirse
  yeniden açılır.

### 13.7 Tier-2 görev kanıtı ve challenger trigger'ı

Fischer ve diğerlerinin 2024 tarihli
[*A comparative study of RGB and multispectral imaging for weed detection in
precision agriculture*](https://publica.fraunhofer.de/entities/publication/6ccbec33-82c8-4b18-9145-ba924096769f/details)
çalışması exact `FS-3200T-10GE-NNC`'yi tractor üzerinde yaklaşık `1,8 m`'den,
iki `EFFI-FLEX-HSI` ile `5 fps`/walking speed'de kullandı. Üç gün/üç hafta
boyunca güneşli ve bulutlu koşullarda 508 image, 3.189 weed ve 3.199 crop
instance topladı; Mask R-CNN RGB, RGB+NIR1 ve RGB+NIR1+NIR2 kontrolleri aynı
veri protokolünde karşılaştırıldı.

| Input | mAP@50–95 | mAP@50 | Crop AP@50 | Weed AP@50 |
|---|---:|---:|---:|---:|
| RGB | 55,9 ±0,6 | 76,8 ±0,7 | 95,5 ±0,6 | 58,2 ±1,2 |
| RGB+NIR1 | 60,0 ±0,8 | 78,5 ±0,9 | 95,3 ±0,5 | 61,8 ±1,8 |
| RGB+NIR1+NIR2 | 62,1 ±1,0 | 81,3 ±1,1 | 94,1 ±0,5 | 68,5 ±1,9 |

`FACT_T2`: beş-channel satırı RGB'ye karşı mAP@50–95'te `+6,2 puan` ve
weed AP@50'de `+10,3 puan` verir; crop AP@50 `-1,4 puan` değişir. Çalışmanın
alt analizinde weed AP@50 artışı erken büyümede `50→72`, ileride `54→63`,
güneşlide `42→58` ve bulutluda `58→67`'dir.

Bu güçlü **task trigger**, target-rig güvenlik kanıtı değildir: `70/15/15`
tek split, 20 bootstrap tekrar, alanın `≤%0,1`'i küçük nesnelerin filtrelenmesi,
bbox AP semantiği, `1,8 m`/`5 fps` ve yalnız üç gün/üç hafta koşulu target
`520–590 mm`, `15 Hz`, instance-mask/track/action veya chemical safety ile
eşdeğer değildir. Bu nedenle H9 açılır; H1/H6/H7/H8 ve fiziksel A–E kapanmaz.

Gao ve diğerlerinin 2018 tarihli
[*Near-infrared snapshot mosaic hyperspectral imagery for pre-emergence
weed/maize classification*](https://biblio.ugent.be/publication/8557865)
çalışması maize ve üç weed sınıfında mean correct rate olarak sırasıyla
`1,000 / 0,789 / 0,691 / 0,752` bildirir. Ancak paired RGB kontrolü yoktur ve
görev instance segmentation/track/action değil classification'dır.
`FACT_T2_DIRECTIONAL` olarak XIMEA sınıfını keşfetmeye yarar; H9'u açmaz.

## 14. Pass 4 ephemeral validation receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan 63 deterministic assertion
çalıştırıldı. JAI span/WD/GSD/target/blur/safe-swath, R/B independent support
ve 8/10/12-bit üç-stream payload; XIMEA raw `floor` lattice, 16 mm WD/FOV,
target sampling, bay count, service-lens aralığı, 2/6-lane payload, 24 band
sayısı/uçları ve üç public partial-cost toplamı PASS verdi. İlk iki koşuda
validation fixture'ındaki fazla hassas iki hard-coded XIMEA expected literal'i
exact formüle bağlandı; survey'nin altı-haneli gösterim değeri değişmedi.

```text
jai_wd_480=551.478260869565
jai_payload10_15_headroom=1698.693120000000
ximea_band_lattice=409x217
ximea_fov_wd590=404.096000000000
ximea_service_fov=99.756097560976
ximea_service_bays=6
ximea_service_focal_range=52.758735838644..59.860873355385
PASS: 63 snapshot-multispectral geometry, lattice, target, payload, band and partial-cost assertions
```

Bu receipt optical throughput, installed MTF, SNR, spectral crosstalk, ışık
uniformity, multi-camera trigger skew, transport reliability, model utility
veya fiziksel A–E ölçmez.

## 15. RGB+thermal screen'i

### 15.1 Safety mimarisi ve bounded shortlist

Thermal-only action mimarisi terminal olarak reddedilmiştir. Termal sinyal
bitki su durumu, gölge, rüzgâr, toprak nemi ve gün içi enerji dengesiyle
değişebilir; `NETD` tek başına crop/weed ayrımı veya kimyasal aksiyon
güvenliği değildir. Bu nedenle iki credible aday da frozen Basler RGB action
kanalına **additive** olarak modellendi ve her LWIR kamera için görünür
pencereden ayrı, dedicated bir thermal aperture zorunlu tutuldu.

Retained katalog shortlist'i iki exact gövdeyle sınırlıdır:

1. **Geometri/fiyat primary — Teledyne FLIR Boson+
   `22640AS50-6IARX`.** `640×512`, 12 µm, industrial-grade, radiometric,
   shuttered ve factory `9,2 mm` compact lensli exact model. Mode A ortak FOV'a
   tek LWIR gövdeyle girer; fakat row-at-a-time sensor readout ve source-bound
   effective integration eksikliği H2'yi terminal kapatır.
2. **Snapshot timing backup — FLIR A6751 SLS `29439-251` + lens
   `4215424`.** `640×512`, 15 µm cooled SLS, snapshot readout, exact 17 mm
   `7,5–12 µm` lens. H2'yi desk'te geçer; fakat en kısa factory lensle
   Mode A FOV'a giremez, iki thermal bay, en az 3 toplam camera body ve
   quote-only maliyet gerektirir.

Bu adlandırma satın alma sırası değildir. “Primary” en iyi kompakt katalog
geometrisini, “backup” ise timing-clean kontrolü ifade eder; aşağıdaki hard
screen sonunda **ikisi de challenger olarak tutulmaz**.

### 15.2 Exact Boson+ stack ve timing hard fail'i

`FACT_T1`: [exact Boson+ ürün sayfası](https://oem.flir.com/products/boson-plus/?model=22640AS50-6IARX&segment=oem&vertical=lwir)
model `22640AS50-6IARX` için in-production, `640×512`, 12 µm,
industrial `≤20 mK`, radiometric, `8–14 µm`, varsayılan 60 Hz / runtime
30 Hz, factory NUC/FFC, USB3/CMOS/MIPI video ve UART/USB/I2C control verir.
Doc `102-2013-45`, Release 114, resmi yayın tarihi **2025-09-05** olan
[Boson+ Product Datasheet](https://flir.netx.net/file/asset/55485/original/attachment/)
exact `22640 AS50` optiği için `49,9·39,3°`, `f/1,01`, `9,2 mm`, yeni/refocus
near-focus `7,5/0,3 m`, `%90` average transmission, `%42` on-axis Nyquist MTF,
`<%18` distortion, M18×0,5, 20 mm max lens çapı, 40 mm camera length ve
36 g camera+lens ağırlığını verir. `520–590 mm` için üreticinin focus
tool'u ile refocus gerekir.

Exact sensor timing sonucu katalogdaki “Full-frame snapshot via GUI” alanından
çıkarılamaz. Release 114 şunları doğrudan söyler:

- microbolometer ROIC her frame'i **bir satırı bir defada** okur;
- `EXT_SYNC` yükselen kenarından `0,5 ms` sonra sensor **readout başlar**;
  bu sinyal ortak/global integration anı olarak tanımlanmaz;
- 15 Hz, 60 Hz sensor yolundan `frame-skip=3` ile üretilen output rate'tir;
  60 Hz'den uzak slave rate'lerde üretici non-uniformity/image quality
  bozulması ve daha sık FFC bekler;
- nominal thermal time constant `8 ms`, pre-AGC pipeline latency yaklaşık
  `6 ms`'dir; 8 ms latency hesabına dahil değildir;
- shuttered default automatic FFC sırasında video son geçerli frame'i tekrar
  ederek donar. Telemetry'deki FFC state/frozen-frame politikaya dahil edilmeden
  thermal frame action'a eşlenemez.

RHP [`RHP-BOS-CL-SY-IF`](https://oem.flir.com/products/boson-camera-link-interface-board/?model=RHP-BOS-CL-SY-IF&segment=oem&vertical=lwir)
Camera Link Base, master/slave sync, 5–26 V ve 3,3 V TTL/UART yolunu exact
Boson/Boson+ accessory olarak tanımlar. Ancak vendor sayfası sync-enabled
board'u yalnız 30 Hz diye listelerken camera datasheet düşük sync rate'in
mümkün fakat bozulmuş olabileceğini söyler. Bu nedenle 15 Hz output'u 15 Hz
global capture gibi yorumlamak veya USB frame arrival'ı trigger anı saymak
yasaktır.

**H2 sonucu:** `FAIL_ROW_SEQUENTIAL_READOUT_AND_EFFECTIVE_INTEGRATION_UNKNOWN`.
Tek-shot output buffer modu duplicate/drop riskini azaltabilir; sensoru
snapshot/global yapmaz. Bu hard fail, Boson+'ı geometri ve SWaP avantajına
rağmen product challenger listesinden çıkarır.

### 15.3 Exact snapshot backup, lens ve dedicated LWIR window

`FACT_T1`: FLIR support datasheet Rev `90835`, son değişiklik **2023-03-08**,
exact [`A6751 SLS`, P/N `29439-251`](https://support.flir.com/dsdownload/assets/29439-251-en-us.html)
için strained-layer superlattice, `7,5 µm` alt / `10–11 µm` üst spectral
range, `640×512`, 15 µm, `≤45 mK` (`≤40 mK` typical), closed-cycle rotary
cooling, **snapshot** readout, asynchronous integrate-while-read / then-read,
Sync In/Out, timestamp, `480 ns–full frame` integration, `0,0015–125 Hz`
full-window, 14-bit ve radiometric GigE Vision verir. Gövde `226×102×109 mm`,
lenssiz `2,3 kg`, 24 V'ta `<24 W` ve `-20–50 °C`'dir.

Exact [FLIR `4215424` lens](https://www.flir.com/products/17-mm-f2.5-lwir-fpo-manual-lens?segment=solutions&vertical=rd+science)
`17 mm`, `f/2,5`, `7,5–12 µm`, four-tab FPO manual bayonet, manual
`0,1 m–∞` focus, `%92,18` average transmission, `<%3` distortion ve `0,44 kg`
olarak tanımlanır. A6751 ürün sayfası bu exact lensi compatible accessory
olarak listeler. Aynı lens sayfası ayrıca `3 m` bir distance alanı yayınlar;
alanın anlamı focus-range satırıyla source-level uyuşmaz. Bu nedenle
`520–590 mm` installed focus **PASS sayılmaz**. Bundan bağımsız olarak en
kısa factory 17 mm optiğin FOV'u zaten Mode A için dardır.

Her iki thermal yol için exact protective-window adayı Crystran
[`GEP50-3AR/DLC`](https://www.crystran.com/ge-50mm-x-3mm-optically-polished-ar-dlc-7-14/),
50 mm çap × 3 mm optically polished germanium ve `7–14 µm` AR/DLC'dir.
Spektral bant Boson+ `8–14 µm` ve A6751/lens `7,5–12 µm` yollarını kapsar.
2026-08-14 live receipt'i **`POA` / out of stock** gösterirken sayfanın
structured product metadata'sı `1.375 GBP` taşır. İki fiyat temsili çeliştiği
için usable public price `quote_required`'dır; `1.375 GBP` total'a eklenmez.
Bu parça görünür Basler penceresinin yerine kullanılmaz; RGB ve LWIR ayrı
aperture ister. Installed tilt, stand-off, cone clearance, thermal
emission/reflection, vignetting, refocus ve calibration Stage C'de açıktır.

### 15.4 Common-FOV geometri, native destek ve camera count

#### Boson+ Mode A prescreen

`CALC`: yatay sensor span'i `640×0,012 = 7,68 mm`'dir. Exact 9,2 mm
lens için:

| Ground FOV (mm) | WD (mm) | Thermal GSD (mm/px) | 10 mm (px) | 20 mm (px) | Common-safe üst sınır (mm) | 8 ms response displacement (px) |
|---:|---:|---:|---:|---:|---:|---:|
| 474 | 577,012500 | 0,740625 | 13,502110 | 27,004219 | 444,375 | 10,801688 |
| 480 | 584,200000 | 0,750000 | 13,333333 | 26,666667 | 450,000 | 10,666667 |
| 484 | 588,991667 | 0,756250 | 13,223140 | 26,446281 | 453,750 | 10,578512 |

WD'nin tamamı `520–590 mm` içindedir; nominal co-boresight varsayımında bir
RGB + bir Boson+ = **2 body / 1 optical bay** ve 480 mm ortak FOV mümkündür.
Tablodaki safe width, iki lens merkezi/pose'u dondurulmadığı için calibrated
common-valid-FOV değil, `min(RGB FOV, thermal FOV)×1920/2048` üst sınırıdır.
`<%18` lens distortion nedeniyle fiziksel registration maskesi bunu azaltabilir.

`8 ms ×1 m/s = 8 mm` characteristic displacement satırı, shutter exposure
blur'u değil, source-bound microbolometer temporal-response risk ölçeğidir.
Boson+ effective integration/global capture tanımlanmadığından 170 µs blur
PASS **hesaplanmaz**. Auxiliary thermal'in düşük native target desteği RGB'nin
`41/82 px` action desteğiyle karıştırılmaz.

#### A6751 Mode A fail ve iki-bay sonucu

`CALC`: yatay sensor span'i `640×0,015 = 9,6 mm`'dir.

| WD (mm) | Thermal FOV (mm) | GSD (mm/px) | 10 mm (px) | 20 mm (px) | Safe width (mm) | Thermal bay | 170 µs analytic blur (px) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 520 | 284,047059 | 0,443824 | 22,531478 | 45,062956 | 266,294118 | 2 | 0,383035 |
| 590 | 323,576471 | 0,505588 | 19,778941 | 39,557882 | 303,352941 | 2 | 0,336242 |

480 mm FOV için gereken WD `867 mm`'dir ve mevcut zarfı ihlal eder. Tersine,
`520–590 mm` WD ve `474–484 mm` FOV için gereken focal aralık yaklaşık
`10,113–11,712 mm`'dir; A6751'in en kısa factory lensi 17 mm'dir. Planner bay
formülü her iki WD ucunda 2 thermal bay verir. Frozen tek RGB full swath'i
koruduğu için en küçük mimari **1 RGB + 2 A6751 = 3 body** olur. İki
A6751 gövde+lens en az `2×(2,3+0,44)=5,48 kg` ve `<48 W` steady-state camera
power demektir; window, power supply, cable, mount ve vibration isolation buna
dahil değildir.

Snapshot integration 170 µs'e programlanabilir ve tablodaki analytic blur
kapıyı geçer. Bu, 170 µs'te bitki/toprak thermal CNR, radiometric accuracy,
cooler vibration veya iki-camera sync PASS'i değildir.

### 15.5 Interface, payload ve dated cost completeness

| Mimari / format | Thermal raw @15 Hz | RGB dahil raw @15 Hz | RGB dahil +%20 | Toplam body |
|---|---:|---:|---:|---:|
| 1× Boson+ 16-bit pre-AGC + frozen Bayer10 | 78,643200 Mbit/s | 707,788800 Mbit/s | 849,346560 Mbit/s | 2 |
| 1× A6751 14-bit | 68,812800 Mbit/s | N/A; swath eksik | N/A | 2 fakat coverage fail |
| 2× A6751 14-bit + frozen Bayer10 | 137,625600 Mbit/s | 766,771200 Mbit/s | 920,125440 Mbit/s | 3 |

Boson+ 16-bit pre-AGC/T-linear USB ve A6751 14-bit GigE formatları Tier-1
kaynaklıdır. Nominal payload'lar ilgili USB3/GigE linklerinin altındadır;
Camera Link frame grabber, iki A6751 için dedicated network capacity, cable,
packet loss, deterministic timestamp association ve mevcut RTX 3090'da
fusion/inference kapasitesi fiziksel olarak kanıtlanmamıştır.

| Stack | 2026-08-14 public receipt | Bilinen partial cost | H8'i kapatmayanlar |
|---|---|---:|---|
| Boson+ primary, 1 LWIR body | Suntek exact `22640AS50` family ve listelenen `6IARX` dahil varyantlar `5.375–6.500 USD`; RHP board `399 USD`; Crystran window live `POA`/out of stock | `5.774–6.899 USD + window_quote` | dropdown exact `6IARX` fiyat eşlemesi, window fiyat çelişkisi, Camera Link frame grabber/cable/power, visible+LWIR dual-window frame, calibration target, mount, landed quote; frozen RGB hariç |
| A6751 backup, 2 LWIR body | camera `29439-251` ve lens `4215424` distributor'da `On Request`; 2× Crystran window `POA` | `2×(camera_quote + lens_quote + window_quote)` | power supplies, dual GigE/sync cables, cooling/vibration mount, calibration/software, dual-window frame, landed quote; frozen RGB hariç |

Suntek [family listing'i](https://thermal.suntekglobal.com/product/teledyne-flir-boson-640-x-512-9-2mm-50-hfov-short-lens/)
exact family part numaralarını ve fiyat aralığını verir, fakat UI receipt'i
hangi fiyatın exact `6IARX`'e ait olduğunu göstermez. RHP board
[vendor fiyatı](https://www.oemcameras.com/products/rhp-bos-cl-sy-if-htm)
`399 USD`'dir. A6751 ve exact lens
[distributor satırları](https://www.datatec.eu/at/en/teledyne-flir-29439-251)
quote-only'dir. Crystran visible `POA` ile structured `1.375 GBP` çelişkisi
fiyat olarak normalize edilmedi. Para birimi dönüşümü, vergi, shipping,
tariff ve local availability varsayılmadı. Bu nedenle hiçbir satır
complete-stack USD/mm, baseline cost ratio veya price-performance winner
üretmez.

### 15.6 H1–H10 hard screen ve disposition

| Gate | Boson+ `22640AS50-6IARX` primary | A6751 SLS `29439-251` backup |
|---|---|---|
| H1 identity | `FAIL_COMPLETE_STACK_IDENTITY`: exact camera/lens/radiometric state/window/sync board var; exact suffix fiyatı, frame grabber/cable/power/mount/calibration eksik | `FAIL_COMPLETE_STACK_IDENTITY`: camera/lens/window exact; cable/power/software/calibration/mount ve fiyat quote-only |
| H2 timing | **`FAIL`**: sensor row-at-a-time; EXT_SYNC readout başlangıcını bağlar, global integration değil; 8 ms time constant; 15 Hz frame-skip; FFC freeze | `PASS_DESK_STAGE_B_OPEN`: snapshot, Sync In/Out, timestamp, 480 ns–full-frame, 15 Hz programlanabilir; installed trigger skew/CNR ölçülmedi |
| H3 native geometry | `PASS_AUX_REPORT_ONLY`: 13,2–13,5 / 26,4–27,0 thermal px; RGB action samples korunur | `PASS_AUX_REPORT_ONLY`: 19,8–22,5 / 39,6–45,1 thermal px; utility/CNR threshold yok |
| H4 optics/geometry | `PASS_MODE_A_PRESCREEN_STAGE_C_OPEN`: WD/focus/spectrum uyumlu; <%18 distortion, dual-window vignetting/MTF/calibration açık | **`FAIL_MODE_A`**: 17 mm ile 284–324 mm FOV; 2 bay; gerekli 10,113–11,712 mm exact factory lens yok; lens sayfasındaki `0,1 m–∞`/`3 m` alanları çelişkili; dual-window Stage C açık |
| H5 spectrum | `PASS_DEFINITION`: 8–14 µm factory lens + ayrı 7–14 µm Ge window | `PASS_DEFINITION`: 7,5–10/11 µm body + 7,5–12 µm lens + ayrı 7–14 µm Ge window |
| H6 interface | `PASS_RAW_MATH / FAIL_PHYSICAL_LANE`: 16-bit payload kaynaklı; 15 Hz sync-board çelişkisi, frame grabber ve deterministic frame receipt açık | `PASS_RAW_MATH / FAIL_DUAL_LANE_PROOF`: 14-bit GigE; iki port/cable/timestamp/packet-loss kanıtı yok |
| H7 registration/compute | **`FAIL_CURRENT_PROOF`**: 2 body common-FOV yalnız prescreen; pose/skew/FFC/common mask/calibration/compute açık | **`FAIL_CURRENT_PROOF`**: 3 body, iki thermal bay; shared sync, registration, cooler vibration ve compute açık |
| H8 cost | **`FAIL_PRICE_RANKING`**: family range + mixed currency + zorunlu parçalar eksik | **`FAIL_PRICE_RANKING`**: camera/lens quote-only, iki-bay integration eksik |
| H9 task value | `PASS_DIRECTIONAL_T2_ONLY`: paired visible/thermal paddy paper'ı var; exact camera, rig, instance-mask/track/action transferi yok | aynı; A6751 için crop/weed paired source yok |
| H10 safety | `PASS_ARCHITECTURE_ONLY`: RGB korunur; hard fail nedeniyle A/B eligible değil; thermal-only terminal reject | aynı; fiziksel A–E ve chemical boundary bypass edilemez |

Dispositions:

- **Boson+:** `SCREENED_OUT_H2_H7_H8`. En ucuz/kompakt ve tek-bay catalog
  stack olsa da row-sequential sensor timing ile exact action anı kurulamaz.
  Yeni bir Boson-benzeri candidate ancak source-bound global/snapshot capture,
  effective temporal response, deterministic 15 Hz frame association ve
  controlled FFC policy getirirse yeniden incelenir.
- **A6751:** `SCREENED_OUT_H4_H7_H8`. Bu bir timing referansıdır, buildable
  proof challenger değildir. Yeniden açılması exact `~10,1–11,7 mm` compatible
  lens, tek-bay veya tam fiyatlanmış iki-bay mekanik, synchronized registration
  ve measured task trigger gerektirir.
- **Thermal-only:** `TERMINAL_REJECT_SAFETY`. Daha yüksek NETD, daha pahalı
  camera veya olumlu bir classification paper'ı RGB crop-safety kanalını
  kaldırma yetkisi vermez.

### 15.7 Tier-2 görev kanıtı ve trigger sonucu

Zamani ve Baleghi'nin 2023 tarihli
[*Early/late fusion structures with optimized feature selection for weed
detection using visible and thermal images of paddy fields*](https://link.springer.com/article/10.1007/s11119-022-09954-8)
birincil çalışması 100 paired visible/thermal paddy image'inde rice/weed
segmented object'lerinden morphological, spectral, textural ve 11 thermal
feature çıkarır; en iyi late-fusion ELM+GA accuracy'si `%98,08`'dir. Yazarların
[dataset v3 receipt'i](https://data.mendeley.com/datasets/9xg52j8tmw/3)
100 pair, `595×385`, natural light, yaklaşık eşzaman, camera merkezleri arası
5 cm, 1,2 m capture height ve T8 camera'yı kaydeder. Fakat dataset metni
thermal'i aynı zamanda “near-infrared” diye adlandırır; exact spectral band,
trigger skew ve sensor timing vermez. Küçük object-classification seti,
520–590 mm instance-mask/track/action veya chemical safety A/B'si değildir.

Ranario ve diğerlerinin 2026 tarihli
[*Thermal image segmentation in weedy fields via synthetic RGB-trained models
and GAN-based cross-modality alignment*](https://www.sciencedirect.com/science/article/pii/S2643651526000518)
çalışması açık alandaki thermal görüntüde plant/weed/background kontrastının
benzer sıcaklıklar, gölge, rüzgâr ve nemle zorlaştığını raporlar. Çözüm,
thermal'i RGB'den bağımsız action channel yapmak değil, RGB-trained maskeleri
RGB-to-thermal translation/template matching ile termal fenotiplemeye aktarmaktır.
Bu da RGB'nin korunması yönünü destekler; paired RGB-vs-RGB+LWIR action
kazancı vermez.

`FACT_T2_DIRECTIONAL` sonucu thermal task value'nun teorik olmadığını, fakat
koşula ve registration'a bağlı olduğunu gösterir. Repository'de passing
hood/light sonrası fiziksel visible-collapse failure bin'i, aynı anda ölçülmüş
plant/soil thermal contrast veya exact stack'e ait instance-mask/track/action
kazanımı yoktur. Bu nedenle modality trigger'ı kapalıdır; iki exact adayın
hard fail'leri ayrıca devam eder. Sonuç **no thermal A/B challenger** ve frozen
RGB baseline değişikliği yoktur.

## 16. Pass 5 ephemeral validation receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan 24 deterministic assertion
çalıştırıldı. Boson+ ve A6751 span/FOV/WD/GSD/10–20 mm support/safe-width,
A6751 bay count ve 170 µs blur, iki formatın 15 Hz payload/headroom'u,
RGB-additive toplamları ve public camera+board cost bounds aritmetiği PASS
verdi. İlk current re-run, A6751'in hard-coded full-precision expected
literal grubunu yakaladı; fixture exact formül/altı-hane receipt değerlerine
yeniden bağlandı ve survey tablo değerleri değişmedi.

```text
boson_wd_480=584.200000000000
boson_gsd_480=0.750000000000
boson_tau8ms_displacement_px_480=10.666666666667
boson_rgb_plus_thermal_headroom=849.346560000000
a6751_fov_wd520=284.047058823529
a6751_fov_wd590=323.576470588235
a6751_wd_480=867.000000000000
a6751_thermal_bays=2
a6751_rgb_plus_2thermal_headroom=920.125440000000
PASS: 24 thermal geometry, target, timing-risk, payload, bay-count and known-cost assertions
```

Bu receipt effective thermal integration, plant/soil contrast, installed
window transmission/emission, MTF, common-FOV registration, trigger skew, FFC
policy, transport reliability, cooler vibration, model utility veya fiziksel
A–E ölçmez.

## 17. RGB+depth screen'i

### 17.1 Güvenli rol, bounded shortlist ve host-stereo reject'i

Depth bu survey'de replacement değildir. Dondurulmuş Basler RGB action
kanalı, `2048²` raster'ı, 41/82 px hedef kapıları, dış `64 px` abstain halkası
ve fiziksel A–E ile aynen korunur. Depth yalnız height/structure hypothesis'i
için auxiliary kanaldır. Bu nedenle iki retained çözüm de toplam **iki camera
body** taşır:

| Rol | Exact aday | Depth nerede üretilir? | Kısa karar |
|---|---|---|---|
| Integrated RGB-D primary | Orbbec Gemini 335L, model `G40055-170` | Orbbec `MX6800` ASIC içinde stereo depth ve D2C | en düşük bilinen incremental cost; exact 520–590 mm p95/valid-fraction ve frozen-RGB sync'i yok |
| Industrial backup | Basler blaze-101, order `107796`, Sony DepthSense `IMX556` | camera-side ToF range/depth/confidence components | exact near-range typical accuracy var; multi-subframe full-frame timing, intended-ambient validity ve complete trigger-power cost açık |

Bu iki adaydan sonra depth SKU araması durdurulmuştur. Stereolabs ZED gibi
passive **host stereo** mimarisi exact SKU shortlist'ine alınmaz:
[`ZED SDK Recommended Specifications`](https://docs.stereolabs.com/docs/development/zed-sdk/specifications)
2026-08-14'te PC için NVIDIA RTX ve compute capability `≥7.5` şartını verir;
Stereolabs'ın ROS dokümanı depth computation'ın seçilen GPU'da yapıldığını
ayrıca [açıklar](https://docs.stereolabs.com/docs/integrations/ros-2/zed-stereo-node).
Bu, mevcut tek-camera/RTX 3090 proof sözleşmesine ölçülmemiş
host GPU yükü ekler ve H7'yi terminal olarak ihlal eder. Karar:
`TERMINAL_REJECT_HOST_STEREO_HIDDEN_GPU`; yeni bir stereo body fiyatı taranmaz.

### 17.2 Orbbec Gemini 335L exact primary

`FACT_T1`: üreticinin
[`G40055-170` product page'i](https://www.orbbec.com/products/stereo-vision-camera/gemini-335l/)
ve [`Gemini 330 Series Datasheet V1.6`](https://www.orbbec.com/wp-content/uploads/2025/06/Gemini-330-series-Datasheet-V1.6.pdf)
(revision-history girdisi 2025-04-10; 2026-08-14'te kontrol edildi) şu exact
sınırları verir:

- active+passive stereo, `95 mm` baseline, `850±6 nm` Class-1 VCSEL ve
  visible+NIR-pass depth path;
- `1280×800 @30 fps` native Y16 depth, nominal `90°×65° ±3°`; fixed-focus
  global-shutter IR; `0,17–20 m+`, ideal `0,25–6 m`;
- `1280×800` global-shutter, IR-cut RGB; `94°×68° ±3°`; depth/RGB/IR için
  aynı hardware timestamp kaynağı ve camera-side D2C;
- Orbbec ASIC içinde hardware disparity/depth; USB 3 Type-C, `133 g`, ortalama
  `<3 W`, depth/RGB/IR/point-cloud output ve 8-pin hardware sync;
- depth manual exposure `1–199.000 µs`, default `3.000 µs`; free-trigger
  modunda 15 Hz input ancak camera fixed rate `30 fps` seçildiğinde izinli
  (`66,7 ms` minimum trigger interval / `≤15 Hz`);
- multi-device dokümanında aynı-camera-family RGB/depth sync bound'u auto
  exposure kapalıyken `≤5 ms`; datasheet başka yerlerde `100 µs` external
  pulse, pin tablosunda `1 ms` VSYNC_IN ister. Exact frozen-Basler electrical
  interface ve skew bu çelişki altında fiziksel olarak kapanmalıdır;
- IP65 yalnız screw-locked USB ile ve **8-pin sync port kullanılmıyorken**
  kaynaklıdır. Proof için sync port açılırsa sealed ingress state'i yeniden
  doğrulanmadan IP65 iddiası taşınmaz.

Manufacturer depth-performance tablosu `2 m`de accuracy `≤±1%`, spatial
precision `≤0,8%`, temporal precision `≤0,4%` ve fill rate `≥99,5%` verir;
hepsi yüksek yansıtıcılı düz hedef/merkez ROI “typical” koşuludur. V1.6'da
`500 mm`den başlayan spatial-precision ve fill-rate grafiklerinin noktaları
tablo olarak yayımlanmamıştır. Dolayısıyla **520–590 mm exact numeric p95
error, single-frame precision ve valid-depth fraction `UNKNOWN`** kalır; 2 m
yüzdeleri lineer ölçeklenmez veya grafikten göz kararı okunmaz.

“Indoor/outdoor” ve “full sunshine” ifadeleri categorical manufacturer
claim'idir; exact spectral irradiance/lux sınırı veya 520–590 mm crop/soil
validity değeri yoktur. Datasheet ambient illumination ve target'ın gerçek
accuracy'yi değiştirdiğini açıkça söyler. SDK genel confidence property'leri
taşısa da V1.6 veya current SDK support/release kaydı bunların value/sentinel
semantics'ini `G40055-170`a bağlamaz. Bu nedenle candidate-specific
confidence map, threshold ve invalid-pixel sentinel da `UNKNOWN`dur.

Factory cover/lens/filter, depth ile RGB'yi kendi gövdesinde tanımlar; ayrı
sensör veya lens part number'ı yayımlanmaz. Eğer ortak hood ayrıca dış pencere
isterse, mevcut exact Edmund `#37-014` VIS-NIR pencere 425–1000 nm aralığıyla
850 nm'yi katalogda geçirir. Ancak `94°` cone, VCSEL çift geçişi, ghost,
vignetting, refocus, installed transmission ve Class-1 accessible emission
yeniden ölçülmeden window feasibility PASS değildir.

### 17.3 Basler blaze-101 on-device-depth backup

`FACT_T1`: Basler
[`blaze-101` Version 130](https://docs.baslerweb.com/blaze-101)
(release 2026-07-14; 2026-08-14'te kontrol edildi) order `107796`, Sony
`IMX556` area-scan ToF, integrated lens, `640×480`, `67°×51°`, short
`0,3–1,5 m`, long `0,3–10 m`, `20 fps` default/`30 fps` FastMode, GigE Vision,
hardware trigger/PTP, `940 nm` Class-1 VCSEL, IP67, `<690 g`, `<15 W` mean ve
`<85 ms` latency verir. Camera range, intensity ve confidence component'lerini
kendi içinde üretir; host stereo/GPU disparity yoktur.

Range dahilinde yayımlanan `±5 mm` **typical accuracy** ve `<1 mm` typical
temporal noise 520–590 mm'yi kapsar, fakat bu bir p95 saha sınırı değildir.
Basler'ın
[`Accuracy and Precision`](https://docs.baslerweb.com/accuracy-and-precision)
testi default settings, 20 dakika warm-up, `90%` yansıtıcılı beyaz düz hedef,
ambient ışık yok, `22°C`, merkez `40×40 px` ve **25-frame average** kullanır.
Tek kare, tüm FOV, leaf edge/occlusion veya soil/crop reflectance sonucu
yayımlanmamıştır.

Ambient claim de sınırlandırılmıştır. Basler'ın
[`Ambient Light Robustness`](https://docs.baslerweb.com/ambient-light-robustness)
testi `6 m`, `90%` düz beyaz hedef, `250 µs` exposure ve 940 nm ek ışık
kullanır. `920–970 nm`de `12,8 W/m²` (yaklaşık `60 klux` sunlight) noktasında
görüntü “usable” kalırken noise yaklaşık `7×` olur; sınır aşılınca sensor
saturate olur ve depth üretilemez. Bu değer 520–590 mm bitki/soil validity
PASS'i değildir.

Valid-pixel semantics exact ve loglanabilirdir:

- [`Confidence Threshold`](https://docs.baslerweb.com/confidence-threshold)
  camera içi her pixel için `0–65335` değer kullanır; threshold altındaki depth
  `Scan3dInvalidDataValue`ya, confidence sıfıra gider. Üretici uygulamalar
  değiştiği için genel threshold önermediğini açıkça belirtir.
- [`Scan 3d Invalid Data Value`](https://docs.baslerweb.com/scan-3d-invalid-data-value)
  default sentinel'i `0` verir; feature için invalid flag etkinleştirilmelidir.
  Bu semantics valid fraction'ı ölçülebilir kılar, fakat intended scene için
  bir minimum fraction veya mevcut ölçüm vermez.

Timing fail-closed tutulur. `ExposureTime` revision'a göre minimum `250 µs`
(≤rev07), `100 µs` (rev08–12) veya `50 µs` (≥rev13), maximum `1.000 µs`dür;
azaltmak measurement accuracy'yi düşürebilir. Current order code hardware
revision'ı encode etmez. Daha önemlisi standard depth mode farklı modulation
frekanslarında **çoklu subframe** birleştirir; katalog tek bir
`FrameDuration`/effective integration değeri yayımlamaz. Tek-subframe
250 µs smear hesabı düşük olsa da full depth-frame motion timing PASS'i
üretemez. Hardware trigger gerçektir: Line0 rising edge bir frame'i başlatır,
trigger-to-FrameActive typical `<300 µs`, max `500 µs`; Basler ayrıca ace/ace2
`ExposureActive` çıkışının blaze Line0'ı sürmesi için resmi wiring/config
path'i verir. Installed skew, full-frame timestamp ve `<85 ms` delivery
latency'nin tracker ile telafisi yine fiziksel Stage B'dir.

Factory bandpass/integrated cover path `940 nm` için tasarlanmıştır. Dış
Edmund `#37-014` pencere spektral aralıkta uyumludur; active emitter cone,
ghost, heating, Class-1 safety, focus ve installed accuracy henüz ölçülmediği
için H4/H5 yalnız katalog düzeyinde kapanır.

### 17.4 Matched geometri, native depth sampling ve common FOV

`CALC`: angular FOV ön-elemesi için
`ground_FOV = 2 × WD × tan(angular_FOV/2)` kullanıldı. Bu düz, optical-axis'e
normal ground varsayımıdır; distortion veya extrinsic calibration değildir.

| Aday / WD | Nominal ground FOV H×V (mm) | Native H-GSD (mm/px) | 10 mm (depth px) | 20 mm (depth px) | RGB safe `444,375 mm` üstündeki depth sample üst sınırı |
|---|---:|---:|---:|---:|---:|
| Gemini 335L / 520 mm | `1.040,000×662,553` | `0,812500` | `12,307692` | `24,615385` | `546,923077` |
| Gemini 335L / 590 mm | `1.180,000×751,743` | `0,921875` | `10,847458` | `21,694915` | `482,033898` |
| blaze-101 / 520 mm | `688,361×496,055` | `1,075564` | `9,297447` | `18,594895` | `413,155316` |
| blaze-101 / 590 mm | `781,025×562,831` | `1,220352` | `8,194360` | `16,388721` | `364,136889` |

Gemini'nin source-bound `±3°` horizontal tolerance'i ve WD uçları birlikte
ground width'i `986,923–1.243,461 mm` yapar; yine bir gövde frozen RGB
swath'ını geometrik olarak örter. blaze nominal H/V FOV'u da 520 mm'de bile
frozen yaklaşık `474–484 mm` square FOV'u örter. Bu yüzden ikisinde de
**depth bay count = 1**, total camera body = `1 RGB + 1 depth = 2`dir.

Tablodaki common-FOV sample değerleri yalnız co-centered analytic üst
sınırdır. Calibrated common-valid-FOV mask, edge invalidity, camera offset,
occlusion ve reprojection residual ölçülmediğinden safe action swath
`444,375 mm` otomatik olarak depth-valid sayılmaz.

Gemini'nin kendi global-shutter RGB'si yalnız intra-body registration
yardımcısıdır. `94°` nominal FOV'da 520–590 mm boyunca GSD
`0,871300–0,988590 mm/px`, 20 mm desteği yalnız `22,954–20,231 px`dir;
frozen action kanalının `≥82 px` kapısını geçmez. Upscale/D2C bunu native
sample olarak artırmaz. Dolayısıyla integrated RGB bile frozen Basler'ın
yerine geçemez.

### 17.5 Exposure, payload, interface ve camera count

Gemini için tek source-consistent desk configuration: depth/RGB global
shutter, AE off, manual depth exposure `170 µs`, fixed-rate `30 fps`, external
trigger `15 Hz`, Y16 depth ve gerekirse YUYV RGB'dir. `170 µs`te nominal
depth smear `0,209231 px` (520 mm) / `0,184407 px` (590 mm) olur. Default
`3.000 µs` bırakılırsa aynı değerler `3,692308/3,254237 px` olur ve H2
geçmez. `170 µs`te depth accuracy/fill korunacağına dair kaynak yoktur;
catalog timing eligibility, quality PASS değildir.

blaze için depth exposure tek-subframe değeridir. Revision-13 gövdede
`170 µs` ayarlanabilir; exact revision ve full multi-subframe acquisition
zamanı kaynakla kapanmadığı için yalnız single-subframe blur hesaplanır,
full-frame H2 `UNKNOWN/FAIL` kalır.

| 15 Hz raw stream | Raw (Mbit/s) | +%20 headroom (Mbit/s) | Transport sonucu |
|---|---:|---:|---|
| Gemini Y16 depth | `245,760000` | `294,912000` | Orbbec USB3 lane içinde analytic |
| Gemini Y16 depth + YUYV16 RGB | `491,520000` | `589,824000` | tek Orbbec USB3 lane; IR kapalı |
| Frozen Bayer10 + Gemini depth | `874,905600` | `1.049,886720` | iki dedicated USB3 root gerekir |
| Frozen Bayer10 + Gemini depth+RGB | `1.120,665600` | `1.344,798720` | iki root; sustained proof yok |
| blaze Coord3D_C16 depth + Confidence16 | `147,456000` | `176,947200` | dedicated GigE; quality-minimum diagnostic pair |
| blaze depth + confidence + Mono16 intensity | `221,184000` | `265,420800` | dedicated GigE; optional intensity |
| Frozen Bayer10 + blaze depth+confidence | `776,601600` | `931,921920` | USB3 + dedicated GigE toplamı |

Payload pixel data'dır; UVC/GigE framing, retries, timestamps ve host copy
yoktur. Gemini için ikinci dedicated USB root; blaze için dedicated NIC,
deterministic camera timestamp ve sustained 15 Hz Stage-B receipt olmadan H6
PASS verilmez. Depth output camera-side olduğundan bu hesapların hiçbirinde
host stereo/GPU disparity yoktur; downstream feature/model compute ise ayrıca
ölçülmelidir.

### 17.6 Dated public cost ve completeness

Fiyatlar **2026-08-14 checked**, tax/shipping/tariff hariç public USD
snapshot'larıdır. Frozen RGB'nin tarihsel `709+136=845 USD` bedeli incremental
depth subtotal'larına dahil değildir.

| Stack | Kaynaklı parçalar | Known partial incremental subtotal | Eksik ve karar etkisi |
|---|---|---:|---|
| Gemini 335L | body `359`; Orbbec Dev Star sync hub `35`; 1 m 8-pin sync cable `7`; Edmund `#37-014` window `153`; body paketinde 1 m USB cable | **`554 USD`**; frozen RGB ile mixed-date known partial `1.399 USD` | dev hub/cable frozen Basler'a doğrudan level-shift çözümü değildir; exact sealed cross-vendor trigger harness, mount, second-root controller, ingress restoration ve landed quote yok → H8 FAIL |
| blaze-101 trigger path | body `1.799`; 10 m M12/RJ45 data `72,26`; 2 m M12/open power-I/O `25,28`; ace/ace2 bracket `48,69`; Edmund window `153` | **`2.098,23 USD`**; frozen RGB ile mixed-date known partial `2.943,23 USD` | exact compliant 24 V LPS, trigger conditioning/connector, dedicated NIC, hood mount, region AC, installed window ve landed quote yok → H8 FAIL |

Orbbec'in
[`manufacturer store`](https://store.orbbec.com/products/gemini-335l)
`359 USD`, in-stock ve camera/USB cable/tripod setini; store ayrıca
[`Dev Star`](https://store.orbbec.com/products/sync-hub-dev-star) için `35 USD`
ve [`8-pin cable`](https://store.orbbec.com/products/sync-cable-8-pin-1m-for-astra-2-and-gemini-2-330-series)
için `7 USD` verir. Bunlar satın alma veya Türkiye landed availability
kanıtı değildir.

Graftek exact `107796` blaze body'yi `1.799 USD`, request-lead-time; exact
accessories'i yukarıdaki değerlerle listeler. Basler'ın resmi requirement'ı
power supply, GigE cable, bracket ve NIC içerir. Trigger kullanılırken
power-I/O open cable ile uyumlu exact supply/conditioning seçilmediği için
non-trigger adapter+brick fiyatı subtotal'a yanlış güvenle eklenmemiştir.

### 17.7 H1–H10 hard screen ve disposition

| Gate | Gemini 335L `G40055-170` primary | blaze-101 `107796` backup |
|---|---|---|
| H1 identity | `FAIL_COMPLETE_IDENTITY`: model/filter/shutter/interface/price exact; IR/RGB sensor ve fixed lens part identity, sealed sync harness yok | `FAIL_REVISION_TRIGGER_POWER_IDENTITY`: body/sensor/lens/interface exact; hardware revision, compliant trigger-power chain ve exact installed window path açık |
| H2 timing | `PASS_CATALOG_CONFIG / PHYSICAL_OPEN`: global shutters, manual 170 µs ve fixed30/external15 mümkün; default 3 ms fail, pulse semantics/skew ve 170 µs depth quality ölçülmedi | `FAIL_SOURCE_BOUNDED_FULL_FRAME_TIMING`: hw trigger ve per-subframe exposure var; multi-frequency/subframe full depth event, exact revision ve motion artifact bound'u yok |
| H3 native geometry/utility | `CONDITIONAL`: 10/20 mm `10,85–12,31 / 21,69–24,62 px`; exact near p95 ve valid fraction yok | `CONDITIONAL`: `8,19–9,30 / 16,39–18,59 px`; ±5 mm typical/25-frame center result p95 değil; minimum valid fraction yok |
| H4 optical/window | `FAIL_INSTALLED_OPTICS`: factory path ve range uygun; external 94° cone/window/ghost/vignette/Class-1 ve sync-port ingress açık | `FAIL_INSTALLED_WINDOW`: integrated lens/range/FOV uygun; external 940 nm window/emitter cone/focus/Class-1/accuracy açık |
| H5 spectral definition | `PASS_CATALOG`: 850±6 nm VCSEL, visible+NIR-pass depth, IR-cut RGB; installed window open | `PASS_CATALOG`: 940 nm VCSEL/factory bandpass and confidence path; installed window open |
| H6 interface | `FAIL_INSTALLED_TRANSPORT`: payload ve included USB kaynaklı; second root, sealed trigger adapter, timestamps ve sustained run yok | `FAIL_INSTALLED_TRANSPORT`: payload/GigE/M12 kaynaklı; complete power-I/O/NIC, timestamps ve sustained run yok |
| H7 registration/no hidden GPU | `FAIL_CROSS_CAMERA_REGISTRATION`: camera-side depth/D2C PASS, hidden GPU yok; frozen RGB common mask ve cross-vendor sync yok, source family bound `≤5 ms` | `PASS_CATALOG_PATH / PHYSICAL_OPEN`: camera-side depth, official ace→blaze trigger path ve bracket var; common mask, FrameDuration/skew/latency tracking ve installed calibration yok |
| H8 complete cost | `FAIL`: `554 USD` partial; sync/ingress/mount/root/landed cost eksik | `FAIL`: `2.098,23 USD` partial; supply/conditioning/NIC/mount/landed cost eksik |
| H9 task value | `PASS_DIRECTIONAL_T2 / PROMOTION_TRIGGER_CLOSED`: RGB-D crop/weed task signal'i var; exact camera/action transferi ve repo structure-failure bin'i yok | aynı; exact blaze task evidence yok |
| H10 safety | `PASS_ARCHITECTURE_ONLY`: frozen RGB, 82 px service class, abstain ve A–E korunur; own RGB replacement olamaz | aynı; Class-1 catalog state external window sonrası yeniden doğrulanır, chemical fire yok |

İki adayın nihai depth disposition'ı aynıdır:
**`CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD`**. Bu etiket
`BOUNDED_CHALLENGER_AB_ELIGIBLE` değildir. Orbbec düşük known partial cost
ve integrated D2C nedeniyle yalnız **discovery primary**, blaze ölçülebilir
confidence semantics/industrial trigger path nedeniyle **backup** tutulur;
hiçbiri price-performance winner değildir.

### 17.8 Tier-2 görev kanıtı ve trigger sonucu

Ni et al.'ın 5 Kasım 2021 tarihli
[`Multi-Modal Deep Learning for Weeds Detection in Wheat Field Based on RGB-D Images`](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2021.732968/full)
(DOI `10.3389/fpls.2021.732968`) çalışması applicable fakat directional
Tier-2 kanıttır:

- Intel RealSense D415 ile `1280×720` RGB/depth, canopy üstünden `70 cm`, açık
  ve rüzgarsız doğal koşullar; `1.228` paired image, `1.105/123` train/test;
- RGB-only VGG16 broadleaf/grass mAP `38,5/24,7`, IoG `77,6`; doğrudan RGB-D
  fusion IoG `72,6` ile daha kötü, PHA-aware correlated fusion `81,4`, ensemble
  `89,3` verir. Yani depth değeri network/fusion tasarımına bağlıdır;
- yazarlar lighting, IR reflectance ve occlusion nedeniyle depth void'lerini
  ayrıca bildirir ve hole-filling uygular.

Bu çalışma exact Orbbec/blaze değildir; `520–590 mm`, hood/strobe, single-frame
p95, valid-depth threshold, instance mask, track continuity, 20 mm action veya
crop-hit safety ölçmez. Üstelik bbox detection ve aynı-dataset split kullanır.
H9'da depth hypothesis'ini meşru kılar ama satın alma/promotion veya fiziksel
A/B trigger'ı açmaz. Repository'de structure/height eksikliğine atfedilmiş bir
baseline failure bin'i de yoktur.

### 17.9 Eksik utility threshold ve frozen stop kuralı

Repository/owner authority şu iki değeri tanımlamamıştır:

```text
maximum_useful_depth_error_p95_mm = UNKNOWN
minimum_valid_depth_fraction = UNKNOWN
```

Bu boşluk sıfırla, Basler'ın typical `±5 mm` değeriyle veya Orbbec'in 2 m
yüzdesiyle doldurulamaz. Basler'da ölçülebilir invalid sentinel olması threshold
yerine geçmez; Orbbec'te near-range sayı bulunmaması da “yeterli” sayılmaz.

Depth satırını yeniden açmanın en küçük exact koşulu:

1. downstream feature owner iki threshold'u height/structure geometry'sine
   bağlayarak dondurur;
2. retained aday, 520/555/590 mm ve intended hood/ambient/leaf/soil zarfında
   single-frame p95 error ile valid fraction'ı calibrated common RGB safe
   swath'ta ölçer;
3. 15 Hz trigger/timestamp, registration residual, latency/tracking ve sustained
   payload Stage B'de geçer; window/emitter/ingress Stage C'de kapanır;
4. yalnız bundan sonra aynı split/seed ve safety metric'leriyle RGB-only versus
   RGB+depth target-rig A/B istenir.

Bu koşul gelmeden daha fazla depth SKU taranmaz ve depth price-performance
sıralaması yapılmaz. Frozen RGB baseline değişmez.

## 18. Pass 6 ephemeral validation receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan independent FOV/GSD/target,
common-swath sample, exposure smear, payload/headroom, body-count ve dated
partial-cost hesapları yeniden çalıştırıldı. Source/disposition/plan bağlarıyla
birlikte `91` assertion geçti; exact stdout:

```text
gemini_depth_wd520_fov=1040.000000000000x662.553071239793
gemini_depth_wd590_fov=1180.000000000000x751.742907752842
blaze_depth_wd520_fov=688.360983643519x496.054554006087
blaze_depth_wd590_fov=781.024962210916x562.831128583829
frozen_plus_gemini_depth_headroom=1049.886720000000
frozen_plus_blaze_depth_conf_headroom=931.921920000000
gemini_known_partial_usd=554.00
blaze_known_partial_usd=2098.23
PASS: 91 depth geometry, blur, payload, cost, provenance, decision and plan assertions
```

Bu receipt depth accuracy, valid fraction, ambient survival, full multi-subframe
timing, registration, ingress, window/emitter safety, model utility veya
fiziksel A–E ölçmez.

## 19. Terminal survey kararı

```text
overall_decision = RETAIN_RGB_BASELINE
proof_baseline = 1× Basler a2A2464-77ucPRO + C23-0824-5M-P
bounded_challenger_ab_eligible = []
replan_required = false
```

`INFERENCE`: frozen RGB, current kaynak ve hesaplarla tek-gövde action
kontrolü olarak korunur. Bunun nedeni challenger'ların daha az bilgi
taşıması değil, hiçbirinin aynı anda (a) decisive H1–H10 kapılarını, (b)
failure-attributed bir promotion trigger'ını ve (c) complete-stack maliyet
sınırını kapatmamasıdır. JAI exact-camera Tier-2 task sinyali açıktır;
H1/H6/H7/H8 ve fiziksel A–E açık olduğu için A/B-eligible değildir.

Bu fiyat/performans sonucu arbitrary score veya eksik fiyatlardan USD/mm
sıralaması değildir. Frozen RGB, source-locked ve golden-hesabı geçen mevcut
proof control olduğu için **fail-closed ordinal winner** olarak tutulur;
hiçbir challenger absolute veya complete-cost price-performance winner ilan
edilmez. Baseline'ın `845 USD` kamera+lens değeri de tarihsel/partial'dır ve
satın alma quote'u değildir.

`REPLAN_REQUIRED` da üretilmez: beş pinned local authority hash'i ve baseline
golden hesapları current dosyalarla aynıdır; minimum servis boyutu, swath,
hız, WD veya safety contract'unda source drift bulunmamıştır. Fiziksel A–E
henüz çalışmadığı için bu karar `READY` veya field/product/chemical GO
değildir.

## 20. Cross-modality H1–H10 terminal matrisi

Kodlar: `P` source/calc desk PASS; `P/O` desk path var, installed/physical
receipt açık; `C` trigger veya utility threshold eksik; `F` decisive current
FAIL; `N/A` uygulanmaz. Bu matris Section 10, 11, 13, 15 ve 17'deki exact
candidate tablolarının lossless karar projeksiyonudur; kısa kod ayrıntılı
gerekçenin yerine geçmez.

| Exact mimari / aday | H1 | H2 | H3 | H4 | H5 | H6 | H7 | H8 | H9 | H10 | Terminal disposition |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| Frozen RGB `109779` + C23 | P | P/O | P | P/O | P | P/O | N/A | P/O | P/O | P/O | `RETAIN_RGB_BASELINE` |
| Visible mono Basler `109778` | P | P/O | P | P/O | P | P/O | N/A | F | C | C | `CONDITIONAL_TRIGGER_CLOSED` |
| Visible mono FLIR `BFS-U3-51S5M-C` | P | P/O | P | P/O | P | P/O | N/A | F | C | C | `SCREENED_OUT_PARETO_DOMINATED` |
| NIR-only, retained NIR bodies | F | P/O | P | P/O | P | P/O | N/A | F | F | F | `SCREENED_OUT_AS_ACTION_REPLACEMENT` |
| RGB+NIR Basler `109778` primary | F | P/O | P | P/O | P | P/O | F | F | C | P/O | `CONDITIONAL_H7_H8_TRIGGER_CLOSED` |
| RGB+NIR Basler `106555` backup | F | P/O | P | P/O | P | P/O | F | F | C | P/O | `SCREENED_OUT_PARETO_DOMINATED` |
| JAI `FS-3200T-10GE-NNC` | F | P/O | P | P/O | P/O | F | F | F | P | P/O | `CONDITIONAL_CHALLENGER_TASK_TRIGGER_OPEN_H6_H8_PHYSICAL_CLOSED` |
| XIMEA `MQ022HG-IM-SM5X5-7NIR2` | F | P/O | F | F | P/O | F | F | F | F | F | `SCREENED_OUT_H3_H4_H7_H8_H9` |
| Boson+ `22640AS50-6IARX` + RGB | F | F | P | P/O | P | F | F | F | C | P/O | `SCREENED_OUT_H2_H7_H8` |
| A6751 `29439-251` + 2-bay RGB | F | P/O | P | F | P | F | F | F | C | P/O | `SCREENED_OUT_H4_H7_H8` |
| Gemini 335L `G40055-170` + RGB | F | P/O | C | F | P | F | F | F | C | P/O | `CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD` |
| blaze-101 `107796` + RGB | F | F | C | F | P | F | P/O | F | C | P/O | `CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD` |

Bu satırların hiçbirinde `BOUNDED_CHALLENGER_AB_ELIGIBLE` yoktur.
`P/O`, fiziksel PASS değil, yalnız kaynakla buildable bir bench yolunun
mevcut olduğunu söyler. H9'daki JAI `P` de task signal'idir; crop-hit veya
chemical-action safety kanıtı değildir.

## 21. Geometri, camera-count, payload ve cost decision matrisi

Payload, `15 Hz`te source-bound minimum stream setinin raw pixel hesabına
`%20` headroom ekler. Cost alanı challenger lehine en düşük tarihli public
değeri kullanır; `complete=false` ise oran ve winner üretilmez.

| Mimari | Action / auxiliary 20 mm native destek | Safe-swath ve Mode | Bay / toplam body | Minimum stream +%20 (Mbit/s) | Dated known cost boundary | Complete? | Source bundle |
|---|---|---|---:|---:|---|---:|---|
| Frozen RGB | action `84,628–86,414 px` | `444,375–453,750 mm`, Mode A | `1 / 1` | `754,974720` Bayer10 | `845 USD` historical body+lens | false | `SB-RGB` |
| Visible mono Basler / FLIR | action baseline ile aynı | `444,375–453,750 mm`, Mode A | `1 / 1` | `754,974720` Mono10 | `1.123 / 1.738 USD` partial | false | `SB-MONO` |
| NIR-only primary / backup | action geometry `85,333 px`, fakat H10 FAIL | nominal `450 mm`, Mode B | `1 / 1` | `754,974720` Mono10 | `2.243 USD + 967 EUR` / `3.365 USD + 3.950 EUR`, partial | false | `SB-NIR` |
| Frozen RGB + NIR primary / backup | RGB action `85,333`; NIR `85,333 px` | analytic common `450 mm`, Mode B | `1 aux / 2` | `1.509,949440` | historical RGB `845 USD` + yukarıdaki mixed-currency partial | false | `SB-RGB` + `SB-NIR` |
| JAI snapshot | carrier/NIR `85,333`; R/B lattice `42,667 px` | `450 mm`, Mode A prescreen | `1 / 1` | `1.698,693120` 3×10-bit | `6.787 USD` partial | false | `SB-JAI` |
| RGB + 2× XIMEA | RGB action korunur; per-band `20,243–23,054 sample` | iki spectral bay ile aggregate swath; matched service FAIL | `2 aux / 3` | `1.557,135360` | historical RGB `845 USD + 1.576 USD + 2×UNKNOWN body` | false | `SB-RGB` + `SB-XIMEA` |
| RGB + Boson+ | RGB action korunur; thermal `26,446–27,004 px` | common-safe analytic `444,375–453,750 mm`, Mode A | `1 aux / 2` | `849,346560` | historical RGB `845 USD + 5.774–6.899 USD + window_quote` | false | `SB-RGB` + `SB-BOSON` |
| RGB + 2× A6751 | RGB action korunur; thermal `39,558–45,063 px` | tek lens FOV fail; 2-bay matched coverage | `2 aux / 3` | `920,125440` | historical RGB `845 USD + 2×(camera+lens+window quote)` | false | `SB-RGB` + `SB-A6751` |
| RGB + Gemini depth | RGB action korunur; depth `21,695–24,615 px` | RGB safe swath üstü analytic overlay, Mode B auxiliary | `1 aux / 2` | `1.049,886720` depth-only | mixed-date `1.399 USD` partial | false | `SB-RGB` + `SB-GEMINI` |
| RGB + blaze depth/confidence | RGB action korunur; depth `16,389–18,595 px` | RGB safe swath üstü analytic overlay, Mode B auxiliary | `1 aux / 2` | `931,921920` | mixed-date `2.943,23 USD` partial | false | `SB-RGB` + `SB-BLAZE` |

Exact source-bundle expansion'ı; her token Section 25'te tek bir registered
source key'e çözülür:

- `SB-RGB` = `L-V2-CONFIG`, `L-V2-REPORT`, `L-IMAGING-DECISION`,
  `L-RIG-RUNBOOK`, `L-V2-RESULT`, `S-BASLER-CAMERA`, `S-BASLER-LENS`,
  `S-BASLER-TRIGGER`;
- `SB-MONO` = `S-BASLER-MONO`, `S-FLIR-MONO`, `S-FLIR-EMVA`,
  `S-MIDOPT-SP700`, `S-EDMUND-WINDOW`, `P-BASLER-MONO`, `P-FLIR-MONO`,
  `P-SP700`, `T2-MONO-BOUNDED`;
- `SB-NIR` = `S-BASLER-MONO`, `S-BASLER-ACA-NIR`, `S-KOWA-LM8`,
  `S-KOWA-LM12`, `S-MIDOPT-BP850`, `S-EDMUND-WINDOW`, `S-SVL-JWL`,
  `P-BASLER-MONO`, `P-ACA-NIR`, `P-BP850`, `T2-WEEDMAP`,
  `T2-CABBAGE-NIR`;
- `SB-JAI` = `S-JAI-FS3200`, `S-JAI-MANUAL`, `S-JAI-LENS`, `S-EFFI-HSI`,
  `S-EDMUND-WINDOW`, `P-JAI-FS`, `P-JAI-LENS`, `T2-FISCHER-MSI`;
- `SB-XIMEA` = `S-XIMEA-NIR-MOSAIC`, `S-XIMEA-MANUAL`, `S-XIMEA-LENS`,
  `S-EDMUND-WINDOW`, `T2-GAO-MOSAIC`;
- `SB-BOSON` = `S-FLIR-BOSONPLUS-PAGE`, `S-FLIR-BOSONPLUS-DATASHEET`,
  `S-RHP-BOSON-SYNC`, `S-CRYSTRAN-GE`, `P-BOSONPLUS`,
  `P-RHP-BOSON-SYNC`, `T2-ZAMANI-THERMAL`, `T2-ZAMANI-DATASET`,
  `T2-RANARIO-THERMAL`;
- `SB-A6751` = `S-FLIR-A6751`, `S-FLIR-A6751-LENS`, `S-CRYSTRAN-GE`,
  `P-A6751`, `T2-ZAMANI-THERMAL`, `T2-ZAMANI-DATASET`,
  `T2-RANARIO-THERMAL`;
- `SB-GEMINI` = `S-ORBBEC-G335L`, `S-ORBBEC-G330-V16`, `S-ORBBEC-SYNC`,
  `P-ORBBEC-G335L`, `P-ORBBEC-SYNC`, `S-EDMUND-WINDOW`, `T2-NI-RGBD`,
  `S-STEREOLABS-HOST`;
- `SB-BLAZE` = `S-BASLER-BLAZE`, `S-BASLER-BLAZE-QUALITY`,
  `S-BASLER-BLAZE-TIMING`, `P-BASLER-BLAZE`, `S-EDMUND-WINDOW`,
  `T2-NI-RGBD`.

`CALC/INFERENCE`: body count avantajını gizleyen tek-camera fiyatı veya
reconstructed raster kullanılmamıştır. Additive satır RGB'yi cost ve
body count'tan çıkarmaz. Analytic common FOV calibrated common-valid-FOV
değildir; table'daki her additive stack için registration/occlusion receipt'i
açıktır.

## 22. Failure-attribution ve re-plan trigger ledger'i

| Trigger ID | Açılma koşulu | Current state | Karar sahibi rolü | En küçük sonraki adım / etki |
|---|---|---|---|---|
| `TR-BL-DRIFT` | beş pinned local hash veya golden baseline değeri değişir | `CLOSED` | V2 contract owner | challenger araştırmasını durdur; `REPLAN_REQUIRED` |
| `TR-SUPPLY` | exact PRO/C23 için dated EOL veya temin edilemez landed quote | `CLOSED` | procurement + imaging owner | aynı safety/geometri sınırında replacement re-plan; mono'yu otomatik seçme |
| `TR-GEOMETRY` | `<20 mm`, `>1 m/s`, `>444,375 mm` safe swath veya `520–590 mm` dışı WD requirement'ı | `CLOSED` | product/safety contract owner | tüm lens, bay, blur ve compute zarfını yeniden planla |
| `TR-MONO-SNR` | passing hood/light ile 170 µs'te sensor-intrinsic Stage-D SNR `<20 dB` veya aynı SNR için exposure/light limiti aşılır | `CLOSED_UNMEASURED` | imaging validation owner | Basler RGB vs exact visible-mono paired photon/color-loss A/B tasarla |
| `TR-SPECTRAL` | same-rig failure bin'i spectral separability/glare/CNR eksikliğine causal bağlanır | `OPEN_T2_ONLY_FOR_JAI`; physical attribution closed | perception + optics owners | önce JAI H1/H6/H7/H8'i kapat; sonra owner-onaylı paired A/B; RGB+NIR için 850 nm CNR ölç |
| `TR-THERMAL` | passing visible hood/light sonrası visible-collapse ve aynı anda yeterli plant/soil thermal contrast | `CLOSED` | perception + agronomy owners | global/snapshot timing ve complete lens/window/cost taşıyan yeni exact stack ara; mevcut iki SKU'yu promote etme |
| `TR-DEPTH` | feature owner p95/valid-fraction threshold'larını dondurur ve structure/height eksikliği causal failure bin'idir | `BLOCKED_MISSING_THRESHOLD` | depth-feature + perception owners | 520/555/590 mm intended-ambient common-FOV error/validity bench; sonra RGB-only/RGB+depth A/B |
| `TR-COMPUTE` | retained additive stack için 15 Hz latency/throughput budget ve tracker compensation tanımlanır | `GATE_NOT_PROMOTION_TRIGGER` | compute/integration owner | dedicated roots/NIC, timestamps, sustained payload ve inference latency receipt'i |
| `TR-MODEL-DATA` | model, split, annotation veya dataset failure'ı | `NOT_A_SENSOR_TRIGGER` | perception owner | önce data/model nedenini düzelt ve aynı sensorla tekrar ölç |
| `TR-HOOD-LIGHT` | hood, window, strobe, polarizer veya uniformity failure'ı | `NOT_A_CAMERA_TRIGGER` | enclosure/illumination owner | optical/enclosure nedenini kapat; sensor'a ancak residual causal failure kalırsa dön |

Hiçbir trigger 20 mm service class'ı, `64 px` abstain halkasını,
crop-safety metriklerini veya chemical authority'yi gevşetmez. `OPEN_T2_ONLY`
bir hardware A/B komutu değildir.

## 23. Pareto, source-tier ve stopping audit'i

| Satır | Fail-closed Pareto sonucu | Search durdurma gerekçesi |
|---|---|---|
| Frozen RGB | `NON_DOMINATED_CONTROL_RETAINED` | source/golden drift yok; yeni SKU ekleme |
| Visible mono Basler | `NON_DOMINATED_BUT_TRIGGER_CLOSED` | causal low-photon failure yok |
| Visible mono FLIR | `DOMINATED_BACKUP` | daha pahalı; kaynaklı task/geometry üstünlüğü yok |
| NIR-only | `SCREENED_OUT_H10` | color safety kanalını kaldırır |
| RGB+NIR Basler primary | `CONDITIONAL_TRIGGER_CLOSED_H7_H8` | CNR/failure attribution, registration ve complete cost yok |
| RGB+NIR Basler backup | `DOMINATED_BACKUP` | aynı örnek/swath, daha pahalı body/lens, task üstünlüğü yok |
| JAI snapshot | `NON_DOMINATED_TASK_SIGNAL_HARD_GATES_OPEN` | H1/H6/H7/H8 ve fiziksel A–E kapanana kadar yeni multispectral SKU yok |
| XIMEA mosaic | `SCREENED_OUT_H3_H4_H7_H8_H9` | raw per-band sampling ve exact lens/bay sonucu decisive fail |
| Boson+ / A6751 | `SCREENED_OUT` | sırasıyla H2 ve H4 decisive fail; current modality trigger kapalı |
| Gemini / blaze | `CONDITIONAL_MISSING_UTILITY_THRESHOLD` | owner threshold gelmeden yeni depth SKU tarama |
| thermal-only / host stereo / pushbroom / filter-wheel / rolling shutter | `TERMINAL_REJECT` | safety, hidden GPU, sequential-motion veya timing contract ihlali |

Source register local authority/calculation, Tier-1 manufacturer, Tier-2
primary-paper/dataset ve Tier-3 vendor/commerce satırlarını ayrı tutar.
Teknik kabiliyet vendor fiyat sayfasından; fiyat/performance ise paper'dan
türetilmez. Mutable/undated kaynaklar açık etiketlidir ve her satır
`checked=2026-08-14` taşır. Terminal validation blank tarih, duplicate key,
unsupported winner, eligibility contradiction ve safety flag açılmasını
fail eder.

Bu audit sonunda:

```text
price_performance_challenger_winner = NONE
bounded_challenger_ab_eligible = []
terminal_reject_classes = [thermal_only, host_stereo, pushbroom,
                           sequential_filter_wheel, rolling_shutter]
```

## 24. Bilinen belirsizlikler ve sınırlar

- Fiziksel A–E receipt yoktur; katalog hesabı gerçek MTF/SNR/blur/sync PASS
  değildir.
- Basler/C23 kamu fiyatları 2026-08-11 tarihli tarihsel kayıttır; satın alma
  öncesi landed quote ve lead time yeniden alınmalıdır.
- Yeni challenger fiyatları checked-on snapshot'tır; tax, shipping, tariff,
  local stock ve EUR/USD dönüşümü içermez. Mixed-currency NIR satırından total
  USD veya price-performance sonucu çıkarılmamıştır.
- Basler `109778` commerce sayfası `ready for dispatch`, Version 130 docs footer
  ise “not in series production yet” metnini gösterir; Graftek ayrıca request
  lead time ister. Bu çelişki supply PASS değil, `quote_required` üretir.
- Exact LED setpoint, scene reflectance, photon throughput ve gerçek SNR
  ölçülmemiştir.
- JWL225-MD'nin 850 nm option'ı kaynaklıdır; terminal configuration suffix,
  selected lens/polarizer, radiant intensity ve 480 mm uniformity kaynaklı
  değildir. Exact order identity bu nedenle açık kalır.
- OG05C/CMV4000 için sayısal 850 nm QE, iki Kowa lens için 850 nm throughput
  yüzdesi ve installed stack loss aynı integralde bulunmadığı için mono/NIR
  signal-ratio veya SNR gain hesaplanmamıştır.
- SP700/BP850 C-mount insertion ve #37-014 window, katalogda uyumludur; filter
  back-focus etkisi, tilted-window ghost/vignetting ve installed MTF fiziksel
  Stage C olmadan bilinmez.
- C23 yalnız 400–700 nm için kaynaklıdır; başka spectral yola taşınamaz.
- İkinci kamera veya additive modality için mevcut RTX 3090 kapasitesi
  kanıtlanmamıştır.
- RGB+NIR için shared trigger skew, timestamp semantics, common-valid-FOV mask,
  registration residual ve second-root sustained transport ölçülmemiştir.
- Bounded mono search exact paired visible-mono sensor A/B bulmadı. NIR
  paper'ları yönseldir; biri aerial semantic segmentation, diğeri random-split
  bounding-box detection'dır.
- JAI exact-camera Tier-2 sonucu paired ve göreve yakındır; fakat tek
  `70/15/15` split, küçük-nesne filtresi, bbox AP, `1,8 m` ve `5 fps` koşulları
  target-rig mask/track/action veya safety transferi sağlamaz.
- JAI body/lens/window kimliği kapanmıştır; exact HSI light suffix/adet,
  10GigE NIC/cable/power/trigger, calibration hedefi/file'ı, mount/hood ve
  landed cost açık kalır.
- XIMEA exact sayfasındaki `Active`/`Product is discontinued` çelişkisi supply
  PASS'i engeller. Vertical band lattice için yaklaşık `218` vendor değeri
  yerine raw `floor(1088/5)=217` kullanılmıştır.
- Boson+ public fiyatı exact `22640AS50` family aralığıdır; dropdown
  receipt'i `6IARX` suffix'ini tek bir fiyata bağlamaz. Bu maliyet eksiği
  H2 timing hard fail'ini değiştirmez.
- Crystran exact germanium window 2026-08-14'te live `POA`/out of stock,
  structured metadata'da `1.375 GBP`'dir; usable fiyat `quote_required` kalır.
  Installed transmission/emission, tilt, vignetting, refocus ve calibration
  etkileri fiziksel Stage C olmadan bilinmez.
- A6751'in exact 17 mm factory lensi iki thermal bay gerektirir; camera/lens
  quote-only, cooler vibration ve iki-camera registration/sync fiziksel olarak
  kanıtlanmamıştır.
- RGB+thermal crop/weed papers are directional task evidence only. Passing
  hood/light sonrası visible-collapse ve eşzamanlı plant/soil thermal contrast
  receipt'i olmadığından thermal modality trigger'ı kapalıdır.
- Gemini'nin `2 m` high-reflectivity/central-ROI typical tablosu ve kategorik
  outdoor/full-sunshine beyanı, `520–590 mm` crop/soil single-frame p95 veya
  valid-depth fraction değildir. Exact confidence/invalid semantics'i de
  `G40055-170`a kaynakla bağlanamamıştır.
- blaze'in `±5 mm` typical accuracy'si no-ambient beyaz hedefte merkez `40×40`
  ROI ve 25-frame average'dır; full-FOV p95 değildir. Ambient sonucu da `6 m`,
  `250 µs`, `90%` hedefe özgüdür. Current order hardware revision'ı ve çoklu
  modulation-subframe full `FrameDuration`'ı kaynakla kapanmamıştır.
- Her iki retained depth stack'i frozen RGB ile iki gövdelidir. Analytic FOV
  kesişimi, calibrated common-valid-FOV mask, occlusion, reprojection residual,
  cross-camera skew veya latency compensation kanıtı değildir.
- Orbbec sync port kullanımı documented IP65 koşulunu bozar; blaze dış
  pencere/emitter yolu da installed optical, ingress ve Class-1 receipt ister.
  İki partial subtotal landed veya installation-complete fiyat değildir.
- Depth feature için `maximum_useful_depth_error_p95_mm` ve
  `minimum_valid_depth_fraction` henüz owner tarafından dondurulmamıştır.
- Model/data/hood/light başarısızlığı tek başına sensor-upgrade trigger'ı
  değildir; failure attribution gerekir.

## 25. Source register

| Source key | Tier | Publisher / title | Version / release | Checked | Exact scope | Desteklenen claim | URL / arşiv notu |
|---|---|---|---|---|---|---|---|
| `L-V2-CONFIG` | local authority | Repository / controlled capture V2 config | schema 2; evidence 2026-08-11 | 2026-08-14 | frozen proof contract | baseline fields, safety, prices | [local file](../../configs/deploy/spot_spray_capture_optimization_v2.yaml), SHA above |
| `L-V2-REPORT` | local authority | Repository / Controlled Capture Optimization V2 | evidence 2026-08-11 | 2026-08-14 | frozen human-readable derivation | baseline geometry, capture and validation boundary | [local file](../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md), SHA above |
| `L-IMAGING-DECISION` | local authority | Repository / Spot-Spray Product Imaging Decision V1 | evidence 2026-08-12 | 2026-08-14 | proof architecture authority | camera/lens control and product-decision boundary | [local file](../SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md), SHA above |
| `L-RIG-RUNBOOK` | local authority | Repository / Spot-Spray Rig Acceptance Runbook V1 | repository release | 2026-08-14 | physical acceptance authority | A–E stages and no-ready boundary | [local file](../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md), SHA above |
| `L-V2-RESULT` | local calculation | Repository / controlled capture V2 result | schema 2; evidence 2026-08-11 | 2026-08-14 | golden calculations | geometry, payload, checks | [local file](../results/controlled_capture_optimization_v2.json), SHA above |
| `S-BASLER-CAMERA` | Tier 1 | Basler / a2A2464-77ucPRO | Version 130; 2026-07-14 | 2026-08-14 | exact color PRO model | `C-BASLER-1/2` | [manufacturer documentation](https://docs.baslerweb.com/a2a2464-77ucpro); mutable web, exact version/date recorded |
| `S-BASLER-LENS` | Tier 1 | Basler / C23-0824-5M-P | Version 130; 2026-07-14 | 2026-08-14 | exact lens/order | `C-LENS-1/2` | [manufacturer documentation](https://docs.baslerweb.com/c23-0824-5m-p); mutable web, exact version/date recorded |
| `S-BASLER-TRIGGER` | Tier 1 | Basler / Triggered Image Acquisition | Version 130; 2026-07-14 | 2026-08-14 | trigger semantics | `C-TRIGGER-1` | [manufacturer documentation](https://docs.baslerweb.com/triggered-image-acquisition); camera-specific capability cross-checked above |
| `S-BASLER-MONO` | Tier 1 | Basler / a2A2464-77umPRO | Version 130; 2026-07-14 | 2026-08-14 | exact order 109778 mono body | sensor, spectrum, geometry, shutter, trigger, USB/power, 525 nm EMVA fields | [manufacturer documentation](https://docs.baslerweb.com/a2a2464-77umpro) and [product identity/EMVA](https://www.baslerweb.com/en/shop/a2a2464-77umpro/) |
| `S-FLIR-MONO` | Tier 1 | Teledyne FLIR / BFS-U3-51S5 | firmware 1801.0.1.0; doc family 2022-11-18 | 2026-08-14 | exact M-C model | sensor, raster, shutter, exposure, I/O, USB, formats | [manufacturer specification](https://softwareservices.flir.com/BFS-U3-51S5/latest/Model/spec.html) and [installation](https://softwareservices.flir.com/BFS-U3-51S5P/latest/40-Installation/InstallationCamera.htm) |
| `S-FLIR-EMVA` | Tier 1 | Teledyne FLIR / BFS-U3-51S5 EMVA 1288 | firmware 1801.0.1.0; 2022-11-18 | 2026-08-14 | exact mono model at 525 nm | QE, read noise, well, SNR, dynamic range and test conditions | [manufacturer EMVA receipt](https://softwareservices.flir.com/BFS-U3-51S5/latest/EMVA/EMVA.html) |
| `S-MIDOPT-SP700` | Tier 1 | MidOpt / SP700-25.4 | manufacturer page undated | 2026-08-14 | exact C-mount VIS-pass/IR-block | 405–690 nm, cutoffs, transmission, mount | [manufacturer filter page](https://midopt.com/filters/sp700/) |
| `S-MIDOPT-BP850` | Tier 1 | MidOpt / BP850-25.4 | manufacturer page undated | 2026-08-14 | exact C-mount NIR filter | 820–910 nm, FWHM, transmission, 840/850 LED | [manufacturer filter page](https://midopt.com/filters/bp850/) |
| `S-KOWA-LM8` | Tier 1 tech / Tier 3 public price | Kowa / LM8JC10M, product 10703 | mutable product page | 2026-08-14 | 2/3-inch NIR primary lens | focal/image format/pixel/min focus/400–1000 nm; `967 EUR` | [manufacturer product page](https://www.kowa-lenses.com/LM8JC10M-2-3-8.5mm-10MP-C-Mount-Lens/10703) |
| `S-KOWA-LM12` | Tier 1 tech / Tier 3 public price | Kowa / LM12HC-VIS-SW, product 12199 | mutable product page | 2026-08-14 | 1-inch NIR backup lens | focal/image format/pixel/min focus/450–2000 nm; `3.950 EUR` | [manufacturer product page](https://kowa-lenses.com/LM12HC-VIS-SW-1-12mm-12MP-VIS-SWIR-lens/12199) |
| `S-EDMUND-WINDOW` | Tier 1 tech / Tier 3 public price | Edmund Optics / #37-014 | mutable product page | 2026-08-14 | exact protective window | dimensions, aperture, coating, reflectance; `153 USD` | [manufacturer product page](https://www.edmundoptics.com/p/50mm-dia-2mm-thick-vis-nir-coated-4-n-bk7-window/37339/) |
| `S-SVL-JWL` | Tier 1 tech / Tier 3 public price | Smart Vision Lights / JWL225-MD | mutable product page | 2026-08-14 | emitter family + 850 nm option | trigger, modes, IP65, WD; base `1.241 USD`; suffix unresolved | [manufacturer product page](https://smartvisionlights.com/products/jwl225-md/) |
| `S-BASLER-ACA-NIR` | Tier 1 | Basler / acA2040-90umNIR | Version 130; 2026-07-14 | 2026-08-14 | exact order 106555 backup body | sensor/raster/pitch/spectrum/shutter/trigger/interface | [manufacturer documentation](https://docs.baslerweb.com/aca2040-90umnir) and [product identity](https://www.baslerweb.com/en/shop/aca2040-90umnir/) |
| `S-JAI-FS3200` | Tier 1 | JAI / FS-3200T-10GE-NNC | page undated | 2026-08-14 | exact three-CMOS prism body | exact streams, bands, raster, IMX252, pitch, global shutter, fps, 10GigE, trigger/PTP, size/power | [manufacturer product page](https://www.jai.com/products/fs-3200t-10ge-nnc/) |
| `S-JAI-MANUAL` | Tier 1 | JAI / FS-3200T-10GE-NNC User Manual | v1.0; 2020-01 | 2026-08-14 | exact camera manual | Bayer/Mono formats, three streams, hardware trigger sources, exposure floor, raster | [manufacturer manual, hosted mirror](https://cdn.graftek.com/system/files/16830/original/JAI_FS-3200T-10GE-NNC_Manual.pdf) |
| `S-JAI-LENS` | Tier 1 | JAI + Edmund Optics / JVS-C118-0824-C3 | pages undated | 2026-08-14 | exact prism-optimized lens | FS-3200T compatibility, 8 mm, C-mount, image circle, aperture, WD, VIS-NIR, distortion | [JAI compatibility table](https://news.jai.com/hubfs/Blogs-News%20files/Lenses-for-JAI%20cameras.pdf) and [manufacturer-commerce specification](https://www.edmundoptics.com/p/8mm-focal-length-prism-optimized-fixed-focal-length-lens/57133/) |
| `S-XIMEA-NIR-MOSAIC` | Tier 1 | XIMEA / MQ022HG-IM-SM5X5-7NIR2 | page undated; conflicting lifecycle labels | 2026-08-14 | exact 5×5 NIR mosaic body | carrier, sensor, global shutter, 24 bands/range, interface, trigger, fps, exposure, power/size, quote/lifecycle conflict | [manufacturer product page](https://www.ximea.com/products/hyperspectral-imaging/xispec-hyperspectral-miniature-cameras/imec-sm-range-600-1000-usb3-hyperspectral-camera) |
| `S-XIMEA-MANUAL` | Tier 1 | XIMEA / xiSpec Technical Manual | v2.00; ©2025 | 2026-08-14 | exact model and SM5x5 lattice | 24 centers, 5×5 mosaic, approximate spatial raster, serial calibration, angle/crosstalk, calibrated lens kits | [manufacturer manual](https://www.ximea.com/getattachment/9ca53218-192e-4701-bafa-3cf17375c82e/xiSpec_TechnicalManual-DWL_manual.pdf) |
| `S-XIMEA-LENS` | Tier 1 tech / Tier 3 public price | Edmund Optics / #67-714 | page undated | 2026-08-14 | exact retained 16 mm kit lens | focal, 2/3 inç, C-mount, 425–1000 nm, WD; `635 USD` | [manufacturer-commerce product page](https://www.edmundoptics.com/p/16mm-c-series-vis-nir-fixed-focal-length-lens/22382/) |
| `S-EFFI-HSI` | Tier 1 family only | Effilux / EFFI-FLEX-HSI | datasheet/page undated | 2026-08-14 | illumination family used in JAI paper | broad HSI family and configurable spectrum/optics; exact target-rig suffix/quantity unresolved | [manufacturer page](https://effilux.com/product/machine-vision/barlight/effi-flex-hsi/) and [datasheet](https://www.effilux.com/docs/datasheet/DATASHEET_EFFI-FLEX-HSI.pdf) |
| `S-FLIR-BOSONPLUS-PAGE` | Tier 1 | Teledyne FLIR / Boson+ `22640AS50-6IARX` | mutable product page, undated | 2026-08-14 | exact camera/lens option | production state, raster, pitch, NETD grade, radiometry, spectrum, interfaces, nominal rates | [manufacturer product page](https://oem.flir.com/products/boson-plus/?model=22640AS50-6IARX&segment=oem&vertical=lwir) |
| `S-FLIR-BOSONPLUS-DATASHEET` | Tier 1 | Teledyne FLIR / Boson+ Product Datasheet | doc `102-2013-45`, Release 114; official publication 2025-09-05 | 2026-08-14 | exact `22640 AS50` camera/lens family | row-at-a-time readout, EXT_SYNC, frame skip, FFC, time constant, latency, lens/focus/MTF/transmission/distortion/SWaP | [manufacturer datasheet](https://flir.netx.net/file/asset/55485/original/attachment/) |
| `S-RHP-BOSON-SYNC` | Tier 1 | Teledyne FLIR / RHP Boson Camera Link Sync Interface `RHP-BOS-CL-SY-IF` | mutable product page, undated | 2026-08-14 | exact compatible sync accessory | Camera Link Base, master/slave sync, voltage and control interface | [manufacturer accessory page](https://oem.flir.com/products/boson-camera-link-interface-board/?model=RHP-BOS-CL-SY-IF&segment=oem&vertical=lwir) |
| `S-FLIR-A6751` | Tier 1 | Teledyne FLIR / A6751 SLS P/N `29439-251` | Rev 90835; last modified 2023-03-08 | 2026-08-14 | exact cooled LWIR body | spectrum, raster/pitch/NETD, snapshot/integration/sync, radiometry, rate/interface and SWaP | [manufacturer support datasheet](https://support.flir.com/dsdownload/assets/29439-251-en-us.html) |
| `S-FLIR-A6751-LENS` | Tier 1 | Teledyne FLIR / `4215424` manual FPO lens | mutable product page, undated | 2026-08-14 | exact compatible 17 mm lens | focal length, f-number, spectrum, transmission, distortion and mass; conflicting `0,1 m–∞` focus / `3 m` distance fields retained | [manufacturer lens page](https://www.flir.com/products/17-mm-f2.5-lwir-fpo-manual-lens?segment=solutions&vertical=rd+science) |
| `S-CRYSTRAN-GE` | Tier 1 tech / Tier 3 commerce state | Crystran / `GEP50-3AR/DLC` | mutable product page, undated | 2026-08-14 | exact dedicated LWIR window | 50×3 mm germanium, 7–14 µm AR/DLC, live `POA`/out of stock; structured `1.375 GBP` conflict, hence quote-required | [manufacturer-commerce product page](https://www.crystran.com/product/ge-50mm-x-3mm-optically-polished-ar-dlc-7-14/) |
| `S-ORBBEC-G335L` | Tier 1 | Orbbec / Gemini 335L `G40055-170` | mutable product page | 2026-08-14 | exact integrated RGB-D body | active/passive stereo, ASIC, global shutters, raster/FOV, wavelength, range, interface, SWaP, IP65 boundary | [manufacturer product page](https://www.orbbec.com/products/stereo-vision-camera/gemini-335l/) |
| `S-ORBBEC-G330-V16` | Tier 1 | Orbbec / Gemini 330 Series Datasheet | V1.6; revision entry 2025-04-10 | 2026-08-14 | exact `G40055-170` family row | sensor paths, baseline, exposure, free trigger, timestamps, sync pulse ambiguity, performance test bounds and unavailable near-range table values | [official manufacturer PDF](https://www.orbbec.com/wp-content/uploads/2025/06/Gemini-330-series-Datasheet-V1.6.pdf) |
| `S-ORBBEC-SYNC` | Tier 1 | Orbbec / Set up Cameras for External Synchronization | updated 2025-12-16 | 2026-08-14 | Gemini 335L family integration path | hub/cable topology, fixed-rate/external-trigger setup and same-family timestamp example; frozen-Basler electrical compatibility not covered | [manufacturer integration documentation](https://doc.orbbec.com/documentation/Camera%20Accessories/Set%20up%20Cameras%20for%20External%20Synchronization) |
| `P-ORBBEC-G335L` | Tier 3 manufacturer commerce | Orbbec store / Gemini 335L | mutable listing | 2026-08-14 | exact body public-price boundary | `359 USD`, listed in stock, package contents; no landed availability | [manufacturer store](https://store.orbbec.com/products/gemini-335l) |
| `P-ORBBEC-SYNC` | Tier 3 manufacturer commerce | Orbbec store / Dev Star and 1 m 8-pin cable | mutable listings | 2026-08-14 | candidate-family sync accessory prices | `35 USD` hub and `7 USD` cable; no cross-vendor level shifting, sealed harness or compatibility proof | [Dev Star listing](https://store.orbbec.com/products/sync-hub-dev-star) and [cable listing](https://store.orbbec.com/products/sync-cable-8-pin-1m-for-astra-2-and-gemini-2-330-series) |
| `S-BASLER-BLAZE` | Tier 1 | Basler / blaze-101 order `107796` | Version 130; released 2026-07-14 | 2026-08-14 | exact on-device ToF body | IMX556, integrated optics/emitter, raster/FOV/range, GigE, trigger/PTP, SWaP, latency, factory accuracy and ambient test conditions | [manufacturer documentation](https://docs.baslerweb.com/blaze-101) |
| `S-BASLER-BLAZE-QUALITY` | Tier 1 | Basler / depth quality features | Version 130/131 current pages | 2026-08-14 | blaze quality semantics and bounded tests | accuracy/precision conditions, confidence range/threshold behavior, invalid sentinel and ambient robustness curve/test conditions | [accuracy](https://docs.baslerweb.com/accuracy-and-precision), [confidence](https://docs.baslerweb.com/confidence-threshold), [invalid value](https://docs.baslerweb.com/scan-3d-invalid-data-value), [ambient](https://docs.baslerweb.com/ambient-light-robustness) |
| `S-BASLER-BLAZE-TIMING` | Tier 1 | Basler / blaze acquisition and multi-camera timing | Version 130 current pages | 2026-08-14 | exact-family timing boundary | revision-dependent exposure floor, multi-subframe acquisition, Line0 trigger latency and official ace/ace2-to-blaze trigger path | [exposure](https://docs.baslerweb.com/exposure-time-%28blaze%29), [acquisition/I/O](https://docs.baslerweb.com/image-acquisition-and-io-control), [multi-camera path](https://docs.baslerweb.com/working-with-multiple-cameras) |
| `S-STEREOLABS-HOST` | Tier 1 | Stereolabs / ZED SDK and ROS 2 requirements | mutable current documentation | 2026-08-14 | architecture rejection boundary, not a retained SKU | NVIDIA/CUDA host requirement and GPU-selected depth computation | [SDK requirements](https://docs.stereolabs.com/docs/development/zed-sdk/specifications) and [ROS 2 node](https://docs.stereolabs.com/docs/integrations/ros-2/zed-stereo-node) |
| `T2-WEEDMAP` | Tier 2 primary paper | Sa et al. / WeedMap | submitted 2018-07-31; Remote Sensing 2018 | 2026-08-14 | aerial sugar-beet semantic segmentation | exact RGB, RGB+NIR, NIR-only, 9-channel AUC and context | [primary manuscript](https://arxiv.org/abs/1808.00100), journal DOI `10.3390/rs10091423` |
| `T2-CABBAGE-NIR` | Tier 2 primary paper | 2025 / Weed detection in cabbage fields using RGB and NIR images | Smart Agricultural Technology 2025 | 2026-08-14 | paired shielded RGB/RGB+NIR detection | capture geometry, split, mAP and inference time | [primary article](https://www.sciencedirect.com/science/article/pii/S2772375525004630), DOI `10.1016/j.atech.2025.101232` |
| `T2-MONO-BOUNDED` | Tier 2 primary paper, non-equivalent | Mekhalfa & Yacef / color and texture features | arXiv 2021-06-19 | 2026-08-14 | bounded negative comparator | RGB-derived feature comparison is not mono-camera A/B | [primary manuscript](https://arxiv.org/abs/2106.10581) |
| `T2-FISCHER-MSI` | Tier 2 primary paper | Fischer et al. / A comparative study of RGB and multispectral imaging for weed detection in precision agriculture | GIL 2024; DOI `10.18420/giljt2024_60` | 2026-08-14 | exact JAI camera, paired RGB/RGBN/RGBNN | capture conditions, dataset/split, Mask R-CNN bbox AP tables and condition subsets | [official Fraunhofer record](https://publica.fraunhofer.de/entities/publication/6ccbec33-82c8-4b18-9145-ba924096769f/details) and [primary PDF](https://publica-rest.fraunhofer.de/server/api/core/bitstreams/a6a9d050-1a8e-48eb-a93d-b522c64b437e/content) |
| `T2-GAO-MOSAIC` | Tier 2 primary paper, directional | Gao et al. / NIR snapshot mosaic hyperspectral imagery for pre-emergence weed/maize classification | Biosystems Engineering 2018; DOI `10.1016/j.biosystemseng.2018.03.006` | 2026-08-14 | snapshot mosaic crop/weed classification | class-wise mean correct rate; no paired RGB comparator or action task | [institutional primary-paper record](https://biblio.ugent.be/publication/8557865) |
| `T2-ZAMANI-THERMAL` | Tier 2 primary paper, directional | Zamani & Baleghi / visible–thermal paddy-field weed detection | published 2022-08-21; Precision Agriculture 2023 | 2026-08-14 | paired visible/thermal object classification | 100 pairs, feature-level/decision-level fusion and best reported accuracy; no target-rig instance/track/action transfer | [primary article](https://link.springer.com/article/10.1007/s11119-022-09954-8) |
| `T2-ZAMANI-DATASET` | Tier 2 author dataset | Zamani & Baleghi / Rice and weed images dataset | Version 3; published 2022-07-25 | 2026-08-14 | paired source-data receipt | 100 pairs, raster, natural light, approximate simultaneity, camera separation/height; spectral/timing ambiguity retained | [Mendeley Data record](https://data.mendeley.com/datasets/9xg52j8tmw/3) |
| `T2-RANARIO-THERMAL` | Tier 2 primary paper, directional | Ranario et al. / thermal segmentation via synthetic RGB-trained models and alignment | accepted 2026-04-11; online 2026-04-30; DOI `10.1016/j.plaphe.2026.100214` | 2026-08-14 | open-field thermal segmentation | thermal contrast limitations and RGB-preserving cross-modality approach; no paired RGB+LWIR action benefit | [publisher article](https://www.sciencedirect.com/science/article/pii/S2643651526000518) and [open full-text mirror](https://pmc.ncbi.nlm.nih.gov/articles/PMC13319522/) |
| `T2-NI-RGBD` | Tier 2 primary paper, directional | Ni et al. / Multi-Modal Deep Learning for Weeds Detection in Wheat Field Based on RGB-D Images | published 2021-11-05; DOI `10.3389/fpls.2021.732968` | 2026-08-14 | paired D415 RGB-D wheat-field bbox task | capture geometry/dataset, RGB-only and fusion IoG/mAP, depth-void causes and hole filling; no exact-camera mask/track/action transfer | [primary article](https://www.frontiersin.org/journals/plant-science/articles/10.3389/fpls.2021.732968/full) |
| `P-BASLER-MONO` | Tier 3 vendor | Graftek / a2A2464-77umPRO | mutable listing | 2026-08-14 | body price/lead-time only | `689 USD`, request lead time | [vendor listing](https://graftek.com/product/a2a2464-77umpro/) |
| `P-FLIR-MONO` | Tier 3 distributor | DigiKey / BFS-U3-51S5M-C | mutable listing | 2026-08-14 | body price/status only | `1.304 USD`, active, available-to-order, 4-week manufacturer lead | [distributor listing](https://www.digikey.com/en/products/detail/flir-integrated-imaging-solutions-inc/BFS-U3-51S5M-C/16528383) |
| `P-SP700` | Tier 3 vendor | Machine Vision Direct / SP700-25.4 | mutable listing | 2026-08-14 | filter price/lead only | `145 USD`, 15 business days | [vendor listing](https://machinevisiondirect.com/products/mid-sp700-25-4) |
| `P-BP850` | Tier 3 vendor | Machine Vision Direct / BP850-25.4 | mutable listing | 2026-08-14 | filter price/lead only | `160 USD`, 15 days | [vendor listing](https://machinevisiondirect.com/products/mid-bp850-25-4) |
| `P-ACA-NIR` | Tier 3 vendor | Soda Vision / acA2040-90umNIR | mutable listing | 2026-08-14 | body price/status only | `1.811 USD`, backorder | [vendor listing](https://www.sodavision.com/product/basler-aca2040-90umnir/) |
| `P-JAI-FS` | Tier 3 vendor | Machine Vision Direct / FS-3200T-10GE-NNC | mutable listing | 2026-08-14 | body price/lead only | `5.400 USD`; 4–12 weeks | [vendor listing](https://machinevisiondirect.com/products/jai-fs-3200t-10ge-nnc) |
| `P-JAI-LENS` | Tier 3 vendor | B&H / JVS-C118-0824-C3 | mutable listing | 2026-08-14 | exact lens price only | `1.234 USD` | [vendor listing](https://www.bhphotovideo.com/c/product/1894413-REG/jai_jvs_c118_0824_c3_lens_for_apex_fusion.html) |
| `P-BOSONPLUS` | Tier 3 vendor | Suntek / Boson+ 640 9.2 mm 50° family | mutable listing | 2026-08-14 | family price boundary; exact suffix mapping unresolved | `5.375–6.500 USD` and listed `22640AS50` variants including `6IARX` | [vendor listing](https://thermal.suntekglobal.com/product/teledyne-flir-boson-640-x-512-9-2mm-50-hfov-short-lens/) |
| `P-RHP-BOSON-SYNC` | Tier 3 vendor | OEMCameras / `RHP-BOS-CL-SY-IF` | mutable listing | 2026-08-14 | exact sync-board price/rate listing | `399 USD`; vendor describes 30 Hz sync-enabled configuration | [vendor listing](https://www.oemcameras.com/products/rhp-bos-cl-sy-if-htm) |
| `P-A6751` | Tier 3 distributor | DataTec / FLIR `29439-251` | mutable listing | 2026-08-14 | exact camera commerce state | quote-only; no public complete-stack price | [distributor listing](https://www.datatec.eu/at/en/teledyne-flir-29439-251) |
| `P-BASLER-BLAZE` | Tier 3 vendor | Graftek / blaze-101 `107796` and listed accessories | mutable listing | 2026-08-14 | exact body and partial trigger-path price boundary | body `1.799 USD`, request lead time; data `72,26`, power-I/O `25,28`, bracket `48,69 USD`; no complete installed/landed cost | [vendor listing](https://graftek.com/product/blaze-101/) |

## 26. Full document-only validation receipt'i

2026-08-14'te kalıcı yardımcı dosya yazmadan terminal validation yeniden
çalıştırıldı. Planner'daki auxiliary YAML/script/result/test dosyaları lane
write contract'ı tarafından supersede edilmiştir. Ephemeral check şunları
birlikte doğruladı:

- `5/5` pinned local authority byte hash'i current dosyalarla aynı;
- V2 JSON baseline span/FOV/GSD/10–20 mm/WD/blur/safe-swath/payload goldens;
- terminal modality arithmetic, body/bay, payload ve dated-partial cost;
- `12` exact H1–H10 satırı, `10` cost satırı, `10` trigger ve empty
  eligible list;
- `60` unique source key, exact source-bundle resolution, nonblank
  tier/version/checked date ve `125` direct URL syntax receipt'i;
- `27` sıralı bölüm, `41` column-consistent Markdown table block'u,
  false safety flags ve prohibited auxiliary output yokluğu;
- iki allowed dosya için `git diff --no-index --check` boş diagnostic.

Exact stdout:

```text
PASS: 686 terminal sensor-optics assertions
headings=27 h_rows=12 cost_rows=10 triggers=10
source_keys=60 direct_urls=125 table_blocks=41
tier_counts=Tier 1:26; Tier 1 family only:1; Tier 1 tech / Tier 3 commerce state:1; Tier 1 tech / Tier 3 public price:5; Tier 2 author dataset:1; Tier 2 primary paper:3; Tier 2 primary paper, directional:4; Tier 2 primary paper, non-equivalent:1; Tier 3 distributor:2; Tier 3 manufacturer commerce:2; Tier 3 vendor:9; local authority:4; local calculation:1
overall_decision=RETAIN_RGB_BASELINE eligible=0 replan=false
```

Bu receipt live URL uptime, physical optics, SNR, sync, registration, latency,
ingress, model utility, crop-hit, deposition veya chemical safety ölçmez.

## 27. Final freeze ve bounded successor kuralları

1. Frozen proof baseline: `1× Basler a2A2464-77ucPRO + C23-0824-5M-P`,
   centered native `2048×2048`, `474–484 mm` FOV, `520–590 mm` WD,
   `170 µs`, `15 Hz`, global shutter, hardware trigger ve dedicated USB3.
2. Visible mono yalnız `TR-MONO-SNR`; RGB+NIR/JAI yalnız `TR-SPECTRAL`;
   yeni RGB+thermal yalnız `TR-THERMAL`; RGB+depth yalnız `TR-DEPTH`
   koşuluyla yeniden açılır. Exact hard fail taşıyan mevcut SKU bu trigger
   oluşsa bile otomatik promote edilmez.
3. `TR-BL-DRIFT`, `TR-SUPPLY` veya `TR-GEOMETRY` oluşursa mevcut survey
   stale olur ve yeni `REPLAN_REQUIRED` değerlendirmesi gerekir.
4. Yeni "belki daha iyi" SKU, physical failure attribution veya contract
   değişikliği olmadan eklenmez. Complete cost olmayan satır sıralanmaz.
5. Bu freeze satın alma, rig kurulumu, GPU işi veya physical A/B başlatmaz.

| Terminal authority flag | Frozen value |
|---|---:|
| `purchase_authorized` | `false` |
| `physical_ready` | `false` |
| `controlled_capture_ready` | `false` |
| `product_go` | `false` |
| `field_go` | `false` |
| `chemical_go` | `false` |
| `gpu_work_performed` | `false` |

Sonuç: **`RETAIN_RGB_BASELINE`**. Bu, kataloglardan bir production camera
satın alma kararı değil; kontrollü fiziksel A–E ve target-rig kanıtına gidecek
tek source-locked proof control'ünün korunmasıdır.
