# Unreal-EBİS gerçeklik revizyonu — 2026-07-29

## Sonuç

`realism_r5_full_58200`, yeni fiziksel tarif için **16-kare full-depth teknik
release validation PASS** sonucudur. RGB, depth, physical-instance maskeleri,
visible-bbox partition zinciri ve sensör manifesti birlikte doğrulandı. Bu
sonuç production kabulü, Unreal’ın Blender’dan daha gerçekçi olduğu veya
sentetik verinin YOLO’yu iyileştirdiği anlamına gelmez; 100-kare iki kişilik
QC, güncel determinizm ve model ablation’ı henüz tamamlanmadı.

## Doğrulanan kanıt

| Kontrol | Sonuç |
| --- | --- |
| Engine | UE 5.8.1 CL 56057345, RTX 3090 |
| Render | 16 × 1280×720 RGB; engine aşaması 49,184 s |
| Depth | 16 geçerli ve 16 benzersiz EXR |
| Kamera | 8 `camera_angled` + 8 `camera_door` |
| Numune | 8 cube + 8 cylinder |
| Instance pass | 65 visible + 65 amodal; beklenen 65/65 |
| Partition | 7 standard + 7 hard_occlusion + 2 exclude |
| RFID statüsü | 27 standard + 11 hard + 2 below-hard/exclude + 5 fully-occluded + 4 outside-frame |
| Bbox fit | Dört camera×shape concrete hücresinin tamamı gerçek hedefe mutlak `.06` içinde |
| Validator | `ok=true`, `errors=[]`, `warnings=[]` |
| Kaynak | scene SHA-256 `40ab5a28…b18c`; config SHA-256 `bcc274d1…0457` |
| Sensör cevabı | RGB-only, 16 input byte-for-byte korunmuş; mask/depth/geometri değişmedi |
| Resmî MCP | Güncel r5, loopback protocol `2025-11-25`; 9 çağrı/0 JSON-RPC error; build/validate/1080p RGB+depth PASS; sunucu durduruldu |

Kanıtlar:

- [`validation.json`](../../output/realism_r5_full_58200/validation.json)
- [`sensor response manifest`](../../output/realism_r5_full_58200/raw/sensor_response_manifest.json)
- [`contact sheet`](assets/realism_r5_full_58200_contact_sheet.png)
- [`engine log`](../../evidence/engine/realism_r5_full_58200_stdout.log)
- [`release manifest`](../../evidence/release/realism_r5_full_58200_manifest.json)
- [`current-scene MCP summary`](../../evidence/mcp/realism_r5_verification_summary.json)
- [`current-scene MCP contact sheet`](assets/mcp_realism_r5_58203_contact_sheet.png)

## Sensör ve annotation sözleşmesi

Deterministik CCTV output curve yalnız RGB’ye uygulanır. Ham Unreal PNG’leri
`raw/images_pre_sensor/` altında byte-for-byte korunur; sensörlü RGB
`raw/images/` altında yer alır. `raw/sensor_response_manifest.json`, config ve
script SHA-256’ları ile 16 kare için pre/post RGB hash’lerini pinler ve
`geometry_changed=false`, `masks_changed=false`, `depth_changed=false`
alanlarını taşır. İşlem korunmuş girdiden tekrar üretildiği için idempotenttir.

Bu curve ölçülmüş sensor response değildir. Önceki dört-kare audit, ham r5’te
gerçek referansa göre fazla black crush gösterdiği için black pedestal/gamma
fallback’i eklenmiştir. İşlem kayıp shadow detayını geri üretmez;
fixed-exposure grey-card/empty-chamber seti gelene kadar görsel kalibrasyon
katmanıdır. Bbox’lar sensörlü RGB’den veya semantic union’dan değil, aynı
kameranın physical-instance visible maskelerinden çıkar.

## Görsel ve fiziksel revizyon

- 40/40 cm used-steel tabla, aynı eksen ve sample temas ilişkisi.
- Front access, yaklaşık 90° açık safety-glass kapı, gasket/hinge/handle ve
  görünen workshop derinliği.
- Upper-platen kotunda back/left/right aluminium channel + opal diffuser; üç
  physical RectLight ve ayrı, düşük enerjili diffuse-return kontrolü.
- Ana gri powder-coat yüzeyleri dielectric V4; düzensiz ve mm’ye yakın dark
  stipple proxy; mavi yalnız aperture/workshop aksanı.
- Concrete V8 daha dar albedo aralığı, iki noise ölçeği, pore/aggregate ve aynı
  `EBIS_INSTANCE`; RGB için 8-frame Lumen/TSR warm-up, AO radius 3,5 cm.
- Contact sheet iki kamera ve iki numune şeklini bütün partition’larla birlikte
  gösterir; `exclude` kareler normal train manifest’ine girmez.

## Tarihsel lineage

- `output/realism_r5_sensor_calibration_58200`: önceki dört-kare, depth’siz
  sensörlü görsel/annotation calibration.
- `output/realism_r5_calibration_58200`: aynı dört karenin sensör-öncesi engine
  kalibrasyon girdisi.
- `output/pilot_release_v4`, `hero_release`, `mcp_hero` ve mevcut determinism:
  önceki v1 geometri için tarihsel teknik baseline.

Bu kayıtların hiçbiri güncel `realism_r5_full_58200` yerine kanonik release
kanıtı değildir; eski MCP/determinism sonucu da yeni fiziksel sahneye mal
edilmez.

## Açık gerçeklik farkları ve kabul kapıları

1. Üst tabla yan bandı ve bazı workshop yüzleri gerçek CCTV’ye göre hâlâ fazla
   koyu; surface scan/roughness ve gerçek ambient ölçümü gerekir.
2. Concrete ve sac external PBR scan kullanmaz; procedural noise yakından CG
   görünür. Düzenli primitive proxy production asset’i değildir.
3. Kapı/CAD, kamera intrinsics/distortion ve sensor response ölçülmemiştir.
4. Camera 02 gerçek verisindeki insan/el ve gerçek workshop dağılımı simüle
   edilmez.
5. 100-kare stratified iki kişilik bbox/görsel QC tamamlanmadı.
6. Güncel fiziksel sahne için resmî MCP round-trip pinlendi; aynı-seed iki
   bağımsız editor determinizmi henüz pinlenmedi.
7. Frozen gerçek testte YOLO ablation sonucu yoktur.

Kullanıcıdan ölçüm/materyal/review paketi
[`USER_SUPPORT_AND_REVIEW.md`](../../docs/USER_SUPPORT_AND_REVIEW.md), kalan
insan QC/determinizm ve nano ablation sırası
[`INTENSIVE_14_DAY_ENGINEERING_PLAN.md`](../../docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
içindedir.
