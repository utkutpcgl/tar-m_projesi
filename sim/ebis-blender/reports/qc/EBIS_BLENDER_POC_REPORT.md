# EBIS Blender POC doğrulama raporu

> **Tarihsel v1.4.2 baseline:** Bu rapor 150 mm/5,37 mm ve tek-RFID semantic-mask POC’sini belgeler. Güncel v1.5 teslimi için `reports/handoff/EBIS_BLENDER_HANDOFF_REPORT.md`, `README.md` ve `configs/ebis_led_v2.json` esas alınmalıdır.

**Tarih:** 28 Temmuz 2026  
**Karar:** **Teknik POC geçti; üretim ve YOLO ablation aşamasına doğrudan geçmek için henüz yeterli değil.**

Blender 4.5.12 LTS/Cycles üzerinde EBIS iç haznesi, beton küp ve görsel RFID etiketi için kontrol edilebilir ve tekrar üretilebilir bir sentetik veri hattı çalışıyor. İki kamera, RGB, ikili sınıf maskeleri, maskeden türetilen YOLO kutuları, iki depth temsili, metadata, seed ve bütünlük hash'leri üretildi. RTX 3090 üzerindeki 24 görüntülük pilot **24/24 PASS** verdi; BlenderMCP add-on'unun gerçek JSON/TCP komut yolu üzerinden ayrı bir Blender oturumunda sahne okuma, nonce taşıyan kod çalıştırma, viewport alma ve Cycles render üretme işlemleri de doğrulandı.

Bu sonuç hattın işlevsel olduğunu kanıtlar; CAD doğruluğunu, fotogerçekçiliği, gerçek/sentetik domain gap'inin yeterince küçük olduğunu veya sentetik verinin YOLO performansını artıracağını kanıtlamaz. Mevcut çıktı en doğru biçimde **ablation öncesi, kontrollü EBIS vision POC** olarak sınıflandırılmalıdır.

## Doğrulanan kapsam

- Sınıflar: `0 = rfid_tag`, `1 = concrete_sample`.
- Sabit temel bakışlar: `camera_door` ve `camera_angled`.
- Kontrollü değişkenler: beton konumu/yaw/nem/hasar, RFID yerleşimi/yüzü/dönüşü, dört ışık profili ve pozlama.
- Görsel RFID: yaklaşık 60 × 10 × 0,12 mm, farklı ön/arka yüz, bakır anten hissi ve siyah merkez kapsülü. RF, UID, RSSI veya okuma mesafesi kapsam dışıdır.
- Çıktılar: RGB PNG, görünür sınıf için 8-bit `0/255` semantik maskeler, bu maskelerden türetilmiş YOLO detection etiketleri, ham metrik ve yaklaşık RGB-hizalı EXR depth, görüntü başına JSON metadata ve isteğe bağlı `.blend`.
- Kapsam dışı: insan sınıfı, kırılma fiziği, tren/Unreal, model eğitimi ve real+synthetic ablation.

Uygulama ve yeniden üretim sözleşmesi [README](../../README.md), parametreler [ebis_pilot.json](../../configs/ebis_pilot.json), uygulama ise [generate_ebis.py](../../scripts/generate_ebis.py) içindedir. Kaynak hedefleri [ana planda](../../../blender_ve_unreal_ablation_plan.md) tanımlanmıştır.

## Teknik sonuçlar

### 24 görüntülük pilot

[Pilot validation](../../output/pilot_final/validation.json) ve [run manifest](../../output/pilot_final/run_manifest.json) birlikte şu sonucu veriyor:

| Kontrol | Sonuç |
| --- | --- |
| Durum / kapsam | `PASS`; 24 beklenen, 24 bulunan; 24 benzersiz seed ve render anahtarı |
| Kameralar | `camera_door`: 12, `camera_angled`: 12 |
| Çözünürlük / render | 24 × 1280×720, 64 sample, 24/24 OptiX — NVIDIA GeForce RTX 3090 |
| Süre | toplam 93,007 s; ortalama 3,875 s; min 3,658 s; maks 4,136 s |
| Bütünlük | 144 dosya SHA-256 kontrolü; 48 ikili maske; 48 EXR depth; hata ve uyarı yok |
| Sınıf kapsamı | RFID: 24/24 görüntü; beton: 24/24 görüntü |
| RFID durumları | `sample_front`: 16, `sample_side`: 1, `loose_back`: 6, `loose_front`: 1, `missing`: 0 |
| Işık profilleri | `led_neutral`: 12, `door_daylight`: 8, `led_cool`: 3, `warm_dirty`: 1 |
| Görünür RFID | 393–5.262 piksel; bbox genişliği 54–190 px, yüksekliği 11–141 px |
| Görünür beton | 205.453–269.379 piksel |
| Depth sağlık kontrolü | ham ve hizalı dosyalarda en düşük finite/geçerli metrik oranı `1,0`; global ham aralık 0,09998–0,50746 m |

