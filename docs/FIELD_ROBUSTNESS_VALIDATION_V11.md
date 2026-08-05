# Tarla bağımsızlığı V10/V11 model kapısı

Tarih: 2026-08-04

## Sonuç

Tarla/yüzey/aydınlatma çeşitliliği için üretilen V10 ve profilli V11
sentetik katkılarının ikisi de gerçek-saha model kapısında reddedildi.
Kabul edilmiş global model değişmedi:

```text
simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8
temsilci seed: 43
checkpoint SHA-256: b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f
```

V10 gerçek seçim skorunu artırdı, ancak CWFID ve mevcut gerçek çekirdek
alanlarında dondurulmuş non-inferiority sınırlarını aştı. V11'in
korelasyonlu hava/yüzey/ışık profilleri bu sorunu düzeltmedi; hedefe yakın
gerçek domain makrosunu daha da düşürdü. Bu nedenle seed 29/43
confirmation ve yeni model-güdümlü asset iterasyonu açılmadı.

Sentetik val/test'in gerçek seçim skorundaki ağırlığı her iki deneyde de
tam `0.0`'dır. Bu çalışma deployment veya spray-safety onayı değildir.

## Dondurulmuş gerçek seçim kontratı

Seçim birimi görüntü veya piksel değildir. Önce her field/session, sonra
her gerçek dataset/domain eşit oy alır. Birleşik skor:

- `%60` hedefe yakın gerçek domain makrosu;
- `%25` breadth gerçek domain makrosu;
- `%15` tüm gerçek field/session birimlerinin alt `%25` kuyruğu.

Hard non-inferiority sınırları model çıktısından önce donduruldu:

- herhangi bir hedef domain: en fazla `-0.010` mIoU;
- herhangi bir breadth domain: en fazla `-0.015` mIoU;
- herhangi bir field/session: en fazla `-0.025` mIoU;
- hedef makro: en fazla `-0.005`;
- alt-kuyruk: en fazla `-0.010`;
- toplam skor: en fazla `-0.002` regresyon ve kabul için en az `+0.002`
  ortalama kazanç.

283 ardışık Sugar Beets 2016 karesi tek field/date/session ve tek dataset
oyu olarak sayılır. Panel artık development/holdout karşılaştırmasında
tüketilmiştir; 283 bağımsız saha kanıtı değildir.

## V10 tamamlanan seed-17 ekranı

V10, 14 CC0 soil ve 14 HDRI ailesiyle nem, tillage, clod, güneş,
lokal gölge ve robot ışığını randomize eden 48 train + 12 val + 12
test karelik pakettir. A/B'de toplam sentetik oran `%10` tutuldu; challenger
yalnız dryland V3 payının `%2,5`'ini V10 ile değiştirdi.

| Seed-17 gerçek skor farkı | V10 − kontrol |
|---|---:|
| birleşik gerçek seçim skoru | `+0.006884` |
| target-like domain makrosu | `+0.003331` |
| breadth domain makrosu | `+0.014153` |
| field alt-kuyruk | `+0.008981` |
| CWFID | `-0.048846` |
| mevcut gerçek çekirdek | `-0.029437` |
| SugarBeets2016 holdout | `+0.012674` |
| en kötü field/session | `-0.311180` |

Ortalama kazanç kapıları geçti, fakat paired non-inferiority geçmedi:
111 gerçek field/session biriminin 21'i `-0.025` sınırını kaybetti.
Sonuç `accepted=false`'tur.

Kanonik skor:

```text
data/processed/audits/target_weighted_field_robustness_prescreen_v10_r2.json
SHA-256 c75dda65283d4dd255470efa8db4b57c3969e904f42bac43e6f9fa59c6f2a165
```

## V11 hipotezi ve veri kapıları

V10'da aynı kare içinde birbirinden bağımsız uç koşulların birikmesi ve
train crop oranının V3'ten yaklaşık `%25` düşük olması olası task
interference olarak belirlendi. V11 bu nedenle aynı lisanslı V10 asset
paketini, V3'e daha yakın bitki/kamera kompozisyonunu ve fiziksel olarak
birbiriyle uyumlu dört profili kullandı:

1. `clear_day`;
2. `overcast_moist`;
3. `low_sun`;
4. `robot_light_low_ambient`.

Yeni haricî botanik mesh sırf asset sayısını artırmak için eklenmedi.
Mevcut erken-dönem crop/weed ontolojisine uymayan bir asset, yüksek poligon
veya görsel kaliteye sahip olsa da bu gate için doğru veri değildir.

### R1: reddedilen üretim

R1'in 80 train karesi iki önceden dondurulmuş kalite kapısını kaybetti:

- ortalama crop piksel oranı `0.007548 < 0.008`;
- robot-ışığı warmth açıklığı `0.61565 < 0.70`.

Eşikler gevşetilmedi. R1 reddedilmiş kanıt olarak tutulur:

```text
data/synthetic/cropcraft/field_robustness_pilot_v11_r1/roles/train/release_receipt.json
SHA-256 dc0e05e7875c38d725fc35738381b0d04c1336d98662688292f824650d5ad8cc
```

### R2 ve nesnel R2Q karantinası

R2, hafif daha yoğun satırlar, V3'e yakın kamera oranı ve deterministik
stratified endpoint'lerle 80 train + 16 val + 16 test kare üretti. Tüm
generation, seed ve asset-disjoint kapıları geçti. Train crop/weed piksel
oranları `0.009401 / 0.018917` oldu; her rol dört profili kapsadı.

Tam R2 release'i yine de kabul edilmedi. Sabit radyometri taraması yalnız iki
train outlier' buldu:

- `scene_0034/frame_0002`: ortalama parlaklık `39.603 < 40`;
- `scene_0035/frame_0002`: beyaz clip oranı `0.0040245 > 0.002`.

Val/test'te ihlal yoktu; manuel RGB-mask hizası ve sahne plausibility kontrolü
geçti. Tam R2 visual receipt bu nedenle bilinçli olarak `passed=false`'tur:

```text
data/synthetic/cropcraft/field_robustness_pilot_v11_r2/visual_review_receipt.json
SHA-256 cf2bf09c55db41dea78ae7c6721e5cc669cdb1e0ea995692650ca958de8b6142
```

Sonuç görülmeden dondurulmuş, yalnız otomatik radyometri ihlallerini ve
en fazla `%2,5` train karesini dışlayan türetme kuralı iki kareyi karantinaya
aldı. Hiçbir val/test karesi filtrelenmedi. Model gate'ine uygun tek V11
verisi bu türetilmiş `R2Q` sürümüdür:

| R2Q rol | Kare | Profil dağılımı |
|---|---:|---|
| train | 78 | `20 / 20 / 19 / 19` |
| synthetic-val | 16 | her profil `4` |
| synthetic-test | 16 | her profil `4` |

```text
manifest SHA-256:   576bf35a4ed203534a89d836a5a3eb23c966c99ee43a6df98a848e39cedd0aa1
conversion SHA-256: 6ec8ebfab7cb4e33c5866f259c81b9d783d9f22afd6911a248964ede2657dd08
```

Birleşik A/B manifesti 4.344 train + 1.637 val satırı içerir. Yalnız 78
R2Q train satırı eklendi; 32 sentetik val/test satırı kaynak validation'dan
hash-kilitli olarak dışlandı:

```text
data/processed/manifests/real_sorghum_cropcraft_v3_025_fieldrobust_v11_025_paddy05_trainval_v11_r2q.csv
SHA-256 af739cbe535c542bf5a836efc8fd013c551431683a4225f3819cd02ab045d6e7
```

## V11-R2Q seed-17 gerçek model ekranı

Kontrol ve challenger aynı `%90` gerçek / `%10` sentetik sampler bütçesini,
8 epoch'u, seed 17'yi ve kaynak kodunu kullandı. Challenger sentetik bütçesi
`%2,5 V3 + %2,5 V11-R2Q + %5 paddy R5` idi.

| Resmî alan-makro skor | Kontrol | V11-R2Q | Fark |
|---|---:|---:|---:|
| birleşik gerçek seçim skoru | `0.505326` | `0.495253` | `-0.010073` |
| target-like domain makrosu | `0.540444` | `0.524482` | `-0.015962` |
| breadth domain makrosu | `0.449403` | `0.451884` | `+0.002481` |
| field alt-kuyruk | `0.458057` | `0.450622` | `-0.007435` |
| tanısal crop IoU makrosu | `0.384847` | `0.372525` | `-0.012321` |
| tanısal weed IoU makrosu | `0.239252` | `0.223874` | `-0.015378` |

