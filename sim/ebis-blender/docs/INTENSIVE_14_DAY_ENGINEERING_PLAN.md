# Blender-EBİS: 14 günlük yoğun gerçekçilik ve YOLO nano planı

## Sprint hedefi

On dört günün sonunda iki ayrı soruya kanıtla cevap ver:

1. Blender sahnesi seçilen gerçek EBİS makinesinin değişmeyen geometrisini, materyalini, iki kamerasını ve LED aydınlatmasını release üretimi için yeterli doğrulukta temsil ediyor mu?
2. Instance-aware güvenli bbox hattından geçen sentetik görüntüler, aynı frozen gerçek validation/test üzerinde en küçük YOLO modelinin RFID detection performansını iyileştiriyor mu?

Hero render, insan review’u, validator PASS ve model sonucu ayrı kapılardır. İyi görünen kare AP kazancı; tek seed veya yalnız validation artışı da genellenebilir model faydası sayılmaz.

## Başlangıç noktası: `v1.8.1 / V8 cast-pore PBR`

Sprint sıfırdan başlamaz. Kanonik
`realism_v8_cast_pores_release_60100`; 12-kare engine validator ve
güncel wide-open V8 BlenderMCP turunda `PASS`tir. Düz nominal numune
konturu, right-hinged solid front door, üç mavi sabit hammertone duvar,
gri hareketli kapı/servis kapağı, iki `Ø400 mm` tabla, üç-duvar U-LED ve
düşük-oranlı ambientCG concrete hibriti birlikte doğrulanmıştır. Bu bir
dijital ikiz veya model-faydası kanıtı değildir.
Mevcut üreticide aşağıdaki parçalar vardır; her biri ölçü/referans
geldikçe yeniden kalibre edilecektir:

- REF-65218/İvedik varsayımlı makine profili: back/left/right sabit
  yüzeyler mavi pebbled/hammertone; hareketli kapı/servis kapağı gri sac;
- dışarıdan bakınca sağ menteşeli, dolu gri ve dışa açılan ön kapı;
  `near_closed / partially_open / wide_open` bounded modları;
- üst tabla seviyesinde back + left + right duvar boyunca ince metal kanal, opal difüzör, contact spill ve kapı açısına bağlı dış ortam fill;
- aynı eksenli büyük alt/üst çelik tablalar, küçük ölçekli machining/roughness varyasyonu;
- düz dikey kenarlı düzenli küp/silindir, daha küçük çok ölçekli beton
  pore/aggregate ve bounded edge-worn/spalled varyasyonu;
- cam-10 ve cam-11’e ayrı lens, düşük/bounded distortion, exposure,
  hedef ve küçük mount jitter; görüntüde güvenilir olmayan fiziksel kamera
  gövdesi uydurulmaz;
- küp üzerinde baskılı kağıt/tape, RFID ile bağlı kısmi veya tam örtme;
- paper/tag linkage, camera realization, door, lighting ve machine state metadata’sı;
- scoped RNG, scene contract ve instance görünürlük/partition validator hook’ları.

`v1.8.1` doğrulanmış fiziksel ground truth değil, iyileştirilmiş
başlangıç release candidate’ıdır. En yüksek değerli üç dış girdi:

1. iç chamber, sağ kapı pivotu/leaf'i, iki tabla ve iki kamera mount'unun ölçülü CAD'i;
2. mavi pebbled boyalı sac, gri kapı sacı, kullanılmış çelik, kalıp yüzlü beton ve kırık betonun
   scale-referanslı cross-polarized PBR/scan seti;
3. cam-10/cam-11 checkerboard/ChArUco intrinsics, distortion, grey-card,
   empty-chamber ve diffuser açık/kapalı exposure/lux ölçüleri.

Silindir yüzeyini gerçekten takip eden conformed paper henüz yoktur. Düz
kağıdı silindirin önünde yüzdürmek annotation hatası üretebileceğinden
UV/curve/deform, yüzey offset’i ve RGB-mask warp eşliği doğrulanana kadar
ertelenir.

## İki kapsam kararı ve varsayılanlar

