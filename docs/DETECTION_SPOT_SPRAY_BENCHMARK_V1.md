# Detection-only spot-spray benchmark v1

## Kısa karar

**Detection-only, ilk kimyasal spot-spray PoC'si için mantıklı ve daha basit
baseline'dır; saha püskürtme onayı değildir.** Aynı 1024 px, seed 17,
tarih-ayrı WSD koşullarında detection-only weed-kutusu merkezi:

- iyimser GT weed-kutusu isabetinde precision/recall/F1
  `0,7496 / 0,7822 / 0,7655`;
- etiketli gövdeye en fazla `%10` GT weed-kutusu diyagonali uzaktaki sıkı
  isabette `0,6452 / 0,6764 / 0,6604` verdi.

Pose modelinin tahmin edilen keypoint'i aynı ölçümlerde sırasıyla F1
`0,7493 / 0,6591` verdi. Keypoint bu veri diliminde darboğazı aşmadı;
asıl sorun weed proposal/localisation/classification'dır. Detection-only
spot F1 hedeflenen `0,95` kapısını geçmedi. Bugünkü karar:

- **kimyasal spot spray araştırma baseline'ı:** detection-only kutu/instance
  + segmentasyon crop-safety/footprint;
- **lazer veya mekanik nokta:** detection + stem/root/meristem keypoint;
- **gerçek saha ateşlemesi:** `NO-GO` — deposition, kill, crop injury,
  kamera–alet kalibrasyonu ve untouched video testi yoktur.

Kolay okunan 10 sayfalık rapor:
[DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf](results/DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf).

## Detection-only spot spray yapabilir mi?

Prensipte evet. Nozulun etkili ayak izi, kutu-merkezi hatasından genişse ve
weed kutusu doğruysa ayrı stem keypoint zorunlu olmayabilir. Ancak bu
benchmark'taki “spot isabet”, tahmin noktasının GT weed bounding rectangle
içinde olmasıdır. Dikdörtgen toprak da içerir; weed dokusuna damla, yeterli
doz veya öldürme kanıtı değildir.

Dar lazer ışını ya da mekanik sökücü için detection-only yeterli değildir.
Kutu merkezi sap, kök, crown veya meristem olmak zorunda değildir. Bu
müdahalelerde keypoint/eşdeğer instance-geometri, mm kalibrasyon ve fiziksel
outcome testi gerekir.

## Protokol

| Öğe | Dondurulan koşul |
|---|---|
| Veri | WSD yayınından indirilebilen 511 eşli 2048×2048 robot karesi |
| Split | çekim tarihi ayrı: 211 train / 152 validation / 148 test |
| Sınıflar | weed, maize, soybean |
| Detection modeli | YOLO26s detect, 1024 px, seed 17, 100 epoch isteği; patience 30 ile epoch 67'de durdu |
| Pose kontrolü | aynı splitteki YOLO26s-pose 1024 baseline |
| Seçim | checkpoint, confidence ve aynı-kare dedupe yalnız validation'dan |
| Test | 1.102 weed kutusu; 1.097 görünür stem noktası |
| Eşleşme | one-to-one; bir aksiyon iki weed'i doğru sayamaz |

WSD test tarihi önceki resolution/keypoint geliştirmesinde incelendiği için
bu panel artık **development holdout**'dur; pristine final test değildir.

## İki müdahale metriği

1. **Weed-kutusu proxy isabeti:** Aksiyon noktası veya tanımlı dairesel
   footprint bir GT weed kutusuyla kesişir. Kimyasal spot spray için iyimser
   üst sınırdır.
2. **Sıkı stem isabeti:** Aksiyon noktası görünür GT weed stem noktasına,
   ilgili GT weed kutusu diyagonalinin en fazla `%10`u kadar uzaktır. Lazer
   benzeri noktasal localisation için daha sıkı proxy'dir; mm değildir.

Her iki metrikte TP eşleşmesi one-to-one'dır. Precision yanlış aksiyonları,
recall kaçırılan weed'leri, F1 ikisini birlikte gösterir.

## Eşit koşullu A/B

