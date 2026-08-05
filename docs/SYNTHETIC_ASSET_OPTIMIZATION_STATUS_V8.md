# Sentetik asset optimizasyon durumu — v8

> **Takip notu (2026-08-03):** Bu dosya immutable v8 portföy audit'ini
> anlatır. RiceSEG sonrası late-reproductive R1/R2 retleri, R3 kalite kabulü
> ve global model reddi
> [`SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md`](SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md)
> içinde tamamlandı. Gerçek RiceSEG'in üç global karışım ekranı da
> [`REAL_DATA_RICESEG_MODEL_GATE_V1.md`](REAL_DATA_RICESEG_MODEL_GATE_V1.md)
> içindedir. Ayrı metadata-routed gerçek-RiceSEG specialist daha sonra
> seed 17/29/43'te kabul edildi; kazanan, kabul edilmiş dryland V3 + paddy R5
> tabanını kullandı ve reproductive R3'le eğitilmedi. Karar
> [`REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`](REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md)
> içindedir. V8'deki “next gate” bölümü tarihsel gerekçedir; yeni benzer rice
> asset/global doz araması açık değildir.
>
> **Tarla-robustluk takibi (2026-08-04):** Daha sonra 14 soil/14 HDRI,
> nem/tillage/clod, doğal+robot ışığı, lokal gölge ve sığ su kapsayan V10;
> ardından korelasyonlu dört koşul profilli V11 üretildi. V10 ortalama
> gerçek skoru artırdı fakat alan non-inferiority kapısında, kalite-kapılı
> V11-R2Q ise hedef makro `-0,015962` ve 30/111 alan regresyonuyla model
> kapısında reddedildi. Kabul edilmiş global kontrol yine değişmedi. Tam
> defter
> [`FIELD_ROBUSTNESS_VALIDATION_V11.md`](FIELD_ROBUSTNESS_VALIDATION_V11.md)
> içindedir; aşağıdaki V8 “yeni asset üretilmedi” ve “next gate” ifadeleri
> V8 anına ait tarihsel kararlardır.

## Sonuç

Sentetik asset'ler ham/prototip seviyede değildir. Hash-kilitli portföy audit'i
beş son asset aşamasının beşinde de asset kalite kapısının geçtiğini, ancak
yalnız iki aşamanın ortak model açısından yararlı kabul edildiğini doğruladı:

```text
asset-quality pass:             5 / 5
globally useful accepted stage: 2 / 5
global model-gate rejection:    3 / 5
```

Kabul edilen ortak kontrol değişmedi:

```text
simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8
seed 43 / epoch 8 / last.pt
SHA-256 b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f
```

Kanonik portföy makbuzu:

```text
data/processed/audits/synthetic_asset_portfolio_v8.json
SHA-256 c38516e4d4eba60b168f2b935741d2ab3fd6f95c81811104b19f9933007dd466
```

Bu audit yeni asset veya büyük sentetik batch üretmedi. Bunun nedeni kapasite
veya isteksizlik değil: son üç kaliteli challenger'ın gerçek-domain
non-inferiority kapılarını kaybetmesi, darboğazın artık yalnız görsel asset
kalitesi olmadığını doğrudan gösteriyor.

## Portföy ne kadar optimize edildi?

### Dryland V3 R3 — geçti

Dryland paket beş büyüme evresinde 15 bağımsız sorgum geometrisi ve üç albedo
fenotipiyle 45 crop modeli içerir. Dört yabani ot ailesinde 51 modelin 27'si
dört resmi Poly Haven CC0 texture-backed kaynaktan gelir. Ayrıca 16 residue,
üç soil PBR ve üç HDRI bulunur.

İki başarısız ara sürüm materyal yolu/texture-existence gate'inde tutuldu.
Kabul edilen R3; geometri, boyut, MTL texture çözümleme, lisans, smoke,
RGB-mask, scene ayrımı, duplicate ve gerçek-domain A/B kapılarını geçti.
V2'ye karşı üç seed'in üçünde robust kazandı; ortalama fark `+0,017015` oldu.

