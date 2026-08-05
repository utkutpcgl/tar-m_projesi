# EBIS Blender handoff guide

## Görev sınırı ve doğru durum

Bu paket yalnız iki detection sınıfı üretir:

- `0 rfid_tag`
- `1 concrete_sample`

İnsan/el, AprilTag, RF UID/RSSI, beton dayanım fiziği ve gerçek kırılma
simülasyonu kapsam dışıdır. Gerçek LED setindeki person/domain farkı
YOLO raporunda açıkça tutulmalıdır.

Kanonik generator `scripts/generate_ebis.py` sürümü `v1.8.1`’dir.
Sahne, `REF-65218_IVEDIK_LED_TARGET` için reference-fit topoloji,
iki-camera bounded calibration ve instance-aware annotation sözleşmesi
taşır. Bu teknik durum:

- CAD doğruluğu,
- ölçülmüş lens/fisheye kalibrasyonu,
- production fotogerçekçiliği,
- sentetik verinin YOLO metriğine katkısı

anlamına gelmez.

Kanonik teknik pin
[`realism_v8_cast_pores_release_60100/validation.json`](../output/realism_v8_cast_pores_release_60100/validation.json),
güncel MCP pini
[`pins_v1_8_1.json`](../evidence/mcp/pins_v1_8_1.json), son actual-pixel karar
kaydı ise
[`EBIS_REALISM_V2_PASS1_2026-07-30.md`](../../reports/qc/EBIS_REALISM_V2_PASS1_2026-07-30.md)
dosyasıdır. Son pilot 12/12 validator ve current-source BlenderMCP `PASS`
almıştır; üst yük izleri dahil bütün materyal değerleri ölçüm gelene kadar
bounded fallback'tir.

## Kanonik ve compute çalışma alanları

- Local source of truth:
  `/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/ebis-blender`
- RTX 3090 compute mirror:
  `/home/ankaref/Documents/Projects/simulation/ebis-blender`
- Blender 4.5.12:
  `/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender`
- Gerçek LED veri, paket dışında:
  `/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli`

Remote çalışma klasörünü local köke körlemesine geri mirror etmeyin.
Scratch, probe ve yarım renderlar kanonik pakete karışmamalıdır.

## Güvenli ve doğrudan rsync

Değişkenleri local shell’de tanımlayın:

```bash
export EBIS_LOCAL=/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/ebis-blender
export EBIS_REMOTE=/home/ankaref/Documents/Projects/simulation/ebis-blender
export BLENDER_REMOTE=/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender
```

Önce dry-run, ardından aynı trailing-slash köklerle gerçek kopya:

```bash
rsync -anic -s --delay-updates --safe-links \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='output/' --exclude='.rsync-partial/' \
  "$EBIS_LOCAL/" "3090:$EBIS_REMOTE/"

rsync -aic -s --delay-updates --safe-links \
  --partial-dir=.rsync-partial \
  --exclude='__pycache__/' --exclude='*.pyc' --exclude='*.pyo' \
  --exclude='output/' --exclude='.rsync-partial/' \
  "$EBIS_LOCAL/" "3090:$EBIS_REMOTE/"
```

Yalnız generator ve config göndermek daha emniyetliyse doğrudan dosya
hedefleri kullanın:

```bash
rsync -aic -s \
  "$EBIS_LOCAL/scripts/generate_ebis.py" \
  "3090:$EBIS_REMOTE/scripts/generate_ebis.py"

rsync -aic -s \
  "$EBIS_LOCAL/configs/ebis_led_v2.json" \
  "3090:$EBIS_REMOTE/configs/ebis_led_v2.json"
```

Bir remote run’ı local’e almak için hedef klasörü açıkça oluşturun:

```bash
run_name=reference_fit_pilot_63000
mkdir -p "$EBIS_LOCAL/output/$run_name"
rsync -aic -s --partial-dir=.rsync-partial \
  "3090:$EBIS_REMOTE/output/$run_name/" \
  "$EBIS_LOCAL/output/$run_name/"
```

`--relative`, `.../ebis-blender/./...`, unresolved remote glob,
`--delete`, `--delete-excluded` ve `--copy-links` kullanmayın.
`--relative` daha önce hedef altında nested
`ebis-blender/.../ebis-blender/...` riski yaratmıştır; bu guide’daki
komutlar direct source → direct destination kullanır.

## Ana dosyalar

- `configs/ebis_led_v2.json`: hedef profil, ölçü fallback’leri,
  iki-camera aralıkları, lighting, domain randomization ve annotation
  policy.
- `scripts/generate_ebis.py`: build/render/batch/validate ve tek sahne
  kaynağı.
