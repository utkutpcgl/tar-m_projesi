# Segmentasyonla %95+ saha müdahalesi kanıt planı v1

Okunabilir 15 sayfalık görsel rapor:
[SEGMENTASYON_95_VE_RAKIP_CEILING_RAPORU_V1.pdf](results/SEGMENTASYON_95_VE_RAKIP_CEILING_RAPORU_V1.pdf).

## Net karar

Ana hat instance segmentation olarak kalır. Hedef, mask mIoU `%95` değil;
deploy-benzeri videoda bitki/track bazında güvenli müdahale başarısıdır.

| Metrik | Minimum GO | Güçlü hedef |
|---|---:|---:|
| Track-level weed action precision | `%97` | `%98` |
| Track-level weed action recall | `%95` | `%97` |
| Track-level weed action F1 | `%96` | `%97+` |
| Crop'a yanlış aksiyon | `≤%0,5` | `≤%0,1–0,25` |
| Nozul-footprint safe hit | `≥%95` | `≥%97` |
| Fiziksel weed knockdown | `≥%90` | `%93–95` |

Ana başarı iddiası ortalama skorla değil, tamamen ayrılmış saha/session
testindeki `%95` güven aralığının alt sınırıyla verilir. Küçük weed, crop'a
yakın weed, gölge, ıslak toprak ve hareketli görüntü sonuçları ayrıca geçer.

## Küçük weed'i dışarıda bırakınca bugün neredeyiz?

Boyut, PhenoBench native/model `1024` rasterında
`sqrt(exact instance kutu alanı)`dır. Bu fiziksel milimetre değildir.

İki teşhis vardır:

1. Orijinal `%0,49` confidence ile yalnız GT başarı paydasını değiştirir.
2. Predicted weed maskesinin boyutunu kullanarak validation'da confidence ve
   minimum tahmin boyutu seçer; aynı policy testte uygulanır.

| Minimum GT weed | Test weed | Orijinal F1 | Predicted-size gate F1 | P / R |
|---:|---:|---:|---:|---:|
| Tümü | 1.754 | `%74,0` | `%72,3` | `%83,2 / %63,9` |
| `≥14 px` | 1.481 | `%78,1` | `%78,9` | `%83,1 / %75,0` |
| `≥28 px` | 980 | `%81,0` | `%83,1` | `%83,0 / %83,2` |
| `≥42 px` | 625 | `%79,7` | **`%84,1`** | **`%88,5 / %80,2`** |
| `≥56 px` | 409 | `%73,8` | `%83,1` | `%90,5 / %76,8` |

En iyi teşhis `≥42 px` grubudur. Validation'da seçilen policy confidence
`0,56`, predicted-mask boyutu `≥35 px` kullanır. Testte:

- `501 TP`, `124 FN`, `65 FP`;
- FP'nin `48`i toprak, `10`u crop, `7`si duplicate aksiyondur;
- crop temas oranı `%1,77`;
- `%95` recall için yaklaşık `93` ek weed bulunmalı;
- `%95` precision için FP yaklaşık `65 → ≤31` seviyesine inmeli;
- `%0,5` crop riski için crop hit `10 → ≤3` olmalıdır.

Sonuç: yeterli görüntü boyutu gerekli ama tek başına yeterli değildir. Boyut
ve predicted-size gate ana F1'ı yaklaşık `+10,1` puan yükseltebilir; kalan
yaklaşık `11` puan hedef-domain sınıflandırma, false-action bastırma ve temporal
kanıttan gelmelidir.

Bu analiz **post-hoc teşhistir**. PhenoBench testi ana A/B'de daha önce açıldığı
için tekrar untouched sayılamaz ve bu policy saha gate'i olarak kullanılamaz.
Yeniden üretim:

- `configs/benchmark/phenobench_actionable_size_diagnostic_v1.yaml`
- `scripts/analyze_phenobench_actionable_size_v1.py`
- yerel exact çıktı:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/phenobench_detect_segment_fair_v1/actionable_size_diagnostic_v1/actionable_size_metrics.json`

### Train-fit teşhisi: yalnız domain shift değil

Aynı final segmenter, eğitimde gerçekten gördüğü 1.407 karede, testten önce
kilitlenmiş aynı `0,49` eşikle değerlendirildi:

| Split | Precision | Recall | F1 |
|---|---:|---:|---:|
| Train | `%90,9` | `%65,9` | `%76,4` |
| Validation | `%79,5` | `%71,7` | `%75,4` |
| Test | `%86,0` | `%64,9` | `%74,0` |

Train boyut recall'ı `<14 / 14–28 / 28–56 / ≥56 px` için sırasıyla
`%23,9 / %54,9 / %82,6 / %84,9`dur. Train F1'ın da düşük olması, PhenoBench
içindeki parsel/domain farkının ana açıklama olmadığını gösterir. Model mevcut
reçetede küçük bitki temsilini ve yüksek-recall/az-FP ayrımını yeterince
öğrenemiyor. Kendi robot domainimiz yine zorunludur, fakat yalnız hedef-domain
fine-tune'ın `%95`e sıçratacağı varsayılamaz. Aşağıdaki kasıtlı-overfit
deneyi bu yorumu netleştirdi: aynı model hedef görüntülerini `%99,68` F1 ile
öğrenebiliyor; sorun temsil kapasitesinden çok yeni parsel/session'a genellemedir.

## `%95` teknik olarak mümkün mü? Tamamlanan kanıt deneyleri

### 1. Küçük-set kapasite kapısı

Aynı final segmenter checkpoint'inden başlayan iki `126`-kare kol,
augmentation kapalı, tam çözünürlük maske kaybı ve `120` epoch ile kasıtlı
olarak aynı train karelerine overfit edildi. Ana aksiyon, tahmin edilen crop
maskesinin `14 px` güvenlik halesini weed maskesinden çıkarıp kalan weed
dokusundaki en yeşil noktayı seçer. Payda yalnız önceden tanımlı `≥42 px`
weed'lerdir.

| Aynı-kare kapasite testi | Kare / parsel | Precision | Recall | F1 | Crop hit | `%98` kapısı |
|---|---:|---:|---:|---:|---:|---|
| Kaynakta dağıtılmış alt küme | `126 / 21` | `%97,15` | `%97,77` | `%97,46` | `0/316` | Kaldı |
| Hedef-benzeri üç parsel | `126 / 3` | **`%99,68`** | **`%99,68`** | **`%99,68`** | `0/317` | **Geçti** |

Hedef-benzeri kolda `316 TP / 1 FP / 1 FN` vardır. Bu sonuç saha
genellemesi değildir; model ve etiket/aksiyon hattının uygun görüntüde `%95+`
kapasiteye sahip olduğunu gösteren bilinçli ezberleme testidir. Aynı modellerde
segmentasyon kutu merkezi F1'ı yalnız `%61,05 / %59,18` oldu; maskeden doğru
aksiyon noktası çıkarmak gerçek bir kazançtır.

### 2. Görülmemiş parsellerde basit aksiyon ve sıra prior'ları

Validation'da eşik seçilip aynı `403` test karesi / `625` uygun weed'de
uygulandı. Test daha önce açıldığı için bunlar post-hoc development
sonuçlarıdır.

| Aksiyon noktası | Precision | Recall | F1 | Crop hit / atış |
|---|---:|---:|---:|---:|
| Weed maskesinde en derin iç nokta | `%86,21` | `%75,04` | `%80,24` | `17/544` (`%3,13`) |
| **Crop-safe excess-green** | **`%92,02`** | **`%77,44`** | **`%84,10`** | `15/526` (`%2,85`) |
| Yalnız confidence ile güvenli eşik | `%100` | `%27,20` | `%42,77` | `0/170` |

RGB'den alınan basit excess-green noktası F1'ı `+3,86` puan artırdı;
fakat confidence ile crop riskini sıfırlamak recall'ı kullanışsız seviyeye
indirdi. Sorun sadece nokta seçimi veya threshold değildir.

Tahmin edilen crop merkezlerinden çıkarılan kamera-dikey sıra bantları da
sadece veto olarak denendi:

| Sıra yarı-genişliği | Precision | Recall | F1 | Crop hit / atış |
|---:|---:|---:|---:|---:|
| `21 px` | `%93,98` | `%69,92` | `%80,18` | `%0,86` |
| `42 px` | `%94,65` | `%65,12` | `%77,16` | `%0,70` |
| `63 px` | `%94,85` | `%58,88` | `%72,66` | `%0,26` |
| `84 px` | `%96,69` | `%51,36` | `%67,08` | `%0` |

Sıra bilgisi crop güvenliğini artırır ama in-row weed'leri de sildiği için
ana crop/weed sınıflandırıcısı olamaz. RTK ekim haritası veya temporal
sıra fit'i ile **soft safety prior** olarak kalır.

### 3. Hedef-domain uyarlama gerçekten genelliyor mu?

Dört model aynı `172`-kare ortak kalibrasyonda eşiklendi ve aynı `403`
test karesi / `625` uygun weed'de karşılaştırıldı. Ana metrik yine
crop-safe excess-green aksiyonudur.

| Model | Precision | Recall | F1 | Crop hit / atış | Base F1 farkı |
|---|---:|---:|---:|---:|---:|
| **Dondurulmuş base** | **`%92,02`** | `%77,44` | **`%84,10`** | `%2,85` | — |
| 126 kaynak kare, agresif overfit | `%74,86` | `%82,88` | `%78,66` | `%4,91` | `-5,44` puan |
| 126 hedef-benzeri kare, agresif overfit | `%88,41` | `%79,36` | `%83,64` | `%5,35` | `-0,46` puan |
| 126 hedef + 126 kaynak replay, 30 epoch | `%81,40` | **`%85,44`** | `%83,37` | `%5,64` | `-0,73` puan |

Replay recall'ı `+8,00` puan yükseltti; buna karşılık precision `-10,61`
puan ve crop riski yaklaşık iki kat kötüleşti. Güvenli replay eşiğinde
precision/recall/F1 `%98,90/%28,64/%44,42` oldu. Challenger reddedildi.

Bu dört bulgu birlikte şunu kanıtlar:

1. Model/pipeline hedef görüntüde `%95+` kapasiteye sahiptir.
2. `≥42 px` boyut ve hedef veri recall için güçlü kaldıraçlardır.
3. Mevcut hedef veri, yeni parselde crop/weed precision'ını korumaya yetmez.
4. Sıradaki yazılım deneyi daha uzun fine-tune değil; session-dengeli replay,
   crop-yakın hard-negative oversampling/loss ve ID-etiketli temporal A/B'dir.
5. Kamera/GSD–focus–exposure koşulunu standardize etmeden veri uyarlaması
   tek başına saha kanıtı üretemez.

## Rakipler gerçekten ne yapıyor?

Kamuya açık verilerde sensörün gerçek megapikseli çoğunlukla açıklanmıyor.
Bu nedenle kamera sayısı, fiziksel hedef/spray çözünürlüğü ve saha outcome'u
ayrı yazılmıştır. Vendor placement doğruluğu, weed-recognition precision/recall
ile aynı şey değildir.

| Sistem | Fiziksel "çözünürlük" / donanım | Kamuya açık başarı | Dürüst yorum |
|---|---|---|---|
| John Deere See & Spray | 36 boom kamerası; `>2.500 ft²/s`; `15 mph`; kamera MP yok | 2025'te 5 milyon acre; ortalama yaklaşık `%50` non-residual herbisit azalması; broadcast-benzeri hit-rate ifadesi | Ticari ölçek çok güçlü; P/R/F1 ve minimum weed yayımlanmıyor |
| Greeneye | 24 yakın yüksek-çözünürlük kamera, 12 GPU, 72 ışık; 40 fps; `15 mph`; scouting GSD'si "sub-mm" | Volcani gözetimli vendor trial recall `%95,7`; UNL'de broadleaf kontrol `%96,3`, grass `%89,6` | Bizim hedef recall seviyemizin piyasada mümkün olduğunu gösterir; precision/minimum weed yok |
| Ecorobotix ARA 620 | Altı yakın RGB+3D vision modülü; `156` nozul; `7,2 km/h`; sprey footprint `6×6 cm` | 2025/26 brochure: minimum weed tanıma `≥2 mm`, crop `≥2 cm`, dock/thistle `≥5 cm`; girdide `%95`e kadar tasarruf | `2 mm` bir vendor recognition threshold'udur; `6 cm` fiziksel sprey alanı ve P/R/F1 ayrıdır |
| Bosch/BASF ONE SMART SPRAY | Yüksek çözünürlüklü boom kameraları + LED; GoG/GoB; kamera MP/minimum weed yok | Vendor `>%95 application accuracy`, broadcast ile kıyaslanabilir | "Application accuracy" tanımı ve P/R ayrımı yayımlanmıyor |
| Bilberry | Boom kamera sistemi; `25 km/h`; opsiyonel gece görüşü | Vendor: normal koşulda çapı `≥5 cm` weed'lerin `>%90` hit'i; iki geçiş için teorik `%99` | Boyut+hit birlikte açıklanan en okunabilir kontratlardan; iki-geçiş hesabı bağımsız hata varsayar |
| WEED-IT QUADRO | Kamera yok; aktif ışıklı klorofil fluoresansı; her sensörde dört `25 cm` zone; `25 km/h` | Vendor bitki hit-rate `%95–98`; kimyasal tasarrufu `%95`e kadar | Green-on-brown için güçlü ceiling; klasik sensör crop/weed tür ayrımını bizim vision task'ı gibi yapmaz |
| Verdant SharpShooter | Yüksek hızlı imaging, özel ışık, spatial tracking ve aimable turret; `7 acre/h` | Vendor: atışların `%99`u hedefin `2 mm` içinde; 2025 üniversite trial'ında broadcast-benzeri kontrol | `%99` conditional actuator placement'tır; recognition P/R ve minimum weed değildir |
| Carbon LaserWeeder G2 | Her modülde 3 kamera, 20 LED, 2 GPU, 2 lazer; G2 600'de 36 kamera; vendor sub-mm hedefleme | Vendor G2 600 `up to %99` weed kill; hakemli eski nesil çoklu-geçişte weed biomass `≥%97` az, crop stunting `≤%1` | En yakın lazer ceiling'i; recognition P/R/minimum weed yok, erken/küçük meristem ve tekrarlı geçiş kritik |

Kaynaklar:

- [John Deere 2025 saha ölçeği ve tasarruf](https://www.deere.com/en/news/all-news/see-spray-technology-across-5-million-acres/)
- [Greeneye detection trial](https://greeneye.ag/trials/)
- [Greeneye UNL saha kontrol sonucu](https://greeneye.ag/press-releases/greeneye-unl-publish-field-trials-results/)
- [Greeneye kamera/GPU/ışık mimarisi](https://greeneye.ag/press-releases/first-greeneye-technology-dealership-opens-in-nebraska/)
- [Ecorobotix 2025/26 brochure: `2 mm` tanıma, `6×6 cm` sprey](https://ecorobotix.com/wp-content/uploads/2026/01/Ecorobotix_Brochure_ARA_620_FR_20251215_LD.pdf)
- [Ecorobotix vision-box ve LED yapısı](https://help.ecorobotix.com/en/ara/user-manual/620_s_g2-ts4-2/electrical-system)
- [ONE SMART SPRAY `>%95 application accuracy`](https://www.onesmartspray.com/)
- [Bilberry `≥5 cm` weed için `>%90` hit](https://bilberry.io/faq/)
- [WEED-IT `%95–98` vendor hit-rate](https://weed-it.com/our-technology/spot-spraying/)
- [Verdant placement ve tracking iddiası](https://www.verdantrobotics.com/faqs)
- [Carbon G2 donanımı](https://carbonrobotics.com/laserweeder-g2-600)
- [Carbon kullanılan hakemli Cornell/Rutgers saha denemesi](https://doi.org/10.1002/ps.8912)

### Piyasada vision ceiling'i çözen ürün var mı?

Kamuya açık ve denetlenebilir biçimde, bütün crop/weed/ışık/toprak koşullarında
insan seviyesinde P/R/F1 kanıtlayan evrensel bir ürün yoktur. Piyasadaki
ayrı kanıt parçaları Greeneye'nin `%95,7` recall'ı, Ecorobotix'in `≥2 mm`
recognition threshold'u ve `6×6 cm` spray footprint'i, Bilberry'nin `≥5 cm`
weed için `>%90` hit'i, Verdant'ın `2 mm` atış yerleştirmesi ve Carbon'ın
fiziksel biomass sonucudur. Hiçbiri aynı deneyde minimum boyut + recognition
precision/recall + crop hit + kill-rate sözleşmesinin tamamını yayımlamıyor.

Pratik ticari ceiling, iyi tanımlı crop/domain ve kontrollü donanımda yaklaşık
`%95–98` hit/recall veya broadcast'e benzer weed-control'dür. `2 mm` ya da
"sub-mm" pazarlama iddiası, o boyutta `%95` F1 veya aynı boyutta fiziksel
müdahale anlamına gelmez. Bizim ürün kontratı bu belirsizliği tekrar etmemeli.

Ceiling ürün değil, tekrarlanan sistem mimarisidir:

1. Bitkiye yakın çoklu yüksek çözünürlüklü kamera.
2. Güneşe güvenmeyen LED/flash ve mümkünse kapalı/gölgeli görüş hacmi.
3. Kısa pozlama veya global shutter ile motion-blur kontrolü.
4. Bilinen crop/domain için özel veri ve sürekli fleet-data döngüsü.
5. Encoder/homography ile temporal-spatial tracking ve gecikme telafisi.
6. Crop safety zone, abstention ve fiziksel actuator kalibrasyonu.

Bu desen bizim kamera + ışık + tracking hipotezimizi kuvvetlendirir; fakat
başarı artışını bizim saha verimizde ölçmeden garanti etmez.

## Kamera/çözünürlük için bugün elimizde hangi kanıt var?

Önceki dondurulmuş kamera tanısı, aynı unseen sentetik geometriyi native
`256/384/512/768/1024` render etti. Model ve eşik sabitken mIoU
`0,5553/0,6338/0,6952/0,7753/0,8250`; safe weed recall
`0,1936/0,2539/0,3334/0,4416/0,4882` oldu. Aynı sahnede defocus `σ=3`
mIoU'yu `-0,0826`, `7 px` motion blur `-0,0121` değiştirdi. Bu, apparent
size ve focus'un güçlü etken olduğunu gösterir; sentetik saha garantisi
değildir.

Gerçek holdout'ta aynı capture'ı yazılımla `1,5×/2×` büyütmek ise
SugarBeets mIoU'yu `0,5772 → 0,3621/0,4282`, crop riskini
`%4,10 → %65,20/%29,60` değiştirdi. Kör upscale kesin olarak reddedildi.
Kazancın gelmesi için yeni **optik bilgi**, doğru focus/pozlama ve o native
rasterda eğitim gerekir.

Canvas `768` hedef-specialist iki seed ortalamasında SugarBeets mIoU'yu
`+0,1301` artırdı; CWFID'yi `-0,0442` düşürdü. Bu da yüksek raster ve
hedef-domain verinin etkili olabileceğini, fakat koşulsuz global modele
genellenemeyeceğini gösterir. Ayrıntı:
[KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md](KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md).

Sabit sentetik düşük-ışık enerji sweep'i yaklaşık düz kaldı; bu değer
lux/watt değildi. Dolayısıyla "daha çok ışık F1'ı şu kadar artırır" sonucu
yoktur. Işık; kısa shutter, düşük gain, sabit renk ve focus'u mümkün kılan
bir sistem olarak fiziksel paired bench'te ölçülmelidir.

## Minimum müdahale edilebilir weed sözleşmesi

Küçük weed'i metriğin dışına almak ancak **model sonucundan önce**, fiziksel
aktüatör ve kamera kontratıyla yapılır. Sonradan zor örnekleri elemek yasaktır.

Her kayıt için şu eligibility dondurulur:

- minimum görünür canopy genişliği: `d_min_mm`;
- minimum visible fraction;
- crop/nozul safety mesafesi;
- kamera kalibrasyonundan minimum predicted-mask fiziksel boyutu;
- müdahale anındaki maksimum crop/weed örtüşmesi.

Fiziksel nozul henüz seçilmediği için kalıcı `d_min` uydurulamaz. İlk saha
kanıtı için şu iki katmanlı geçici sözleşme kullanılmalıdır:

- ana PoC/G0 paydası: görünür canopy kısa kenarı `≥20 mm` ve visible fraction
  `≥%70`;
- stretch paydası: `10–20 mm`; ayrı raporlanır, ana sonucu saklamaz;
- `<10 mm`: kaçırılan agronomik fırsat sayısı olarak raporlanır; kamera bu
  boyutu insan üst sınırında güvenilir göstermeden aksiyon F1 paydasına girmez;
- crop mesafesi, gerçek spray footprint'in yarısı + kalibrasyon/latency
  hatasının `%95` persentilinden küçükse sistem ateşlemez.

Bu, küçük otları sonsuza kadar yok saymak değildir. İlk geçişte yüksek
güvenli faydayı kanıtlar; sonraki kamera/optik iterasyonu `d_min`i `20→10→<10 mm`
indirir. Bilberry'nin `≥5 cm` vendor hit sözleşmesi ve iki-geçiş stratejisi de
piyasada boyut kontratı + tekrar geçişin normal olduğunu gösterir.

Başlangıç kamera hedefi, en küçük uygun weed'in **model girdisinde** en az
`42 px`, tercihen `56 px` görünmesidir. 4K kareyi tek parça `1024`e küültmek
bu şartı bozabilir; native tile gerekir. Gerekli GSD:

```text
GSD_mm_per_px ≤ d_min_mm / target_pixels
FOV_width_mm  = sensor_width_px × GSD_mm_per_px
```

| Fiziksel minimum weed | `42 px` için GSD | 4096 px yatay FOV | `1 m/s`, `<1 px` blur için pozlama |
|---:|---:|---:|---:|
| `20 mm` PoC | `≤0,476 mm/px` | `≤1,95 m` | `≤0,476 ms` (`≈1/2100 s`) |
| `10 mm` stretch | `≤0,238 mm/px` | `≤0,975 m` | `≤0,238 ms` (`≈1/4200 s`) |

Geniş bomu tek kamerayla çözmeye çalışmak yerine rakipler gibi yakın
çoklu kamera veya iki dar-FOV kamera gerekir. 4096 genişlikte tam kare model
girdisine küçültülmez; örtüşmeli `1024/1536` native tile işlenir.

Motion blur bütçesi de fiziksel hesaplanır:

```text
blur_px = vehicle_speed_mm_s × exposure_s / GSD_mm_per_px
```

Bu yüzden güçlü senkron LED/strobe, global shutter ve kontrollü görüş
hacmi model değişiminden önce gelir. Tablo teorik başlangıçtır; lens MTF,
defocus, demosaic ve titreşim nedeniyle gerçek rig'de USAF/bitki target'la
doğrulanır.

## Başarıyı hangi deneyle ispatlarız?

### A. Paired kamera–ışık–hareket deneyi

Aynı işaretli bitkiler dakikalar içinde şu koşullarda tekrar çekilir:

| Faktör | Kontrol | Challenger |
|---|---|---|
| GSD/sensör | Mevcut kamera | Global-shutter, native yüksek çözünürlük; uygun weed `≥42–56 px` |
| Işık | Ortam ışığı | Senkron LED/strobe + gölgelik |
| Hareket | Durgun/yavaş | Hedef saha hızı, exposure ile `<1 px` blur |
| Model rasterı | Native 1024 | Native tile 1536/2048; dijital upscale yok |

Önce aynı frozen model kullanılır; görüntü donanımının saf katkısı ölçülür.
Sonra her kol yalnız kendi native verisiyle aynı bütçede fine-tune edilir;
train–inference uyumu ayrıca ölçülür.

### B. Hedef-domain veri ve task sözleşmesi

- Başlangıç task'ı `crop instance / weed instance / unknown-partial`dır.
- Spot spray için species classification zorunlu değildir: bilinen crop
  dışındaki uygun bitki weed adayıdır.
- Ekim sırası ve mümkünse planting-map crop sınıflandırması/safety prior'ıdır;
  ana model sonucunun yerine geçmez.
- Train/val/test tüm video session'ları ve tarlalar bazında ayrılır; komşu
  frameler farklı split'e düşmez.
- İki insan aynı raw video ve aynı zoom altında weed-track üst sınırını ölçer.
  İnsan da `%95`e ulaşamıyorsa kamera veya task tanımı düzeltilir.

### C. Temporal A/B

Tek-kare segmentasyon ile aynı modelin temporal kolu eşlenir:

```text
instance mask + confidence
        ↓ kamera kalibrasyonu / ground-plane projection