Pilot klasörü 24 RGB, 24 label, 24 metadata, 48 maske, 48 depth ve ilk sahnenin `.blend` dosyasını içeriyor. Bounding box'lar yayımlanmış ikili görünür maskelerden türetildiği için RGB/maskeye uygulanan yaklaşık lens warp'ı ile aynı piksel uzayındadır. `depth_raw` lens warp'sız Blender Z pass'idir; `depth_aligned` bilinear olarak yeniden örneklenmiş yaklaşık eşlemedir ve özellikle kenarlarda metrik ground truth sayılmamalıdır.

Temel kimlikler:

- Canonical config SHA-256: `98eebddc6bc1fbf149be55eb92200656e2392bf0f07f7580e31cb73b432bcc34`
- Generator SHA-256 / sürüm: `260f5728aaee6e0f48152b4f32bc908de4b09a3ddf60fff657941f443a368235` / `1.4.2`
- `validation.json` SHA-256: `98d029cf6e07583236358307b43116f5df02088a56a65f795ccbdd91f519f2f9`
- `run_manifest.json` SHA-256: `f3d7bd78ecd8ca364650cf28e582563d4ce377d270a57b381a24bf8809dfca7e`

### Aynı-seed tekrarlanabilirlik kontrolü

[Tekrarlanabilirlik özeti](../../evidence/determinism/summary.json), seed `43102` ve `camera_door` için aynı RTX 3090/Blender 4.5.12/OptiX ortamında iki bağımsız 960×540, 32-sample renderı karşılaştırır. YOLO etiketi ile RFID ve beton maskeleri bit-bit aynıdır. Denoise edilmiş RGB bit-bit aynı değildir; 1.555.200 kanal değerinin yalnız 42'si (`%0,0027`) değişmiş ve en büyük fark bir 8-bit seviyede kalmıştır. Metadata farkları yalnız render süresi ve buna bağlı RGB hash'idir. Bu sonuç geometri tabanlı anotasyonların aynı ortamda deterministik olduğunu destekler; farklı GPU, sürücü veya Blender build'i için bit determinizmi iddiası değildir. Ham iki koşu [run_a](../../evidence/determinism/run_a/) ve [run_b](../../evidence/determinism/run_b/) altında korunmuştur.

### Hero ve RFID asset çıktıları

[Hero validation](../../output/hero_final/validation.json) iki kameranın her biri için bir 1920×1080, 256-sample sahneyi **PASS** olarak doğruladı: sekiz dosya hash'i ve dört ikili maske kontrol edildi. İki karede de `door_daylight` ve `sample_front` seçildi; ortalama render süresi 13,339 s oldu. Hero renderlarda depth bilinçli olarak kapalıdır ve tek validator uyarısı `depth_explicitly_disabled_for_2_image(s)` kaydıdır. Her iki `.blend` sahnesi de [hero_final](../../output/hero_final/) altında bulunur.

[RFID manifest](../../output/rfid_final/manifest.json), 1920×1080 ve 256 sample ile OptiX üzerinde üretilen ön, arka ve birleşik makroları ve düzenlenebilir `.blend` dosyasını kapsıyor. Birleşik/ön/arka PNG SHA-256 değerleri sırasıyla `8efbba8930087d01841929eac7e4a2f52eec55a3950e83d142db26bdd308e5ff`, `d68cbd3560a5a4ffe6b426492c67f355a2e432c7e7bce0d61d8069d0c7727ed0` ve `9684ce536f989b890a68b7be6551cf15435269726fd994eede6adf20d861dc64` değerleridir.

## Görsel QC ve gerçek referansla farklar

[24 karelik pilot contact sheet](pilot_final_contact_sheet.png), iki kamerada beton ve RFID kutularının görünür nesneleri takip ettiğini; ışık, beton yüzeyi ve RFID yerleşiminin seed'ler arasında değiştiğini gösteriyor. [Hero contact sheet](hero_final_contact_sheet.png) iki temel bakışın yüksek çözünürlüklü özetidir. [Gerçek Kamera 01 / sentetik camera_angled karşılaştırması](real_vs_synthetic_camera01.png) ana kompozisyonun doğru yönde olduğunu gösteriyor: küp kadrajı baskılıyor, üst pres tablası görülüyor ve mavi boyalı hazne yüzeyi korunuyor.