[`USER_SUPPORT_AND_REVIEW.md`](USER_SUPPORT_AND_REVIEW.md) içindeki iki karar sprintin release yorumunu değiştirir:

1. Hedef makine REF-65218/İvedik mi? Yanıt gelmezse bu profil `assumption` olarak sürer.
2. Elde/duvarda staged tag’ler hedef pozitif mi? Yanıt gelmezse yalnız beton/tabla operasyonel tag’ler hedef kabul edilir.

Bu yanıtlar geliştirmeyi bekletmez; ancak yanlış makine karışımı veya yanlış pozitif kapsamla “gerçekçi/başarılı” release ilan edilmez.

## Değişmez veri ve annotation sözleşmesi

- Sınıflar: `0 rfid_tag`, `1 concrete_sample`.
- Kamera eşleme: `camera_angled = cam-10/Kamera 01`, `camera_door = cam-11/Kamera 02`.
- RGB, semantic mask ve her RFID instance maskesi aynı sahne/kamera warp’ından gelir.
- RFID bbox amodal karttan değil, görünür per-instance maskeden sıkı türetilir.
- Tam kapalı veya frame dışında tag bbox almaz.
- Görünürlük `<0.15` veya largest-component ratio `<0.45` ise kare `exclude`; üretim/eğitimde kullanılmaz.
- `0.15–0.35` görünürlük ve component ratio `≥0.45` ayrı `hard`; ana production’a kendiliğinden girmez.
- Görünürlük `≥0.35` ve component ratio `≥0.65` `standard` adayıdır.
- Bölünmüş görünür tag tek instance/tek union bbox kalır; largest-component gate kötü union’ı yakalar.
- Kağıt, kapı, tabla, sample ve chamber gerçek occluder’dır; segmentation sonrası keyfi bbox büyütülmez.
- Gerçek train/val/test capture/session bazında ayrılır; ardışık frameler split’ler arasında sızmaz.
- Validation ve test yalnız gerçektir. Sentetik val/test raporuyla fayda iddia edilmez.

Eşikler Day 1’de config hash’iyle dondurulur. Eşik değişikliği yeni annotation schema sürümü ve bütün pilot/QC’nin tekrarını gerektirir.

## Seed, sürüm ve artefakt sözleşmesi

Her render metadata’sı şunları taşımalıdır:

```text
dataset_id
scenario_seed
generator_version
annotation_schema_version
config_sha256
generator_sha256
asset_manifest_sha256
blender_binary_version_sha256
camera_id + camera_realization
machine_profile
sample_shape + dimensions
door_profile + angle
led_profile
paper/tag placement + visibility
partition + exclusion_reasons
```

- Global scenario seed’den `geometry`, `door`, `camera`, `lighting`, `sample`, `paper`, `rfid` scoped seed’leri türetilir. Bir materyal fonksiyonuna yeni random çağrı eklemek tag sayısını değiştirmemelidir.
- Calibration seed’leri yeni sprintte `60000..60099` altında ayrı manifestte
  ayrılır; kanonik `60100..60111` release seed’leri tekrar kullanılmaz.
- Pilot/production aralıkları calibration ile çakışmaz; aralıklar manifestte kaydedilir.
- Model seed’leri: `17`, `29`, `43`.
- Output dizini immutable’dır; config/script/asset hash’i değişince yeni dataset ID açılır, eski release üzerine yazılmaz.
- Lokal ve 3090 mirror için seçilen source/release artefaktlarında SHA-256 eşliği doğrulanır.
- Her gün `decision_log.md` satırı: değişiklik, kanıt, komut, süre, PASS/FAIL, açık risk, ertesi gün kararı.

## Kapılar

