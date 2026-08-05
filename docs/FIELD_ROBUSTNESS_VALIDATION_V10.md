# Tarla bağımsızlığı, hedef-ağırlıklı ölçüm ve V10 sentetik stres hattı

Tarih: 2026-08-04

## Karar özeti

Bu aşama veri kalitesini ve ölçüm kontratını belirgin biçimde iyileştirdi,
fakat gerçek-saha doğrulamasının doygunluğa ulaştığını göstermez.

- Gerçek model seçimi yalnız gerçek development/validation verisinden yapılır.
- Sentetik train kullanılabilir; sentetik val/test yalnız robustness tanısıdır
  ve gerçek seçim skorundaki ağırlığı tam `0.0`'dır.
- Büyük datasetlerin görüntü/piksel sayısıyla skoru ele geçirmesi engellendi:
  önce field/session macro, sonra dataset/domain macro alınır.
- Hedefe yakın domainler skorda `%60`, genişlik domainleri `%25`, tüm gerçek
  field/session birimlerinin alt `%25` kuyruğu `%15` ağırlıktadır.
- Mevcut global fallback hâlâ
  `simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8`, seed 43,
  SHA-256 `b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f`'dir.
  Yeni V10 veri kalite gate'i tek başına checkpoint değiştirmez.

## Gerçek validation durumu

Mevcut source validation session-ayrık ve çok-datasetlidir; buna rağmen altı
field'ın dördü eğitimde de temsil edilir. CWFID, Sorghum, CropAndWeed, erken
rice, GrowingSoy, WeedMap, Tobacco, DeBlur ve RiceSEG calibration/transfer
panelleri önemli dağılım kaymaları ekler; fakat çoğu artık tüketilmiş
development/calibration verisidir. Bu nedenle:

1. araştırma tariflerini karşılaştırmak için güçlü bir development panelidir;
2. yeni bir tarla/saha deployment iddiası için bağımsız final holdout değildir;
3. bu çalışma sırasında bulunan yeni Sugar Beets 2016 paneli eğitimle
   field/session çakışmayan gerçek robot-camera holdout açığını kapatır;
4. fakat panel tek tarla/tarih/oturumdur ve tek başına deployment kanıtı
   değildir.

Eski strict v2 kontratı tarihsel olarak korunur. Yeni holdout release'i
model çıktısı görülmeden dondurulduktan sonra onun yerine üç-seed strict v3
kontratı oluşturuldu:

- `configs/benchmark/target_weighted_field_robustness_v2.yaml`
- `configs/benchmark/target_weighted_field_robustness_v3.yaml`
- `scripts/score_target_weighted_field_benchmark.py`

V10 için tek-seed yön eleme kontratı aynı ağırlıkları korur ama mevcut source
field overlap'ini açıkça ilan eder; yalnız üç-seed confirmation açabilir,
model değiştiremez:

- `configs/benchmark/target_weighted_field_robustness_prescreen_v10_r2.yaml`

Her gerçek dataset eşit oy alır. Bir datasetteki binlerce benzer karo, az
örnekli ama hedefe yakın başka bir tarlayı bastıramaz. Herhangi bir field'da
`-0,025`, hedef domain ortalamasında `-0,010`, breadth domaininde `-0,015`
üzerinde regresyon hard-fail'dir.

## V10 asset paketi

Paket:

`data/raw/synthetic_assets/cropcraft_field_robustness_v10_r1`

`PACK.json` SHA-256:

`a943d03c0dd3e2487fe3edd1aac45e42839d59c775688de487a8bdb00368efde`

Toplam inventory: `441.718.675` bayt. Veri HDD'dedir; üretim öncesi HDD'de
yaklaşık `276 GiB` boşluk doğrulandı. Root filesystem'e büyük veri yazılmadı.

Paket dryland V3 botaniğini ve paddy R5 kapsamını korur. Altı mevcut + sekiz
yeni olmak üzere 14 CC0 Poly Haven toprak ailesi ve aynı şekilde 14 HDRI
ailesi train/val/test arasında asset-disjoint dağıtıldı:

