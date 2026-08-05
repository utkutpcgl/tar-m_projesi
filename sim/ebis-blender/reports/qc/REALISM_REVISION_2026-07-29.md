# Blender-EBİS tarihsel v1.6 gerçeklik revizyonu — 2026-07-29

> **SUPERSEDED:** Bu dosya `v1.6.0 / realism_v3_2` tarihsel
> checkpoint’idir. Güncel karar ve kanıt için
> [`REALISM_REVISION_V5_2026-07-29.md`](REALISM_REVISION_V5_2026-07-29.md)
> kullanılmalıdır.

## Sonuç

`realism_v3_2_pilot_53200`, yeni fiziksel tarif için **teknik calibration
PASS**'idir; fotogerçekçi dijital ikiz veya YOLO kazancı kanıtı değildir.
Kapalı cabinet/açık safety-glass kapı, 40/40 cm tabla, üst tabla kotunda üç
duvarı izleyen dar opal U-kanal, gri pebbled iç sac, küp/silindir ve fiziksel
RFID yerleşimleri aynı generator içinde bulunur.

## Doğrulanan kanıt

| Kontrol | Sonuç |
| --- | --- |
| Render | 8 × 1280×720, 64 Cycles sample, RTX 3090; 55,40 s toplam / 6,92 s ortalama |
| Kapsama | camera_door 4, camera_angled 4; cube 4, cylinder 4 |
| Annotation | 5 standard, 3 hard_occlusion, 0 exclude; 25 fiziksel RFID instance |
| RFID kararları | 14 standard, 4 hard, 3 outside-frame, 4 fully-occluded |
| Validator | `status=PASS`, `errors=[]`; 57 hash ve 41 binary mask kontrolü |
| Kaynak | generator SHA-256 `086dfc58…cbfea`; canonical config SHA-256 `2071f6d3…60e80` |
| BlenderMCP | Güncel v1.6 `.blend`; 209 nesne önce/sonra aynı, 1200×698 viewport, 1920×1080/128-sample OptiX PASS; proses/port kapalı |

Kanıtlar:

- [`validation.json`](../../output/realism_v3_2_pilot_53200/validation.json)
- [`run_manifest.json`](../../output/realism_v3_2_pilot_53200/run_manifest.json)
- [`contact sheet`](realism_v3_2_pilot_53200_contact_sheet.png)
- [`release manifest`](../../evidence/release/realism_v3_2_pilot_53200_manifest.json)
- [`historical v1.6 BlenderMCP pin`](../../evidence/mcp/pins_v1_6.json)
- [`historical v1.6 BlenderMCP render`](../../evidence/mcp/20260729T093942Z-d4702303/render.png)

Temsilci sekiz gerçek karede max-channel black-crush `%0,327–0,617`, clipped
highlight `%2,318–6,920` aralığındadır. Bu Blender pilotunda aynı basit
frame-level ölçümler sırasıyla `%0,027–2,894` ve `%0,934–1,767` oldu. Bu yalnız
pozlama sanity kontrolüdür; materyal veya model benzerliği metriği değildir.

## Görsel olarak düzeltilenler

- Önceki 61–68 cm proxy tablalar yerine iki motorda ortak 40 cm disk kullanıldı.
- Büyük beyaz panel/tek ışık yerine aluminium housing + opal cover + gizli area
  source içeren back/left/right U-kanalı kuruldu.
- Ana iç yüzler mavi plastik oda olmaktan çıkarılıp iki ölçekli gri
  hammertone/roughness yüzeye çevrildi; mavi yalnız aperture/workshop aksanıdır.
- Kapı kanadı 90° açık glass/gasket/frame/hinge/handle parçalarına ayrıldı ve
  camera_door görüşüne workshop derinliği eklendi.
- Üst/alt tablada kullanılmış çelik, wear zone ve kontrollü diffuse bounce;
  betonda çok ölçekli ton/roughness, pore ve edge damage artırıldı.

## Açık gerçeklik farkları

1. Kutu/kapı/tabla ölçüleri fotoğraf-fit'tir; CAD veya cetvelli ölçüm değildir.
2. Concrete hâlâ procedural ve bazı karelerde gerçek kalıp yüzüne göre fazla
   açık/düzdür. Ölçekli scan ile mould-face, aggregate ve broken-edge ayrılmalı.
3. Pebbled sac gerçek normal/height scan yerine procedural fallback'tir.
4. Workshop basit geometry proxy'dir; gerçek backplate/CAD değildir.
5. Kamera 2,8 mm görsel fit ve tahmini distortion kullanır; ChArUco intrinsics
   olmadan lens eşleşmiş sayılmaz.
6. Güncel BlenderMCP scene-info/viewport/1080p OptiX round-trip PASS'tir;
   owner clay/material/light review'ı, güncel determinizm ve 100-kare iki
   kişilik QC yapılmadan bu revizyon production freeze değildir.

Kullanıcının en yüksek değerli katkıları ve review formatı
[`USER_SUPPORT_AND_REVIEW.md`](../../docs/USER_SUPPORT_AND_REVIEW.md), günlük
uygulama ve YOLO karar kapıları ise
[`INTENSIVE_14_DAY_ENGINEERING_PLAN.md`](../../docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
içindedir.