- `scripts/create_qc_contact_sheet.py`: yayımlanmış YOLO kutularıyla
  contact sheet.
- `scripts/analyze_detection_domain.py`: gerçek/sentetik bbox ve split
  audit’i.
- `docs/PHYSICAL_REALISM_SPEC.md`: değişmeyen topoloji ile bounded
  randomization sınırı.
- `docs/BBOX_OCCLUSION_POLICY.md`: standard/hard/exclude karar
  sözleşmesi.
- `reports/qc/REALISM_REVISION_V5_2026-07-29.md`: v5 delili ve açık
  risklerin karar kaydı.

## v1.7.15'e kadar kanonik reference-fit değişiklikleri

- Hedef panel haritası sabitlendi: back/left gri, right + lokal aperture
  cobalt-mavi.
- Sol access door gerçek pivot ve bimodal açı profiline alındı.
- LED, upper-platen kotunda back + left + right boyunca tam boy üç
  channel/diffuser/emitter segmentidir.
- İki `400 mm` machined steel platen ve küp kenarına yaklaşık `2.22×`
  oranı config contract’ına bağlandı.
- Rear ve side görünür fisheye stack’lerine bezel/lens/port katmanları
  eklendi.
- Cube/cylinder dağılımı `.42/.58`; beton pore/aggregate/roughness/
  bounded damage katmanları ayrıldı.
- Basılı kâğıt, semantic sınıf olmayan fiziksel occluder’dır. Kâğıt
  altındaki RFID’nin görünür instance maskesi bbox’u belirler.
- Her kamera için position/target/lens/focus/roll/distortion/exposure ve
  door-fill dar, seed’li aralıklardadır.
- Bağımsız detection still’leri için küp yaw dağılımı kamera profiline
  koşulludur: `camera_angled=-42…-28°`,
  `camera_door=-35…20°`. Bu, 32-kare gerçek-bbox dağılım fit’idir;
  senkron iki-kamera sahnesinde kullanılmaz. Paired üretimde tek fiziksel
  yaw seçip iki kameraya aynı sahneyi render edin.
- Güncel config vignette, sensor sharpen ve highlight bloom’u kapatır.
  Gerçek sensör profili ölçülmeden bu efektleri açmayın.
- v5 hotfix’i periyodik tabla Wave-normalini kaldırır; metalde düzensiz
  mikronormal/roughness kullanır, iri yapışık agrega ve dekoratif rubble
  ölçeğini küçültür, orta hasarlı küplerde boncuk görünümünü kaldırır ve
  yan duvarlardaki büyük kopya kapakları kompakt fisheye stack’e çevirir.
- v1.7.4–v1.7.14; yüzey relief/rejimlerini, basılı form/tag
  occlusion'ını, ayrı üst/alt used-steel contact face'leri, sabit cabinet
  ve kamera stack'lerini, düşük-glare üst tabla ile tek-hull spall
  fallback'ini ekler.
- v1.7.15, task 9–14 LED ve bütün REF makine-kamera gruplarından fresh
  piksel incelemesine dayanan küçük, kümeli ochre/koyu üst-yük artığını
  ayrı RNG ile ekler. Gerçek prevalans/BRDF ölçülmedi; scan/texture
  geldikten sonra procedural proxy değiştirilmelidir.

## Config ve seed sözleşmesi

Her seed; kapı açısı, numune şekli/hasarı/nemi, tag sayısı/yerleşimi,
paper ilişkisi, ışık profili, camera realization ve Cycles seed’ini
belirler. Bit-exact RGB; driver/denoiser/Blender build’i arasında garanti
değildir. v5 aynı-seed kontrolünde scenario metadata, label ve bütün
semantic/instance maskeleri byte-identical kalmış, OptiX-denoised RGB
hash’i değişmiştir. Aynı script/config pininde scene metadata ve
annotation kararları deterministik olmalıdır.

Bir değişiklikte tek parametre ailesini oynatın:

1. sabit topoloji ve physical contact;
2. kamera framing/lens;
3. LED/exposure/material;
4. paper/RFID placement;
5. sensor post-process.

Config ya da generator SHA’sı değişmiş eski run yeni kaynak için PASS
kanıtı değildir. Her fresh run’da:

```bash
sha256sum \
  "$EBIS_LOCAL/scripts/generate_ebis.py" \
  "$EBIS_LOCAL/configs/ebis_led_v2.json"
```

değerlerini `run_manifest.json`, bir metadata JSON’u ve
`validation.json` içindeki SHA’larla karşılaştırın.

## Fresh batch → validate → pull → QC

Remote’da fresh adla 32-kare 1280×720 pilot:

