# Unreal-EBIS detection simulation

Bu klasör EBİS beton kırım makinesi için Unreal Engine 5.8.1 ile
`rfid_tag` ve `concrete_sample` detection verisi üretir. Tek config
[`configs/ebis_unreal_v1.json`](configs/ebis_unreal_v1.json), tek sahne
üreticisi [`Content/Python/ebis_scene.py`](Content/Python/ebis_scene.py).

## Güncel release

| Alan | Değer |
| --- | --- |
| Engine | Unreal Engine `5.8.1-56057345`, RTX 3090 |
| Physical revision | `front_hinged_door_blue_chamber_neutral_cast_brdf_pass8f_2026-07-30` |
| Immutable run | [`realism_r59_neutral_cast_brdf_release_60160`](output/realism_r59_neutral_cast_brdf_release_60160/validation.json) |
| Validator | `ok=true`, 16/16; 8+8 kamera, 8+8 cube/cylinder, `errors=[]`, `warnings=[]` |
| Annotation | 70 visible + 70 isolated-amodal mask; 5 standard / 2 hard / 9 exclude |
| Framing | dört camera×shape bbox medyanı gerçek hedefe mutlak `≤0.06` |
| Review | [`output/current_samples/contact_sheet.png`](output/current_samples/contact_sheet.png) |
| Epic MCP | [`r59 round-trip`](evidence/mcp/20260730-neutral-cast-r59-roundtrip.json), [`summary`](evidence/mcp/20260730-neutral-cast-r59-verification-summary.json) |

Güncel exact r59 sahnesi Epic resmi Unreal MCP'de 9-call
initialize/list/describe/build/validate/status/render ile `PASS`; standard
seed `60175`, `1920×1080` RGB + EXR + üç instance için visible/amodal.
Endpoint yalnız
`127.0.0.1:8000`, tur sonunda editor ve port kapalıdır.

## Fiziksel sözleşme

- `camera_angled = cam-10 / Kamera 01`;
  `camera_door = cam-11 / Kamera 02`.
- Sabit back/left/right hazne duvarları mavi tırtıklı procedural hammertone;
  ceiling koyu düşük-glare, tray gri sacdır.
- Dolu gri ön kapı dışarıdan sağ menteşeli ve dışa açılır. Gri rounded
  servis kapağı leaf ile döner. Sürgü rayı, glass leaf ve turuncu sabit
  hardware yoktur.
- İki aynı eksenli `Ø400 mm` used-steel tabla arasında `180 mm` küp veya
  `Ø126 × 201 mm` silindir bulunur; nominal yan konturlar düzdür.
- İnce opal U-difüzör upper-platen kotunda back/left/right boyunca uzanır;
  görünür cover ile fiziksel ışık katkısı ayrıdır.
- Paper, platen ve sample gerçek occluder'dır. RFID cylinder'a segmentli
  yay olarak konforme olabilir veya plate-gap'te micro/partial/major uç
  gösterebilir.
- Multipart hedefler tek `EBIS_INSTANCE` taşır. Visible ve isolated-amodal
  pass ayrı; bbox visible maskeden ve visibility visible/amodal oranından.

Ölçüler, camera fit ve ışık değerleri CAD/intrinsics/lux gelene kadar bounded
görsel fallback'tir.

## Materyal ve çevrimiçi asset kararı

Canonical beton `procedural_cast_concrete_v2`, material asset
`M_ConcreteProceduralV27`'dir. V24'teki hücresel ve V25'teki büyük mermerimsi
albedo noise'u actual-pixel A/B ile reddedildi; V27 nötr döküm tonu ve
`0.86` roughness kullanır, ölçekli değişim 54–92 küçük-ağırlıklı fiziksel
gözenek/edge relief/residue geometrisinden gelir.

ambientCG `Concrete003` direct-UV deneyi cylinder'da yatay gerilme, cube'da
aşırı kontrast ürettiği için reddedildi. Poly Haven mavi sacı da seam/çizik
ve UV ölçeği nedeniyle canonical yapılmadı.

- [Asset provenance](docs/ASSET_PROVENANCE.md)
- [Kompakt Unreal concrete A/B](reports/qc/asset_ab/)
- [Engine kıyası](reports/qc/ENGINE_COMPARISON.md)

## Output ve annotation

```text
output/current_samples/
├── contact_sheet.png
├── CURRENT.json
├── images/       # cam10/cam11 × cube/cylinder
├── labels/
├── metadata/
├── masks_visible/
└── masks_amodal/
```

Yeni validated run'ı repository kökünden yayınlama:

```bash
python3 scripts/promote_ebis_current_samples.py \
  --engine-root unreal-ebis \
  --source-run unreal-ebis/output/YENI_RUN
```

Normal train yalnız `partitions/standard`; `hard_occlusion` yalnız isimli
ablation; `exclude` hiçbir train/val/test manifest'i değildir. r59 batch
RGB/visible/amodal release'idir. Fisheye RGB warp ile eşlenmemiş depth
fail-closed kapalıdır; MCP'nin tek-kare EXR'i batch'e depth atfetmez.

## 3090 üretim ve MCP

```bash
ssh 3090
cd /home/ankaref/Documents/Projects/simulation/unreal-ebis
./scripts/run_remote_release.sh engineer_pilot_60220 16 60220 1280 720 0
```

Wrapper mevcut output üzerine yazmayı reddeder; capture sonrası camera model,
sensor response, bbox/partition validator ve QC contact sheet otomatik çalışır.

Güncel scene için bounded Epic MCP kontrolü:

```bash
cd /home/ankaref/Documents/Projects/simulation/unreal-ebis
./scripts/start_unreal_mcp.sh

python3 scripts/unreal_mcp_client.py \
  --config "$PWD/configs/ebis_unreal_v1.json" \
  --output "$PWD/evidence/mcp/engineer_check_artifacts" \
  --evidence "$PWD/evidence/mcp/engineer_check.json" \
  --seed 60175 --camera camera_angled --shape cylinder --render

./scripts/stop_unreal_mcp.sh
```

MCP auth/TLS taşımaz; dış arayüze bind edilmez.

## Çalışma alanı

```text
Local source:
/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/unreal-ebis

RTX 3090 workspace:
/home/ankaref/Documents/Projects/simulation/unreal-ebis

UE 5.8.1:
/media/ankaref/SSD-MNT-500GB/unreal-engine-5.8.1

Workspace engine link:
/home/ankaref/Documents/Projects/simulation/.tools/unreal-engine-5.8.1

DDC:
/media/ankaref/SSD-MNT-500GB/unreal-ddc
```

## Handoff ve sınırlar

Okuma sırası:

1. [Teslim raporu](reports/handoff/UNREAL_EBIS_HANDOFF_REPORT.md)
2. [Front-door/PBR release raporu](../reports/qc/EBIS_FRONTDOOR_PBR_RELEASE_2026-07-30.md)
3. [Fiziksel spec](docs/PHYSICAL_REALISM_SPEC.md)
4. [Kullanıcı desteği/review](docs/USER_SUPPORT_AND_REVIEW.md)
5. [14 günlük plan](docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
6. [YOLO ablation README](experiments/yolo/README.md)

Ölçülü CAD/PBR/intrinsics, 100-kare iki kişilik insan QC, güncel same-seed
determinism ve frozen gerçek test YOLO ablation'ı açık kalır. Unreal r59
teknik/görsel QC adayıdır; Blender'ı geçtiği veya model faydası sağladığı
iddia edilmez.
