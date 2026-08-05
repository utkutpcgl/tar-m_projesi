# EBIS gerçekçilik tekrarı — pass 1/6

Tarih: 2026-07-29  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: bir adet bounded materyal/ışık/geometri iyileştirme ve kanıt turu.

## Sonuç

En büyük güvenli kazanım Blender'da betonun düz procedural görünümünü,
tabla temasını ve hazne içi bounce'u; Unreal'da ise yanlış ölçekli cellular
betonu, LED U-segment uzunluğunu, üst tabla materyalini ve genel exposure'u
düzeltmek oldu. Seçilen iki pilot da instance-aware annotation validator'ını
geçti ve yerel dosyalar 3090 çalışma alanındaki kaynak/çıktılarla SHA-256
eşleşti.

Bu tur bir **surface calibration pilotu**dur. Depth kapalıdır; yeni kaynak
revizyonlarında MCP round-trip tekrarlanmadı; 100-kare insan QC'si ve YOLO
ablation yoktur. Dolayısıyla production, fotogerçekçi dijital ikiz, engine
üstünlüğü veya model kazancı iddia edilmez.

## Yeniden incelenen bağımsız referans kanıtı

Önceki forensik örneklemin gerçek pikselleri yeniden açılıp geometri,
materyal, ışık ve occlusion açısından ayrı geçişlerde incelendi:

- [altı LED RGB task/batch, erken–orta–geç](ebis-blender/reports/qc/reference_forensics/led_cam10_cam11_batches.png);
- [2026-01-16 LED zamansal örnek](ebis-blender/reports/qc/reference_forensics/led_160126_temporal_18.png);
- [REF cam-10 erken–orta–geç](ebis-blender/reports/qc/reference_forensics/ref_cam10_early_mid_late.png);
- [REF cam-11 A](ebis-blender/reports/qc/reference_forensics/ref_cam11_a_early_mid_late.png) ve
  [REF cam-11 B](ebis-blender/reports/qc/reference_forensics/ref_cam11_b_early_mid_late.png).

Toplam forensik kapsam 52 LED RGB + 33 IR/gri ton, 18 `REF-*` klasörü ve
2024-12-02–2026-01-21 aralığındaki 85 benzersiz karedir. Bu 85 kare,
20.041 dosyalık arşivin tamamının tek tek review edildiği anlamına gelmez.
IR kareler renk/response kalibrasyonu için değil, değişmeyen cabinet,
tabla, kamera ve kapı topolojisini çapraz kontrol etmek için kullanıldı.

[Tek birleşik gerçek–Blender–Unreal sheet](reports/qc/multi_repeat_pass1_reference_blender_unreal.png)
çıktı piksellerini referansın altına aynı genişlikte koyar. Kaynak forensik
ve karar kaydı:
[REFERENCE_FORENSICS_RGB_IR_2026-07-29.md](ebis-blender/reports/qc/REFERENCE_FORENSICS_RGB_IR_2026-07-29.md).

## En büyük farklar ve bu turdaki müdahale

| Alan | Gerçek referansta | Tur başındaki baskın sentetik sorun | Uygulanan değişiklik |
| --- | --- | --- | --- |
| Beton kalıp yüzü | birkaç ölçekte gözenek, uzun/düşük kontrast kalıp izi, lokal kırık ve agrega | Blender fazla yumuşak; Unreal büyük cellular/marble lekeli | Blender'a anisotropic object-space cast streak + mikro relief ve daha yoğun küçük pore; Unreal noise ölçekleri piksel sonucuna göre ters yönde düzeltildi, iri protrusion küçültüldü |
| Üst/alt tabla | kullanılmış dairesel çelik; sample ile yakın temas; üst altı daha mat/oksitli | üst tabla fazla steril/parlak; Unreal iç içe disk/bullseye | Blender üst tabla rough/diffuse yapıldı; Unreal tek tam çap tabla ve ayrı `M_UpperContactSteelV1` kullandı |
| LED | üst tabla alt kotunda back+left+right boyunca ince opal U-diffuser; temas yakınına lokal katkı | sol segment kısa; diffuse return/contact yetersiz | Unreal sol/sağ/back uzunluğu `46/46/57 cm`; iki engine'de bounded contact spill/bounce ve daha düşük global fill |
| İç sac | gri pebbled/hammertone, yerel mavi paneller, kullanılmış yüzey | geniş düz/plastik alanlar | iki engine'de metal/dielectric ayrımı, roughness ve mikro-normal revize edildi |
| Annotation | tag kâğıt/tabla arkasında kısmen veya tamamen saklanabilir | görünmeyen instance'a bbox sızması riski | görünür instance maskesi kaynaklı bbox; fully hidden/outside-frame metadata'da kalır, normal YOLO satırı almaz |