track association + 3–5 gözlemde logit/mask fusion
        ↓
k-of-n doğrulama + crop safety veto
        ↓
bir track / bir atış
```

Mevcut `≥42 px` tek-kare recall `%77,44` için üç **bağımsız** görüşte
teorik any-hit `%98,85` olur; gerçek hatalar aynı occlusion/domain nedeniyle
korelasyonludur ve k-of-n precision'ı da değiştirir. Bu sayı başarı iddiası
değildir. ID-etiketli video üzerinde track P/R/F1, crop hit ve duplicate-shot
oranı ölçülmeden tracking kazanımı yazılmaz.

### D. Model deneyi sırası

YOLO26s-seg güçlü ve hızlı baseline'dır; ideal olduğu kanıtlanmadı.
Küçük-set kapasite kapısı tamamlandı: hedef-benzeri `126` karede
crop-safe action F1 `%99,68` ile geçti. Bu nedenle ilk darboğaz model
kapasitesi değil genellemedir. Agresif target-only ve basit replay ortak testte
base'i geçmedi; ikisi de reddedildi. Kalan deney sırası:

1. `mask_ratio=1` korunarak crop-yakın hard-negative ve session-dengeli
   source/target replay; 120-epoch ezber yerine erken validation seçimi.
2. Hedef GSD + kontrollü ışık + doğru exposure ile paired fiziksel capture.
3. Aynı optikte target instance-mask fine-tune; parsel/session ayrı validation.
4. 4K native tile `1024/1536/2048` A/B; dijital upscale yok.
5. ID-etiketli videoda tek-kare ile 3–5 görüş temporal fusion A/B.
6. Bunlar plateau yaparsa tek bir daha büyük aynı-aile segmenter ve tek bir
   alternatif instance segmenter; mimari zoo yok.
7. Yalnız hata analizi desteklerse NIR/depth. RGB crop-vs-weed darboğazını
   kendiliğinden çözmeyecekleri için ilk satın alma değildir.

### E. Untouched saha ve fiziksel kanıt

- En az üç ayrı tarla ve tamamen ayrılmış session'lar.
- Untouched testte en az `2.000` uygun weed track'i.
- Crop collision `≤%0,1` iddiası için tercihen en az `3.000` crop-yakın aksiyon
  fırsatı ve sıfır crop hit; `rule of three` ile %95 üst sınır yaklaşık `%0,1`.
- Boyut, ışık, toprak, nem, crop mesafesi ve hız stratification'ı.
- Confidence/track policy validation'da JSON'a kilitlenir; test bir kez açılır.
- Su/UV boya bench'inde nozzle footprint ve gecikme ölçülür.
- Gerçek kimyasal denemede 7/14 gün weed knockdown, crop injury, kullanılan
  herbisit ve verim karşılaştırılır.

## P0 uygulama sırası

1. Geçici ana PoC `d_min=20 mm`, stretch `10–20 mm`; gerçek nozul footprint,
   crop mesafesi ve hedef hızla kalıcı sözleşmeyi dondur.
2. **Tamamlandı:** 126-kare intentional-overfit + full-res mask-loss hedef
   kapasite kapısı `%99,68` F1 ile geçti.
3. **Tamamlandı ve reddedildi:** agresif target-only ve basit 1:1 replay,
   ortak testte base F1/crop safety'yi iyileştirmedi.
4. Kamera GSD/FOV/exposure hesabını yap ve iki rig kur: mevcut kontrol ile
   global-shutter + yüksek çözünürlük + LED/strobe challenger.
5. Aynı 300–500 işaretli bitkide paired optik deneyi yap.
6. En iyi rig ile session-ayrı instance-mask + track-ID pilotu topla.
7. Crop-hard-negative target fine-tune, native-resolution ve temporal A/B'yi
   sırayla çalıştır.
8. Yalnız offline alt güven sınırı kapıları geçerse fiziksel su/UV boya ve
   ardından sınırlı herbisit denemesine geç.

Bugünkü dürüst durum: segmentasyon doğru temel; model aynı hedef-benzeri
görüntülerde `%99,68` F1 kapasite gösterdi, fakat farklı parsellerde en iyi
post-hoc action P/R/F1 `%92,02/%77,44/%84,10` ve crop hit `%2,85`tir.
Dolayısıyla `%95` saha genellemesi kanıtlanmadı. Rakipler bu seviyeye yalnız
model değiştirerek değil, görüntüleme hacmini kontrol edip çoklu yakın kamera,
ışık, tracking, aktüatör kalibrasyonu ve büyük hedef-domain veri döngüsüyle
yaklaşıyor.