| Kapı | Ölçüt | Fail davranışı |
| --- | --- | --- |
| G0 — kaynak/kapsam | makine ve pozitif kapsam kararı veya açık fallback; tüm ölçü/asset kaynak-birim-lisans/hash kayıtlı | tahmin gerçek ölçü diye sunulmaz |
| G1 — geometri | iki kamera × iki shape clay grid; kapı/LED/tabla/kamera landmark ve sample-platen temas PASS | materyal calibration dondurulmaz |
| G2 — appearance | clipping/black crush temiz; owner + operatör ayrı overall medyan `≥3/5`, ortak dört eksen medyanı `≥3/5`, blocker `0` | tek katmanlı bounded düzeltme |
| G3 — annotation pilot | 16 deterministic senaryoda RGB/mask/metadata/label eşliği, duplicate yok, coverage tam, validator PASS | production yok |
| G4 — insan bbox QC | 100 stratified kare; standard’da görünür unlabeled tag `0`, kritik bbox/partition hata `0`, diğer hata `≤%2` | generator düzelir, fresh 100 tekrar |
| G5 — split/model disiplini | split hash’i, source-only ve mix manifestleri, environment/checkpoint/update budget eş | karşılaştırma geçersiz, run tekrarlanır |
| G6 — model faydası | önceden yazılmış GO eşikleri frozen testte üç seed ile sağlanır | HOLD; daha çok sentetik üretme yok |

## YOLO nano deney tasarımı

En küçük sabit checkpoint kullanılır (`yolo11n.pt`, proje ortamı başka nano sürüm pinliyorsa hash’li eşdeğeri). Checkpoint, Ultralytics/container environment, image size, batch, optimizer, LR schedule, augmentasyon, weight decay, AMP ve model selection kuralı bütün koşullarda byte-identical config’ten gelir. Ana kıyas modeli, ortak optimizer-update bütçesinin sonundaki `last.pt`dir; `best.pt` yalnız real-val teşhisi olarak saklanır.

Gerçek train setine `R`, uygun gerçek görüntü sayısına `N` de. Sentetik doz, `S/R` oranıdır:

| Koşul | İçerik | Amaç |
| --- | --- | --- |
| `R_ONLY` | `R`, sentetik yok | source-only baseline |
| `R_S025` | `R + 0.25N standard Blender` | düşük doz |
| `R_S050` | `R + 0.50N standard Blender` | orta doz |
| `R_S100` | `R + 1.00N standard Blender` | eşit doz |
| `R_Sbest_HARD` | en iyi val dozu + kontrollü hard subset | hard-occlusion ablation |

Her koşul seed `17/29/43` ile çalışır. Karşılaştırmayı daha büyük datasetin daha fazla optimizer update almasıyla karıştırmamak için `target_optimizer_updates` Day 1’de sabitlenir; dataset uzunluğuna göre epoch sayısı hesaplanır ve sözleşme update sayısı loglanır. Tek GPU ile `nbs=batch` kullanılarak bir loader batch'i bir optimizer update'e sabitlenir. Early stopping ana matriste kapalıdır. Dataset boyuna bağlı epoch sınırlarında real-val değerlendirme cadence'i aynı update noktalarına denk gelmediği için ana model seçimi yapılmaz; ortak bütçe sonundaki `last.pt` kullanılır. Integer epoch granularity hedef update budget'ından `%1`den fazla sapıyorsa run başlamaz ve dört standard frozen manifestin paylaşabildiği bütçe Day 1'de yeniden seçilir. Day 13 hard manifesti seçilen standard dozla aynı toplam uzunlukta olduğu için aynı bütçe hesabını devralır ve ayrıca preflight edilir.

Hard ablation için:

- yalnız annotation/QC kapılarını geçmiş `hard` görüntüler;
- en iyi standard sentetik dozun toplam sentetik sayısı sabit;
- standard subsetin belirlenmiş bir kısmı hard ile değiştirilir; ekstra görüntü eklenmez;
- başlangıç replacement oranı `%20`, gerekirse yalnız önceden kayıtlı `%10/%30` sensitivity;
- `exclude` hiçbir koşulda kullanılmaz.

Bu tasarım “source-only + üç mix oranı + hard occlusion” sorusunu aynı veri bölümü ve sabit update bütçesiyle yanıtlar.

## Ana metrikler, slice’lar ve GO/HOLD

Ana hedef RFID’dir. Üç seed için tek değer yerine median ve IQR raporlanır:

- RFID AP50-95, AP50, precision, recall;
- concrete AP50-95 ve recall;
- cam-10/cam-11;
- cube/cylinder;
- tiny/small/medium görünür tag alanı;
- paper-under-tag, plate-gap, loose/front/side;
- standard/hard gerçek occlusion slice’ı;
- door full/partial ve LED/exposure zamanı;
- varsa person/hand ve staged/operational.

Önceden yazılmış ana GO ölçütü:

- `R_ONLY`a göre RFID AP50-95 median farkı `≥ +2.0` puan;
- üç seed’in en az ikisi pozitif;
- RFID recall medianı gerilemez;
- concrete AP50-95 kaybı `≤1.0` puan;
- cam-10 ve cam-11 slice’larından hiçbiri anlamlı negatif yönde değildir;
- kritik tiny/plate-gap slice’ında mutlak FN artışı yoktur.

Bootstrap confidence interval ve per-seed değerler raporlanır; CI sıfırı kesiyorsa sonuç “promising/inconclusive”, kazanç diye yazılmaz. Sonuç görülünce eşik değiştirilmez.

## Gün 1 — referans, kapsam, split ve baseline freeze

Amaç: hangi makineyi, hangi pozitifleri ve hangi gerçek benchmarkı hedeflediğimizi sabitlemek.

- LED RGB arşivinin cam-10/cam-11 erken-orta-geç zaman örnekleri ve bütün `REF*` IR klasörlerinin stratified sheet’i dondurulur.
- Aynı makinede değişmeyen parçalar ile makineye/zamana bağlı varyasyon ayrılır. IR yalnız topoloji, kamera ve occlusion için kullanılır; RGB fotometriye hedef yapılmaz.
- İki kritik kapsam sorusunun yanıtı kaydedilir; yoksa yukarıdaki fallbacks metadata’ya yazılır.
- Mevcut gerçek label inventory yeniden audit edilir; class `0/1` derived set, bozuk/boş label ve staged/operational alanı çıkarılır. Orijinal dosyaya dokunulmaz.
- Capture/session/task gruplarıyla leakage’siz `train/val/test` oluşturulur. Manifest, derived label inventory ve split-audit SHA-256 ile `split_freeze.json` içine pinlenir.
- `test_seal.json` Day 14’e kadar final testi erişime kapatır.
- `v1.8.1` source/config, V8 release/current-samples ve güncel V8 MCP
  kanıtı baseline olarak hashlenir.
- YOLO nano checkpoint/environment pinlenir; update budget ve model seçim kuralı sonuç görülmeden yazılır.

Çıktı: reference manifest/sheet, machine/invariance ledger, scope decision,
split freeze, sealed test, v1.8.1 baseline ve experiment contract. Kapı:
split leakage `0`, hash recheck PASS.

## Gün 2 — ölçü ve iki kamera kalibrasyonu

- Kullanıcıdan gelen ölçü/CAD varsa [`ebis_physical_measurements_template.json`](../configs/ebis_physical_measurements_template.json) doldurulur; yoksa fallback/mm belirsizlikleri açık kalır.
- Kutu, sağ kapı/pivot, servis kapağı, üç panel, ram, iki tabla, U-LED
  ve kamera mount için tek eksen/birim sözleşmesi çizilir.
- Cam-10/cam-11 checkerboard/ChArUco intrinsics çözülür. Board manifesti yoksa calibration değil `visual fit` etiketi kullanılır.
- Gerçek frame’lerde tabla/sample/LED/kapı/kamera landmark’ları kamera bazında ölçülür.
- Kapı açısı yaklaşık dağılımı güncel bounded
  `near_closed=4–18° / partial=20–55° / wide=60–95°` fallback’iyle
  karşılaştırılır; veri gelirse dağılım güncellenir.
- mm↔m, parent transform ve camera projection unit testleri eklenir.

Çıktı: measurement, camera calibration/fit ve landmark raporu. Kapı: birim/eksen PASS; belirsizlikler görünür.

## Gün 3 — chamber, kapı, kamera ve press geometri kilidi

- REF-65218 hedefiyse sabit back/left/right mavi hammertone ve hareketli
  kapı/servis kapağı gri sac ayrımı korunur; farklı makine seçildiyse
  ayrı bir profile geçilir, iki makine bilinmeden karıştırılmaz.
