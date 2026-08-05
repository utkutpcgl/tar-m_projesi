# EBIS gerçekçilik tekrarı — pass 5/6

Tarih: 2026-07-30  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: bir adet bounded, kanıt-temelli alt used-steel tabla ve görünür
debris fizik düzeltme turu.

## Sonuç

Bu turda zamana, makineye ve kameraya yayılan gerçek pikseller sıfırdan
yeniden açıldı. Task 9–14'ten 18 LED RGB kare ve mevcut **18 REF
makine×kamera grubunun tamamından** birer IR/non-LED gri kare incelendi.
İki engine'in en büyük ortak lokal açığı alt temas tablasıydı: gerçek
makinedeki koyu, kullanılmış, radyal aşınmalı ve artık taşıyan çelik
yerine fazla temiz/parlak beyaz bir yüz görünüyordu.

Blender ve Unreal'a gövdeden ayrı, ince bir `lower_contact_face` ve üç
bounded yüzey rejimi taşındı:

- `dry_used`
- `dusty_used`
- `damp_residue`

Profil seçimi bağımsız deterministik RNG kullanır. Böylece aynı seed'de
kamera, kapı, numune, RFID ve ışık kararı değişmeden yalnız hedef yüzey
karşılaştırılabilir. Her karede profil, çap, kalınlık, üst kot,
sample-gap ve belirsizlik durumu metadata'ya yazılır; validator eksik,
ölçüsüz veya config dışı sözleşmeyi hard-fail eder.

Unreal'da ayrıca somut bir fizik hatası giderildi: 32 debris actor'ı
`z=7,0–9,6 cm` aralığında oluşturulurken alt tabla üstü `z=23,55 cm`
idi. Debris görünür yüzün altındaydı. Tarihsel z random draw'u yine
tüketilip sonuç gerçek tabla üstüne remap edildi; böylece downstream
numune/tag RNG sırası korundu. Radyal yerleşim tabla yarıçapının
`0,48–0,91` aralığına sınırlandı ve santimetre-ölçekli dekor taşı kuyruğu
yalnız iki nadir büyük chip olacak şekilde küçültüldü.

RTX 3090'da iki engine için sekizer final kare üretildi. İki bağımsız
validator PASS verdi ve final pikseller tam çözünürlükte açıldı. Bu
sonuç:

- fotogrammetri veya ölçülmüş BRDF,
- CAD veya ölçülmüş kamera/ışık,
- production dataset onayı,
- engine üstünlüğü,
- YOLO faydası

değildir. Depth ve güncel BlenderMCP/Unreal MCP bu turda çalıştırılmadı;
önceki turların kanıtı yeni source hash'lerine mal edilmez.

## Sıfırdan incelenen referans pikselleri

Yeni referans sheet'leri:

- [18 LED RGB kare](reports/qc/multi_repeat_pass5_led_fresh.png):
  task 9–14, 2026-01-21, cam-10 ve cam-11; küp/silindir, değişken kapı,
  basılı kâğıt, kısmi RFID, kuru/tozlu/nemli temas durumları;
- [18 IR/non-LED gri kare](reports/qc/multi_repeat_pass5_ir_fresh.png):
  `REF-*` altındaki her makine×kamera grubundan bir kare;
