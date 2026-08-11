# Spot-spray deploy sözleşmesi v1

> **Güncel satın alma ve kurulum baseline'ı:** Bu V1 mimari niyeti korur,
> fakat kamera/lens/FOV/çalışma mesafesi, tek-kamera 15 Hz hesap sınırı,
> hood/ışık/BOM ve A–F fiziksel kabul kapıları
> [`CONTROLLED_CAPTURE_OPTIMIZATION_V2.md`](CONTROLLED_CAPTURE_OPTIMIZATION_V2.md)
> ile sayısallaştırılmış ve V2 tarafından üstlenilmiştir.

## Karar

PoC için tek geniş outdoor kamera yerine tekrarlanabilir bir **kapalı görüş
modülü** kullanılacak:

```text
mat siyah başlık + esnek etek
        ↓ dış ışığı bastır
senkron, çok açılı diffuse LED strobe
        ↓
2048×2048 global-shutter RGB, 0,45–0,50 m FOV
        ↓ dört native karo; tam kareyi küçültme yok
instance segmentation + crop veto + 3/5 video onayı
        ↓
kalibre dünya koordinatında bir track / bir atış
```

Bu, modeli açık hava ışığının tamamını öğrenmeye zorlamak yerine
kameranın gördüğü dağılımı fiziksel olarak daraltır. Global shutter'ın
hızlı hareket için uygun, rolling shutter'ın ise hareketli nesnelerde
geometrik bozulma üretebildiği üretici dokümanında açıkça belirtilir
([Basler shutter dokümanı](https://docs.baslerweb.com/electronic-shutter-types)).
Tarla üzerinde kapalı canopy ve kontrollü LED kullanan daha eski bir gerçek
sistem de aynı mimari deseni saha hızında uygulamıştır
([Slaughter ve ark. sistemi](https://pmc.ncbi.nlm.nih.gov/articles/PMC7013443/)).

Bu yaklaşım yalnız laboratuvar varsayımı değildir. Güncel ARA 620 ürün sayfası
gündüz/gece çalışmayı ve drift'i azaltan alt siyah koruyucu örtüyü açıkça
belirtir; vision tarafında RGB+3D kamera modülleri kullanır
([Ecorobotix ARA 620](https://ecorobotix.com/crop-care/ara-620-uhp-sprayer/)).
Verdant da yüksek çözünürlüklü görüntü, spatial tracking ve hareketi önden
tahmin eden aimable nozul mimarisini tarif eder
([Verdant FAQ](https://www.verdantrobotics.com/faqs)). Bunlar bizim başarı
rakamımızı kanıtlamaz; fakat **kapalı/tekrarlanabilir görüntüleme + temporal
konumlama** kararının ticari sistemlerle aynı yönde olduğunu gösterir.

## Dondurulan optik hedef

- Ham raster: `2048×2048` renkli global shutter.
- Yer FOV'u: en fazla `0,50×0,50 m`; tercihen `0,45–0,50 m`.
- GSD: `0,244 mm/px` veya daha iyi.
- `10 mm` weed: yaklaşık `41 px`; `20 mm` weed: yaklaşık `82 px`.
- Çalışma mesafesi: ilk bench için `0,55–0,65 m`.
- Lens: 1" sensörü kapsayan, düşük distorsiyonlu C-mount `12,5–16 mm`
  aday aralığı. Son seçim katalog hesabıyla değil, dokuz bölgede ölçülen
  FOV, distorsiyon ve fokus/MTF ile yapılacak. Basler da lens seçiminin sensör,
  FOV ve çalışma mesafesi birlikte ele alınarak yapılmasını tarif eder
  ([lens seçim kılavuzu](https://www.baslerweb.com/en-us/learning/lens-selection/)).

Bugün satın alınabilir bir referans aday `Basler ace acA2040-90uc`:
`2048×2048`, renkli, global shutter, `90 FPS`, USB3, 1"/`11,26 mm`
kare sensör ve C-mount. Bu bir zorunlu marka kararı değildir; kısa pozda SNR
ve strobe bench'ini geçmeden satın alma kararı verilmez
([resmî teknik sayfa](https://www.baslerweb.com/en/shop/aca2040-90uc/)).

## Hız, pozlama ve hesap

Hareket bulanıklığı:

```text
blur_px = hız_mm_s × exposure_s / GSD_mm_px
```

`0,75 px` bulanıklık bütçesiyle:

| Araç hızı | En uzun poz |
|---:|---:|
| `0,5 m/s` | `366 µs` |
| `1,0 m/s` | `183 µs` |

PoC `0,5 m/s` ile başlar; `1,0 m/s` son kontrollü hız gate'idir. Kamera,
strobe ve encoder aynı hardware trigger zaman tabanında olmalıdır. Sabit
pozlama, gain, white balance, fokus ve diyafram kullanılır.

RTX 3090 üzerindeki gerçek segmentasyon checkpoint'i, belleğe önceden
yüklenmiş dört gerçek `1024` karede ön-işleme + forward + NMS + maske +
CPU sonuç dönüşü dâhil, dört karoyu tek batch'te ortalama `33,87 ms`, p95
`34,34 ms` işledi. Bu yaklaşık `29,52` tam modül FPS'dir. `64 px` halo
compute proxy'si girdiyi `1152`ye çıkarınca ortalama `46,06 ms`, p95
`52,68 ms` ve `21,71` modül FPS ölçüldü. Kamera aktarımı, tracking ve
aktüatör iki sayıya da dâhil değildir; bu yüzden ilk uçtan-uca PoC `15 FPS`
ile başlar, `20 FPS` optimizasyon sonrası gate'tir.

Karo sınırında bitkiyi kesmemek için dört `1024` core karoya ham komşu
pikselden halo eklenecek; tahmin core'a kırpılıp dünya koordinatında
birleştirilecek. `64 px` halo latency gate'ini çıplak model düzeyinde geçti;
seam-accuracy ve uçtan-uca `15 FPS` gate'leri hâlâ fiziksel kamera akışında
geçilmelidir. Benchmark'taki reflect padding yalnız hesap boyutu proxy'sidir;
üretimde halo komşu ham sensör pikselinden gelir.

## Işık ve başlık

- Altı esnek etek/labirentli, içi mat siyah kapalı başlık.
- Kameranın çevresinde simetrik ve diffuse geniş spektrum beyaz LED.
- Sürekli aydınlatma yerine kamera tetikli strobe; pulse pozlamadan uzun değil.
- Strobe kapalı/açık ortalama luma oranı bench'te `≤0,10`.
- Wet-leaf/toprak glare kalırsa source ve lens çapraz polarize A/B; polarizer
  ışık kaybettirdiği için varsayılan değil. Çapraz polarizasyonun specular
  glare/hotspot azaltma kullanımı optik üreticisi tarafından da tarif edilir
  ([Edmund Optics](https://www.edmundoptics.com/knowledge-center/application-notes/imaging/machine-vision-filter-technology/)).
- RGB ile başlanır. Kontrollü RGB paired bench'te crop/weed ayrımı yine
  yetersiz kalırsa NIR/red-edge challenger açılır.

Strobe/overdrive'ın kısa pozlamaya ve hareketi dondurmaya hizmet ettiği
makine-görüsü aydınlatma kaynaklarında da belirtilir
([Smart Vision Lights](https://smartvisionlights.com/resources/lighting-basics-resources/machine-vision-lighting-technology/)).

## Model ve aksiyon

Segmentasyon temel olmaya devam eder. Weed maskesinin en derin iç noktası
sprey adayıdır; crop maskesi fiziksel safety veto'dur. Her instance zemin
düzlemine projekte edilir, `3/5` görüşte onaylanır ve her track en fazla bir
kez ateşlenir. Sınırda kesik instance tam görülene veya cross-tile/video
birleşimi tamamlanana kadar `abstain` olur.

No-fire mesafesi henüz sayı değildir:

```text
spray footprint yarıçapı + toplam registration/latency hatasının p95'i
```

Bu iki fiziksel değer su-duyarlı kâğıt/fluorescent dye bench'i olmadan
uydurulmayacak.

## Gerçek veri toplamadan önce ve sonra gate

Veri toplamadan önce rig şunları geçmeli:

1. Dokuz görüntü bölgesinde `10 mm ≥41 px`, fokus ve distorsiyon kontrolü.
2. `0,5` ve `1,0 m/s` hareketli target'ta `≤0,75 px` blur.
3. Strobe kapalı/açık luma oranı, clipping ve uniformity kaydı.
4. Kamera–encoder zamanı ve zemin homography kalibrasyonu.
5. Nozzle footprint, latency ve p95 atış hatası fiziksel ölçümü.

Gerçek model için en az 3 tarla / 4 session gerekir. Split birimi kare değil
`field + session + video track`tir. Ana etiket crop/weed instance maskesi ve
track ID'dir; stem/meristem keypoint lazer/mekanik fazına ertelenir.

Offline ateşleme GO gate'i, önceden dondurulmuş `≥20 mm, ≥%70 görünür`
weed-track paydasında:

- precision `≥0,98`;
- recall `≥0,95`;
- F1 `≥0,965`;
- crop-hit `≤0,005` ve üst güven sınırı ayrı rapor;
- duplicate shot `≤0,01`;
- her tarla ve worst-field ayrı rapor;
- sentetik skorun gerçek GO kararındaki ağırlığı `0`.

Bu gate geçse bile fiziksel deposition/kill ve crop injury deneyi geçmeden
kimyasal ateşleme yapılmaz. Tam makine-okunur sözleşme:
[`configs/deploy/spot_spray_poc_v1.yaml`](../configs/deploy/spot_spray_poc_v1.yaml).
