# Unseen ve dağılım-dışı görsel segmentasyon galerisi V1

> **Erratum — 5 Ağustos 2026:** RiceSEG `country-transfer` manifesti,
> coverage split'inin alternatifiymiş; ikisi birlikte bağımsız roller gibi
> kullanılamaz. Kabul edilmiş rice specialist'in training manifestiyle
> country panelinin RGB/mask path kesişimi `1.254/1.254`'tür. Dolayısıyla
> specialist country galerisi model-unseen/held-out performans kanıtı değil,
> **train-seen diagnostic** olarak okunmalıdır. Global fallback gerçek
> RiceSEG ile eğitilmediğinden onun aynı karelerdeki görseli yine transfer
> tanısıdır. Yeni specialist ana sonucu, training path kesişimi `0/604`
> olan `riceseg_v1.csv / external_calibration` (Guangdong + Tokyo) panelinden
> gelir. Bu 604 kare specialist eğitimine girmedi, ancak önceki doz/seed
> seçiminde development metriği olarak kullanıldı; dolayısıyla
> **training-held-out calibration**, untouched final test değildir. Makbuz:
> `data/processed/audits/intervention_metrics_v1/riceseg_split_path_overlap_audit.json`.

Bu çalışma üç farklı “unseen” düzeyini birbirine karıştırmadan raporlar:

1. **Tam model-unseen, etiketsiz gerçek:** FarmBot Soy, Naïo Oz online video
   ve daha önce hazırlanmış BoniRob 11:36 sekansı. Bunlar yalnız görsel hata
   keşfidir; mIoU yoktur ve seçim ağırlığı `0,0`'dır.
2. **Eğitim-unseen, etiketli fakat development'ta tüketilmiş gerçek:**
   SugarBeets2016 10:37 holdout ve WeedMap UAV. RiceSEG country-transfer bu
   kategoriye yalnız global fallback için girer; rice specialist için yukarıdaki
   erratum geçerlidir. Ground-truth/prediction galerileri değerlendirilebilir
   fakat artık final test veya deployment kanıtı değildir.
3. **Asset/seed-ayrık sentetik stres:** V11-R2Q val/test. Gerçek seçim skoruna
   katılmaz; yalnız sentetik kapsam ve hata modu gösterir.

Bu ayrım, geniş validation ihtiyacını karşılarken etiketsiz ya da sentetik
görüntülerden sahte accuracy üretmemek içindir.

## Yeni bağımsız gerçek kaynak: FarmBot Soy

