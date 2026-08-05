# Reproductive rice sentetik asset kalite raporu — v9 R3

> **Takip notu (2026-08-03):** Ayrı parametreli gerçek-RiceSEG specialist,
> reproductive R3 eğitim girdisi olmadan seed 17/29/43'te kabul edildi. Bu,
> R3'ün asset-kalite kabulünü değiştirmez; fakat global/specialist büyük batch
> açmak için gerekçe oluşturmaz. Güncel model kararı
> [`REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`](REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md)
> içindedir.

## Karar

R3 paketi asset, smoke, pilot, görsel kalite, dağılım, manifest ve leakage
kapılarının tamamını geçti. Buna karşılık `%2,5` global sampler kolu seed 17
model non-inferiority kapısını geçmedi. Sonuç iki ayrı karardır:

```text
asset/pilot quality:                    PASS
equal-budget model benefit:             FAIL
large synthetic batch:             NOT OPENED
accepted global recipe changed:           NO
retained global control: paddy R5 + dryland V3
```

R3 specialist/stress-test girdisi olarak saklanır; mevcut global eğitime
otomatik eklenmez.

## Neden bu asset üretildi?

RiceSEG'in `3.077` kalite-kapılı karesi ile kabul edilmiş paddy R5 paketinin
coverage'ı model sonucu kullanılmadan karşılaştırıldı. R5'in 60 crop modeli
yalnız 15–25 günlük erken pirinci kapsıyor; açık panicle, grain veya senescent
fenotipi yok.

Sıfır explicit coverage taşıyan faktörler arasında kaynak piksel oranı en
yüksek olan açık seçildi:

| Faktör | RiceSEG kaynak piksel oranı | R5 explicit coverage | Karar |
|---|---:|---|---|
| late reproductive rice (class 2+3) | %5,862841 | yok | seçildi |
| duckweed carpet (class 5) | %0,827691 | yok | sonraki izole faktör; ertelendi |

Bu nedenle rastgele yeni botanik çeşit üretmek yerine yalnız late-reproductive
pirinç morfolojisi ve fenotipi hedeflendi.

## R1 → R2 → R3 iyileştirmesi

- **R1:** 48 model/24 geometriyle statik kapıyı geçti; smoke incelemesinde
  panicle'lar seyrek, açık renkli boncuk iskeleti ve radial starburst
  silueti verdi. Pilot üretilmeden reddedildi.
- **R2:** minimum grain sayısı `96 → 235`, branch sayısı `11 → 16` oldu ve
  radial starburst azaldı. Buna rağmen exposed bead skeleton ve ağırlıkla
  sarkan kümeli rice-panicle formu geçmedi. Pilot üretilmeden reddedildi.
- **R3:** minimum grain `310`, branch `18`; kompakt alternating branch,
  stage-conditioned gravity droop ve 512 px kamera mesafesinde görülebilen
  grain hedefleri eklendi. Smoke ve bounded pilot görsel kapısını geçti.

R3 nihai paket özeti:

```text
models / unique geometries:      48 / 24
growth stages: heading, flowering, grain_fill, mature
texture phenotypes: heading_green, grain_fill_transition, mature_senescent
faces per model:          11.994 – 29.550
minimum per model: 4 tiller, 22 leaf, 2 panicle, 18 branch, 310 grain
inventory:              406 files / 334.826.911 bytes
base-pack changed paths: 0
```

Üç 1254x1254 texture source'u bu proje için görüntü üretim aracıyla üretildi;
prompt ve SHA provenance'ı
`assets/source_textures/rice_reproductive_v9/PROMPTS.json` içinde korunur.
Bunlardan 1024x1024 seamless albedo ve normal map'ler türetildi; seam farkı
üç fenotipte de `0` ölçüldü. Üretilmiş texture'lar CC0 diye yeniden
etiketlenmedi. Auth gerektiren iki Sketchfab CC0 adayının yalnız metadata'sı
doğrulandı; byte'ları alınmadığı için paket veya lisans iddiasına katılmadı.

## 100 kare pilot

Pilot 80 train / 20 validation, scene-disjoint olarak üretildi ve 48 crop
varyantının tamamını kullandı. Dört growth stage ile üç fenotip; sparse/dense
ürün, wet-ground ve ortam varyasyonu iki rolde de görsel olarak görüldü.

```text
samples:                         100
mean crop fraction:         0,467304
mean weed fraction:         0,027669
crop-free / weed-free:          0 / 0
RGB class pixels:
  background               13.238.980
  crop                     12.250.106
  weed                        725.314
```

RiceSEG'in q05–q95 bandına karşı önceden dondurulmuş altı düşük-mertebe
metriğin 6/6'sı geçti: brightness mean/std, crop fraction, Laplacian variance,
saturation ve texture gradient. Bu test yalnız gross dağılım uyumunu ölçer;
botanik gerçekçilik veya model katkısı ispatı değildir.

Tüm 100 RGB/maske için makine kontrolleri, stage x role uçlarını kapsayan 16
kare için manuel review yapıldı. Crop semantiği yaprak, culm, panicle ve
grain'i içerdi; sistematik shift/swap/hole, boş veya ters maske gözlenmedi.

