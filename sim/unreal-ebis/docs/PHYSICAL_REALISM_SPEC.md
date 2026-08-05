# EBİS fiziksel ve görsel gerçeklik sözleşmesi — Unreal

Revision: `2026-07-30-r4`. Bu dosya Unreal scene generator için kanonik görsel tariftir. Ölçülmeyen değerler config fallback’idir; CAD veya gerçek ölçü sayılmaz.

## Kanıt ve ortak asset kuralı

Öncelik: doğrudan ölçüm → üretici CAD → checkerboard/ChArUco → multi-view oran → single-view fit → artistik tercih. Yeni değerler [`ebis_physical_measurements_template.json`](../configs/ebis_physical_measurements_template.json) içinde kaynak dosya adıyla tutulur. Engine kıyasında Blender ve Unreal aynı measurement/CAD/PBR kaynağını kullanır.

## Kutulu press ve kapı

- EBİS açık oda değildir. Önünde büyük safety-glass pencereli, siyah gasket’li ve metal framed access door olan kapalı cabinet’tir.
- Referans ürün fotoğrafında kapı sol menteşeli ve yaklaşık 90° açıktır. Leaf, glass, gasket, hinge, handle ve chamber aperture ayrı geometry olmalıdır.
- `camera_door/cam-11` solda open door/workshop aperture’ünü kadrajın yaklaşık üçte biri kadar görür. `camera_angled/cam-10` hazneye daha doğrudan bakar.
- Back/left/right/floor/roof kapalı yüzeyler ve ön sac kalınlığı vardır; siyah sonsuz boşluk veya düz proxy oda reddedilir.
- Rounded light-grey service hatch, seam/gasket ve dört countersunk screw gerekir.

Fallback chamber `62 × 56 × 76 cm`; ölçüm değildir.

## Tabla ve sample

- Üst/alt iki büyük, aynı eksenli circular used-steel platen sample’ı fiziksel olarak sıkıştırır.
- Sample iki yüzeye temas eder; gap/penetration hard fail.
- Karşılaştırma fallback çapı iki tabla için de `40 cm`; 18 cm cube edge’in `2.22×`ı. Önceki 61–68 cm çaplar kullanıcı tarifine göre büyüktü.
- Apparent image ratio perspective’e bağlıdır: cube’da yaklaşık `1.6–1.7`, cylinder’da yaklaşık `3.0`; fiziksel çap bu piksel oranından türetilmez.
- Radial machining, scratch, cement dust/grease, tonal patch ve bevel okunur. Mirror/chrome veya clipped white disc kabul edilmez.
- Lower platen gövdesinden ayrı, fallback `39.4 cm` çap ve `0.08 cm`
  kalınlıkta ince used-steel contact face taşır; üst kot `23.55 cm`,
  specimen gap `0`dır. `dry_used / dusty_used / damp_residue`
  profilleri bağımsız seed'li bounded augmentation'dır; measured BRDF
  veya gerçek prevalans değildir. Geometri, profil ve temas metadata ile
  validator'da doğrulanır.
- Lower platen kontrollü debris ve loose/plate-gap tag alabilir. Debris
  aktör merkezleri gerçek lower-top kotuna göre yerleşir; tabla altında
  gizli veya santimetre ölçekli dekoratif taş kuyruğu reddedilir.

## U biçimli LED diffuser

- Tek floating RectLight veya büyük beyaz wall panel değildir.
- Upper platen alt seviyesine yakın back + left + right boyunca dar recessed channel’dır; door opening’de segment yoktur.
- Üç segmentin aluminium housing, opal acrylic cover ve gizli physical light contribution’ı ayrıdır.
- Upper platen diffuser’ı occlude eder; wall spill, contact shadow ve steel reflection gerekir.
- Diffuser doğrudan clip olabilir; concrete midtone ve geniş platen alanı korunur.
- Fallback `5000–6500 K`; screenshot’tan Kelvin iddia edilmez. Lux/CCT/CRI veya IES gelince Unreal lumens/profile buna bağlanır. Manual exposure pinlidir.

## İç sac ve PBR

- Ana görünüm koyu/gri hammered/orange-peel powder-coat, mm ölçekli pebbled normal ve macro mottling’dir.
- Dataset bazı regionlarda güçlü blue pebbled panel gösterirken kullanıcı gri duvar tarif eder. Bu makine varyantı doğrulanana kadar ana chamber grey, blue yalnız gerçek local panel/aperture accent’tir; tüm duvar random renk değiştirmez.
- Texture scale, roughness ve normal import ayarları auditable olmalıdır. Hücresel wallpaper veya düz plastik görünüm reddedilir.
- Unreal BaseColor sRGB açık; roughness/metallic/normal uygun non-color importta; normal direction ve channel packing doğrulanır.

## Beton

