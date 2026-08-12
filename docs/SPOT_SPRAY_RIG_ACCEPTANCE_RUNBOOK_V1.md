# Controlled Spot-Spray Rig Kabul Runbook V1

Bu runbook, dondurulmuş tek kameralı Basler `a2A2464-77ucPRO` modülünün
**A–F donanım kabulünü** ölçmek ve sürümlü bir YAML receipt ile fail-closed
değerlendirmek içindir. Fiziksel A–E geçişi kontrollü RGB veri toplamayı;
fiziksel A–F geçişi ayrıca kimyasal içermeyen dry-marker aktüasyonunu açabilir.
İki karar ayrıdır. Dondurulmuş V2'de nicel deposition ve crop-injury kabul
eşikleri bulunmadığından kimyasal fire her durumda unsupported ve kapalıdır.

Kaynak kontrat
[`spot_spray_rig_acceptance_v1.yaml`](../configs/deploy/spot_spray_rig_acceptance_v1.yaml),
evaluator
[`evaluate_spot_spray_rig_acceptance_v1.py`](../scripts/evaluate_spot_spray_rig_acceptance_v1.py)
ve sentetik test receipt'leri
[`tests/fixtures/spot_spray_rig_acceptance_v1`](../tests/fixtures/spot_spray_rig_acceptance_v1)
altındadır.

## Değişmez güvenlik kuralları

- `measurement_status: measured` ancak değer gerçekten cihazdan/fixture'dan
  alındığında yazılır. Eksik değer silinmez veya sıfırla doldurulmaz;
  `not_measured` kalır. Eksik, `null` ve `not_measured` hiçbir kapıda PASS
  olamaz.
- Fiziksel receipt `evidence_kind: physical_bench`, `deployment_evidence: true`
  ve `synthetic_fixture: false` kullanır. Her ölçülmüş aşama en az bir kanıt
  artifact'ına referans verir; artifact dosyası mevcut olmalı ve SHA-256'sı
  receipt ile aynı olmalıdır.
- `synthetic_pass.yaml` dahil bütün test fixture'ları yalnız evaluator mantığı
  içindir. İsimleri, URI'leri ve sayıları donanım kanıtı değildir; bunları
  `physical_bench` olarak yeniden etiketlemek geçiş üretmez.
- F eksik veya geçmemişken fiziksel A–E PASS kontrollü RGB capture'a yeter;
  dry-marker ise tam fiziksel A–F PASS olmadan açılamaz. Dry-marker PASS de
  kimyasal fire izni değildir.
- Dış lux, LED peak akımı, strobe pulse ve termal operating state fiziksel
  D ölçümünde ilk kez kaydedilir. Ölçülmemiş optik enerji/joule için sayı
  uydurulmaz; ayrı bir bench değişkeni olarak kalır. Renderer energy fiziksel
  birim değildir.
- Receipt, dondurulmuş V2 config ve karar dokümanı SHA-256'larını taşır.
  Workspace kaynaklarından biri değişmişse evaluator bütün kapılar iyi görünse
  bile izin vermez.
- Evaluator yalnız bu V1 default contract kimliğini kabul eder. CLI exact-byte
  SHA-256 `a6c0e69f1c489e58b7a6c94a92bf50d9dfd97eef0c1b6ec709b872b2f7b66e3c`
  ve canonical-policy SHA-256
  `c05ae3837d98f313c32e81178045a9fef39965199c276ec06e9d01195e88ff21`
  değerlerini gate değerlendirmesinden önce doğrular. `--contract` gevşetme
  kanalı değildir: boş/eksik/yeniden sıralanmış stage listesi, gevşetilmiş eşik
  veya yalnız yorum/whitespace kaynaklı byte drift bile reddedilir. Library
  çağrısı byte path almadığında da exact canonical policy zorunludur.
- Contract veya receipt içindeki duplicate YAML mapping key parse hatasıdır;
  son değer ilkini sessizce ezemez. YAML merge ile aynı safety alanını yeniden
  tanımlamak da kullanılmaz.

## Fiziksel receipt'i başlatma

Yeni bir YAML receipt oluşturun; test fixture'ının kendisini değiştirmeyin.
Kök alanlar şu sınıfı izler:

