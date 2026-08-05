# CropCraft özel asset kalite ve gerçek-domain A/B raporu

## 1. Karar

Özel erken-dönem sorgum asset paketi, önceden dondurulan eşit-bütçeli
asset-quality gate'ini **geçti**. Stock CropCraft `%10` koluna karşı epoch 8,
`3.600` örnek/epoch ve seed `17/29/43` sabit tutuldu. Üç gerçek geliştirme
alanının seed başına minimumu olan robust mIoU, üç seed'in üçünde de yükseldi:

| Seed | Stock robust mIoU | Özel asset robust mIoU | Fark |
|---:|---:|---:|---:|
| 17 | 0,568428 | 0,590082 | +0,021653 |
| 29 | 0,515735 | 0,535603 | +0,019868 |
| 43 | 0,540738 | 0,560132 | +0,019394 |
| **Ortalama** | **0,541634** | **0,561939** | **+0,020305** |

Donmuş dört kabul kontrolünün tamamı geçti: pozitif paired ortalama, en az
2/3 seed galibiyeti (gerçekte 3/3), kaynak validation regresyonu en fazla
`0,01` ve Sorghum validation regresyonu en fazla `0,01`.

Resmi seçim makbuzu
`data/runs/simulation_asset_quality_selection_v2.json` dosyasındadır. Seçilen
temsilci epoch-8 checkpoint'i seed 43 `last.pt`, SHA-256 değeri
`cf053d92512630cfbd228d2a000c417e0041c929b2e49675eeec911cfb457189`'dur.

Bu karar özel asset tarifini stock asset tarifine tercih eder. Mevcut tarihsel
epoch-15 genel modeli otomatik olarak değiştirmez; bunun için eşit-bütçeli
epoch-15 confirmation gerekir. Ayrıca safety/deployment onayı değildir.

## 2. Önceki assetler ne kadar optimizeydi?

Önceki hat; pinli CropCraft commit'i, izole Blender kurulumu, deterministik
seed, scene-ayrık üretim, maske paleti doğrulaması, duplicate denetimi ve
eşit-bütçeli gerçek-veri A/B açısından güçlüydü. Darboğaz pipeline değil,
içerik kapsamıydı:

| Özellik | Stock paket | Özel paket |
|---|---:|---:|
| Crop modeli | 5 maize | 15 sorgum, 5 evre × 3 varyant |
| Crop yüz sayısı | min 106, medyan 156, max 172 | min 356, medyan 676, max 1.156 |
| Yabancı ot | 3 tip / 21 model | 4 tip / 24 model |
| Tarla artığı/debris | 7 küçük taş | 16 stick/chip/clod |
| Soil PBR ailesi | 1 | 3 |
| HDRI ailesi | 1 | 3 |
| Asset lisansı | bundled, tek tek belirtilmemiş | dosya-hash'li CC0-1.0 |

Stock crop model sayısı ve medyan geometri ayrıntısı sırasıyla `3×` ve
`4,33×` artırıldı. Statik gate'te dejenere yüz `0`, beyan edilen yükseklik
hatası `0` ve tüm dosyaların inventory hash'i doğrulandı.

## 3. Yeni asset paketi

`cropcraft_agri_early_v2_r3` paketi şunları içerir:

- 6–24 cm aralığını kapsayan, kıvrımlı/fold'lu yaprak, midrib ve gövdeli 15
  prosedürel `Sorghum bicolor` modeli;
- cotyledon, broadleaf, grass ve rosette ailelerinde altışar yabancı ot;
- düzensiz stick, chip ve clod biçimlerinde 16 arka plan artığı;
- `dry_mud_field_001`, `brown_mud`, `cracked_red_ground` 2K PBR zeminleri;
- `farm_field_puresky`, `overcast_soil_puresky`,
  `citrus_orchard_puresky` 2K HDRI'ları.

