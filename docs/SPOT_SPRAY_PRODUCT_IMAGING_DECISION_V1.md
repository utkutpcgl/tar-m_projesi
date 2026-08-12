# Spot-spray ürün görüntüleme kararı V1

Durum: **PRE_REAL — donanım proof kararı donduruldu, fiziksel A–E henüz
ölçülmedi.**

Karar tarihi: **2026-08-12**

Makine-okunur karar:
[`spot_spray_product_imaging_decision_v1.yaml`](../configs/deploy/spot_spray_product_imaging_decision_v1.yaml).
Dayanak planner kaydı:
[`part-spot-spray-product-imaging-value-decision.md`](plans/part-spot-spray-product-imaging-value-decision.md).

## Yönetici özeti

Fiyat/performansı en iyi ilk adım, daha pahalı veya daha çok kamera değil;
**bir adet kapalı ve sabit aydınlatmalı Basler PRO proof modülünü fiziksel
A–E'den geçirmektir.** Mevcut mimari; `20 mm` ve üzeri, yeterince görünür
weed track'lerini ilk müdahale-uygun sınıf olarak ele alır. `10 mm`, optik
kalite tanığıdır; bugün bir ürün vaadi değildir.

| Karar | Bugün seçilen | Neden |
|---|---|---|
| Kamera | 1× Basler `a2A2464-77ucPRO` | Global shutter, trigger, haricî `12–24 VDC`; BAS tasarrufu yalnız `90 USD` |
| Lens | Basler `C23-0824-5M-P`, `8,06 mm`, `f/5,6` | Mevcut sensör/FOV/GSD kontratına bağlı ve kilitlenebilir |
| Çözünürlük | Native merkez `2048×2048`; resize yok | En kötü kabul GSD'sinde `20 mm ≥82 px`, `10 mm ≥41 px` |
| FOV / mesafe | `474–484 mm`; ayarlı `520–590 mm` WD | Lens birimi toleransını katalog varsayımıyla değil ölçümle kapatır |
| Pozlama / hız | `170 µs`, hardware trigger, `15 Hz`, `0–1 m/s` | Teorik blur `<0,75 px`; mevcut RTX 3090'da kanıtlı tek compute baseline |
| Hood | Min. `600×600 mm`, mat siyah, çift etek, labirent, eğik AR pencere | Güneş/gölgeyi bastırır; pencere takılıyken kalibre edilir |
| Işık | Dört simetrik diffuse LED quadrant, `150–170 µs` strobe | Kısa pozlamada SNR ve tekrarlanabilir renk; exact akım bench'te bulunur |
| Kamera sayısı | Proof'ta 1 | `≥444,375 mm` güvenli swath; ikinci kamera mevcut RTX'te kanıtlanmadı |

Bu, **nihai saha ürününün ideal olduğu iddiası değildir.** Bir adet
satın alınabilir mimari hipotezini minimum harcamayla çürütme planıdır.

## Neyi gerçekten araştırdık?

### Literatürde tekrarlanan başarılı desen