```yaml
receipt_schema_version: 1
contract_id: controlled_spot_spray_rig_acceptance_v1
receipt_id: <benzersiz-rig-tarih-run-kimliği>
created_at_utc: <offset-içeren-ISO-8601>
evidence_kind: physical_bench
deployment_evidence: true
synthetic_fixture: false
rig_unit_id: <fiziksel-seri>
hardware_revision: <revizyon>
software_commit: <40-haneli-git-commit>
frozen_v2_source_sha256:
  capture_contract: f9fd1cbed95118b4606199e9b67b317c07384e2cb063b60a00e5466848f657e9
  decision_document: c5eb80d8eb074b36463906a4dee993776d2415ae1e41ad50a988c8592e8ed7aa
artifacts:
  A_INVENTORY:
    kind: inventory_quote_and_photos
    path: <receipt-dizinine-göre-dosya-yolu>
    sha256: <dosya-sha256>
    captured_at_utc: <offset-içeren-ISO-8601>
stages:
  A_procurement_and_identity:
    measurement_status: not_measured
  B_transport_trigger_and_thermal:
    measurement_status: not_measured
  C_optics_and_window:
    measurement_status: not_measured
  D_light_hood_and_polarization:
    measurement_status: not_measured
  E_motion_tracking_and_compute:
    measurement_status: not_measured
  F_registration_and_safe_actuation:
    measurement_status: not_measured
```

Her ölçüm dosyasından sonra SHA-256 üretin ve ilgili aşamanın
`evidence_artifact_ids` listesine artifact kimliğini ekleyin. Ham log, fotoğraf,
kalibrasyon çıktısı veya benchmark özeti kaybolursa ölçüm geçemez.

## A–F çalışma sırası

### A — Procurement ve identity

Kamera/lens etiketlerini ve seri numaralarını fotoğraflayın; Basler PRO sipariş
`109779`, renk sensör, fabrika IR-cut, lens `C23-0824-5M-P` sipariş
`2200000568`, kilitli `≤3 m` USB3 kablo, dedicated USB3 root ve harici
`12–24 VDC` power path'i receipt'e yazın. Supplier quote ID, lead time ve
2026-08-11'den **sonraki** quote tarihini kaydedin.

### B — Transport, trigger ve termal

20 Hz hardware trigger ile en az 10.000 frame çalıştırın. Missing/duplicate
counter ve geçersiz timestamp sıfır olmalıdır. Encoder stale olayı sıfır;
trigger–encoder farkı p95 `≤100 µs`, max `≤250 µs`; strobe jitter p95
`≤5 µs`, pulse-width hata oranı `≤0,05`, bus droop `≤0,05` olmalıdır.

En az 120 dakikalık kayıt `5–40 °C` dış ortam zarfını kapsamalı; kamera housing
`≤50 °C`, LED plate `≤60 °C`, frame drop ve throttle sıfır olmalıdır. Bu frozen
baseline PRO harici güç yoludur; powered-USB fallback bu receipt'te kullanılamaz.

### C — Optik ve pencere

Koruyucu pencere takılı, fokus ve iris witness-mark ile kilitliyken gerçek yer
FOV'unu (`474–484 mm`), working distance'ı (`520–590 mm`) ve dış 64 px abstain
sonrası action-safe uzunluğu (`≥444,375 mm`) ölçün.

`0/55/110 mm` object-plane ofsetlerinin her birinde `R1…R9` için tam 27 hücre
girin. Her hücre ayrı geçmelidir: local GSD `≤0,243902439 mm/px`, 10 mm span
`≥41 px`, 20 mm span `≥82 px`, MTF50 `≥0,15 cycles/px`, reprojection RMS
`≤0,30 px`, p95 `≤0,50 px` ve geçerli distortion modeli. Ortalama ile hücre
saklamak veya eksik hücreyi atlamak yasaktır.

### D — Light, hood ve polarization

Installed hood/pencere ile tek bir `bench_setting_id` seçin ve kamera
kontrollerini dondurun. Amaçlanan worst-ambient koşulun kimliğini ve exterior
lux değerini kaydedin. Exposure `170 µs`; strobe pulse `150–170 µs`; peak akım
`0–10 A`; CCT `4500–5500 K`; CRI `≥90`; light branch `≤20 W`; compute hariç
capture modülü `≤60 W` zarfındadır. Aynı passing ayarda 120 dakika termal kapı
tekrar geçer.

