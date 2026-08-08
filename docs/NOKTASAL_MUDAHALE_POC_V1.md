# Noktasal bitki müdahalesi PoC v1

## Kısa karar

`%9,72`, gerçek bitki-müdahale recall'ı değildi. 768 uzman modelin `weed_threshold=0.99` ve uncertainty/crop guard sonrasında kalan weed **piksellerini** yakalama oranıydı. Aynı 283 gerçek SugarBeets robot karesinde semantik sonuç mIoU `0.7003`, weed-pixel P/R/F1 `0.5299/0.5456/0.5376` idi.

Gerçek sap etiketi olan WSD robot verisiyle kurulan detection+keypoint PoC'sinde mevcut en iyi 1536 fine-tune, ayrı test tarihinde 10% GT weed-box diagonal toleransında P/R/F1 `0.6335/0.7612/0.6915` verdi. TP/FP/FN `835/483/262`; `1097` geçerli weed sapı vardı. %95 F1 kapısı **geçilmedi**.

Bugün için doğru mimari: segmentasyon safety/context olarak kalır; noktasal aktüatör komutu crop/weed instance detection + weed stem/root keypoint'ten gelir. Video katmanı kalibre zemin koordinatında track, ≥3-kare onay ve fire-once mantığı kullanır. ReID ancak ölçülmüş uzun occlusion/geri dönüş sorunu varsa eklenir.

Literatür de bu işi otomatik olarak %95'e çözmüş değil: WSD çalışması kendi simüle weeding deneyinde detection kontrolü için %75,37, detection+stem regression için %80,42 weeding accuracy raporlar. Bu metrik bizim one-to-one F1'imizle aynı değildir; yalnızca hedefin zorluğunu kalibre eder.

## Sonuçlar

| Model / karar | Precision | Recall | F1 | Not |
|---|---:|---:|---:|---|
| 1024 pose + within-frame dedupe | 0.6442 | 0.6800 | 0.6616 | tarih-ayrı WSD |
| 1536 fine-tune, ham keypoint | 0.5410 | 0.6737 | 0.6001 | eşik validation'dan |
| **1536 fine-tune + dedupe** | **0.6335** | **0.7612** | **0.6915** | mevcut en iyi |
| 1536 box-center kontrol | 0.5432 | 0.6764 | 0.6025 | keypoint'in 10% toleranstaki ham farkı küçük |
| 1536 seen-date tanısı + dedupe | 0.7022 | 0.9003 | 0.7890 | final kanıt değil |

### Tolerans duyarlılığı — mevcut en iyi model

| Tolerans | P | R | F1 | TP/FP/FN |
|---|---:|---:|---:|---:|
| 5% box diagonal | 0.4439 | 0.5333 | 0.4845 | 585/733/512 |
| 10% box diagonal | 0.6335 | 0.7612 | 0.6915 | 835/483/262 |
| 20% box diagonal | 0.6995 | 0.8405 | 0.7636 | 922/396/175 |
| 5 px | 0.6055 | 0.7274 | 0.6609 | 798/520/299 |
| 10 px | 0.6935 | 0.8332 | 0.7569 | 914/404/183 |
| 20 px | 0.7102 | 0.8532 | 0.7752 | 936/382/161 |

`crop_as_weed_false_fire=0`: unmatched predicted-weed kutularından GT crop kutusuyla IoU≥0.50 eşleşen yoktu. Bu, crop canopy/yaralanma garantisi değildir. Tahmin noktalarının `0.1366` oranı bir GT crop bounding rectangle içinde kaldı; bu daha muhafazakâr bir mekânsal proxy'dir ve fiziksel temas olarak yorumlanmaz.

## Dedupe ve tracking

1536 ham keypoint FP sayısı `627` idi: `331` tekrar-aksiyon, `89` yakın kaçırma ve `207` diğer/arka plan. Validation'da seçilen within-frame dedupe, yeni threshold ile F1'i `0.6001→0.6915` yaptı.