```bash
run_name=reference_fit_pilot_63000

ssh 3090 "$BLENDER_REMOTE -b --factory-startup \
  --python $EBIS_REMOTE/scripts/generate_ebis.py -- \
  --config $EBIS_REMOTE/configs/ebis_led_v2.json \
  --action batch --seed 63000 --count 32 \
  --output $EBIS_REMOTE/output/$run_name \
  --resolution 1280x720 --samples 64 --no-depth"
```

Validator:

```bash
ssh 3090 "$BLENDER_REMOTE -b --factory-startup \
  --python $EBIS_REMOTE/scripts/generate_ebis.py -- \
  --config $EBIS_REMOTE/configs/ebis_led_v2.json \
  --action validate \
  --output $EBIS_REMOTE/output/$run_name \
  --expected-count 32 --require-both-cameras"
```

Run’ı yukarıdaki direct rsync komutuyla local’e aldıktan sonra:

```bash
python3 "$EBIS_LOCAL/scripts/create_qc_contact_sheet.py" \
  --dataset "$EBIS_LOCAL/output/$run_name" \
  --output "$EBIS_LOCAL/reports/qc/${run_name}_contact_sheet.png" \
  --columns 4 --limit 32

python3 "$EBIS_LOCAL/scripts/analyze_detection_domain.py" \
  --real-root /home/utkutopcuoglu/Documents/utku/stajyerler/simulation/260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli \
  --synthetic-root "$EBIS_LOCAL/output/$run_name" \
  --json "$EBIS_LOCAL/reports/qc/${run_name}_domain.json" \
  --markdown "$EBIS_LOCAL/reports/qc/${run_name}_domain.md"
```

Production-candidate için aynı akışı fresh run adı, `1920x1080` ve en az
128 spp ile tekrarlayın. Depth kullanılacaksa `--no-depth` kaldırılır.
Fresh validator PASS, 100-kare iki kişilik QC ve güncel BlenderMCP
round-trip olmadan production etiketi vermeyin.

## Güncel v5 delili

### Framing dağılım kapısı

- Dataset:
  `output/realism_v5_1_distribution_gate_54120/`
- Audit:
  `reports/qc/realism_v5_1_distribution_gate_audit.md`
- Contact sheet:
  `reports/qc/realism_v5_1_distribution_gate_contact_sheet.png`
- `640×360`, 20 spp, seed `54120–54151`, validator `32/32 PASS`.
- 25 standard + 3 hard + 4 exclude; 99 fiziksel RFID.
- İki kamera × cube/cylinder dört hücrenin her biri `N=7–9` ve gerçek
  bbox medyanına görsel `±0.03` kapısında `PASS`.

Bu düşük çözünürlüklü run kamera intrinsics kanıtı veya production görsel
kalitesi değildir; 32 örnekli kadraj dağılım kanıtıdır.

### Reference-fit görsel pilot

- Dataset:
  `output/realism_v5_1_referencefit_pilot_54120/`
- Contact sheet:
  `reports/qc/realism_v5_1_referencefit_pilot_contact_sheet.png`
- `1280×720`, 64 spp, seed `54120–54127`, iki kamerada 4’er görüntü.
- Validator `8/8 PASS`; 8 standard.
- 23 fiziksel RFID: 11 standard-positive, 10 fully-occluded,
  2 outside-frame; 39 binary maske ve 55 hash.
- Bu sekiz-kare run görsel inceleme içindir; iki örnekli tek
  door/cube hücresinin framing medyanı TUNE’dur. Release kadraj kanıtı
  yukarıdaki 32-kare dağılım kapısıdır.

### Güncel 1080p BlenderMCP

- Güncel MCP pin: `evidence/mcp/pins_v1_8_1.json`
- Round-trip: `evidence/mcp/20260730-cast-pores-v8/roundtrip.json`
- Render: `evidence/mcp/20260730-cast-pores-v8/render.png`

MCP turu 163 nesneyi değiştirmeden scene-info, nonce execute, viewport
ve RTX 3090 OptiX render yolunu doğrular. Listener yalnız loopback’te
açılmış ve tur sonunda kapatılmıştır. Bu fotogerçekçilik veya YOLO
faydası kanıtı değildir.

## Tarihsel, artık output'u tutulmayan kalibrasyonlar

Aşağıdaki run adları tarihsel karar günlüğüdür; obsolete render klasörleri
geri alınabilir çöp alanına taşınmıştır ve current review için kullanılmaz.

### Topoloji/material calibration4

- Dataset:
  `output/realism_v4_calibration4_low_54100/`
- Contact sheet:
  `reports/qc/realism_v4_calibration4_low_54100_contact_sheet.png`