- Kapı erişim boşluğu, sac kalınlığı, çerçeve, menteşe ve açık kanat gerçek pivotla düzeltilir; kapı her açıda kameraları kesmemelidir.
- Servis kapağı, conta ve dört vida kapı leaf'ine parent edilir. Görüntüde
  güvenilir olmayan bezel/lens/yardımcı port uydurulmaz; ölçü veya açık
  referans gelirse ayrı reference-fit obje yapılır.
- Alt/üst tablalar aynı eksende, ölçülü çap/kalınlık/bevel ve ram bağlantısıyla kurulur.
- Küp/silindir iki tablaya temas eder; penetration ve air-gap validatorı çalışır.
- U-LED metal kanal + opal cover olarak üst tabla seviyesinde back/left/right tam segmentlenir.
- Cam-10/cam-11 × cube/cylinder nötr clay grid render edilir.

Çıktı: `geometry_rc`, landmark overlay ve contact/penetration report. Owner review A. Kapı: G1.

## Gün 4 — chamber ve çelik PBR

- Mavi sabit iç sac için gerçek mm texel scale’de pebbled/hammertone
  normal, paint roughness, coat ve bounded edge wear kalibre edilir;
  tüylü/keçe görünümü reddedilir.
- Gri hareketli kapı/servis kapağı aynı mikro-topolojiyi kopyalamak yerine
  referansın gösterdiği daha sakin sac/roughness profiline sahip olur.
- Üst/alt tabla radial machining, ince scratch, çimento tozu/grease ve bounded renk/roughness varyasyonu alır. Ayna, beyaz plastik ve merkezde yapay bullseye reddedilir.
- LED kanalı metali, opal difüzör, gasket, kamera camı ve siyah bezel ayrı materyal olur.
- Material debug: albedo, roughness, normal ve specular pass; dört fixed seed, nötr ışık.
- Her procedural ölçek mm ve kaynak/fallback bilgisiyle material manifestine yazılır.

Çıktı: material library/manifest ve review B grid’i. Kapı: texture swimming, macro-noise veya ölçek dışı çizik yok.

## Gün 5 — beton, kağıt ve RFID fiziksel görünümü

- Küp kalıp yüzü, küçük bevel, kenar aşınması; silindir yan kalıp yüzü ve uç yüzü ayrı karakterize edilir.
- Pore/aggregate çok ölçekli fakat mm tabanlıdır; boncuk, köpük veya rastgele yüzen taş görünümü reddedilir.
- Sample boyutları düzenli; deformasyon/damage düşük ve bounded prior’dır.
- RFID film, antenna, chip, adhesive ve küçük edge-lift ayrılır; neon doygunluk kullanılmaz.
- Küpte paper print, tape, stain, curl/offset ve linked RFID partial/full occlusion unit testleri çalışır.
- Fully hidden tag’in metadata’da kalıp YOLO label almaması; partial tag’in tek instance/union bbox olması doğrulanır.
- Silindir conformed paper için küçük teknik spike yapılır. Surface-following mesh + offset + RGB/instance-mask alignment her iki kamerada PASS değilse release’e alınmaz ve `deferred` kalır.

Çıktı: cube/cylinder material grid, paper/tag occlusion testleri ve cylinder-paper karar kaydı.

## Gün 6 — U-LED ve gölge tabanı kalibrasyonu

- Görünen emissive difüzör ile sahneyi aydınlatan strip/area kaynaklar ayrılır.
- LED kanalı üç duvar boyunca ince ve kesintisizdir; dev beyaz panel veya tek parlak ellipse oluşmaz.
- Betonun üst tabla temas çizgisinde küçük spill/highlight; chamber içinde sıfır siyah olmayan gölge tabanı hedeflenir.
- Cam-10 ve cam-11 için gerçek ROI histogram/percentile karşılaştırılır. Cam-11’de aşırı koyu aperture lift edilir; center/right clipping engellenir.
- Door/workshop fill kapı açısıyla koreledir; full ve partial aralıkları ayrı kalibre edilir.
- CCT, güç, bloom/halation ve denoiser smear dört fixed seed’de kontrollü ablation görür.