- train: 10 soil + 10 HDRI;
- synthetic-val: 2 soil + 2 HDRI;
- synthetic-test: 2 soil + 2 HDRI.

Yeni surface/light profili şunları randomize eder:

- soil moisture ile albedo/roughness;
- flat, paralel sürüm, çapraz sürüm ve wheel-track benzeri makro normal;
- tillage yönü, ölçeği ve şiddeti;
- clod makro normal ayrıntısı;
- environment gücü ve dönüşü;
- ayrı sun energy/elevation/azimuth/angular size;
- kamera takipli robot area-light, boyut ve renk sıcaklığı;
- lokal, kamerada görünmeyen ama gölge atan occluder'lar;
- opsiyonel sığ su, roughness ve dalga parametreleri.

Önemli sınır: tillage/clod ayrıntısı shader-normal tabanlıdır; ölçülmüş fiziksel
displacement geometrisi değildir. Yağmur, rüzgâr, yaprak ıslaklığı ve hastalık
fiziği modellenmez.

## 72-kare split-aware pilot

Release:

`data/synthetic/cropcraft/field_robustness_pilot_v10_r1`

Manifest:

`data/processed/manifests/cropcraft_field_robustness_pilot_v10_r1.csv`

Manifest SHA-256:

`a9da5ccfa05b730436bd0fe30394a6abd37cf9319b3247f5e63eeec169aaf1ec`

Dağılım:

| Rol | Scene | Kare | Kullanım |
|---|---:|---:|---|
| train | 24 | 48 | küçük nedensel challenger screen'i |
| synthetic-val | 6 | 12 | asset-disjoint stres tanısı |
| synthetic-test | 6 | 12 | asset-disjoint stres tanısı |

Seed aralıkları sırasıyla `310000..310023`, `410000..410005` ve
`510000..510005`'tir. Cross-role RGB/mask exact duplicate, seed, soil ve HDRI
örtüşmesi sıfırdır. Train 10/10 soil ve 10/10 HDRI ailesini, 45 crop model
varyantını kullandı. Ölçülen train parametre açıklıkları örneğin:

- soil moisture: `0,894030`;
- tillage mode: `2,877260`;
- environment strength: `0,841699`;
- sun energy: `1,210201`;
- local shadow fraction: `0,464325`;
- artificial-light energy: `143,476271`.

48 train karesinin biri yalnız weed/background içeren yararlı hard-negative
görüntüdür. Bu oran `%2,083` ile dondurulmuş `%2,5` üst sınırının altındadır.
İlk `crop-free=0` kapısı bunu reddetti; kare tek tek incelendikten sonra sahne
hatası olmadığı kanıtlandı ve reddedilen release kanıt olarak saklandı.

Tüm 72 karede RGB/mask shape, palette ve radyometri tarandı. En yüksek
all-channel `>=250` oranları train/val/test için sırasıyla `%0,0538`,
`%0,0969`, `%0,0000`'dır; tümü `%0,2` hard limitinin altındadır. Görsel karar:

`data/synthetic/cropcraft/field_robustness_pilot_v10_r1/visual_review_receipt.json`

Conversion kararı:

`data/processed/manifests/cropcraft_field_robustness_pilot_v10_r1_conversion.json`

Model A/B manifestine yalnız 48 `train` satırı girer. Synthetic-val/test
satırlarının source validation'a girmediği hash-kilitli olarak doğrulandı:

`data/processed/manifests/real_sorghum_cropcraft_v3_025_fieldrobust025_paddy05_trainval_v10_r1_receipt.json`

## Lisanslı unseen robot sekansı

Ordinary YouTube içeriği yerine açık lisansı ve kamera platformu doğrulanabilen
resmî Sugar Beets 2016 BoniRob dizisi seçildi:

- resmî sayfa: <https://www.ipb.uni-bonn.de/data/sugarbeets2016/index.html>
- lisans: CC BY-SA 4.0;
- platform: BoniRob field robot;
- kullanılan akış: `camera/jai/rgb`;
- 31 RGB kare, `1296x966`, gerçek zaman damgalarıyla yaklaşık `0,999973 fps`;
- kaynak arşiv SHA-256:
  `d68a78f0a5dbaba6a78889a205df021394a613f809324339116390ec6566561f`.

Kaynak MP4 gerçek 1 Hz örneklemeyi korur; yapay temporal interpolation yoktur:

`data/raw/unseen_video/sugarbeets2016_bonirob_2016_05_23_11_36_43_4/derived_jai_rgb/bonirob_jai_rgb_1fps.mp4`

Kabul edilmiş global fallback, `target_crop_id=0 / Beta vulgaris` ile 31
karenin tamamında çalıştırıldı. Kaynak training manifestine karşı path/exact
byte duplicate yoktur. Sonuç özeti:

| Etiketsiz tanı | 31-kare ortalama |
|---|---:|
| semantic target-crop alanı | `%1,1660` |
| semantic other-vegetation alanı | `%0,6401` |
| source-frozen unknown alanı | `%0,7352` |
| source-frozen safe-weed alanı | `%0,0429` |
| mean confidence | `0,989062` |
| mean normalized entropy | `0,025989` |

Görsel olarak toprak/bitki sınırları temiz ve geniş yapraklı bitkiler ağırlıkla
crop'tur. İnce/çimsi bitkilerde crop-other karışması ve unknown görülür. Kareler
etiketsiz olduğu için bu gözlem doğruluk değildir; mIoU, crop IoU veya weed IoU
raporlanmadı. Robot hareketi nedeniyle registration olmadan ardışık-mask IoU da
flicker metriği sayılmadı.

Audit:

- `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/unseen_sequence_evaluation.json`
- `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/manual_visual_review.json`

Bu 31-kare 11:36 dizisi etiketsiz tanı olarak kalır. Sayısal holdout için aynı
resmî kaynağın ayrı 10:37 oturumundaki publisher anotasyonları kullanıldı;
iki rol birbiriyle karıştırılmaz.

## Yeni resmî anotasyonlu robot-camera holdout

Resmî `annotations/multiclass/annotations.zip` içindeki 283 ground-truth
maske ile bunların eşleştiği
`bonirob_2016-05-23-10-37-10_0.zip` tam olarak indirildi. Kaynak yayın siyahı
bitki-dışı, kırmızıyı sugar beet, diğer renkleri farklı weed türleri olarak
tanımlar. Ortak dönüşüm bu nedenle:

- black → background `0`;
- red → target crop `1`;
- diğer 16 kilitli publisher rengi → other vegetation `2`;
- beklenmeyen renk → fail-closed; üretilen ignore pikseli `0`.

Tam RGB arşivi `1.689.110.596` bayt, SHA-256
`1ec5786606a4fdf1f21363930913b852aa59ae8f82ae2ad0ee3b7ea9e7fb4cb3`;
anotasyon arşivi SHA-256
`b8729d1bb4c79e38d1b583e0b3488c1bce796d032e7bc07ea328ec1c2f9378e7`'dir.
16.479 ZIP üyesinin tam CRC'si, safe-path, 283/283 pairing, `1296x966`
decode ve 18-renk exact palette kapıları geçti. Ortak piksel dağılımı:

| Sınıf | Piksel | Oran |
|---|---:|---:|
| background | 332.745.564 | `%93,9169` |
| target crop | 14.623.075 | `%4,1273` |
| other vegetation | 6.929.249 | `%1,9558` |
| ignore | 0 | `%0,0000` |

12 önceden seçilmiş RGB/overlay çiftinde bariz kayma, sınıf tersliği veya
boş/bozuk maske görülmedi. Bu inceleme coding-agent görsel kontrolüdür; insan
agronomist tür auditi değildir. Training manifestine karşı 283×5.951 exact
SHA/dHash-256 Hamming≤2 eşleşme `0`, en yakın Hamming `77`; önceki 20.765
gerçek kaydın tamamına karşı da eşleşme `0`, en yakın Hamming `72`'dir.