## Sızıntı ve manifest kapısı

Nihai manifestte 100/100 dosya mevcut, maskeler `0/1/2`, 80/20 scene-disjoint
ve manifest auditi temizdir. `20.765` kabul edilmiş gerçek kayda karşı
SHA-256 exact ve dHash-256 Hamming<=2 eşleşme `0`; aday içinde de eşleşme `0`.
En yakın gerçek görüntü dHash mesafesi `66`'dır.

## Eşit-bütçeli model ekranı

Kapılar model eğitilmeden önce donduruldu. Her iki kol aynı mimari/hyperparam,
seed 17, epoch 8 ve `28.800` sampled-example bütçesini kullandı:

- kontrol: `%90` gerçek + `%5` dryland V3 + `%5` early-paddy R5;
- aday: `%90` gerçek + `%5` dryland V3 + `%2,5` early-paddy R5 + `%2,5`
  reproductive R3.

Gerçek RiceSEG ve erken rice verileri iki kolda da yalnız development
değerlendirmesidir; eğitim exposure'ı `0`'dır. External/final test açılmadı.

| Development domain | Kontrol | R3 adayı | Delta | Gate |
|---|---:|---:|---:|---|
| source | 0,801428 | 0,811273 | +0,009844 | pass |
| CWFID | 0,638260 | 0,598731 | -0,039529 | **fail** |
| Sorghum | 0,819230 | 0,833609 | +0,014379 | pass |
| CropAndWeed | 0,697676 | 0,681650 | -0,016026 | **fail** |
| early rice | 0,384724 | 0,517093 | +0,132369 | pass |
| RiceSEG | 0,290154 | 0,431335 | +0,141180 | pass |
| RiceSEG reproductive | 0,032876 | 0,134739 | +0,101863 | pass |
| macro | 0,523478 | 0,572633 | +0,049154 | pass |
| robust minimum | 0,032876 | 0,134739 | +0,101863 | pass |

R3 hedef domaini çok güçlü iyileştirdi; fakat CWFID ve CropAndWeed için
önceden dondurulan azami `-0,01` regresyon sınırını aştı. Bu nedenle aday
reddedildi, seed 29/43 confirmation açılmadı ve kontrol korundu. Asset'in
kalitesiz olduğu sonucu çıkmaz; `%2,5` global ikamenin robust tarif olmadığı
sonucu çıkar.

## Sınırlar ve sonraki yetkili kullanım

- Prosedürel form ve generated texture botanik tarama değildir; branch düzeni
  tarla panicle'ından daha düzenlidir.
- Wind, disease, wet-leaf deformation, ölçülmüş kamera optiği ve motion blur bu
  izole faktörün dışındadır.
- Paket research-use/fail-closed'dur; commercial-use iddiası yoktur.
- Yeni büyük batch veya benzer mesh üretimi açılmamıştır.
- Gerçek RiceSEG katkısı iki additive ve bir exact-index fixed-compute kapıda
  ölçüldü: hedef kazanım çok büyük, global non-inferiority başarısız oldu.
  Bu nedenle R3 için yeni global doz araması veya benzer mesh üretimi açılmaz;
  paket yalnız crop-conditioned specialist/stress girdisi olarak korunur.

## Kanonik makbuzlar

```text
R3 static asset audit
data/processed/audits/cropcraft_reproductive_asset_quality_v9_r3.json
SHA-256 e16208f20ca004fa8f3d3b6902b5b2f43911ebeae56b76de28a166bfdd062054

R3 final asset/pilot gate
data/processed/audits/cropcraft_reproductive_final_gate_v9_r3.json
SHA-256 755931bf460dd5b50a254d8096ef6ea64a1ac858f2ef65b74c2c436fcdc9eec8

pilot manifest
data/processed/manifests/cropcraft_reproductive_pilot_v9_r3.csv
SHA-256 756bb57561551455546dd4db67b72a46447b31ff845d8efed2ba3ba8ecd7880d

pilot RiceSEG distribution audit
data/processed/audits/cropcraft_reproductive_riceseg_distribution_v9_r3_pilot.json
SHA-256 e342c6035ffc80be0003fa34c8ee00cac6e80762870bf0b0122a81aaaf7739ce

pilot manual review
data/processed/audits/cropcraft_reproductive_pilot_manual_visual_review_v9_r3.json
SHA-256 20685bd0623ecc542009c2abb74c289970fb0cd8489650e9f77fba6b31a67a00

duplicate audit
data/processed/audits/cropcraft_reproductive_duplicate_audit_v9_r3.json
SHA-256 0ba4dba65734dd01cf51a6df36fce31a0c58efa87ad2e03d7777238b24039d02

frozen model protocol
configs/benchmark/simulation_reproductive_asset_selection_protocol_v9_r3.yaml
SHA-256 90ef5e180f0fe053f14ce30a355831dc91d5888c2c5eba5399a73ba7acdd8c63

model selection receipt
data/processed/audits/cropcraft_reproductive_asset_screen_selection_v9_r3.json
SHA-256 70307274373b1701c61b6acf85dd963d9ad822ede3aa5845f8f88de446afc215
```
