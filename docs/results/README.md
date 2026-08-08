# Segmentasyon ve bitki müdahalesi sonucu

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