Belirsiz `40 cm` tabla ve cabinet/camera ölçüleri gerçek ölçüm değildir.
Fiziksel olarak makul, kayıtlı fallback aralığı olarak korunmuştur; yanlış
hassasiyet iddia edilmemiştir.

## Seçilen Blender pilotu

- Kaynak: `scripts/generate_ebis.py` v1.7.4,
  SHA-256 `cc5e4254...4bd`.
- Run: [`realism_v5_2_surface_p1d_54120`](ebis-blender/output/realism_v5_2_surface_p1d_54120).
- Görsel: [8-kare contact sheet](ebis-blender/reports/qc/realism_v5_2_surface_p1d_54120_contact_sheet.png).
- Validator: [PASS](ebis-blender/output/realism_v5_2_surface_p1d_54120/validation.json);
  8/8 kare, iki kameradan 4'er kare, 22 fiziksel RFID, 38 binary maske,
  54 hash kontrolü, partition `4 standard / 2 hard / 2 exclude`.
- Render: RTX 3090 OptiX, `1280×720`, 64 spp, toplam `44,998 s`.
- Pin: [release manifest](ebis-blender/evidence/release/realism_v5_2_surface_p1d_54120_manifest.json).

`surface_p1`, `p1b` ve `p1c` ara koşuları karar kanıtıdır, seçilen release
değildir. Özellikle `p1b` concrete midtone'u aşırı yükseltti; gerçek
referansa yaklaşmak için contact bounce kademeli azaltıldı.

## Seçilen Unreal pilotu

- Kaynak: `Content/Python/ebis_scene.py`,
  SHA-256 `26c0fe0a...c78`; physical revision
  `surface_realism_pass1_2026-07-29`.
- Run: [`realism_r6_surface_p1f_58200`](unreal-ebis/output/realism_r6_surface_p1f_58200).
- Görsel: [4-kare contact sheet](unreal-ebis/reports/qc/assets/realism_r6_surface_p1f_58200_contact_sheet.png).
- Validator: [PASS](unreal-ebis/output/realism_r6_surface_p1f_58200/validation.json);
  4/4 kare, 2 cam-10 + 2 cam-11, 2 cube + 2 cylinder, 14 visible + 14
  amodal maske, partition `3 standard / 1 exclude`, dört concrete
  camera×shape bbox hücresi de normalize koordinatta `abs ≤0,06`.
- Engine: UE 5.8.1 / RTX 3090, `1280×720`, depth kapalı, engine süresi
  `10,05 s`.
- Pin: [release manifest](unreal-ebis/evidence/release/realism_r6_surface_p1f_58200_manifest.json).

`p1`–`p1e` ara koşuları seçilmedi. İlk noise ölçeği dev cellular desen
üretti; Unreal Material Noise `Scale` davranışının Blender'daki spatial
scale sezgisiyle aynı olmadığı ancak gerçek çıktı pikselleri incelenince
görüldü. `p1e` exact-contact denemesi siyah üst sınırı kaldırmadı ve
partition dağılımını `1 standard / 3 exclude` seviyesine bozdu; `p1f`
0,05 cm kayıtlı film/gap fallback'ine döndü.

## Temsilî piksel kontrolü

Makine-okunur tam sonuç:
[multi_repeat_pass1_pixel_audit.json](reports/qc/multi_repeat_pass1_pixel_audit.json).
Değerler Pillow RGB→L, tam kare ve class-1 concrete bbox ROI'sinde
`p5 / p50 / p95 / mean` ölçümüdür.

