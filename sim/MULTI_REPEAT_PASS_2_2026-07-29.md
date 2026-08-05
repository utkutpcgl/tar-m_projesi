# EBIS gerçekçilik tekrarı — pass 2/6

Tarih: 2026-07-29  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: bir adet bounded, kanıt-temelli form/kâğıt ve fiziksel RFID
örtülme iyileştirme turu.

## Sonuç

Bu turda en yüksek değerli güvenli açık olarak, gerçek küp numunelerde sık
görülen kirli/buruşuk basılı form ile formun altında tamamen veya yalnız ucu
görünecek biçimde kalan RFID seçildi. Blender ve Unreal'a aynı semantik
sözleşme taşındı: form fiziksel bir **non-target occluder**; bbox kaynağı
formun geometrik tahmini değil, örtme sonrası ayrı RFID visible-instance
maskesidir.

Seçilen iki final pilot da teknik validator'dan geçti, gerçek pikseller
tam çözünürlükte açıldı ve kaynak/çıktıların seçilmiş yerel–3090 SHA-256
değerleri eşleşti. Blender formu düzensiz mesh, lif/kir/buruşma normal'i,
baskı satırları, okunmayan el yazısı ve bant aldı. Unreal ilk denemedeki
tan/parşömen görünümünü düşüren V2 materyali, basılı/el yazılı katmanları,
bantları ve RFID bağlantılı kısmi/tam örtme metadata'sını aldı.

Bu sonuç “gerçek forma daha yakın kontrollü varyasyon ve daha doğru
occlusion label sözleşmesi” ile sınırlıdır. Taranmış gerçek form dokusu,
ağır kırışıklık/yırtık, ölçülmüş kamera/ışık, depth, güncel MCP turu,
100-kare iki kişilik QC ve YOLO ablation bu turda yoktur. Fotogerçekçi
dijital ikiz, engine üstünlüğü veya model kazancı iddia edilmez.

## Sıfırdan yeniden incelenen referans pikselleri

Önceki turdaki seçime güvenilmeden yeni bir zaman/görev örneklemi açıldı:

- [dokuz LED RGB kare](reports/qc/multi_repeat_pass2_led_fresh.png):
  task 9–14, cam-10/cam-11; silindir, küp, hasarlı uç, farklı kapı/operatör
  durumları ve form bulunan örnekler;
- [yedi IR/gri ton kare](reports/qc/multi_repeat_pass2_ir_fresh.png):
  `REF-65250`, `REF-65423`, `REF-65080`, `REF-65218`; 2024-12–2025-02,
  iki kamera ve farklı makine/zaman örnekleri;
