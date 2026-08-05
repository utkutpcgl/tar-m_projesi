# Gerçek veri coverage ve CropAndWeed gate raporu — v2

## Sonuç

Mevcut gerçek çekirdekteki en yüksek değerli erişilebilir boşluk için
[CropAndWeed](https://github.com/cropandweed/cropandweed-dataset) seçildi.
Kaynak, mevcut robot/UAV havuzundan farklı bir 1,1 m üstten DSLR perspektifi,
929 ham çekim oturumu ve nem/toprak/ışık/ayrıştırma-zorluğu metadata'sı sağlar.
Veri gate'i geçti; model katkısı ise önceden dondurulmuş eşit-bütçeli ablation
ile ayrı değerlendirilmektedir.

Bu kaynak yalnız `research_max` hattındadır. Yayıncı lisansı ticari olmayan
kullanıma izin verir, ham veya değiştirilmiş verinin yeniden dağıtımını
yasaklar ve geri döndürülemeyen eğitilmiş soyut temsillere izin verir. Bu teknik
özet hukuki görüş değildir.

## Başlangıç coverage'ı

`real_core_final.csv`, beş kaynaktan 6.371 görüntü, 48 manifest çekim grubu,
sekiz ürün ve şu perspektifleri içeriyordu: UAV, yer robotu, manuel trolley,
dört ROSE robotu ve saha multispektral kamerası. Botanik ürün dağılımı:

| Ürün | Görüntü |
|---|---:|
| Beta vulgaris | 2.589 |
| Zea mays | 1.684 |
| Phaseolus vulgaris | 1.110 |
| Glycine max | 303 |
| Vicia faba | 210 |
| Pisum sativum | 205 |
| Fagopyrum esculentum | 137 |
| Helianthus annuus | 133 |

Ana boşluklar ülke/saha çeşitliliğinin sınırlı olması, yer seviyesinde bağımsız
DSLR görüntüsünün azlığı, ayrıntılı hava/toprak metadata'sının yokluğu ve bazı
ürünlerin tek kaynağa bağlı olmasıydı.

## Aday kaynak kararı

| Kaynak | Karar | Gerekçe |
|---|---|---|
| CropAndWeed | **Seçildi** | 8.034 maskeli RGB, 929 oturum, 9 kullanılabilir hedef ürün, 4 koşul alanı, yeni kamera geometrisi |
| [RiceSEG](https://www.global-rice.com/) | Sonraki erişim adayı | Beş ülke ve tüm büyüme döngüsü değerli; indirme erişim-gated ve site/HF lisans sunumu ayrıca uzlaştırılmalı |
| Weed/crop robot bbox kaynakları | Elendi | Piksel maskesi yerine yalnız bbox; bu fazın segmentasyon hedefi için zayıf |
| SugarBeets2016 | Ertelendi | Mevcut şeker pancarı ve yakın-saha coverage'ıyla yüksek tekrar |
| VegAnn | Ertelendi | Vegetation-only kısmi etiket; ayrı partial-label loss ablation'ı gerekli |
| WeedMap | Ertelendi | Mevcut PhenoBench UAV kapsamına göre daha düşük öncelik |

CropAndWeed için sayılar yayıncının [WACV 2023 makalesi](https://openaccess.thecvf.com/content/WACV2023/html/Steininger_The_CropAndWeed_Dataset_A_Multi-Modal_Learning_Approach_for_Efficient_Crop_WACV_2023_paper.html),
resmî repository ve indirilen arşivlerin doğrudan denetiminden gelir.

## İndirme ve immutable provenance

Beş resmî TAR toplam `11.470.154.240` bayttır. Arşiv boyutları ve SHA-256
değerleri `configs/datasets.yaml` içine kaydedildi. Annotation arşivi SHA-256:

```text
52444898ff142e95051c40073121fd509f2dee9e7766eadd8608b52785584041
```

Resmî kod snapshot'ı:

```text
e471c47971af431f4fb8d7463f6b4c9e2b3b35fa
```

Tüm TAR üyeleri için absolute path, `..`, link ve özel dosya kontrolleri
geçti. 8.034 RGB, semantik maske, bbox ve params stem'i bire bir eşleşti.

## Fail-closed ontoloji gate'i

Ortak hedef `background / target crop / other vegetation / ignore` olduğu için
ham görüntü ancak semantik maskesinde tam bir resmî hedef ürün grubu varsa
kabul edildi.

| Karar | Görüntü |
|---|---:|
| Tam bir hedef ürün — kabul | **4.584** |
| Hedef ürün yok — dışla | 3.341 |
| Birden fazla hedef ürün — dışla | 109 |

Ham `255` belirsiz vegetation ve CropAndWeed'in resmî crop/weed üst
ontolojisine girmeyen türler `ignore` oldu; hiçbir belirsiz bitki background'a
çevrilmedi. Semantic maskeler segmentasyon için otoritatif tutuldu. 66/8.034
maskede bbox ile semantic label-set farkı raporlandı; oran `%0,822` ve piksel
maskesi sağlam olduğundan örnekler sessizce yeniden eşlenmedi.

Kabul edilen ürünler ve dondurulmuş roller:

| Ürün | Train | External calibration | Toplam |
|---|---:|---:|---:|
| Zea mays | 1.403 | 350 | 1.753 |
| Beta vulgaris | 952 | 238 | 1.190 |
| Helianthus annuus | 390 | 98 | 488 |
| Glycine max | 262 | 66 | 328 |
| Cucurbita spp. | 253 | 63 | 316 |
| Vicia faba | 172 | 43 | 215 |
| Pisum sativum | 140 | 35 | 175 |
| Solanum tuberosum | 83 | 23 | 106 |
| Phaseolus vulgaris | 12 | 1 | 13 |

## Oturum-ayrık split

Split, model çalıştırılmadan önce annotation'lardan MILP ile donduruldu.
Hedef ürün, AVE/VWG seti, nem, toprak, ışık, ayrıştırma zorluğu ve yararlı
etkileşimler yaklaşık `%80/%20` korunurken bir çekim oturumu yalnız tek role
girebilir.

| Rol | Görüntü | Oturum |
|---|---:|---:|
| Train | 3.667 | 350 |
| External calibration | 917 | 87 |

Koşul marjinalleri:

| Alan | Değerler | Train | Calibration |
|---|---|---|---|
| Moisture | dry / medium / wet | 1.964 / 1.000 / 703 | 493 / 249 / 175 |
| Soil | fine / medium / coarse | 3.639 / 13 / 15 | 903 / 3 / 11 |
| Lighting | sunny / diffuse | 2.702 / 965 | 676 / 241 |
| Separability | easy / medium / hard | 3.518 / 140 / 9 | 880 / 35 / 2 |

Kaba toprak yalnız iki uygun oturumdan geldiği için görüntü oranı `%20`
olamaz; bir oturum bütünüyle calibration'a ayrıldı. Hard separability ve common
bean sonuçları düşük örnekli tanısal dilimlerdir, güçlü istatistiksel kanıt
değildir.

## Quality gate sonuçları

| Gate | Sonuç |
|---|---|
| Eksik görüntü/maske | 0 |
| Shape mismatch | 0 |
| Geçersiz ortak maske sınıfı | 0 |
| Train/calibration grup sızıntısı | 0 |
| CropAndWeed içi dHash-256, Hamming ≤2 eşleşmesi | 0 / 4.584 |
| Tüm roller arası dHash-256, Hamming ≤2 eşleşmesi | 0 / 11.142 |
| Rastgele 36 overlay görsel QC | Pass |
| Ürün+koşul stratified 45 overlay görsel QC | Pass |

Kanonik manifest SHA-256:

```text
63fead62f9cdd92e3c21129d6b8e6e09a2df672395661757a7e64b969f124399
```

Normalize maske ağacı SHA-256:

```text
736a4009fce53778a926dbef466f71467d564664a6afe823c1ca95c44686a7f1
```

Tam makbuz `data/processed/audits/real_data_cropandweed_freeze_v1.json`
içindedir.

## Bilinen bağımsızlık sınırları

- AVE birkaç yüz Avusturya ticari sahasını kapsar; fakat yayıncı görüntü
  başına gerçek saha kimliği vermediği için `field_id` sentetik olarak
  çoğaltılmadı. Oturum kimliği korunur.
- VWG ile WE3DS Groß-Enzersdorf araştırma bölgesini paylaşır. 11.142 görüntülük
  denetimde piksel/çok-yakın kopya yoktur; yine de coğrafi bağımsızlık iddia
  edilmez.
- Bu 917 görüntü ilan edilmiş development calibration'dır; yeni untouched
  final test değildir.
- Kaynak Avrupa ağırlığını azaltmıyor. Sonraki gerçek-veri önceliği, lisansı
  net ve oturum/saha kimliği doğrulanabilir çok-ülkeli pirinç veya benzeri bir
  dış-domain maskeli kaynaktır.

## Dondurulmuş model katkı deneyi

Kontrol, kabul edilmiş CropCraft v3 stack'idir. CropAndWeed `%10` ve `%20`
maruziyetleri, sentetik oran `%10` ve toplam `8 × 3.600` eğitim örneği sabitken
taranır. Source validation, CWFID, Sorghum validation ve 917 CropAndWeed
calibration mIoU'nun minimumu birincil metriktir. Her eski development alanı
için izin verilen gerileme en fazla `0,01`'dir. Tarihsel kilitli testler bu
seçimde okunmaz.

Kontrolün CropAndWeed zero-shot sonucu:

| Metrik | Değer |
|---|---:|
| mIoU | 0,694439 |
| Crop IoU | 0,821262 |
| Weed IoU | 0,268277 |

Bu sonuç yeni verinin özellikle `other vegetation / weed` ayrımında gerçek bir
coverage boşluğunu hedeflediğini gösterdi. Bununla birlikte veri kalitesi ile
model katkısı ayrı kapılardır.

### Eşit-bütçeli ikame ekranı

Seed 17'deki dondurulmuş sonuçlar:

| Tarif | Source | CWFID | Sorghum | CropAndWeed | Robust min | Robust Δ |
|---|---:|---:|---:|---:|---:|---:|
| Kabul edilmiş v3 kontrol | 0,801456 | 0,604038 | 0,816028 | 0,694439 | 0,604038 | — |
| CropAndWeed %10 ikame | 0,799432 | 0,553706 | 0,825023 | 0,721539 | 0,553706 | -0,050332 |
| CropAndWeed %20 ikame | 0,800763 | 0,569590 | 0,813901 | 0,715694 | 0,569590 | -0,034447 |

Her iki aday da CropAndWeed kazanım eşiğini geçti (`+0,027100` ve
`+0,021255`), source ve Sorghum non-inferiority kapılarında kaldı. Fakat
CWFID gerilemeleri `-0,050332 / -0,034447` oldu; bu nedenle primary robust ve
CWFID kapılarını geçemediler. Üç-seed confirmation açılmadı.

Kanonik seçim makbuzu:
`data/runs/real_data_cropandweed_screen_selection_v1.json`.

### Replay-preserving additive takip

İkame etkisini sınamak için ikinci protokol ilk ekran bittikten sonra, yeni
eğitimler başlamadan donduruldu. Additive tarif, kabul edilmiş 3.600
örnek/epoch tarifindeki her eski kaynağın mutlak draw sayısını koruyup 400
CropAndWeed draw ekledi. Salt ek hesap etkisini ayırmak için aynı 4.000
örnek/epoch bütçeli, CropAndWeed görmeyen kontrol de eğitildi.

| Tarif | Source | CWFID | Sorghum | CropAndWeed | Robust min | Robust Δ vs v3 |
|---|---:|---:|---:|---:|---:|---:|
| Kabul edilmiş v3 kontrol | 0,801456 | 0,604038 | 0,816028 | 0,694439 | 0,604038 | — |
| 4.000-example compute kontrol | 0,799782 | 0,578456 | 0,823817 | 0,715862 | 0,578456 | -0,025582 |
| Replay + %10 CropAndWeed | 0,805025 | 0,544732 | 0,824622 | 0,705481 | 0,544732 | -0,059306 |

Compute kontrolün CropAndWeed zero-shot kazanımı `+0,021423` oldu. Additive
kol ise v3'e karşı yalnız `+0,011042`, compute kontrole karşı `-0,010381`
aldı. Bu, tek-seed yeni-domain artışının tamamını CropAndWeed verisine
atfetmenin hatalı olacağını gösterir. Additive kol CWFID'de v3'e karşı
`-0,059306`, compute kontrole karşı `-0,033724` geriledi ve reddedildi.

Kanonik freeze ve seçim makbuzları:

- `data/runs/real_data_cropandweed_additive_protocol_freeze_v1.json`
- `data/runs/real_data_cropandweed_additive_screen_selection_v1.json`
- `data/runs/real_data_cropandweed_final_selection_v1.json`

Sonuç: CropAndWeed indirme, ontoloji, split, sızıntı ve görsel kalite
kapılarını geçen değerli bir research-only veri kaynağıdır; fakat test
edilen üç karışımda robust model kapısını geçmedi. Kabul edilmiş v3
kontrol korunur. Kilitli testler ve safety selector tarafından okunmadı; bu
sonuç saha/püskürtme onayı değildir.

Bir sonraki gerçek-veri önceliği daha fazla aynı-Avusturya karışım ayarı
aramak değil, CWFID benzeri yakın-saha sıra/geometriyi ve Avrupa dışı
koşulları kapsayan, lisansı net, oturum/saha-ayrık maskeli bir kaynaktır.
RiceSEG bu kapsama aday olsa da erişimi gated ve lisans sunumu uzlaştırma
gerektirir; kullanıcı adına erişim koşulu kabul edilmedi.