Gözle kontrol edilen olumlu noktalar:

- Beton, RFID ve makine birbirine göre makul ölçekte; hedef sınıflar her pilot karesinde okunabilir.
- İki yanal bakış, gerçek kayıtlardaki genel görüş yönünü ve geniş açı hissini temsil ediyor.
- Beton yüzeyinde nem/ton, gözenek, çatlak, kenar hasarı ve kırıntı varyasyonu var.
- RFID ön/arka farkı makroda belirgin; sahne içindeki etiket arka plandan ayrılıyor.

Üretim öncesi kapatılması gereken görsel farklar:

- Gerçek karedeki sert yakın alan aydınlatması, sensör gürültüsü/sıkıştırma, güçlü lokal parlama ve gerçek geniş açı karakteri sentetikte eksik veya fazla temiz. Kamera intrinsics ve distorsiyon görsel tahmindir.
- Makine içi geometri CAD'e dayanmıyor; gerçek pres tablasının aşınması, bağlantılar, kapı çerçevesi ve yüzey kiri daha karmaşık. Sentetik metal/paneller halen düzenli ve CG görünümündedir.
- Beton silueti fazla kübik ve keskin; bazı oyuklar düzenli koyu delik, büyük kırıklar ise fasetli kaya gibi görünüyor. Gerçekteki ince yüzey porozitesi ve kenar aşınması daha düzensizdir.
- RFID anteni ve merkez kapsülü tanınabilir fakat stilize, simetrik ve temizdir; üretim CAD'i veya ölçülü malzeme katmanı değildir.
- Karşılaştırma sayfası yalnız bir `Kamera 01` karesini kapsıyor. `Kamera 02`, farklı gerçek ışık koşulları ve RFID ön/arka durumları için eşlenik karşılaştırma henüz yok.
- 24 örnekte `missing` durumu hiç oluşmadı; `sample_side`, `loose_front` ve `warm_dirty` yalnız birer kez görüldü. Ağırlıklı rastgele seçim çalışıyor olsa da bu pilot dengeli varyasyon kapsamı sağlamıyor.

Dolayısıyla görsel sonuç **kullanışlı ve denetlenebilir bir POC**, ancak fotogerçekçi dijital ikiz veya doğrudan üretim dataseti olarak onaylanmış değildir. Mevcut 24 kare, ana plandaki 100 örneklik manuel QC ve 500–1.000 görüntülük dataset teslim hedefini karşılamaz.

## Blender MCP doğrulaması

[Pin kaydı](../../evidence/mcp/pins.json) Blender `4.5.12 LTS` (`84afd5f785f7`) ve BlenderMCP commit `da4e16d2069ce5154eaa2535bf995e843caf5c73` kullanıldığını; add-on SHA-256 değerinin `ca6955bb584d78e229f020a8b9d7011440adc6e94dab0ac8e01ab2794db19dc0` olduğunu gösteriyor.

[Round-trip kaydı](../../evidence/mcp/20260728T132900Z-9dd6f23b/roundtrip.json) üzerinden:

- `127.0.0.1:9876` adresindeki pinlenmiş BlenderMCP add-on'una gerçek JSON/TCP komutları gönderildi.
- 145 nesne ve 20 materyalli `EBIS_SYNTHETIC_DATA_SCENE` önce/sonra okundu; nesne sayısı değişmedi.
- Benzersiz nonce Blender içinde çalıştı ve Blender sürümü/sahne adı geri döndü.
- 990×693 viewport üretildi: SHA-256 `5bf874d74ce1c73c07155ff86f0e9d2c40d593e939737ceca33e64408008b2fa`.
- 1920×1080 aktif kamera Cycles renderı üretildi: SHA-256 `6a48bbd2c46e32f3a38fc7e4595692ed317bdfec3e366aed67cdc9f6d249ec64`.
- Doğrulama Blender prosesi kapatıldı ve portun kapandığı kontrol edildi.

`roundtrip.json` SHA-256 değeri `944f45a783c53a5acfd6dd89dce1ada8e373a6cc975f0e636d685e82b0cdd11e`'dir. Bu kanıt, BlenderMCP add-on'unun gerçek komut yolunu doğrular; ayrı stdio MCP server prosesinin uçtan uca çalıştırıldığını iddia etmez. Endpoint yalnız loopback'te tutulmuştur fakat protokolde auth/TLS yoktur; dış ağa açılmamalıdır.

