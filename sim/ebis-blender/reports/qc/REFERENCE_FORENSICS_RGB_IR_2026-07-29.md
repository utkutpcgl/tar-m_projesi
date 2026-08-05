# EBİS RGB + IR referans adli incelemesi

**Tarih:** 2026-07-29
**Hedef sahne:** `REF-65218_IVEDIK_LED_TARGET` varsayımıyla Blender EBİS
**İnceleme amacı:** Sahnenin değişmez fiziksel parçalarını, gerçek koşullarda
değişen etkenleri ve simülasyon–gerçek farklarını birbirinden ayırmak; yalnız
kanıtla savunulabilen parametreleri generator'a taşımak.

## Yönetici sonucu

Arşivdeki aynı makine kareleri, hedef EBİS haznesinin **tek renk gri bir kutu
olmadığını** gösteriyor. Hedef profil gri hammertone arka/sol gövde, kobalt
mavi sağ duvar ve ön aperture; iki büyük dairesel çelik tabla; contalı ve dört
vidalı arka servis kapağı; üst tabla alt kotunda arka–sol–sağ duvarı izleyen
ince, üç parçalı opal LED; solda açılan çerçeveli/camlı kapı ve iki farklı
fisheye bakıştan oluşuyor. Bunlar domain randomization yapılacak öğeler değil,
aynı makine için sabitlenmesi gereken topolojidir.

Gerçek kareler düzenli küp ve silindir numuneleri, yüzey kusuru/nem, kırıntı,
kapı açısı, kişi/el, kâğıt form ve RFID yerleşiminde güçlü değişkenlik
gösteriyor. Bu değişkenlerin generator'da seed'li ve sınırlı dağılımlarla
üretilmesi uygundur. Buna karşılık farklı `REF-*` makinelerin renk, kapak,
kamera ve LED parçalarını tek bir hibrit makinede birleştirmek uygun değildir.

İnceleme Blender sahnesindeki ana geometri, materyal, ışık, kâğıt/RFID
örtülmesi ve kamera ayrımını iyileştirmiştir. Son `v1.7.3` görsel turu,
1080p’de belirginleşen periyodik tabla halkasını, iri yapışık agrega
geometrisini ve aşırı büyük yan servis kapaklarını ayrıca kaldırmıştır.
**Fotometrik dijital ikiz
kalibrasyonu veya YOLO başarım artışı kanıtlanmış değildir.** Model faydası
ancak sabit gerçek test setli ablation ile ölçülebilir.

## Kanıt sınıfları ve kapsam

Bu raporda iddialar aşağıdaki sınıflardan biriyle sınırlandırılmıştır:

- **V — görsel kanıt:** Kaynak karelerin tam çözünürlükte ve zamansal contact
  sheet'lerde doğrudan incelenmesi.
- **A — anotasyon/envanter kanıtı:** Dosya ve YOLO label'larının programatik
  sayımı veya bbox istatistiği.
- **C — uygulama kanıtı:** Rapor anındaki canonical config/generator durumu.
- **H — hipotez:** Fotoğraftan yapılan ve ölçüm/CAD/kalibrasyonla doğrulanması
  gereken çıkarım.

| Küme | Arşiv envanteri | Benzersiz görsel inceleme örneklemi | Tarih/kamera kapsamı |
| --- | ---: | ---: | --- |
| LED RGB | 2.960 PNG | 52 | 2026-01-16 ve 2026-01-21; cam-10 ve cam-11 |
| `REF-*` IR/gri ton | 17.081 PNG | 33 | 2024-12-02–2025-02-21; 18 `REF-*` klasörü |
| **Toplam** | **20.041 PNG** | **85** | erken/orta/geç ve iki kamera ailesi |

Envanter sayısı tüm dosyaları, 85 sayısı ise görsel olarak incelenen benzersiz
kareleri ifade eder; 20.041 karenin tamamı tek tek görülmüş gibi
yorumlanmamalıdır. Örnekleme, aynı videonun art arda neredeyse aynı karelerine
yoğunlaşmamak için erken/orta/geç zamanlardan ve farklı task/makine
gruplarından katmanlı yapılmıştır. Contact sheet'ler birden fazla geçişte
geometri, materyal/ışık, kamera ve RFID/kâğıt açısından ayrı ayrı
karşılaştırılmıştır.

