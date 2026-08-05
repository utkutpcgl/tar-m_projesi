# İki haftalık Unreal-EBIS gerçekçilik backlog’u

Amaç “daha güzel hero” değil; gerçek LED domain gap’ini ölçülebilir biçimde azaltıp frozen gerçek testte detection faydası aramaktır. Mevcut Unreal v1 teknik baseline’dır ve Blender’dan daha gerçekçi kabul edilmemiştir.

## Öncelik sırası

| Sıra | İş | Beklenen etkisi | Kabul kapısı |
| ---: | --- | --- | --- |
| 1 | Makine/tabla/numune fiziksel ölçüsü ve iki kamera checkerboard intrinsics/extrinsics | kompozisyon ve scale gap | reprojection + ölçü raporu |
| 2 | Ölçülü/bevel’li CAD veya temiz mesh importu | basic-shape/kenar gap | silhouette ve landmark QC |
| 3 | Gerçek beton/çelik yüzeyinden lisanslı albedo-normal-roughness scan | en büyük görsel gap | matched crop histogram/texture review |
| 4 | LED konumu, diffuser ölçüsü, exposure/WB örneği | clipping ve gölge gap | camera×light QC, clipping raporu |
| 5 | Sensor noise, sharpening, chromatic/lens distortion | CCTV domain gap | RGB ve mask aynı geometrik transform |
| 6 | RFID film curl, yapıştırıcı, edge lift ve gerçek kalınlık | tiny-object görünümü | instance mask continuity |
| 7 | Camera 02 kapı/atölye CAD veya kontrollü backplate | background FP gap | lisans + per-camera FP analizi |

## On iş günü

- Gün 1–2: Ölçü/intrinsics toplama, coordinate ve CAD kabul sözleşmesi.
- Gün 3: CAD import; Unreal/Blender’da aynı mesh/scale hash’i.
- Gün 4: PBR scan ingest; dört sabit seed gerçek crop kıyası.
- Gün 5: LED/sensor kalibrasyonu, clipping ve noise ölçümü.
- Gün 6: RFID mesh/material ve plate-gap görünürlük testleri.
- Gün 7: 16-kare calibration pilotu, validator ve contact sheet.
- Gün 8: 100-kare stratified iki kişilik bbox/artefakt QC.
- Gün 9: Yalnız PASS standard’dan 1N sentetik üretim; render maliyeti.
- Gün 10: Nano `R`, `R+B-1N`, `R+U-1N` toplu gerçek-test raporu ve GO/HOLD.

## Bounded kararlar

- CAD/intrinsics yoksa camera fit’i daha fazla elle tune etmeyin.
- Gerçek surface scan yoksa prosedürel noise node sayısını artırmayı kalite ilerlemesi saymayın.
- Unreal görüntüsü Blender’dan niteliksel olarak daha zayıfken büyük Unreal dataset üretmeyin.
- 100-kare bbox QC PASS olmadan model eğitmeyin.
- 1N üç-seed ablation fayda göstermeden 2N/10k büyütmeyin.
- Person/el sentetiğini ancak gerçek-test hata analizi bunun baskın gap olduğunu gösterirse ekleyin.

## Devir çıktıları

İki hafta sonunda ölçü dosyası, camera calibration JSON’u, CAD/PBR asset lisansı ve hashleri, yeni config/generator hashleri, 100-kare QC tablosu, render maliyeti ve üç engine koşullu nano ablation raporu bulunmalıdır. Negatif sonuç da geçerlidir; “Unreal daha gerçekçi” iddiası yalnız görsel tercihle yazılmaz.