## Teslimler

| Teslim | Kanıt |
| --- | --- |
| Generator ve yapılandırma | [README](../../README.md), [generate_ebis.py](../../scripts/generate_ebis.py), [ebis_pilot.json](../../configs/ebis_pilot.json) |
| 24 görüntülük pilot dataset | [pilot_final](../../output/pilot_final/), [validation](../../output/pilot_final/validation.json), [contact sheet](pilot_final_contact_sheet.png) |
| İki yüksek kaliteli hero ve sahneleri | [hero_final](../../output/hero_final/), [hero QC](hero_final_contact_sheet.png) |
| Görsel RFID ön/arka asseti | [rfid_final](../../output/rfid_final/), [manifest](../../output/rfid_final/manifest.json) |
| Gerçek/sentetik kadraj kontrolü | [comparison](real_vs_synthetic_camera01.png), [referans indeksi](../../assets/reference/README.md) |
| Blender MCP kanıt paketi | [pins](../../evidence/mcp/pins.json), [round-trip](../../evidence/mcp/20260728T132900Z-9dd6f23b/roundtrip.json), [viewport](../../evidence/mcp/20260728T132900Z-9dd6f23b/viewport.png), [render](../../evidence/mcp/20260728T132900Z-9dd6f23b/render.png) |
| Aynı-seed tekrar kanıtı | [özet](../../evidence/determinism/summary.json), [run_a](../../evidence/determinism/run_a/), [run_b](../../evidence/determinism/run_b/) |

## Bilinen sınırlar

- EBIS ve beton CAD/ölçümle eşlenmedi; 150 mm küp bir POC varsayımıdır.
- 2,8 mm lens, 5,37 mm sensör ve `-0,105` compositor distorsiyonu ölçülmüş kalibrasyon değil, görsel eşlemedir.
- Beton hasarı görsel prosedürdür; basınç, kırılma, FEM/DEM veya malzeme dayanımı simülasyonu değildir.
- Maskeler sınıf düzeyinde semantiktir; instance ID, COCO, normal, optical flow ve keypoint yoktur.
- Geometri ve metadata pinli sürümlerde seed ile deterministiktir; GPU sürücüsü, Blender build'i veya denoiser değişirse RGB'nin bit-bit aynı kalması garanti edilmez.
- Aynı seed'in iki kamera karşılığı mevcut yerleştirme mantığında kalibre stereo/eşlenik multiview değildir; `sample_side` seçili kameraya yönlenebilir.
- Kapı açıklığı ve gerçek sensör noise/blur modeli henüz sistematik randomization ekseni değildir.

## Sonraki üretim ve ablation kapısı

**Şimdi verilecek karar:** generator'ı çöpe atmadan geliştirme ve kalibrasyon aşamasına geçirmek için **GO**; 500–1.000 görüntülük üretim dataseti ile model faydası iddiası için **HOLD**.

1. EBIS hazne/tabla ve beton ölçülerini doğrula; iki kamera için ölçülmüş intrinsics, distorsiyon ve mümkünse pozlama/ışık örnekleri topla. RFID boyutunu ve katman görünümünü üretim referansıyla eşleştir.
2. Gerçek karelere karşı materyal-aşınma, beton kenarı/porozitesi, lens/sensör karakteri ve makine detaylarını iyileştir. Her iki kamera ve temel gerçek koşullar için yan yana QC oluştur.
3. Ağırlıklı rastgele örnekleme yerine kamera × ışık × RFID durumu için kapsama garantili **100 karelik stratified QC seti** üret. `missing`, yan, gevşek ön/arka ve dört ışık profilini yeterli sayıda zorunlu kıl; anotasyon, görünürlük ve fiziksel yerleşim hata ölçütlerini renderdan önce yazılı sabitle.
4. 100 kare manuel QC'yi geçerse ayrı output dizininde en az 500 kare üret; mevcut hash/mask/depth/orphan validator'ını tam set üzerinde yeniden çalıştır.
5. Aynı gerçek train/val/test bölmesini ve yalnız gerçek test setini koruyarak önce `R` ile `R+B` koşullarını karşılaştır; sentetik bütçeyi plandaki `1N` ve `2N` seviyelerinde dene. Ancak mAP50-95, recall/F1 ve sınıf bazlı hata analizi gerçek testte raporlandıktan sonra sentetik verinin faydası hakkında karar ver.