İncelenen sheet'ler:

- [LED RGB — altı task, erken/orta/geç](reference_forensics/led_cam10_cam11_batches.png)
- [LED RGB — 2026-01-16 zamansal örnek](reference_forensics/led_160126_temporal_18.png)
- [REF cam-10 — erken/orta/geç](reference_forensics/ref_cam10_early_mid_late.png)
- [REF cam-11 A — erken/orta/geç](reference_forensics/ref_cam11_a_early_mid_late.png)
- [REF cam-11 B — erken/orta/geç](reference_forensics/ref_cam11_b_early_mid_late.png)

## Ana kaynak yolları

Canonical gerçek LED kökü:

- [`260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli`](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli)

Kamera ve zamansal farklılığı gösteren kesin RGB örnekleri:

- [2026-01-16 LED RGB, erken kare](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/160126-ivedik-ledli-part-1/images/train/vlcsnap-2026-01-16-16h16m02s362.png)
- [cam-10 / task 10](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_10_dataset_2026_01_23_12_54_24_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-2_frame-00000.png)
- [cam-11 / task 11](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_11_dataset_2026_01_23_07_32_53_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-6_frame-00000.png)
- [cam-10 / task 13](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_13_dataset_2026_01_23_12_04_05_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-3_frame-00000.png)
- [cam-11 / task 14](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_14_dataset_2026_01_23_14_19_44_yolo_1.1__İVEDİK_2026-01-21_cam-11_batch-5_frame-00000.png)

Hedef profil ve çapraz-makine sınırını gösteren kesin IR örnekleri:

- [REF-65218 cam-10](../../../260312_EBIS_RFID_DATASET/REF-65218_CAM10/images/train/TİMKO_REF-65218_2025-02-21_cam-10-000000.png)
- [REF-65218 cam-11](../../../260312_EBIS_RFID_DATASET/REF-65218_CAM11/images/train/TİMKO_REF-65218_2025-02-21_cam-11-000000.png)
- [en erken tarih, başka makine: REF-65250 cam-11](../../../260312_EBIS_RFID_DATASET/REF-65250_CAM11/images/train/ELİZ_REF-65250_2024-12-02_cam-11_frame-000010.png)
- [orta dönem, başka makine: REF-65423 cam-11](../../../260312_EBIS_RFID_DATASET/REF-65423_CAM11/images/train/BTN_REF-65423_2025-01-16_cam-11_frame-000000.png)
- [geç dönem, başka makine: REF-65080 cam-10](../../../260312_EBIS_RFID_DATASET/REF-65080_CAM10/images/train/AYKAR_REF-65080_2025-01-27_cam-10_frame-000002.png)

İstatistik kaynakları:

- [Gerçek LED detection audit](real_led_detection_audit.md)
- [Makine-okunur gerçek/sentetik audit](led_v2_detection_domain_audit.json)
- [Canonical sahne config'i](../../configs/ebis_led_v2.json)
- [Instance-aware bbox/occlusion politikası](../../docs/BBOX_OCCLUSION_POLICY.md)

## Aynı makinede değişmez kabul edilen parçalar

### Hazne ve kapı

**V:** Hedef karelerde arka ve sol sac gri hammertone/pebbled, sağ iç duvar ve
ön aperture kobalt mavidir. Ton küçük pozlama/beyaz ayarı farkları gösterse de
panel kimliği yer değiştirmez. Solda workshop'a açılan aperture bulunur; kapı
çerçeve, cam, conta, menteşe ve kol ile fiziksel bir örtücüdür.

**V/H:** Kapı çoğunlukla yaklaşık 78–108° tam açık görünür; daha seyrek
yaklaşık 30–72° kısmi açıklık görülür. Dereceler görüntüden yaklaşık fit'tir,
encoder ölçümü değildir. Cam ve çerçeve özellikle cam-11'de görüntünün bir
kısmını gerçekten örtebilir; post-process maske olarak eklenmemelidir.

### Tabla ve numune ilişkisi

**V:** Beton, alt ve üstte iki büyük dairesel metal tabla arasında dikey
sıkıştırılır. Tablalar numuneden belirgin biçimde geniştir ve yansımaları
tamamen kusursuz değildir; kullanılmış çelik, silme/yönlü iz, toz ve lokal ton
değişimi vardır. “Üstte küçük hedef + bullseye” görünümü gözlenmemiştir.

**C/H:** Mevcut fotoğraf-fit 0,40 m tabla çapı ve 0,18 m küp kenarı, yaklaşık
2,22:1 oran verir. Bu oran görsel ilişkiyi korur fakat CAD/cetvelli ölçüm
olmadan kesin fiziksel ölçü sayılmaz.

### Arka servis/kamera grubu

**V:** Yuvarlatılmış dikdörtgen servis kapağı; ayrı dar gri plaka; çevresel
conta ve dört köşe vidası zamansal olarak sabittir. İncelemedeki görsel fit,
yaklaşık 33–40 mm dış bezel, 20–26 mm lens açıklığı, 16–20 mm ikincil port ve
yaklaşık 32×16 mm koyu slotu destekler. Bunlar pikselden tahmin edilen
ölçeklerdir; teknik resim değildir.

### LED topolojisi

**V:** Işık kaynağı büyük beyaz tavan paneli değildir. Üst tabla alt kotuna
yakın, arka duvar ve iki yan duvar boyunca ilerleyen ince opal difüzörlü
dikdörtgen bir U-kanaldır. Her iki yan segment de boydan boya devam eder.
Tabla, kameraya göre kanalın önemli bölümünü fiziksel olarak gizler. Kanal
lokal clipping/halation üretse de beton–üst tabla temasında ve hazne
köşelerinde tamamen siyah gölge bırakmaz.

## Aynı makinede kontrollü değişmesi gerekenler

| Değişken | Gerçek kanıt | Generator kararı |
| --- | --- | --- |
| Numune şekli | 1.233 küp `%41,9`; 1.712 silindir `%58,1` (**A**) | `0,42 / 0,58` seed'li seçim |
| Numune yüzeyi | Kalıp yüzü, küçük gözenek, agrega, nem ve kenar aşınması değişiyor (**V**) | Çok ölçekli roughness/ton; sınırlı hasar/nem |
| Kapı açısı | Tam açık baskın, kısmi açık azınlık (**V/H**) | `%82` 78–108°; `%18` 28–68° |
| Işık | LED tonu/pozlama ve açık kapı fill'i değişiyor (**V**) | Dört sınırlı profil; sabit LED topolojisi |
| Kamera | Montaj ve lens ailesi sabit, küçük kadraj/roll farkı var (**V**) | Kamera başına küçük mount/target/lens jitter |
| Kırıntı | Miktar ve konum operasyon boyunca değişiyor (**V**) | Küçük/yassı, numuneden ayrı non-target parçalar |
| Kâğıt | Küp yüzlerinde form/etiket, bant ve baskı görülebiliyor (**V**) | Küp yüzünde 0/1/2 fiziksel non-target kâğıt |
| RFID | Yüzeyde, tabla aralığında, kâğıt altında veya kadraj dışında görülebiliyor (**V/A**) | Fiziksel instance, z-order sonrası görünür maske |
| İnsan/el | Staged LED setinde çok yaygın (**V/A**) | Ayrı ablation/domain konusu; makine geometrisi sanılmamalı |

## Kamera ve ışık karşılaştırması

### Kamera kimliği

- `cam-10 / Kamera 01 = camera_angled`: Hazneye daha doğrudan, karşı
  taraftan bakar; kapı çoğunlukla kenarda veya FOV dışındadır.
- `cam-11 / Kamera 02 = camera_door`: Sol açıklık ve kapının küçük bir
  bölümünü tutan daha çapraz bakıştır.

Bu eşleme dosya adı, overlay ve kadrajın birlikte incelenmesine dayanır.
Kameralar tek ortak pose'un jitter edilmiş hâli olarak üretilmemelidir.

### Gerçek bbox kadraj medyanları

Aşağıdaki `(cx, cy, w, h)` medyanları 2.945 gerçek concrete anotasyonundan
gelir; yalnız görsel kadraj hedefidir:

| Kamera / şekil | N | Gerçek medyan YOLO bbox |
| --- | ---: | --- |
| camera_angled / cube | 401 | `(0,500; 0,574; 0,496; 0,852)` |
| camera_angled / cylinder | 445 | `(0,502; 0,594; 0,255; 0,809)` |
| camera_door / cube | 451 | `(0,511; 0,575; 0,487; 0,849)` |
| camera_door / cylinder | 455 | `(0,511; 0,573; 0,267; 0,854)` |

Nihai `v1.7.3` 32-kare sentetik framing gate’inde bu dört slice'ın en
büyük mutlak medyan farkları sırasıyla `0,02978`, `0,02453`, `0,02322`,
`0,02741` oldu; her hücre `N=7–9` örnekle tanımlı `±0,03` görsel kapıyı
geçti. Bu sonuç fiziksel küp ölçüsünü bozmak yerine bağımsız detection
stilleri için kamera-koşullu bounded yaw ve ayrı kamera mesafe fit’ini
destekler. Senkron iki-kamera üretimine uygulanmaz ve kalibre intrinsics
kanıtı değildir.

### Temsilî ROI yoğunluk özeti

8-bit RGB'de temsilî hazne ROI'ları için p5 / p50 / p95:

| Kamera | Gerçek LED | Önceki sentetik | Okuma |
| --- | --- | --- | --- |
| cam-10 / camera_angled | `42 / 123,6 / 244` | `38,8 / 119,2 / 235,3` | Global ton yakın; lokal LED clipping/halation yetersiz |
| cam-11 / camera_door | `45,7 / 137,7 / 205,2` | `19,4 / 156,1 / 230,3` | Gölge fazla koyu, orta/üst ton fazla parlak |

Bu tablo, forensik örneklem ROI'ları ile önceki pilotun basit piksel
karşılaştırmasıdır. Tüm arşiv popülasyonunun dağılımı, sahne lineer ışık
ölçümü, lux değeri veya kamera response curve kalibrasyonu değildir.
Cam-11 için doğru yön; açıklık gölgesini fiziksel fill/bounce ile kaldırırken
merkez/sağ parlaklığını yaklaşık `0,2–0,4 stop` azaltmaktır. Son değerler,
aynı kare eşlemesi ve ölçülmüş kamera response'u olmadan “tam kalibre” kabul
edilmemelidir.

## Beton, kâğıt ve RFID bulguları

### Beton

**V:** Gerçek operasyon numunesi nizami küp veya silindirdir; procedurally
parçalanmış kaya kütlesi değildir. Yüzeyde birkaç ölçekte küçük gözenek,
kalıp izi, agrega ve lokal aşınma bulunur. Bazı silindirlerde daha düzgün ve
nispeten mumsu/yoğun kalıp yüzü görülür. Büyük, eşit aralıklı siyah
“boncuklar” veya aşırı kabarık displacement sentetik ipucu oluşturur.

Generator'ın düzenli ana silueti koruyup küçük kusurları shader/az sayıda
gömülü geometri ile vermesi doğru yaklaşımdır. Mould-face scan,
agrega-kırık-yüz ayrımı ve ölçülmüş nem/roughness hâlâ eksiktir.

### Kâğıt

Forensik task taraması kâğıt/form görülme oranını yaklaşık `%29–33`
aralığında destekler. Bu oran video kareleri birbirinden bağımsız saha
olayları olmadığı için gerçek operasyon prior'ı sayılmamalıdır. Kâğıt; kirli
beyaz/bej, baskı çizgili, bantlı ve küçük dönüklük gösterir. İlk güvenli
uygulama yalnız düz küp yüzüdür; silindir için yüzeye konforme segmented mesh
olmadan düz levha kullanmak fiziksel olarak yanlış bir cue üretir.

### RFID

Gerçek LED detection setinde 15.596 RFID bbox vardır; görüntü başına medyan
5, p95 14 ve en yüksek 19'dur. Dağılım, 1-tag kareler ile 7–19-tag staged
kuyruğu arasında belirgin biçimde bimodaldir. Bu nedenle `tag_count` değerleri
operasyon sıklığı sanılmamalı; yalnız açıkça adlandırılmış training
ablation'larında kullanılmalıdır.

RFID bbox–concrete bbox ilişkisi:

- `%36,6`: RFID bbox tamamen concrete bbox içinde;
- `%43,3`: kısmi kesişim;
- `%20,1`: concrete bbox dışında.

“Dışarıda” oranının önemli bölümü el/duvar/tabla üzerinde staged
yerleşimlerden gelir. Bunu doğrudan çalışma anındaki tag placement prior'ına
kopyalamak doğru değildir.

Kâğıt altındaki tag tamamen kaybolabilir veya yalnız ucu görünebilir.
İncelenen örnekler, görünür uç uzunluğu için yaklaşık `%15–55`, daha tipik
merkez için `%25–40` bandını destekler. Canonical simülasyon bandı,
ekstremi daraltarak `%15–50` seçer.

### Bbox/occlusion sözleşmesi

Kâğıt ve tabla gerçek geometri olarak RFID'nin önünde bulunur. Eğitim kutusu,
semantic sınıf-union maskesinden değil **her RFID instance'ının son görünür
maskesinden** üretilir:

- tam gizli RFID: YOLO satırı yok;
- `visibility ≥0,35` ve en büyük component oranı `≥0,65`: `standard`;
- `0,15≤visibility<0,35` ve component `≥0,45`: `hard_occlusion`;
- bunun altında görünür kalıntı: `exclude`;
- iki parçaya ayrılan tek tag: tek instance union bbox; fakat en büyük
  component eşiği kalite kapısıdır;
- fully hidden/outside-frame nesne, görünmeyen tam fiziksel boyutuyla
  kutulanmaz.

Piksel/alan alt eşikleri ve 640 model-input ölçeklemesi için source of truth
[BBOX_OCCLUSION_POLICY.md](../../docs/BBOX_OCCLUSION_POLICY.md)'dir.

## IR kanıtının doğru ve yanlış kullanımı

`REF-*` kareleri şu konularda değerlidir:

- tabla, hazne, kapak, vida, kamera yuvası ve aperture topolojisi;
- iki kameranın görüş ilişkisi;
- kapı/kişi/tabla/kâğıt kaynaklı örtülme örüntüsü;
- farklı zamanlarda hangi fiziksel parçaların sabit kaldığı;
- farklı makinelerin hibritleştirilmemesi gerektiği.

IR/gri ton kareleri şu konularda doğrudan RGB kalibrasyon kaynağı değildir:

- boya RGB/HSV rengi;
- PBR base color veya metallic değeri;
- visible-light roughness ve specular şiddeti;
- LED Kelvin, güç, kamera white balance veya exposure;
- siyah görünen bölgenin “ışık almıyor” olduğu sonucu.

IR aydınlatma, sensör spektral duyarlılığı, otomatik gain/exposure ve
malzemenin NIR yansıtması visible RGB'den farklıdır. Dolayısıyla IR'daki
parlaklık sırası RGB shader değerine kopyalanmamıştır; IR yalnız
geometri/topoloji/örtülme kanıtıdır.

## Gerçek–sentetik fark ve uygulama durumu

| Gerçek referansa göre fark | Etki | Durum / alınan karar |
| --- | --- | --- |
| Tüm duvarların aynı gri/mavi hibrit olması | Yanlış makine kimliği, kolay sentetik cue | **Uygulandı:** hedef profile özgü gri arka/sol + mavi sağ/aperture; zonlar bağımsız randomize edilmiyor |
| Büyük ışıklı panel veya eksik/kısa yan LED | Yanlış gölge ve yansıma topolojisi | **Uygulandı:** üst tabla kotunda ince üç segmentli opal U-kanal, iki yan tam uzunluk |
| Cam-11 açıklık gölgesinin siyaha çökmesi | Gerçek olmayan dinamik aralık | **Uygulandı:** kapı açısına bağlı fiziksel daylight/workshop fill, dünya ve tabla bounce; **ölçüm bekliyor:** eş kare ROI recalibration |
| Lokal LED bloom/halation'ın zayıf olması | Fazla temiz CG kenarı | **Ertelendi:** ölçüsüz compositor bloom/vignette yayınlanmadı; lens/response kalibrasyonundan sonra eklenmeli |
| Betonun kaya gibi düzensiz veya boncuk gözenekli olması | Hedef sınıf silueti ve doku hatası | **Uygulandı:** düzenli küp/silindir, daha küçük ve seyrek kusur, çok ölçekli roughness; orta hasarda iri protruding agrega kapalı; **ertelendi:** ölçülü surface scan |
| Tablaların temiz, koyu, bullseye veya periyodik halkalı olması | Endüstriyel kullanım izi eksikliği ve güçlü CG cue | **Uygulandı:** kullanılmış/machined steel varyasyonu, yapay merkezi hedef ve Wave-driven normal çıkarıldı; **ertelendi:** tabla CAD/normal/roughness scan |
| Kâğıt formun bulunmaması | Gerçek ana occluder eksikliği | **Uygulandı:** küpte kirli baskılı/bantlı fiziksel kâğıt ve linked RFID z-order; **ertelendi:** silindire konforme kâğıt |
| Tag'lerin yalnız tam açık ve yüzeyde olması | Kolay örnek bias'ı | **Uygulandı:** sample yüzü, tabla aralığı, kâğıt altı, tam/yarı örtülü fiziksel instance; operation prior hâlâ bilinmiyor |
| Kapının yanlış pivotta veya sabit 90° olması | Cam-11 occlusion ve fill hatası | **Uygulandı:** sol erişim aperture'üne bağlı camlı kapı ve iki modlu açı |
| Tek kamera pose'u | Cam-10/cam-11 domainlerinin karışması | **Uygulandı:** ayrı pose/exposure/lens-distortion profili; **ertelendi:** SKU + ChArUco intrinsics |
| Kamera/servis kapağının kaba veya yanlarda aşırı büyük proxy olması | Yakın planda belirgin kimlik hatası | **Uygulandı:** baskın arka conta/dört vida/servis kapağı korundu, yanlar kompakt port/lens stack’e indirildi; teknik ölçüm hâlâ gerekli |
| Workshop'un basit geometri olması | Açık kapıda oyuncak arka plan cue'su | **Geçici:** kontrollü proxy/defocus; **ertelendi:** lisanslı gerçek backplate veya ölçülü set |
| Farklı `REF-*` parçalarının karıştırılması | Var olmayan makine üretimi | **Yasaklandı:** cross-machine örnekler domain kıyasıdır, hedef profil asset kaynağı değildir |

## Seed'li ve sınırlı randomization sözleşmesi

### Asla rastgeleleştirilmemesi gerekenler

- hedef makine kimliği ve panel renk haritası;
- servis kapağı, conta, dört vida ve kamera portlarının topolojisi;
- iki dairesel tabla ve bunların numuneye göre temel oranı;
- LED'nin üç-segment U-kanal topolojisi ve üst tabla kotu;
- `cam-10 = camera_angled`, `cam-11 = camera_door` kimliği;
- cam/çerçeve/kâğıdın gerçek occluder olması;
- instance-aware görünür bbox kuralı.

### Canonical, kayıt altına alınmış kontrollü aralıklar

| Parametre | Dağılım/aralık | Sınırın gerekçesi |
| --- | --- | --- |
| Şekil | cube `0,42`, cylinder `0,58` | 2.945 concrete label dağılımı |
| Numune konum jitter | x `±14 mm`, y `±10 mm`; yaw `±6°` | Kadrajı bozmayan operasyon varyansı |
| Nem / hasar proxy | nem `0–0,34`; hasar `0,05–0,64`, düşük hasar ağırlıklı | Görsel çeşit; fiziksel dayanım parametresi değil |
| Kapı | `%82`: `78–108°`; `%18`: `28–68°` | Görsel tam/kısmi açık modları |
| LED enerji ölçeği | profile göre `0,88–1,10` | Gerçek pozlama/LED farkının dar bandı |
| LED CCT profili | 4300/5200/5700/6500 K; ağırlık `0,05/0,52/0,16/0,27` | Renk/ışık çeşitliliği; kalibre lux değil |
| Kapı fill profili | `0,42–0,68`, ayrıca gerçek kapı açısıyla çarpılır | Kısmi kapıda siyah çöküşü önleme |
| Lens | iki kamerada `2,77–2,83 mm` görsel fit | SKU bilinmediği için dar tutuldu |
| Mount jitter | konum eksen başına yaklaşık `±3 mm`; roll `±0,3°` | Aynı montaj ailesi içinde küçük tolerans |
| Lens distortion | cam-10 `-0,11…-0,09`; cam-11 `-0,13…-0,11` | Son görsel fit; ChArUco sonrası değişebilir |
| Kâğıt adedi | küplerde 0/1/2: `0,32/0,64/0,04` | Tüm şekillerde beklenen yaklaşık `%28,6` kâğıt oranı |
| Kâğıt altı RFID | uygun face tag'lerinde `0,58` | Kâğıt–tag ortak örneklerini üretme |
| Kâğıt occlusion | partial `0,78`, full `0,22`; görünür uç `0,15–0,50` | Görsel inceleme + bbox güvenliği |
| RFID adedi/yerleşimi | yalnız açık deney değişkeni | Staged set gerçek operasyon prior'ı değil |

Her kare metadata'sında seed, seçilen makine profili, kapı açısı, ışık profili,
kamera realization'ı, numune şekli, kâğıt–RFID link'i ve visibility kararı
saklanmalıdır. Yeni bir aralık yalnız:

1. aynı makineden yeni görsel/ölçüm kanıtı,
2. kaynak ve hesap yöntemi,
3. before/after paired render,
4. annotation validator sonucu

ile değiştirilmelidir. “Daha çeşitli görünüyor” tek başına aralığı
genişletme gerekçesi değildir.

## Kritik fakat çalışmayı durdurmayan sorular

Mevcut uygulama aşağıdaki varsayımlarla devam edebilir; cevaplar production
freeze'den önce gereklidir:

1. **Tek hedef makine gerçekten REF-65218 / İvedik LED konfigürasyonu mu?**
   Değilse renk zonu, kapak, LED ve kamera parçaları hedef `REF-*` için yeniden
   profillenmelidir.
2. **El/kişi üzerinde tutulan veya hazne duvarına staged yerleştirilen RFID'ler
   gerçek inference sırasında pozitif sayılacak mı?** Sayılmayacaksa bunlar
   training prior'ına eklenmemeli; ayrı robustness slice olmalıdır.
3. **ArUco/AprilTag/QR ve basılı makine etiketleri kalıcı saha bağlamı mı?**
   Kalıcıysa non-target context olarak simülasyonda bulunmalı, hedef sınıf
   yapılmamalıdır.
4. **Cam-10 ve cam-11'in kamera SKU'su, sensör ölçüsü ve distortion/intrinsics
   kalibrasyonu mevcut mu?** Varsa 2,8 mm görsel fit yerine gerçek
   calibration kullanılmalıdır.

Yüksek değerli ancak blocker olmayan ilave kanıtlar: kapı açılarını gösteren
6–10 ölçülü fotoğraf, tabla/numune gerçek ölçüsü, gri/mavi sac ve tablanın
polarize yakın planı, boş haznenin iki kameradan sabit exposure RAW/JPEG çifti
ve farklı kâğıt/RFID yerleşimlerinin operasyon frekansıdır.

## Yayın ve YOLO karar sınırı

Bu inceleme için savunulabilen sonuç şudur: generator, hedef sahnenin daha
doğru fiziksel topolojisini ve daha güvenli occlusion/bbox üretim mantığını
taşır. Şunlar henüz savunulamaz:

- “sentetik görüntüler gerçek fotoğraftan ayırt edilemez”;
- “IR ve RGB fotometrik olarak eşleşmiştir”;
- “YOLO precision/recall/mAP artmıştır”;
- “tag count/placement dağılımı gerçek operasyon prior'ıdır”;
- “fotoğraf-fit ölçüler CAD doğruluğundadır”.

YOLO faydası; capture-group sızıntısı giderilmiş sabit gerçek validation/test,
aynı seed/epoch/imgsz/hyperparameter ile en küçük modelde en az `real-only`,
`real+önceki sentetik`, `real+yeni sentetik`, `real+yeni sentetik+hard`
kolları karşılaştırılmadan raporlanmamalıdır. Sonuçlar kamera, şekil,
kâğıt-altı, tabla-aralığı, kişi var/yok, küçük tag ve occlusion slice'larına
ayrılmalıdır. Bu deney yapılana kadar doğru ifade **“referans-fit ve validator
hazır; model etkisi ölçülmedi”**dir.
