# Gerçek veri coverage matrisi — v1

## Sonuç

On hash-kilitli manifestten 18 kalite-kapılı veri kümesi ve 20.765 kayıt
tek bir provenance matrisinde doğrulandı. Bu audit görüntü piksellerini,
external test'i veya model çıktısını okumadı.

```text
accepted real records:                 20.765
datasets:                                   18
capture groups:                            575
dataset-qualified fields:                  57
common-semantic-compatible records:     18.710
partial-training-locked records:          2.055
partial train candidates:                 1.710
partial external calibration:               345
commercial-allowed records:               9.072
research-only records:                   11.693
```

Kanonik makbuz:

```text
data/processed/audits/real_data_coverage_matrix_v1.json
SHA-256 43ad9f0c10a32a3a1d7a001b4fcac09ee6a2c512016ce379f1e3b77b97d500d8
```

Manifestte `train` yazan 14.417 satırın 1.710'u fail-closed partial track'tir
ve mevcut ortak loss'a açık değildir. Gerçek ortak-semantik train envanteri
bu nedenle 12.707 satırdır; sayı büyütülerek 14.417 diye raporlanmamalıdır.

## Veri kümesi matrisi

`T/C/V/E` sırasıyla train / external-calibration / val / test+external-test
satırlarını gösterir.

| Veri | Kayıt | T/C/V/E | Grup | Supervision | Ana coverage | Güncel karar |
|---|---:|---:|---:|---|---|---|
| ACRE | 1.000 | 600/0/200/200 | 10 | dense common | ground robot, maize+bean | core |
| CamelinaWeed | 1.097 | 999/98/0/0 | 7 | positive-only partial | UAV, Camelina field, 2 region/season/platform | training locked |
| Carrot-Weed | 39 | 0/0/0/39 | 1 | dense common | early carrot ground stress | consumed external test |
| CropAndWeed | 4.584 | 3.667/917/0/0 | 437 | dense fail-closed | top-down, 9 accepted crop IDs | research candidate; additive model gate failed |
| CWFID | 60 | 0/60/0/0 | 1 | dense fail-closed | canonical early carrot field | calibration only |
| DeBlurWeedSeg | 200 | 0/200/0/0 | 1 | dense common | paired sharp/real motion blur, sorghum | diagnostic only |
| EWIS1 | 88 | 0/0/0/88 | 39 | dense common | UAV maize/sorghum fields | consumed external test |
| GrowingSoy | 1.000 | 541/459/0/0 | 2 | dense fail-closed | six time points/two trajectories | candidate; global model gate failed |
| PhenoBench | 2.179 | 1.407/0/772/0 | 6 | dense common | high-res UAV sugar beet | core, non-commercial |
| Rice Seedling & Weed | 224 | 224/0/0/0 | 1 | partial three-class | early transplanted paddy | training locked |
| RiceSEG | 3.077 | 2.473/604/0/0 | 18 | dense fail-closed | 19 subdataset, çok-ülkeli/tam-döngü paddy | veri accepted; global mix failed; crop-routed specialist 3-seed accepted |
| ROSE | 1.235 | 735/0/250/250 | 10 | dense common | multiple robots/years, maize+bean | research core |
| SorghumWeed | 252 | 202/25/0/25 | 3 | dense common | DSLR sorghum field | train+development; external test consumed |
| Tobacco Aerial | 2.520 | 1.536/984/0/0 | 8 | dense common | low UAV, eight campaigns | candidate; global model gate failed |
| WE3DS | 1.801 | 1.018/0/389/394 | 19 | dense common | trolley RGB, seven crops/growth dates | core |
| WeedMap | 519 | 424/95/0/0 | 5 | dense fail-closed | UAV sugar beet orthomosaic | candidate; global model gate failed |
| WeedsGalore | 156 | 104/0/26/26 | 3 | dense common | multispectral maize dates | core |
| Weedy Rice UAV | 734 | 487/247/0/0 | 4 | positive-only partial | mature rice, four UAV flights/two locations | training locked |

“Dense fail-closed”, kabul edilen piksellerin ortak sınıflarla uyumlu olduğu
ama release'in bazı pikselleri veya kayıtları `ignore` tutmayı gerektirdiği
anlamına gelir. “Partial” ise daha güçlü bir sınırdır: unlabeled pikselin
negatif olduğu varsayılamaz ve mevcut ortak cross-entropy eğitimine veri
eklenemez.

