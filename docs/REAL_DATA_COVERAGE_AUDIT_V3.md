# Gerçek veri coverage ve robust katkı denetimi — v3

> **Takip notu (2026-08-03):** Bu dosyanın RiceSEG oturumu bekleyen bölümü
> tarihsel v3 durumunu anlatır. RiceSEG daha sonra tamamen indirildi, kalite
> kapısından geçti ve üç global-mixture ekranı cross-domain kapılarında
> reddedildi. Ayrı metadata-routed RiceSEG specialist daha sonra paired
> seed 17/29/43'te 3/3 robust galibiyetle kabul edildi; global fallback
> değişmedi. RiceSEG sonrası taramada BAWSeg'in 7.5 GB resmî IEEE DataPort
> artifact'i/content-ID'si görüldü ve disk ön-kontrolü geçti; indirme
> `Subscription Required` durumundadır. Güncel kararlar
> `docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md`,
> `docs/REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md` ve
> `docs/REAL_DATA_BAWSEG_PREFLIGHT_V1.md` içindedir.

## Sonuç

Bu turda gerçek-veri önceliği sentetik üretimden ayrı tutuldu. GrowingSoy,
DeBlurWeedSeg ve WeedMap erişim, ontoloji, sızıntı ve geliştirme rolleriyle
incelendi. Sonuçlar:

- GrowingSoy kalite kapısını geçti; `%5/%10` eğitim katkısı kendi alanını çok
  artırdı fakat CWFID ve/veya CropAndWeed/Rice alanlarını geriletti.
- DeBlurWeedSeg yalnız tek-saha sharp/motion-blur tanısı olarak kullanıldı.
  Kabul edilmiş kontrolün motion-blur mIoU kaybı `-0,144855` oldu; veri
  bağımsız bir model-seçim seti olmadığı için checkpoint seçmedi.
- WeedMap kalite kapısını geçti ve yeni bir UAV şeker-pancarı alanı sağladı.
  `%2,5/%5` eğitim katkıları WeedMap'i `+0,160505 / +0,177702` yükseltti,
  fakat dondurulmuş mevcut-alan non-inferiority kapılarını geçemedi.
- WeedyRice-RGBMS-DB'nin 734 UAV RGB/maskesi kalite kapısını geçti; 487
  Thoaison partial-label train adayı ve ayrı Longxuyen uçuşunda 247 binary
  calibration karesi üretildi. Kabul edilmiş model ham argmax'ta görüntünün
  `%96,694`'ünü weed söyleyerek specificity `0,068876`'da kaldı; source-frozen
  güvenli recall ise `0,000064` oldu. Veri/model seçmedi.

Bu nedenle kabul edilmiş ortak model değişmedi:

```text
simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8
representative seed: 43
checkpoint: data/runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt
SHA-256: b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f
```

WeedMap sonucu tek-seed ekran kararıdır; hiçbir challenger geçmediği için
seed 29/43 confirmation başlatılmadı. Kilitli external/final test kullanılmadı.

## Güncel gerçek-veri önceliği