R1…R9'un her birinde ambient off/on `≤0,10`, luma `40–205`, white clip
`≤0,002`, black clip `≤0,001` ve temporal SNR `≥20 dB` ölçün; evaluator dokuz
region luma min/max oranını türetir ve `≥0,75` ister. Paired wet-glare testi
zorunludur. Polarization varsayılan `false`; yalnız measured saturated-glare
azalması `≥0,50` ve aynı seçili-state D kapıları geçerse `true` olabilir.

### E — Motion, tracking ve compute

`0,5` ve `1,0 m/s` motion trial'larında exposure `≤170 µs` ve blur `≤0,75 px`
olmalıdır. `1,0 m/s`, `12 Hz` en kötü faz testinde en az 5 geçerli-region
gözlemi kaydedin.

Son benchmark tam olarak bir kamera, 15 Hz, frozen checkpoint ve measured
RTX 3090 üzerinde camera acquisition + tracking + result transfer zincirini
içerir. P95 E2E latency `≤66,6666667 ms`, deadline miss ve frame drop sıfırdır.
Frame sayısı kaydedilir; bu receipt 20 Hz veya ikinci kamerayı açmaz.

### F — Registration ve güvenli dry-marker aktüasyonu

F, A–E veri toplama kararını değiştirmez; ayrı dry-marker readiness üretir.
Stage artifact'ları dört açık `evidence_roles` anahtarına bağlayın:
`homography_encoder_and_daily_registration`, `nozzle_latency_and_footprint`,
`dry_marker_and_deadline`, `hardware_safety_fault_injection`. Tek bir bütünleşik
log birden çok role bağlanabilir; her bağlı artifact yine fiziksel dosya ve
doğrulanmış SHA-256 ister.
Installed pencere/fokus/iris/light state dondurulmuşken homography residual p95
`≤1 mm`, max `≤2 mm` ve kimliği receipt'e yazılan günlük fiducial kontrolünde
drift `≤2 mm` ölçün. Shared real-time
clock ile kamera trigger ve encoder latch aynı hardware event'ten gelmelidir;
host arrival timestamp kontrol için kullanılamaz. Encoder resolution
`≤1 mm/count`, scale error `≤1 mm/m`, trigger–encoder farkı p95 `≤100 µs`,
max `≤250 µs` ve stale no-fire eşiği `≤5 ms` olmalıdır.

Kamera–nozzle along-track ofsetini fiziksel ölçün; `offset_physically_measured:
true`, `offset_CAD_assumed: false` ve pozitif yönü araç seyri olarak kaydedin.
Valve onset latency ile footprint radius, yalnız
water-sensitive paper veya fluorescent dye ölçümünden gelir. Evaluator şu iki
değeri girdilerden yeniden hesaplar; receipt'teki değer tam eşleşmelidir:

```text
command_encoder_mm = capture_encoder_mm
                   + measured_camera_to_nozzle_offset_mm
                   - speed_mm_s × measured_valve_onset_latency_ms / 1000

frozen_no_fire_distance_mm = measured_footprint_radius_mm
                           + p95_total_registration_error_mm
```

Feasible ve forced-missed case'lerde speed, remaining encoder distance,
worst-case inference/result-transfer/controller latency ve aynı fiziksel valve
latency'yi kaydedin. Evaluator gerekli toplam latency'yi ve
`remaining_distance / speed` available time'ı yeniden hesaplar. Feasible örnek
dry-marker komutu üretmelidir. Ayrıca gecikme bütçesini bilerek aşan forced case
çalıştırın: `abort_observed: true`, `valve_enable: false`,
`fire_command: false` zorunludur. Kimyasal içermeyen dry-marker E2E ölçümünde
en az bir mark; hata p95 `≤5 mm`, max `≤10 mm`.

Hardware safety fiziksel test edilir: SELV/LPS ve ayrı sigortalı camera/light/
controller dalları doğrulanır; E-stop strobe ve valve-enable'ı keser; watchdog
default no-fire ve valve disabled kalır. `timestamp_invalid`, `encoder_stale`,
`frame_drop`, `calibration_invalid`, `overtemperature`, `hood_open` hatalarının
her biri ayrı enjekte edilir ve her birinde no-fire ile `valve_enable: false`
gözlenir. Eksik fault satırı ortalamayla geçemez.

