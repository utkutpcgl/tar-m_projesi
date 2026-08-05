# EBIS gerçekçilik tekrarı — pass 3/6

Tarih: 2026-07-30  
Run: `multi-repeat-simulation-realism-6da1ae98b227`  
Kapsam: bir adet bounded, kanıt-temelli üst baskı tablası ve ince
U-difüzör/temas ışığı iyileştirme turu.

## Sonuç

Bu turda en büyük ortak ve güvenle düzeltilebilir açık, gerçek makinedeki
koyu dairesel üst baskı tablasının iki engine'de geniş beyaz ışıklı
tavan/fascia gibi okunmasıydı. Yeni ve zamana yayılmış LED ile IR
pikselleri, değişmeyen parçanın koyu ve kullanılmış bir çelik temas diski
olduğunu; ışığın ise üç duvar boyunca tabla alt hizasını izleyen ince bir
U-difüzörden geldiğini doğruladı.

Blender ve Unreal'a aynı fiziksel sözleşme taşındı:

- `400 mm` görsel-fit üst tablanın altında `394 mm` çaplı, çok ince,
  koyu fırçalanmış çelik temas yüzü;
- beton/RFID filmiyle fiziksel çakışmayı önleyen doğrulanmış küçük temas
  boşluğu;
- kalın ışıklı fascia yerine üç duvarı tam boy izleyen ince difüzör;
- her kare metadata'sında çap, kalınlık, alt kot, boşluk ve materyal
  profili;
- validator'da eksik/yamuk temas yüzü ve geçersiz temas boşluğu için
  hard-fail.

Final Blender ve Unreal pilotları RTX 3090'da sekizer kare üretildi,
iki kamera ile küp/silindir dengesi sağlandı, actual pixels tam
çözünürlükte açıldı ve bağımsız validator ikinci kez çalıştırıldı.
Seçili 14 kaynak/çıktı/asset'in yerel ve 3090 SHA-256 değerleri eşleşti.

Bu sonuç yalnız üst tabla/LED kategorik hatasının düzeltilmesidir.
Ölçülmüş çelik BRDF/roughness, CAD, kamera intrinsics/distortion,
LED lux/CCT/CRI, depth, güncel MCP round-trip, 100-kare iki kişilik QC ve
YOLO ablation bu turda yoktur. Fotogerçekçi dijital ikiz, engine
üstünlüğü veya model kazancı iddia edilmez.

## Sıfırdan yeniden incelenen referans pikselleri

Önceki pass seçimine güvenilmeden yeni örneklem açıldı:

- [13 LED RGB kare](reports/qc/multi_repeat_pass3_led_fresh.png):
  `160126-ivedik-ledli-part-1` içinden 2026-01-16 zaman süpürmesi,
  `Kamera 01` ve `Kamera 02`; küp, silindir, operatör/kapı ve farklı
  RFID durumları;
- [16 IR/gri ton kare](reports/qc/multi_repeat_pass3_ir_fresh.png):
  `REF-65166`, `REF-65171`, `REF-65244`, `REF-65260`, `REF-65553`
  CAM10/CAM11 grupları; 2025-01-02–2025-01-27 aralığı;