Çıktı: LED açık/kapalı/profil grid’i, ROI histogram raporu. Owner review C-light. Kapı: sample/tabla geniş alan clipping yok, black-crush gate PASS.

## Gün 7 — kamera, lens, kapı prior’ı ve sensor görünümü

- Cam-10 ve cam-11 intrinsics varsa uygulanır; yoksa dar bounded focal/distortion visual-fit aralıkları korunur.
- Ana framing korunur; yalnız küçük mount jitter, roll, target ve focal varyasyonu scoped RNG ile yapılır.
- Door angle bimodal full/partial prior’ı gerçek arşivle eşlenir; door/glass/frame gerçek occluder’dır.
- Vignette, sharpening, bloom, noise, WB ve compression gerçek crop’tan kamera bazında ölçülür. Efekt yalnız RGB’ye uygulanır; mask alignment bozulmaz.
- Dört seed’de checkerboard/landmark projection ve concrete bbox medyan farkı hedefi `≤0.03` normalize kadrajdır.
- Cam-10/cam-11 için ayrı hero ve stress grid’i çıkar.

Çıktı: camera profiles, sensor ablation ve framing report. Owner review C-camera. Kapı: warp/mask eşliği PASS.

## Gün 8 — placement, görünürlük ve bbox güvenliği

- Operasyonel tag placement prior’ı front/side, upper/lower plate-gap, paper-under-tag ve loose olarak dondurulur; staged veri ayrı tutulur.
- Gerçek arşiv staging nedeniyle 0–19 tag gösterebilse de production tag-count gerçek operasyon prior’ından gelir; yoğun staging otomatik kopyalanmaz.
- `standard`, `hard`, fully hidden, below-threshold, outside-frame ve multi-component için en az beşer deterministic unit scene üretilir.
- Visible mask alanı, largest component, tight bbox, frame clip ve worst-instance partition hem validator hem elle kontrol edilir.
- Paper-linked fully hidden tag `include_in_yolo=false` olmalıdır; label varsa hard fail.
- Annotation schema/report hashlenir.

Çıktı: occlusion matrix ve validator test raporu. Kapı: standard visible-unlabeled sızıntısı `0`.

## Gün 9 — reference-fit release candidate ve kör review

- Gerçek arşivden aynı makine/camera/shape/zaman stratified referanslarla old Blender vs candidate vs real kör grid hazırlanır.
- Dört fixed seed 1280×720 veya üzeri yeterli Cycles sample ile fresh output’a render edilir.
- Geometri, materyal, ışık ve kamera tek tek [`USER_SUPPORT_AND_REVIEW.md`](USER_SUPPORT_AND_REVIEW.md) rubric’iyle owner + operatör tarafından puanlanır.
- Yalnız ortak blocker/yüksek en fazla üç sorun, bir katman değişikliğiyle düzeltilir.
- Değişen config/script/asset yeni RC hash’i açar; dört seed yeniden render edilir.

Çıktı: blind review ledger, before/after grids ve bounded change log. Kapı: G2.

## Gün 10 — deterministic 16 pilot ve 100-kare insan QC

- `2 camera × 2 shape × 2 door × 2 paper/tag state = 16` deterministic scenario table; her hücrede RGB, semantic ve bütün instance maskeleri.
- Duplicate hash, camera/shape/state coverage, RGB-label-mask-metadata eşliği ve partition validatorı çalışır.
- G3 PASS sonrası farklı seed’lerden 100 kare camera × shape × LED × door × placement × visibility stratified seçilir.
- İki reviewer bbox sıkılığı, eksik/fazla label, fully-hidden, partition ve fiziksel imkânsızlığı bağımsız işaretler.
- G4 fail ise generator düzeltilir; fresh 16 + fresh 100 tekrar edilir. Sadece problemli kareleri silerek PASS üretilmez.

Çıktı: `annotation16` release, 100-QC manifest/error ledger. Kapı: G3 ve G4.

## Gün 11 — standard sentetik havuz ve deney manifestleri

