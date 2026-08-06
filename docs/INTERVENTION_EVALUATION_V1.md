# Crop segmentasyonu ve bitki müdahalesi — ayrıntılı karar raporu

Tarih: 5 Ağustos 2026  
Durum: kabul edilmiş global model + kabul edilmiş RiceSEG uzmanı; eşikler hedef setlerde yeniden ayarlanmadı.

## Yönetici sonucu

Global modelin seen-validation mIoU'su `0.805`; semantic weed-component hit proxy'si `%66.4`. Ancak dondurulmuş güvenli aksiyon politikasının component hit recall'ı yalnız `%27.5` ve weed-pixel recall'ı `%14.0`. Bu nedenle model iyi bir algı tabanı olsa da mevcut policy ile saha püskürtme onayı yoktur.

Küçük-weed bulgusu sayısaldır: `<14 px` semantic-component hit `%24.1`, tüm boyutlarda `%66.4`; safe-action küçük hit yalnız `%2.0`. Pooled crop-point hit `%0.5` olsa da worst seen dataset `WE3DS` içinde `%4.6`; safety ortalamayla geçirilmez.

RiceSEG uzmanı eğitime girmeyen 604-kare calibration split'inde crop IoU `0.802`, weed IoU `0.222` üretir. Bu panel önceki specialist seçiminde kullanıldığı için untouched final test değildir. Güvenli aksiyon eşiği pirinç üzerinde kalibre edilmediği için safe-action recall çok düşüktür; bu sonuç 'güvenli ama etkisiz/no-spray' davranışıdır.

En kısa MVP yolu noktasal/mikro ilaçlamadır; çünkü mevcut semantic maske ile gerekli proxy'lerin çoğu ölçülebilir. Mekanik sökme ve lazer için kök/crown veya meristem keypoint etiketi, kamera–alet kalibrasyonu ve mm cinsinden hata zorunludur. Bugünkü rapor bu iki yöntemi başarısız saymaz; ölçülemez sayar.

## Önceki raporda neden yoktu?

Önceki pipeline mIoU/IoU ve çok temkinli piksel-level spray riskine odaklandı. Mevcut bağlı-komponent ölçümü bir weed proxy'sini ancak maskenin en az %50'si bulunursa 'tespit' sayıyordu. Bu spot spray için gereğinden katı, kök/meristem hedefi için ise yetersizdi. Ayrıca veri true instance, root, stem veya meristem etiketi taşımıyor ve removal aktüatörü/GSD henüz sabitlenmemişti. Yeni evaluator bu eksikleri gizlemeden ayrı proxy'ler üretir.

## Sınıflar ve iki çıktı modu

- `target_crop`: korunacak hedef mahsul.
- `other_vegetation`: bu hedef ürün tanımına göre istenmeyen/diğer bitki; botanik tür instance'ı değildir.
- `background`: toprak, su, residue ve bitki olmayan alan.
- `ignore`: etiketi güvenilir olmayan piksel; metrik paydasına girmez.
- `semantic_argmax`: modelin en olası sınıfı; algı kapasitesi, doğrudan spray izni değil.
- `frozen_safe_action`: kaynak validation'da seçilmiş weed threshold + belirsizlik filtresi + predicted-crop guard. External sette retune edilmez.

### Dondurulmuş policy'nin exact değerleri

- Global checkpoint: `default weed 0.995; unknown-crop weed 0.995; crop guard 0.400; min confidence 0.550; min margin 0.150; max entropy 0.850; crop dilation 5 px`.
- Global crop override'ları: `crop_id 0: 0.990, crop_id 2: 0.985, crop_id 3: 0.990, crop_id 5: 0.999, crop_id 6: 0.999, crop_id 7: 0.999, crop_id 8: 0.999, crop_id 9: 0.999`.
- Rice specialist checkpoint: `default weed 0.999; unknown-crop weed 0.999; crop guard 0.400; min confidence 0.550; min margin 0.150; max entropy 0.850; crop dilation 5 px`.
- Rice checkpoint crop override'ları: `crop_id 0: 0.999`.
- Bu eşikler deployment crop injury/actuator outcome'u ile kalibre edilmiş safety sertifikası değildir; yalnız checkpoint'te saklı source-validation policy'sidir.

## Müdahale yöntemine göre minimal başarı ölçüsü