| Strateji | Spot P | Spot R | Spot F1 | Sıkı stem F1 |
|---|---:|---:|---:|---:|
| **Detection-only → kutu merkezi** | **0,7496** | 0,7822 | **0,7655** | **0,6604** |
| Pose model → kutu merkezi | 0,7011 | **0,8067** | 0,7502 | 0,6559 |
| Pose model → tahmin keypoint | 0,6994 | **0,8067** | 0,7493 | 0,6591 |

Detection-only daha yüksek precision ile en iyi spot F1'ı verdi. Pose
keypoint ile pose kutu-merkezi arasındaki sıkı stem F1 farkı yalnız `+0,0032`
oldu. Bu, “keypoint gereksizdir” demek değildir; bu veri ve toleransta modelin
önce weed'i doğru önermesi/sınıflandırması gerektiğini gösterir.

WSD makalesindeki detection + stem regression de kutu/sınıf tahminine ek bir
2B stem koordinatı, yani tek keypoint benzeri bir başlıktır. Makale kendi
simüle weeding deneyinde detection kontrolü için `%75,37`, detection+stem
regression için `%80,42` weeding accuracy raporlar. Bu ölçü bizim one-to-one
F1'ımızla aynı değildir ve fiziksel lazer kill-rate değildir.

## `%95 recall` zorlandığında

Validation'da recall hedefi için bulunan en düşük eşik `0,01` oldu; validation
yine de `%95` recall'a ulaşamadı. Aynı politika testte:

| Politika | Precision | Recall | F1 | Aksiyon | FP | FN |
|---|---:|---:|---:|---:|---:|---:|
| Dengeli max-F1 | 0,7496 | 0,7822 | 0,7655 | 1.150 | 288 | 240 |
| Recall-95 denemesi | 0,3582 | 0,9428 | 0,5191 | 2.901 | 1.862 | 63 |

Dolayısıyla mevcut modelde kaçırmayı threshold ile azaltmak, sahada kabul
edilemez sayıda yanlış püskürtme adayı üretir. Tracking ve sıra prior'ının bu
yanlışları ne kadar azalttığı ID-etiketli videoda ölçülmeden başarı hanesine
yazılmadı.

GT crop bounding rectangle ile nokta çakışması dengeli detection-only
politikasında `159/1.150 = 0,1383` oldu. Bu dikdörtgen gerçek crop canopy
değildir ve crop injury oranı olarak yorumlanamaz; fakat mevcut etiketlerle
spray-safety kapısını açamayacağımızı gösterir.

## Küçük nesne sonucu ve 28 px

Boyut, model girişinde `sqrt(GT weed kutu alanı)`dır; bitki maskesi çapı
değildir.

| 1024 giriş boyutu | Weed sayısı | Dengeli spot recall |
|---|---:|---:|
| `<14 px` | 65 | 0,5385 |
| `14–<28 px` | 874 | 0,7826 |
| `28–<56 px` | 162 | 0,8827 |
| `≥56 px` | 1 | 0,0000; örnek sayısı yetersiz |

Küçüklük belirgin bir darboğazdır, fakat tek darboğaz değildir. 28–56 px
grubunda dahi recall `%88,3`, `%100` değildir. Önceki sentetik `%100`
ifadesi yalnızca 26 connected semantic component'in her birinde en az bir
güvenli tahmin pikseli bulunmasıydı; gerçek instance-level müdahale başarısı
değildi. Aynı sentetik grupta weed-pixel coverage yaklaşık `%47` idi.

Test dağılımında 1024 model girişinde weed kutularının yalnız `%14,8`i 28 px
üstündedir. Geometrik olarak aynı 2048 kaynak pikselleri korunursa:

| İşlenen raster | `≥28 px` kutu oranı | Medyan kutu-eşdeğer boyut |
|---:|---:|---:|
| 1024 | `%14,8` | 22,6 px |
| 1536 | `%79,0` | 33,9 px |
| 2048 | `%94,1` | 45,2 px |