Manifest:

`data/processed/manifests/sugarbeets2016_multiclass_holdout_v1.csv`

Release receipt:

`data/processed/audits/sugarbeets2016_multiclass_holdout_v1_manual_visual_review.json`

283 ardışık kare 283 bağımsız oy değildir. Tüm panel
`cka_sugarbeet_field_2016 / bonirob_2016-05-23-10-37-10_0` adıyla tek
field/session birimine indirgenir, sonra target-like dataset makrosuna yalnız
bir oy verir. Eğitim kullanımı kapalıdır. Bu panel semantic model replacement
karşılaştırmasını güçlendirir; coğrafi/seasonal genelleme veya spray safety
kanıtı değildir.

## V10 model ekranı

Nedensel seed-17 ekranında gerçek veri `%90`, toplam sentetik `%10` kalır:

- kabul edilmiş kontrol: dryland V3 `%5` + paddy R5 `%5`;
- challenger: dryland V3 `%2,5` + field-robust V10 `%2,5` + paddy R5 `%5`.

Güncel config:

`configs/benchmark/simulation_field_robustness_screen_v10_r2.yaml`

İlk iki deneme ortak GPU'daki ayrı Ollama sürecinin yaklaşık `19–20 GiB`
VRAM tutması nedeniyle fail-closed kesildi; yarım artefaktlar kabul edilmedi.
GPU boşken aynı dondurulmuş R2 config'i tamamlandı. V10 birleşik gerçek
seçim skorunu `+0,006884`, target-like makroyu `+0,003331`, breadth makroyu
`+0,014153` ve alt-kuyruğu `+0,008981` yükseltti. Buna karşın CWFID
`-0,048846`, mevcut gerçek çekirdek `-0,029437` ve en kötü field/session
`-0,311180` geriledi. 111 alanın 21'i hard field kapısını kaybetti.
Dolayısıyla paired non-inferiority geçmedi ve `accepted=false` oldu;
seed 29/43 açılmadı.

Ardından fiziksel olarak korelasyonlu hava/yüzey/ışık profilleri ve V3'e
daha yakın kompozisyonla V11 takip deneyi yapıldı. R1 kalite kapısında,
tam R2 ise iki train radyometri outlier'ı nedeniyle reddedildi. Yalnız bu
iki kareyi nesnel olarak karantinaya alan 78/16/16 karelik R2Q türevi model
ekranına girdi. V11-R2Q gerçek seçim skorunu `-0,010073`, target-like
makroyu `-0,015962` düşürdü; 111 alanın 30'u hard kapıyı kaybetti.
Bu aday da reddedildi ve dondurulmuş stop kuralı gereği yeni model-güdümlü
asset iterasyonu açılmadı.

Tam V10/V11 gate defteri, domain tablosu ve hashler:

`docs/FIELD_ROBUSTNESS_VALIDATION_V11.md`

## En yüksek değerli kalan işler

1. Farklı ülke/tarla, toprak, hava, gün ve kamera yüksekliğini kapsayan ikinci
   bir gerçek robot-camera holdout; mevcut 283 kare tek oturumdur.
2. Sugar Beets sınıf dönüşümünün bağımsız insan/agronomist spot-check'i.
3. Farklı tarla, toprak, hava, gün ve kamera yüksekliğini kapsayan yeni gerçek
   video/sequence; aynı yürüyüşün ardışık kareleri ayrı bağımsız örnek sayılmaz.
4. Yeni, bağımsız gerçek alan gelmeden V10/V11 sonucuna bakarak aynı
   prosedürel asset hattını yeniden ayarlamamak.
5. Strict v3 üç-seed kapısı geçmeden model replacement; ayrı safety ve yeni
   saha testleri geçmeden saha-ready iddiası yapılmamalıdır.
