# Blender-EBİS kullanıcı desteği ve kontrollü review protokolü

Bu çalışma mevcut arşivle ve açıkça işaretlenmiş varsayımlarla ilerleyebilir; yeni veri beklemek günlük geliştirmeyi durdurmaz. Yine de aşağıdaki iki kapsam kararı release ve YOLO yorumunun doğruluğu için cevaplanmalıdır. Bunların dışındaki girdiler blocker değil, belirsizliği azaltan yüksek değerli desteklerdir.

## Cevaplanması gereken iki kritik kapsam sorusu

### 1. Hedef makine gerçekten REF-65218 / İvedik profili mi?

Mevcut `v1.7.15` üretici; gri pebbled/hammertone arka ve sol yüzey,
kobalt-mavi sağ panel, dört vidalı servis kapağı, iki dairesel tabla ve
soldaki erişim kapısı olan REF-65218/İvedik görünümünü hedefler.
Arşivdeki bütün `REF*` klasörleri aynı makine değildir; farklı
makinelerin sabit parçalarını tek bir hibrit kutuda birleştirmek doğru
olmaz.

Beklenen tek cümlelik karar:

```text
Hedef makine: REF-65218/İvedik | başka: <klasör/makine kimliği>
```

Bu karar gelene kadar REF-65218 varsayımı sürer ve metadata’da `target_machine_assumption` olarak görünür. Başka makine seçilirse geometri, duvar renkleri, kamera donanımı ve split yalnız o makinenin referanslarıyla yeniden dondurulur.

### 2. Elde tutulan veya hazne duvarına yapıştırılmış tag’ler hedef pozitif mi?

Arşivde tag’in beton üzerinde/tabla aralığında olduğu operasyonel karelerin yanında elde tutulan, duvarda sergilenen veya çok sayıda tag’in test için dizildiği staging kareleri vardır. Bunlar gerçek kullanımda aranmayacaksa training prior’ına ve frozen test metriğine katılmamalıdır.

Beklenen karar:

```text
Pozitif kapsam: yalnız beton/tabla operasyonel | operasyonel + elde/duvarda staging
```

Varsayılan ve önerilen kapsam `yalnız beton/tabla operasyonel`dir. Staging görüntüler istenirse ayrı bir `staged` slice/ablation olur; operasyonel tag-count ve placement dağılımını değiştirmez.

## En yüksek değerli, fakat blocker olmayan girdiler

| Girdi | Minimum kabul edilebilir içerik | Sağladığı somut iyileştirme |
| --- | --- | --- |
| Cam-10/cam-11 SKU ve ayarları | marka/model, native çözünürlük, lens/focal length, exposure/gain/WB, codec | tahmini fisheye, black level ve keskinleştirme yerine sensöre bağlı profil |
| Kamera intrinsics | her kamera için 20–30 geçerli checkerboard/ChArUco frame’i ve baskı manifesti | lens/fisheye ve distortion’ın görsel fit olmaktan çıkıp ölçülü kalibrasyon olması |
| Ölçü/CAD | kutu, kapı, tabla, LED, kamera landmark ölçüleri veya STEP/IGES | perspektif ve parça oranlarının mm tabanlı kilitlenmesi |
| Native RAW eşleri | aynı sahnenin kamera native RGB/IR export’u; mümkünse RAW/DNG veya sıkıştırılmamış frame | exposure, noise, WB, highlight roll-off ve IR topoloji kontrolü |
| Materyal swatch/yakın plan | ölçek ve gri kartla diffuse + grazing-light çekimi | gerçek texel scale, roughness, normal ve renk hedefi |
| Kapı açı serisi | aynı sahne, yaklaşık 0/30/60/90° ve tam açık; açı/cetvel görünür | kapı prior’ı, gerçek occlusion ve dış ortam fill kalibrasyonu |
| Kağıt/RFID yerleşim serisi | görünürlük yüzdesi ve yerleşim türü kaydedilmiş kontrollü örnekler | paper-under-tag/plate-gap dağılımı ve bbox eşiklerinin doğrulanması |
| Kör A/B review | aşağıdaki rubric ile en az owner + bir operatör | estetik beğeni yerine bölgesel, tekrar edilebilir kabul kapısı |

