[![SynDRA](https://images.openai.com/static-rsc-4/TZKL-oL8r0YlUkV0i_1qj4HKkZw0AlDhL4KGrSv9uW4TWjDMAzgz76WLs0TZMBX9O7K32S8-fii3cHjPYApP7siL2gDulVQKZbcgQYl_n3oJ6W5-zaRbVVLZFEnwLIzbCa8D-bAfz0kHgB5n8sz_Ly1o0vhUWiI8pogBmjodPcU?purpose=inline)](https://syndra.retis.santannapisa.it/syndrabox.html?utm_source=chatgpt.com)

## Net değerlendirmem

**Evet, aklındaki sistem bugün yapılabilir.** Hatta bazı açılardan **EBİS beton kırım cihazı ve tren rayı uygulamaları, tarımdan daha kolay ve daha güvenilir sentetik veri alanlarıdır.**

En doğru tanım şu olur:

> **Doğal dil tarifini, doğrulanmış ve tekrar üretilebilir bir sentetik veri generator’ına çeviren LLM destekli sistem.**

Blender MCP burada “tek tek güzel görseller üreten yapay zekâ” değil; Blender’da çalışan bir **teknik artist, simülasyon geliştiricisi ve görsel debugger** olur.

Doğru akış:

```text
Türkçe kullanım senaryosu
        ↓
LLM tarafından yapılandırılmış scenario.yaml
        ↓
Şema ve fiziksel kural doğrulaması
        ↓
Blender Python + Geometry Nodes generator
        ↓
16–50 örneklik ön izleme
        ↓
Deterministik kontroller + görsel inceleme
        ↓
Headless batch üretim
        ↓
RGB + maskeler + depth + metadata
```

MCP, generator’ı geliştirir. Binlerce görüntüyü ise sabitlenmiş Python kodu üretir.

---

# Üç kullanım alanının gerçekçi sıralaması

Bu tablo benim mühendislik değerlendirmemdir:

| Alan                                                   |    Uygunluk | Asıl zorluk                                           |
| ------------------------------------------------------ | ----------: | ----------------------------------------------------- |
| **EBİS cihazı, beton numunesi ve görsel RFID etiketi** |  Çok yüksek | Doğru CAD, kamera ve materyal eşleşmesi               |
| **Ray bileşeni, engel ve çevre gözetleme**             |      Yüksek | Defekt ontolojisi ve gerçek sensör eşleşmesi          |
| **Ray yüzeyindeki çok küçük çatlak/aşınma ölçümü**     |        Orta | Milimetre ölçeği, line-scan optiği ve materyal fiziği |
| **Tarım crop/weed/soil üretimi**                       | Orta–yüksek | Biyolojik asset ve gerçek saha dağılımları            |

Temel neden:

```text
Kontrollü endüstriyel hücre
        >
Standartlaştırılmış ray dünyası
        >
Biyolojik ve açık tarla dünyası
```

EBİS makinesi, etiketi ve beton numunesinin ölçüleri büyük ölçüde sabit. Tarımda ise her bitki gerçekten farklı.

---

# Blender MCP bugün neyi değiştiriyor?

Blender Lab’in resmî MCP çalışması ve topluluk MCP’leri, LLM’nin Blender sahnesini incelemesine, obje ve materyal oluşturmasına, Blender Python kodu çalıştırmasına ve sahneyi iteratif olarak değiştirmesine imkân veriyor. Popüler topluluk uygulaması viewport ekran görüntüsü alma, Poly Haven ve Sketchfab’dan asset bulma, bazı text/image-to-3D servislerine bağlanma ve uzaktaki Blender instance’ını kontrol etme özellikleri de sunuyor. ([Blender][1])

Dolayısıyla şu döngü artık pratik:

```text
LLM kodu değiştirir
→ Blender sahneyi üretir
→ render / viewport görüntüsü döner
→ LLM hatayı inceler
→ ölçüm ve assertion çalışır
→ generator düzeltilir
```

Ancak resmî Blender sayfası da MCP’nin LLM tarafından üretilen kodu Blender içinde koruyucu katman olmadan çalıştırabildiği konusunda uyarıyor. Bu nedenle ayrı Linux kullanıcısı, sınırlı proje klasörü, secretsiz ortam ve pinlenmiş MCP commit’i gerekir. ([Blender][1])

---

# 1. EBİS beton kırım cihazı için ne yapılabilir?

Bu, genel platformu kanıtlamak için bence **en iyi ilk dikey**.

ASELSANNET’in ürün ailesinde beton kırım cihazı ve beton RFID etiketi birlikte yer alıyor; dolayısıyla cihaz, numune ve etiket ilişkisi sınırlı ve açıkça tanımlanabilen bir dünya. ([Aselsannet][2])

## Dijital ortam

Elinizde cihazın CAD’i veya teknik ölçüleri varsa şunlar modellenebilir:

* cihaz gövdesi, pres plakaları ve numune haznesi,
* güvenlik kapağı ve camı,
* kamera ve aydınlatma,
* beton küp/silindir numuneleri,
* RFID etiketi,
* kırılmış beton parçaları,
* beton tozu ve agrega,
* pas, yağ, çizik ve yüzey aşınması,
* kablo, uyarı etiketi ve laboratuvar arka planı.

CAD yoksa çok açılı fotoğraflar, birkaç temel ölçü ve basit fotogrametriyle yeterli görsel model çıkarılabilir. Fakat makine için CAD kullanmak sim-to-real açığını ciddi biçimde azaltır. CAD temelli Blender/BlenderProc endüstriyel veri hatları üretim benzeri görsel kontrol görevlerinde uygulanmış; 2025 tarihli küçük ölçekli bir çalışmada sentetik veride eğitilmiş model gerçek test görüntülerinde 0,93’e kadar mAP@0.5:0.95 bildirmiştir. Çalışmanın gerçek test örneklemi küçük olduğu için bunu üretim garantisi değil, güçlü bir fizibilite kanıtı olarak görmek gerekir. ([arXiv][3])

## Görsel RFID etiketi

Görsel olarak oldukça gerçekçi etiketler üretilebilir. Her örnekte şunları kontrollü değiştirebilirsiniz:

```text
etiket geometrisi
- kalınlık
- köşe yuvarlaklığı
- eğilme / bükülme
- kırık veya kesik kenar

materyal
- plastik / PET / epoksi
- parlaklık ve roughness
- kir ve beton kalıntısı
- ıslaklık
- çizik ve yüzey aşınması

yerleşim
- beton içine gömülme derinliği
- görünen yüzey oranı
- rotasyon
- numune kenarına uzaklık
- kısmi kapanma

kamera etkileri
- yansıma
- odak kaçması
- motion blur
- düşük pozlama
- LED titreşimi
- lens distortion
```

Çıktı olarak yalnız bounding box değil, şunlar alınabilir:

```text
tag semantic mask
tag instance mask
4 köşe keypoint'i
6D pose
visibility / occlusion oranı
numuneye göre konumu
etiketin hasar durumu
basılı kod veya seri numarası
```

BlenderProc; semantic ve instance segmentation, depth/distance, normals, optical flow, kamera pozları ve COCO/BOP/HDF5 çıktıları sağlıyor. Ayrıca lens distortion, dust, motion blur ve rolling-shutter örnekleri bulunuyor. ([GitHub][4])

### Kritik RFID ayrımı

**Kamera, gizli RFID UID’sini görüntüden okuyamaz.**

Etikette görünür bir seri numarası, QR veya barkod varsa kamera onu okuyabilir. Ancak yalnız anten/inlay içeren veya betonun içinde tamamen kaybolan pasif tag’in kimliği görüntüden çıkarılamaz.

Bu nedenle multimodal simülasyon şöyle kurulmalı:

```text
Blender
→ görüntü
→ tag maskesi, pose ve visibility

Ayrı RF modeli
→ read probability
→ RSSI
→ phase
→ anten-tag geometrisi

İki akış
→ görsel + RFID fusion
```

RF modeli ilk aşamada gerçek ölçümlerden öğrenilmiş istatistiksel bir kanal modeli olabilir. Yüksek doğrulukta elektromanyetik simülasyon gerekiyorsa Blender yerine özel EM araçları gerekir.

## Beton kırılması

Blender’da betonun parçalanması **görsel olarak ikna edici** yapılabilir:

* önceden hazırlanmış fracture varyantları,
* Voronoi fracture,
* agrega büyüklüğü varyasyonları,
* toz parçacıkları,
* kırılma sonrası farklı parça dağılımları.

Bu; “numune doğru yerleşmiş mi?”, “etiket görünür mü?”, “kırılma sonrası etiket nerede?”, “hazne temiz mi?” gibi vision görevleri için yeterli olabilir.

Fakat Blender’dan şu sonucu beklememek gerekir:

> Uygulanan kuvvete göre betonun gerçek kırılma çizgisini ve basınç dayanımını fiziksel olarak doğru hesaplamak.

Bunun için gerçek malzeme parametreleriyle FEM/DEM gerekir; Blender yalnızca sonucu görselleştiren katman olabilir.

---

# 2. Tren rayı gözetleme projesi

Ray ortamı prosedürel üretim için son derece uygun. Çünkü geometri standartlaştırılmıştır:

```text
track centerline
→ raylar
→ traversler
→ bağlantı elemanları
→ balast
→ sinyalizasyon
→ katener
→ çevre
```

Bir curve üzerinden Geometry Nodes ile kilometrelerce ray üretilebilir. Parametreler:

* ray açıklığı,
* travers aralığı,
* viraj yarıçapı,
* eğim ve superelevation,
* balast yüksekliği,
* ray ve travers tipi,
* tünel/köprü/istasyon/açık arazi,
* kamera güzergâhı.

## Üretilebilecek gözetleme senaryoları

### Yüksek güvenle üretilebilecekler

* ray ve travers segmentasyonu,
* eksik veya yanlış konumlu bağlantı elemanı,
* kırık veya çatlamış travers,
* balast eksikliği ve kirlenmesi,
* ray üzerinde taş, ağaç dalı veya metal parça,
* insan/hayvan/araç engeli,
* bitki istilası,
* pas ve genel yüzey kirliliği,
* sinyal ve işaret algılama,
* kamera localization ve ego-track çıkarımı.

### Daha zor olanlar

* ray başındaki ince rolling-contact-fatigue çatlakları,
* küçük spalling ve pitting,
* milimetre altı yüzey kusurları,
* hassas ray geometrisi ölçümü,
* termal, ultrasonik veya eddy-current sinyal üretimi.

İkinci grup için yalnız görsel olarak güzel bir shader yeterli olmaz. Gerçek line-scan kamera, aydınlatma açısı, polarizasyon, MTF, pozlama ve kusur topografyasının ölçülmesi gerekir.

Ray alanındaki fizibilite yalnız teorik değil. WACV 2025’te yayımlanan SynDRA, Unreal üzerinde hazırlanmış olsa da, dört farklı çevre ile değişen hava ve ışık koşullarında 80 stereo RGB sekansı ve piksel seviyesinde semantic anotasyon üretildiğini gösteriyor. Bu, Blender’a özgü bir kanıt değil; ray ortamının prosedürel sentetik veriyle modellenebilir olduğunun kanıtı. ([Open Access Computer Vision Foundation][5])

Blender karşılığı şöyle kurulabilir:

```text
rail_spec.yaml
       ↓
RailGenerator
       ↓
DefectInjector
       ↓
CameraTrajectory
       ↓
Cycles RGB
       +
BlenderProc ground truth
       ↓
RGB / depth / mask / flow / pose
```

Örneğin bir defekt senaryosu:

```yaml
track:
  gauge_mm: 1435
  sleeper_spacing_mm: 600
  curvature_radius_m: 900

defects:
  - type: missing_fastener
    rail_side: left
    probability: 0.03

  - type: ballast_fouling
    severity: medium

  - type: vegetation_encroachment
    distance_to_rail_m: [0.0, 0.4]

camera:
  profile: undercarriage_cam_v1
  speed_kmh: [20, 70]
  vibration_rms_deg: [0.05, 0.4]

weather:
  rain: [none, light]
  rail_wetness: [0.0, 0.8]
```

LLM bu dosyayı doğal dilden oluşturur; domain şeması ise imkânsız veya anlamsız kombinasyonları reddeder.

---

# 3. Tarım neden hâlâ değerli ama daha zor?

CropCraft, Blender üzerinde çalışan YAML tabanlı bir tarımsal dünya generator’ı. Ürün sıraları, bitki ve taş yerleşimleri üretebiliyor; güncel repo Cycles RGB ve EEVEE semantic mask çıktısını da destekliyor. ([GitHub][6])

Bu nedenle tarım modülü sıfırdan başlamaz:

```text
CropCraft fork
+ yeni bitki assetleri
+ growth-stage sistemi
+ gerçek kameraya göre sahne profilleri
+ MCP ile geliştirme
```

Fakat asıl sorun tarla oluşturmak değil:

* doğru büyüme evreleri,
* gerçek yaprak sayısı ve açıları,
* hedef crop’un biçimi,
* weed morfolojileri,
* nem–topografya–bitki korelasyonu,
* gerçek saha yoğunlukları.

Raydaki travers standarttır. Mısır veya yabani ot standart değildir. Bu yüzden tarım generator’ı daha fazla gerçek veri kalibrasyonu ister.

---

# LLM ile “yüksek kontrol” nasıl sağlanmalı?

Kontrol doğrudan prompttan değil, **promptun çevrildiği şemadan** gelmeli.

Örneğin EBİS için:

```yaml
domain: ebis_press_v1
seed: 43102

camera:
  profile: chamber_camera_01
  exposure_jitter_ev: [-0.4, 0.4]
  focus_error_probability: 0.08

sample:
  geometry: cube
  size_mm: 150
  concrete_profile: c30_rough
  moisture: [0.05, 0.4]

rfid_tag:
  state_weights:
    correctly_embedded: 0.60
    partially_exposed: 0.18
    covered_by_concrete: 0.10
    damaged: 0.07
    missing: 0.05
  embed_depth_mm: [0, 15]
  rotation_deg: [-30, 30]

machine:
  plate_wear: [0.1, 0.7]
  chamber_dust: [0.0, 0.6]
  door_state: closed

outputs:
  rgb: true
  semantic_mask: true
  instance_mask: true
  depth: true
  tag_keypoints: true
  camera_metadata: true
```

Kullanıcı doğal dille şunu söyleyebilir:

> “Etiketin çoğunlukla düzgün, bazen kısmen betonla kaplı olduğu; kamerada yansıma ve odak kaçması bulunan 5.000 numune üret.”

LLM bunu şemaya çevirir. Generator ise yalnız izin verilen parametrelerle çalışır.

Böylece:

* aynı seed aynı görüntüyü verir,
* sınıf dağılımı bilinir,
* hangi varyasyonun modeli geliştirdiği ölçülür,
* hatalı batch yeniden üretilebilir,
* LLM değişse bile generator çalışmaya devam eder.

---

# Ne kadar güvenebiliriz?

| Katman                                                | Güven                       |
| ----------------------------------------------------- | --------------------------- |
| Semantic/instance mask doğruluğu                      | Çok yüksek                  |
| Depth, kamera pose ve 3B koordinat                    | Çok yüksek                  |
| CAD tabanlı makine geometrisi                         | Çok yüksek                  |
| Kontrollü sahnede görsel materyal eşleşmesi           | Yüksek olabilir             |
| Açık ray/tarım dünyasının gerçek dağılımı             | Kalibrasyona bağlı          |
| Sentetik verinin gerçek model performansını artırması | A/B testinden önce bilinmez |
| RFID elektromanyetik davranışı                        | Blender’a güvenilmez        |
| Betonun gerçek kırılma mekaniği                       | Blender’a güvenilmez        |

İnsan gözüyle gerçekçi görünmesi tek başına kanıt değildir. Karar deneyi her zaman:

```text
A — yalnız gerçek veri
B — yalnız sentetik veri
C — sentetik pretraining + gerçek fine-tuning
D — gerçek + sentetik karışım
```

ve sabit gerçek holdout üzerinde yapılmalı.

---

# Kuracağım ortak platform

```text
synthetic-data-platform/
├── core/
│   ├── scenario-schema
│   ├── asset-registry
│   ├── blender-compiler
│   ├── camera-models
│   ├── renderer
│   ├── annotation-writers
│   └── validators
│
├── domains/
│   ├── ebis/
│   │   ├── machine-assets
│   │   ├── tag-states
│   │   └── concrete-profiles
│   │
│   ├── railway/
│   │   ├── track-generator
│   │   ├── component-assets
│   │   └── defect-ontology
│   │
│   └── agriculture/
│       ├── cropcraft-fork
│       ├── plant-assets
│       └── field-profiles
│
└── experiments/
    ├── real-only
    ├── synthetic-only
    └── mixed
```

Renderer’ı da soyut tutmak gerekir:

```text
Renderer
├── NativeBlenderRenderer
└── BlenderProcRenderer
```

Bunun güncel bir nedeni var: BlenderProc’un son kararlı sürümü 2.8.0, Ekim 2024’te yayımlanmış ve Blender 4.2.1’e yükseltilmiş durumda; CropCraft ise güncel render akışını Blender 5.0.1 üzerinde doğruladığını belirtiyor. Bu nedenle bütün sistemi tek BlenderProc/Blender sürümüne körlemesine bağlamak yerine backend adaptörü ve pinlenmiş ortamlar kullanmak daha güvenli. ([GitHub][7])

---

# En yüksek ROI başlangıç

Platform fikrini önce **EBİS görsel RFID senaryosunda** kanıtlardım:

1. Cihaz CAD’i veya sadeleştirilmiş dijital ikiz.
2. Gerçek kamera intrinsics’i ve sabit kamera pozu.
3. Gerçek RFID tag geometrisi ve materyali.
4. Beş durum: doğru, kısmen kapalı, hasarlı, yanlış konumlu, eksik.
5. 2.000–5.000 sentetik görüntü.
6. 100–300 adet dokunulmamış gerçek test görüntüsü.
7. Tag detection + köşe/keypoint + görünürlük modeli.
8. Real-only ile synthetic-pretrain + real-finetune karşılaştırması.

Bu deney başarılı olursa ortak çekirdeğin çalıştığı kanıtlanır. Ardından ray için `RailGenerator`, tarım için `CropCraft` domain modülü eklenir.

## Son hüküm

**Bu artık yalnızca oyuncak bir “promptla Blender kullanma” fikri değil.** Özellikle kendi cihaz CAD’iniz, kameranız ve gerçek referans görüntüleriniz varsa ciddi bir sentetik veri platformu kurulabilir.

Ancak gerçek değerli varlık Blender MCP olmayacak:

> **Doğrulanmış domain şemaları + CAD/asset kütüphanesi + sensör profilleri + otomatik QA + gerçek holdout geri bildirim döngüsü.**

MCP değiştirilebilir kontrol katmanıdır. Asıl ürün, doğal dil tarifini **ölçülebilir, denetlenebilir ve deterministik veri generator’ına** dönüştüren sistem olur.

[1]: https://www.blender.org/lab/mcp-server/?utm_source=chatgpt.com "MCP Server"
[2]: https://www.aselsannet.com.tr/tr/urun/2836?title=beton-kirim-cihazi "İhtiyaçlarınızı dinlemek ve çözüm sunmak için buradayız"
[3]: https://arxiv.org/html/2509.13089v1 "A Synthetic Data Pipeline for Supporting Manufacturing SMEs in Visual Assembly Control"
[4]: https://github.com/DLR-RM/BlenderProc/blob/main/docs/tutorials/renderer.md "BlenderProc/docs/tutorials/renderer.md at main · DLR-RM/BlenderProc · GitHub"
[5]: https://openaccess.thecvf.com/content/WACV2025/html/DAmico_SynDRA_Synthetic_Dataset_for_Railway_Applications_WACV_2025_paper.html?utm_source=chatgpt.com "Synthetic Dataset for Railway Applications - CVF Open Access"
[6]: https://github.com/Romea/cropcraft "GitHub - Romea/cropcraft: A Procedural World Generator for Robotics Simulation of Agricultural Tasks · GitHub"
[7]: https://github.com/DLR-RM/BlenderProc/releases?utm_source=chatgpt.com "Releases · DLR-RM/BlenderProc"