Gerçek video kazanımı henüz sayısal olarak raporlanmıyor; WSD'de frame-level GT var ama botanik track ID ve kamera–zemin hareket kalibrasyonu yok. Uydurma bir tracking F1 vermek yerine `src/agri_seg/temporal_action.py` calibrated world-coordinate gözlemleri için testli minimum uygulamayı sağlar: nearest-world association, ≥3 gözlem, crop veto, ortalama nokta ve fire-once.

## Çözünürlük

| Model / inference | P | R | F1 |
|---|---:|---:|---:|
| 1024 model / 768 inference | 0.5700 | 0.6235 | 0.5956 |
| 1024 model / 1024 inference | 0.6442 | 0.6800 | 0.6616 |
| 1024 model / 1536 inference | 0.6133 | 0.6955 | 0.6519 |
| 1024 model / 2048 inference | 0.4499 | 0.5934 | 0.5118 |
| 1536 fine-tune / 1536 inference | 0.6335 | 0.7612 | 0.6915 |

Kör inference upscale monotonik fayda vermedi. 1536'da train+inference uyumu yaklaşık 3 F1 puanı kazandırdı; deney equal-compute değil ve aynı development test tarihi model kararında tekrar kullanıldı.

## Crop-row prior

| Mod | Safe weed-pixel recall | Crop-pixel risk |
|---|---:|---:|
| Baseline | 0.0783 | 0.0455 |
| Practical guard | 0.0660 | 0.0406 |
| Oracle guard | 0.0698 | 0.0203 |

Sıra guard risk ile birlikte recall'ı da azalttı. Sıra içi weed bulunduğu için `in-row=crop` hard kuralı kullanılmayacak. RTK/planter veya temporal row fit, skor özelliği ve soft safety prior olarak kullanılacak.

## %95 kabul kapısı

1. Hedef kamera/GSD ve fiziksel doğru-isabet toleransı mm olarak dondurulacak.
2. 3–4 yeni tarla/kamera oturumunda weed instance + stem/root point + crop instance ve video track ID etiketlenecek.
3. Farm/session ayrı untouched testte track-level precision/recall/F1 ≥0.95 aranacak; crop-as-weed ve duplicate-shot ayrı safety gate olacak.
4. Sonra aktüatör testinde gerçek deposition/removal/kill ≥0.95 ve crop injury ayrı kapı olarak ölçülecek.

Bugün: **research PoC GO; sahada ilaç/lazer ateşleme NO-GO**.

## Veri ve protokol sınırları

- WSD indirilebilir labelled arşivinde 511 eşli kare vardır; makale 1.556 etiketli kare bildirir.
- Train/validation/test tarihleri ayrıdır; fakat resolution/fine-tune kararında test yeniden görüldüğü için artık development holdout'tur.
- 10% weed-box diagonal toleransı fiziksel mm değildir; GSD, kamera–alet extrinsic ve latency yoktur.
- Ultralytics baseline AGPL-3.0 araştırma PoC kapsamındadır; ürün lisansı ayrı çözülmelidir.

## Birincil kaynaklar

- [Weed Stem Detection — laser için detection + stem regression](https://arxiv.org/abs/2502.06255)
- [RoWeeder — row prior ve intra-row weed sınırı](https://arxiv.org/abs/2410.04983)
- [ByteTrack — basit detection association](https://arxiv.org/abs/2110.06864)
- [Ultralytics pose görev dokümanı](https://docs.ultralytics.com/tasks/pose/)

## Exact artefaktlar

- 1024 action JSON: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/wsd_pose_poc_v1/yolo26s_pose_1024_seed17/action_metrics_v2_img1024/action_metrics.json`
- 1536 action JSON: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/wsd_pose_poc_v1/yolo26s_pose_1536_finetune_seed17/action_metrics_v2_img1536/action_metrics.json`
- 1536 best checkpoint SHA-256: `569b7c71995c3dc75cb2cf6a6bd81d87861cb4911965d1143d95037011116945`
- Dataset receipt: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/weed_stem_detection_v1_receipt.json`
