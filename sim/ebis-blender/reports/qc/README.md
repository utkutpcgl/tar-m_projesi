# QC artefakt indeksi

Bu klasörde hem güncel release kanıtı hem de ayar ararken üretilmiş
tarihsel/development raporları bulunur. Dosya adında `TUNE` görmek güncel
release’in başarısız olduğu anlamına gelmez; kaynak/config hash’i ve aşağıdaki
pin belirleyicidir.

## Güncel v1.7.3 / v5.1 kanıtı

1. `REFERENCE_FORENSICS_RGB_IR_2026-07-29.md`
   85 benzersiz RGB/IR karenin görsel incelemesi, 20.041 dosyalık envanter ve
   değişmez/değişken parça kararı.
2. `realism_v5_1_distribution_gate_audit.md`
   Nihai 32-kare bbox dağılım kapısı; iki kamera × cube/cylinder dört hücre de
   `±0.03` görsel toleransta `PASS`.
3. `realism_v5_1_distribution_gate_contact_sheet.png`
   Aynı gate’in YOLO kutulu görsel özeti.
4. `realism_v5_1_referencefit_pilot_contact_sheet.png`
   8-kare, 1280×720/64 spp görsel pilot. Validator `PASS`; küçük-N bbox
   dağılım kararı için kullanılmaz.
5. `REALISM_REVISION_V5_2026-07-29.md`
   Uygulanan düzeltmeler, kalan görsel farklar ve production HOLD gerekçesi.
6. `real_vs_v5_1_cam10_cube.png`
   Gerçek cam-10 küp ile v1.7.3 `camera_angled` hero'nun etiketli doğrudan
   görsel karşılaştırması.
7. `real_vs_v5_1_cam11_cube.png`
   Operatör/kapı oklüzyonlu gerçek cam-11 küp ile v1.7.3 `camera_door`
   küp/tag hero'nun etiketli doğrudan görsel karşılaştırması.

Kanonik release manifesti:
`../../evidence/release/realism_v5_referencefit_manifest.json`.

## Development/tarihsel raporlar

`realism_v5_detection_domain_audit*`,
`realism_v5_1_framing_calibration*`,
`realism_v5_1_fisheye_calibration*`,
`realism_v5_1_yaw15_calibration*`,
`realism_v5_1_yawm30_calibration*`,
`realism_v5_1_bounded_yaw_calibration*` ve
`realism_v5_1_camera_conditioned_calibration*` ayar arama izleridir.
Karar kaydını korumak için silinmemiştir; güncel kaynak pin’i veya release
gate’i değildir.

`realism_v5_1_referencefit_pilot_audit.md` de yalnız sekiz kare içerir.
Door/cube hücresi `N=2` olduğu için `TUNE` sonucu release’i geçersiz kılmaz;
dağılım kararı `N=7–9` hücreli 32-kare gate’ten alınır.
