# RiceSEG edinim, release ve kalite denetimi — v1

## Sonuç

RiceSEG başarıyla indirildi ve kalite kapısından geçti. Hugging Face release'i
commit `1a891ced931d5b3ac2a907b045f53414f1a615b4` üzerinde pinlidir. Altı
repository dosyasının toplamı `1.564.399.537` bayttır; iki arşivin de tam CRC,
safe-path ve symlink kontrolleri geçti.

```text
upstream RGB/mask pairs:                 3.078
quality-eligible pairs:                  3.077
coverage-training train:                 2.473
coverage-training external calibration:    604
country-transfer source:                 1.823
country-transfer target:                 1.254
quarantined same-train near duplicate:       1
external/final test created:                 0
```

Ham release veri diskinde yaklaşık `1,5 GiB`, türetilmiş görüntü/maske ağacı
yaklaşık `265 MiB` tutar. Veri diskinin denetim sonundaki boş alanı yaklaşık
`280 GiB`'dır. Proje kök diski doluluğa yakın olduğu için büyük artifact'ler
`data` symlink'inin hedefi olan veri diskinde tutulur.

## Release bütünlüğü

`RiceSEG.zip` içinde tam `3.078 RGB + 3.078 maske` eşleşti. Tüm rasterlar
decode edildi; release görüntüleri `512x512`, maskeler yalnız `0..5` değerleri
içeriyor ve XLSX sınıf sayımları decoded maskelerle birebir uyuşuyor. On dokuz
subdataset'in sayımları da publisher metadata'sıyla eşleşti.

`original.zip`, 416 yüksek çözünürlüklü parent görüntüden oluşan kısmi bir
provenance arşividir; 3.078 eğitim karesinin tamamının parent karşılığı olduğu
varsayılmadı. Eğitim release'i `RiceSEG.zip` içindeki eşlenmiş 512x512 ağaçtır.

Kaynak kapsamı:

```text
countries:     5  (China, India, Japan, Philippines, Tanzania)
institutes:   12
subdatasets:  19
platforms:     4
sensors:       9
years:        13  (2012–2024)
```

Growth-stage üyelikleri publisher metadata'sında birbirini dışlamaz:
vegetative `2.484`, transition `1.164`, reproductive `798`. Bunlar toplanarak
örnek sayısı üretilmemelidir.

## Ontoloji ve türetme

Altı sınıflı kaynak maskeleri byte olarak korunur; üç sınıflı common maskeler
ayrı derived ağaçta üretilir:

```text
0 background             -> common background (0)
1 green rice vegetation  -> common crop       (1)
2 senescent rice         -> common crop       (1)
3 rice panicle           -> common crop       (1)
4 weed                   -> common weed       (2)
5 duckweed               -> common weed       (2)
```

RGB yeniden encode edilmedi. Kaynak maske ağacı, derived common maske ağacı
ve manifest hash'leri conversion receipt'inde ayrı tutulur.

Lisans sunumu fail-closed'dur: Hugging Face kartı MIT gösterirken yayın
sunumunda farklı lisans ifadesi bulunur. Bu çelişki hukuken uzlaştırılmadan
`commercial_allowed=false` korunur; mevcut kullanım araştırma benchmarkıdır.

## Split ve kalite kararı

Coverage protokolü model sonucu görülmeden subdataset bazında donduruldu.
`GD` (100 kare) ve `TKO_2` (504 kare) yalnız external calibration'dır; diğer
gruplar train adayıdır. Random görüntü split'i yapılmadı.

İçerik denetimi, `JS_1` ve `JS_2` train gruplarında dHash-256 Hamming `0`
olan fakat maskeleri `15.819` pikselde farklı tek bir yakın-kopya çifti buldu.
Kaynak dosyalar silinmedi veya değiştirilmedi. Leksikografik olarak ilk örnek
train'de tutuldu, ikinci örnek karantina manifestine taşındı. Böylece nihai
coverage `2.473 train / 604 external_calibration` ve `3.077` eligible örnektir.

Alternatif country-transfer protokolü kalite sonrası `1.823` China+Japan
source ve `1.254` India+Tanzania+Philippines target içerir. Bu manifest
coverage-training manifestiyle birleştirilemez. Target ülkeler training'e
girdikten sonra eski sonuç zero-shot diye sunulamaz.