Karar: **globally useful asset component**.

### Paddy V4 R5 — geçti ve ortak kontrol oldu

Paddy paket 20 bağımsız rice geometrisinin beş evre/üç fenotip varyantlarıyla
60 crop modeli, üç yabani ot morfolojisinde 36 model, üç ıslak PBR, üç paddy
HDRI, 16 debris ve `2–8 mm` sığ su profilini içerir.

R1–R4 sırasıyla fazla karanlık/ayna su, aşırı yoğun radyal morphology, doğru
kompozisyon ama yanlış morphology ve doğru morphology ama yetersiz crop
coverage nedenleriyle kaldı. R5 her ikisini dengeledi. Asset gate'inden sonra
`%5 dryland + %5 paddy`, üç seed'in üçünde beş-domain robust metriği artırdı:

```text
robust mIoU: 0,317954 -> 0,366759  (+0,048805)
CWFID:                              +0,040521
Rice:                               +0,048805
macro:                              +0,017722
```

Karar: **accepted global control**.

### Soy V5 R3 + V6 R5 stress — asset geçti, ortak model kalmadı

Soy paket 20 bağımsız geometri, beş evre, üç fenotip ile 60 crop modeli; 53
weed, üç soil PBR, üç HDRI ve 16 debris içerir. Semantic alpha kartlarındaki
görünmez ama etiketlenmiş pikseller düzeltildi. Dört stress iterasyonundan
sonra V6 R5 yüksek-weed/düşük-crop kompozisyon kapısını geçti.

Model etkisi hedefte güçlüydü:

```text
GrowingSoy: +0,100142
```

fakat ortak robustlukta kabul edilemez trade-off üretti:

```text
CWFID:       -0,130207
Rice/robust: -0,029398
macro:       -0,009288
```

Karar: **asset-quality pass, global-model fail; specialist adayı**.

### Sensor Motion V7 R1 — asset geçti, ortak model kalmadı

V7 R1; 16 linear + 16 smooth-curved olmak üzere 32 normalize `41×41` CC0
PSF, `5–25 px` uzunluk, en az sekiz açı dilimi ve reflect border ile 100
dryland + 100 paddy RGB üretir. 18/18 otomatik, 12-strata manuel, manifest ve
15.857 gerçek görüntüye karşı leakage kapıları geçti.

Modelde hedeflenen real-motion alanını belirgin iyileştirdi:

```text
DeBlur motion: +0,064939
matched sharp: +0,023246
```

ama CWFID `-0,052882`, Rice `-0,018441`, WeedMap `-0,013881` ve existing
macro `-0,007517` geriledi.

Karar: **asset-quality pass, global-model fail; stress/specialist adayı**.

### Sensor Motion V7 R2 — etiket belirsizliği düzeldi, ortak model yine kalmadı

R2 aynı RGB/PSF byte'larında class exposure majority `<0,50` sınırlarını
`ignore` yaparak piksellerin `%2,2551`'ini fail-closed kaldırdı. Manuel ve
otomatik asset kapıları geçti. Doz `%2,439`dan `%0,625`e indirildi.

Bu daha temkinli versiyon GrowingSoy'u `+0,050333` artırdı fakat asıl motion
hedefinde `-0,004755`, CWFID'de `-0,072316` ve macro'da `-0,003716` geriledi.

Karar: **asset-quality pass, global-model fail; stress/specialist adayı**.

## Optimize edilen kalite eksenleri

Portföy şu eksenleri zaten kapsıyor:

- bağımsız crop geometrisi ile yalnız renk varyantının ayrı sayılması;
- büyüme evresi ve albedo/stress fenotipi;
- authored texture-backed ve prosedürel weed çeşitliliği;
- CC0 lisans/provenance ve her artifact için checksum;
- PBR zemin, HDRI, residue/debris;
- paddy sığ su, roughness, turbidity ve ıslak zemin;
- crop/weed density ve high-weed/low-crop kompozisyon;
- yönlü linear/curved exposure PSF;
- motion-boundary uncertainty/ignore;
- static mesh/material, smoke render, RGB-mask alignment, scene split,
  exact/near duplicate ve gerçek-domain model A/B.

