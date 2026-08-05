# EBIS Blender detection teslim raporu

Date: 2026-07-30  
Generator: `1.8.1`  
Physical revision:
`front_hinged_door_blue_chamber_cast_pores_pass8_2026-07-30`

## Teslim kararı

Paket, 3090 üzerinde tekrar üretilebilir reference-fit detection release
candidate olarak devredilebilir. Production dataset, ölçülü dijital ikiz veya
kanıtlanmış YOLO iyileştirmesi değildir.

## Kanonik artefaktlar

- Sabit review:
  [contact sheet](../../output/current_samples/contact_sheet.png),
  [CURRENT.json](../../output/current_samples/CURRENT.json)
- Immutable release:
  [validation](../../output/realism_v8_cast_pores_release_60100/validation.json),
  [QC sheet](../qc/realism_v8_cast_pores_release_60100_contact_sheet.png),
  [release manifest](../../evidence/release/realism_v8_cast_pores_release_60100_manifest.json)
- BlenderMCP:
  [pins](../../evidence/mcp/pins_v1_8_1.json),
  [round-trip](../../evidence/mcp/20260730-cast-pores-v8/roundtrip.json),
  [1080p render](../../evidence/mcp/20260730-cast-pores-v8/render.png)
- Online asset A/B:
  [karar raporu](../qc/ONLINE_ASSET_AB_2026-07-30.md),
  [provenance](../../docs/ASSET_PROVENANCE.md)
- Ortak final rapor:
  [front-door/PBR release](../../../reports/qc/EBIS_FRONTDOOR_PBR_RELEASE_2026-07-30.md)

Release `PASS`, 12/12; 6 cam-10 + 6 cam-11, dört kamera×şekil hücresi,
32 fiziksel RFID ve 56 visible binary maskedir. BlenderMCP V8 wide-open
sahnede `163→163` nesne, nonce execute, viewport ve 1080p/128 spp OptiX
render ile `PASS`; process/port kapalıdır.

## Değişmeyen fiziksel sözleşme

- Sabit back/left/right yüzeyler mavi tırtıklı hammertone.
- Dolu gri ön kapı dışarıdan sağ menteşeli ve dışa açılır; servis kapağı
  leaf'e parent'tır.
- Sürgü rayı, glass leaf veya turuncu sabit machine hardware yoktur.
- `Ø400 mm` iki tabla arasında düz nominal `180 mm` cube veya
  `Ø126 × 201 mm` cylinder.
- Upper-platen kotunda back/left/right boyunca ince opal U-difüzör.
- Bbox görünür per-instance maskeden; fully hidden/frame dışı RFID satırı yok.
- `hard` normal train'e karışmaz; `exclude` hiçbir train/val/test'e girmez.

Ölçülü CAD/calibration gelirse bu fallback değerler config'ten birlikte
değiştirilir; Blender ve Unreal fiziksel spec'i ayrıştırılmaz.

## Materyal kararı

- Mavi wall: `procedural_hammertone_v2`.
- Beton: procedural geometry/hasar + düşük-oranlı ambientCG Concrete003
  box-projection hibriti; V8 görünür gözenek sayısı/radius dağılımı gerçek
  pitted-cast ölçeğine daraltıldı.
- Poly Haven blue metal aynı-seed A/B'de seam/uzun çizik nedeniyle reddedildi.
- Poly Haven Rough Concrete 1K, iki same-seed ROI'de yalnız
  `4.78–4.94/255` ortalama mutlak fark ve plaster karakteri verdiği için
  reddedildi; compact kanıt `reports/qc/asset_ab/` altındadır.
- Generic online compression-machine ve damaged scanned cylinder canonical
  geometri değildir.

## Sonraki mühendisin ilk iki günü

1. İki current sheet'i ve gerçek LED/IR reference-forensics'i aç; owner'ın
   yalnız somut yanlış-parça/yüzey/kadraj notlarını ledger'a yaz.
2. `configs/ebis_led_v2.json`, generator ve external asset hash'lerini pinle.
3. Fresh `60200..60215` 16-kare pilot üret; validator, 2×2 contact sheet ve
   üç kişi değil en az iki bağımsız label/görsel reviewer kullan.
4. Gördüğün fark için aynı seed'de yalnız bir katmanı değiştir; source kod
   veya node varlığını değil final RGB/mask piksellerini karşılaştır.
5. 100-kare QC geçmeden large batch, frozen gerçek split hazır olmadan YOLO
   kıyası başlatma.

Detaylı sıra:
[14 günlük plan](../../docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md),
[kullanıcı desteği](../../docs/USER_SUPPORT_AND_REVIEW.md),
[bbox policy](../../docs/BBOX_OCCLUSION_POLICY.md),
[YOLO planı](../../experiments/yolo/README.md).

## Çalışma kökleri

```text
Local source:
/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/ebis-blender

3090:
/home/ankaref/Documents/Projects/simulation/ebis-blender

Blender:
/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender
```

`output/current_samples/` yalnız repository-root promotion scriptiyle atomik
güncellenir. Eski run/QC/MCP-image artefaktları geri alınabilir çöp alanına
taşınmıştır; temizlik manifestleri ortak final rapordadır.

## Açık kabul kapıları

- ölçülü chamber/door/platen/camera-mount CAD;
- cross-polarized mavi boya/gri sac/çelik/concrete scan;
- cam-10/cam-11 intrinsics ve sensor response;
- 100-kare iki kişilik insan QC;
- capture-safe frozen gerçek testte seed `17/29/43` YOLO nano ablation.

Bu kapılar olmadan “fotogerçekçi” veya “modeli iyileştiriyor” yazılmaz.
