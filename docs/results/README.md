# Segmentasyon ve bitki müdahalesi sonucu

## Güncel kontrollü spot-spray PoC — 2026-08-12

- [Buradan başlayın — 6 sayfalık sade PDF](kontrollu_spot_spray_poc_v1/BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Okunabilir detaylı PDF](kontrollu_spot_spray_poc_v1/DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Aranabilir rapor, exact JSON ve self-sufficient görseller](kontrollu_spot_spray_poc_v1/README.md)
- [Fiyat/performans odaklı ürün görüntüleme kararı](../SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md)
- [Exact kamera/lens/ışık/hız/BOM baseline'ı](../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md)
- [Fiziksel A–F rig kabul runbook'u](../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md)
- [Capture/annotation/split sözleşmesi](../SPOT_SPRAY_DATA_CAPTURE_AND_ANNOTATION_V1.md)
- [Fail-closed target-rig fine-tune ve track-action hattı](../SPOT_SPRAY_TARGET_RIG_MODEL_PIPELINE_V1.md)

Henüz gerçek target-rig performansı ölçülmedi. Eşit bütçeli pre-real
karşılaştırmada V12 sentetik ek maruziyeti yerine ROSE native-detail robot
görünümü kullanan aday seçildi. Tüketilmiş PhenoBench UAV geliştirme
panelindeki `≥82 px` frame-action F1 `%72,6→%75,4`, aynı kilitli Pheno
eşiğiyle tüketilmiş tek-session BoniRob dış robot-view panelindeki F1
`%5,4→%9,0` oldu. Pheno %95 fark aralığı sıfırı kesiyor ve yeni aday V12
sentetik holdout'ta sabit eşikte `%0,0` F1 veriyor; dolayısıyla bu yalnız
yönsel pre-real model seçimi, sentetik karar ağırlığı yine `0`. Seçilen
ROSE-native foundation SHA-256
`3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`;
target-rig fine-tune/deployment checkpoint'i değildir.

Karar: instance segmentation devam, mevcut modelle saha ateşlemesi NO-GO.
Pipeline `PRE_REAL_NOT_READY`: physical A–E receipt, gerçek capture READY,
fine-tune sonucu ve frozen evaluated checkpoint yoktur. A–E yalnız kontrollü
RGB collection; A–F yalnız nonchemical dry-marker açabilir. Chemical fire,
nicel deposition/crop-injury eşiği olmadığı için kapalıdır. İlk unblock
physical A–E PASS; ardından aynı rig'den en az 3 tarla / 4 field-session,
image SHA + exact metadata, deterministic field `60/20/20` split ve ayrı
track-action testidir. Dondurulan başlangıç tek Basler PRO kamera, native
2048² ROI, 474–484 mm FOV, 170 µs ve 15 Hz'dir; 20 Hz/ikinci kamera ayrı E2E
benchmark geçmeden açılmaz.

## Adil target-trained detection vs segmentation A/B — 2026-08-10

- [Yeni — `%95` kapasite/genelleme, kamera kontratı ve rakip ceiling raporu](SEGMENTASYON_95_VE_RAKIP_CEILING_RAPORU_V1.pdf)
- [Önce bunu açın — 11 sayfalık sade ve görselli PDF](FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf)
- [Aranabilir exact metrikler ve deney sözleşmesi](../FAIR_DETECTION_SEGMENTATION_KARARI_V1.md)
- [Altı açıklamalı untouched-test örneği](fair_detection_segmentation_gallery_v1/README.md)
- [%95+ saha kanıtı ve rakip sistem planı](../SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md)

İki model de aynı `1.407` gerçek PhenoBench train görüntüsünü ve aynı bitki
instance'larını gördü; ikisi de YOLO26s ailesinde `1024 px`, `50 epoch`,
`seed 17` ile eğitildi. Validation'da kilitlenen eşiklerle untouched testte
detection kutu-merkezi precision/recall/F1 `%69,0/%60,9/%64,7`, segmentasyon
güvenli-iç-noktası `%86,0/%64,9/%74,0` verdi. Paired bootstrap F1 avantajı
`+9,3` puan, `%95 GA [+7,02, +11,56]` oldu.

Sonuç: gelecekte footprint, crop no-go maskesi ve lazer/keypoint koluna daha
rahat genişlemek için instance segmentation temeli tercih edilir. Bu bir saha
GO kararı değildir: PhenoBench UAV domainidir, tek seed kullanılmıştır ve
balanced test recall yalnız `%64,9`dur. Önceki target-trained detector vs
zero-shot segmenter WSD sonucu mimari gate olarak geçersizdir; yalnız gerçek
hedef-domain veri görmenin etkisini gösterir.

Actionable-size post-hoc tanısı, predicted-mask size gate ile en iyi sonucu
`≥42 px` grubunda verdi: precision/recall/F1 `%88,5/%80,2/%84,1`. Özet JSON
[buradadır](phenobench_actionable_size_summary_v1.json). Test daha önce
açıldığı için bu yalnız teşhistir; saha gate'i değildir.

Kapasite/genelleme ayrımı da tamamlandı. Aynı hedef-benzeri 126 karede
crop-safe aksiyon F1 `%99,68` ile `%98` kasıtlı-overfit kapısını geçti; ortak
farklı-parsel testinde en iyi base F1 `%84,10` kaldı. Hedef+kaynak replay
recall'ı `%77,44→%85,44` yükseltti fakat precision'ı
`%92,02→%81,40`, crop hit'i `%2,85→%5,64` bozduğu için reddedildi.
[Exact yeni kanıt özeti](phenobench_95_evidence_summary_v1.json) ve
[okunabilir `%95`/rakip planı](../SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md)
birlikte okunmalıdır. PDF/hash makbuzu
[buradadır](segmentation_95_market_report_receipt_v1.json).

## Detection-only spot-spray A/B — 2026-08-10

- [Önce bunu açın — 10 sayfalık basit PDF](DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf)
- [Aranabilir exact sonuçlar ve kamera hesabı](../DETECTION_SPOT_SPRAY_BENCHMARK_V1.md)

Detection-only kutu merkezi, eşit 1024 WSD A/B'sinde iyimser spot-spray
precision/recall/F1 `0,7496/0,7822/0,7655`; sıkı stem F1 `0,6604` verdi.
Pose keypoint'in karşılıkları F1 `0,7493/0,6591` oldu. Sonuç: ilk kimyasal
spray PoC'sinde detection-only yeterli ve daha basit baseline; lazer/mekanik
için keypoint gerekir. `%95` saha kapısı geçilmedi.

`28–56 px` weed recall'ı `%88,3`, `<14 px` recall'ı `%53,8` oldu. 1024
girişte test weed'lerinin yalnız `%14,8`i 28 px üstündedir. Kör 1536 resize
F1'ı düşürdü; gerçek sensör detayı/FOV ve o çözünürlükte eğitim gereklidir.

## Noktasal müdahale PoC'si — 2026-08-08

- [Önce bunu açın — 14 sayfalık tek ve açıklamalı PDF](BASLA_BURADAN_NOKTASAL_MUDAHALE_POC.pdf)
- [Aranabilir exact metrikler](../NOKTASAL_MUDAHALE_POC_V1.md)

`%9,72` bitki-müdahale recall'ı değil, aşırı temkinli semantik
policy'nin weed-pixel recall'ıydı. Gerçek sap/keypoint etiketi olan ayrı
robot verisindeki mevcut en iyi tek-kare+düzeltme sonucu precision `%63,4`,
recall `%76,1`, F1 `%69,2` oldu. `%95` kapısı geçilmedi. PDF; iki büyük
gerçek saha örneği, tolerans tablosu, resolution A/B, row-prior sonucu ve
tracking kararını bir fikir/sayfa düzeninde gösterir.

## Kamera/domain/küçük-ot kararı — 2026-08-06

- [Önce bunu açın — 10 sayfalık kısa karar](BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf)
- [23 sayfalık açıklamalı detaylı rapor](KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf)
- [Aranabilir exact sonuçlar](../KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md)

Kısa sonuç: global generalist 512 kontrol olarak kaldı. Canvas768 iki seedde
hedef-SugarBeets specialist kapısını geçti (ortalama `+0,13010` mIoU), fakat
CWFID ortalama `-0,04424` geriledi; bu nedenle yalnız doğrulanmış hedef robot
kamera profilinde route edilir. Gerçek holdout'ta kör 1,5×/2× inference
upscale reddedildi. 10 hedef-benzer gerçek karelik domain adaptation iki seed
ortalamasında Sorghum'u `+0,17966` yükseltti. Crop-row bilgisi ana model değil,
ölçülü risk–recall safety veto'sudur.

Tam yerel kanıt paketi:
`/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_domain_report_v1/`.

Yeni, removal-yöntemi odaklı raporlar:

- [Kısa karar PDF'i](BASLA_BURADAN_MUDAHALE_RAPORU.pdf)
- [Anlaşılır, örnekli ayrıntılı PDF — önerilen](DETAYLI_BITKI_MUDAHALE_RAPORU.pdf)
- [Aranabilir teknik metin eki](../INTERVENTION_EVALUATION_V1.md)

Detaylı PDF `48` sayfadır. Ana bölümde bir sayfa bir fikir taşır; görsel
sayfalarda tek saha örneği ve iki büyük karşılaştırma paneli bulunur. Yoğun
exact tablolar yalnız teknik ektedir. V11 sentetik asset/seed-ayrık holdout'un
güçlü ve zor örnekleri ile 16-kare toplu sonucu da ayrı sayfalarda gösterilir.

Önceki, yalnız segmentasyon-görseli odaklı rapor:

- [BASLA_BURADAN_SEGMENTASYON_SONUCLARI.pdf](BASLA_BURADAN_SEGMENTASYON_SONUCLARI.pdf)

Yeni rapor mIoU'nun yanında spot spray action-point/footprint, semantic
component hit/coverage ve mekanik/lazer için center proxy metriklerini
gösterir. Connected component true plant instance, canopy center ise
root/crown/meristem değildir; bu sınırlar PDF'de açıkça işaretlidir.
RiceSEG'in 604-kare paneli eğitime girmemiştir, ancak geçmiş specialist
seçiminde kullanıldığı için final test değil development/calibration kanıtıdır.

Tam yerel paket (iki PDF + Markdown + ham metrik/A-B + dokuz tekil görsel kanıt):
`data/processed/audits/crop_intervention_report_v1/`.

Kabul edilen modeller:

| Rol | Deney / seed | SHA-256 |
|---|---|---|
| Global model | `simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8`, seed 43 | `b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f` |
| Pirinç uzmanı | `realab_riceseg_add025_compute3780_r5_e8_v2`, seed 29 | `ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7` |

Model ağırlıklarının her biri yaklaşık 143 MB olduğu için normal GitHub
dosya sınırını aşar ve bu depoya eklenmemiştir. Ham datasetler, manifest
çıktıları, run klasörleri ve ayrıntılı görsel galeriler de yerel veri diskinde
tutulur. Repo; kaynak kodu, configleri, testleri, metodoloji dokümanlarını,
kısa karar PDF'ini ve anlaşılır detaylı PDF'i içerir.