## Split ve lisans görünümü

Global manifest rol sayıları:

```text
train:                14.417
external_calibration:  3.689
val:                   1.637
test:                    870
external_test:           152
```

Bu sayılar yeni bir random split önerisi değildir. Her veri kümesinin kendi
field/session/flight/map/campaign grupları korunur. `575 capture group`, 575
bağımsız tarla demek değildir: CropAndWeed oturumları, Tobacco kampanyaları,
WeedMap karoları ve video trajectory'leri aynı saha içinde korelasyon taşır.

9.072 kayıt commercial-allowed görünürken 11.693 kayıt non-commercial veya
embedded-content inceleme sınırlamasındadır. Dolayısıyla araştırma benchmark
skoru ile ticari eğitim corpus'u aynı envanter değildir. Ticari ürün adayı
için yalnız `commercial_allowed=true` filtreli ayrı gate korunmalıdır.

## En kritik gerçek-veri açıkları

### 1. Full-semantic rice edinildi; global karışım reddedildi

Eski rice coverage iki partial kaynaktan ibaretti:

- Rice Seedling & Weed: 224 karo, yalnız 28 erken-dönem ana fotoğraf;
- Weedy Rice UAV: 734 görüntü, mature rice/weedy-rice positive mask fakat
  cultivated rice/background ayrımı yok.