## 30–45 dakikalık minimum çekim paketi

Tek bir makine kimliğiyle çalış. Telefon/kamera uygulamasında HDR, güzelleştirme, portre modu, dijital zoom ve otomatik lens değiştirme kapalı olsun; mümkünse ana `1×` lens kullanılsın. Fotoğrafları mesajlaşma uygulamasıyla sıkıştırmadan, asıl dosya olarak aktar.

1. Kapı tam açıkken haznenin tamamı: karşıdan, cam-10 yönünden ve cam-11 yönünden üç kare.
2. İç genişlik/derinlik/yükseklik, kapı kanadı ve açıklığı: cetvel/metre aynı düzlemde olacak şekilde ayrı kareler.
3. Üst ve alt tabla: çap, kalınlık, boşluk ve merkez eksenini gösteren en az dört ölçü karesi.
4. Üç duvardaki LED kanalı: LED kapalı genel görünüm, opal difüzör kesit yakın planı, segment uzunlukları ve üst tabla seviyesine uzaklık.
5. Boş hazne, küp ve silindir için LED açık/kapalı eşleri; telefon kullanılıyorsa exposure, focus ve white balance iki eş arasında kilitli.
6. Gri pebbled sac, mavi panel, üst/alt tabla, küp ve silindir için bir diffuse ve bir grazing-light yakın plan.
7. Kapı yaklaşık 30°, 60°, 90° ve tam açıkken aynı sample/ışık/kamera durumunu koruyan seri.
8. Gerçek küp/silindir ölçüleri, kağıt boyutu ve RFID fiziksel boyutu.
9. Üst tabla ile temas etmiş bir küp ve bir silindirin üst yük bölgesi:
   önce temizlemeden, cetvel + gri kartla tam karşı ve dört farklı
   grazing-light açısı; mümkünse aynı numunenin yük öncesi/sonrası çifti.

Her dosyanın EXIF’i korunsun. Ad şeması:

```text
YYYYMMDD_<machine>_<cam-or-phone>_<part-or-scene>_<state>_<take>.<ext>
```

Örnek:

```text
20260730_REF65218_phone_upper-platen_diameter_01.dng
20260730_REF65218_cam10_cube_led-on_door-90_03.png
```

Yanına şu alanları taşıyan bir `capture_manifest.csv` bırak:

```text
filename,machine_id,camera_id,timestamp,led_state,door_angle_deg,sample_shape,sample_size_mm,tag_placement,paper_state,exposure,gain,white_balance,notes
```

Bu paket; kutu/tabla/LED oranını, kapı prior’ını, beton temasını, RGB tonal aralığını ve ana materyal hedefini kilitlemeye yeter. Intrinsics ve mikro-PBR için aşağıdaki ideal protokoller gerekir.

## Kamera kalibrasyon protokolü

Her kamera için aynı fiziksel checkerboard veya ChArUco target kullanılmalıdır.

1. Target düz ve rijit zemine basılır; yazdırırken “sayfaya sığdır” kapalıdır.
2. Bir kare kenarı kumpasla ölçülür. Algılanan `inner corners` sayısı ve gerçek kare boyutu manifeste yazılır.
3. 20–30 frame çekilir: merkez, dört köşe, farklı roll/pitch/yaw ve haznenin ön/orta/arka derinlikleri. Target görüntünün yaklaşık %20–80’ini dolduran çeşitlilikte olmalıdır.
4. Motion blur, kısmi target, dijital crop/zoom, focus veya çözünürlük değişimi olan frameler ayrılır.
5. Kamera sökülmez; sökülürse extrinsics yeni oturum sayılır.
6. Source PDF hash’i ve bütün kabul edilen frame hash’leri kaydedilir.

Manifest:

```json
{
  "camera_id": "cam10_or_cam11",
  "target_type": "checkerboard_or_charuco",
  "inner_corners_cols": 0,
  "inner_corners_rows": 0,
  "square_size_mm": 0.0,
  "printed_square_size_mm_verified": 0.0,
  "native_width": 0,
  "native_height": 0,
  "focus_mode": "fixed",
  "source_file": "calibration_target.pdf",
  "source_file_sha256": "..."
}
```