| Yöntem | Birincil gerçek saha ölçüsü | Bugün ölçülen proxy | Eksik zorunlu kanıt |
|---|---|---|---|
| Mikro/spot ilaçlama | weed'e ulaşan doz; crop deposition/injury; missed-weed rate | safe component any-hit, action-point precision, 0/5/10/20 px footprint crop collision | nozzle footprint/deposition, GSD, hız/gecikme, rüzgâr |
| Mekanik sökme/gripper | root/crown içinde tool localization; crop clearance; successful removal | semantic component centroid error (px ve eşdeğer yarıçap) | root/crown keypoint, depth, mm calibration, tool geometry/pose |
| Lazer | meristem/stem hit rate; mm error; crop collateral; enerji/weed | canopy-center proxy; raster işlem varsa %90 mask coverage | meristem/stem etiketi, beam çapı, dwell/energy, geometry |
| Termal/elektrik temas | doğru temas noktası, süre/enerji ve crop clearance | action-point/center proxy | temas noktası etiketi, 3B yüzey, alet footprint'i |
| İntra-row hoe | crop konumu/sırası ve crop injury; lateral mm error | crop segmentation yalnız dolaylı | crop-center/row etiketi, encoder zamanlama, mm calibration |

Lazer için tüm bitkinin eksiksiz segmentasyonu evrensel birincil hedef değildir: tek-shot sistemde kritik olan çoğu zaman apikal meristem veya stem'dir. Tam mask coverage ancak konturu tarayarak enerji uygulayan tasarımda birincil olur.

## Metrik tanımları

- `component hit (any)`: GT semantic weed connected component üzerinde en az bir tahmin pikseli. Spot müdahalenin en iyimser alt sınırı.
- `coverage@10/50/90`: component alanının en az belirtilen oranının bulunması. %90 yalnız alanı tarayan/kaplayan müdahaleye yakındır.
- `action point`: her predicted component içindeki distance-transform maksimumu; şeklin içindeki en derin piksel.
- `point precision`: valid action point'lerin gerçekten GT weed üzerinde olan oranı.
- `crop collision r`: action merkezli r-piksel dairesel footprint'in GT crop'a değme oranı. Fiziksel deposition modeli değildir.
- `center proxy`: en fazla overlap eden prediction centroid'i ile GT semantic-component centroid'i arasındaki hata. Root/crown/meristem değildir.
- Boyut binleri: `<14 px`, `14–28`, `28–56`, `>=56 px` eşdeğer çap. 14 px DINOv2 patch ölçeğidir; bu botanik boyut değil görüntüdeki apparent size'dır.

## Sonuç tabloları

| Set | N | mIoU | Crop IoU | Weed IoU | Semantic hit | <14px semantic hit | Safe hit | <14px safe hit | Safe point precision | Crop point hit | <14px payı |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| PhenoBench | 772 | 0.781 | 0.853 | 0.506 | %56.5 | %21.5 | %22.6 | %0.1 | %91.4 | %1.8 | %27.4 |
| ACRE | 200 | 0.692 | 0.717 | 0.422 | %71.3 | %11.7 | %16.3 | %0.0 | %96.2 | %0.6 | %1.6 |
| ROSE | 250 | 0.824 | 0.803 | 0.691 | %70.6 | %14.4 | %54.5 | %0.1 | %78.2 | %0.2 | %31.4 |
| WE3DS | 389 | 0.691 | 0.792 | 0.282 | %50.8 | %25.3 | %18.7 | %3.8 | %88.0 | %4.6 | %24.0 |
| WeedsGalore | 26 | 0.658 | 0.471 | 0.553 | %56.7 | %41.4 | %24.6 | %6.4 | %87.0 | %0.0 | %72.1 |
| Sorghum test | 25 | 0.828 | 0.796 | 0.695 | %96.7 | %0.0 | %87.4 | %0.0 | %84.5 | %0.0 | %0.5 |
| SugarBeets robot | 283 | 0.577 | 0.518 | 0.236 | %44.0 | %17.2 | %8.0 | %0.3 | %67.0 | %18.2 | %42.2 |
| WeedMap UAV | 95 | 0.349 | 0.000 | 0.125 | %7.0 | %4.6 | %0.1 | %0.0 | %13.0 | %72.5 | %92.8 |
| RiceSEG calibration | 604 | 0.616 | 0.802 | 0.222 | %39.9 | %32.0 | %0.7 | %0.1 | %86.2 | %0.0 | %57.5 |
| Early-rice transfer | 224 | 0.515 | 0.502 | 0.131 | %22.8 | %19.6 | %0.3 | %0.0 | %29.6 | %14.8 | %87.0 |