Dolayısıyla “yüksek kaliteli asset eklemek” için kalan açık, yalnız daha fazla
polygon/texture değildir. Mevcut başarısızlıklar task interference, sampler
dozu ve gerçek koşul coverage'ı ile ilişkilidir.

## Bilinen ama henüz ölçülmemiş eksenler

Portföy rolling shutter, depth-dependent parallax, rüzgârla yaprak hareketi,
yağmur/damla, lens kirlenmesi, gece/çok düşük ışık, gerçek camera response ve
kalibre shutter/exposure dağılımlarını tam modellemez. Ancak güncel gerçek
manifestler bu faktörleri bağımsız, yeterli ve etiketli strata olarak
ölçmediği için bugün bunlardan birini seçmek post-hoc tahmin olur.

## Neden şimdi yeni asset üretilmedi?

Kullanıcı talebindeki “gerekirse” koşulu veriyle değerlendirilmiştir:

1. Dryland ve paddy asset/model gate'i zaten geçti.
2. Daha zengin soy morphology/composition asset'i hedefi artırdı ama global
   modeli bozdu.
3. Ölçülmüş motion açığına yönelik iki fizik/etiket sürümü asset gate'ini
   geçti; biri hedefte kazandı ama diğer gerçek alanları bozdu, diğeri düşük
   dozda hedef kazancını kaybetti.
4. Yeni full-semantic gerçek paddy strata olmadan üçüncü bir asset denemesi,
   aynı development alanlarına iteratif uyum riski taşır.

Bu nedenle yeni asset üretmemek bir gate başarısızlığı değildir; daha pahalı
ve kanıtsız bir aramayı fail-closed durdurma kararıdır. Reddedilen asset'ler
silinmedi; stress/specialist girdisi olarak korunur.

## Bir sonraki asset gate'i

Yeni üretim şu kanıtlar gelince açılır:

1. RiceSEG exact release edinim/kalite makbuzu;
2. country × institution × growth stage × sensor × altitude × illumination ×
   scene condition gerçek-RGB strata auditi;
3. bu auditte ölçülen tek bir under-covered faktör;
4. model çıktısı görülmeden dondurulmuş static/smoke/mask/manual/leakage/
   domain-gap eşikleri;
5. küçük pilot ve eşit-draw seed-17 screen;
6. yalnız bütün guard'lar geçerse seed `17/29/43` confirmation ve sonra büyük
   batch.

Önceden tek faktör seçilmeyecek. RiceSEG örneğin growth-stage veya sensör
açığını değil başka bir aydınlatma/irtifa açığını gösterirse asset çalışması
ona yönelmelidir.

## Immutable kanıt

- Config: `configs/simulation/synthetic_asset_portfolio_v8.yaml`, SHA-256
  `47d1d2dafa78fcaa8759561255d1bd50b0eaf6bcbec5cce345dc891103397e6c`
- Audit script: `scripts/audit_synthetic_asset_portfolio.py`, SHA-256
  `d1041f92128d79f4b7065838a0c6121c8f01cb6f6da40f33c81e498181a6eed3`
- Audit receipt: `data/processed/audits/synthetic_asset_portfolio_v8.json`,
  SHA-256
  `c38516e4d4eba60b168f2b935741d2ab3fd6f95c81811104b19f9933007dd466`
- Ayrıntılı paddy raporu: `docs/SIMULATION_PADDY_ASSET_QUALITY_REPORT_V4.md`
- Ayrıntılı sensor-motion raporu:
  `docs/SIMULATION_SENSOR_MOTION_ASSET_QUALITY_REPORT_V7.md`

Audit mevcut final checkpoint ve kaynak ağacı SHA'larını yeniden doğruladı.
External test okunmadı, model yeniden eğitilmedi ve kabul edilen sampler
değişmedi.