- [LED + IR + iki final engine sheet'i](reports/qc/multi_repeat_pass3_reference_blender_unreal.png).

IR görüntüler renk, exposure veya roughness kalibrasyonu için
kullanılmadı. Farklı makine ve tarihlerde sabit kalan kapalı cabinet,
iki büyük dairesel tabla, ince üst sınır ışığı, access cover ve iki kamera
topolojisini ayırmak için kullanıldı.

En açık tekrar eden bulgu şuydu: üstteki değişmeyen parça parlak beyaz
bir levha veya ışık paneli değil, numuneyi alt diskle sıkıştıran geniş,
koyu, kullanılmış çelik disktir. LED yalnız disk/duvar sınırında ve betonun
üst temas bölgesinde dar highlight üretir. Gerçek temsilî
[`Kamera 01` karesi](260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/160126-ivedik-ledli-part-1/images/train/vlcsnap-2026-01-16-17h20m18s095.png)
tam çözünürlükte tekrar açıldı.

## Uygulanan değişiklikler

### Blender

[`generate_ebis.py`](ebis-blender/scripts/generate_ebis.py) v1.7.6:

- `upper_contact_face` adlı koyu, metalik, anisotropic ve çok ölçekli
  işleme izi taşıyan materyal;
- üst tablanın altında `0,394 m` çaplı, `0,0006 m` kalınlıklı ayrı
  temas diski;
- nominal tabla altından `0,0001 m` uzama ve en kötü RFID kalınlığının
  üzerinde `0,0004 m` fiziksel boşluk;
- config sınırları: kalınlık `0,2–1,5 mm`, çap oranı `0,94–1,00`,
  uzama `≥0` ve kalınlıktan küçük;
- scene contract, kare metadata'sı ve dataset validator'da temas diski
  varlığı/geometrisi/boşluğu;
- her final karede `upper_contact_faces_checked=8`.

Kontrol değerleri
[`ebis_led_v2.json`](ebis-blender/configs/ebis_led_v2.json) içindedir.
`0,4 m` tabla ve yeni milimetre değerleri CAD ölçümü değil, referans
görünümüne bağlı bounded visual-fit fallback'idir.

### Unreal

[`ebis_scene.py`](unreal-ebis/Content/Python/ebis_scene.py) ve
[`ebis_unreal_v1.json`](unreal-ebis/configs/ebis_unreal_v1.json):

- `M_UpperContactFaceV2` koyu, pürüzlü, kullanılmış çelik materyali;
- üst tablanın altında `39,4 cm` çap, `0,06 cm` kalınlık,
  `0,01 cm` uzama ve `0,04 cm` fiziksel boşluk;
- U-difüzör yüksekliği `2,6 cm → 0,9 cm`, kanal yüksekliği
  `5,4 cm → 2,4 cm`, tabla altına göre merkez offset'i
  `2,25 cm → 0,6 cm`;
- metadata ve validator'da temas diski/boşluk sözleşmesi;
- ilk offscreen capture'da mevcut procedural materyalin varsayılan
  checker'a düşmemesi için synchronous material recompile.

[`build_visible_bboxes.py`](unreal-ebis/scripts/build_visible_bboxes.py)
temas diskinin sekiz karede de sözleşmeye uyduğunu doğrular. Tanı
sırasında RFID fiziksel kalınlığının `size_cm[2]` yerine doğru eksen olan
`size_cm[1]` ile denetlenmesi düzeltildi; böylece validator yanlış alarm
vermek yerine gerçek sample-gap sözleşmesini kontrol eder.

## Tanı koşuları ve reddedilen durumlar

- Blender `realism_v5_4_platen_p3_diag_54121`, önceki pass ile aynı seed
  ve kamera kullanılarak kontrollü before/after üretildi. Geometri ve
  ışık yönü kabul edildi; bu tek kare release değildir.
- Unreal `realism_r8_platen_p3_diag_58321` ilk V1 denemesinde temas yüzü
  gereğinden siyah, basılı form ise ilk offscreen capture'da varsayılan
  checker görünümündeydi. Release olarak reddedildi.
- Unreal `realism_r8_platen_p3_diag2_58321`, V2 temas materyali ve
  synchronous recompile sonrasında aynı seed ile tekrar üretildi.
  Checker kayboldu, form bölgesi önceki pass ile aynı piksel değerlerine
  döndü ve temas yüzü orta-koyu oldu. Bu kontrollü tanıdır; final release
  ayrı ve dengeli sekiz seed'dir.

Tanı koşularının saklanma nedeni başarısız denemeyi üretim adayı gibi
göstermek değil, değişiklik ile kabul kararının izlenebilir olmasıdır.

## Seçilen Blender pilotu

- Run:
  [`realism_v5_4_platen_p3_54240`](ebis-blender/output/realism_v5_4_platen_p3_54240).
- Görsel:
  [8-kare contact sheet](ebis-blender/reports/qc/realism_v5_4_platen_p3_54240_contact_sheet.png),
  [cam-10/silindir](ebis-blender/output/realism_v5_4_platen_p3_54240/partitions/hard_occlusion/images/ebis_camera_angled_054241.png)
  ve [cam-11/küp](ebis-blender/output/realism_v5_4_platen_p3_54240/partitions/hard_occlusion/images/ebis_camera_door_054240.png).
- Validator:
  [`PASS`](ebis-blender/output/realism_v5_4_platen_p3_54240/validation.json);
  8/8 kare, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  21 fiziksel RFID, 37 binary maske ve 53 dosya hash kontrolü.
- Partition: `3 standard / 5 hard / 0 exclude`; hard kareler ana train'e
  otomatik karışmaz.
- Temas diski: 8/8 metadata ve geometri/boşluk kontrolü.
- Render: Blender 4.5.12 LTS, RTX 3090 OptiX, `1280×720`, 64 spp;
  toplam `46,229 s`, ortalama `5,779 s/kare`.
- Kaynak SHA-256:
  `generate_ebis.py = 8005ff0a…7cfc`,
  raw config `c39e02d1…af06`,
  canonical config `3bda0691…76cd`.
- Pin:
  [release manifest](ebis-blender/evidence/release/realism_v5_4_platen_p3_54240_manifest.json).

## Seçilen Unreal pilotu

- Run:
  [`realism_r8_platen_p3_58440`](unreal-ebis/output/realism_r8_platen_p3_58440).
- Görsel:
  [8-kare contact sheet](unreal-ebis/reports/qc/assets/realism_r8_platen_p3_58440_contact_sheet.png),
  [cam-10/silindir](unreal-ebis/output/realism_r8_platen_p3_58440/raw/images/ebis_camera_angled_058447.png)
  ve [cam-11/küp](unreal-ebis/output/realism_r8_platen_p3_58440/raw/images/ebis_camera_door_058440.png).
- Validator:
  [`PASS`](unreal-ebis/output/realism_r8_platen_p3_58440/validation.json);
  8/8 kare, 4 cam-10 + 4 cam-11, 4 cube + 4 cylinder,
  31 visible + 31 amodal maske.
- Partition: `3 standard / 3 hard / 2 exclude`.
- Temas diski: 8/8 metadata ve geometri/boşluk kontrolü.
- Dört camera×shape concrete bbox hücresinin her birinde `N=2` var ve
  referans hedefe normalize koordinatta `abs ≤0,06` görsel kapısında.
- Engine: UE 5.8.1 / RTX 3090, `1280×720`, depth kapalı;
  engine batch süresi `31,96 s`.
- RGB sensör manifesti:
  [`PASS`](unreal-ebis/output/realism_r8_platen_p3_58440/raw/sensor_response_manifest.json);
  geometri, mask ve depth değiştirilmedi.
- Kaynak SHA-256:
  `ebis_scene.py = 153f9a07…2465`,
  config `1ee2b6b9…e08e`,
  validator `212c90a0…494e`.
- Pin:
  [release manifest](unreal-ebis/evidence/release/realism_r8_platen_p3_58440_manifest.json).

## Gerçek piksel kontrolü

Makine-okunur audit:
[`multi_repeat_pass3_pixel_audit.json`](reports/qc/multi_repeat_pass3_pixel_audit.json).
ROI'ler full-resolution piksel açıldıktan sonra elle seçilen yaklaşık üst
tabla bantlarıdır. Görüşler geometrik olarak register değildir ve bir
miktar sample/LED/duvar/overlay içerir; değerler kalite skoru değildir.

| Üst bant | L mean / std | p05 / p95 | Dark `≤0,10` | Clip `≥0,95` | Mean gradient |
| --- | ---: | ---: | ---: | ---: | ---: |
| Gerçek LED cam-01 | `0,399 / 0,216` | `0,150 / 0,739` | `0,022` | `0,030` | `0,0124` |
| Blender p2 aynı-seed önce | `0,494 / 0,234` | `0,159 / 0,904` | `0,015` | `0,031` | `0,0065` |
| Blender p3 aynı-seed sonra | `0,427 / 0,256` | `0,083 / 0,874` | `0,178` | `0,025` | `0,0065` |
| Blender p3 release temsilî | `0,478 / 0,251` | `0,105 / 0,917` | `0,039` | `0,029` | `0,0077` |
| Unreal p2 aynı-seed önce | `0,530 / 0,328` | `0,020 / 0,934` | `0,198` | `0,015` | `0,0088` |
| Unreal p3 aynı-seed sonra | `0,365 / 0,311` | `0,020 / 0,860` | `0,352` | `0,001` | `0,0125` |
| Unreal p3 release temsilî | `0,343 / 0,302` | `0,020 / 0,843` | `0,374` | `<0,001` | `0,0148` |

Kontrollü aynı-seed üst bant mean absolute RGB farkı Blender'da `0,067`,
Unreal'da `0,224` oldu. Bu, hedeflenen yüzün gerçekten piksellere
yansıdığını gösterir; değişimin otomatik olarak “daha gerçekçi” veya
YOLO için daha faydalı olduğunu göstermez.

Tam çözünürlük incelemesinin önemli sınırı şudur: Blender'da tabela/LED
kimliği ve genel yüzeyler daha tutarlı olsa da gerçek çeliğin radial
işleme izi ve aşınması ölçülmüş değildir. Unreal beyaz fascia ipucunu
azalttı fakat duvar/tabla geometrisi, beton, ışık dağılımı ve sensör
gürültüsü hâlâ kuvvetli CG ipucu taşır.

## Motorlar arası taşınan sözleşme

İki engine aynı kavramları taşır:

- ayrı `upper_contact_face`;
- `0,985` çap oranı;
- çok ince temas yüzü ve beton/RFID üzerinde pozitif boşluk;
- koyu `dark_brushed_used_steel` materyal profili;
- üst tabla alt hizasında ince tam-boy üç-duvar U-difüzör;
- her karede metadata ve validator hard-gate.

Blender'ın materyal ayrıştırması Unreal V2 için yön verdi. Unreal'da
yakalanan “ilk capture'da procedural material fallback” sorunu da ortak
bir teslim dersi oldu: engine'de asset bulunması, gerçek render
pikselinde doğru shader'ın kullanıldığını kanıtlamaz; final kare mutlaka
açılmalıdır.

Bu aktarım görsel eşitlik değildir. Render süreleri farklı pass, temporal
history ve annotation iş yükleri içerdiğinden engine benchmark'ı olarak
kullanılamaz.

## Yeniden üretim ve doğrulama komutları

Blender final:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action batch --seed 54240 --count 8 \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_4_platen_p3_54240 \
  --resolution 1280x720 --samples 64 --no-depth'
```

Blender bağımsız yeniden doğrulama:

```bash
ssh 3090 '/home/ankaref/Documents/Projects/simulation/.tools/blender-4.5.12-linux-x64/blender \
  -b --factory-startup \
  --python /home/ankaref/Documents/Projects/simulation/ebis-blender/scripts/generate_ebis.py -- \
  --config /home/ankaref/Documents/Projects/simulation/ebis-blender/configs/ebis_led_v2.json \
  --action validate \
  --output /home/ankaref/Documents/Projects/simulation/ebis-blender/output/realism_v5_4_platen_p3_54240 \
  --expected-count 8 --require-both-cameras'
```

Unreal final ve bağımsız yerel annotation validator:

```bash
ssh 3090 'cd /home/ankaref/Documents/Projects/simulation/unreal-ebis && \
  ./scripts/run_remote_release.sh realism_r8_platen_p3_58440 8 58440 1280 720 0'

python3 unreal-ebis/scripts/build_visible_bboxes.py \
  --root unreal-ebis/output/realism_r8_platen_p3_58440 \
  --config unreal-ebis/configs/ebis_unreal_v1.json
```

Her iki validator ikinci kez çalıştırıldı. Seçili 14 source/config,
run-manifest, validation, temsilî kare ve Unreal generated-content dosyası
için yerel ile
`/home/ankaref/Documents/Projects/simulation` SHA-256 karşılaştırması
`CORE_LOCAL_REMOTE_SHA256_PARITY_OK files=14` verdi.

## Kalan materyal açıkları

Öncelik sırasıyla:

1. Gerçek cube/silindir için kalıp yüzü, agrega, kırık uç ve kenar
   photogrammetry/PBR seti. İki engine'de de en kuvvetli CG ipucu
   betondur; Blender fazla düzgün, Unreal fazla düşük-frekanslı ve
   plastiksi kalır.
2. Cam-10/cam-11 ChArUco intrinsics/distortion, aynı exposure grey-card,
   empty-chamber ve boş steel-platen referansı. Fisheye ve pose hâlâ
   visual-fit'tir.
3. Üst/alt çelik disk için polarize/cross-polarized albedo, normal,
   roughness ve radial machining/wear capture. Mevcut koyu renk doğru
   kategori yönüdür, ölçülmüş BRDF değildir.
4. Unreal cabinet'te gerçek panel bevel/conta/kapak/kapı derinliği,
   daha ince LED housing ve cam-11 global lighting. Mevcut basic
   primitive'ler piksellerde belirgin kalır.
5. Blender'da gerçek concrete high-frequency aggregate/chip kuyruğu,
   kapı camı/conta ve workshop backplate; mevcut procedural yüzey iyi
   baseline olsa da scan değildir.
6. PII temizlenmiş gerçek basılı form/kenar atlası ve silindire konforme
   kâğıt davranışı; ölçü olmadan curved card eklenmemelidir.
7. Güncel source hash'leri için depth + MCP + aynı-seed determinism ve
   32-kare düşük maliyetli distribution gate.

## Sonraki en yüksek değerli refinement

Bir sonraki bounded tur için en yüksek değer, yeni renk ayarı değil,
**beton yüzey frekans/hasar ayrıştırmasıdır**. Aynı gerçek cube ve
silindirin:

- orta yüz;
- kalıp izi;
- keskin/çipli kenar;
- üst temas ve alt temas;
- kuru/nemli yüzey

crop'ları çıkarılıp gerçek ile iki engine'in power/gradient ve edge
profilleri karşılaştırılmalıdır. Güvenle kanıtlanan eksik frekans ve
hasar kuyruğu, Blender procedural katmanına ve Unreal tileable
normal/roughness atlasına aynı bounded contract ile taşınmalıdır.

Kamera kalibrasyon paketi kullanıcıdan gelirse beton turundan önce
gelmelidir; lens/pose hatası bütün materyal kararlarını bozar.

YOLO kabul kapısı değişmedi: frozen gerçek test split, en küçük model ve
en az üç seed ile `R`, `R+B-1N`, `R+U-1N`; gerekirse `R+B+U-1N`.
Küçük/örtülü RFID slice recall, concrete AP ve gerçek-test güven aralığı
artmadan bu görsel değişiklik model faydası sayılmaz.