- `640×360`, 32 spp, seed `54100–54107`, iki kamerada 4’er görüntü.
- Validator `8/8 PASS`; 6 standard + 2 hard, 23 RFID instance, 39 binary
  mask, 55 hash.

### Occlusion calibration

- Dataset:
  `output/realism_v4_occlusion_calibration_54120/`
- Contact sheet:
  `reports/qc/realism_v4_occlusion_calibration_54120_contact_sheet.png`
- `640×360`, 20 spp, seed `54120–54135`, iki kamerada 8’er görüntü.
- Validator `16/16 PASS`; 10 standard + 5 hard + 1 exclude.
- 46 fiziksel RFID: 27 standard-positive, 7 hard-positive, 1 excluded,
  4 fully-occluded, 7 outside-frame.
- 78 binary mask, 110 hash; bir linked partial-tip paper senaryosu
  validator tarafından kontrol edildi.

Bu iki dataset **low-res development calibration**’dır. Run’ların kendi
config/generator SHA’ları farklı olabilir; mevcut source/config değişmiş
ise yeniden valide etmek yerine fresh output üretin. Contact sheet’ler
production kalite ya da YOLO faydası kanıtlamaz.

## Annotation ve yayın akışı

Render önce geçici klasörde RGB, semantic mask, her RFID için ayrı visible
instance mask ve opsiyonel depth üretir. RGB ile mask geometric lens
warp’ını paylaşır. Bbox yalnız binary visible instance maskesinden
çıkarılır.

- `standard` → ana synthetic-train adayı;
- `hard_occlusion` → yalnız adlandırılmış ablation;
- `exclude` → hiçbir detection training manifest’ine girmez;
- `fully_occluded` / `outside_frame` → metadata’da fiziksel instance
  kalır, YOLO satırı yazılmaz.

Bir karede tek görünür RFID bile exclude ise tüm kare exclude olur; böylece
unlabelled positive ana train’e sızmaz. Semantic RFID union maskesi çoklu
bbox üretmek için kullanılmaz.

## 100-kare görsel QC checklist

- back/left gri, right cobalt; başka makine varyantı ile hibrit yok;
- sol access door pivot/angle/aperture fiziksel olarak tutarlı;
- beton iki circular platen’a temas ediyor; floating/intersection yok;
- plate çapı cube’un yaklaşık iki katı olarak okunuyor;
- LED üç duvarda tam boy, ince opal channel; büyük beyaz tavan değil;
- LED modu siyah crush üretmiyor, üst temas bölgesinde dar spill var;
- servis cover, dört vida ve rear/side lens stack’leri tutarlı;
- concrete düzenli cube/cylinder; waxy plastik, iri yapay pore veya
  procedural tekrar yok;
- paper betonla temas ediyor; cylinder’da floating planar paper yok;
- her görünür RFID ayrı tight bbox; iki tag tek union bbox değil;
- paper altında tamamen gizli tag’in YOLO satırı yok;
- küçük/ayrık görünen uç doğru hard/exclude partition’ında;
- frame-edge tag bbox’u maskeye sıkı; büyük arka plan alanı kapsamıyor;
- vignette/sharpen/bloom config kapalıysa render metadata ve görünümde
  ölçülmemiş post-effect yok.

## Bilinen açıklar ve en yüksek getirili işler

1. İki kameranın checkerboard/ChArUco intrinsics, distortion ve mount
   pozunu ölçmek.
2. Chamber, kapı, iki tabla, cube/cylinder ve lens-stack ölçülerini almak;
   fallback oranlarını kaldırmak.
3. Gerçek metal/concrete/paper crop veya lisanslı scan ile
   albedo/roughness/normal kalibrasyonu.
4. Conformed cylinder paper ve ölçülmüş paper/tag placement prior’ı.
5. Workshop için lisanslı, aynı tesisten backplate/CAD; proxy cue’yu
   azaltmak.
6. Lux/CCT/CRI, fixed exposure ve gray-card ölçümüyle LED/white-balance
   profili.
7. Güncel 8-kare/1080p/MCP kanıtını 32-kare pilot ve 100-kare
   iki-person QC’ye genişletmek.
8. Frozen gerçek test split’inde nano YOLO ablation; yalnız metrik
   iyileşirse synthetic kolu tutmak.

Arıza sırasında fresh output adı kullanın. `.generation.lock` varsa önce
Blender PID’sini kontrol edin. `config_sha256_mismatch`,
`generator_script_sha256_mismatch` veya `unsafe_partition_*` hatasında
train başlatmayın; farklı pinli artefaktları karıştırmayın.