`point precision=ölçülemez`, model/policy hiç aksiyon noktası üretmediyse paydanın sıfır olduğu anlamına gelir; başarı değildir.

`RiceSEG calibration` training-path-disjoint demektir: 604 kare eğitime girmedi, fakat geçmiş specialist model/doz/seed seçiminde kullanıldı. Bu nedenle final untouched test diye yorumlanamaz. Early-rice de training-unseen fakat aynı geçmiş selector'ın development panelidir.

## Aggregation ve hedef ağırlığı

Crop'a zarar gibi safety ihlalleri ortalama skorla telafi edilmez; worst-field/hard gate olarak kalır. Safety geçtikten sonra semantic model seçimindeki mevcut `%60 target-like + %25 breadth + %15 lower-tail` mantığı method-specific metriklere uygulanabilir. Ancak deployment crop'u, platformu ve aktüatörü sabitlenmeden hangi datasetin target-like sayılacağı yeniden tahmin edilmez. Bu nedenle bugün tek bir karışık 'removal skoru' yerine dataset/method tablosu raporlanır; büyük datasetler piksel sayısıyla diğer alanları bastırmaz.

## İyi/kötü olunan veriler: en olası ilk neden

| Veri | En olası ilk neden | İkincil etken / sınır |
|---|---|---|
| ROSE | Yakın robot görünümü ve büyük/ayrışmış bitki footprint'i eğitim–validation arasında iyi eşleşiyor. | Aynı saha coğrafyası paylaşıldığı için skor tam yeni-tarla genellemesi değildir. |
| Sorghum | Aynı kaynak dağılımı, büyük ve net bitkiler; hedef ürün eğitime doğrudan girdi. | Test yalnız 25 kare; belirsizlik geniştir. |
| PhenoBench | Crop sıraları ve bol crop training verisi crop'u kolaylaştırıyor. | Weed'ler az ve apparent-size küçük; asıl hata küçük weed recall. |
| ACRE | Robot, ışık ve ürün/domain çeşitliliği ayrımı zorlaştırıyor. | Bean/maize ve farklı sessionlar arasında morphology kayması. |
| WE3DS | Birçok ürün/tarih ve crop–weed benzerliği; weed footprint'leri küçük. | Site/date çeşitliliği ve semantik birleşmeler connected-component proxy'yi de zorlar. |
| WeedsGalore | Yalnız 104 training kare ve multispektral-kamera dağılımı; crop görünümü az öğrenildi. | Weed IoU crop IoU'dan iyi olabilir; bu hedef mahsulü korumaya yetmez. |
| WeedMap UAV | 10 m UAV GSD/apparent-size ve sensör/viewpoint domain shift'i. | RGB model, kaynağın multispektral bilgisini kullanmıyor. |
| RiceSEG | Weed/duckweed azlığı ve su/evre/organ çeşitliliği; weed sınıfı zor. | Uzman crop'u iyi ayırsa da weed IoU ve güvenli-action kalibrasyonu zayıf. |
| Early rice | Farklı dataset, kamera yüksekliği ve fide/su domain'i. | Rice specialist bu kaynağı eğitimde görmedi. |

## Küçük weed darboğazı ve çözünürlük

Kullanıcı gözlemi metrikle test edilir: `<14 px` component payı ve bu bindeki hit recall ayrı raporlanır. En önemli teknik sebep küçük bitkinin model input'unda az piksele/patch'e düşmesidir; yalnız sınıf sayısı değildir. Mevcut evaluator görüntüyü tek 512'ye küçültmez: native resolution kullanır ve 4 MP üzerini 1024 px, 128 px overlap tile'larla işler. Dolayısıyla SAHI-benzeri tiling zaten aktiftir.

Yazılımsal 2× interpolasyon yeni optik detay üretmez; patch ölçeğini değiştirerek yardımcı olabilir ve ayrı A/B ile ölçülmelidir. İlk optik tasarım hedefi minimum weed çapını sensörde en az 28 px (tercihen 56 px) yapmak; doğru fokus ve düşük motion blur sağlamaktır. Bu 2/4-patch başlangıç heuristiği saha A/B'siyle dondurulmalıdır.