Domain sonuçları:

| Gerçek domain | Panel | mIoU farkı | Kapı |
|---|---|---:|---|
| CropAndWeed | target | `-0.013418` | FAIL |
| CWFID | target | `-0.063426` | FAIL |
| DeBlur motion | breadth | `+0.027293` | PASS |
| DeBlur sharp | breadth | `-0.017268` | FAIL |
| GrowingSoy | target | `+0.027130` | PASS |
| mevcut gerçek çekirdek | target | `-0.006053` | PASS |
| Rice Seedling | target | `+0.003233` | PASS |
| RiceSEG country transfer | target | `-0.018608` | FAIL |
| SorghumWeed | target | `+0.002730` | PASS |
| SugarBeets2016 holdout | target | `-0.059287` | FAIL |
| Tobacco UAV | breadth | `-0.000964` | PASS |
| WeedMap UAV | breadth | `+0.000861` | PASS |

111 field/session biriminin 30'u `-0.025` sınırını kaybetti. En kötü
alan farkı CropAndWeed `vwg-0171` için `-0.310163` oldu. Dolayısıyla
ortalama kazanç, hedef-makro, domain ve field non-inferiority kapılarının
tamamı geçmedi; `accepted=false` ve seed-17 galibiyeti `0`'dır.

Sentetik tanısal makro V11-test'te `+0.003716`, V11-val'de `-0.009170`
değişti. Sentetik testteki küçük kazanç gerçek hedef makrodaki kaybı
öngörmedi; sentetik val/test'i model seçimine sokmama kararını doğrular.

Kanonik skor ve benchmark:

```text
data/processed/audits/target_weighted_field_robustness_prescreen_v11_r2q.json
SHA-256 0e7e60ce26c35890d922f7395ce88db29edfdbc7a66125e062117eb74d6cf846

data/runs/simulation_field_robustness_screen_v11_r2q/benchmark_results.json
SHA-256 0c0616f0ab611699fa24bf1d8cc68de1b632f50a87c274890eb2fbbd06a5d89b
```

## Karar ve sonraki en yüksek değerli iş

V11 asset kalitesi kontrollü olarak iyileştirilmiş olsa da global model
katkısı kanıtlanmadı. Daha fazla aynı-prosedürel botanik veya model sonucuna
göre surface tuning yapmak, 111 alanlı development paneline overfit riskini
artırır. Dondurulmuş protokol gereği bu V11 hattı burada durur.

En yüksek değerli sonraki veri adımları:

1. farklı ülke, tarla, tarih, hava ve kamera yüksekliğinden en az bir yeni
   gerçek robot-camera holdout;
2. SugarBeets dönüşümünün bağımsız agronomist spot-check'i;
3. etiketli yeni alan gelene kadar sentetiği global sampler yerine stres
   tanısı veya crop-routed specialist girdisi olarak tutmak;
4. BAWSeg arşivi için IEEE DataPort abonelik oturumu sağlanırsa arşiv,
   lisans ve cross-year/cross-plot split kapılarını tamamlamak.

## Yeniden çalıştırma

```bash
.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_field_robustness_screen_v11_r2q.yaml

.venv/bin/python scripts/score_target_weighted_field_benchmark.py \
  --protocol configs/benchmark/target_weighted_field_robustness_prescreen_v11_r2q.yaml \
  --benchmark configs/benchmark/target_weighted_field_robustness_screen_matrix_v11_r2q.yaml \
  --output data/processed/audits/target_weighted_field_robustness_prescreen_v11_r2q.json
```

Tamamlanan challenger run'ı kaynak ağaç SHA-256
`fda1a1c4b715601b6d66bfdaa28637db43154ccf2f01cc2f63669119dc3142eb`
ve normalize maske-ağaç SHA-256
`01fc4e17dfc3bcde54892a0a9215725665eab4af4c9de56a746e3fcaf0fbfe97`
ile provenance-kilitlidir.
