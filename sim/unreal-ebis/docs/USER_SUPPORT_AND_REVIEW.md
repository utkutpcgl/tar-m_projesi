# Unreal-EBİS için kullanıcı desteği ve review protokolü

Unreal tarafında en büyük kazanç daha fazla node eklemekten değil, gerçek makine ölçüsünü, yüzey ölçeğini ve ışık/kamera davranışını sağlamaktan gelir. Hepsini bir seferde vermen gerekmiyor. Aşağıdaki minimum paket proxy sahneyi hızla düzeltir; ideal paket Blender ve Unreal’da aynı fiziksel asset’i kullanarak adil kıyas yapmamızı sağlar.

## En kısa yararlı paket — yaklaşık 20 dakika

1. Kapı açıkken kutunun tamamını, metre/cetvel kadrajdayken çek.
2. İç genişlik, derinlik ve yükseklik için ayrı ölçü fotoğrafları.
3. Üst ve alt dairesel tablanın çapı/kalınlığı; merkezleri ve bağlantı mili görünsün.
4. LED kapalıyken back + left + right duvarı saran opal kanalın genel ve yakın fotoğrafı; kesit yüksekliği/derinliği ölçülsün.
5. Aynı açı ve pozlama kilidiyle LED açık bir kare.
6. Gri/girintili noktalı sacı önden ve eğik ışıkta yakın çek.
7. Küp/silindir ölçülerini ve RFID’nin gerçek boyutunu yaz.
8. Cam-10/cam-11 marka-model veya cihaz etiketi fotoğrafını ekle.

Adlandırma: `YYYYMMDD_ebis_<parça>_<ölçü-veya-açı>.<ext>`. Değerleri [`ebis_physical_measurements_template.json`](../configs/ebis_physical_measurements_template.json) içine yazabilir veya fotoğrafların yanında düz metin verebilirsin.

## İdeal ortak CAD paketi

Blender ve Unreal’ın gerçekten kıyaslanabilmesi için aynı kaynak mesh kullanılmalı. Tercih sırası:

- Üretici `STEP/IGES`; yoksa ölçülü teknik çizim/PDF.
- Alternatif `FBX` veya `GLB`: gerçek dünya ölçeği, pivot/eksen ve birim notuyla.
- Yalnız iç hazne, kapı/frame, iki tabla, ram, LED kanalı ve servis kapağını içeren sadeleştirilmiş model yeterlidir.

Gerekli ölçüler: kutu iç hacmi, kapı açıklığı/kanadı/menteşe, tabla çapı-kalınlığı-ekseni, boş açıklık, ram, U biçimli LED segmentleri ve servis kapağı. Ticari veya gizli detaylar kaldırılabilir. Dosyanın kullanım/lisans durumunu yanına yaz.

Unreal importunda mesh santimetreye normalize edilir; smoothing group/tangent, UV ve material slotları korunur. Nanite yalnız silhouette/mesh yoğunluğu gerektiriyorsa açılır. Collision detection dataset’i için kalite sağlamaz; görsel mesh ve instance kimliği esas alınır.

## PBR yüzey referansı nasıl çekilir?

Telefon yeterlidir. Otomatik HDR kapalı, white-balance sabit ve düşük ISO kullan:

1. Yüzeyi en az 1200×1200 piksel dolduran tam karşı diffuse kare.
2. 30–45° grazing-light kare.
3. Cetvel/madeni para ile gerçek texture ölçeği.
4. Gri kart veya ColorChecker içeren renk karesi.
5. Metal için üç ışık yönü; beton için kuru ve nemli ayrı set.

Yüzey setleri:

- koyu/gri pebbled iç sac;
- üst/alt kullanılmış çelik tabla ayrı ayrı;
- LED kapalı opal plastik ve açık diffuser;
- küp kalıp yüzü, kenar/kırık yüz;
- silindir yan/uç yüz;
- üst tabla ile temas etmiş küp/silindirin üst 20 mm bandı ve üst yüzü;
  cetvel + gri kartla, temizlemeden, tam karşı ve en az dört
  grazing-light yönünde; mümkünse yük öncesi/sonrası aynı numune;
- RFID ön/arka/kenar ve yapışkan kalkması.

RAW/DNG en iyisi; yoksa asıl yüksek kalite JPEG/PNG yeterlidir. Mesajlaşma uygulamasıyla sıkıştırılmış kopya gönderme. Hazır PBR texture varsa lisans, texel ölçeği ve hangi kanalın ne olduğu (`basecolor`, `normal`, `roughness`, `metallic`, `height`, `AO`) belirtilmeli. Unreal’da roughness’ın sRGB kapalı olması ve normal formatı import sırasında doğrulanır.

## Fiziksel LED ve kamera bilgisi

- LED ürün/sürücü kodu, güç, CCT, CRI; varsa IES/LDT dosyası.
- Sample merkezinde yalnız LED açık lux; mümkün değilse aynı açı/pozlama kilidiyle LED açık-kapalı çift.
- Cam-10/cam-11 native çözünürlük, FPS, codec, lens, exposure/gain/WB.
- Her kamera için farklı açı ve konumda 15–25 checkerboard/ChArUco frame; dijital crop, otomatik zoom/focus değişimi ve blur olmasın.
- Boş hazne, küp, silindir; kapı açık/kapalı ve LED açık/kapalı kısa ham örnekleri.