Board ölçüsü/hash’i yoksa sonuç `visual lens fit` olarak kalır; metrik intrinsics diye sunulmaz. Geçerli kalibrasyon cam-10 ve cam-11’in ayrı distortion, principal point, FOV ve mount jitter marjlarını daraltır; bbox ile RGB’nin aynı warp’tan geçmesini doğrular.

## Materyal ve ışık referansı çekim protokolü

Her yüzey için kamerayı otomatik HDR kapalı, sabit ISO/exposure/WB ve mümkünse RAW/DNG’de kullan:

1. Yüzeyi kadrajın çoğunu dolduran, kameraya yaklaşık dik diffuse kare.
2. Aynı bölgenin 30–45° grazing-light karesi.
3. Cetvel veya bilinen ölçek nesnesi bulunan kare.
4. Gri kart/ColorChecker bulunan renk karesi.
5. Metal için ışık yönü değiştirilmiş üç kare; beton için kalıp yüzü, uç yüzü, kenar ve varsa nemli/kirli durum ayrı.

Öncelik sırası: gri pebbled iç sac → üst ve alt tabla → opal difüzör → küp/silindir beton → mavi panel → kağıt/tape → RFID film/anten.

Beton üst yük bölgesi ayrı bir materyal setidir: numunenin gövde ortası,
tabla temasına 0–20 mm kalan bant ve üst yüz aynı exposure/WB ile
çekilmelidir. Ochre/koyu artık, agrega kopması ve yönlü streak aynı
ölçekli karede ayrılabilsin. Mevcut procedural load-zone profili bu
çekimler gelene kadar yalnız bounded proxy'dir.

LED için aynı tripod/kamera durumunda `LED kapalı`, `yalnız LED`, `LED + normal dış ortam` seti çekilir. Native kamera export’u tercih edilir; ekrandan telefonla fotoğraf çekilmez. Lux metre varsa sample üstü, sample ortası ve sample altı ölçülür. Yoksa EXIF/exposure/gain sabit çiftler bile highlight ve gölge oranını kalibre eder. IR frameler RGB renk/pozlama hedefi değildir; değişmeyen geometri, kamera görüşü ve occlusion kanıtı olarak kullanılır.

## Kağıt, RFID ve kısmi görünürlük protokolü

Kontrollü çekimlerin staging olduğu manifeste açıkça yazılmalı; staging frekansı gerçek operasyon prior’ı sanılmamalıdır.

Her sample shape ve kamera için aşağıdakilerden en az üç tekrar:

- tag tamamen görünür, kağıt yok;
- tag kağıt altında yaklaşık %15, %30 ve %50 görünür;
- tag kağıt altında tamamen kapalı;
- tag beton ile üst/alt tabla arasında yalnız uç kısmı görünür;
- tag sample ön/yan yüzeyinde, frame kenarında ve gerçek kullanım varsa katlanmış/kalkmış durumda;
- kağıt var ama tag yok; false-positive kontrolü;
- baskılı kağıt, boş kağıt ve tape kenarı varyantı.

Her örneğe benzersiz instance kimliği ver:

```text
scene_id,tag_id,placement,paper_relation,estimated_visible_fraction,operator_says_positive,notes
```

`estimated_visible_fraction` bbox üretmek için doğrudan kullanılmaz;
instance-aware görünür maskeyle kontrol edilir. Tam kapalı tag label
almaz. Kısmi tag tek instance kalır; birden çok görünür parçaya ayrı bbox
verilmez. Mevcut `v1.7.15` kağıt sistemi küp yüzeyinde kısmi/tam örtmeyi
destekler. Silindire yüzeyi gerçekten takip eden conformed paper henüz
release kapsamı değildir; düz levhayı silindire yüzdürmek yerine
UV/curve/deform + mask hizası doğrulanana kadar ertelenmiştir.

## Zaman çeşitliliği ve gerçek referans seçimi