- Ana detay dünya ölçeğindedir: ölçüm gelene kadar ortak fallback pore/pinhole çapı `0.5–4 mm`, görünen aggregate/mortar lekesi `2–12 mm`, edge chip/spall boyutu `3–20 mm`dir. Measured scan/cetvelli crop gelince aynı aralık Blender ve Unreal’da birlikte güncellenir.
- Projected-pixel QC ayrı katmandır: kanonik 1920×1080 cam-10/cam-11 görüntülerinde okunabilir pore/aggregate çoğunlukla `2–15 px`, edge chip/spall yaklaşık `5–40 px` görünür. Bu bant texture/geometry ölçeğinin kaynağı değildir; çözünürlük veya FOV değişince yeniden hesaplanır.
- Uniform cellular noise gerçek değildir. Pore/pinhole, mortar/aggregate, colour/roughness heterojenliği ve face-to-face variation gerekir.
- Cube edges küçük bevel + bounded chipped/spalled geometry; cylinder side/end farklı yüzeydir.
- Scan/photogrammetry tercih edilir. Procedural V6/V7 yalnız measured texture gelene kadar fallback’tir.
- Normal yoğunluğu TSR shimmer/moire üretmemeli; fixed camera temporal QC yapılır.
- Üst tabla altında yük alan üst bantta fresh LED/IR'de tekrar eden
  ochre/koyu artık, güncel kaynakta küçük ve sığ opaque disc kümeleriyle
  kapsanır. Bunlar betonla aynı instance/semantic kimliğindedir,
  silhouette/bbox'u büyütmez ve ayrı independent RNG taşır. Translucent
  sphere depth-sort kabarcığı ve dışa şişen opaque sphere reddedilmiştir.
  Güncel disc proxy ölçülmüş prevalans/BRDF/yönlü streak değildir;
  ölçekli/polarize scan/decal geldiğinde Blender ile ortak asset'e
  çevrilmelidir.

## Görsel RFID

- Nominal yaklaşık `6 × 1 × 0.010–0.015 cm`.
- İnce amber/yellow translucent film, copper antenna/trace ve rounded/domed dark epoxy blob; kalın neon kart değildir.
- Side notch, clear coat, hafif bend/contact ve sınırlı adhesive edge lift bulunabilir.
- Sample face/side, lower debris ve top/bottom plate-gap physical placements desteklenir. Multipart film/copper/chip aynı `EBIS_INSTANCE` kimliğindedir.
- Plate-gap görünür şerit için visible/amodal policy korunur; yalnız amodal veya semantic union bbox yazılmaz.

## Kamera, SceneCapture ve sensor

- Kaynak 1920×1080 CCTV, wide/fisheye barrel distortion, vignette, sharpening halo, noise/compression ve chromatic fringe gösterir.
- Sample yatay merkezde; üst temas `y≈0.15–0.20`, alt çoğunlukla clipped.
- Concrete bbox framing hedefleri config’te kalır fakat intrinsics yerine geçmez.
- Calibration gelene kadar `92° horizontal FOV` visual-fit placeholder’dır. Distortion uygulanırsa RGB ve masks aynı geometric mapping’i paylaşır; noise/bloom maskeye uygulanmaz.
- Timestamp/overlay synthetic’e sabit bake edilmez.

## Temsilci gerçek kareler

Kök: `../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126`.

- `images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00000.png`
- `images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00399.png`
- `images/val/task_10_dataset_2026_01_23_12_54_24_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-2_frame-00421.png`
- `images/train/task_13_dataset_2026_01_23_12_04_05_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-3_frame-00000.png`
- `images/train/task_12_dataset_2026_01_23_08_53_31_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-4_frame-00000.png`
- `images/train/task_12_dataset_2026_01_23_08_53_31_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-4_frame-00411.png`
- `images/train/task_11_dataset_2026_01_23_07_32_53_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-6_frame-00000.png`
- `images/train/task_11_dataset_2026_01_23_07_32_53_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-6_frame-00304.png`

## Unreal release checklist

- Scene inventory: glass door/frame/gasket/hinges, closed chamber, 3 channel+opal+light segments ve iki source-tracked tabla. Gerçek ölçüm yoksa ikisi de açıkça `40 cm fallback` kalır; “measured” denmez. Service hatch+4 screws korunur.
- Clay/unlit 2×2 owner PASS before material tuning.
- BaseColor/Roughness/Normal debug render and texture import audit.
- Fixed seeds: clipping, black crush, Lumen leak, TSR shimmer, bbox framing/contact.
- Editor restart sonrası mask material compile ve GPU fence smoke.
- RGB/depth/visible/amodal count/uniqueness validator PASS.
- MCP loopback render + stop; 100-kare two-person QC before production.
- Kör owner + operatör review’unda ayrı overall medyanlar ve bütün ortak alt-eksen medyanları `≥3.0/5`; açık blocker yok.

İdeal sonuç shared physical assets, believable render, safe annotation ve frozen real-test model etkisinin birlikte kanıtlanmasıdır.