Kalibrasyon setine `camera_calibration_target.json` ekle. Zorunlu alanlar `target_type`, `inner_corners_cols`, `inner_corners_rows`, `square_size_mm`, `paper_size`, `print_scale_percent`, `printed_square_size_mm_verified`, `source_file` ve `source_file_sha256`dır. `inner_corners` kare sayısı değil algılanan iç köşe sayısıdır. Baskıda “sayfaya sığdır” kapatılır; basılmış kare kumpas/cetvelle yeniden ölçülür. Aynı fiziksel target/manifest Blender ve Unreal’da kullanılır. Target geometrisi veya hash’i yoksa çözüm metrik intrinsics/extrinsics değil, yalnız visual-fit proxy olarak raporlanır.

Unreal’daki lumen/emissive değerleri gerçek lux/CCT verisine bağlanabilir. IES bulunmasa bile diffuser boyutu + lux ölçümü, beyaz panel gibi parlayan mevcut yaklaşımı dar U-kanal area/rect light ile kalibre etmeye yeterlidir.

Güncel üst-yük mikro-disc'leri ölçülmüş texture değildir. Bu yakın planlar
geldiğinde aynı scale-referanslı scan/decal seti Blender ve Unreal'a
birlikte aktarılmalı; procedural disc sayısı artırılarak görüntü
“kirletilmemelidir”.

## Dört kontrollü review turu

| Tur | Sana gösterilecek | Senden beklenen karar |
| --- | --- | --- |
| A — geometri | unlit/clay iki kamera × iki sample | kapı, kutu, tabla ve LED konum/ölçeği |
| B — PBR | kilitli geometri, nötr ışık | sac/çelik/beton/RFID yüzey eşleşmesi |
| C — ışık/kamera | sabit PBR, dört ışık profili | CCT, clipping, black level, lens/exposure |
| D — annotation | RGB + visible/amodal + bbox | gerçek görünürlük ve partition kararı |

Yorum şablonu:

```text
dosya/seed:
bölge: ör. upper_platen / wall_back / diffuser_right / rfid_03
önem: blocker | yüksek | orta | düşük
gözlem: ne yanlış?
gerçekte nasıl: kısa tarif veya referans dosya adı
karar: reject | düzeltip tekrar göster | kabul
```

“Unreal havası var” yerine “sağ duvar düz mavi; referans X’te gri, 1–2 mm ölçekli pebbled ve rough highlight var” biçimi doğrudan parametreye dönüşür. Öncelik fiziksel yanlış → kamera → ışık → ana materyal → küçük dekor sırasıdır.

## Kör ve engine-adil review

Gerçek, Blender ve Unreal crop’ları motor adı kapalı ve aynı çözünürlükte karıştırılır. Her kareye `gerçek olma olasılığı 1–5`, `geometri`, `materyal`, `ışık`, `kamera` puanı ver. En az bir EBİS operatörü/mühendisi daha bağımsız puanlar. Aynı CAD/PBR/camera spec kullanılmadan engine kazananı ilan edilmez.

Production review PASS için owner ve ikinci operatör/mühendisin sentetik karelerdeki ayrı ayrı `overall gerçeklik` medyanı en az `3.0/5`; dört alt eksenin ortak medyanlarının her biri en az `3.0/5` olmalı ve açık blocker kalmamalıdır. Yalnız eski Unreal baseline’dan kötü olmamak yeterli değildir. Bu asgari eşik fotogerçekçilik veya YOLO kazancı anlamına gelmez.

## YOLO tarafında desteğin

- Capture/task/batch sınırlarını doğrula; ardışık frame leakage’ini önle.
- Train’e hiç girmemiş bağımsız gerçek çekimi final test için işaretle.
- Gerçek işte en maliyetli hata türlerini sırala: tiny, plate-gap, glare, hand, background, concrete shape.
- Minimum kabul recall/precision veya kaçırma maliyetini belirt.
- 50 FP + 50 FN review’unda gerçek hata, label sorunu veya sınıf dışı nesne ayrımı yap.

Test sonuç görülmeden kilitlenir. Unreal katkısı yalnız `R`, `R+B-1N`, `R+U-1N` koşullarının aynı nano checkpoint/hyperparameter ve üç seed ile frozen gerçek testte kıyaslanmasıyla kabul edilir.

## Göndermen gerekmeyenler

- Lisansı belirsiz internet asset’i toplama.
- CAD’i Unreal-ready temizleme; ham ama birimi belli model daha değerlidir.
- Binlerce bbox’ı yeniden çizme; önce 20 referans ve 100-kare QC yapacağız.
- Gizli tesis arka planını paylaşmak zorunda değilsin; yalnız hazne crop’u veya maskeli arka plan yeterli.

Her girdi kaynak/lisans/hash ile kaydedilecek. Ölçülmeyen parametre config’te `fallback assumption` olarak kalacak; teknik PASS, görsel gerçekçilik ve model faydası ayrı raporlanacak.