Tek bir ardışık burst gerçek dağılımı temsil etmez. Review/fit seti en az:

- aynı makine için erken/orta/geç tarih;
- cam-10 ve cam-11;
- LED RGB ve REF IR;
- küp/silindir;
- kapı tam açık/kısmi;
- temiz/kirli tabla ve farklı beton yüzeylerinden

stratified seçilir. Aynı capture’ın ardışık frameleri train/val/test arasında bölünmez. Bir makinenin materyali başka makinenin geometrisiyle eşlenmez. Referans listesi dosya yolu, timestamp, kamera, makine kimliği ve SHA-256 ile dondurulur.

## Kör A/B review

Her turda gerçek, önceki sentetik ve aday sentetik crop’lar motor adı olmadan karıştırılır. Aynı dört fixed seed ve iki kamera korunur; bir turda yalnız bir katman değişir:

| Tur | Kilitli olan | Değerlendirilen |
| --- | --- | --- |
| A — geometri | clay materyal, nötr ışık | kutu, kapı, kamera, tabla, LED, sample temas/oran |
| B — materyal | kabul edilmiş geometri ve kamera | sac, çelik, beton, kağıt, RFID |
| C — ışık/kamera | kabul edilmiş geometri/materyal | LED halation, shadow floor, exposure, fisheye, vignette |
| D — detection | release RGB/mask | görünürlük, bbox sıkılığı, exclude/hard/standard partition |

Her kare için şu kısa rubric doldurulur:

```text
reviewer:
dosya/seed:
hangisi daha gerçek: A | B | eşit
geometri: 1..5
materyal: 1..5
ışık: 1..5
kamera/lens: 1..5
RFID-bbox kararı: doğru | yanlış | uygulanamaz
en büyük fark:
kanıt olan gerçek referans:
önem: blocker | yüksek | orta | düşük
karar: reject | düzelt-yeniden-göster | kabul
```

“Biraz daha gerçekçi” yerine bölge, yön ve referans belirt: “üst tabla fazla pürüzsüz; REF X’te radial machining ve merkez dışı mat çimento lekesi var” gibi. İki reviewer’ın ortak `blocker/yüksek` bulguları önce gelir. Görsel review PASS için owner ve bir operatörün ayrı ayrı overall medyanı `≥3/5`, dört ana eksenin ortak medyanı `≥3/5` ve açık blocker sayısı `0` olmalıdır. Bu eşik yalnız production öncesi insan kapısıdır; fotogerçekçilik veya YOLO kazancı kanıtı değildir.

## YOLO değerlendirmesi için kullanıcı desteği

- Frozen test olacak bağımsız gerçek capture/session’ı işaretle.
- Operasyonel pozitif kapsamını ve en pahalı FN türünü sırala: tiny tag, paper-under-tag, plate-gap, glare, kapı/duvar staging vb.
- Cam-10/cam-11, küp/silindir, tag-size, occlusion ve paper slice’larında minimum kabulü yaz.
- 50 FP + 50 FN review’unda `gerçek hata`, `etiket hatası`, `kapsam dışı`, `ambiguous` ayrımı yap.
- Model koşullarını isim görmeden, aynı frozen gerçek test üzerinde review et.

Test sonuç görülmeden kilitlenir. Sentetik fayda yalnız aynı split, aynı nano checkpoint/ayar, aynı update bütçesi ve çoklu seed sonuçlarıyla raporlanır. Renderın güzel görünmesi, validator PASS veya tek seed AP artışı model kazancı sayılmaz.

## Güvenlik ve teslim

Gizli tesis alanlarını paylaşmak gerekmiyorsa yalnız hazneyi crop’la veya arka planı maskeli gönder. CAD’i render-ready temizlemek ve yüzlerce kareye elle bbox çizmek gerekmez; ham ama birimi belli geometri, native frame ve 20 kontrollü referans daha değerlidir. Her gelen dosyanın kaynak, lisans/erişim, hash ve hangi varsayımı kaldırdığı kaydedilir. Ölçülmeyen alan `fallback assumption` olarak kalır.