- `GSD <= minimum weed diameter (mm) / desired pixels`.
- Nadir kamera yaklaşımı: `GSD ≈ sensor_width_mm × height_mm / (focal_length_mm × image_width_px)`.
- Motion blur: `blur_px ≈ ground_speed_mm_s × exposure_s / GSD_mm_px` (titreşim eklenir).
- Öncelik: sabit yükseklik + kısa poz/global shutter veya strobe + focus lock + kontrollü diffuse ışık; sonra sensör/focal/height çözünürlüğü.

### Early-rice software inference-scale A/B

Bu deney aynı 224 kare, aynı specialist ve aynı native evaluation grid'ini kullanır. 1,5×/2,0× bilinear interpolation optik bilgi eklemez; yalnız model patch ölçeğini değiştirir.

| Scale | mIoU | Weed IoU | <14px semantic hit | Safe hit | Crop point hit | Perception ms/image |
|---|---:|---:|---:|---:|---:|---:|
| 1.0× native | 0.515 | 0.131 | %19.6 | %0.3 | %14.8 | 24.6 |
| 1.5× interp. | 0.553 | 0.186 | %26.4 | %0.5 | %22.5 | 59.3 |
| 2.0× interp. | 0.574 | 0.227 | %29.4 | %0.6 | %30.5 | 144.8 |

Karar: software upscale kabul edilmedi. 2,0× `<14 px` semantic hit'i `%19.6` → `%29.4`, weed IoU'yu `%13.1` → `%22.7` artırdı; fakat crop-point hit `%14.8` → `%30.5` ve perception süresi `24.6` → `144.8 ms` oldu. 1,5× de crop-point hit'i `%22.5` seviyesine çıkardı. Bu tek-dataset development A/B'si ölçek darboğazını doğrular, ancak safety/latency guard'larını geçmez. Öncelik optik GSD/fokus/exposure ve eş-hesap multi-scale training'dir.

## Provisional proje gate'leri (aktüatör seçilince dondurulacak)

| Faz | Safety | Etkinlik | Not |
|---|---|---|---|
| Offline aday | action-level crop hit <=%0,5; 10px footprint sensitivity raporlu | spot: safe component hit >=%90 ve point precision >=%95 | Evrensel standart değil, proje başlangıç gate'i |
| Kontrollü saksı/şerit | gerçek deposition/crop injury; fail-safe stop | effective treatment >=%90 | Rüzgâr, hız ve gecikme dahil |
| Tarla pilotu | crop injury üst güven sınırı ürün eşiği altında | residual weed / kill rate ve throughput | agronomist + yasal kimyasal protokol |
| Mekanik/lazer | tool/beam crop collision üst sınırı | p95 mm error aktüatör toleransından küçük; successful kill/removal | Piksel proxy ile geçilemez |

Bu gate'ler literatür rakamlarını kopyalayan evrensel eşikler değildir. Örneğin bir field smart-sprayer çalışması %90,6 effective spray; ayrı bir kontrollü micro-jet çalışma kendi düzeneğinde weed'lerin %98'inin doğru püskürtüldüğünü raporlamıştır. Bir intra-row positioning çalışması da kendi düzeneğinde >%95 tanıma ve ±15 mm hata göstermiştir. Bunlar doğrudan bizim kabul eşiğimiz değildir; aktüatör footprint'i, ürün hassasiyeti ve ekonomik missed-weed/crop-injury maliyetiyle gate yeniden dondurulmalıdır.

## Öncelikli deney planı

1. Kamera rig'i üzerinde checkerboard/intrinsics + çalışma düzleminde homography/GSD; nozzle/tool/beam footprint ve perception-to-actuation latency ölç.
2. 3–4 temsilî saha, farklı saat/nem/toprak ve küçük weed strata içeren untouched field test topla; minimum weed fiziksel çapını kaydet.
3. Spot spray MVP için weed üstü action-point ve crop-footprint metriklerini gerçek deposition kâğıdı/fluorescent dye ile doğrula.
4. Tamamlandı: native 1.0× ile 1.5×/2.0× inference-scale A/B safety/latency guard'ını geçmedi; software upscale'ı bırak.
5. Small-object oversampling + daha büyük train crop/multi-scale training deneyi; aynı hesap ve seed guard'larıyla compare et.
6. Mekanik/lazer seçilirse 500–1000 plant için root/crown veya meristem keypoint + visibility/occlusion etiketi topla; mm P50/P95 ve kill/removal outcome'u primary yap.
7. Safety threshold'u testte değil, aktüatör ve hedef ürüne ayrılmış calibration split'inde seç; untouched test'i bir kez aç.