- [gerçek LED + IR + iki final engine sheet'i](reports/qc/multi_repeat_pass2_reference_blender_unreal.png).

IR renk, roughness veya exposure kalibrasyonu için kullanılmadı. Zamana ve
makineye rağmen sabit kalan hazne, büyük iki dairesel tabla, access-cover,
kapı/kamera görüşü ve operatör örtülmesi topolojisini çapraz kontrol etmek
için kullanıldı.

Yeni RGB örneklemde en belirgin tekrar eden fark şuydu: cube numunelerin
önünde düz bir dijital kart değil, yıpranmış baskılı form, bant, el yazısı,
kat izi ve düzensiz kenar bulunuyor. RFID bazen bu formun arkasında tamamen
kalıyor, bazen küçük turuncu uç görünüyor. Bu categorical boşluk,
ölçülmemiş geometriyi yeniden tahmin etmekten daha güvenli olduğu için
pass 2 müdahalesi seçildi.

## Uygulanan değişiklikler

### Blender

[`generate_ebis.py`](ebis-blender/scripts/generate_ebis.py) v1.7.5:

- düz box form yerine `7×5` kontrollü düzensiz grid mesh; küçük kenar
  jitter'ı, curl/fold, `Solidify` ve `Bevel`;
- kirli/sıcak kâğıt tabanı, ince lif ile geniş buruşma bump zinciri;
- 3–6 deterministik, okunabilir kişisel veri üretmeyen el yazısı stroke'u;
- baskı satırları ve bant katmanları;
- metadata'da yüzey profili, baskı/el yazısı/bant sayıları ve bağlı RFID
  örtülme modu;
- tüm form parçaları non-target; yalnız gerçek görünür RFID instance maskesi
  bbox üretir.

Kontrol parametreleri
[`ebis_led_v2.json`](ebis-blender/configs/ebis_led_v2.json) içindedir.
Silindire form uydurulmadı: ölçülmemiş bir curved-card yaklaşımı daha güçlü
bir sentetik ipucu üreteceği için bu tur cube-only bırakıldı.

İlk `realism_v5_3_paper_p2_54120` tanı koşusu baskı ve el yazısını
gösterdi fakat form silüeti fazla steril kaldı. Düzeltmeden sonraki
`p2b` final adaydır; ilk koşu release değildir.

### Unreal

[`ebis_scene.py`](unreal-ebis/Content/Python/ebis_scene.py):

- `M_UsedPaperFormV2`, `M_PaperInkV1` ve `M_DirtyPaperTapeV1`;
- cube-front form, satır, okunmayan el yazısı stroke'u ve 2–4 bant;
- bağımsız form veya `sample_front` RFID'ye bağlı form;
- `partial_tip_visible` ve `fully_hidden` fiziksel örtme modları;
- `paper_labels` ile RFID `paper_occlusion` arasında iki yönlü metadata
  bağlantısı;
- bağlı hedefi kendi mesh'iyle değil, isolated visible/amodal pass ile
  değerlendiren partition akışı.

[`build_visible_bboxes.py`](unreal-ebis/scripts/build_visible_bboxes.py)
`paper_links_checked` ve `paper_occlusion_counts` alanlarını doğrular;
bağlı RFID yoksa veya modlar uyuşmazsa validator hata verir.

İlk `realism_r7_paper_p2_58320` tanı koşusundaki V1 form fazla tan ve
yüksek kontrastlı parşömen gibi okundu. Aynı seed/geometri korunarak daha
düşük chroma/kontrastlı V2 üretildi; `p2b` final adaydır.

## Seçilen Blender pilotu

- Run:
  [`realism_v5_3_paper_p2b_54120`](ebis-blender/output/realism_v5_3_paper_p2b_54120).
- Görsel:
  [8-kare contact sheet](ebis-blender/reports/qc/realism_v5_3_paper_p2b_54120_contact_sheet.png)
  ve [tam çözünürlük form karesi](ebis-blender/output/realism_v5_3_paper_p2b_54120/partitions/exclude/images/ebis_camera_angled_054123.png).
- Validator:
  [`PASS`](ebis-blender/output/realism_v5_3_paper_p2b_54120/validation.json);
  8/8 kare, iki kameradan 4'er kare, 22 fiziksel RFID, 38 binary maske,
  54 dosya hash kontrolü, `4 standard / 2 hard / 2 exclude`.
- Form dağılımı: 3 bağımsız, 1 RFID bağlantılı `partial_tip_visible`;
  1 bağlantı doğrulandı.
- Render: RTX 3090 OptiX, `1280×720`, 64 spp; toplam `45,622 s`.
- Kaynak SHA-256:
  `generate_ebis.py = 8780bd78…9a04`,
  raw config `b6a4b567…31d`, canonical config `9ecc3f08…16f`.
- Pin:
  [release manifest](ebis-blender/evidence/release/realism_v5_3_paper_p2b_54120_manifest.json).

Bir talep edilen partial-tip hedefi başka fiziksel occluder nedeniyle
görünürlüğünü kaybetti; metadata'da kaldı ve normal YOLO satırına
sızmadı. Bu beklenen güvenli davranış validator uyarısıdır.

## Seçilen Unreal pilotu

- Run:
  [`realism_r7_paper_p2b_58320`](unreal-ebis/output/realism_r7_paper_p2b_58320).
- Görsel:
  [8-kare contact sheet](unreal-ebis/reports/qc/assets/realism_r7_paper_p2b_58320_contact_sheet.png)
  ve [tam çözünürlük form karesi](unreal-ebis/output/realism_r7_paper_p2b_58320/raw/images/ebis_camera_angled_058321.png).
- Validator:
  [`PASS`](unreal-ebis/output/realism_r7_paper_p2b_58320/validation.json);
  8/8 kare, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  30 visible + 30 amodal maske, `2 standard / 4 hard / 2 exclude`.
- Form dağılımı: 1 bağımsız, 2 RFID bağlantılı
  `partial_tip_visible`; 2 bağlantı doğrulandı.
- RFID durumları: `9 standard`, `6 hard`, `2 exclude`,
  `1 fully hidden`, `4 outside frame`.
- Dört camera×shape concrete bbox hücresi de görsel-fit kapısında
  normalize koordinatta `abs ≤0,06`.
- Engine: UE 5.8.1 / RTX 3090, `1280×720`, depth kapalı;
  engine süresi `23,714 s`.
- Kaynak SHA-256:
  `ebis_scene.py = f707dfdc…d1f2`,
  config `45f8ca9b…4570`,
  validator `f22f4583…d75`.
- Pin:
  [release manifest](unreal-ebis/evidence/release/realism_r7_paper_p2b_58320_manifest.json).

## Gerçek piksel kontrolü

Makine-okunur audit:
[`multi_repeat_pass2_pixel_audit.json`](reports/qc/multi_repeat_pass2_pixel_audit.json).
ROI'ler tam çözünürlük görüntü açıldıktan sonra elle seçilen yaklaşık
form bölgeleridir; geometrik olarak register değildir ve bir miktar
beton/bant/ink içerir. Değerler yalnız açık kalan görüntü farklarını
gösterir, kalite skoru değildir.

| Bölge | L mean / std | p05 / p95 | Saturation | Mean abs gradient |
| --- | ---: | ---: | ---: | ---: |
| Gerçek cam-10 form+çevre | `0,635 / 0,182` | `0,309 / 0,967` | `0,086` | `0,0365` |
| Blender p2b | `0,799 / 0,137` | `0,516 / 0,897` | `0,133` | `0,0094` |
| Unreal V1 tanı, reddedildi | `0,779 / 0,100` | `0,594 / 0,885` | `0,091` | `0,0188` |
| Unreal V2 final | `0,786 / 0,102` | `0,595 / 0,889` | `0,075` | `0,0165` |

Okuma:

- gerçek ROI'nin luminance aralığı ve lokal gradient'i iki sentetik
  motordan da belirgin yüksek; gerçek formun kat/yırtık/baskısı ile
  betonun agrega hasar kuyruğu hâlâ eksik;
- Unreal V2, aynı seed'deki V1'e göre tan chroma ve yapay yüksek frekanslı
  görünümü düşürdü; bu yalnız seçilen materyal yönünün kontrollü
  düzeltildiğini gösterir;
- Blender formu artık düz primitive değildir fakat fazla parlak, temiz ve
  düzgün; taranmış gerçek form/albedo-normal verisi olmadan kalan fark
  procedural ayarla güvenle kapatılamaz.

## Motorlar arası taşınan sözleşme

İki engine aynı config semantiğini kullanır: cube-only form occurrence,
independent/linked seçim, partial-tip/fully-hidden modları, tip görünürlük
aralığı, baskı/el yazısı/bant sayısı ve “form target değildir” kuralı.
Blender'ın fiziksel düzensiz mesh yaklaşımı Unreal için bir sonraki
geometry hedefidir; Unreal'ın açık `paper_links_checked` doğrulaması da
Blender validator'ına taşındı.

Bu aktarım görsel eşitlik anlamına gelmez. Blender mevcut sahnede hazne ve
LED kimliğini daha tutarlı gösterirken Unreal'ın isolated amodal/visible
pass'i fiziksel örtülme audit'ini daha doğrudan yapar. Render süreleri
aynı pass/render ayarlarını kullanmadığından benchmark olarak
karşılaştırılamaz.

## Yeniden üretim ve doğrulama komutları

Blender final:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action batch --seed 54120 --count 8 \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_3_paper_p2b_54120 \
  --resolution 1280x720 --samples 64 --no-depth'
```

Blender bağımsız yeniden doğrulama:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action validate \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_3_paper_p2b_54120 \
  --expected-count 8 --require-both-cameras'
```

Unreal final ve yerel annotation validator:

```bash
ssh 3090 'cd /home/ankaref/Documents/Projects/simulation/unreal-ebis && \
  ./scripts/run_remote_release.sh realism_r7_paper_p2b_58320 8 58320 1280 720 0'

python3 unreal-ebis/scripts/build_visible_bboxes.py \
  --root unreal-ebis/output/realism_r7_paper_p2b_58320 \
  --config unreal-ebis/configs/ebis_unreal_v1.json
```

Her iki final validator'ı ikinci kez çalıştırıldı. Seçili kaynak, manifest,
validation, temsilî kare ve Unreal generated-content SHA-256 değerleri
yerel ve `/home/ankaref/Documents/Projects/simulation` kopyalarında
eşleşti.

## Kalan materyal açıkları

Öncelik sırasıyla:

1. Gerçek cube/silindir için kalıp yüzü, kırık uç, kenar ve agrega
   photogrammetry/PBR seti; iki engine'de de en güçlü CG ipucu beton.
2. Unreal'da aşırı büyük beyaz üst fascia/tabla, siyah contact bandı ve
   karanlık cam-11: Lumen/normal/shadow debug pass ile geometri ve ışık
   kaynağını ayrıştırmak.
3. Gerçek numune formlarından kişisel veri temizlenmiş scan/atlas,
   alpha-edge, roughness ve normal; lisans/PII kaydıyla.
4. Unreal formunu düz box yerine deforme subdivided mesh yapmak; formun
   betona penetrasyon/floating gate'ini eklemek.
5. Silindire konforme kâğıt ancak gerçek çap, form ölçüsü ve wrap
   davranışı ölçüldükten sonra.
6. Cam-10/cam-11 ChArUco intrinsics/distortion, fixed exposure grey-card,
   empty chamber ve steel-platen referansı.
7. Operatör/el/kol ayrı slice ve fiziksel occluder; normal ana eğitim
   dağılımına oranı gerçek setten ölçülmeden kör eklenmemeli.

## Sonraki en yüksek değerli refinement

Gerçek ölçü paketi gelmezse bir sonraki bounded tur Unreal'ın siyah üst
temas bandını `unlit albedo / world normal / direct-light-only /
shadow-disabled` aynı-seed debug kareleriyle kaynaklarına ayırmalı; yalnız
kanıtlanan normal/geometri/ışık hatası düzeltilmelidir. Paralel Blender
hedefi, mevcut gerçek task-10 form karesinden PII temizlenmiş bir
paper/edge atlası ve kontrollü edge-chip/aggregate patch'idir.

YOLO kabul kapısı değişmedi: frozen gerçek test split, en küçük model ve
en az üç seed ile `R`, `R+B-1N`, `R+U-1N`; gerekiyorsa `R+B+U-1N`.
Özellikle küçük/örtülü RFID slice recall ve gerçek-test mAP güven aralığı
artmadan bu görsel değişiklik model faydası sayılmaz.
