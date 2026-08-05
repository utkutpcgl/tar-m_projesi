# EBIS gerçekçilik tekrarı — pass 6/6

Tarih: 2026-07-30  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: gerçek LED/IR çıkarımlarını Unreal'a uygulama, aynı fiziksel
sözleşmeyi Blender'a geri taşıma, actual-pixel red/green kararları,
güncel pilot + MCP + devir kanıtı.

## Sonuç

İki engine'in güncel kaynakları teknik olarak doğrulandı:

- Unreal:
  [`realism_r39_matte_spall_p6d_58520`](unreal-ebis/output/realism_r39_matte_spall_p6d_58520),
  `12/12 PASS`, 52 visible + 52 amodal maske, dengeli iki
  kamera × iki shape, dört bbox hücresi `≤0.06`, güncel resmî Unreal MCP
  `PASS`;
- Blender:
  [`realism_v5_19_single_hull_release_p6f_54304`](ebis-blender/output/realism_v5_19_single_hull_release_p6f_54304),
  `12/12 PASS`, 6/6 kamera, 36 fiziksel RFID, güncel BlenderMCP
  scene-query/execute/viewport/1080p OptiX render `PASS`.

Pass; üst tabla glare'ını, betonun yapay geniş koyu bulutlarını ve
spalled cube'un yanlış gövde topolojisini hedefledi. Teknik PASS,
fotogerçekçi dijital ikiz veya model faydası değildir. Güncel
[gerçek–Blender–Unreal sheet'i](reports/qc/multi_repeat_pass6f_real_blender_unreal.png)
iki sentetik motorda da gerçek kırık scale/çeşitliliği, ölçülmüş PBR,
fisheye/sensor response ve contamination açığının sürdüğünü gösterir.

## Bağımsız gerçek piksel zemini

Pass 1–5 boyunca tekrar açılan time-diverse kaynak:

- task 9–14'ten cam-10/cam-11 LED RGB;
- 18 `REF-*` makine×kamera grubundan IR/non-LED gri kare;
- küp/silindir, farklı kapı açıklığı, basılı form, kısmi/gizli RFID,
  clean/pitted/edge-worn/severely-spalled beton ve kuru/tozlu/nemli
  tabla örnekleri.

Bu pass'te full-resolution yeniden açılan iki ana eş:

- [cam-10 silindir LED](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00340.png);
- [cam-11 ağır hasarlı küp LED](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_11_dataset_2026_01_23_07_32_53_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-6_frame-00000.png).

IR, sabit geometriyi, tabla temasını, door/camera stack'i ve yüzey
mikro-topolojisini ayırmak için kullanıldı. IR luminance veya renk,
RGB albedo/exposure hedefi yapılmadı.

## Unreal pass-6d

### Uygulanan

[`ebis_scene.py`](unreal-ebis/Content/Python/ebis_scene.py),
[`ebis_unreal_v1.json`](unreal-ebis/configs/ebis_unreal_v1.json) ve
[`build_visible_bboxes.py`](unreal-ebis/scripts/build_visible_bboxes.py):

- physical revision
  `fixed_machine_fisheye_pbr_pass6d_2026-07-30`;
- upper platen body/contact ayrımı;
- body `M_UpperPlatenBodyUsedSteelV11`:
  base `(0.012,0.015,0.020)`, roughness `.88`, metallic `.12`,
  specular `.18`;
- contact `M_UpperContactFaceUsedV10`:
  base `(0.018,0.021,0.027)`, roughness `.90`, metallic `.14`,
  specular `.16`;
- cube spalled rejiminde üç non-overlap gövde parçası, aynı
  `concrete_00` identity'si, bounded notch ve 7–10 küçük fracture tooth;
- body profile, notch boyut/side/tooth count, fixed camera stack,
  interior finish ve tabla temaslarını validator hard-gate;
- instance-aware visible/amodal mask ve worst-instance partition
  sözleşmesi değişmeden korundu.

### Actual-pixel karar

Aynı seed/material-only üst ROI:

| Ölçüm | Önce | Sonra |
| --- | ---: | ---: |
| mean luma | `125.330` | `92.939` |
| piksel `>200` | `0.204441` | `0.105757` |

Bu kontrollü değişim eski beyaz/temiz tabla ipucunun azaldığını gösterir.
Ölçülmüş BRDF veya kalite skoru değildir.

### Final teknik kanıt

- [release manifest](unreal-ebis/evidence/release/realism_r39_matte_spall_p6d_58520_manifest.json);
- [validation](unreal-ebis/output/realism_r39_matte_spall_p6d_58520/validation.json);
- [contact sheet](unreal-ebis/reports/qc/assets/realism_r39_matte_spall_p6d_58520_contact_sheet.png);
- [resmî MCP transcript](unreal-ebis/evidence/mcp/realism_p6d_matte_spall_roundtrip.json);
- [editor log](unreal-ebis/evidence/mcp/realism_p6d_matte_spall_unreal_editor_stdout.log).

MCP turu sekiz çağrı, `ebis_toolset.EBISTools`, loopback
`127.0.0.1:8000`, seed `58525` angled/cube build ve validator `true`
sonucunu taşır. Tur sonrası port kapatıldı. Camera warp ile depth
registration kapısı çözülemediği için depth fail-closed kapalıdır.

## Blender pass-6e/6f geri aktarımı

### Beton materyali

Geniş procedural cloud/marble cue, time-diverse real concrete ve Unreal
noise-scale dersine göre daraltıldı:

- coarse renk bandı `0.90–1.04`;
- fine band `0.92–1.03`;
- mix etkisi `.32`;
- düşük-amplitüdlü streak/moisture contribution.

Aynı seed `54241` eski/yeni RGB pikselleri tam çözünürlükte açıldı.
Karanlık geniş “mermer bulutu” giderildi; pore, ışık ve küçük kalıp
farkı korundu. Bu karar görsel red/green kararıdır; model metriği
değildir.

### Reddedilen kırık denemeleri

Seed `54310`, camera_door, cube, spalled:

1. `v5_12`: dikdörtgen box Boolean + büyük additive ico tooth;
   kare oyuk ve yapıştırılmış taş gibi okundu, reddedildi.
2. `v5_13/v5_14`: box + scallop + tooth;
   kare sınır kaldı, mask değişimi hedefe ulaşmadı, reddedildi.
3. `v5_15`: 6–9 overlapping low-poly subtractive cutter;
   eski sürüme göre concrete maskesinde `1,603` piksel değişti ve kare
   sınırı kalktı; 1080p MCP renderında kristal/adacık gibi okundu,
   reddedildi.
4. `v5_18/v5_19`: tek kapalı irregular convex-hull Boolean;
   top/front/seçili yan yüzeye açılan tek bağlı eksik hacim; dikdörtgen
   duvar, additive tooth ve izole ada yok. Cluster sürümüne göre aynı
   concrete maskesinde `606`, ilk box/scallop sürümüne göre `997` piksel
   değişti. Bounded fallback olarak kabul.

Güncel profil:

```text
body_profile=single_hull_faceted_upper_front_corner_loss_v5
spall_notch_realization=irregular_convex_hull_boolean_v2
surface_profile=calm_midband_cast_skin_with_bounded_edge_relief_and_single_hull_spall_v6
notch fraction x=[.10,.18], y=[.10,.22], z=[.10,.20]
```

Convex hull gerçek ağır hasarlı sample kadar non-convex/ragged değildir.
Bu bilinçli residual, “ölçülü scan gelene kadar augmentation” olarak
metadata/status'ta kalır.

### Final teknik kanıt

- [release manifest](ebis-blender/evidence/release/realism_v5_19_single_hull_release_p6f_54304_manifest.json);
- [validation](ebis-blender/output/realism_v5_19_single_hull_release_p6f_54304/validation.json);
- [contact sheet](ebis-blender/reports/qc/realism_v5_19_single_hull_release_p6f_54304_contact_sheet.png);
- [domain audit](ebis-blender/reports/qc/realism_v5_19_detection_domain_audit.md);
- [MCP pins](ebis-blender/evidence/mcp/pins_v1_7_14.json);
- [MCP transcript](ebis-blender/evidence/mcp/20260730-pass6f-single-hull/roundtrip.json);
- [MCP 1080p render](ebis-blender/evidence/mcp/20260730-pass6f-single-hull/render.png).

BlenderMCP turu:

- 196 nesne ve 26 materyal önce/sonra aynı;
- nonce-bearing `execute_code`;
- `1200×698` viewport;
- `1920×1080`, 128 spp, RTX 3090 OptiX render;
- yalnız `127.0.0.1:9876`;
- doğrulama process group'u ve listener tur sonunda kapalı.

## Komut kanıtı

Blender pilot:

```bash
blender -b --factory-startup \
  --python ebis-blender/scripts/generate_ebis.py -- \
  --config ebis-blender/configs/ebis_led_v2.json \
  --action batch --seed 54304 --count 12 \
  --output ebis-blender/output/realism_v5_19_single_hull_release_p6f_54304 \
  --resolution 1280x720 --samples 64 --no-depth
```

Unreal pilot:

```bash
cd unreal-ebis
./scripts/run_remote_release.sh \
  realism_r39_matte_spall_p6d_58520 12 58520 1280 720 0
```

Kaynaklar ve artefaktlar release manifestlerinde tam SHA-256 ile
pinlidir. Local/3090 Blender source eşliği doğrudan doğrulandı:

```text
generate_ebis.py  83583645526dae0dde5507a339718815ef1132c22a46c122cefc1596646ba460
ebis_led_v2.json  ae1e617d8851f20110d98a47e39dad65fbb283c8dd3d732a2d42996d666b4817
```

## Engine transfer kararı

Ortak ve korunması gereken fiziksel sözleşme:

- kapalı cabinet + değişken açılan access door;
- upper-platen kotunda yalnız back/left/right ince U-diffuser;
- aynı eksende iki büyük dairesel used-steel tabla ve sample teması;
- rear/side fisheye camera stack ve ayrı cam-10/cam-11 prior'ı;
- düzenli cube/cylinder ana formu, bounded surface regime/damage;
- paper gerçek non-target occluder;
- her fiziksel RFID için ayrı visible instance mask/bbox;
- fully-hidden/outside metadata'da kalır, normal YOLO label almaz;
- `standard`, `hard`, `exclude` ayrımı.

Engine'e özel uygulama:

- Blender tek gövdede exact Boolean ile annotation maskini doğal taşır;
- Unreal multipart body ile Boolean topology riskini azaltır, fakat bütün
  parçalar tek `EBIS_INSTANCE` identity'si taşımalıdır;
- shader/node değerleri motorlar arasında kopyalanmaz; mm ölçek, ölçülmüş
  PBR kanalları ve pixel gate paylaşılır.

## Açık residual ve sonraki en değerli iş

1. **Ortak scan/CAD**: clean, pitted, edge-worn ve severely-spalled gerçek
   küp/silindirlerin scale bar'lı fotogrammetri/LiDAR/structured-light
   taraması; aynı source mesh iki engine'e.
2. **PBR ölçümü**: pebbled sac, üst/alt used-steel, kuru/nemli beton ve
   taze kırık yüz için cross-polarized albedo/roughness/normal,
   grey-card ve mm ruler.
3. **Kamera/ışık**: cam-10/cam-11 ChArUco, distortion, empty chamber,
   diffuser açık/kapalı fixed exposure, lux/CCT/IES.
4. **İnsan QC**: güncel hashlerle 16 deterministic annotation matrix ve
   100 stratified kare, iki bağımsız reviewer.
5. **Model kapısı**: capture-safe frozen gerçek val/test; `yolo11n`,
   aynı checkpoint/environment/hyperparameter, seed `17/29/43`;
   `R`, `R+B1N`, `R+U1N`. Hard ayrı ablation, exclude hiçbir split'e
   girmez.

YOLO faydası bu pass'te ölçülmedi. Sentetik verinin performansı artırdığı
veya bir engine'in diğerinden üstün olduğu iddia edilmez.
