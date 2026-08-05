# EBIS gerçekçilik tekrarı — pass 4/6

Tarih: 2026-07-30  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: bir adet bounded, kanıt-temelli beton yüzeyi ve RFID fiziksel
temas/örtülme iyileştirme turu.

## Sonuç

Bu turda sıfırdan açılan, zamana ve makineye yayılmış gerçek piksellerin
en büyük ortak bulgusu, beton yüzeyinin tek bir “hasar miktarı” ile
temsil edilememesiydi. Gerçekte düzenli silindir ve küpler korunurken
yüzeyler temiz kalıp derisi, yoğun casting pore, aşınmış kenar ve ağır
spall arasında kategorik olarak değişiyor. IR/non-LED görüntüler bu
bulgunun yalnız RGB ışık veya renk yanılgısı olmadığını; numune formu,
tabla teması ve kenar topolojisinin zaman boyunca korunduğunu gösterdi.

Blender ve Unreal'a ortak, konfigüre edilebilir bir sözleşme taşındı:

- `clean_cast`, `pitted`, `edge_worn`, `spalled` yüzey rejimleri;
- küp ve silindir için ayrı fakat açıkça **geçici** ağırlıklar;
- ana kamera/ışık/RFID kararını kaydırmayan bağımsız deterministik yüzey
  RNG'si;
- `0,7–4,5 mm` görsel-fit bounded edge relief;
- her kare metadata'sında rejim, profil, relief sayısı/boyu ve
  “prevalans ölçülmedi” durumu;
- eksik, yanlış veya config dışı rejimi hard-fail yapan validator.

Unreal'da ayrıca gerçek pikselde en yüksek negatif ipucu veren iki fizik
sorunu düzeltildi:

- dışarı taşan gözenek küreleri reddedilip ince tangent koyu disklere
  çevrildi;
- silindir RFID film/copper/chip'i tek düz kart yerine 16 parçalı
  yüzeye-konforme yay oldu; küp tag parçaları ortak yerel eksen taşıdı;
- tabla arası tag'in uzun ekseni boşluğa girdi ve görünür uç
  `micro / partial / major` rejimi metadata/validator'a bağlandı;
- label threshold'u gevşetilmedi. İlk `8/8 exclude` sonucu fiziksel state
  dağılımını düzeltmek için kullanıldı; finalde hâlâ `5/8 exclude` var ve
  bu pilot production karışımı sayılmıyor.

RTX 3090'da sekizer final kare üretildi. İki bağımsız validator PASS
verdi, actual pixels tam çözünürlükte açıldı. Önce 18 core
source/config/generated-content/artefakt, teslim belgeleri eklendikten
sonra toplam 29 seçili dosya için yerel/3090 SHA-256 değeri eşleşti.

Bu sonuç fotogrammetri/PBR scan, CAD, ölçülmüş kamera/ışık veya model
faydası değildir. Unreal'ın düşük frekanslı bulutlu beton ve coarse
cabinet/press geometrisi, Blender'ın fazla sakin/temiz beton kenarı ve
iki engine'in gerçek düzensiz pore/aggregate kuyruğu hâlâ açıktır.
Fotogerçekçi dijital ikiz, engine üstünlüğü veya YOLO kazancı iddia
edilmez.

## Sıfırdan yeniden incelenen referans pikselleri

Önceki pass seçimlerine güvenilmeden yeni örneklem açıldı:

- [16 LED RGB kare](reports/qc/multi_repeat_pass4_led_fresh.png):
  `LED_RFIDTAG_230126` içindeki task 9–14 dizileri, 2026-01-21,
  cam-10 + cam-11; temiz/pitted silindir, clean/edge-worn/spalled küp,
  basılı form, görünür/kısmi RFID ve farklı temas durumları;
- [16 IR/non-LED gri kare](reports/qc/multi_repeat_pass4_ir_fresh.png):
  sekiz farklı makine×kamera grubu, 2024-12-02–2025-02-21;
