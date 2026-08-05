# EBIS Blender detection simulation

Bu klasör EBİS beton kırım makinesinde `rfid_tag` ve `concrete_sample`
detection verisi üretmek için kanonik Blender paketidir. Tek config
[`configs/ebis_led_v2.json`](configs/ebis_led_v2.json), tek generator
[`scripts/generate_ebis.py`](scripts/generate_ebis.py) dosyasıdır.

## Güncel release

| Alan | Değer |
| --- | --- |
| Generator | `1.8.1` |
| Physical revision | `front_hinged_door_blue_chamber_cast_pores_pass8_2026-07-30` |
| Immutable run | [`realism_v8_cast_pores_release_60100`](output/realism_v8_cast_pores_release_60100/validation.json) |
| Validator | `PASS`, 12/12 RGB; 6 cam-10 + 6 cam-11; dört kamera×şekil hücresi mevcut |
| Annotation | 32 fiziksel RFID, 56 visible binary maske; 8 standard / 1 hard / 3 exclude |
| Review | [`output/current_samples/contact_sheet.png`](output/current_samples/contact_sheet.png) |
| MCP | [`pins_v1_8_1.json`](evidence/mcp/pins_v1_8_1.json), [`round-trip`](evidence/mcp/20260730-cast-pores-v8/roundtrip.json) |

Güncel BlenderMCP wide-open V8 sahnesinde `163→163` nesne, nonce execute,
1200×698 viewport ve `1920×1080 / 128 spp` RTX 3090 OptiX render ile
`PASS`tir. Server yalnız `127.0.0.1:9876` üzerinde çalıştı ve tur sonunda
process/port kapatıldı.

## Fiziksel sözleşme

- `camera_angled = cam-10 / Kamera 01`;
  `camera_door = cam-11 / Kamera 02`.
- Sabit back/left/right hazne duvarları mavi tırtıklı procedural hammertone;
  ceiling koyu düşük-glare, tray gri sacdır.
- Dolu gri ön kapı dışarıdan sağ menteşeli ve dışa açılır. Gri rounded
  servis kapağı leaf ile birlikte döner. Sürgü rayı, glass leaf ve turuncu
  sabit makine hardware'i yoktur.
- İki aynı eksenli `Ø400 mm` used-steel tabla arasında `180 mm` küp veya
  `Ø126 × 201 mm` silindir vardır. Nominal dikey kenarlar düzdür;
  fisheye distortion mesh'i içbükey yapmaz.
- İnce opal U-difüzör üst tabla seviyesinde back/left/right boyunca tam
  uzanır; kapı açıklığında LED segmenti yoktur. LED contact spill ve bounded
  camera/door fill ayrı kontrollere sahiptir.
- Basılı/buruşuk kağıt non-target fiziksel occluder'dır. RFID kağıt altında
  tam/kısmi gizlenebilir veya tabla aralığında yalnız ucu görünebilir.
- Concrete ve RFID multipart parçaları instance kimliğini korur. Bbox
  görünür instance maskesinden çıkar; fully hidden/frame dışı target label
  almaz.

`Ø400 mm`, chamber fallback ölçüleri, kapı aralığı ve kamera fit'i gerçek CAD
ve calibration gelene kadar bounded görsel varsayımdır.

## Materyal ve çevrimiçi asset kararı

Canonical beton, procedural pore/edge/spall geometrisi ile ambientCG
`Concrete003` 2K'nın düşük-oranlı box-projection color/roughness/bump
katmanını birleştirir. V8, gerçek LED/IR pikselinde görülen ölçeğe yaklaşmak
için hasara bağlı 79–141 adet küçük-ağırlıklı görünür döküm gözenek kullanır.
Poly Haven `Blue Metal Plate` seam/uzun çizik; Poly Haven `Rough Concrete`
1K ise iki aynı-seed karede yalnız `4.78–4.94/255` bbox-içi ortalama mutlak
fark ve yanlış plaster karakteri verdiği için canonical yapılmadı.

- [A/B ve piksel ölçümü](reports/qc/ONLINE_ASSET_AB_2026-07-30.md)
- [Asset provenance](docs/ASSET_PROVENANCE.md)
- [Kompakt A/B görselleri](reports/qc/asset_ab/)
- [Zaman yayılı LED/IR reference forensics](reports/qc/reference_forensics/)

Hakları/lisansı, ölçeği ve SHA-256'sı bilinmeyen online model production
dataset'ine girmez.

## Output ve annotation

Sabit review klasörü elle düzenlenmez:

```text
output/current_samples/
├── contact_sheet.png
├── CURRENT.json
├── images/       # cam10/cam11 × cube/cylinder
├── labels/
├── metadata/
└── masks_visible/
```

`CURRENT.json` source run/validation ve her dosyanın hash'ini taşır.
Yeni validated run'ı repository kökünden yayınlama:

```bash
python3 scripts/promote_ebis_current_samples.py \
  --engine-root ebis-blender \
  --source-run ebis-blender/output/YENI_RUN
```

Normal YOLO train yalnız `partitions/standard`; `hard_occlusion` yalnız
adlandırılmış ablation; `exclude` hiçbir train/val/test manifest'i değildir.
Detay: [bbox policy](docs/BBOX_OCCLUSION_POLICY.md).

## 3090 üretim

```bash
export EBIS_REMOTE=/home/ankaref/Documents/Projects/simulation/ebis-blender
export BLENDER_REMOTE=/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender

ssh 3090 "cd $EBIS_REMOTE && \
  $BLENDER_REMOTE -b --factory-startup \
  --python scripts/generate_ebis.py -- \
  --config configs/ebis_led_v2.json \
  --action batch --seed 60200 --count 16 \
  --output output/engineer_pilot_60200 \
  --resolution 1280x720 --samples 64 --no-depth"

ssh 3090 "cd $EBIS_REMOTE && \
  $BLENDER_REMOTE -b --factory-startup \
  --python scripts/generate_ebis.py -- \
  --config configs/ebis_led_v2.json \
  --action validate \
  --output output/engineer_pilot_60200 \
  --expected-count 16 --require-both-cameras"
```

Fresh run adı zorunludur; eski release üzerine yazılmaz. Generator/config
değişince yeni run açın ve 2×2 actual-pixel sheet'i görmeden production batch
başlatmayın.

## Handoff ve sınırlar

Okuma sırası:

1. [Teslim raporu](reports/handoff/EBIS_BLENDER_HANDOFF_REPORT.md)
2. [Front-door/PBR release raporu](../reports/qc/EBIS_FRONTDOOR_PBR_RELEASE_2026-07-30.md)
3. [Fiziksel spec](docs/PHYSICAL_REALISM_SPEC.md)
4. [Kullanıcı desteği/review](docs/USER_SUPPORT_AND_REVIEW.md)
5. [14 günlük plan](docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
6. [YOLO ablation README](experiments/yolo/README.md)

Ölçülü CAD/PBR/intrinsics, 100-kare iki kişilik insan QC ve frozen gerçek
test YOLO ablation'ı açık kalır. Bu release teknik/görsel QC adayıdır;
fotogerçekçi dijital ikiz veya model kazancı değildir.