- [referans + Blender + Unreal final actual-pixel sheet'i](reports/qc/multi_repeat_pass5_reference_blender_unreal.png).

Tam çözünürlükte sayısal audit için açılan iki gerçek kaynak:

- [LED cam-10 alt tabla](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00075.png)
- [IR cam-11 boş/az örtülü tabla](260312_EBIS_RFID_DATASET/REF-65553_CAM11/images/train/ASBET_REF-65553_2025-01-24_cam-11_frame-038829.png)

IR veri yalnız sabit disk geometrisi, radyal aşınma/kalıntı, debris ve
lokal yansıma yapısını ayırmak için kullanıldı. IR luminance, RGB albedo,
roughness veya exposure hedefi değildir.

Gözlenen ortak yapı:

- alt disk homojen beyaz veya düz siyah değil;
- koyu kullanılmış çelik üstünde geniş düşük-frekanslı artık alanı var;
- dar/radyal sürtünme izleri ve dairesel temas izi bulunuyor;
- concrete dust ve bazı karelerde nemli/koyu kalıntı birlikte görülüyor;
- lokal LED/specular yansıma koyu yüzü yer yer çok parlak yapabiliyor;
- ufak chips ve kırıntı var, fakat yüzey dekor taşı yatağı değil.

## Uygulanan değişiklikler

### Blender v1.7.8

[`generate_ebis.py`](ebis-blender/scripts/generate_ebis.py) ve
[`ebis_led_v2.json`](ebis-blender/configs/ebis_led_v2.json):

- tabla gövdesinden ayrı `Lower platen used contact face`;
- geçici visual-fit ölçüleri:
  - çap `0,394 m`,
  - kalınlık `0,0008 m`,
  - üst kot `0,241 m`,
  - nominal specimen contact gap `0`;
- ağırlıkları `0,46 / 0,34 / 0,20` olan dry/dusty/damp profilleri;
- her profil için ayrı procedural PBR materyal;
- ana sahne RNG'sinden bağımsız `lower_contact_rng`;
- config validation, scene contract, per-frame metadata ve dataset
  validator hard-gate;
- final validator sonucu:
  `lower_contact_faces_checked=8`,
  `5 dry_used / 2 dusty_used / 1 damp_residue`.

İlk aynı-seed tanı
`realism_v5_6_lower_platen_p5_diag_54241` tam çözünürlükte açıldı.
`dusty_used` fazla açık/renkli okundu; mean response azaltıldı.
`realism_v5_6_lower_platen_p5_diag2_54241` kontrollü tekrarından sonra
sekiz-kare final kabul edildi.

### Unreal r16

[`ebis_scene.py`](unreal-ebis/Content/Python/ebis_scene.py),
[`ebis_unreal_v1.json`](unreal-ebis/configs/ebis_unreal_v1.json) ve
[`build_visible_bboxes.py`](unreal-ebis/scripts/build_visible_bboxes.py):

- physical revision
  `lower_used_platen_contact_pass5_2026-07-30`;
- gövdeden ayrı `39,4 cm × 0,08 cm` alt contact face;
- üst kot `23,55 cm`, nominal sample-gap `0`;
- Blender ile aynı profil adları/ağırlıkları ve bağımsız RNG;
- versiyonlu generated materyaller:
  - `M_LowerContactDryUsedV1`,
  - `M_LowerContactDustyUsedV2`,
  - `M_LowerContactDampResidueV1`;
- metadata ve validator'da profil/geometri/status kapıları;
- debris z remap, bounded radial range ve küçültülmüş size tail;
- eski random draw sayısını koruyarak downstream kontrollü same-seed
  kararlarını yerinde tutma;
- final validator sonucu:
  `lower_contact_faces_checked=8`,
  `4 dry_used / 1 dusty_used / 3 damp_residue`.

İlk aynı-seed tanı
`realism_r16_lower_platen_p5_diag_58523` actual pixels'te fazla
açık/sepia dusty yüz gösterdi. Yeni `M_LowerContactDustyUsedV2` ile
`realism_r16_lower_platen_p5_diag2_58523` üretildi; final batch bundan
sonra seçildi.

## Seçilen Blender pilotu

- Run:
  [`realism_v5_6_lower_platen_p5_54240`](ebis-blender/output/realism_v5_6_lower_platen_p5_54240)
- Görsel:
  [8-kare contact sheet](ebis-blender/reports/qc/realism_v5_6_lower_platen_p5_54240_contact_sheet.png),
  [cam-10/silindir](ebis-blender/output/realism_v5_6_lower_platen_p5_54240/partitions/hard_occlusion/images/ebis_camera_angled_054241.png) ve
  [cam-11/küp](ebis-blender/output/realism_v5_6_lower_platen_p5_54240/partitions/standard/images/ebis_camera_door_054244.png)
- Validator:
  [`PASS`](ebis-blender/output/realism_v5_6_lower_platen_p5_54240/validation.json)
- Kapsam:
  `8/8`, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  21 fiziksel RFID, 37 binary maske, 53 hash kontrolü
- Partition:
  `3 standard / 5 hard_occlusion / 0 exclude`
- Alt temas profili:
  `5 dry / 2 dusty / 1 damp`
- Render:
  Blender 4.5.12 LTS, RTX 3090 OptiX, `1280×720`, 64 spp,
  depth kapalı; toplam `46,0524 s`, ortalama `5,7566 s/kare`
- Kaynak SHA-256:
  `generate_ebis.py = 9614c4e0…5d42`,
  raw config `5a755b0b…53e`,
  canonical config `b8e00fa5…ae95`
- Pin:
  [release manifest](ebis-blender/evidence/release/realism_v5_6_lower_platen_p5_54240_manifest.json)

## Seçilen Unreal pilotu

- Run:
  [`realism_r16_lower_platen_p5_58520`](unreal-ebis/output/realism_r16_lower_platen_p5_58520)
- Görsel:
  [8-kare contact sheet](unreal-ebis/reports/qc/assets/realism_r16_lower_platen_p5_58520_contact_sheet.png),
  [cam-10/silindir](unreal-ebis/output/realism_r16_lower_platen_p5_58520/raw/images/ebis_camera_angled_058523.png) ve
  [cam-11/küp](unreal-ebis/output/realism_r16_lower_platen_p5_58520/raw/images/ebis_camera_door_058524.png)
- Validator:
  [`PASS`](unreal-ebis/output/realism_r16_lower_platen_p5_58520/validation.json)
- Kapsam:
  `8/8`, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  36 visible + 36 amodal instance mask
- Partition:
  `3 standard / 0 hard / 5 exclude`; çoğunluk-exclude label
  politikasının beklenen sonucu, production karışımı değil
- Alt temas profili:
  `4 dry / 1 dusty / 3 damp`
- RFID:
  28 contact model kontrolü
- Bbox:
  dört camera×shape concrete hücresi, hücre başına `N=2`,
  hedefe mutlak fark `≤0,06`
- Engine:
  UE 5.8.1 / RTX 3090, `1280×720`, depth kapalı;
  engine batch `40,194 s`
- RGB sensor manifest:
  [`PASS`](unreal-ebis/output/realism_r16_lower_platen_p5_58520/raw/sensor_response_manifest.json);
  geometri, mask ve depth değiştirilmedi
- Generated content:
  `EBIS_Press.umap = 8aeb9cbd…a9fa`,
  `M_LowerContactDryUsedV1 = b7e9e006…3fa6`,
  `M_LowerContactDustyUsedV2 = 5ee8e64b…896`,
  `M_LowerContactDampResidueV1 = d9c760db…9da`
- Pin:
  [release manifest](unreal-ebis/evidence/release/realism_r16_lower_platen_p5_58520_manifest.json)

## Gerçek piksel kontrolü

Makine-okunur audit:
[`multi_repeat_pass5_pixel_audit.json`](reports/qc/multi_repeat_pass5_pixel_audit.json).
ROI'ler pikseller tam çözünürlükte açıldıktan sonra elle seçildi.
Görüşler register değildir; kamera, crop, exposure, sensor response,
compression ve contamination değişir. Değerler kalite skoru değildir.

| Alt tabla ROI | Mean RGB | L mean / std | Mean gradient | 2 px high-pass |
| --- | ---: | ---: | ---: | ---: |
| Gerçek LED cam-10 koyu sektör | `[70,70,82]` | `0,28091 / 0,14151` | `0,02454` | `0,02932` |
| Gerçek IR cam-11, yapı için | `[113,113,113]` | `0,44411 / 0,25886` | `0,02643` | `0,03396` |
| Blender p4 same-seed | `[126,118,110]` | `0,46876 / 0,10691` | `0,00652` | `0,00723` |
| Blender p5 same-seed | `[98,88,81]` | `0,35375 / 0,07938` | `0,00577` | `0,00655` |
| Unreal p4 same-seed | `[191,175,154]` | `0,69558 / 0,14541` | `0,02338` | `0,01973` |
| Unreal p5 same-seed | `[130,108,80]` | `0,43590 / 0,09432` | `0,04042` | `0,03443` |

Kontrollü before/after:

- Blender tam-kare mean absolute RGB farkı `0,01994`; kanalların
  `%13,399`'u iki seviyeden fazla değişti.
- Unreal tam-kare mean absolute RGB farkı `0,03845`; kanalların
  `%9,237`'si iki seviyeden fazla değişti.

Karar:

- iki motorda eski temiz/beyaz alt disk cue'su materyal olarak azaldı;
- Blender hâlâ gerçek radyal aşınma, sparse debris ve residue kuyruğundan
  daha sakin/düz;
- Unreal hâlâ sepia ve geometrik olarak kaba; high-pass'in gerçek seçili
  ROI'yi hafif aşması sensor noise + material speckle over-texturing
  riski;
- IR median `0,38039`, p90 `0,89804`: koyu kullanılmış yüz ile güçlü
  lokal highlight'ın birlikte olması destekleniyor;
- gerçek üst tabla, fisheye/camera response ve concrete pore/crack tail,
  alt tablayı daha da keyfî karartmaktan daha büyük kalan açıklardır.

Bu değerler hedef düzeltmenin piksele yansıdığını gösterir;
fotogerçekçilik, engine sıralaması veya YOLO faydası göstermez.

## Motorlar arası taşınan sözleşme

İki engine'de ortak:

- gövdeden ayrı alt contact face;
- aynı `dry_used / dusty_used / damp_residue` profil adları ve geçici
  ağırlıklar;
- aynı nominal çap, çok ince görsel-fit yüz ve sıfır sample-gap;
- ana sahne kararlarını kaydırmayan bağımsız RNG;
- aynı per-frame metadata ve validator hard-gate;
- profil prevalansını “ölçülmedi” olarak saklayan status;
- legacy config'te deterministic fallback.

Unreal'daki z bug'ı Blender için doğrudan ders oldu: dekor/debris
actor'ının varlığı değil, temas yüzüyle dünya-kotu ilişkisi validator
kontratına girmelidir. Blender'ın daha sakin yanıtı da Unreal'daki dusty
materyalin ikinci versiyonda koyulaştırılıp nötrleştirilmesine yardım
etti. Buna karşılık Unreal actual-pixel high-pass sonucu, Blender'a
procedural speckle'ı kör artırmaması gerektiğini gösterdi.

Bu aktarım görsel eşitlik veya engine benchmark'ı değildir. Blender ve
Unreal süreleri renderer, pass ve annotation workload'u eşit olmadığı
için hız sıralaması yapılamaz.

## Yeniden üretim ve doğrulama komutları

Blender final:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action batch --seed 54240 --count 8 \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_6_lower_platen_p5_54240 \
  --resolution 1280x720 --samples 64 --no-depth'
```

Blender bağımsız doğrulama:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action validate \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_6_lower_platen_p5_54240 \
  --expected-count 8 --require-both-cameras'
```

Unreal final ve bağımsız annotation validator:

```bash
ssh 3090 'cd /home/ankaref/Documents/Projects/simulation/unreal-ebis && \
  ./scripts/run_remote_release.sh realism_r16_lower_platen_p5_58520 \
  8 58520 1280 720 0'

python3 unreal-ebis/scripts/build_visible_bboxes.py \
  --root unreal-ebis/output/realism_r16_lower_platen_p5_58520 \
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
python3 -m json.tool reports/qc/multi_repeat_pass5_pixel_audit.json
```

Bu komutlara ek olarak iki release manifestindeki 24 source,
generated-content ve artefakt hash'i mevcut dosyalardan yeniden
hesaplandı; tamamı eşleşti. Altı teslim Markdown dosyasındaki 158 yerel
link varlık kontrolünden geçti. Kaynaklar, config'ler, generated Unreal
asset'leri, final manifest/validation'lar, seçili pikseller, QC
sheet'leri ve bu teslim raporu dahil 33 seçili dosyanın yerel ile
`/home/ankaref/Documents/Projects/simulation` SHA-256 değeri
`FINAL_LOCAL_REMOTE_SHA256_PARITY_OK files=33` verdi.

## Kalan materyal ve kanıt açıkları

Öncelik sırasıyla:

1. Cam-10/cam-11 için ChArUco intrinsics/distortion, aynı exposure
   grey-card, empty-chamber ve gerçek steel-platen capture. Fisheye ve
   fotometrik response hâlâ visual-fit.
2. Aynı temiz/tozlu/nemli alt ve üst tabla sektörünün diffuse +
   cross-polarized albedo/roughness/normal/height veya lisanslı
   tileable/scan paketi. Üç procedural rejim ölçülmüş BRDF değil.
3. Gerçek CAD veya iç panel, tabla, kapı, conta ve access cover ölçüleri.
   Özellikle Unreal'ın coarse silhouette/geometri açığı büyük.
4. Aynı gerçek clean/pitted/edge-worn/spalled küp ve silindirin
   photogrammetry/PBR capture'ı; gerçek concrete pore/crack/aggregate
   tail iki engine'de de eksik.
5. Blender'da bounded radial wear/residue/debris placement ve
   cylinder-conforming kâğıt/RFID; Unreal'da sepia sensor fit,
   low-frequency concrete cloud ve aşırı speckle.
6. PII temizlenmiş gerçek basılı kâğıt/form atlası, wrinkle/adhesive ve
   kısmen kâğıt altında kalan tag capture'ı.
7. Güncel source hash'leriyle depth, BlenderMCP, Unreal MCP, same-seed
   determinism ve en az 32-kare distribution gate.
8. 100-kare kör iki-person RGB/annotation QC. Unreal'daki `5/8 exclude`
   gerçek korpus state prevalansına göre ölçülmeden büyütülmemeli.

## Sonraki en yüksek değerli refinement

Bir sonraki tur için en yüksek değer, yeni procedural noise eklemek
değil **kamera-kayıtlı materyal capture paketi**dir:

1. cam-10 ve cam-11 ile empty-chamber, yalnız alt tabla, yalnız üst
   tabla, küp ve silindir durumlarını aynı exposure'da çekin;
2. her çekimde grey-card/ColorChecker ve ölçek cetveli kullanın;
3. ChArUco ile intrinsics ve lens distortion çözün;
4. temiz, kuru-tozlu ve nemli-artıklı tabla sektörlerini diffuse ve
   cross-polarized ışıkla yakalayın;
5. register edilmiş gerçek/sentetik çiftlerde exposure, radial wear,
   high-pass ve specular highlight dağılımını karşılaştırın;
6. sonra aynı source hash'leriyle 32-kare distribution/QC koşusu alın.

Bu paket gelmeden bounded pass gerekirse en güvenli hedef Blender'a
gerçek referanstan sınırlı radial residue/debris alanı eklemek ve
Unreal'ın dusty/noise high-pass'ini düşürmektir; alt yüzü keyfî
karartmak veya primitive sayısını artırmak değildir.

YOLO kabul kapısı değişmedi: frozen gerçek train/val/test ayrımı, en
küçük model ve en az üç seed ile `R`, `R+B-1N`, `R+U-1N`; gerekirse
`R+B+U-1N`. Normal sentetik kola yalnız `standard`, açık adlı ablation'a
`hard`, hiçbir kola `exclude` girer. Küçük/örtülü RFID slice recall,
concrete AP ve gerçek-test güven aralığı artmadan bu görsel değişiklik
model faydası sayılmaz.
