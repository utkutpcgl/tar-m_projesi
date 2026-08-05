# Rice paddy gerçek-veri kalite ve katkı raporu — v1

## Sonuç

`Rice Seedling and Weed` verisi, veri kalitesi açısından kabul edildi; ancak
test edilen `%2,5` ve `%5` global sampler karışımlarında mevcut robust modeli
değiştirmedi.

- 224/224 RGB–maske çifti bütünlük, ontoloji ve görsel kalite kapılarını geçti.
- Kaynak aslında 28 büyük fotoğrafın sekizer karosudur ve tek tarla/tek çekim
  günüdür. Ana-fotoğraf kimlikleri release'te korunmadığı için 224 karonun
  tamamı yalnız `train` rolündedir; hiçbir iç validation/test split'i yoktur.
- Ham `0` sınıfı ürün değildir. Hem ürün hem yabancı ot sınırlarında görülen
  unlabeled/void pikseller `255=ignore` yapıldı.
- Aday içinde ve mevcut 11.394 gerçek örneğe karşı SHA-256/dHash-256
  Hamming≤2 eşleşme sayısı sıfırdır.
- `%2,5` karışım robust minimum mIoU'yu `+0,008422` artırdı; ancak
  CropAndWeed regresyonu `-0,010125` ile önceden dondurulmuş `-0,010000`
  sınırını `0,000125` aştı.
- `%5` karışım CropAndWeed ve Sorghum'u artırdı; fakat CWFID worst-domain
  mIoU `-0,005679` gerileyerek pozitif-primary şartını kaybetti.
- Hiçbir seed-17 aday bütün screen koşullarını geçmedi; üç-seed confirmation
  açılmadı ve kabul edilmiş CropCraft-v3 global tarif korundu.

Bu karar verinin değersiz olduğu anlamına gelmez. Veri, paddy/rice adapter'ı,
ayrı hedef-domain fine-tuning'i ve yeni sentetik paddy asset gate'i için
yüksek değerli, CC-BY-4.0 bir gerçek geliştirme kaynağıdır.

## Kaynak, lisans ve bütünlük