Bu tablo yalnız boyut geometrisidir. Aynı 1024-trained checkpoint'i 1536'ya
büyütmek spot F1'ı `0,7655 → 0,7179` düşürdü; precision kaybı oldu. Yani kör
resize çözüm değildir. Native sensör detayı/FOV, focus, blur ve o rasterda
eğitim birlikte test edilmelidir.

## Her weed'i 28 px üstünde tutabilir miyiz?

“Her weed” ancak minimum müdahale edilecek fiziksel büyüklüğü tanımlarsak
anlamlıdır. Yeni çıkan, optik olarak seçilemeyecek kadar küçük weed'leri geniş
FOV ile 28 px garanti etmek mümkün değildir. Kamera eşitliği:

```text
GSD_max (mm/px) = minimum müdahale weed çapı (mm) / hedef piksel
yatay yer genişliği (mm) = yatay sensör pikseli × GSD
```

Örnekler:

| Minimum weed | 28 px için GSD | 2048 px yatay yer | 4096 px yatay yer |
|---:|---:|---:|---:|
| 10 mm | ≤0,357 mm/px | ≤0,73 m | ≤1,46 m |
| 20 mm | ≤0,714 mm/px | ≤1,46 m | ≤2,93 m |
| 30 mm | ≤1,071 mm/px | ≤2,19 m | ≤4,39 m |

Blur, defocus, perspektif ve demosaic kaybı nedeniyle tasarım hedefi olarak
28 yerine `42–56 px` daha güvenli başlangıç marjıdır. Alternatifler daha dar
FOV/zoom, daha yüksek gerçek sensör çözünürlüğü, birden çok kamera veya çok
küçük weed'lerde `no-fire / sonraki geçiş` kuralıdır.

## Sonraki en etkili benchmark

1. Minimum öldürülebilir weed çapını, nozul footprint'ini, çalışma yüksekliği
   ve yatay kapsama ihtiyacını dondur; buradan GSD ve optiği seç.
2. Aynı sahneyi native `1024-equivalent / 1536 / 2048` detail ve gerçek
   focus–motion koşullarında çek; dijital upscale kullanma.
3. Detection-only'yi native tile/high-resolution eğitimle tekrar ölç;
   segmentasyon crop veto olarak ayrı ablate edilsin.
4. En az 3–4 yeni tarla/session'da weed/crop instance, stem ve track ID
   etiketi topla. Deploy distribution validation, tamamen yeni session test
   olsun.
5. Basit world-coordinate association + `≥3` kare onay + fire-once ile
   track-level P/R/F1 ölç. ReID yalnız uzun occlusion problemi ölçülürse ekle.
6. Offline track F1 `≥0,95` sonrası fiziksel deposition/kill `≥0,95` ve crop
   injury kapısını ayrı aktüatör bench'inde ara.

## Birincil kaynaklar

- [Weed Stem Detection — detection + stem regression](https://arxiv.org/abs/2502.06255)
- [RoWeeder — row prior ve intra-row weed sınırı](https://arxiv.org/abs/2410.04983)
- [ByteTrack — basit detection association](https://arxiv.org/abs/2110.06864)

## Exact artefaktlar

- 1024 A/B JSON:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/wsd_detection_poc_v1/yolo26s_detect_1024_seed17/spot_spray_ab_1024_final_v1/spot_spray_ab_metrics.json`
- 1536 inference A/B JSON:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/wsd_detection_poc_v1/yolo26s_detect_1024_seed17/spot_spray_ab_1536_inference_v1/spot_spray_ab_metrics.json`
- Detection checkpoint SHA-256:
  `c101548c235aa064af691b79aa15353166ad1285d6c65e0ea12f6075e6484177`
- Detection dataset receipt:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/weed_stem_detection_detect_v1_receipt.json`
- Self-contained yerel paket:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_detection_spot_spray_benchmark_v1/`

Ultralytics baseline AGPL-3.0 araştırma PoC kapsamındadır; ürün/deployment
lisansı ayrıca çözülmelidir. Dataset, checkpoint ve tam galeriler boyut ve
lisans nedeniyle Git deposuna konmaz.