- Robotti tabanlı plant-specific sprayer, `2048×1536` çözünürlüklü dört
  kamerayı `0,91×2,80×1,05 m` kutu, siyah kauçuk perdeler ve diffuse
  `6500 K` LED altında kullandı; aynı bitkiyi sürüş yönünde üç kereye
  kadar gördü. Bu, kapalı görüş + aktif ışık + temporal tekrar
  mimarimizi doğrudan destekler
  ([hakemli çalışma](https://www.mdpi.com/1424-8220/20/24/7262)).
- AgBot II, aşağı bakan `1,3 MP` global-shutter kamerayı capture ile
  senkron darbeli aydınlatmayla kullandı. Bu, megapikselden önce shutter ve
  kontrollü ışığın önemini destekler
  ([kaynak](https://www.mdpi.com/2077-0472/13/2/413)).
- 2023 micro-jet sistemi `120×180 mm` görüntü alanını `80 ms` içinde
  işleyip `3,2 km/h` hızda kapalı deneyde yabancı otların `%98`ini doğru
  püskürttü. Ancak crop signalling ile problemi kolaylaştırdı ve sonuç
  indoor'dur; bizim saha F1'imiz değildir
  ([hakemli çalışma](https://www.sciencedirect.com/science/article/pii/S1537511023000375)).

Ortak sonuç: **yakın kamera, dar ve kalibre FOV, kısa pozlama/global
shutter, aktif ışık, dış ışığı bastıran hacim ve aynı hedefin temporal
tekrarı.** Tek başına daha yüksek megapiksel bu zincirin yerine geçmiyor.

### Piyasadaki en güçlü sistemlerden çıkan ders

Detaylı sekiz-sistem tablosu ve metrik semantiği
[`SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md`](SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md#rakipler-gerçekten-ne-yapıyor)
içindedir. Donanım kararı için önemli ortak noktalar:

- Deere See & Spray, geniş bom için tek dev kamera yerine `36` kamera ve
  edge compute kullanıyor; resmî sayfa `15 mph` ve `2.100 ft²` taramayı
  bildiriyor ([Deere](https://www.deere.com/en-us/our-company/technology-and-innovation/sense-and-act)).
- Carbon LaserWeeder G2 600, `12` modülde `36` yüksek çözünürlük kamera
  ve `240` yüksek yoğunluklu LED kullanıyor. Bu, genişliği tam optik/compute
  bay'leri tekrarlayarak büyütme kararını destekler
  ([Carbon](https://carbonrobotics.com/laserweeder-g2-600)).
- Ecorobotix ARA 620, altı RGB+3D vision modülü ile `156` nozulu ve
  `6×6 cm` spray footprint'i birlikte veriyor
  ([Ecorobotix](https://ecorobotix.com/crop-care/ara-620-uhp-sprayer/)).
  Recognition boyutu ile fiziksel püskürtme footprint'inin ayrı olması,
  yalnız “çok küçük otu görüyor” iddiasıyla kamera seçmememiz gerektiğini
  gösterir.
- Greeneye, ONE SMART SPRAY, Bilberry, WEED-IT ve Verdant da aktif ışık,
  modüler yakın kamera, tracking veya hızlı nozzle/aiming desenini
  destekliyor. Fakat yayımlanan `recall`, `application accuracy`, `hit-rate`,
  `placement` ve `kill-rate` aynı metrik değildir.

Piyasa ve literatür taraması, **proof mimarisini seçmek için yeterli;
nihai sensör modelini ve ürün F1'ini ilan etmek için yetersizdir.** Hiçbir
kamu kaynağı aynı testte minimum weed boyutu + recognition P/R/F1 + crop hit
+ fiziksel kill oranını eksiksiz vermiyor.

## Neden bu kamera ve neden yalnız bir tane?

### Çözünürlük kararı hedef boyuttan türetiliyor

En kötü kabul GSD'si `0,243902 mm/px`:

```text
20 mm / 0,243902 mm/px = 82 px
10 mm / 0,243902 mm/px = 41 px
5 mm  / 0,243902 mm/px ≈ 20,5 px
```

Bu nedenle `20 mm` ilk servis sınıfında mevcut 5 MP sensör, native
`2048²` ROI ve yaklaşık `480 mm` FOV rasyonel bir fiyat/performans
noktasıdır. `5 mm` müdahale hedeflenirse mevcut karar kullanılmaz; daha dar
FOV, daha yüksek gerçek sensör çözünürlüğü veya daha fazla bay için yeni
optik+compute kontratı gerekir.

### PRO primi rasyonel

2026-08-11 kamu fiyatlarında kamera `709 USD`, lens `136 USD`dir. Tam proof
modülü mevcut RTX 3090 yeniden kullanılarak vergi/kargo hariç
`3.115–6.545 USD`, `%15` contingency ile `3.582–7.527 USD` budgetary
aralıktadır. Bunlar landed quote değildir.

BAS gövde yalnız `90 USD` ucuzdur; bu, alt modül toplamının yaklaşık
`%2,9`udur. Bunun karşılığında kamera gücü USB data hattına bağlanır.
Proof için PRO'nun ayrı `12–24 VDC` yolu daha değerlidir. FLIR challenger
aynı piksel geometrisinde, challenger lehine en düşük kamu fiyatıyla bile
PRO gövdenin `1,84×` fiyatıdır; kanıtlanmış ek ürün değeri olmadan
satın alınmaz.

### Kamera sayısı swath kararıdır

Bir kameranın dış `64 px` no-fire halkası sonrası minimum güvenli swath'ı
`444,375 mm`dir. Bu ilk proof ve yaklaşık yarım metre sınıfı bir robot
için yeterlidir. İkinci kamera yalnız dört koşul birlikte sağlanırsa alınır:

1. Tek bay physical A–E geçer.
2. Gerçek ürün swath ihtiyacı `444,375 mm`yi aşar.
3. Çok-bay USB/transport ve end-to-end compute ayrı geçer.
4. Her bay ile overlap şeridi optik, ışık ve hareket kapılarını geçer.

Mevcut RTX 3090 ölçümünde bir kamera/15 Hz compute-only geçerken
bir kamera/20 Hz ve iki kamera/12–15 Hz conservative p95 hesabı geçmiyor.
Bu nedenle ikinci kamerayı erken almak fiyat/performansı kötüleştirir.

## Hood ve aydınlatma kararı

Proof muhafazası:

- en az `600×600 mm` mat siyah rijit üst/yan kabuk;
- doğrudan yer–gökyüzü görüş hattı yok;
- iki kat `100–150 mm` esnek EPDM/kaplı kumaş etek;
- `30–50 mm` şaşırtmalı bindirme ve `0–20 mm` çalışma açıklığı;
- en az `50 mm` iki kademeli labirent ve geriye bakan contalı S-kablo yolu;
- takılıyken kalibre edilen, temizlenebilir `2–3 mm` AR cam ve `3–5°` tilt;
- breakaway/no-entanglement, hood-open ve overtemperature fail-closed.

Dört diffuse beyaz LED bölgesi lens etrafında simetriktir. Hedef
`4500–5500 K`, `CRI≥90`, pulse `150–170 µs`dir. `0–10 A` ve `240 W`
yalnız elektrik zarfıdır; setpoint değildir. Takılı hood içinde dokuz
bölgenin tamamında ambient/strobe `≤0,10`, uniformity `≥0,75`, SNR
`≥20 dB`, clipping, güç ve iki saat termal kapılarını aynı anda geçen en
düşük akım seçilir.

Cross-polarization varsayılan kapalıdır. Yalnız eşlenmiş ıslak
yaprak/toprak A/B'sinde glare alanını `≥%50` azaltıp diğer tüm D
kapılarını korursa açılır.

## Rugged ve IP konusunda dürüst sınır

Seçilen çıplak Basler kameranın resmî koruma sınıfı **IP30**dur
([Basler teknik dokümanı](https://docs.baslerweb.com/a2a2464-77ucpro)).
Tanımlanan hood; controlled proof için işlevsel rugged muhafazadır, IP
sertifikası değildir. Yağmur, basınçlı yıkama, yoğun toz, taş darbesi,
şok veya titreşim production gereksinimi olursa:

1. ayrı environmental contract yazılır;
2. IP65/67 seviyesinde doğrulanmış kapalı muhafaza veya rugged kamera
   challenger seçilir;
3. optik yol etkilenirse C–E, kamera/power/transport değişirse A–E tekrar
   edilir.

Bugün kesin bir IP67 kamera SKU'su seçmemek bilinçli karardır: servis boyutu,
swath ve fiziksel baseline arıza modu ölçülmeden daha pahalı bir rugged
sensörün ürün değeri kanıtlanmış değildir.

## Frozen, provisional ve kapalı kararlar

### Proof için frozen

- 1× PRO + C23, external power, dedicated USB3 root;
- native `2048²`, `474–484 mm`, `520–590 mm`, `f/5,6`, `170 µs`, `15 Hz`;
- `20 mm` ilk eligible servis sınıfı; `10 mm` yalnız optik witness;
- dört bölgeli diffuse strobe ve kapalı çift-etekli hood;
- 27/27 optik hücre ve mevcut A–E fail-closed eşikleri.

### Fiziksel bench'te belirlenecek

- exact LED parçası, diffuser, akım, lux ve optik enerji;
- exact working distance, gain ve manual white balance;
- heatsink/fan, imalat malzemesi ve kalınlık;
- landed fiyat ve teslim süresi.

### Challenger kanıtına kadar kapalı

- 20 Hz, ikinci kamera ve tek RTX 3090'da multi-camera;
- BAS veya FLIR satın alma;
- daima açık polarization;
- `20 mm` altı müdahale ve daha geniş FOV;
- production quantity ve certified IP/vibration iddiası;
- chemical fire.

## Satın alma sınırı

Bugün **satın alma yapılmış veya yetkilendirilmiş değildir.** Sonraki
adım, 2026-08-11 sonrası tarihli landed quote ve owner onayıdır. İlk paket
en fazla bir PRO/C23 proof seti, tek bay kablo/power/trigger/light prototipi,
ayarlı hood ve ölçüm elemanlarıdır. İkinci kamera, BAS, FLIR, ikinci
accelerator ve production quantity bu pakette yoktur.

## En az maliyetle kanıt sırası

1. **A — kimlik/quote:** exact order, power, cable, host/USB root ve güncel
   teklif hash-bound receipt'e girer.
2. **B — transport/termal:** 20 Hz'te 10.000 trigger, sıfır missing/duplicate,
   timing, droop ve `5–40 °C` iki saatlik zarf geçer.
3. **C — optik:** pencere takılı, `0/55/110 mm` düzlemlerde 27/27 hücre
   GSD, `41/82 px`, MTF ve reprojection geçer.
4. **D — hood/ışık:** en kötü ölçülmüş ambient, dokuz bölge, SNR,
   clipping, güç, termal ve ıslak glare geçer.
5. **E — hareket/E2E:** `0,5/1,0 m/s`, blur `≤0,75 px`, en az beş gözlem,
   tek kamera `15 Hz` p95 `≤66,6667 ms`, sıfır miss/drop geçer.

V2 compute ölçümü tarihsel aynı-mimari checkpoint
`0b30e143…` için bir proxy'dir. Güncel pre-real foundation `3aba4b19…` ve
sonraki target-rig checkpoint için Stage E tekrar edilir veya daha yavaş
olmadığı hash-bound ölçümle kanıtlanır.

Yalnız A–E'nin tamamı physical receipt ile geçerse durum
`FROZEN_FOR_CONTROLLED_CAPTURE` olur. Bu, product GO, field GO veya chemical
fire değildir. A–F ayrı olarak yalnız nonchemical dry-marker'a aday olabilir.

## Ne zaman yeniden tasarlarız?

Mevcut mimari zorlanmaz; aşağıdakilerden biri olursa yeniden planlanır:

- PRO/C23 tedariki proof takvimini bloke eder;
- hedef FOV/WD veya 27 hücre optik kapısı kalıcı geçmez;
- hiçbir ışık setpoint'i tüm D kapılarını aynı anda geçmez;
- `1 m/s`, `170 µs` blur veya tek kamera 15 Hz E2E geçmez;
- hız `>1 m/s`, güvenli swath `>444,375 mm` veya servis boyutu `<20 mm`
  olur;
- `5–40 °C` dışı ya da certified ingress/washdown/dust/shock/vibration
  gerekir;
- nozul footprint/crop-safety sözleşmesi `20 mm` sınıfını değiştirir.

## Bugünün net sonucu

Araştırma, **tek PRO kamera + native 5 MP detay + kapalı diffuse-strobe
modülünün en iyi ilk fiyat/performans hipotezi olduğunu** destekliyor.
Araştırma, nihai production kamerayı veya kamera sayısını tek başına
kanıtlamıyor. Bundan sonra masa başında kamera eklemek yerine bir exact
modülü A–E'den geçirmek en yüksek değerli adımdır.
