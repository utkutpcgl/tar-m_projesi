# CamelinaWeed gerçek-veri kalite raporu — v1

## Sonuç

[CamelinaWeed v1.0.0](https://zenodo.org/records/20148697) kaydının tam
`69.007.560.436` baytlık bölünmüş arşivi körlemesine indirilmedi. Son parçadan
ZIP merkez dizini çıkarıldı; yalnız `Annotated` klasörlerindeki JPEG ve COCO
JSON kayıtları HTTP Range ile alındı. Böylece ağdan `3.365.212.169` bayt
indirildi ve tam arşive göre `%95,12` aktarım tasarrufu sağlandı.

Release içindeki kanonik etiketli altküme:

```text
1.120 RGB JPEG
7 kanonik COCO JSON (+ 5 kaynak/merge provenance JSON'u)
4.474 annotation
4.441 kabul edilen weed polygon annotation
1.097 pozitif içeren görüntü
```

Archive/range, tam JPEG decode, COCO–JPEG eşleşmesi, poligon, maske,
konum-ayrık rol, görsel ve 16.591 mevcut gerçek görüntüye karşı exact/dHash
kapılarının tamamı geçti. Nihai kalite makbuzu:

```text
data/processed/audits/camelinaweed_quality_v1.json
SHA-256 53280f54337746a69b1c87cd29ca396a8650245b2bf3cad71c392ab87d77c73d
```

Bu veri ortak `background/crop/weed` modeli için doğrudan eğitim verisi
değildir. Yayın yalnız weed-instance poligonları sağlar; Camelina ve gerçek
arka plan piksellerini exhaustively ayırmaz. Normalize maske bu nedenle:

```text
kabul edilen weed polygon -> common 2 (other vegetation / weed)
diğer her piksel          -> common 255 (ignore)
```

olarak üretildi. Ayrı, dondurulmuş ve doğrulanmış bir partial-label objective
yazılmadan hem ortak üç-sınıf eğitim hem positive-only eğitim kilitlidir.

## Seçmeli ve yeniden üretilebilir edinim

Zenodo kaydı beş parça yayımlar:

| Parça | Bayt | Upstream MD5 |
|---|---:|---|
| `part-aa` | 17.179.869.184 | `a62495c7...bee4d` |
| `part-ab` | 17.179.869.184 | `91f0a754...e580` |
| `part-ac` | 17.179.869.184 | `b32019d0...f1ef` |
| `part-ad` | 17.179.869.184 | `ab90c20b...ca58` |
| `part-ae` | 288.083.700 | `6054b620...d706` |

Yalnız son parça önce indirildi:

```text
data/raw/candidate_screening/camelinaweed_v1/CamelinaWeed.zip.part-ae
SHA-256 386c4e4bf063300b2d4118b2c867020d68cc7b0c6b7293cf51207dcac2f83443
```

Merkez dizin `10.983` entry / `10.944` dosya gösterir. Dosya uzantısı
envanteri `6.316 TIF + 4.601 JPG + 12 JSON + 15 proje/artifact`'tır. Tüm
COCO JSON'ları ve COCO-referenced JPEG'ler `Annotated` ağaçlarındadır.
Range fetch, her HTTP yanıtında `206` ve exact `Content-Range` doğrular;
seçilen her ZIP üyesini okuyarak CRC kontrolü yapar.

```text
çıkarılan dosya:       1.132
çıkarılan byte:        3.331.550.356
seçili release tree:   40ae938ffefef8577e14a427c8d3a6e0643861649821bb3755c97e579eb2f810
remote range byte:     3.077.128.469
son parça dahil ağ:    3.365.212.169
```

Pinli girdiler:

- `configs/data/camelinaweed_acquisition_screen_v1.yaml`
- `scripts/fetch_camelinaweed_sparse_ranges.py`
- `data/processed/audits/camelinaweed_annotated_ranges_v1.json`
- `configs/data/camelinaweed_partial_label_gate_v1.yaml`, SHA-256
  `7ce1b39a43af6ff6b7e24f7f0d03c07139ae02ed7bc74bfb5d88f9bc164d9a31`

Zenodo açıklaması daha geniş bir annotated-image sayısı bildirir; byte-level
v1.0.0 ZIP indeksi ise yalnız 12 JSON ve bunların kapsadığı 1.120 benzersiz
JPEG içerir. Bu rapor yayın özetini genişletmez; yalnız indirilebilir exact
release'te yeniden üretilebilen COCO altkümesini kabul eder.

## Capture grupları ve roller

Roller RGB pikselleri veya model çıktıları görülmeden önce konum bazında
donduruldu. Thessaloniki yalnız train adayı, ayrı Chalkidiki yalnız
`external_calibration`'dır.

| Grup | Platform | İrtifa | Kaynak | Kabul | Pozitif ann. | Rol |
|---|---|---:|---:|---:|---:|---|
| Summer Thessaloniki | Phantom 4 Pro | 10 m | 297 | 297 | 1.911 | train candidate |
| Summer Thessaloniki | Phantom 4 Pro | 5 m | 34 | 33 | 82 | train candidate |
| Winter Thessaloniki Flight 1 | Mavic 3M | 2 m | 627 | 605 | 1.860 | train candidate |
| Winter Thessaloniki Flight 2 | Mavic 3M | 2 m | 47 | 47 | 104 | train candidate |
| Winter Thessaloniki | Phantom 4 Pro | 3 m | 17 | 17 | 41 | train candidate |
| Winter Chalkidiki | Phantom 4 Pro | 3 m | 43 | 43 | 229 | external calibration |
| Winter Chalkidiki | Phantom 4 Pro | 5 m | 55 | 55 | 214 | external calibration |
| **Toplam** |  |  | **1.120** | **1.097** | **4.441** | **999 / 98** |

Train/calibration field overlap `0`'dır. Publisher/random image split'i
kullanılmadı ve external test oluşturulmadı. COCO `date_captured` alanları
2026 export zamanlarını gösterip raporlanan summer-2025/winter-2025-2026
sezonlarıyla uyuşmadığından manifest `capture_date` alanı bilinçli olarak boş
bırakıldı; tarih üretilmedi.

## COCO ve piksel kalite kapısı

Yedi kanonik JSON, kendi klasöründeki JPEG kümesiyle birebir eşleşir.
`1.120/1.120` görüntü tam decode edildi ve metadata boyutları doğrulandı:

```text
Phantom 4 Pro: 5472 x 3078, 446 görüntü
Mavic 3M:      1920 x 1080, 674 görüntü
Pillow format: 674 JPEG + 446 MPO
```

`MPO`, DJI `.JPG` dosyalarındaki MPF metadata'sından kaynaklanır; her dosyada
frame 0 tam RGB decode edilip exact boyutla doğrulanmıştır.

Tüm kabul edilen poligonlar numeric, finite, çift koordinat sayılı, en az üç
noktalı ve COCO sürekli görüntü alanı içindedir. Sağ/alt sürekli sınırındaki
`x=width` veya `y=height` koordinatları geçerlidir ve son piksele clip edilir.
İki boş segmentation ignore edildi. `k` adlı açıklamasız kategorideki 31
annotation güvenli biçimde ignore edildi; tür veya crop anlamı tahmin
edilmedi. Bu ignore'lardan sonra pozitif poligonu kalmayan 23 görüntü
manifestten çıkarıldı.

Normalize 1.097 maskenin paleti yalnız `{2,255}`'tir. Pozitif piksel kaplaması:

```text
minimum: %0,016927
medyan:  %0,921372
ortalama:%2,531953
maksimum:%51,255574
mask tree SHA-256:
9bd61c26b1c3b1d1198c68d44f647abc87577e4661c4696c1da3162a39c9be8b
```

Kanonik tüm-manifest:

```text
data/processed/manifests/camelinaweed_partial_v1.csv
1.097 satır
SHA-256 dc7bac610d2a3ffa472dc6a2c937032f1e8ca4f7ad2161aa4bd64820a1594b68
```

## Görsel ve sızıntı denetimi

Yedi capture grubu için grup-içi pozitif coverage `q=0,10/0,50/0,90`
örnekleri donduruldu. Toplam 21 RGB / partial-mask / positive-overlay hücresi
ve yedi büyük detay sayfası elle incelendi. Poligonlar kuru yaz sahneleri,
genç kış bitkileri, iki sensör, irtifalar ve iki konumda görünür hedef
bitkileri izledi; sistematik offset veya decode bozulması görülmedi.

Karelerde poligon dışındaki çok sayıda bitki, etiketlerin exhaustive
olmadığını görsel olarak da doğrular. Dolayısıyla bu review hiçbir non-polygon
pikseli background veya crop'a açmaz.

```text
aday -> 16.591 mevcut gerçek exact/dHash<=2: 0
aday-içi exact/dHash<=2:                       0
Thessaloniki <-> Chalkidiki exact/dHash<=2:   0
en yakın mevcut-gerçek Hamming: min 39 / median 92 / max 100
```

Duplicate audit SHA-256:
`4f5b32d2950488e42d807c971d7c7808dea02785b58b248a010cd8728e3a25df`.

## Kullanım kararı

1. Veri kalite kapısını geçti ve ticari kullanıma izin veren CC-BY-4.0
   kaydı vardır.
2. 999 Thessaloniki görüntüsü yalnız positive-only partial-label train
   adayıdır; mevcut ortak eğitim manifestlerine eklenmedi.
3. 98 Chalkidiki görüntüsü yalnız konum-ayrık development calibration'dır;
   model seçimi veya external test için kullanılmadı.
4. İlk sonraki deney, model veya RGB çıktısı görülmeden dondurulacak ayrı bir
   partial-label loss + replay/non-inferiority protokolü olmalıdır.
5. Çok-ülkeli, full-semantic RiceSEG hâlâ daha yüksek önceliklidir; yerel
   Hugging Face oturumu açılır açılmaz pinli edinim çalıştırılmalıdır.

Bu tur yalnız veri edinim/kalite aşamasıdır; checkpoint değişmedi, eğitim
başlatılmadı ve sentetik veri üretilmedi.