## Sentetik ve unseen değerlendirme

Dryland V3 ve paddy R5 sentetik aşamaları gerçek-domain model gate'ini geçti. Soy, motion ve field-robustness asset'leri görsel/asset kalite gate'lerini geçse de ortak robust modelde domain regresyonu yarattı; bu nedenle global modele eklenmedi. Bu doğru fail-closed davranıştır: daha fazla kaliteli sentetik otomatik olarak daha iyi model değildir.

V11 asset/seed ayrık sentetik test 16 kareden oluşur; 14 karede GT weed vardır. Pixel-level visual-audit aggregate: macro crop IoU `%41.8`, weed bulunan karelerde macro weed IoU `%56.1`, micro safe-weed recall `%33.3`, micro safe precision `%96.7` ve crop-spray pixel risk `%0.0`. Bunlar sentetik-domain performansıdır; gerçek saha kanıtı değildir.

Gerçek unlabeled online videolar (FarmBot soy, Naïo Oz, BoniRob) ve sentetik V11 val/test görselleri mevcut görsel pakete eklendi. Etiket olmayan videolara accuracy yazılmaz. Labeled development/transfer kanıtı SugarBeets robot, WeedMap UAV, Sorghum test, RiceSEG training-held-out calibration ve early-rice setlerinden gelir; bunların tamamı untouched final deployment testi değildir.

## RiceSEG split erratum

Önceki specialist `country-transfer` galerisi bağımsız performans kanıtı değildir. Alternatif country manifestindeki 1.254/1.254 RGB ve mask yolu specialist training coverage manifestinde bulunur; yalnız dataset/sample prefix'i farklıdır. Yeni ana RiceSEG sonucu `riceseg_v1.csv / external_calibration` kullanır: 604 kare, Guangdong + Tokyo, training image overlap 0/604. Bu training-held-out panel geçmiş specialist seçiminde kullanıldığı için development/calibration kanıtıdır, untouched final test değildir. Eski galeri train-seen diagnostic olarak yeniden sınıflandırılmalıdır.

## Sınırlamalar

- Semantic connected component true instance değildir: temas eden bitkiler birleşir, ayrık yapraklar bölünebilir.
- Canopy centroid root/crown/meristem değildir.
- px radius gerçek nozzle/tool/beam footprint'i değildir; GSD ve lens distortion gerekir.
- Offline mask metriği actuation latency, wind, deposition, terrain ve kill outcome'u içermez.
- Seen-validation field independence her kaynakta aynı güçte değildir; ROSE/WE3DS coğrafi sınırları raporlanmıştır.
- Current safety policy yüksek threshold nedeniyle etkisiz no-spray'e kayabilir; düşük crop risk tek başına başarı değildir.
- Dataset nedenleri scale/metadata/görsel hata ile desteklenen öncelikli hipotezlerdir; tek-faktörlü nedensel A/B olmayan yerde kesin neden diye sunulmaz.

## Kaynaklar

- Zhang et al., apical meristem localization for laser weeding: https://doi.org/10.3390/agronomy14092121
- Li et al., crop positioning for intra-row mechanical weeding (>95%, ±15 mm in that setup): https://doi.org/10.3965/j.ijabe.20150806.1932
- Sa et al., WeedMap and GSD/downsampling/tiled inference: https://arxiv.org/abs/1808.00100
- Real-time high-resolution micro-jet sprayer (98% weeds sprayed in its setup): https://www.sciencedirect.com/science/article/pii/S1537511023000375
- Field smart-sprayer evaluation (effective spray, precision, recall): https://www.sciencedirect.com/science/article/pii/S2666154324003685
- Remote sensing segmentation and sprayed-area analysis: https://arxiv.org/abs/2410.22554

## Reproducibility

All intervention JSONs use the accepted checkpoint, frozen source-selected policy, native-resolution inference and no external threshold tuning. Exact checkpoint/manifest/mask hashes are stored in each JSON under `provenance`. The evaluator protocol is `intervention_semantic_component_proxy_v1`.