| Kare | Tam kare p5/p50/p95; mean | Concrete ROI p5/p50/p95; mean |
| --- | --- | --- |
| Gerçek cam-10 | `39/107/242; 114,9` | `59/144/255; 144,8` |
| Blender cam-10 | `47/143/217; 137,3` | `56/146/182; 142,3` |
| Unreal cam-10 | `5/125/229; 129,6` | `5/170/215; 140,4` |
| Gerçek cam-11 | `36/121/222; 120,1` | `65/134/254; 140,0` |
| Blender cam-11 | `45/145/215; 135,4` | `95/149/182; 146,3` |
| Unreal cam-11 | `5/80/225; 98,3` | `5/112/221; 123,3` |

Okuma:

- Blender concrete mean'i iki temsilî gerçek kareye yakın; buna rağmen
  gerçek kırık/agrega/LED highlight kuyruğu (`p95=254–255`, `%5,61–7,92`
  clip) sentetikte yok denecek kadar azdır. Ortalama eşleşmesi materyal
  eşleşmesi değildir.
- Unreal cam-10 mean'i yaklaşırken concrete medyanı yüksek, `p5=5` üst
  temas siyah bandından etkileniyor. Cam-11 global ve concrete midtone'u
  belirgin düşük.
- Altı kare population calibration değildir. Aynı fiziksel sahnenin
  grey-card/ChArUco, fixed exposure ve ölçülü ROI çifti gelmeden response
  curve fit edilmemelidir.

## İki engine arasında taşınan ders

Blender'dan Unreal'a fiziksel U-LED, üst tabla altında ayrı rough contact
yüzeyi, beton cast streak/pore ölçeği ve global exposure yerine lokal bounce
fikri taşındı. Unreal'ın isolated visible/amodal pass sözleşmesi Blender
partition kontrolünü daha katı yorumlamak için kullanıldı. Her iki motorda
aynı hatanın adı değişse de çözüm aynıdır: önce doğru topoloji/ölçek,
sonra materyal, en son sensör cevabı.

## Kalan materyal açıkları

Öncelik sırasıyla:

1. Gerçek cube/silindir için kalıp yüzü, uç yüzü ve kırık köşe ayrı
   cross-polarized PBR/photogrammetry capture; procedural beton hâlâ en
   büyük sentetik ipucudur.
2. Cam-10/cam-11 ChArUco intrinsics + distortion ve aynı exposure'da
   grey-card/empty-chamber/steel-platen çekimi.
3. Unreal'da üst tabla–sample siyah boundary bandı: shadow bias/contact,
   one-sided normals ve Lumen geometry debug view ile ayrıştırılmalı.
4. Unreal cam-11 physical fill ve exposure; histogramı yükseltmek için
   post pedestal değil, yanlış visibility/occlusion varsa önce geometri.
5. Silindire konforme basılı kâğıt ve kâğıt altında kontrollü
   `%30 altı / eşik çevresi / %30 üstü` görünürlük slice'ları.
6. Kapı camı, conta, kol, menteşe ve operatör/kol occluder'ları için gerçek
   ölçüm ya da lisanslı tarama; bugünkü workshop hâlâ proxy'dir.

## Sonraki en yüksek değerli tur

Aynı gerçek numune ve boş hazneyi iki kamerada fixed exposure ile çekip bir
grey card ve ChArUco karesini eklemek; aynı numunenin en az dört ışık
yönünde cross-polarized yakın planını almak. Bu tek veri paketi exposure,
fisheye, steel/concrete roughness ve color response belirsizliklerini aynı
anda azaltır. O gelene kadar sonraki sentetik tur, Unreal siyah temas
bandının debug-pass ayrıştırmasına ve Blender'da scan gerektirmeyen sınırlı
edge-chip/aggregate atlasına odaklanmalıdır.

YOLO kabul kapısı değişmedi: frozen gerçek test split, en küçük model,
en az üç seed; `R`, `R+B-1N`, `R+U-1N` ve ancak gerekirse `R+B+U-1N`.
Gerçek test metriği ve slice recall artmadan sentetik fayda iddia edilmez.