- [referans + iki final engine actual-pixel sheet'i](reports/qc/multi_repeat_pass4_reference_blender_unreal.png).

IR kareler renk, exposure, roughness veya ışık şiddeti fit etmek için
kullanılmadı. Değişmeyen kapalı kutu, iki büyük dairesel tabla, düzenli
küp/silindir, temas kenarı, kapı/açıklık ve küçük fisheye kamera formunu
ayırmak için kullanıldı.

Tam çözünürlükte tekrar açılan iki temsilî gerçek kaynak:

- [cam-10 silindir](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00000.png):
  farklı boyda düzensiz koyu casting pore, kalıp derisi ve lokal LED
  highlight;
- [cam-11 küp](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_11_dataset_2026_01_23_07_32_53_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-6_frame-00000.png):
  düz ana yüz, çatlak, kırık üst/yan kenar, agrega ve temas artığı.

Referanslar her numunenin ağır hasarlı olduğunu söylemez. Rejimler
çeşitliliği kapsar; config ağırlıkları tam korpus prevalansının yerini
tutmaz.

## Uygulanan değişiklikler

### Blender

[`generate_ebis.py`](ebis-blender/scripts/generate_ebis.py) v1.7.7 ve
[`ebis_led_v2.json`](ebis-blender/configs/ebis_led_v2.json):

- şekle bağlı dört kategorik yüzey rejimi;
- rejime bağlı relief sayısı:
  `clean 0–1`, `pitted 2–5`, `edge_worn 6–10`, `spalled 10–16`;
- `0,0007–0,0045 m` relief sınırı;
- kamera, ışık, kapı ve RFID RNG akışını koruyan ayrı `surface_rng`;
- nominal beton ölçüsünü ve `concrete_sample` instance kimliğini
  değiştirmeyen, çoğunlukla yüzeye gömülü bounded relief;
- daha dengeli çok-ölçekli concrete shader frekans/bump ayarı;
- metadata ve validator'da rejim/profil/sayı/boy/status sözleşmesi;
- finalde `concrete_surface_regimes_checked=8`.

Kontrollü seed `54244` before/after tam çözünürlükte açıldı. Değişiklik
subtle kaldı; yüzeye yapışmış taş veya non-manifold siyah artefakt
üretilmedi. Bu bilinçli olarak scan benzeri ağır geometri iddiası değil,
güvenli bir baseline artışıdır.

### Unreal

[`ebis_scene.py`](unreal-ebis/Content/Python/ebis_scene.py),
[`ebis_unreal_v1.json`](unreal-ebis/configs/ebis_unreal_v1.json) ve
[`build_visible_bboxes.py`](unreal-ebis/scripts/build_visible_bboxes.py):

- Blender ile aynı dört rejim, ağırlık, relief sınırı, bağımsız RNG ve
  metadata/validator sözleşmesi;
- `M_ConcreteProceduralV14`: daha sınırlı low-frequency color contrast
  ve daha dengeli fine detail;
- ilk küresel gözenek proxy'si yerine yüzeye tangent, çok ince cylinder
  diskleri ve `M_ConcretePoreV3`;
- yüzeye yapıştırılan silindir tag'i için 16 segmentli conforming arc;
- film, copper wing ve chip'in aynı `EBIS_INSTANCE` ve aynı yerel
  normal/length eksenini kullanması;
- küp yüzünde ortak eksen takımı ve doğru copper-long-axis;
- tabla arası tag için boşluğa giren uzun eksen, seed modulo ile
  `major, partial, partial, micro` görünür uç seçimi;
- metadata'da contact model/profile, eksenler, segment sayısı,
  tip hedefi/rejimi;
- validator'da birim/ortogonal eksen, doğru contact model, segment sayısı,
  seed→tip rejimi ve aralık kontrolü;
- dört veya daha çok karede tamamının exclude olmasını hard-fail yapan
  dağılım kapısı.

Config'teki tag state listesi geçici olarak
`5/8 sample-attached, 2/8 plate-gap, 1/8 loose` yapıldı. Bu oran gerçek
korpusta ölçülmeden production kabulü değildir.

## Görsel regresyon ve reddedilen denemeler

Artefaktlar başarısız denemeyi gizlememek ve kabul kararını izlenebilir
tutmak için saklandı:

- Blender `realism_v5_5_surface_p4_diag_54244`: kontrollü aynı-seed
  surface tanısı; kabul edildi fakat tek kare release değildir.
- Unreal `realism_r9_surface_p4_diag_58444`: kenardaki proxy'ler iri,
  küresel ve beton üstüne yapışmış boncuk gibi; reddedildi.
- `realism_r9_surface_p4_diag2_58444`: boy/flatness iyileşti; final değil.
- `realism_r9_concrete_p4_58520`: sekiz kare teknik PASS olsa da
  silindir RFID'leri yüzeyden düz/floating; reddedildi.
- `realism_r10_tag_contact_p4_diag_58522`: tangent düz tag düzeldi ama
  uçları cylinder eğrisinden ayrıldı; reddedildi.
- `realism_r10_tag_contact_p4_diag2_58522`: 10 segmentli arc ilk başarılı
  contact tanısı; finalde 16 segmente çıkarıldı.
- `realism_r10_concrete_tag_p4_58520`: label threshold'larını
  gevşetmeden `8/8 exclude`; fiziksel state/tip dağılımı blocker olarak
  kabul edildi.
- r11/r12 bounded dağılım tanıları sırasıyla exclude sayısını azalttı;
  kalibrasyon lineage'ıdır.
- `realism_r13_concrete_tag_p4_58520`: contact/state ve label policy
  teknik PASS; tam çözünürlük clean-cast kare gözenek kürelerinin hâlâ
  boncuk gibi olduğunu gösterdi.
- `realism_r14_pore_disc_p4_diag_58526`: ince disk formu doğru, fakat
  fazla açık/polka-dot; reddedildi.
- `realism_r14_pore_disc_p4_diag2_58526`: koyu V3 aynı seed'de açıldı;
  dışarı taşan boncuk ipucu kayboldu. Sekiz-kare final için kabul edildi.
- `realism_r15_concrete_tag_p4_58520`: seçilen final pilot.

Hiçbir tanı koşusu production release veya model kazancı sayılmaz.

## Seçilen Blender pilotu

- Run:
  [`realism_v5_5_concrete_p4_54240`](ebis-blender/output/realism_v5_5_concrete_p4_54240).
- Görsel:
  [8-kare contact sheet](ebis-blender/reports/qc/realism_v5_5_concrete_p4_54240_contact_sheet.png),
  [cam-10/silindir](ebis-blender/output/realism_v5_5_concrete_p4_54240/partitions/hard_occlusion/images/ebis_camera_angled_054241.png)
  ve [cam-11/küp](ebis-blender/output/realism_v5_5_concrete_p4_54240/partitions/standard/images/ebis_camera_door_054244.png).
- Validator:
  [`PASS`](ebis-blender/output/realism_v5_5_concrete_p4_54240/validation.json);
  8/8 kare, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  21 fiziksel RFID, 37 binary maske ve 53 dosya hash kontrolü.
- Partition: `3 standard / 5 hard / 0 exclude`; hard kareler normal
  train'e otomatik karışmaz.
- Surface: `1 clean / 3 pitted / 4 edge_worn / 0 spalled`. Sekiz seed'in
  rejim kapsaması distribution kanıtı değildir.
- Render: Blender 4.5.12 LTS, RTX 3090 OptiX, `1280×720`, 64 spp,
  depth kapalı; toplam `48,385 s`, ortalama `6,048 s/kare`.
- Kaynak SHA-256:
  `generate_ebis.py = d56e24a1…9ff7`,
  raw config `89701d54…1125`,
  canonical config `15d52234…56fd`.
- Pin:
  [release manifest](ebis-blender/evidence/release/realism_v5_5_concrete_p4_54240_manifest.json).

## Seçilen Unreal pilotu

- Run:
  [`realism_r15_concrete_tag_p4_58520`](unreal-ebis/output/realism_r15_concrete_tag_p4_58520).
- Görsel:
  [8-kare contact sheet](unreal-ebis/reports/qc/assets/realism_r15_concrete_tag_p4_58520_contact_sheet.png),
  [cam-10/silindir](unreal-ebis/output/realism_r15_concrete_tag_p4_58520/raw/images/ebis_camera_angled_058523.png),
  [cam-11/küp](unreal-ebis/output/realism_r15_concrete_tag_p4_58520/raw/images/ebis_camera_door_058524.png)
  ve [cam-11/pore tanı seed'i](unreal-ebis/output/realism_r15_concrete_tag_p4_58520/raw/images/ebis_camera_door_058526.png).
- Validator:
  [`PASS`](unreal-ebis/output/realism_r15_concrete_tag_p4_58520/validation.json);
  8/8 kare, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  36 visible + 36 amodal maske.
- Partition: `3 standard / 0 hard / 5 exclude`. Majority-exclude sonucu
  politika tarafından korunur; bu pilot doğrudan train karışımı değildir.
- Surface: `1 clean / 4 pitted / 1 edge_worn / 2 spalled`;
  sekiz rejim kontrolü.
- RFID contact: `11 cylinder-conformed`, `7 planar-sample`,
  `7 plate-gap-tip`, `3 loose`; 28 model kontrolü.
- Tip: `1 major / 4 partial / 2 micro`; seed/rejim/aralık kontrolü PASS.
- Dört camera×shape concrete bbox hücresi `N=2`; gerçek hedefe en büyük
  mutlak fark `0,05756`, yani mevcut `abs ≤0,06` görsel kapısında.
- Engine: UE 5.8.1 / RTX 3090, `1280×720`, depth kapalı;
  engine batch süresi `34,545 s`.
- RGB sensor manifest:
  [`PASS`](unreal-ebis/output/realism_r15_concrete_tag_p4_58520/raw/sensor_response_manifest.json);
  geometri, mask ve depth değiştirilmedi.
- Kaynak SHA-256:
  `ebis_scene.py = f705150e…b469`,
  config `a992350b…0273`,
  validator `013189d0…f31`.
- Generated content:
  `EBIS_Press.umap = ffca108d…9dc3`,
  `M_ConcreteProceduralV14 = 61b9be6f…b84a`,
  `M_ConcretePoreV3 = 9f5fa579…ff1`.
- Pin:
  [release manifest](unreal-ebis/evidence/release/realism_r15_concrete_tag_p4_58520_manifest.json).

## Gerçek piksel kontrolü

Makine-okunur audit:
[`multi_repeat_pass4_pixel_audit.json`](reports/qc/multi_repeat_pass4_pixel_audit.json).
ROI'ler full-resolution pikseller açıldıktan sonra elle seçilen sample
yüz bölgeleridir. Görüşler register değildir; çözünürlük, kamera,
exposure, sharpening, compression ve Unreal sensor-noise farklıdır.
Değerler kalite skoru değildir.

| Yüzey ROI | L mean / std | Mean gradient | Edge `≈≥0,04` | 2 px high-pass |
| --- | ---: | ---: | ---: | ---: |
| Gerçek LED cam-10 cylinder | `0,635 / 0,161` | `0,01249` | `0,05528` | `0,01484` |
| Gerçek LED cam-11 cube | `0,518 / 0,082` | `0,00525` | `0,02820` | `0,00776` |
| Blender p3 same-seed cube | `0,697 / 0,045` | `0,00401` | `0,00057` | `0,00318` |
| Blender p4 same-seed cube | `0,688 / 0,045` | `0,00432` | `0,00055` | `0,00352` |
| Unreal r13 same-seed cylinder | `0,670 / 0,130` | `0,00751` | `0,00571` | `0,00562` |
| Unreal r15 same-seed cylinder | `0,669 / 0,131` | `0,00750` | `0,00465` | `0,00595` |

Kontrollü before/after:

- Blender mean absolute RGB farkı `0,00995`; kanalların `%46,942`'si
  iki seviyeden fazla değişti. Değişim yaygın fakat küçüktür.
- Unreal mean absolute RGB farkı `0,00135`; kanalların yalnız `%0,849`'u
  iki seviyeden fazla değişti. Değişim amaçlandığı gibi lokal pore
  proxy'sidir.

Tam çözünürlük incelemesinin kararı:

- Blender yüzeyi tutarlı ve daha sakin; gerçek cube/cylinder'ın sparse
  yüksek-kontrast pore, chip, crack ve aggregate kuyruğu yok.
- Unreal'ın dışarı taşan pore boncuğu düzeldi ve conforming RFID açık
  kazançtır; concrete low-frequency bulutlanma, kusursuz dairesel
  proxy'ler, coarse cabinet/press geometri, aşırı düz yüzler ve sert
  global ışık hâlâ kuvvetli CG ipucudur.
- Unreal post-sensor noise gradient'i artırır; yüksek gradient tek başına
  daha gerçek materyal demek değildir.

Bu değerler değişikliğin piksele yansıdığını gösterir; fotogerçekçilik,
engine sıralaması veya YOLO faydası göstermez.

## Motorlar arası taşınan sözleşme

İki engine'de ortak:

- aynı dört kategori ve shape-conditioned geçici ağırlık;
- aynı relief count/size bounds;
- bağımsız deterministik yüzey RNG;
- aynı metadata status metni ve validator hard-gate;
- nominal sample geometrisi ile semantic instance kimliğini koruma;
- bilinmeyen dağılımı sahte kesinlik yerine bounded augmentation yapma.

Blender'ın daha sakin çok-ölçekli concrete görünümü Unreal V14
frekans/kontrastını sınırlandırdı. Unreal actual-pixel denemesi de
Blender'a şu geri bildirimi verdi: gözenek/aggregate primitive sayısını
artırmak gerçekçilik değildir; cavity/scan olmadan geometri proxy'si
küçük ve gömülü kalmalıdır. Unreal'ın silindir contact ekseni ve visible
tip-regime sözleşmesi `lessons_learned.md` ile Blender'ın sonraki fiziksel
RFID turuna aktarıldı; bu turda Blender tag geometrisi yeniden
yazılmadı.

Bu aktarım görsel eşitlik veya engine benchmark'ı değildir. Render
süreleri eşit renderer/pass/annotation workload'u taşımadığı için hız
sıralaması çıkarılamaz.

## Yeniden üretim ve doğrulama komutları

Blender final:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action batch --seed 54240 --count 8 \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_5_concrete_p4_54240 \
  --resolution 1280x720 --samples 64 --no-depth'
```

Blender bağımsız yeniden doğrulama:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action validate \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_5_concrete_p4_54240 \
  --expected-count 8 --require-both-cameras'
```

Unreal final ve bağımsız yerel annotation validator:

```bash
ssh 3090 'cd /home/ankaref/Documents/Projects/simulation/unreal-ebis && \
  ./scripts/run_remote_release.sh realism_r15_concrete_tag_p4_58520 \
  8 58520 1280 720 0'

python3 unreal-ebis/scripts/build_visible_bboxes.py \
  --root unreal-ebis/output/realism_r15_concrete_tag_p4_58520 \
  --config unreal-ebis/configs/ebis_unreal_v1.json
```

Static sözleşme:

```bash
python3 -m py_compile \
  ebis-blender/scripts/generate_ebis.py \
  unreal-ebis/Content/Python/ebis_scene.py \
  unreal-ebis/scripts/build_visible_bboxes.py \
  unreal-ebis/scripts/run_unreal_batch.py \
  unreal-ebis/scripts/apply_sensor_response.py \
  unreal-ebis/scripts/create_qc_contact_sheet.py

python3 -m json.tool ebis-blender/configs/ebis_led_v2.json
python3 -m json.tool unreal-ebis/configs/ebis_unreal_v1.json
```

İki validator tekrar çalıştırıldı. Önce 18 core source/config,
generated-content, run-manifest, validation, contact sheet, engine log ve
temsilî kare; teslim raporu/manifest/sheet'leri eklendikten sonra toplam
29 seçili dosya için yerel ile
`/home/ankaref/Documents/Projects/simulation` SHA-256 karşılaştırması
`FINAL_LOCAL_REMOTE_SHA256_PARITY_OK files=29` verdi.

## Kalan materyal ve kanıt açıkları

Öncelik sırasıyla:

1. Aynı gerçek clean/pitted/edge-worn/spalled cube ve cylinder için
   lisanslı photogrammetry veya tileable albedo/normal/roughness/height
   capture. Mevcut relief ve diskler scan/cavity değildir.
2. Cam-10/cam-11 ChArUco intrinsics/distortion ile aynı exposure
   grey-card, empty-chamber ve steel-platen referansı. Fisheye/pose ve
   photometric response hâlâ visual-fit'tir.
3. Gerçek CAD veya en azından iç panel/tabla/kapı/access-cover ölçüm seti.
   Unreal coarse primitive/top-plate silhouette'i en güçlü global CG
   ipucudur.
4. Blender'da gerçek chip/spall silüeti, kenar normal sürekliliği,
   silindire-konforme kağıt/RFID ve gerçek alt tabla debris dağılımı.
5. Unreal'da true cavity/height mesh veya scan, low-frequency concrete
   cloud düzeltmesi, cabinet bevel/conta/kapak derinliği ve cam-11
   photometric lighting.
6. PII temizlenmiş gerçek basılı form/kağıt atlası ve fiziksel
   wrinkle/adhesive davranışı.
7. Güncel source hash'leriyle depth, BlenderMCP, Unreal MCP, aynı-seed
   determinism ve en az 32-kare düşük maliyetli distribution gate.
8. 100-kare kör iki-person RGB/annotation QC. Unreal'daki `5/8 exclude`
   state dağılımı gerçek korpusa göre ölçülmeden büyütülmemeli.

## Sonraki en yüksek değerli refinement

Bir sonraki en yüksek değer yeni procedural noise eklemek değil,
**aynı gerçek numune ve aynı görüş için ölçülü materyal/kamera
kalibrasyon paketi** üretmektir:

1. clean/pitted/edge-worn/spalled küp ve silindirin ön/yan/üst temas
   yüzünü diffuse ve cross-polarized ışıkla çekin;
2. ölçek cetveli ve grey-card ekleyin;
3. cam-10/cam-11 intrinsics/distortion'u ChArUco ile çözün;
4. mümkünse her kategori için albedo/normal/roughness/height veya
   photogrammetry mesh çıkarın;
5. aynı kamera/pose/exposure ile Blender ve Unreal'ı register ederek
   yüzey power/gradient/edge ölçümü yapın.

Bu paket gelmezse bir sonraki bounded tur, gerçek prevalansı en az
etiketleyip Unreal low-frequency cloud ve Blender sparse edge tail'i
ayrı ayrı düzeltmeli; yeni primitive sayısını kör artırmamalıdır.

YOLO kabul kapısı değişmedi: frozen gerçek train/val/test ayrımı, en küçük
model ve en az üç seed ile `R`, `R+B-1N`, `R+U-1N`; gerekirse
`R+B+U-1N`. Normal sentetik kola yalnız `standard`, açık adlı ablation'a
`hard`, hiçbir kola `exclude` girer. Küçük/örtülü RFID slice recall,
concrete AP ve gerçek-test güven aralığı artmadan bu görsel değişiklik
model faydası sayılmaz.