Bu ikisi gerçek paddy görünümü sağlar ama ortak üç sınıfı exhaustive öğretmez.
[RiceSEG](https://huggingface.co/datasets/PheniX-Lab/RiceSEG) artık edinildi:
3.078 release çiftinden bir çatışmalı same-train yakın kopya karantinaya
alındı; 2.473 train ve 604 subdataset-ayrık calibration karesi ortak-semantik
uyumludur. Kabul edilmiş kontrolün RiceSEG/saf-reproductive mIoU'su
`0,290154 / 0,032876` idi. İki additive ve bir sabit-compute exact-index
seed-17 ekranı hedefi yaklaşık `+0,32 / +0,37` iyileştirdi; buna karşın
her tarif mevcut-domain non-inferiority kapısında kaldı. En kontrollü kol
CWFID'i korurken source/Sorghum/CropAndWeed `-0,012139 / -0,023556 /
-0,025475` geriledi. Veri rice specialist/adapter için kabul edildi, global
sampler için reddedildi. Ayrı parametreli metadata-routed specialist daha
sonra `%2,38095` exposure ile seed 17/29/43'te 3/3 rice-target robust galibiyet
ve ortalama `+0,382517` robust farkı sağladı; non-rice/unknown girdiler aynı
global fallback'e gitti.

### 2. Bağımsız coğrafya sayısı örnek sayısından zayıf

20.765 kayıt geniş görünür fakat birçok büyük kaynak tek araştırma sahası,
tek kampanya veya korelasyonlu tile/video dizisidir. Robust model için yeni
bir tek-saha 1.000 kare, farklı ülke/kurum/sensör/gelişim evresi içeren daha
küçük ama grup-ayrık bir setten daha düşük marjinal değere sahiptir.

### 3. Gerçek motion/ışık/hava coverage sınırlı

Gerçek motion-blur kanıtı yalnız DeBlurWeedSeg'in tek sorghum sahasındaki 100
sharp + 100 blur crop'udur. Manifest metadata'sı yağmur, gece, yoğun gölge,
farklı shutter/exposure ve lens kirlenmesini sistematik, bağımsız strata
olarak kanıtlamaz. Sentetik motion asset'i kalite gate'ini geçti fakat global
model non-inferiority kapılarını geçemedi; bu açık “daha çok blur üret” ile
tek başına çözülmedi.

### 4. Partial specialist verisi kaliteli ama objective eksik

CamelinaWeed'in 1.097 ve Weedy Rice'ın 734 karesi toplam 1.831 güçlü UAV
positive-only örnek sağlar. Bunun 1.486'sı train adayı, 345'i konum/uçuş
ayrık calibration'dır. Ancak unlabeled alanı negatif sayan standart loss,
ürünü ve etiketsiz yabani otları yanlış bastırır. Önce partial-label loss,
sampling, replay ve mevcut-domain non-inferiority kuralları model çıktısı
görülmeden dondurulmalıdır.

## Aday sırası

1. **Yeni dense çok-saha coverage:** BAWSeg'in resmî 7.5 GB IEEE DataPort
   artifact'i/content-ID'si artık görünür ve disk ön-kontrolü geçti. Abonelik
   oturumu sağlandığında arşivi yalnız fail-closed merkez-dizin/CRC/iç-SHA/
   lisans kapısıyla al; bu kapılar geçmeden matrise ekleme.
2. **CWD30-S:** resmi semantic release `Coming Soon` durumundan çıkmadan alma.
3. **Rice/partial specialist:** Kabul edilen RiceSEG specialist'i yalnız kesin
   `crop_id=12 / Oryza sativa` metadata route'uyla kullan. Camelina ve Weedy
   Rice'ı ayrı positive-only objective protokolüyle değerlendir; ortak
   sampler'a sessizce ekleme.
4. **Yeni gerçek veri araması:** yalnız yeni coğrafya, sensör, büyüme evresi
   veya ölçülmüş koşul açığı ekliyorsa indir. Tek orthomosaic/random tile
   tekrarlarına öncelik verme.

## Sentetik veri için ölçülebilir backlog

Mevcut dryland V3 ve paddy R5 botanik/zemin paketleri asset ve model gate'ini
geçen en güçlü tabandır. Soy V6 ve motion V7 asset'leri görsel/statik gate'i
geçse de global sampler model kapısını geçmedi. RiceSEG ile seçilen
late-reproductive R3 paketi de asset/pilot kapısını geçti; `%2,5` kol hedef
RiceSEG'i kuvvetle iyileştirirken CWFID/CropAndWeed non-inferiority'yi kaybetti.
Gerçek RiceSEG de artık üç global tarifte ölçüldü ve aynı tip domain
çatışmasını gösterdi. Ayrı metadata-routed gerçek-RiceSEG specialist
seed `17/29/43`'te kabul edildi; kazanan mevcut dryland V3 + paddy R5 tabanını
kullandı ve reproductive R3 ile eğitilmedi. Bu nedenle bir sonraki sentetik
tur yeni oran/mesh aramaz: geometry/texture kalite kapısı model kapısından
ayrı tutulur, R3 yalnız ileride dondurulmuş yeni bir stress/ablation hipotezi
doğarsa kullanılır; mevcut kanıt büyük R3 batch'ini açmaz.

Şimdilik yeni rastgele sentetik batch üretmek veya daha fazla benzer mesh
eklemek kanıtla desteklenmez. Veri tarafında en yüksek marjinal değer yeni
coğrafya/sensör/koşul içeren dense çok-saha coverage; model tarafında ise
global mixture yerine parametre-izole specialist/adapter'dır.

## Provenance

- Dondurulmuş matris config'i:
  `configs/data/real_data_coverage_matrix_v1.yaml`, SHA-256
  `93b0c621fdf4f35f0fdaab8a100dc83c7d80a105697f12dad4ec47f0e0de8738`
- Audit aracı:
  `scripts/audit_real_data_coverage_matrix.py`, SHA-256
  `33549b724601b34d1686a9b2117e092f01414ce617a62a2601ae440c19d24f50`
- Camelina ayrıntılı kalite raporu:
  `docs/REAL_DATA_CAMELINAWEED_AUDIT_V1.md`
- Önceki erişilebilirlik taraması:
  `docs/REAL_DATA_COVERAGE_AUDIT_V3.md`
- RiceSEG edinim/split/release kalite denetimi:
  `docs/REAL_DATA_RICESEG_PREFLIGHT_V1.md`
- RiceSEG üç global-mixture model kapısı:
  `docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md`
- RiceSEG metadata-routed specialist doz/confirmation kapısı:
  `docs/REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`
- Reproductive-rice R3 asset ve model kapısı:
  `docs/SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md`
- BAWSeg resmî artifact/kamu/disk ön-kontrolü:
  `docs/REAL_DATA_BAWSEG_PREFLIGHT_V1.md`

Audit sırasında pixel dosyası, external-test görüntüsü veya model çıktısı
okunmadı; checkpoint seçilmedi.