[Mendeley FarmBot Soybean and Weed 2026](https://data.mendeley.com/datasets/78ms3sw487/1)
release'i CC-BY-4.0 altında indirildi. Dış ZIP'in içindeki gerçek ZIP de
safe-path, symlink, duplicate-member, suffix, kapasite ve tam CRC kapılarından
geçirildi. Yayıncıya ait 2.400 macOS metadata/resource-fork girdisi yalnız
deklaratif pattern'lerle karantinaya alındı. 1.300 görüntünün tamamı decode
edildi.

Makale 4K acquisition belirtse de dağıtılan 659 etiketsiz kaynak fotoğraf
`1600x1200`, 641 Roboflow türevi `640x640`'tır. Yalnız 659 kaynak fotoğraf
seçime uygundur; çözünürlük farkı audit ve erratum'da açıkça kaydedildi.

- Gün 1–20'nin her birinden iki kare: 40 görüntü.
- Kabul edilmiş checkpoint'in 4.266 benzersiz train görüntüsüne karşı exact
  eşleşme yoktur.
- Seçilen karelerin train'e minimum dHash-64 Hamming mesafesi `12`'dir;
  gate `>=3` idi.
- Görsel incelemede çatlak/topaklı toprak, sap artığı, sert/difüz gölge,
  büyüme evresi ve yabancı ot yoğunluğu çeşitliliği kabul edildi.
- Tek kontrollü saha, çoğunlukla kuru toprak ve dense mask eksikliği temel
  sınırlamalardır.

Kaynak temas sayfaları:

- `data/processed/audits/farmbot_soy_unseen_v4/gallery_selection_v1/source_contact_sheet_corrected_01.jpg`
- `data/processed/audits/farmbot_soy_unseen_v4/gallery_selection_v1/source_contact_sheet_corrected_02.jpg`

İlk hash-kilitli temas sayfalarındaki “4K source” başlığı yalnız görsel etiket
hatasıydı; seçim ve dosyalar değiştirilmeden
`contact_sheet_resolution_erratum.json` ile düzeltildi.

Kanonik seçim makbuzu:
`data/processed/audits/farmbot_soy_unseen_v4/gallery_selection_v1/selection_receipt.json`.

## Online robot videosu: Naïo Oz

[Naïo Technologies Oz videosu](https://www.youtube.com/watch?v=9LdXvkvcSxM)
1080p olarak yalnız yerel analiz için alındı. Metadata yeniden kullanım
lisansı belirtmediği için kaynak ve türetilmiş galeri yeniden dağıtıma
kapalıdır. FarmDroid adayı çoğunlukla dış makine/bare-soil sinematografisi ve
çok az görünür bitki içerdiği için model çalıştırılmadan reddedildi.

Naïo videosunda modelden bağımsız timeline incelemesiyle seçilen 12 kareden
iki zamansal tekrar yine model çıktısı görülmeden çıkarıldı. Son 10 kare:

- 1920x1080 ve tümü decode edilebilir;
- 4.266 train görüntüsüne minimum dHash mesafesi `8`;
- kendi içinde minimum dHash mesafesi `9`;
- greenhouse, açık tarla, robot altı/tool occlusion ve farklı bitki ölçekleri
  içerir.

Video birden fazla ürün türünü karıştırdığı ve kare-bazlı ürün kimliği
vermediği için crop-vs-weed yorumu yasaktır. `target_crop_id=unknown` ile
yalnız **vegetation union vs background** görselleştirilir. Subtitles,
pillar-box ve robot/tool occlusion bu galeriyi temiz near-nadir benchmark
değil, kasıtlı OOD failure probe yapar.

Kaynak temas sayfası:
`data/processed/audits/online_unseen_naio_oz_v1/selection_v2/source_contact_sheet.jpg`.

## Önceden tamamlanmış BoniRob unseen sekansı

Sugar Beets 2016 11:36 BoniRob JAI-RGB sekansında 31 gerçek robot karesi daha
önce kabul edilmiş seed-43 modelle çalıştırılmıştı. Görsel çıktı gerçekte
mevcuttur; önceki teslimatta yeterince görünür sunulmamıştı:

- temas sayfası:
  `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/accepted_model_contact_sheet.jpg`
- semantic overlay video:
  `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/accepted_model_semantic_overlay_1fps.mp4`
- makbuz:
  `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/unseen_sequence_evaluation.json`

Geniş yaprak sınırları kuvvetliyken ince/çimsi bitkilerde crop-other ve
unknown karışması görülür. Etiket yoktur; mIoU raporlanmaz.

## Üretilen segmentasyon çıktıları

Kabul edilmiş global fallback seed-43 checkpoint'iyle kanonik galeri
tamamlandı. Otomatik index kapıları 3/3 etiketsiz gerçek kaynak ve 5/5
etiketli/sentetik panel için geçti:

`data/processed/audits/unseen_visual_gallery_v1/gallery_index.json`

Renkler üç-sınıflı panellerde crop=yeşil, other vegetation=kırmızı ve
unknown=mor; Naïo'da crop kimliği bilinmediği için tüm semantic vegetation
yeşildir. Etiketli panellerde her tile sırası RGB, ground truth, semantic
prediction ve frozen safety policy'dir.

| Panel | Rol | Değerlendirilen/gösterilen | Temas sayfaları |
|---|---|---:|---|
| FarmBot Soy | tam model-unseen, etiketsiz gerçek | 40/40 | `farmbot_soy_accepted_seed43/prediction_contact_sheet_01..04.jpg` |
| Naïo Oz | online video, etiketsiz OOD | 10/10 | `naio_oz_accepted_seed43/prediction_contact_sheet_01.jpg` |
| BoniRob 11:36 | tam model-unseen, etiketsiz robot sekansı | 31/31 | tarihsel `accepted_model_contact_sheet.jpg` + overlay video |
| SugarBeets 10:37 | session-ayrık etiketli development | 283/20 best-worst | `sugarbeets2016_holdout/{best,worst}_contact_sheet.jpg` |
| RiceSEG country transfer | ülke-ayrık etiketli development | 1.254/20 best-worst | `riceseg_country_transfer/{best,worst}_contact_sheet.jpg` |
| WeedMap UAV | ölçek kayması development | 95/20 best-worst | `weedmap_uav/{best,worst}_contact_sheet.jpg` |
| V11-R2Q val | asset/seed-ayrık sentetik | 16/16 | `synthetic_v11_val/{best,worst}_contact_sheet.jpg` |
| V11-R2Q test | asset/seed-ayrık sentetik | 16/16 | `synthetic_v11_test/{best,worst}_contact_sheet.jpg` |

Yolların tabanı:
`data/processed/audits/unseen_visual_gallery_v1/`.

## Görsel bulgular

- **FarmBot:** Gün 1-10'da çatlak/topaklı toprak, residue ve sert gölgede
  apparent soy sınırları güçlüdür. Gün 11-20'de birden çok gerçek soy yaprağı
  other vegetation'a kayar; en yüksek other oranı `0,380020`'dir. Ortalama
  confidence yine `0,976410` olduğundan salt confidence OOD alarmı değildir.
  Frozen policy birçok kararsız alanı unknown yapar; mean/max safe-weed alanı
  yalnız `0,000103/0,000555` olduğu için crop-korumacı fakat eylemsizdir.
- **Naïo:** Büyük greenhouse/açık-tarla canopy'si ve çoğu çıplak toprak iyi
  ayrılır. Yeşil robot gövdesi/tool yüzeyleri bitki sanılır; ince onion-benzeri
  sıralar ve ağır occlusion kısmen kaçar. Bu video için crop-vs-weed yorumu
  yapılmaz.
- **SugarBeets:** Geniş yapraklı crop geometrisi çoğunlukla iyi, ince çimsi
  weed ve saplarda miss/confusion belirgindir. Worst karelerde crop-hit ve çok
  düşük safe-weed recall vardır.
- **WeedMap:** Row-scale vegetation izlenir ve ignore/black sınırları korunur;
  küçük UAV ölçekli weed'ler sıkça kaybolur veya birleşir.
- **Sentetik V11:** Asset/light ayrımında birçok sınır korunur, ancak küçük
  bitkiler, aşırı pozlama ve ince geometri zayıftır. Görüntülerin sentetikliği
  belirgindir ve gerçek-saha claim'i üretmez.

## Rice route için gerekli karşılaştırma

RiceSEG galerisi global fallback'in dağılım dışı hatasını göstermek için
korundu: özellikle wet/dense rice karelerinde gerçek crop blade'leri kırmızı
other vegetation olur ve safety panelinde crop-hit görülür. Mevcut kabul
edilmiş araştırma sistemi kesin `crop_id=12 / Oryza sativa` metadata'sında
global fallback'i kullanmaz; seed-29 specialist'e route eder.

Bu nedenle aynı 1.254 kare ayrıca kabul edilmiş specialist ile işlendi:

- `riceseg_country_transfer_specialist_seed29/best_contact_sheet.jpg`
- `riceseg_country_transfer_specialist_seed29/worst_contact_sheet.jpg`
- checkpoint SHA-256:
  `ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7`

Specialist global modeldeki crop-as-other hatasını büyük ölçüde kaldırır ve
rice'ı korur; fakat worst karelerde aşırı crop-biased olup weed'i kaçırır.
Bu yüzden semantic specialist kabulü spray-ready sonucu değildir ve otomatik
görsel routing yapılmaz.

Tüm sayfaların insan inceleme kaydı ve açık hata listesi:
`data/processed/audits/unseen_visual_gallery_v1/manual_prediction_review.json`.

## Yorumlama sınırları

- Etiketsiz gerçek galerilerde alan oranı/confidence yalnız trace'tir,
  accuracy değildir.
- Etiketli development galerileri model hatasını görünür kılar; tekrar model
  seçimi ya da final test değildir.
- Sentetik val/test yeni bir gerçek-saha claim'i üretmez.
- Semantic başarı, no-spray/püskürtme güvenliğini tek başına kanıtlamaz.