Bu turdan sonra en yüksek değerli erişilebilir olmayan aday
[RiceSEG](https://www.global-rice.com/)'dir: 3.078 yüksek çözünürlüklü görüntü,
beş ülke, 12 kurum, tam büyüme döngüsü ve altı semantik sınıf bildirir. Resmî
[Hugging Face kaydı](https://huggingface.co/datasets/PheniX-Lab/RiceSEG)
ile indirme, kullanıcı hesabında iletişim bilgisi paylaşımı koşulunun kabulünü
ve yetkili token'ı gerektirir. Kullanıcı koşulu daha sonra kabul etti; bu
makinede yerel Hugging Face tokenı bulunmadığından indirme hâlâ oturum bekler.
Commit `1a891ced931d5b3ac2a907b045f53414f1a615b4`, altı dosyalık exact set ve
`1.564.399.537` bayt remote metadata ile doğrulandı. Weedy Rice edinimi
sonrasında HDD'de yaklaşık 290 GB boşluk vardır.
`configs/data/riceseg_acquisition_v1.yaml` ve `scripts/acquire_riceseg.py`, dört
LFS dosyası için SHA-256, 50 GiB rezerv, exact file-set, archive path/symlink,
tam CRC ve acquisition receipt kapılarını dondurur. Anonim preflight geçmiştir;
yalnız gated payload indirmesi yerel token bekler.
Erişim açıldığında bir sonraki gerçek-veri gate'i RiceSEG olmalıdır.

Bu bekleme sırasında erişilebilir
[WeedyRice-RGBMS-DB](https://data.mendeley.com/datasets/vt4s83pxx6/1)
indirildi ve tam gate'ten geçirildi. Dış/iç arşiv SHA-256'ları
`62c9a168...6aff3 / e1cf031b...86395`, iki katmanlı full CRC ve 5.145
dosyalık exact release denetimi geçti. Publisher'ın 438/148/148 listelerinin
her biri dört `%70`-overlap uçuşu da içerdiği için bu split reddedildi; üç
Thoaison uçuşu train adayı, ayrı Longxuyen uçuşu development oldu. Source
`0` cultivated rice/background karışımı olduğundan ortak ontolojide ignore
kaldı ve ortak-model eğitimi açılmadı. Ayrıntılı kanıt
`docs/REAL_DATA_WEEDY_RICE_UAV_AUDIT_V1.md` içindedir.

## 2026 erişilebilir kaynak tekrar taraması

RiceSEG oturumu beklerken yalnız yeni, piksel-seviyeli ve tarla kaynaklı
adaylar birincil yayın/repository kanıtıyla yeniden tarandı:

| Kaynak | Kanıt | Karar |
|---|---|---|
| [BAWSeg](https://www.mdpi.com/2072-4292/18/6/915) | Dört yıl, iki ticari barley paddock ve dense crop/weed/other etiketi; IEEE DataPort artık `Multispectral Image Benchmark Dataset.zip` (7.5 GB), content ID 101935 gösteriyor | Kamu/disk gate'i geçti; `Subscription Required`. Authenticated archive, merkez-dizin/CRC/iç-SHA ve paket lisansı bekleniyor; henüz matrise/eğitime eklenmedi |
| [CWD30-S](https://cwd-30.github.io/cwd-30/) | Resmî sayfa semantic uzantıyı `Coming Soon` olarak gösterir | Byte-level release yok; indirme yok |
| [Weeds-Banana](https://doi.org/10.1016/j.atech.2026.101875) | 272 RGB/NIR+binary patch'in tamamı Ekvador'daki tek 4,3 ha parselde, Nisan 2024 11:00–12:00 uçuşundan gelen tek `5571×5855` orthomosaic ve maskeden üretilmiştir; yayın 218/27/27 patch split'i kullanır | 4,32 GB paket indirilmedi: tek kaynak orthomosaic, komşu-karo korelasyonu ve weed-only ontoloji yeni bağımsız robust coverage sağlamaz |
| [CoFly-WeedDB](https://zenodo.org/records/6697343) | 201 RGB, tek cotton field/tek UAV coverage mission; yalnız üç weed türü ve background etiketi, cotton crop sınıfı yok | Weedy Rice'a göre daha küçük/tek-saha partial-label tekrar; indirilmedi |
| [Potato Weed v2](https://data.mendeley.com/datasets/xbmktnnsmb/2) | 813 RGB+813 txt eşleşmesi, fakat 6.014 satırın 39'u YOLO box ve 5.975'i dört-köşe polygon; 5.973 polygon tam eksen hizalı dikdörtgendir | Dense semantic maske değildir; 97.748.442 bayt arşiv yalnız candidate quarantine'da tutuldu ve dönüştürülmedi |

Potato taramasının SHA-256/CRC, dosya sayımı ve geometri makbuzu
`data/processed/audits/potato_weed_v2_candidate_screening.json` içindedir.
Bu retler “veri kötü” iddiası değildir; mevcut crop/weed semantic loss ve
bağımsız-domain benchmark amacı için uygun olmadıklarını belirtir.

Yeni bir tek-saha kaynağı veya daha fazla karışım oranı aramak, çok-ülkeli ve
tam gelişim döngülü veri açığını kapatmaktan daha düşük önceliklidir.

## GrowingSoy özeti

Pinli MIT kaynak ağacından 1.000 gerçek görüntü dönüştürüldü. Yayıncı rastgele
split'i ve augmented-labeled ağaç kullanılmadı; çıkarılan boylamsal
trajectory B'nin 541 karesi train, tamamen ayrı trajectory A'nın 459 karesi
development-only `external_calibration` oldu. Exact/dHash sızıntı ve görsel
kalite kapıları geçti.

Seed-17 eşit-bütçeli ekranında:

| Katkı | GrowingSoy Δ | CWFID Δ | CropAndWeed Δ | Rice Δ | Robust Δ | Karar |
|---|---:|---:|---:|---:|---:|---|
| `%5` | +0,284888 | -0,097095 | -0,015299 | -0,049882 | -0,049882 | Red |
| `%10` | +0,296242 | -0,048174 | -0,014734 | +0,020746 | +0,020746 | Red |

`%10` kol robust minimumu artırsa da CWFID ve CropAndWeed bireysel
non-inferiority kapılarını aşarak geriledi. Sonuç, tek bir boylamsal sahada
yüksek in-domain kazancın ortak-model robustluğu için yeterli olmadığını
gösterir.

Kanonik karar:
`data/processed/audits/real_data_growingsoy_screen_selection_v1.json`.

## DeBlurWeedSeg motion-blur tanısı

Yayıncı train/val ve yayıncı model kullanılmadı. Tek deneysel sorgum
sahasındaki publisher-test bölümünün 100 sharp + 100 motion-blur görüntüsü
yalnız `external_calibration` rolüne alındı. İki modalite aynı capture-group
altında tutuldu; unseen-field veya bağımsız test iddiası yapılmadı.

Kabul edilmiş kontrolün seed 17/29/43 ortalaması:

| Metrik | Sharp | Motion blur | Blur − sharp |
|---|---:|---:|---:|
| mIoU | 0,525724 | 0,380869 | -0,144855 |
| Crop IoU | 0,351107 | 0,160609 | -0,190498 |
| Weed IoU | 0,245564 | 0,035578 | -0,209986 |

Tanısal kapı 0/3 seed geçti. Bu veri model seçmedi; sonuç gerçek motion-blur
eğitim verisi ve kamera/exposure çeşitliliği ihtiyacını nicelleştirir.

Kanonik protokol ve makbuzlar:

- `configs/benchmark/deblurweedseg_motion_blur_protocol_v1.yaml`
- `data/processed/audits/deblurweedseg_motion_blur_diagnostic_v1.json`

## WeedMap edinim ve immutable provenance

Resmî ETH bitstream'i bu makineden HTTP 403 döndürdüğü için arşiv, kayıtlı
OPIA aynasından indirildi; resmî DOI ve hak beyanı kanonik kaynak olarak
korundu.

```text
archive: data/raw/weedmap/archives/WeedMap_OPIA_2023.zip
bytes: 4.480.204.702
SHA-256: 8247a5a2e690ee77a34eb7bdcb3a1729c7ce3c8f6ef3ef9ff93067f17e90c53b
members/files: 18.875 / 18.746
compressed/uncompressed: 4.476.313.284 / 5.362.213.286 bytes
full ZIP CRC: pass
unsafe path/symlink: 0 / 0
```

Checksum yerelde edinim kimliği olarak hesaplandı; ETH ve OPIA bu nesne için
kriptografik checksum yayımlamıyor. Veri hakkı `In Copyright - Non-Commercial
Use Permitted` olduğundan yalnız research track'tedir. Arşivdeki LGPL MATLAB
scriptleri veri hakkını değiştirmez.

İndirme öncesi HDD'de yaklaşık 310 GB boş alan vardı. Dönüşüm ve iki model
ekranından sonra aynı veri diskinde yaklaşık 308 GB boş alan kaldı; arşiv
`4,2 GiB`, normalize WeedMap ağacı `125 MiB`, iki challenger koşusu toplam
yaklaşık `576 MiB` kullanır. Kök diskte veri tutulmadı.

## Release anomalileri ve fail-closed çözüm

Yayın README'si ile gerçek arşiv arasında üç uyuşmazlık vardı. Model
çalıştırılmadan önce gözlenebilir arşiv kanıtıyla sabit çözüldü:

1. README `1=crop`, `10000=non-class` der; 970 indexed label'ın hiçbirinde
   `1` yoktur. Bundled MATLAB stitcher `10000` değerini crop index `1`e
   çevirir ve 970/970 renk eşleşmesinde `10000=green crop`, `2=red weed`,
   `0=black background` doğrulanır. Ortak eşleme `0→background`, `2→weed`,
   `10000→crop` olarak donduruldu.
2. README validity mask polarity'sini ters tarif eder. Tüm 167.616.000
   RedEdge pikselinde `mask=0` tam olarak non-black RGB alanı, `mask=255`
   tam olarak siyah padding alanıdır. `0=valid`, `255=ignore` kullanıldı.
3. Yayıncı 497 effective RedEdge tile bildirir; arşivde 557 non-black tile
   vardır ve hangi tile'ların elendiği yayımlanmamıştır. Uniform örneklemede
   neredeyse boş kenar sliver'larını önlemek için modelden önce tüm haritalara
   sabit `%5` valid-pixel tabanı uygulandı. 519 tile kabul edildi; yayıncı
   listesini yeniden ürettiğimiz iddia edilmez.

Sequoia CIR 005–007 subset'inde gerçek blue kanal olmadığı için ortak RGB
benchmark'ından çıkarıldı. Yalnız RedEdge-M true-RGB 000–004 haritaları
kullanıldı.

## WeedMap roller ve kalite kapıları

Tüm seçili haritalar aynı Rheinbach şeker-pancarı sahasının 2017-09-18 UAV
uçuşundan gelir. Orthomosaic kimlikleri ayrı mekânsal gruplardır, bağımsız
tarla değildir.

| Harita | Kaynak tile | Tamamen geçersiz | `%5` altı | Kabul | Rol |
|---|---:|---:|---:|---:|---|
| 000 | 221 | 104 | 10 | 107 | train |
| 001 | 176 | 79 | 7 | 90 | train |
| 002 | 252 | 93 | 9 | 150 | train |
| 003 | 204 | 102 | 7 | 95 | external calibration |
| 004 | 117 | 35 | 5 | 77 | train |
| **Toplam** | **970** | **413** | **38** | **519** | **424 / 95** |

Kalite sonucu:

| Gate | Sonuç |
|---|---|
| Görüntü/maske eksik, shape mismatch, geçersiz sınıf | 0 / 0 / 0 |
| Indexed/color ontoloji uyuşmazlığı | 0 / 970 |
| Valid-mask/RGB footprint uyuşmazlığı | 0 / 167.616.000 piksel |
| Train/calibration grup çakışması | 0 |
| 519 aday × 12.818 mevcut gerçek referans exact/dHash≤2 eşleşme | 0 |
| Aday-içi cross-role exact/dHash≤2 eşleşme | 0 |
| Stratified ve ham-arşiv overlay görsel QC | Pass |

Ortak maske pikselleri background/crop/weed/ignore için sırasıyla
`67.864.881 / 3.271.655 / 2.532.646 / 16.014.018`'dir.

Kanonik manifestler:

```text
weedmap.csv                 fd8d01faa5284b52c6a7039ed0ccd001cc544c4f7d1ab75cbb87ec50b05e7005
weedmap_train_v1.csv        ebbd6ce78c2fbab260cc89acd6bbeb240cada6946d4fd6ec151423581c664d85
weedmap_calibration_v1.csv  da5311e80cf51534a1af51df1b3ffb3543a21d0426a0fd5fb74240cd778f6be9
```

Kabul edilmiş 5.903 satırlık kontrol manifestine yalnız 424 train satırı
eklenerek 6.327 satırlık challenger manifesti üretildi. Map 003 ve hiçbir
external/final test bu manifestte yoktur. Train/calibration group overlap
`0`'dır.

## Dondurulmuş WeedMap model ekranı

Kurallar challenger eğitiminden önce donduruldu:

- seed `17`, epoch `8`, `last.pt`, kol başına `8 × 3.600 = 28.800` draw;
- mimari ve hiperparametreler aynı;
- sentetik exposure `%10` sabit;
- WeedMap `%2,5/%5`, eski gerçek draw'ları oransal olarak ikame eder;
- mevcut altı alan: source, CWFID, Sorghum, CropAndWeed, Rice, GrowingSoy;
- genişletilmiş alanlar bu altıya WeedMap'i ekler;
- WeedMap kazanımı en az `+0,01`;
- mevcut/genişletilmiş robust ve macro gerilemesi yasak;
- her mevcut alan için azami mIoU gerilemesi `0,01`;
- DeBlurWeedSeg raporlanır fakat seçime katılmaz.

Kontrol koşusu yeniden eğitilmedi; seed-17 checkpoint, summary, history ve
resolved-config artefaktları byte-for-byte tekrar kullanıldı.

### Mutlak mIoU

| Tarif | Source | CWFID | Sorghum | CropAndWeed | Rice | GrowingSoy | WeedMap |
|---|---:|---:|---:|---:|---:|---:|---:|
| Kabul edilmiş kontrol | 0,801428 | 0,638260 | 0,819230 | 0,697676 | 0,384724 | 0,429324 | 0,349823 |
| WeedMap `%2,5` | 0,798138 | 0,587849 | 0,809908 | 0,650499 | 0,428065 | 0,463059 | 0,510329 |
| WeedMap `%5` | 0,799413 | 0,578236 | 0,813205 | 0,677341 | 0,365100 | 0,503113 | 0,527525 |

### Kontrole karşı fark ve aggregate sonuç

| Tarif | WeedMap Δ | CWFID Δ | CropAndWeed Δ | Rice Δ | GrowingSoy Δ | Mevcut robust Δ | Mevcut macro Δ | Geniş robust Δ | Karar |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `%2,5` | +0,160505 | -0,050411 | -0,047177 | +0,043341 | +0,033735 | +0,043341 | -0,005521 | +0,078241 | Red |
| `%5` | +0,177702 | -0,060024 | -0,020335 | -0,019623 | +0,073789 | -0,019623 | -0,005706 | +0,015277 | Red |

`%2,5` kol WeedMap crop IoU'yu `0,001239 → 0,338145`, `%5` kol
`0,359133` yaptı. Veri açıkça yeni alanı öğretiyor; reddin nedeni yetersiz
in-domain öğrenme değil, ortak-model non-inferiority kaybıdır.

`%2,5` kol CWFID, CropAndWeed ve mevcut-macro kapılarını; `%5` kol bunlara ek
olarak Rice ve mevcut-robust kapılarını kaybetti. İki aday da geçmediği için
üç-seed confirmation veya daha büyük WeedMap üretimi/eğitimi açılmadı.

## Yorum ve bir sonraki en küçük deney

Bu sonuçlar şu iddiaları destekler:

1. Tek-saha UAV verisini global sampler'a eklemek, o alanı büyük ölçüde
   iyileştirebilir fakat yakın-saha ve farklı anotasyon dağılımlarında
   forgetting yaratabilir.
2. Daha yüksek WeedMap oranı monoton robust iyileşme sağlamadı. `%5`, WeedMap
   ve GrowingSoy'u daha çok artırırken Rice robust minimumunu düşürdü.
3. Aynı karışımın `%1/%2/%7,5` gibi ek oranlarını aramak, çok-saha coverage
   eksikliğini çözmez ve şu kanıttan sonra düşük önceliklidir.

Öncelik sırası (RiceSEG edinimi/model kapısı sonrası güncelleme):

1. BAWSeg authenticated arşivini extraction yapmadan merkez-dizin/CRC/iç-SHA
   ve lisans kapısından geçir; ancak sonra field/year-ayrık RGB protokolü.
2. Weedy Rice'ın 487 kaliteli pozitif-kısmi eğitim adayı
   için ayrı partial-label/specialist loss protokolü; source-zero hiçbir zaman
   ortak background/crop supervision olmayacaktır.
3. Gerçek motion-blur, kamera yüksekliği ve saha çeşitliliği olan yeni
   train/calibration kaynağı.
4. Ancak yeni coverage sağlandıktan sonra replay-balanced sampler veya
   crop/domain-conditioned adapter gibi ortak-model forgetting kontrolleri.

WeedMap tek başına specialist/adapter geliştirme verisi olarak ileride yeniden
kullanılabilir; bu rapor yalnız test edilen global-mixture tariflerini
reddeder. External test, safety selector ve spray deployment bu protokolün
kapsamı değildir.

## Reprodüksiyon ve kanonik kanıtlar

```bash
.venv/bin/python scripts/convert_weedmap.py \
  --gate-config configs/data/weedmap_real_gate_v1.yaml

.venv/bin/agri-seg benchmark \
  configs/benchmark/real_data_weedmap_screen_v1.yaml

.venv/bin/python scripts/select_real_data_weedmap.py \
  --protocol configs/benchmark/real_data_weedmap_selection_protocol_v1.yaml \
  --benchmark data/runs/real_data_weedmap_screen_v1/benchmark_results.json \
  --output data/processed/audits/real_data_weedmap_screen_selection_v1.json
```

Ana kilitler:

```text
selection protocol  de8d735a823f0bbbe18b76f301cee0c7b7e2d718367c4959827ba480a643005e
screen matrix       efd040caf83ad3cb9fe8f74a25c9ee4ec688536657cd74e254fa92ff2129dd83
benchmark receipt   6f3026c32f2bbb3e808b2a238e4b48ec3f41a991ebafcbe401ae6c40bdb052ad
selection receipt   dff12ebfee31ee1db4008176f4d08b90c96b51cf54cf6a305f31c01af93b7ebd
```

Seçim makbuzu:
`data/processed/audits/real_data_weedmap_screen_selection_v1.json`.

Bu bir araştırma robustness kararıdır; saha, püskürtme, ticari kullanım veya
genel SOTA iddiası değildir.