- Resmî veri kaydı: [Figshare v5](https://doi.org/10.6084/m9.figshare.7488830.v5)
- Eşlik eden yayın: [Ma et al., PLOS ONE 2019](https://doi.org/10.1371/journal.pone.0215676)
- Lisans: CC-BY-4.0
- Arşiv boyutu: `30.093.419` byte
- Yayıncı MD5: `4460b4958eaebf6d326eb555e36ea8ab`
- Doğrulanan SHA-256:
  `dab8deb4d412cf26094279337b198cbaef4588cd4dd9f6327c67871124b47bf5`
- Çıktı: 224 RGB JPEG + 224 PNG maske, tümü `912×1024`
- Çekim: Jiangmen, Guangdong; 13 Nisan 2018; Canon IXUS 1000 HS;
  su yüzeyinden 0,8–1,2 m; transplantasyondan yaklaşık 20 gün sonra
- Yabancı ot: `Sagittaria trifolia`; hedef ürün: `Oryza sativa`

Yayın 28 adet `3648×2048` fotoğrafın 2 satır × 4 sütuna bölünerek 224 karo
elde edildiğini açıklar. Yayındaki rastgele `%80/%20` karo split'i sibling
leakage riski taşır. Bu projede tekrar edilmedi.

## Ontoloji kararı

Ham piksel sayıları:

| Ham ID | Piksel | Ortak sınıf |
|---:|---:|---|
| 0 | 13.752.258 | `255 ignore` |
| 1 | 22.507.511 | `1 target_crop` |
| 2 | 163.104.287 | `0 background` |
| 3 | 9.826.856 | `2 other_vegetation` |

Ham `0` dışarıda bırakıldığında kalan üç sınıfın oranları:

- crop: `0,115164071`
- background: `0,834554903`
- weed: `0,050281026`

Bunlar yayının bildirdiği `%11,517 / %83,455 / %5,028` oranlarıyla aynı
değerlerdir. Görsel QC'de ham `0`, hem rice hem Sagittaria yaprak sınırlarını
izler. Dolayısıyla bazı üçüncü taraf kodların yaptığı `0→crop` birleştirmesi
yanlış supervision üretir; fail-closed `ignore` kararı hem sayısal hem görsel
kanıta dayanır.

## Kalite ve sızıntı kapıları

- Manifest: 224 `train`, tek field/session group
- Eksik dosya: 0
- Geçersiz maske: 0
- Boyut uyuşmazlığı: 0
- Aday-içi exact/near duplicate: 0
- Aday–mevcut 11.394 gerçek örnek exact/near duplicate: 0
- En yakın mevcut-veri dHash mesafesi: minimum 77, medyan 94
- Birleşik training manifesti: 6.027 örnek; 4.390 train / 1.637 val
- Görsel QC:
  `data/processed/qc/rice_seedling_weed_common_labels_30_v1.jpg`

Bu denetim sequence independence kanıtı değildir. Sequence riski, bütün
Rice karolarını tek `train` group'unda tutarak fail-closed yönetildi.

## Dondurulmuş model katkı ekranı

Tüm kollar seed 17, epoch 8 ve epoch başına 3.600 örnekle çalıştı. Kabul
edilmiş CropCraft-v3 sentetik exposure'ı `%10` sabit tutuldu. Rice dozu eski
gerçek kaynak draw'larını oransal olarak değiştirdi; ek compute verilmedi.

Seçim alanları:

1. source validation
2. CWFID external calibration
3. SorghumWeed external calibration
4. CropAndWeed session-disjoint external calibration

Rice karoları, Rice-eğitimli adayların değerlendirmesinde kullanılmadı.
`real_core_final.test`, Carrot-Weed, EWIS1 ve Sorghum external test açılmadı.

| Kol | Source | CWFID | Sorghum | CropAndWeed | Robust min | Macro |
|---|---:|---:|---:|---:|---:|---:|
| kontrol | 0,801456 | 0,604039 | 0,816030 | 0,694439 | 0,604039 | 0,728991 |
| Rice %2,5 | 0,804408 | 0,612462 | 0,811348 | 0,684313 | 0,612462 | 0,728133 |
| Rice %5 | 0,797642 | 0,598360 | 0,822047 | 0,708018 | 0,598360 | 0,731517 |

Kontrole eşli deltalar:

| Kol | Source Δ | CWFID Δ | Sorghum Δ | CropAndWeed Δ | Robust Δ | Karar |
|---|---:|---:|---:|---:|---:|---|
| Rice %2,5 | +0,002952 | +0,008422 | -0,004682 | -0,010125 | +0,008422 | reject: CropAndWeed non-inferiority |
| Rice %5 | -0,003814 | -0,005679 | +0,006017 | +0,013579 | -0,005679 | reject: primary |

Screen yaklaşık 69 dakika sürdü. Kaynak full-resolution validation, 8 epoch
512-crop eğitimden daha pahalıydı; yöntem bütün kollarda aynı kaldı.

## Zero-shot domain-gap teşhisi

Rice'a hiç maruz kalmamış güncel kontrol, seçimden bağımsız tek bir zero-shot
teşhiste 224 Rice karosunda ölçüldü:

- mean IoU: `0,311910`
- background IoU: `0,868117`
- crop IoU: `0,038403`
- weed IoU: `0,029208`

Bu sonuç global modelin paddy su/yansıma + erken rice/Sagittaria koşulunda
gerçek bir coverage açığı olduğunu gösterir. Aynı karolar Rice-eğitimli
adaylarda ölçülmediği için train leakage ile kazanım iddiası yapılmadı.

## Karar ve sonraki sentetik hedef

Global seçili tarif değişmedi:

```text
simab_real_sorghum_cropcraft_robust10_e8_v3
seed 43 / epoch 8
SHA-256 2fed7e2b4a3e42b183ffa3911d2014ed60e8088efc5532b7a79753d7356b3771
```

Bir sonraki sentetik asset deneyi genel “daha güzel bitki” üretmek yerine şu
kanıtlanmış açığı hedeflemelidir:

- sığ paddy suyu, çamur ve yansıma/shadow materyalleri,
- erken dönem `Oryza sativa` dar-yaprak/tiller morfolojisi,
- `Sagittaria` benzeri geniş-yaprak/aquatic weed morfolojisi,
- 0,8–1,2 m top-down kamera geometrisi,
- gerçek Rice development + mevcut source/CWFID/Sorghum/CropAndWeed
  non-inferiority gate'i.

## Kanonik makbuzlar

- Dönüşüm: `data/processed/manifests/rice_seedling_weed_conversion.json`
- Manifest: `data/processed/manifests/rice_seedling_weed.csv`
- All-role duplicate audit:
  `data/processed/audits/rice_seedling_weed_all_roles_duplicates_v1.json`
- Benchmark:
  `data/runs/real_data_rice_seedling_weed_screen_v1/benchmark_results.json`
- Dondurulmuş screen seçimi:
  `data/runs/real_data_rice_seedling_weed_screen_selection_v2.json`
- Zero-shot teşhis:
  `data/runs/realab_rice_control_e8_v1/seed_17/development/rice_seedling_weed_zero_shot_v1.json`
- Nihai veri/model kararı:
  `data/runs/real_data_rice_seedling_weed_final_selection_v1.json`