- G4 geçen fresh seed aralığından yalnız `standard` production havuzu üretilir.
- Camera×shape×door×light×placement×tag-size dağılımı gerçek train hedeflerine göre stratified olur; simülasyonda kontrol edilebilir nadir slice’lar ayrıca işaretlenir.
- `R_S025`, `R_S050`, `R_S100` sentetik subsetleri nested ve deterministic seçilir; doz farkı dışında dağılım mümkün olduğunca sabit kalır.
- Frozen gerçek train sayısı `N`, exact integer doz ve tam `%20` hard
  replacement için `20`ye bölünebilir seçilir; en fazla 19 uygun gerçek
  kare stratification korunarak önceden ayrılır.
- Hard havuz ayrı tutulur; `exclude` hiçbir frozen manifeste girmez.
- Dört standard koşul için train manifestiyle birebir sıralı
  `image_path,source,partition` composition CSV'si üretilir ve runner
  preflight PASS alınır. `R_Sbest_HARD` manifesti henüz oluşturulmaz;
  Sbest Day 12 val-only sonucundan önce bilinemez.
- Dört composition tek `standard_matrix_lock.json` içinde hashlenir;
  aynı real set ile `R_S025 ⊂ R_S050 ⊂ R_S100` sentetik nesting ilişkisi
  fail-fast doğrulanır. Bütün standard run'lar aynı lock SHA'sını pinler.
- Her manifest için image/label SHA inventory, config/source/Blender/GPU/driver hash’i, render süresi ve disk maliyeti yazılır.
- Dataset leakage, aynı RGB’nin koşullar arası yanlış label varyantı ve duplicate audit edilir.

Çıktı: frozen standard/hard pool ve dört ana training manifesti. Kapı: dataset hash/audit PASS.

## Gün 12 — source-only ve üç mix oranı nano training

- Önce iki epoch ingest smoke; NaN, class mapping, empty batch, image/label cache ve VRAM kontrol edilir.
- `R_ONLY`, `R_S025`, `R_S050`, `R_S100` seed `17/29/43` çalıştırılır.
- Bütün koşullarda frozen real validation; test seal kapalıdır.
- Dataset uzunluğuna göre epoch sayısı yalnız sabit optimizer update bütçesini sağlamak için hesaplanır. Gerçek updates, seen images, wall time, peak VRAM ve images/s loglanır.
- Ana kıyas checkpoint'i ortak update bütçesinin sonundaki `last.pt`dir;
  `best.pt` yalnız teşhistir. Sbest dozu her seed'in `last.pt` real-val
  RFID AP50-95 değerlerinden seçilir; validation sonuçlarıyla generator
  veya split tune edilmez.
- Per-seed ve median/IQR real-val tablo hazırlanır; hard ablation dozu önceden tanımlı kuralla seçilir: en iyi median RFID AP50-95, eşitse recall, yine eşitse daha düşük sentetik doz.
- Exact 12-satırlı val metrics CSV, dört koşul × üç seed `PASS`
  contract ve `last.pt` hash'lerine bağlanır. `select_sbest.py` seçim
  kuralını yeniden hesaplayıp immutable `sbest_selection.json` yazar;
  Sbest elle seçilmez.

Çıktı: 12 ana run, environment/run manifests ve val-only doz kararı. Kapı: G5.

## Gün 13 — hard-occlusion ablation ve hata analizi

- Seçilen en iyi dozdaki sentetik sayısı sabit tutularak standard örneklerin `%20`si QC-geçmiş hard örneklerle değiştirilir.
- Hard composition; aynı real seti, Sbest ile aynı toplam sentetik sayıyı,
  Sbest'ten kalan standard altkümesini ve tam `%20` yeni
  `hard_occlusion` replacement'ı kanıtlar. Day 11'deki `N % 20 = 0`
  sözleşmesi üç olası Sbest sentetik toplamının da `5`e bölünmesini
  garanti eder.
- `R_Sbest_HARD` train/composition manifesti ancak Sbest kararından sonra
  üretilir; hash/audit ve runner preflight PASS olmadan eğitim başlamaz.