Prosedürel geometri bu çalışma tarafından CC0-1.0 olarak yayımlandı. Soil ve
HDRI girdileri [Poly Haven lisansına](https://polyhaven.com/license) göre
CC0-1.0'dır ve resmi [Poly Haven API](https://polyhaven.com/our-api) metadata'sı
üzerinden byte count/MD5 kontrolüyle indirildi. Paket 131 dosya ve
`71.906.159` byte'tır. Inventory SHA-256
`9fe47f634febb08cd9579c022fc60bfa5daf516c0ec360f569880496cd80025f`,
`PACK.json` SHA-256
`8eaf624d666ff8adce877ff11aed1ed806aa93e0018631e84876e6503704d3af`'tır.

İndirme öncesinde `369.910.575.104` byte boş alan, gerekli koruma payı olarak
`1.213.959.632` byte hesaplandı; kapasite gate'i geçti. Çıktılar root disk
yerine HDD-backed `data` köküne yazıldı.

## 4. İterasyon ve kalite kapıları

Başarısız ara sürümler kanıt olarak korundu ve eğitime alınmadı:

- İlk asset paketi erken crop modellerinde 228 yüzle `min_faces=350` statik
  gate'ini geçemedi.
- İlk smoke'ta rosette ölçeği gerçek dışı büyüktü; genişlik/yükseklik oranı
  sınırlandı.
- Sonraki smoke'ta iki satır arasına bakan kamera crop-free kare üretti; tek
  crop satırı ve stage-aware kamera yüksekliği kullanıldı.
- Weed-free smoke oranı için yalnız yoğunluk aralıkları düzeltildi.
- Dikdörtgen chip'ler düzensiz, tapered altıgen artıklara çevrildi.
- İlk 100-kare pilot 7 crop-free kare ve iki boş-mask duplicate'i, ikinci
  pilot bir crop-free kare nedeniyle reddedildi.

Kabul edilen smoke `data/synthetic/cropcraft/agri_smoke_v2_r5`, kabul edilen
pilot `data/synthetic/cropcraft/agri_early_pilot_v2_r2` altındadır. Temsili
RGB/mask çiftlerinde ölçek, hizalama, debris ve ışık manuel olarak da
incelendi; hash'li görsel inceleme makbuzu pilot klasöründedir.

## 5. Kabul edilen pilot ve manifest

| Kontrol | Sonuç |
|---|---:|
| Bağımsız scene / kare | 25 / 100 |
| Renderer-QC train/val scene | 20 / 5 |
| Crop-free kare | 0 |
| Weed-free kare | 4 (%4) |
| Ortalama crop / weed piksel oranı | 0,009395 / 0,023247 |
| Exact RGB duplicate | 0 |
| Scene'ler arası exact mask duplicate | 0 |
| Kullanılan crop / soil / HDRI varyantı | 15 / 3 / 3 |

Ortak ontoloji manifesti 80 train / 20 val ve scene ayrık olarak üretildi.
Eğitim manifestinde 100 sentetik karenin tamamı train rolüne çevrildi; bu
yalnız renderer-val sahnelerinin model selection için kullanılmaması
nedeniyle yapıldı. Model validation'ı değişmeden 1.637 gerçek karede kaldı ve
sampler exposure tam `%10` olarak sabitlendi.

Sınırlı low-order domain-gap taramasında özel pilotun parlaklık, kontrast,
saturation, green dominance, texture, crop ve weed oranı medyanlarının hiçbiri
gerçek pooled q05–q95 aralığının dışında değildi. Bu yalnız kaba uyumsuzluk
kontrolüdür; kabul kriteri gerçek-veri A/B'sidir.

## 6. Eşit-bütçeli gerçek geliştirme sonucu

| Alan, üç-seed ortalama mIoU | Stock `%10` | Özel `%10` | Özel − stock |
|---|---:|---:|---:|
| Kaynak gerçek validation | 0,803451 | 0,797521 | -0,005930 |
| CWFID `external_calibration` | 0,541634 | 0,561939 | **+0,020305** |
| Sorghum `external_calibration` | 0,823498 | 0,818323 | -0,005175 |
| Robust minimum | 0,541634 | 0,561939 | **+0,020305** |

Kazanç esas olarak en zayıf alan olan CWFID'de geldi. Özel paket CWFID crop
IoU ortalamasını `0,190929 → 0,217782`, weed IoU ortalamasını
`0,459054 → 0,492573` yükseltti. Buna karşılık kaynak ve Sorghum'da küçük bir
ortalama gerileme vardır; bu gerilemeler donmuş non-inferiority sınırının
içindedir, yok sayılmamalıdır.

Tüm koşular aynı source-tree SHA-256
`4d08a822084321404609c3c43b5d32283249be7d93c1e3358ac02b449ac2e8f5`,
aynı epoch, örnekleme bütçesi, model ve seed'lerle üretildi. Hiçbir final test
selection için okunmadı.

## 7. Sınırlar ve sonraki doğru adım

- Prosedürel morfoloji botanik scan değildir; yaprak dokusu, hastalık, rüzgâr,
  ıslak yaprak, motion blur ve ölçülmüş kamera response'u modellenmedi.
- Safety constraint bütün geliştirme alanı/seed kombinasyonlarında geçmedi.
  Seçilen checkpoint crop/weed semantik araştırma checkpoint'idir; püskürtme
  için uygun değildir.
- Sorghum `external_test` daha önce tarihsel olarak tüketildi ve bu asset
  seçiminde özellikle okunmadı. Yeni seçilen tarifin final iddiası için yeni,
  dokunulmamış ve tercihen birden çok tarlalı saha testi gerekir.
- Epoch-8 asset sonucu, tarihsel stock-asset epoch-15 modelinin doğrudan
  yerine geçmez. Bir sonraki model adımı, önceden dondurulmuş eşit-bütçeli
  özel-asset epoch-15 confirmation ve ardından yeni final settir.
- Depth, Unreal, robot fiziği ve büyük sentetik batch bu gate'e karıştırılmadı.

Bu nedenle pratik karar: özel CC0 asset tarifi **kabul**, aynı stock assetlerin
körlemesine büyütülmesi **ret**, saha/deployment iddiası ise **beklemede**.

## 8. Kanonik kanıtlar

- Gate: `configs/simulation/cropcraft_agri_asset_gate_v2.yaml`
- Asset audit: `data/processed/audits/cropcraft_asset_quality_v2.json`
- Pilot release: `data/synthetic/cropcraft/agri_early_pilot_v2_r2/release_receipt.json`
- Görsel inceleme: `data/synthetic/cropcraft/agri_early_pilot_v2_r2/visual_review_receipt.json`
- Manifest audit: `data/processed/audits/cropcraft_agri_ablation_manifest_v2.json`
- Domain-gap: `data/processed/audits/cropcraft_agri_early_pilot_domain_gap_v2.json`
- Training matrix: `configs/benchmark/simulation_asset_quality_confirm_v2.yaml`
- Fixed-epoch evaluation receipt:
  `data/runs/simab_real_sorghum_cropcraft_agri10_e8_v2/development_fixed_epoch8_evaluations.json`
- Selection receipt: `data/runs/simulation_asset_quality_selection_v2.json`
- Kod testleri: `39 passed`