F receipt'i şu kimyasal durumu aynen taşır:

```yaml
chemical:
  chemical_enable: false
  chemical_enable_hardware_line_verified_disabled: true
  deposition_acceptance_status: unsupported_unmeasured_no_frozen_threshold
  crop_injury_acceptance_status: unsupported_unmeasured_no_frozen_threshold
```

Bu bir geçici placeholder PASS değildir: frozen V2 nicel eşik vermediği için
evaluator kimyasal kapıyı açamaz ve sayı icat etmez.

## Değerlendirme

```bash
.venv/bin/python scripts/evaluate_spot_spray_rig_acceptance_v1.py \
  --receipt <physical-receipt.yaml> \
  --output <acceptance-result.json>
```

Varsayılan exit kodu yalnız kontrollü veri-toplama kararını izler: doğrulanmış
fiziksel A–E geçişinde, F henüz ölçülmemiş olsa bile exit `0` verir. Fail,
`NOT_MEASURED` A–E ve bütün sentetik fixture'lar exit `2` verir.

Dry-marker otomasyonunda ayrı hedef zorunludur:

```bash
.venv/bin/python scripts/evaluate_spot_spray_rig_acceptance_v1.py \
  --receipt <physical-receipt.yaml> \
  --output <acceptance-result.json> \
  --decision-target dry-marker
```

Bu hedef yalnız fiziksel A–F PASS için exit `0` verir; F fail/unmeasured ve
bütün sentetik fixture'lar exit `2` verir.

`--output` yolu receipt, seçili contract veya default contract ile aynı dosya
(symlink/hardlink dahil) olamaz. Sonuç aynı dizinde geçici dosyaya tam yazılıp
`fsync` edildikten sonra atomik replace ile yayınlanır; yarım JSON görünmez ve
replace başarısızsa eski sonuç korunur. Contract/receipt parse, identity veya
output-safety hatası exit `1`; değerlendirilmiş fakat izin vermeyen güvenli
karar exit `2` üretir. Sonuçtaki `contract_identity`, exact-byte ve canonical
policy doğrulamasını ayrıca kaydeder. `implementation` alanı da portable
script yolunu ve evaluator SHA-256'sını
`596c6db31e6ce90f06b1019657e58631415f1b90fdeeb9fdbd917b4ab461fda2`
olarak kaydeder. Capture audit, fiziksel collection izni için bu iki kimliğin
de kendi dondurulmuş kaynaklarıyla tam eşleşmesini ister; eski veya kimliksiz
bir sonuç PASS alanları taşısa bile geçersizdir.

- `GO_CONTROLLED_DATA_COLLECTION`: fiziksel receipt, source/artifact integrity
  ve bütün A–E kapıları geçti; kontrollü RGB capture açılabilir.
- `NO_GO_NOT_MEASURED`: eksik receipt alanı, stage, ölçüm veya artifact vardır.
- `NO_GO_FAILED`: measured değer, schema, source veya artifact integrity kapısı
  ihlal edilmiştir.
- `SYNTHETIC_NOT_DEPLOYMENT_EVIDENCE`: yalnız test mantığı çalışmıştır; saha
  veya veri toplama izni yoktur.
- `READY_SAFE_DRY_MARKER`: fiziksel source/artifact integrity ve bütün A–F
  geçti; yalnız kimyasal içermeyen dry-marker aktüasyonu açılabilir.
- `NOT_READY_DRY_MARKER_NOT_MEASURED` / `NOT_READY_DRY_MARKER_FAILED`: F veya
  başka bir A–F önkoşulu eksik/başarısız; dry-marker kapalıdır.
- `SYNTHETIC_NOT_DRY_MARKER_EVIDENCE`: sentetik F mantığı çalışmıştır;
  aktüasyon izni yoktur.

Her sonuçta `stage_F_evaluated: true` olur; stage sonucu ayrıca raporlanır.
Dry-marker READY olsa bile `chemical_fire_allowed: false` ve açık
`chemical_fire_blocker` kalmalıdır.