## Geçilen kapılar

- 6/6 pinli repository dosyası, boyut ve SHA-256 doğrulaması;
- iki ZIP için full CRC, unsafe path `0`, symlink `0`;
- 3.078/3.078 RGB-mask canonical pairing ve tam raster decode;
- `512x512`, yalnız `0..5`, tüm altı sınıf ve global piksel sayımı;
- 19/19 subdataset ve iki XLSX metadata doğrulaması;
- 19 subdataset x 5 deterministik örnek = 95 hücre manuel RGB/source/common
  maske ve overlay incelemesi;
- 17.688 önceki gerçek kayda karşı exact/dHash<=2 eşleşme `0`;
- train-calibration cross-split exact/dHash<=2 eşleşme `0`;
- tek same-train çatışmalı yakın kopyanın fail-closed karantinaya alınması.

## Kanonik artifact'ler

```text
quality manifest
data/processed/manifests/riceseg_quality_v1.csv
SHA-256 f3bcfedf4d56da5ba43f7b79d06f511a17645a1e26ad33bac9656da34d52dc5c

quality train manifest
data/processed/manifests/riceseg_quality_train_v1.csv
SHA-256 bf2c81e0cb4a10c92877e489b60b10655edd481f3c2e67627a93c24f37489208

quality calibration manifest
data/processed/manifests/riceseg_quality_calibration_v1.csv
SHA-256 39fcce0ee2f886346ed36b93d4af2008a06bb9cc9628297926222ce5bd77d14b

quality gate receipt
data/processed/audits/riceseg_quality_gate_v1.json
SHA-256 1653ebfed22e9b8920b88ddbb3460a8648729b0934f63018077d78e2b8ed4904

release inspection receipt
data/processed/audits/riceseg_release_inspection_v1.json
SHA-256 1cf8bc05a379bff77a3a82d2112df676ff1970e2d9569c54642763559a562564

conversion receipt
data/processed/audits/riceseg_conversion_v1.json
SHA-256 23fd67404ae6abcc0162fdbb1a0f50e154f5b8474be727f6e3810cec93d8489e

duplicate audit
data/processed/audits/riceseg_duplicate_audit_v1.json
SHA-256 b7e773ac961db79c0b99755d4078185b38d78b88eefb8d42d3aa65d781d56e78

manual visual review
data/processed/audits/riceseg_visual_review_v1.json
SHA-256 3930c4dc67ec7196791b8d8cb6e343db16a43620c3748111ab28a4dff026066d
```

## Tekrar çalıştırma

Yerel Hugging Face oturumu artık geçerlidir. `git credential helper` uyarısı
dataset indirmeyi etkilemez; yalnız Git üzerinden Hub'a push credential'ını
ilgilendirir. Yeniden oturum gerekirse güncel komut:

```bash
.venv/bin/hf auth login
```

Doğrulama/üretim sırası:

```bash
.venv/bin/python scripts/acquire_riceseg.py
.venv/bin/python scripts/inspect_riceseg_release.py
.venv/bin/python scripts/convert_riceseg.py
.venv/bin/python scripts/build_riceseg_contact_sheet.py
.venv/bin/python scripts/finalize_riceseg_quality_gate.py
```

Token proje dosyasına, config'e veya makbuza yazılmaz.

## Model açısından mevcut durum

Kabul edilmiş kontrol, hiç gerçek RiceSEG train exposure almadan tüm RiceSEG
calibration'da mIoU `0,290154`, saf reproductive 100-kare altkümede mIoU
`0,032876` aldı. Sonraki iki additive ve bir sabit-compute exact-index
replacement seed-17 ekranında RiceSEG/reproductive yaklaşık `+0,32 / +0,37`
arttı. Buna karşın her global tarif en az bir mevcut-domain kapısını kaybetti.
En kontrollü exact-index kol CWFID'i `-0,006124` ile korudu; source/Sorghum/
CropAndWeed `-0,012139 / -0,023556 / -0,025475` geriledi. Aday reddedildi,
seed 29/43 açılmadı ve kabul edilmiş model değişmedi. Veri model faydasını
kuvvetle gösterir, ancak global mixture tarifini kanıtlamaz; ayrıntılar
`docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md` içindedir.