- Runner selection ledger'ın matrix-lock SHA'sını, bütün 12 standard
  run contract/checkpoint hash'ini ve verilen Sbest composition'ın
  gerçekten seçilmiş koşula ait olduğunu yeniden doğrular.
- `R_Sbest_HARD` seed `17/29/43`, aynı checkpoint/config/update bütçesiyle eğitilir.
- Frozen real val’de cam-10/11, shape, tag-size, paper, plate-gap ve occlusion slice’ları çıkarılır.
- Ana koşullardan toplam en az 50 FP + 50 FN; label error, real miss, scope mismatch, glare, tiny, plate-gap, paper ve background bucket’larına ayrılır.
- Test hâlâ kapalıdır. Teste bakarak hard oranı veya generator ayarı değiştirilmez.

Çıktı: üç hard run, val slice table ve FP/FN gallery. Kapı: bütün candidate checkpoint listesi Day 14 öncesi hashlenir.

## Gün 14 — tek sealed gerçek-test, karar ve devir

- Eval öncesi split, derived label, environment, model checkpoint ve training manifest hash’leri yeniden doğrulanır.
- `test_seal.json` yalnız kayıtlı final komutu için açılır; zaman, operator, checkpoint listesi ve gerekçe append-only unseal kaydına yazılır.
- `R_ONLY`, üç standard doz ve hard ablation `last.pt` checkpoint’leri frozen gerçek testte aynı komutla bir kez değerlendirilir.
- Üç-seed median/IQR, bootstrap CI, bütün zorunlu slice’lar, render/train/QC maliyeti raporlanır.
- G6 eşiği değiştirilmeden uygulanır. GO ise yalnız kazanan dozla daha büyük production ayrı gelecek sprinttir. HOLD/inconclusive ise 10k üretim yapılmaz; baskın kanıta göre ölçü/kamera/PBR/placement/annotation önceliği seçilir.
- README/handoff, source/release/evidence hash’leri ve 3090 mirror güncellenir.

Çıktı: final model-impact report, GO/HOLD/inconclusive kararı, reproducibility manifesti ve en fazla üç sonraki öncelik.

## Fail-fast kuralları

Aşağıdaki durumlardan biri varsa render veya training büyütülmez:

- hedef makine parçaları başka REF makineyle bilinmeden karışmış;
- split leakage veya test seal ihlali;
- RGB/mask warp farkı, duplicate veya instance-label eşleşme hatası;
- standard partition’da görünür unlabeled RFID;
- fully hidden tag’e bbox;
- sample-platen penetrasyon/air-gap;
- kapının kamera veya gerçek erişim geometrisiyle fiziksel çelişkisi;
- geniş alanda clipping, yapay tam siyah gölge veya LED’in dev panel/ellipse görünümü;
- 16 pilot/G3 veya 100 QC/G4 fail;
- model koşulları arasında checkpoint/hyperparameter/update budget farkı;
- yalnız bir seed ya da yalnız sentetik/validation metrikle kazanç iddiası.

## İki haftalık teslim kontrol listesi

- target machine ve staged-positive kapsam kararı/fallback kaydı;
- temporally stratified LED RGB + REF IR reference manifest ve invariance ledger;
- ölçü/CAD/camera/material provenance ve fallback listesi;
- `v1.8.1 / V8` baseline ile hash’li final generator/config/asset manifesti;
- iki kamera × iki shape clay/material/light/camera comparison;
- cylinder conformed paper için PASS release veya açık `deferred` kararı;
- deterministic 16 pilot validator PASS ve iki kişilik 100-kare QC;
- frozen gerçek split, test seal ve source-only/üç doz/hard manifestleri;
- environment/checkpoint/update-budget eşliği kanıtlanan 15 nano run;
- frozen gerçek testte seed, median/IQR/CI ve zorunlu slice raporu;
- FP/FN gallery, maliyet ve GO/HOLD/inconclusive kararı;
- lokal/3090 source ve seçili release SHA-256 eşliği.

Bu artefaktlar ve model sonuçları olmadan “ideal hâle geldi”, “Unreal/Blender daha iyi” veya “YOLO’yu iyileştirdi” denmez.
