# Simulation lessons learned

Son kapsam denetimi: `2026-08-01`. Bu belge, gerçekçi Blender/Unreal
simülasyonu için projenin **kalıcı karar ve know-how kaynağıdır**. Exact
parametre, hash ve tekil koşu istatistikleri config/manifest/validation
dosyalarında kalır; burada bunlardan tekrar kullanılacak yöntem, sınır,
başarılı yaklaşım ve failure pattern'leri birikir. EBIS Blender ve
Unreal-EBIS sonuçları gerçek render/label kanıtına dayanır. Blender-tren,
Unreal-tren ve tarım bölümleri açıkça plan-temellidir; deneysel sonuç veya
engine benchmark'ı değildir.

## Belgenin otoritesi ve kanıt dili

- Güncel detection release gerçeği için sırasıyla kök [README](README.md),
  motorların `output/current_samples/CURRENT.json` dosyaları ve
  [pass-11 raporu](reports/qc/EBIS_REALISM_PASS11_2026-07-30.md) esas alınır.
  Eski fiziksel spec veya QC raporu bunlarla çelişirse tarihsel kanıttır;
  yeni geometriye kopyalanmaz.
- Component authoring için
  [hero-quality guide](ebis-blender/docs/HERO_QUALITY_DIGITAL_TWIN_GUIDE.md),
  ilgili immutable run manifesti ve en son karar dosyası birlikte esas
  alınır. Teknik build `PASS`, `HERO_ACCEPTED` anlamına gelmez.
- Codex sohbeti hata izi ve eksik kanıt keşfetmek için değerlidir, fakat
  kendi başına artefakt kanıtı değildir. `Simulation` adlı Codex oturumu
  (`019fa88b-61b8-7f10-a63f-7ebb3765cda5`) `2026-08-01 09:17 +03`
  kesitine kadar metin-bazlı tarandı. Buraya taşınan sonuç ya güncel
  manifest/piksele bağlanır ya da açıkça başarısız pilot/operasyon dersi
  olarak yazılır; bu kesitten sonra üretilen işler aynı kapıdan yeniden
  geçer.
- Kanıt önceliği: doğrudan ölçüm + ölçünün göründüğü kare → üretici CAD →
  board metadata'sı tam kamera kalibrasyonu → aynı makine çoklu
  açı/modalite → zaman-yayılı tek makine görüntüleri → tek kare visual-fit →
  artistik tercih. Üst sıradaki kanıt alt sıradaki fallback'i geçersiz kılar.
- Bu belgede `KANITLI`, gerçek artefakt/validator/piksel ile doğrulanmış;
  `GÖRSEL ADAY`, bounded A/B'de ilerlemiş ama acceptance'ı açık; `PLAN`,
  henüz uygulanmamış; `AÇIK`, ölçüm veya deney borcu demektir.
- Bir şeyin kodda, node graph'ta veya asset klasöründe bulunması piksele
  ulaştığını kanıtlamaz. Piksele ulaşması da domain yakınlığını; domain
  yakınlığı da model faydasını kanıtlamaz. Bu üç karar ayrı tutulur.
- Farklı `REF*` klasörleri farklı makine varyantları içerebilir. Tek hedef
  makine seçilmeden bir makinenin duvarı, diğerinin kapısı ve üçüncünün
  kamerası hibritlenmez. Güncel pass-11 varsayımı REF-65218/İvedik'tir.

## En kısa kanonik karar

Gerçekçilik renderer seçerek değil şu zinciri doğru kurarak elde edildi:

```text
task/ontology freeze
→ ölçü + zaman-yayılı gerçek referans
→ faktörize canonical asset
→ fiziksel geometri ve temas
→ ölçekli, role-bazlı PBR
→ kamera + ışık kalibrasyonu
→ sensor look
→ scoped randomization
→ instance-aware annotation
→ same-seed actual-pixel A/B
→ stratified QC + immutable release
→ frozen-real downstream ablation
```

Blender; canonical high-poly/render-mesh authoring, UV/bake, Cycles truth
renderı, headless batch ve fitting için bugün en sade merkezdir. Unreal;
aynı kabul edilmiş asset'i büyük/dinamik sahne, runtime, PCG ve hızlı üretime
taşımak için güçlüdür. EBIS için doğru hibrit sıra Blender'da master asset →
Unreal Path Tracer parity → Lumen/runtime adaydır. Unreal'da aynı component'i
primitive'lerle yeniden kurmak motor kıyası değil asset kıyası üretir.

## Kanonik uçtan uca çalışma şekli

### 1. Önce görev ve truth sözleşmesini dondur

- Çıktının detection, segmentation, depth, pose veya appearance hedefi
  baştan yazılır. Asset ayrıntısı göreve yetecek fiziksel doğrulukta seçilir;
  beauty realism tek hedef değildir.
- Class, fiziksel instance, occluder, context/debris, visible/amodal ve
  fully-hidden anlamları üretimden önce dondurulur. Annotation sonradan
  rendera uydurulmaz.
- Gerçek split capture/session/sequence bazında dondurulur. Ardışık video
  kareleri train/val/test'e rastgele bölünmez.
- Hedef makine, kamera rolleri ve operasyonel pozitif kapsamı açık yazılır.
  Elde/duvarda sergilenen tag'ler gerçek görev kapsamı değilse ayrı `staged`
  slice olur; operasyonel prior'a karışmaz.

### 2. Referansı üç role ayır

1. **Geometry:** çoklu açı, parallax, ölçü, CAD/scan; silüet, hacim ve temas.
2. **Material:** kilitli exposure/WB, ölçek, diffuse/grazing ve mümkünse
   cross/parallel polarization; albedo, roughness ve mikro-yüzey.
3. **Validation/holdout:** authoring'de kullanılmamış ayrı session, açı,
   ışık ve mümkünse ayrı specimen/makine; final actual-pixel ve task testi.

`Boş chamber != specimen capture != RFID capture != holdout`. Aynı görüntüyü
her dört rol için kullanmak overfit'i gizler. RGB LED kareleri renk/material
için; REF IR/non-LED kareleri değişmeyen topoloji, temas ve occlusion için
kullanılır. IR'den RGB albedo, white balance veya CCT fit edilmez.

### 3. Asset'i tek görüntü değil faktörize ürün olarak kur

Minimum canonical paket:

```text
authorable high-poly source
render mesh + applied transforms + real unit
non-overlap UV + texel-density/scale contract
base_color + roughness + tangent normal + height
material-region masks
semantic/instance map
variation controls
neutral/grazing/matched-camera validation views
source/license/hash/claim-boundary manifest
```

Coarse photogrammetry/COLMAP/RealityCapture veya Gaussian Splatting referansı
final asset değildir; kamera/coverage ve kaba geometri kaynağıdır. Blender'da
artefakt temizliği, semantik parçalama, retopo ve UV'den sonra render mesh
üretilir. High-poly detay kaynağı; render mesh ise simülasyon ve annotation
otoritesidir.

### 4. Düzeltme sırasını karıştırma

İki sıra birlikte geçerlidir:

1. **Fiziksel kurulum:** sabit topoloji → nominal geometri/temas → damage
   geometri → UV/PBR → deployed scene. Clay + nötr/grazing ışık, shader'ın
   geometri hatasını gizlemesini engeller.
2. **Piksel/material fitting:** geometry sabitlendikten sonra camera/sensor
   geometry → light geometry/photometry → base material → spatial roughness/
   albedo → displacement/surface form → layered dirt/wear → sensor look.

Bütün blokları aynı anda optimize etmek albedo, roughness, ışık ve exposure'un
birbirinin hatasını telafi ettiği sahte çözümler üretir. Her iterasyon en
büyük tek farkı değiştirir; diğer seed kararları dondurulur.

### 5. Önce küçük pilot, sonra release, en son model

- Yeni değişiklik dört kamera×şekil hücresinde küçük stratified pilot ve
  sabit hero görünüşlerde incelenir. Contact sheet tek kanıt değildir; en az
  bir native `1:1` crop ve full-resolution actual pixel açılır.
- Aday ancak validator, annotation regression, determinism, iki ışık yönü ve
  kör A/B birlikte olumluysa ilerler. `NOT_OBSERVABLE`, karmaşıklığı
  reddetmek için geçerli sonuçtur.
- Fresh run adı kullanılır; immutable release üzerine yazılmaz. Validated
  run atomik promotion ile `output/current_samples/`a alınır ve `CURRENT.json`
  bütün dosya hashlerini pinler.
- 100-kare, iki kişilik QC ve frozen-real model testi geçmeden 10k batch,
  “production”, “fotogerçekçi” veya “YOLO iyileşti” denmez.

## Sahada veri toplarken kaybedilmemesi gereken know-how

Tam sözleşme [HERO_CAPTURE_PROTOCOL.md](ebis-blender/docs/HERO_CAPTURE_PROTOCOL.md)
ve [saha checklist'inde](ebis-blender/docs/HERO_CAPTURE_FIELD_CHECKLIST_TR.md)
bulunur. Kalıcı kısa reçete:

- Tek canonical makine ve tek capture cihazı/lens seç. Mümkünse 4K/30 fps,
  en yüksek bitrate; dijital zoom, HDR video, portre modu ve stabilizasyon
  crop'u kapalı. Focus, exposure, WB ve zoom take boyunca kilitli.
- Ham dosya kırpılmaz, filtrelenmez, sosyal medya/mesajlaşma ile yeniden
  sıkıştırılmaz. EXIF/metadata ve orijinal ad korunur; SHA-256 manifesti
  üretilir.
- Ölçek çubuğu yüzeyle aynı düzlemde olmalı. Her ışık kurulumunda gri kart
  veya ColorChecker; PBR macro'da diffuse + grazing-left + grazing-right,
  mümkünse cross/parallel polarized çift alınır.
- İlk beton paketi clean/az gözenekli ve ağır kırık cube + cylinder'dır.
  Her specimen için `orbit_mid/high/low` 45–75 sn, yaklaşık `%75–85`
  örtüşme ve gerçek parallax; ayrıca 6 tam görünüş, 4 üç-çeyrek, en az 8
  örtüşmeli hasar macro, 2 cetvelli kare ve 3 ışık yönü alınır.
- Specimen hiçbir turda kırpılmaz; çekim içinde parça/toz oynamaz. Alt yüz
  gerekiyorsa dönüş ayrı take'tir. Cast ve fracture aynı karede en az bir
  kez birlikte görünür ki material rolleri ayrılabilsin.
- Boş chamber; concrete, RFID, kağıt, el ve geçici objeler çıkarılarak
  çekilir. LED kapalı diffuse geometri; `closed/quarter/half/full` kapı;
  chamber W/D/H, platen çap/kalınlık/boşluk, pivot, diffuser ve kamera mount
  landmark ölçüleri kaydedilir.
- Aynı sabit kadrajda LED-off, LED-only ve LED+ambient; mümkünse sample
  üst/orta/alt lux alınır. Diffuser clip olmamalı. Ekran fotoğrafı değil
  native camera export'u kullanılır.
- RFID için ölçülü parametrik mesh genellikle photogrammetry'den daha
  kontrollüdür. Ön/arka/kenar, kalınlık, film/anten/chip, düz-bükük-kırışık-
  kirli ve gerçek partial/plate-gap örnekleri çekilir. Turuncu kağıt decoy
  ayrı non-target klasörüdür.
- Her gerçek kamera/lens/zoom için merkez, dört köşe, farklı roll/pitch/yaw
  ve derinliklerde 15–30 keskin checkerboard/ChArUco kare gerekir. Board
  source hash'i, inner-corner sayısı, print scale ve **basılmış** kare mm
  ölçüsü yoksa sonuç metrik kalibrasyon değil visual-fit'tir. Kamera sökülür
  veya focus/zoom değişirse extrinsics/session yenilenir.
- Cam-10/cam-11'den 10–20 normal çalışma karesi authoring dışında frozen
  holdout tutulur; mümkünse aynı specimen/state iki kameradan senkron alınır.

### Mevcut kalibrasyon artefaktı: değerli ama henüz fail-closed aday

`/home/utkutopcuoglu/Projects/ebis/calibration/` altında gerçekten bir
`calibration_data_final.npz` vardır; SHA-256
`2bfde736d9eaf8f498473ab180cc3dcae73ef859aa4a752c4a5d8fbf6c7261ab`.
`calibration_images_v2` içinde 267 adet `1920×1080` kare, NPZ'de 255 geçerli
view bulunur. Script `10×7` inner corner ve doğrulanmamış `25 mm` kare
varsayar ve fisheye modeli yerine standart OpenCV `calibrateCamera` beş
katsayılı distortion modelini kullanır. Kaydedilmiş pinhole matrisi yaklaşık:

```text
fx=1331.7495, fy=1319.2851, cx=964.6582, cy=525.3074
k1=-0.274855, k2=0.001563, p1=-0.000667,
p2=-0.001402, k3=0.024155
```

Ancak artefakt kamera kimliği/cam-10–cam-11 eşlemesi, baskı target
manifesti/hash'i, ölçülmüş kare doğrulaması, RMS/per-view error ve ayrı iki
kamera sonucu taşımıyor. Generator config'leri hâlâ açıkça visual-fit'tir ve
bu NPZ'yi kullanmaz. Bu nedenle sayı **uygulanacak calibration değildir**;
board ve kamera provenance'ı doğrulanıp kareler yeniden kalibre edilene kadar
yalnız yüksek değerli bir lead'dir. Tek kameranın sonucunu iki kameraya
kopyalamak yasaktır.

## Geometri ve materyal: tekrar kullanılacak fiziksel kurallar

### Geometri otoritesi

- Silüet, depth, temas gölgesi veya occlusion'ı etkileyen kırık, çentik,
  bombe, büyük oyuk ve deformasyon mesh/displacement olmalıdır. Mikro-pürüz,
  sub-pixel pore ve ince çizik normal/roughness olabilir.
- Aynı frekans hem geometry/displacement hem normal/height ile iki kez
  kabartılmaz. Base Color'a yönlü ışık, specular highlight veya ağır AO
  bake edilmez.
- Damage kapatılınca clean nominal asset birebir geri gelmelidir. Ağır
  hasar her seed'e sürekli scalar olarak yayılmaz; `clean`, `pitted`,
  `edge_worn`, `spalled_light`, `spalled_heavy` kategorik state'lerdir.
- Büyük hasar primary connected manifold üzerinde olmalı. Aggregate'i dışa
  icosphere/boncuk olarak yapıştırmak, eş ölçekli Boolean cutter, düzenli
  cookie-bite ve dikdörtgen notch güçlü CG ipucudur.
- Clay neutral + iki grazing render, PBR'dan önce geometri gate'idir.
  Beauty'deki hata clay'de de varsa texture/roughness ile gizlenmez.
- UV gate fail-closed'dur: gerçek raster texel occupancy ve farklı polygon
  overlap'i ölçülür; boundary paylaşımı ile gerçek overlap ayrılır. Tangent
  normalde non-finite/lower-hemisphere hit açıkça sayılır; bounded repair
  oranı manifestte kalır. Repair teknik transfer kanıtıdır, görsel kabul
  değildir.
- Boolean pore/damage yüzlerinde authoring split-normal kararı korunur;
  bütün shell'i smooth etmek uzun support triangle'larını sahte oluk ve
  origami highlight'a çevirir. Fiziksel edge response authoring mesh'teki
  uygulanmış bevel'den gelir (güncel fallback cube `1.2 mm`, cylinder
  `0.8 mm`, 4 segment). Bakery'de ikinci global bevel eklemek Boolean
  topolojiyi bozduğu için reddedildi; bake sonrası aynı render mesh üzerinde
  raster UV-overlap kapısı yeniden çalıştırılır.
- Fracture normal transferi tek reçete değildir. Büyük fracture silüet/depth'i
  render geometry'de kalır. Retessellated high source yalnız bounded mikro
  relief aktarabilir; lower-hemisphere/non-finite ray hitleri pre/post sayılır
  ve repair yalnız açık eşik içinde yapılır. Dense fracture self-bake yıldız
  üretiyorsa kötü in-island değerleri gizlenmez: fracture geometry otoritesi
  korunur, tangent katkısı nötrlenir. Yalnız tam siyah, kullanılmayan atlas
  arka planını `(0.5, 0.5, 1)` ile doldurmak ayrı ve güvenli işlemdir.

### Topoloji, koordinat ve bake validator tuzakları

- Material/damage rolü hard-coded “mesh merkezde ve Z aralığı
  `-H/2…+H/2`” varsayımından çıkarılmaz. Bir silindir `Z=0…H`
  koordinatında yeniden kurulduğunda eski classifier üst yan yüzleri
  `end_face` sanabildi. Roller applied/evaluated koordinat, gerçek bounds
  ve açık contact landmark'larından üretilir; transform veya topoloji
  değişince rol başına yüz/alan coverage'i ve beklenmeyen boş rol hard
  gate'tir.
- Normal recalculation, triangulation ve retopo polygon sırasını korumak
  zorunda değildir. UV, material veya semantic rol `polygon.index`/face
  order'a bağlanmaz; persistent POINT/vertex parametresi (`u/v`, role,
  source id) ya da yeniden hesaplanabilir topoloji kuralı kullanılır. Her
  topology/normal işleminden sonra raster UV overlap ve rol coverage yeniden
  çalışır. Bir pilotta face-order varsayımı tek başına `49` texel overlap
  üretmiştir.
- High-source displacement genliği lokal hücre boyu, eğrilik yarıçapı ve
  ray yönüne göre sınırlandırılır. `0.55 mm` “micro” relief'in yaklaşık
  `0.25–1 mm` hücrelerde low-facet normalinin arkasına katlandığı pilot,
  cage'i büyütmenin ölçek hatasını çözmediğini gösterdi. Önce fold/self-hit
  ve ray-miss incelenir; büyük fracture zaten render mesh'teyse high source
  yalnız daha küçük, rol-bounded mikro relief taşır. Bu sayılar global reçete
  değil başarısız ölçek örneğidir.
- Yapısal bir yüzeyde çok sayıdaki gözenek ayrı Boolean cutter zinciriyle
  retopo ve UV'yi parçalıyorsa, ölçülü pit'leri tek welded/parametrik
  manifold içinde üretmek daha güvenlidir. Sparse Boolean yalnız manifold,
  split-normal, rol ve raster-UV kapıları geçerse kalabilir. Dense triangulated
  yüzeyi kör `Smart UV` ile açmak atlas alanını israf eder; fiziksel yüzey
  parametresi tercih edilir.
- Çözünürlüğe göre sayılan hata oranında pay ve payda aynı target raster'a
  ait olmalıdır. Gerçek target occupancy en iyisidir; yalnız UV alanı
  çözünürlükten bağımsızsa açıkça bildirilen karesel alan ölçeklemesi
  fallback olabilir. 4K hata pikselini 1K occupancy'ye bölen eski kontrol
  aynı fracture asset'ini yapay `%11.65` gösterdi; eşlenik payda ile
  [manifestte](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cylinder_fractured_v17_role_scan_4k_v1/evidence/ASSET_BUILD_MANIFEST.json)
  oran `%0.728` (`38,613 / 5,301,408`) oldu ve ilan edilmiş `%5`
  üst sınırının altında PASS verdi. Eşik gevşetilmedi; nötrlenen tangent pikselleri ve
  geometry-authority claim boundary'si manifestte kaldı. Bu teknik transfer
  PASS'i hero kabulü değildir.

### Ölçek ve frekans

Ölçüm/scan gelene kadar EBIS beton fallback'leri: pore `0.5–4 mm`, görünen
mortar/aggregate `2–12 mm`, chip/spall `3–20 mm`. 1920×1080'de gözlenen
`2–15 px` pore ve `5–40 px` chip bantları yalnız projected-pixel QC'dir;
texture dünya ölçeğinin kaynağı değildir ve FOV/çözünürlük değişince yeniden
hesaplanır.

Materyal en az iki frekansta kurulmalıdır:

```text
macro: leke, kir, nem, aşınma zonu, renk ve roughness alanı
micro: pore, orange-peel, tanecik, hairline scratch, küçük roughness/normal
```

Tek uniform noise gerçek materyal değildir. Kir ve kusur fiziksel nedene
bağlanır: toz yatay/temas yüzünde, çizik hareket doğrultusunda, nem/grease
lokal, edge wear köşe ve temas bölgesinde olur.

### Renk uzayı ve motorlar arası PBR

- Base Color sRGB; roughness, metallic, normal, height ve maskeler linear/
  Non-Color import edilir. Roughness, Base Color'ın gri kopyası değildir.
- Powder-coat boyalı sac dielectric'tir (`metallic=0`); çıplak çelik metal,
  üstündeki toz/çimento/grease ayrı dielectric katmandır. Mirror chrome ve
  uniform plastik response reddedilir.
- Blender tangent normal sözleşmesi OpenGL'dir. Unreal'a aktarırken tangent
  basis ve UV aynı tutulur, DirectX beklentisi için green/Y kanalı yalnız
  açık manifest kuralıyla çevrilir; gözle deneme-yanılma yapılmaz.
- Büyük relief render mesh'te, sub-mm relief high→render bake'te kalır.
  Material-region maskeleri en az cast/end/fracture/aggregate'i ayırır;
  role boundary'de feather/transfer büyük fracture'ı yumuşatmamalıdır.

### EBIS concrete'ten öğrenilenler

- Clean specimen düz nominal kalıp formudur; her beton rastgele kaya/blob
  yapılmaz. Cube `180 mm`, cylinder yaklaşık `Ø126 × 201 mm`; iki tabla
  temas düzlemi korunur. Bunlar güncel fallback'tir, CAD ölçümü değildir.
- Pore için iki popülasyon (çok küçük sığ pinhole + seyrek düzensiz casting
  void) tek ölçekli koyu noktalardan daha doğrudur. Silindir yan/end material
  rolü ayrılır; Boolean oyuk normalleri tüm shell'i smooth ederek dikey
  ışık çizgisi üretmemelidir.
- Ağır cylinder hasarı üst yük bandının ve çevrenin bir bölümünün lokal
  kaybıdır; alt gövdeyi incelten waist/taper değildir. Gerçek kırık geniş,
  asimetrik mortar/aggregate petrology taşır; eş sıra/lattice yatay teras
  gibi okunur.
- Normalize UV'de Delaunay, silindirin metre-aspektini bozdu. Triangulation
  öncesi çevre/yükseklik ölçeklemesi ve donor crop'un fiziksel aspektini
  korumak yatay plaka cue'sunu kaldırdı.
- Separate aggregate boncuğu yerine recessed primary-manifold face rolü;
  damage-face retessellation → SIMPLE subdivision → role-bounded relief →
  clay grazing → PBR sırası daha güvenli oldu. İkinci global bevel Boolean
  topolojide origami regression üretti ve reddedildi.
- Debris ana specimen bbox'ını otomatik şişirmez. `concrete_debris`, owner
  `concrete_00` ve ayrı auxiliary/context mask taşır; tarihsel label
  prevalansı ölçülene kadar primary bbox yalnız primary visible maskedir.

### Makine, tabla, LED, kağıt ve RFID

- Güncel pass-11 makinesi kapalı cabinet'tir: back/left/right mavi pebbled
  sac; dışa açılan sağ menteşeli dolu gri ön kapı ve onun servis kapağı;
  doğrulanmamış sürgü/cam leaf/turuncu hardware yok. Tarihsel safety-glass/
  sol menteşe spec'i güncel kaynak değildir.
- İki aynı eksenli yaklaşık `Ø400 mm` used-steel platen sample'ı sıfır gap
  ile sıkar. Contact face ana platen gövdesinden ayrı ince used-steel bölge
  olabilir. Radial machining, hairline scratch, dust/grease ve lokal rough
  highlight gerekir; periyodik Wave halkası ve beyaz/ayna disk reddedilir.
- LED tek panel/point light değildir. Upper-platen kotunda back+left+right
  boyunca dar U-channel, aluminium housing, opal diffuser ve gizli fiziksel
  emitter'dır; kapı açıklığında dördüncü kol yoktur. Görünen cover, emissive,
  direct light, bounce/contact fill ayrı kontrollerdir.
- Chamber gölgesi mutlak siyah değildir; global pedestal kayıp ışığı geri
  getirmez. Önce lokal bounce/contact spill ve ışık geometrisi düzeltilir.
  Diffuser lokal clip olabilir; geniş concrete/platen clip olamaz.
- Kağıt non-target fiziksel occluder'dır; shader overlay değildir. Cube için
  subdivided/solidify/bevel irregular mesh işe yaradı. Ölçüsüz planar kağıdı
  silindire yüzdürmek yerine gerçek conformed mesh+mask gelene kadar state
  atlanır.
- RFID yaklaşık `60 × 10 × 0.09–0.15 mm` ince film/anten/chip yapısıdır;
  kalın neon kart değildir. Cylinder'a konform tag aynı local frame'i
  paylaşan segmentli yay olabilir. Film iki görünür parçaya bölünse de tek
  fiziksel instance kalır.

## Kamera, ışık ve sensor fitting know-how'ı

- Kamera rolleri sabittir: `camera_angled = cam-10/Kamera 01`,
  `camera_door = cam-11/Kamera 02`. Bbox medyanına fit edilmiş FOV, intrinsics
  değildir. Her kameranın lens, principal point, distortion, pose, response,
  exposure ve WB'si ayrı kalibre edilir.
- RGB ile visible/amodal maskeler aynı geometrik lens warp'ını paylaşır.
  Noise, denoise, sharpen, bloom, compression, chromatic fringe ve overlay
  maskeye uygulanmaz. Warp ile eşlenmeyen depth fail-closed kapatılır veya
  açıkça `approximate` denir.
- Timestamp/`Kamera 01/02` overlay gerçek modelde spurious feature olabilir.
  İki domain birlikte normalize edilir veya overlay ayrı bounded
  randomization olur; sabit sentetik overlay bake edilmez.
- Whole-frame mean yanıltır. Black/clip percentile, concrete/platen/material
  ROI, highlight width, shadow floor, local gradient/high-pass ve power
  spectrum birlikte incelenir. Kayıtlı olmayan gerçek/render crop'un mutlak
  luma farkıyla materyal kör karartılmaz.
- Bbox center/size ve occupancy doğru yönelimi kanıtlamaz. Cam-10'da yatay
  aynalanmış bir sahne, specimen merkeze yakın olduğu için bbox kapısını
  geçebildi. Her kamera için en az bir asimetrik semantic landmark, beklenen
  sol-sağ yerleşim/işaret veya oriented keypoint gate'i gerekir.
- Diagnostic crop beklenen kanıt bölgesine bağlıdır. Üst-load hasarı olan
  uzun specimen'da bbox-merkezli crop fracture bandını dışarıda bırakıp adayı
  sahte biçimde clean göstermiştir. Full frame korunur; native `1:1` crop
  damage/contact landmark'ına anchor edilir ve crop koordinatı/politikası/
  source hash'i manifestlenir. Deployed state kararı aynı frozen sentetik
  kamera/ışıkta `gerçek / clean baseline / aday` üçlüsüyle verilir;
  authoring grazing macro'da görünen ama deployed ölçekte clean'den
  ayrışmayan state henüz gözlenebilir değildir.
- LED fitting sırası source geometry/extent → diffuser → direct:bounce oranı
  → local contact spill → exposure/WB/response'tur. Global exposure, yanlış
  normal/geometri veya siyah contact bandını güvenli biçimde çözmez.
- Sensor look en son gelir. Grain, blur, vignette, bloom, sharpen, compression
  ve black pedestal fiziksel renderı kamufle etmek için kullanılmaz.
- Same-object/same-pose çoklu LED ve IR seti inverse fitting için çok
  değerlidir. LLM baskın hata bloğunu ve accept/rollback'u seçebilir;
  sayısal optimizer küçük parametre bloğunu arar. Camera/light/material/noise
  aynı anda serbest bırakılmaz.

## Blender uygulama playbook'u

- Blender scene unit metre; transformlar uygulanmış; nominal bounds ve iki
  contact plane validator'da hard gate'tir. Canonical high source ile
  üretim/render mesh ayrı isim, rol ve hash taşır.
- Cycles neutral diffuse, grazing-left/right, silhouette/depth ve deployed
  cam-10/cam-11 paketi component validation'ın temelidir. Denoised beauty
  tek başına geometri kanıtı değildir.
- Büyük batch tek config + deterministic Python CLI ile üretilir. BlenderMCP
  scene-info/semantic readback, viewport ve bounded current-source render
  verifier'ıdır; batch engine veya uzun prosedürel edit zinciri değildir.
- Her fiziksel instance ayrı pass index/mask alır. RGB ve mask aynı lens
  distortion'ından geçer; bbox yazılmış visible instance maskeden yeniden
  türetilip metadata/YOLO ile exact karşılaştırılır.
- Compositor `Render Result`/in-memory pass okumaları staging sırasında stale
  veya yanlış bağlam verebilir. Published dosyayı yeniden açıp pixel audit
  yapmak; pass-index çakışmasını validator'da hard fail yapmak gerekir.
- Library-appended fakat henüz view layer'a bağlanmamış objenin
  `matrix_world` değeri stale olabilir. Staging'de link/update sonrası
  evaluated transform ve gerçek bounds'tan contact kotu yeniden hesaplanır;
  kaynak objenin eski merkez Z'si körlemesine kopyalanmaz.
- GPU denoise/render aynı ortamda dahi birkaç `1/255` fark verebilir. Scene,
  RNG, mesh, label ve mask exact; beauty için açık tolerans kullanılır.
  PNG container yerine canonical decoded pixel hash'i tutulur.
- Paylaşılan GPU kullanıcıya ait başka işlerle doluysa o süreçlere
  dokunulmaz. Açık `--device cpu` fallback yalnız süre/device provenance'ını
  değiştirir; scene, seed ve kalite sözleşmesini değiştiremez. Seçilen
  backend/device manifestte kalır; OOM, non-zero exit veya yarım map seti
  publish edilmez. Uzun uzak koşunun stdout'u bounded kanıt loguna yöneltilir;
  SSH pipe `BrokenPipe` sonrası yarım klasörden devam etmek yerine fresh run
  çalıştırılır.
- MCP listener yalnız loopback'te açılır, pinli scene/add-on hash'iyle tur
  yapılır, exact process ve port tur sonunda kapatılır. MCP PASS yalnız
  kontrol yolunu kanıtlar.
- Yerel→3090 sync'te iki root zaten hedefi tanımlar; `--relative` veya
  `.../ebis-blender/./...` kullanmak nested-path kopyası üretti. Önce
  `rsync --checksum` dry-run, sonra root→root sync; output ayrı immutable
  artefakttır.

## Unreal uygulama playbook'u

- Blender metre kaynağı Unreal santimetreye tek manifestle normalize edilir;
  pivot, material slot, UV, split normals/tangent ve semantic part isimleri
  korunur. Collision annotation kalitesi sağlamaz; görsel mesh ve instance
  kimliği esastır.
- İlk parity render Unreal Path Tracer'da aynı asset/camera/light ile alınır;
  sonra Lumen/MRQ production adayı karşılaştırılır. Nanite veya HWRT kendi
  başına kötü mesh/PBR'ı iyileştirmez.
- BaseColor sRGB açık; roughness/metallic/mask/normal linear. OpenGL→DirectX
  normal yönü manifestle çevrilir. Direct-UV gerilmesi actual-pixel/grazing
  testte kontrol edilir.
- Procedural sahne her seed'de yeniden kurulunca SceneCapture Lumen/TSR
  history'si yoktur. RGB için sekiz sabit warm-up mevcut hatta first-frame
  sapmasını azalttı; mask/depth warm-up almaz ki truth değişmesin.
- Precompiled editor ilk unlit mask materyalini shader map hazır olmadan
  checker/all-white fallback ile çizebilir. Basit mask materyalleri
  synchronous compile edilir ve ilk seed mutlaka aynı state'te rerender
  edilir.
- Hızlı render-target değişiminde export önceki pass'i kopyalayabilir; küçük
  GPU pixel readback render-thread fence olarak kullanılır. Capture source
  proxy gecikebildiği için sıra RGB → bütün visible/amodal maskeler → depth;
  depth'ten sonra başka pass çalıştırılmaz.
- Multipart concrete/RFID parçaları actor düzeyinde aynı `EBIS_INSTANCE`
  taşır. Visible pass gerçek occluder'ları korur; isolated-amodal pass yalnız
  target'ı bırakır ve frame clipping'i korur.
- RGB fisheye warp'ıyla eşlenmemiş batch depth mevcut release'te bilinçli
  kapalıdır. MCP'nin tek-kare EXR'i batch'e depth özelliği atfetmez.
- Lumen'i kapatmak geniş poligonal light field'i çözmedi. RectLight extent/
  placement/source-angle, material normals ve camera response debug pass'leri
  birlikte ayrıştırılır. `Noise.Scale` küçük sayı = küçük feature varsayımı
  yapılmaz; gerçek feature çapı full-resolution pikselden ölçülür.
- Epic resmi MCP yalnız `127.0.0.1:8000`, auth/TLS'siz bounded control plane'dir.
  Batch deterministic wrapper'dan; MCP build/validate/status/render'dan.
  Editor/listener tur sonunda kapatılır ve hiçbir public/LAN bind yapılmaz.

## Blender → Unreal aktarım sözleşmesi

Taşınan şey node isimleri değil fiziksel ve veri sözleşmesidir:

```text
exact render mesh + unit/transform/pivot
high-source ve bake claim boundary
UV + texel scale + tangent/split-normal convention
basecolor/roughness/normal/height + region masks
material role ve color-space map'i
semantic/instance/owner map'i
reference camera + neutral/grazing light tarifi
source/license/artifact SHA-256
FBX/GLB export ayarı ve importer sürümü
```

Aktarım sırası: import integrity → unlit/clay silhouette/contact → material
slot/mask → tangent-normal → Path Tracer parity → Lumen/runtime → annotation
regression. Her aşamada aynı camera/shape/seed hücresi kullanılır. Unreal'a
geçince kırığı primitive'lerle yeniden yapmak, Blender'daki retopo/scan
kazanımını geri alır.

## Annotation ve occlusion: değiştirilmeyecek güvenlik sözleşmesi

YOLO bbox semantic class-union'dan değil her fiziksel instance'ın RGB ile
aynı warp'tan geçmiş visible maskesinin tight pixel sınırından çıkar. Birden
çok tag veya ikiye bölünmüş görünür tag için union bbox aradaki beton/plakayı
yanlış foreground yapar. Tam örtülü tag metadata/amodal truth'ta kalır, YOLO
satırı almaz.

640 model girişine normalize edilen güncel RFID kapıları:

| Partition | Minimum kural |
| --- | --- |
| `standard` | kısa `≥4 px`, uzun `≥12 px`, foreground `≥40`, visibility `≥.35`, largest component `≥.65`, edge margin `≥2 px` |
| `hard_occlusion` | kısa `≥3 px`, uzun `≥8 px`, foreground `≥20`, visibility `≥.15`, largest component `≥.45`; edge serbest |
| `exclude` | görünür ama hard eşiğinin altında; label yok, tüm kare exclude |
| `fully_occluded` | amodal `>0`, visible `=0`; label yok |
| `outside_frame` | amodal-in-frame `=0`; label yok |

Visibility Unreal'da `visible/amodal_in_frame`; Blender'daki projection
proxy'si piksel-hassas amodal truth değildir. Kare, **en kötü görünür
instance** ile partition edilir: herhangi exclude → `exclude`; yoksa hard →
`hard_occlusion`; aksi → `standard`. Partition yalnız metadata flag'i değil
fiziksel dizindir. Normal train yalnız `standard`; hard yalnız adlandırılmış
ablation; exclude hiçbir manifestte yoktur.

Worst-instance kuralında tek bir çok küçük plate-gap tag bütün kareyi
`exclude` yapabilir. Train yield'i artırmak için piksel/visibility eşikleri
gevşetilmez veya görünür target labelsız bırakılmaz. Bunun yerine gerçek
prevalanstan scenario mixture/tag-count/placement dağılımı düzeltilir ve
küçük pilotun en az bazı `standard` train-eligible kareler ürettiği ayrıca
kapılanır; aksi sonuç generator'ın operasyonel olarak kullanılamadığını
gösterir.

Concrete ana `concrete_00` instance'ıdır. Pore ve primary-manifold aggregate
aynı kimliktir; uzak/tabla debris class 1 veya primary bbox değildir. Büyük
parçalanma gerçekten birden çok hedef yaratırsa union kullanmak yerine
instance ontolojisi yeniden dondurulur. Görüntü kenarı concrete için doğal
olduğundan edge contact tek başına red değildir.

Senkron cam-10/cam-11 aynı fiziksel scene state, yaw, damage ve placement'ı
paylaşır. Kamera koşullu yaw/spall yalnız birbirinden bağımsız detection
still augmentation'ında kullanılabilir; stereo/eşzamanlı veri diye sunulmaz.

## Scoped randomization ve determinizm

- Topoloji, kamera kimliği, class ID, annotation policy, platen ekseni,
  U-LED güzergâhı ve target-machine renk haritası seed ile değişmez.
- Door angle, küçük pose/lens/exposure, light profile, tag count/placement,
  paper, damage category, surface, debris, dirt ve sensor parametreleri ancak
  açıklanmış bounded dağılımda değişir.
- Her yeni realism özelliği ayrı RNG scope/seed türetir; çağrı eklemek eski
  kamera, ışık, RFID veya sample karar zincirini kaydırmaz. Same-seed A/B'de
  hedef katman dışındaki metadata/label/mask exact kalmalıdır.
- Ölçülmemiş range `bounded visual-fit prior` olarak metadata'ya yazılır;
  gerçek prevalans gelince config daraltılır. Güzel bir ağır-hasar örneği
  bütün sentetiğe yayılmaz.
- Küçük pilotta nadir kategorilerin yalnız RNG ile gelmesi beklenmez. Bir
  `22` specimen pilotunda düşük olasılık yüzünden hiç spalled örnek
  çıkmaması coverage'in tesadüfe bırakılamayacağını gösterdi. Pilot
  state×shape×camera kotası veya açık seed manifestiyle bütün kritik
  kategorileri görür; production'daki oran yine gerçek prevalanstan gelir.
- Determinizm katmanları ayrı raporlanır: scenario/metadata, mesh, label,
  decoded mask, decoded beauty ve container byte. PNG encoder metadata'sı
  değişebilir; farklı GPU/driver/engine build'i için bit-exact beauty iddia
  edilmez.
- Her frame seed, engine/build, config+generator+asset hash, kamera, ışık,
  material/damage/state, instance kararları, output hashes ve partition
  taşır. Stable alanlar ve runtime süre/path alanları ayrı karşılaştırılır.

## Doğrulama ve kabul kapıları

### Her değişiklikte

1. Gerçek referans iki kamera, iki shape, erken/orta/geç zaman, LED RGB +
   REF IR ve hasar state'lerine stratified yeniden açılır; path/hash/crop
   manifesti dondurulur.
2. Same-seed tek-variable A/B; neutral diffuse, grazing-left/right, clay,
   full frame, native `1:1` ROI, silhouette/depth ve visible mask üretilir.
3. Geometri, material, ışık/kamera ve annotation ayrı rubric'te incelenir.
   Motor/aday adı körlenir; en az owner + ikinci operatör/mühendis bakar.
4. Builder anlatısı değil actual pixels karar verir. Frame-average yanında
   ROI/frequency/highlight/shadow ve annotation regression ölçülür.
5. Validator fiziksel contract, binary/unique mask, bbox re-derivation,
   orphan/duplicate, partition, hash, camera×shape coverage ve source pinini
   fail-closed kontrol eder.
6. Aynı ortamda determinism repeat ve current-source MCP round-trip yapılır.
7. Aday fresh immutable run'da kalır; bütün kapılar kapanmadan stable current
   veya production'a terfi etmez.

Validator'ın generator/config/asset hashlerini dataset içinde birbiriyle
tutarlı bulması yeterli değildir; embedded hash, koşu anındaki pinli gerçek
source dosyasının hash'iyle karşılaştırılır. Generator değiştiğinde eski
dataset yeni validator altında açıkça fail etmeli veya eski source immutable
olarak pinlenmelidir. Semantic beklentiler de pipeline stage+schema sürümüne
bağlıdır: authoring material adı bekleyen kontrol, doğru baked-master
profilini hata sanmamalıdır.

### Hero component G0–G6

- `G0 provenance`: gerçek/online/scan kaynak, lisans, ölçek, hash ve claim.
- `G1 nominal geometry`: bounds, düz nominal form, contact, damage-off state.
- `G2 damage geometry`: silhouette/depth, connected fracture, bounded state.
- `G3 material`: role ayrımı, texture scale, roughness/highlight, pattern yok.
- `G4 matched hero`: iki gerçek kamera yanında full-res/kör review, blocker yok.
- `G5 dataset safety`: identity, mask/bbox, occlusion, RNG, validator, MCP.
- `G6 release`: immutable pin, local–3090 equality, atomic current, gap kaydı.

G0–G6 kapanmadan `HERO_ACCEPTED=true` yazılmaz. On pass bitmesi guide'ın
bitmesi değildir. `PASS_ASSET_BUILD_NOT_HERO_ACCEPTED` doğru ve değerli bir
teknik sonuçtur.

### Production ve model kapısı

- Her config/generator/asset hash'inde 100 stratified kareyi iki kişi bağımsız
  kontrol eder. Normal train kapısı bbox yanlış/eksik `<%1` ve `standard`
  içinde visible-unlabelled sızıntı `0`dır. Görsel owner+operatör medyanı
  geometri/material/ışık/kamera eksenlerinde en az `3/5`, açık blocker `0`.
- Frozen gerçek test capture-safe ve sonuç görülmeden kilitlidir. Aynı nano
  checkpoint/hyperparameter/imgsz/update budget ve seed `17/29/43` ile
  `R`, `S_B`, `S_U`, `R+B`, `R+U`, `R+B+U` koşulları karşılaştırılır.
- Ana train yalnız standard. Tiny, paper-under-tag, plate-gap, glare,
  cam-10/11, cube/cylinder, hand/person slice'ları ayrı raporlanır. Tek seed,
  yalnız validation artışı veya güzel contact sheet model kazancı değildir.

## Reddedilen yaklaşımlar ve hızlı teşhis atlası

| Belirti | Gerçek neden / ders | Güvenli sonraki hareket |
| --- | --- | --- |
| “Daha çok texture/noise” pikselde görünmüyor | Shader gücü world/projected scale'de yanlış veya etki çok küçük | Same-seed mask-ROI farkı; `NOT_OBSERVABLE` ise kaldır |
| Büyük cellular/marble bulut | Node `Scale` semantiği sezgiyle ters yorumlandı | Full-res feature çapını ölç; sayı adına güvenme |
| Yapışmış taş/boncuk | Additive ayrı aggregate geometry | Recessed primary-manifold role veya ölçülü scan |
| Dikdörtgen oyuk/makine kesisi | Tek düz Boolean/notch | Lokal connected çok ölçekli fracture; clay gate |
| Cookie-bite/periyodik edge | Eş aralıklı/eş ölçekli cutters | Daha küçük, sığ, örtüşen ve evidence-bounded micro-ravel |
| Yıldız/origami kırık | Damage n-gon üzerinde subdivision/displacement veya ikinci bevel | Explicit retessellation → SIMPLE subdiv → role relief |
| Silindirde yatay teras/plaka | Normalize UV/Delaunay fiziksel aspekti bozdu | Çevre/yükseklik metrik ölçek ve donor aspect koruması |
| Fracture UV hatası için tüm bump'ı kapatma | Role ayrımı yok | Cast/end mikro-bump'ı koru; fracture geometry otoritesi |
| Unreal ilk kare checker/all-white | Shader compile fallback | Synchronous compile + aynı ilk seed rerender |
| Unreal pass önceki görüntüyü kopyalıyor | Render-target/export race | GPU readback fence; pass order pinle |
| Unreal depth/RGB kayık veya stale | Capture-source update gecikmesi/warp farkı | RGB+masks önce, depth son; parity yoksa depth kapalı |
| Lumen kapandı ama üçgen ışık kaldı | Renderer değil light extent/normal/response | RectLight + normal + camera diagnostic pack |
| Translucent load residue kabarcık | Depth-sort ve silüet şişmesi | Küçük sığ opaque/decal/scan; bbox regression |
| Koyu bandı global exposure/pedestal ile düzeltme | Lokal bounce/contact veya normal/geometri hatası | Lokal light transport ve debug normals; sensor en son |
| Online asset detaylı ama yanlış | Lisans doğru olsa da ölçek/UV/petrology yanlış | Provenance + same-seed actual-pixel A/B; gerekirse reddet |
| Low-res sheet iyi, 1080p kötü | Periyodik normal, seam, faceting küçültmede gizlendi | İki fixed 1080p hero + native crop zorunlu |
| Semantic maskeden dev bbox | Çoklu instance/occluded component union | Visible per-instance tight bbox + worst-instance partition |
| Same-seed PNG hash farklı | Encoder metadata/sıkıştırma | Decoded canonical pixel hash; container ayrı rapor |
| Frame ortalaması iyi, bölge yanlış | Bimodal clipping/black crush veya background baskın | Material/instance ROI + percentile + local frequency |
| Daha fazla sentetik performansı düşürüyor | Domain gap, prevalence veya leakage | 1N/2N ablation, session-safe split, slice hata analizi |

## Güncel EBIS durumu — 2026-08-01

- Detection front door: Blender `realism_v11_loaded_edge_release_60240` ve
  Unreal `realism_r72_loaded_edge_camfit_release_60260` teknik validator,
  instance annotation, current publication ve MCP kapılarını geçmiştir.
  Bunlar ölçülü dijital ikiz veya kanıtlanmış model kazancı değildir.
- İki motorun ortak en büyük domain gap'i gerçek aggregate/fracture,
  concrete üst-load petrology, used-steel/powder-coat BRDF, ölçülmüş LED ve
  cam-10/cam-11 response'dur. Unreal'da ek olarak poligonal light field ve
  rectilinear fracture; Blender'da fazla temiz fracture/mortar sürer.
- Hero concrete v17, yatay lattice/teras cue'sunu fiziksel-metrik Delaunay ve
  donor-aspect düzeltmesiyle kaldırmış bounded `1K` geometri gelişimidir.
  `29,185` vertex / `57,854` polygon closed render mesh, `331,338` occupied
  texel / `0` overlap ve açık `%1.04` bounded tangent repair teknik PASS'tir;
  matched camera/material/release değildir.
- 1 Ağustos'taki ilk `1K` role-scan smoke build'leri yalnız bake/UV/normal
  hattını sınadı; `FAIL_TEST_RESOLUTION` bu nedenle beklenen pilot sonucu,
  release reddi değildir. Ardından clean/pitted/fractured × cube/cylinder
  altı-state generic kütüphane `4096×4096`, 16-bit RGB basecolor/roughness/
  tangent-normal/height ve role maskeleriyle üretildi. Manifestler builder
  `1.12.1–1.12.2` karışımıdır; altısının da statüsü
  `PASS_ASSET_BUILD_NOT_HERO_ACCEPTED`, 4K map/render mesh/non-overlap UV
  kapıları `PASS`, matched cam-10/cam-11 `OPEN`, `hero_accepted=false`dır.
  [Fail-closed teknik audit](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/LIBRARY_TECHNICAL_AUDIT.json)
  dosya/hash/sözleşme denetiminde `6/6`, hata `0` buldu; fakat stable
  `hero_concrete/current` bilinçli olarak yoktur ve release kapısı açıktır.
- Altı-state [native-pixel inceleme manifesti](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/review/PIXEL_REVIEW_MANIFEST.json)
  her gerçek/generic karar crop'unu resize etmeden `670×600` olarak aynı
  panelde toplar. Sonuç `VISUAL_EVIDENCE_REQUIRES_HUMAN_REVIEW`dur: dört state
  yalnız `MORPHOLOGY_FAMILY_ONLY`, clean cube
  `NEAREST_MORPHOLOGY_NOT_CLEAN_MATCH`, pitted cylinder
  `NEAREST_MORPHOLOGY_NOT_SHAPE_MATCH`tır. Gerçek ve generic kareler aynı
  fiziksel specimen/illumination olmadığı için pixel-error, matched-camera,
  digital-twin veya photorealism sonucu çıkarılamaz.
- İlk pitted v1 adayları deployed ölçekte clean'e fazla yakın kaldı. Sadece
  pitted yüzey profilini değiştiren 1K v2 A/B'nin
  [kararı](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/pilots/pitted_v2_review/PITTED_V2_AB_MANIFEST.json)
  `PASS_TECHNICAL_REQUIRES_HUMAN_VISUAL_DECISION` ve
  `CANDIDATE_NOT_PROMOTED_BY_THIS_SCRIPT`tir. Ardından üretilen pitted v2
  cube/cylinder 4K assetleri 4096²/16-bit map, sıfır raster UV overlap,
  FBX/master Blend ve teknik gate'leri geçti; library audit yine `6/6`
  kaldı. Bunlar yalnız güncel teknik adaydır; `matched_real_cam10_cam11=OPEN`
  ve `hero_accepted=false`dır. Kesitteki actual-pixel gözlemi
  (`GÖRSEL ADAY`), v2 küçük pit'lerin daha okunur olduğunu ve silueti
  bozmadığını; gerçek örneklerdeki iri void/aggregate kontrastı ile
  kamera-yönlü kırık görünürlüğünün ise hâlâ eksik olduğunu gösterdi.
  Başlatılan repeat-render/visibility testi bu kesitte tamamlanmadığı için
  ona sonuç atfedilmez.
- [12-vaka deployed inceleme](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/deployed_review/DEPLOYED_PIXEL_REVIEW_MANIFEST.json)
  iki kamera × iki şekil × üç state staging'ini, native `670×600`
  `gerçek/clean/adayı` panellerini ve bbox/mask/contact sözleşmesini
  tamamladı. Statü `PASS_STAGING_REQUIRES_HUMAN_VISUAL_DECISION`dur. Aynı
  frozen sentetik rig içindeki A/B kontrollüdür; gerçek kareler farklı
  specimen ve fotometrik olarak kayıtsız olduğundan pixel-distance,
  digital-twin, photorealism veya YOLO-fayda kanıtı değildir.
- Güncel altı teknik adayın manifestleri:
  [cube clean](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cube_clean_role_scan_4k_v1/evidence/ASSET_BUILD_MANIFEST.json),
  [cube pitted v2](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cube_pitted_role_scan_4k_v2/evidence/ASSET_BUILD_MANIFEST.json),
  [cube fractured v19](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cube_fractured_v19_role_scan_4k_v1/evidence/ASSET_BUILD_MANIFEST.json),
  [cylinder clean](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cylinder_clean_role_scan_4k_v1/evidence/ASSET_BUILD_MANIFEST.json),
  [cylinder pitted v2](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cylinder_pitted_role_scan_4k_v2/evidence/ASSET_BUILD_MANIFEST.json) ve
  [cylinder fractured v17](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/cylinder_fractured_v17_role_scan_4k_v1/evidence/ASSET_BUILD_MANIFEST.json).
- Kalibrasyon artefaktı keşfedilmiş fakat iki kameraya bağlanıp yeniden
  doğrulanmamıştır. Bu borç kapanmadan config'lerdeki 2.8 mm/100°/distortion
  değerleri visual-fit olarak kalır.
- `PROCEDURAL_PASS_SERIES_EXHAUSTED=true`, `GUIDE_EXHAUSTED=false`,
  `HERO_ACCEPTED=false`. Frozen-real YOLO ablation hâlâ çalıştırılmadı.
- Unreal Path Tracer parity de henüz kanıtlanmış bir koşu değildir; mevcut
  Unreal release Lumen/HWRT hattıdır. Path Tracer → Lumen sırası sonraki ortak
  asset aktarım kapısıdır.

## En yüksek getirili açık işler

1. Cam-10 ve cam-11 kalibrasyonunu ayrı kamera kimliği, board hash/ölçü,
   per-view error ve native resolution ile yeniden doğrula; mevcut NPZ'nin
   hangi kameraya ait olduğunu kanıtla veya reddet.
2. Clean/pitted/fractured cube+cylinder için ölçekli/cross-polarized macro,
   70–85% örtüşmeli photogrammetry ve gerçek upper-load/debris capture al.
3. Alt/üst platen, mavi powder-coat, gri kapı ve opal diffuser için scale,
   ColorChecker, diffuse+dört grazing ve metalde polarization; LED-off/
   LED-only/ambient ile lux/CCT/CRI/IES/LDT mümkünse ekle.
4. Bu veriden gerçek specimen scan/retopo, 4K–8K basecolor/roughness/
   tangent-normal/height ve cast/end/fracture/aggregate maskeleri üret;
   neutral/grazing/cam-10/cam-11 G0–G6 kapılarını yeniden çalıştır.
5. Beton kabulünden sonra aynı master asset'i Unreal'a taşı; Path Tracer
   parity sonrası Lumen ve annotation regression yap. Primitive yeniden
   authoring açma.
6. Son olarak 100-kare iki kişilik QC ve capture-safe frozen-real üç-seed
   ablation ile model değerini ölç.

Yeni procedural katsayı, yeni online model veya renderer toggle ancak bu
listede ölçümle çözülemeyen tek ve gözlenebilir bir gap'e cevap veriyorsa
eklenir.

## Engine seçimi ve başka domain'lere aktarım

- **EBIS/kapalı statik vision:** Blender canonical authoring ve deterministic
  offline annotation için en kısa baseline; Unreal aynı asset ile runtime,
  dinamik kapı/operatör/physics veya daha büyük orchestration gerekiyorsa.
- **Tren/outdoor:** Blender Curve+Geometry Nodes küçük statik RGB/depth/mask
  baseline için; Unreal spline+Landscape+PCG+foliage/weather/world streaming
  için ana aday. İnce rail crack/line-scan defect, iki motorda da gerçek
  pixel pitch/MTF ve ölçülü geometri olmadan gerçekçi sayılmaz.
- **Tarım:** asıl zorluk motor değil tür/büyüme evresi/morfoloji, yaprak SSS,
  occlusion ve toprak/nem prevalansıdır. Asset dosya sayısı değil fiziksel
  state coverage'i ve frozen-real slice faydası yatırımı belirler.

## Bilgi biriktirme ve güncelleme kapısı

Yeni bir realism işi tamamlandığında aynı değişiklikte bu belgeye yalnız şu
kalıcı bilgiler eklenir:

1. hangi gerçek referans/ölçüm yeniden açıldı;
2. baskın fark neydi ve hangi tek değişken denendi;
3. actual-pixel/validator/annotation sonucunda ne kabul veya reddedildi;
4. hangi motor/driver/config/asset sınırında deterministikti;
5. hangi iddia hâlâ yapılamaz ve sonraki en değerli girdi nedir.

Tekil seed sayıları, uzun hash listeleri ve geçici komut logları burada
çoğaltılmaz; ilgili immutable manifest/decision'a linklenir. Yeni bir doc,
pass veya asset build bu beş maddeden kalıcı bir ders ürettiyse
`lessons_learned.md` güncellenmeden iş “handoff complete” sayılmaz.
Sohbet oturumu taraması da aynı kurala tabidir: commentary'deki iddia mevcut
artifact/hash/piksel ile doğrulanır; yalnız hata mekanizması kalıcı ve
tekrarlanabilir ise “başarısız pilot dersi” olarak kanonikleştirilir. Canlı
oturum için denetim kesiti yazılır; “oturumun tamamı” gibi açık uçlu bir
eksiksizlik iddiası yapılmaz.

Ana ayrıntı kaynakları:

- [realistic asset pipeline](realistic_sim_guide.md)
- [iterative fitting ve validation notları](tuning.md)
- [hero-quality component guide](ebis-blender/docs/HERO_QUALITY_DIGITAL_TWIN_GUIDE.md)
- [capture protocol](ebis-blender/docs/HERO_CAPTURE_PROTOCOL.md)
- [Blender bbox policy](ebis-blender/docs/BBOX_OCCLUSION_POLICY.md)
- [Unreal bbox policy](unreal-ebis/docs/BBOX_OCCLUSION_POLICY.md)
- [Blender handoff](ebis-blender/reports/handoff/EBIS_BLENDER_HANDOFF_REPORT.md)
- [Unreal handoff](unreal-ebis/reports/handoff/UNREAL_EBIS_HANDOFF_REPORT.md)
- [Unreal MCP](unreal-ebis/docs/UNREAL_MCP.md)
- [output publication](OUTPUT_CONVENTION.md)
- [model ablation plan](blender_ve_unreal_ablation_plan.md)

# Kronolojik kanıt günlüğü

## Ortak dersler

1. Engine seçimi tek başına kalite üretmez. Kamera/sensör eşleşmesi, doğru asset ölçeği, annotation sözleşmesi ve gerçek-only benchmark engine’den daha belirleyicidir.
2. Görsel gerçekçilik ile model faydası ayrı kapılardır. Önce geometry/label/artefakt PASS, sonra sabit gerçek test setinde ablation.
3. Domain randomization kontrol edilebilir ve raporlanabilir olmalıdır. Her kare seed, kamera, ışık, materyal, hava/çevre, obje durumu ve output hash’i taşımalıdır.
4. Semantic segmentation’dan otomatik bbox, instance/occlusion ontolojisi olmadan güvenli değildir. Çoklu nesnede ayrı instance maskesi gerekir.
5. “Daha çok sentetik” varsayılan çözüm değildir. 100-kare QC ve 1N ablation fayda göstermeden 10k üretime geçilmez.
6. Ardışık video frame’lerinde rastgele split sentetik faydasını yapay biçimde yüksek gösterebilir. Capture/session/sequence ayrımı üretimden önce freeze edilmelidir.
7. MCP en iyi küçük, doğrulanabilir işlemler ve screenshot/scene-info round-trip için çalışır. Büyük prosedürel üretim tek deterministik script/config ile yönetilmeli; MCP doğrulama ve kontrollü ince ayar katmanı olmalıdır.
8. EBİS'in en etkili görsel düzeltmesi renderer değiştirmek değil fiziksel
   topolojiyi düzeltmekti: kapalı cabinet, sağ menteşeden dışa açılan dolu gri
   kapı/servis kapağı, sample'a temas eden iki 40 cm disk ve upper-platen
   kotunda üç duvarı izleyen dar U-diffuser. Aynı spec iki engine'e
   uygulanmadan renderer kıyası anlamlı değildir.
9. Frame ortalaması bimodal ışık hatasını gizler. Gerçek referansın black/clip
   percentile aralığı, concrete ROI ve fixed seed contact sheet birlikte
   izlenmelidir. Sensör pedestal'ı saf siyahı kaldırabilir ama kayıp shadow
   detayını veya yanlış PBR'ı geri getirmez.
10. Gerçek kırık, “hasar noise'u” değil topoloji problemidir. Dikdörtgen
    Boolean makinede açılmış oyuk gibi; büyük additive icos yapıştırılmış taş
    gibi; örtüşen eş ölçekli kesiciler ise kristal/adacık gibi okundu. Blender
    için tek bağlı düzensiz hull daha güvenli bounded fallback, Unreal için
    multipart notched body annotation açısından kararlı fallback oldu. İkisi
    de ölçülmüş kırık scan'inin yerini tutmaz.
11. Malzeme tuning'i actual-pixel red/green kararıyla yapılmalıdır. Unreal
    üst tabla same-seed ROI lumasının düşmesi ve Blender betonundaki geniş
    karanlık bulutun kaldırılması hedeflenen değişimin piksele ulaştığını
    kanıtladı; “daha gerçekçi” veya “YOLO daha iyi” sonucunu tek başına
    kanıtlamadı.
12. Motorlar arası aktarılabilir olan node isimleri değil fiziksel
    sözleşmedir: aynı cabinet parçaları, aynı tabla/sample teması, aynı
    U-diffuser topolojisi, aynı kamera/shape hücreleri ve aynı görünür-instance
    bbox politikası. Blender Boolean ve Unreal multipart mesh uygulaması
    farklı kalabilir.
13. Çevrimiçi asset “daha gerçekçi” olduğu için otomatik seçilmez. Poly Haven
    mavi sacı gerçek hammertone yerine seam/uzun çizik; Unreal direct-UV
    ambientCG concrete ise gerilme/kontrast ipucu üretti ve reddedildi.
    Blender'da yalnız düşük-oranlı box-projection concrete hibriti gerçek ROI
    yönünde ilerledi. Lisans+ölçek+hash ve same-seed actual-pixel A/B zorunlu.
14. Unreal'da ilk karedeki checker, sahne materyali gibi görünebilen shader
    compilation fallback'idir. Batch'in yalnız ilk seed'inde görülmesi
    diagnostiği sağladı; synchronous recompile ve aynı ilk-seed rerender
    release öncesi kapı olmalıdır.
15. Review klasörü immutable run adı olmamalıdır. İki engine'de
    `output/current_samples/` dört kamera×şekil hücresini atomik yayınlar;
    `CURRENT.json` kaynak validation ve dosya hash'lerini taşır. Eski run,
    hero, A/B ve MCP görselleri current release seçilmeden temizlenmez.

## Hero concrete asset-build dersi — 2026-07-31

- On procedural pass'i bitirmek, hero guide'ı bitirmek değildir. İlk seri
  geometry/annotation/determinism/MCP iskeletini güvenilir yaptı; fakat
  measured specimen scan, petrology/BRDF, matched camera ve release kapıları
  açık kaldığı için `HERO_ACCEPTED=false` doğru sonuçtur.
- Silindir kırığında en büyük görünür sıçrama daha yüksek texture resolution
  veya daha fazla noise'dan gelmedi. Normalize UV'deki structured lattice ve
  Delaunay, metre uzayında yatay taş/plaka üretti. Triangulation `u`
  koordinatını çevre/yükseklikle ölçeklemek ve donor crop'un fiziksel
  aspektini korumak yatay teras cue'sunu kaldırdı.
- Aggregate'i yüzeye ayrı icosphere/boncuk olarak eklemek yerine recessed
  primary manifold üzerindeki face rolü yapmak, hem clay görünümünü hem
  instance ontolojisini iyileştirdi. Büyük kırık depth render mesh'te,
  sub-mm mikro relief high→render bake'te kalmalıdır.
- Clay grazing render, PBR'dan önce geometriyi elemek için en ucuz kapıdır.
  v17'de iyileşmenin clay'de de görünmesi shader kamuflajı olmadığını
  doğruladı; buna rağmen real crop'taki asimetrik mortar/aggregate petrology
  hâlâ açıktır.
- UV ve tangent gate'leri fail-closed olmalıdır. v17 1K atlasında
  `331,338` occupied texel / `0` overlap; tangent bake'te açıkça kayıtlı
  `%1.04` bounded repair ve final `0` invalid pixel vardır. Bunlar teknik
  aktarım kanıtıdır, materyal/hero kabulü değildir.
- Aynı seed'deki PNG dosya hashleri encoder metadata'sı yüzünden farklıyken
  decoded neutral/grazing/mask RGB bufferları bit-exact çıktı. Görsel dataset
  determinismi container byte'ı yerine canonical decoded pixel hash'iyle
  ölçülmeli veya PNG metadata'sı normalize edilmelidir.
- Blender→Unreal aktarımında taşınacak değer node graph değil; aynı
  `29,185`-vertex closed render mesh, metre ölçeği, split normals,
  cast/end/fracture/aggregate masks ve OpenGL→DirectX normal sözleşmesidir.
  Unreal'da kırığı primitive'lerle yeniden yapmak bu kazanımı geri alır.
- Bir sonraki büyük kaldıraç yeni procedural katsayı değildir:
  cross-polarized/ölçekli macro veya photogrammetry, ardından altı canonical
  state için current-pipeline 4K bake ve matched cam-10/cam-11 kalibrasyonudur.
  Altı generic 4K teknik build 1 Ağustos'ta tamamlandı; gerçek capture,
  matched-camera ve hero kabulü açık kaldı. Bunlar kapanmadan görsel kalite
  YOLO faydası olarak yazılamaz.

## Final front-door/PBR ve temizlik turu — 2026-07-30

- 18+ zaman/makine yayılı LED/IR incelemesinden çıkarılan sabit topoloji,
  iki engine'de aynı sözleşmeye taşındı: mavi back/left/right hammertone,
  gri solid right-hinged front door ve ona parent servis kapağı, çıplak
  çelik tablalar, üç-duvar U-LED.
- Blender `realism_v7_frontdoor_pbr_release_59300` 12/12 `PASS`; 41 RFID
  ve 65 visible binary maske. Güncel BlenderMCP wide-open V7 sahnesinde
  `164→164`, 1080p/128 spp OptiX `PASS`; listener kapalı.
- Unreal `realism_r56_frontdoor_release_59400` 12/12 `PASS`; 54 visible
  + 54 amodal maske, dört bbox hücresi gerçek hedefe `≤0.06`. Güncel Epic
  MCP 9-call build/validate/status/render `PASS`; editor/port kapalı.
- Küp/silindir içbükey dikey konturu, sürgü/cam kapı ve turuncu sabit
  hardware negatif ipuçları kaldırıldı. Turuncu kalan parçalar yalnız
  gerçek hedef sınıfı olan görsel RFID'lerdir.
- Sabit review girişleri
  [`ebis-blender/output/current_samples`](ebis-blender/output/current_samples/contact_sheet.png)
  ve
  [`unreal-ebis/output/current_samples`](unreal-ebis/output/current_samples/contact_sheet.png);
  convention [`OUTPUT_CONVENTION.md`](OUTPUT_CONVENTION.md) içindedir.
- Yerelde 2,848 GiB + 0,023 GiB, 3090'da 3,324 GiB obsolete
  output/QC/MCP-image artefaktı `gio trash` ile geri alınabilir biçimde
  taşındı. Manifestler `reports/cleanup/` altındadır; gerçek veri, code,
  config, docs, PBR kaynakları ve nested reference-forensics hedef değildi.
- Bu turda YOLO eğitimi yapılmadı; görsel/teknik iyileştirmeler model
  kazancı olarak yazılamaz.

## Multi-repeat gerçekçilik pass 1 — 2026-07-29

- 52 LED RGB + 33 IR/gri ton karedaki ortak topoloji yeniden kontrol
  edildi. IR renk/PBR kalibrasyonu için değil, cabinet–tabla–kapı–kamera
  parçalarının zaman ve makine boyunca ayırt edilmesi için yararlıdır.
- Tam kare histogramı tek başına yanıltıcıdır. Aynı turda gerçek/sentetik
  tam kare ile concrete bbox ROI `p5/p50/p95`, clipping ve black crush
  birlikte ölçülmelidir. Blender concrete mean'i yaklaşırken gerçek
  highlight/hasar kuyruğunu kaçırdı; Unreal cam-10 mean'i yaklaşırken
  temas sınırı `p5=5` üretti ve cam-11 karanlık kaldı.
- Unreal Material Noise `Scale` alanı Blender'daki “özellik boyutu”
  sezgisiyle ayarlanırsa dev cellular/marble desen oluşabilir. Parametre
  ismine değil, sabit seed tam çözünürlük çıktısındaki feature çapına
  bakılmalıdır.
- Lokal fiziksel bounce/contact spill, global exposure veya siyah pedestal
  ile yapılan düzeltmeden daha güvenlidir. Yine de ışıkla geometri/normal
  hatası örtülmemelidir: Unreal üst tabla–sample siyah bandı debug-pass
  gerektiren açık blocker olarak bırakıldı.
- Blender v1.7.4 ve Unreal surface pass kaynakları teknik RGB/instance
  pilotunda PASS aldı; bu tur depth veya yeni MCP round-trip çalıştırmadı.
  Önceki engine kanıtları yeni source hash'lerine mal edilmedi.
- [Piksel audit'i](reports/qc/multi_repeat_pass1_pixel_audit.json) ve
  [birleşik sheet](reports/qc/multi_repeat_pass1_reference_blender_unreal.png)
  sonraki motorlar-arası kıyasın başlangıç pin'idir. Model faydası hâlâ
  yalnız frozen gerçek test split'li üç-seed nano ablation ile kabul edilir.

## Multi-repeat gerçekçilik pass 2 — 2026-07-29

- Farklı task ve tarihlerden 9 yeni LED RGB ile 7 IR/gri kareyi yeniden
  açmak, küp numune formunun kategori seviyesinde eksik olduğunu gösterdi:
  gerçek form düz kart değil; kirli, kırışık, bantlı, basılı/el yazılı ve
  RFID'yi fiziksel olarak tamamen ya da uç bırakacak biçimde örtebiliyor.
- Kâğıt bir detection target değil, fiziksel occluder olmalıdır. RFID bbox'ı
  kâğıdın varsayılan örtme oranından değil, örtme sonrası ayrı
  visible-instance maskesinden çıkarılmalı; tamamen gizli instance
  metadata'da kalıp normal YOLO satırı almamalıdır.
- Blender'da yalnız shader bump silüeti düzeltmedi. Bounded subdivided
  irregular mesh + Solidify/Bevel, baskı/el yazısı/bant katmanlarıyla
  birlikte gerekli oldu. Yine de scan olmadan ağır yırtık/kat ve gerçek
  baskı varyansı yakalanmadı.
- Unreal'ın ilk kâğıt materyali tan/parşömen gibi okundu. Aynı seed'i
  koruyup V2 chroma/kontrastını düşürmek kontrollü düzeltme sağladı;
  full-resolution ROI hâlâ gerçek kareden daha dar luminance dağılımı ve
  daha düşük lokal gradient gösterdi.
- Silindire kâğıt sarmak ölçü/mesh olmadan “floating card” ipucu
  üretmektedir; belirsizliği sahte hassasiyetle kapatmak yerine cube-only
  kontrollü augmentation olarak kaydetmek daha güvenlidir.
- Blender v1.7.5 ve Unreal r7 final pilotları teknik PASS aldı ve seçili
  local/3090 SHA-256'ları eşleşti. Bu tur depth, yeni MCP veya YOLO
  çalıştırmadı; önceki kanıtlar yeni source hash'lerine mal edilmedi.
- [Piksel audit'i](reports/qc/multi_repeat_pass2_pixel_audit.json) ve
  [birleşik sheet](reports/qc/multi_repeat_pass2_reference_blender_unreal.png)
  sonraki tur için pin'dir. En yüksek açık Unreal contact/fascia/cam-11
  debug ayrıştırması ve iki engine için gerçek concrete/form surface
  capture'dır.

## Multi-repeat gerçekçilik pass 3 — 2026-07-30

- 13 yeni LED RGB ve 16 IR/gri kareyi gerçek piksellerden yeniden açmak,
  iki engine'deki büyük beyaz üst fascia yorumunun yanlış olduğunu
  gösterdi. Zaman ve makine boyunca sabit parça, numuneyi alt diskle
  sıkıştıran geniş koyu dairesel üst çelik disktir; ışık üç duvar
  boyunca ince bir sınırdan gelir.
- Renk/exposure'u kör ayarlamak yerine ayrı `upper_contact_face`
  geometrisi kurmak daha güvenliydi. Çap, kalınlık, alt uzama ve pozitif
  sample-gap her kare metadata'sına kondu ve validator hard-gate yapıldı.
- Milimetre değerleri ölçüm gibi sunulmamalıdır. CAD gelene kadar
  `0,985` çap oranı ve çok ince yüz/boşluk yalnız bounded visual-fit
  fallback'idir; gerçek ölçü gelince config'ten değiştirilebilir.
- Aynı-seed actual-pixel karşılaştırmasında üst bant luminance mean'i
  Blender'da `0,494 → 0,427`, Unreal'da `0,530 → 0,365` oldu. Bu yalnız
  hedeflenen düzeltmenin piksele yansıdığını gösterir; kalite veya model
  kazancı değildir.
- Unreal ilk tanıda koyu diski gereğinden siyah çizdi ve mevcut procedural
  kâğıt ilk offscreen capture'da default checker'a düştü. V1 artefaktı
  reddedildi; V2 yüz ve synchronous material recompile ile aynı seed
  tekrar açıldı. Asset varlığını değil final pikseli denetlemek gerekir.
- Blender v1.7.6 ve Unreal r8 final pilotları 8/8 teknik PASS aldı;
  iki kamera ile iki sample şekli dengelidir ve 14 seçili local/3090
  SHA-256 çifti eşleşti. Depth, güncel MCP, production QC ve YOLO bu
  turda çalıştırılmadı.
- [Piksel audit'i](reports/qc/multi_repeat_pass3_pixel_audit.json) ve
  [birleşik sheet](reports/qc/multi_repeat_pass3_reference_blender_unreal.png)
  sonraki tur için pin'dir. En yüksek kalan ortak açık, gerçek cube ve
  silindirin yüksek frekanslı agrega/edge-chip/temas yüzeyi
  photogrammetry/PBR eşleşmesidir.

## Multi-repeat gerçekçilik pass 4 — 2026-07-30

- Altı farklı LED task dizisinden 16 RGB kare ile sekiz farklı
  makine×kamera grubundan 16 IR/gri kareyi yeniden açmak, betonu tek bir
  sürekli `damage` sayısıyla temsil etmenin yetersiz olduğunu gösterdi.
  Temiz kalıp yüzü, pitted döküm, kenar-aşınmış ve spalled numune ayrı
  kategorik rejimlerdir. Yine de bu rejimlerin config ağırlıkları gerçek
  korpusta ölçülmüş prevalans değil, geçici bounded augmentation'dır.
- Yüzey RNG'sini ana sahne RNG'sinden ayırmak kontrollü karşılaştırmayı
  korudu: aynı seed'de kamera, ışık ve RFID kararı değişmeden yalnız
  yüzey rejimi/relief uygulanabildi. Yeni bir realism parametresi
  eklerken eski karar zincirini kaydırmamak regression denetimini ciddi
  biçimde kolaylaştırır.
- Geometri proxy'si mutlaka tam çözünürlükte açılmalıdır. Unreal'daki
  ilk koyu gözenek küreleri sayısal olarak “daha fazla detail” üretse de
  beton üstüne yapışmış boncuk gibi okundu. İnce tangent koyu diskler bu
  negatif ipucunu azalttı; hâlâ dairesel proxy'dir, gerçek cavity veya
  scan değildir.
- Silindire yapışan RFID tek bir düz kart olamaz. Film, copper ve chip
  aynı yerel eksen takımını paylaşan 16 parçalı yay olarak yüzeye
  konforme edildi. Tabla arası tag'in uzun ekseni boşluğa girmeli ve
  görünür uç micro/partial/major rejimi metadata ile validator'da
  doğrulanmalıdır.
- Occlusion threshold'larını “daha çok train karesi çıksın” diye
  gevşetmemek doğruydu. İlk Unreal pilotunda 8/8 exclude sonucu fiziksel
  state/tip dağılımındaki sorunu açığa çıkardı. State karışımı referans
  gözleme göre geçici `5/8 sample-attached, 2/8 plate-gap, 1/8 loose`
  yapıldı; final pilot yine 5/8 exclude verdi. Bu, label politikasının
  çalıştığını gösterir ama production dağılımı değildir.
- Actual-pixel ROI denetimi açığı nicel tuttu. Gerçek cylinder için
  2 px high-pass `0,01484`, Unreal r15 için `0,00595`; gerçek cube için
  `0,00776`, Blender v1.7.7 için `0,00352` oldu. Unreal sensör gürültüsü
  gradient'i şişirdiği hâlde gerçek düzensiz pore/aggregate kuyruğu
  kapanmadı.
- Blender'ın sakin çok-ölçekli materyali Unreal V14 frekans/kontrastını
  sınırlamak için; Unreal'ın conforming-contact ve tip-regime validator'ı
  ise Blender'ın sonraki RFID fiziksel temas turu için kullanılmalıdır.
  Motorlar arası aktarım ortak sözleşmedir, görsel eşitlik değildir.
- [Piksel audit'i](reports/qc/multi_repeat_pass4_pixel_audit.json) ve
  [birleşik actual-pixel sheet](reports/qc/multi_repeat_pass4_reference_blender_unreal.png)
  sonraki tur için pin'dir. Depth, güncel MCP, production insan QC'si ve
  frozen gerçek test split'li YOLO ablation bu turda yoktur; model
  kazancı iddia edilemez.

## Multi-repeat gerçekçilik pass 5 — 2026-07-30

- Task 9–14'e ve iki kameraya yayılmış 18 yeni LED RGB kare ile
  **18 REF makine×kamera grubunun tamamından** birer IR/non-LED gri kareyi
  yeniden açmak, iki motorun ortak en büyük lokal hatasının alt tablayı
  fazla temiz, parlak ve beyaz göstermesi olduğunu ortaya çıkardı.
  Gerçekte temas yüzü koyu kullanılmış çelik; dairesel/radyal aşınma,
  beton tozu veya nemli artık, ufak debris ve lokal speküler yansıma
  birlikte görülüyor.
- Tabla gövdesinin materyalini global değiştirmek yerine ayrı, ince bir
  `lower_contact_face` geometrisi eklemek hem fiziksel sözleşmeyi hem de
  controlled same-seed regresyonu korudu. `dry_used`, `dusty_used` ve
  `damp_residue` rejimleri ana sahne RNG'sinden bağımsız seçiliyor;
  kamera, kapı, numune, RFID ve ışık kararı yerinde kalıyor.
- Çap/kalınlık/kot ve profil ağırlıkları CAD, ölçülmüş BRDF veya korpus
  prevalansı değildir. Blender'daki `394 mm × 0,8 mm`, Unreal'daki
  eşdeğer `39,4 cm × 0,08 cm` yüz yalnız bounded visual-fit fallback'idir;
  metadata ve validator bu belirsizliği açıkça taşır.
- Unreal'da 32 debris actor'ı `z=7,0–9,6 cm` iken tabla üstü
  `z=23,55 cm` idi; yani dekorun çoğu görünür yüzün altında kalıyordu.
  Eski random z draw'u tüketilip yeni kot tabla üstüne remap edilerek
  sonraki sample/tag RNG sırası korunurken bu fizik hatası giderildi.
  Sekiz santimetre-ölçekli dekor taşı yerine yalnız iki nadir büyük chip
  ve daha küçük bir kuyruk bırakıldı.
- İlk same-seed tanılarda dusty yüz iki motorda da fazla açık/renkli
  okundu; finalden önce daha koyu ve nötr ikinci materyal açıldı. Başarılı
  render kod veya asset varlığı değil, actual pixels açıldıktan sonra
  seçildi.
- Kontrollü alt-tabla ROI mean RGB'si Blender'da
  `[126,118,110] → [98,88,81]`, Unreal'da
  `[191,175,154] → [130,108,80]` oldu. Seçilen gerçek LED koyu sektör
  `[70,70,82]` idi. Görüşler register olmadığı için bu değerler yalnız
  eski beyaz-disk ipucunun azaldığını gösterir; renk kalibrasyonu veya
  engine sıralaması değildir.
- Unreal'ın 2 px high-pass değeri `0,01973 → 0,03443` yükselip seçilen
  gerçek LED ROI'nin `0,02932` değerini hafif geçti. Noise ile materyal
  speckle'ını “daha fazla gerçek detay” diye yorumlamamak gerekir; güncel
  Unreal çıktısında over-texturing açık risktir. Blender'ın circular
  residue/wear alanı ise gerçek örnekten hâlâ fazla sakin ve düzgündür.
- İki motorun sekizer final pilotu iki kamera ve iki numune şeklinde
  dengeli teknik PASS aldı. Blender `3 standard / 5 hard`, Unreal
  `3 standard / 5 exclude` verdi; partition politikası daha çok train
  karesi almak için gevşetilmedi.
- [Piksel audit'i](reports/qc/multi_repeat_pass5_pixel_audit.json) ve
  [birleşik actual-pixel sheet](reports/qc/multi_repeat_pass5_reference_blender_unreal.png)
  güncel pindir. Bu tur depth, güncel Blender/Unreal MCP, production
  insan QC'si veya frozen gerçek test split'li YOLO ablation çalıştırmadı;
  fotogerçekçilik, engine üstünlüğü ve model kazancı iddia edilemez.

## EBIS Blender — kanıt-temelli

### Ne işe yaradı?

- 2.960 gerçek LED görüntüsü, 15.596 RFID ve 2.945 concrete kutusunu ölçmek; kamera, sample ölçeği ve tag görünürlük politikasını tahminden çıkardı.
- Küp ve silindiri ayrı koşullar olarak modellemek zorunlu oldu. Tek küp POC gerçek dağılımın önemli bölümünü kaçırıyordu.
- Büyük dairesel üst/alt tabla ve numunenin üst hizasındaki tam genişlik difüzör, sahne kimliğini küçük dekorlardan daha fazla iyileştirdi.
- Per-instance object pass index ve RGB ile aynı lens warp’lı maske, çoklu tag bbox’ını güvenli hâle getirdi.
- `standard/hard/exclude` için ayrı fiziksel dizin, visible-unlabelled tag’in normal train’e sızmasını metadata uyarısından daha güçlü biçimde engelledi.
- 32-kare contact sheet, tek hero renderın kaçırdığı non-manifold siyah yüz artefaktını yakaladı. Stratified küçük pilot gerçek bir release kapısıdır.
- Camera×shape medyanlarını ayrı ölçmek önemliydi: sekiz-kare pilot tek bir `camera_door × cube` hücresinde yanıltıcı küçük-N TUNE verdi. Nihai `v1.7.3` 32-kare gate’inde hücre başına `N=7–9` ile dört hücre de `±0.03` görsel kapıda geçti. Fiziksel küpü en/boy bozmak yerine, bağımsız detection still’lerinde kamera-koşullu bounded yaw kullanıldı; senkron iki-kamera üretiminde tek fiziksel yaw paylaşılmalı.
- Periyodik tabla Wave-normalini ve büyük yüzeyden taşan agrega parçalarını 1080p hero incelemesi yakaladı. Düşük çözünürlükte makul görünen procedural detay, gerçek çözünürlükte yapay tekrar veya “yapıştırılmış taş” okuyabilir; en az iki sabit 1080p material hero zorunludur.
- Blender CLI üretim hattı; config hash, atomic publication, output hash ve validator ile MCP’ye göre batch için daha basit ve tekrar üretilebilirdi. BlenderMCP’nin güncel `v1.7.3` loopback turu 160 nesnenin scene-info kararlılığını, offscreen viewport'u ve 1920×1080/128-sample OptiX renderı ayrıca doğruladı; doğrulama prosesi/portu tur sonunda kapatıldı.

### Nerede dikkat gerekiyor?

- Mevcut kamera intrinsics’i görsel fit’tir. Bbox medyanına yaklaşmak lens kalibrasyonu değildir.
- Gerçek dataset insan/el ağırlıklıdır; insan olmayan sentetiği tam gerçek sete körlemesine karıştırmak domain farkı yaratır.
- Gerçek timestamp/kamera overlay’i spurious feature olabilir. Ya iki domain normalize edilmeli ya overlay randomizasyonu yapılmalı.
- Boolean yüz hasarı, küçük sahnede bile non-manifold/normal artefaktı üretebilir. Pore/spall QC’si ve manifold kontrolü olmadan production yok.
- Warp öncesi amodal projection / warp sonrası visible mask visibility oranı proxy’dir. Kenar tag’leri hard partition’a yönlendirmek güvenli; piksel-hassas amodal truth için ikinci isolated-object pass gerekir.
- Workshop proxy kapı tarafına kaba derinlik verir ama gerçek fabrika yerine geçmez. Kalibrasyon ve lisanslı backplate yüksek etkili sonraki iştir.
- Model faydası henüz ölçülmedi. Son teknik PASS’i “YOLO sonucu iyileşti” diye aktarmak doğru değildir.

## Blender-tren — plan-temelli, deneysel sonuç değildir

Blender, statik RGB/depth/mask dataset’i ve deterministik offline annotation için doğrudan adaydır. İlk POC küçük tutulmalıdır:

- Curve + Geometry Nodes ile ray merkezi, iki ray, travers ve ballast koridoru tek parametreli generator olsun.
- Sınıflar önce `rail`, `sleeper`, `ballast`, `foreign_object`; defect ontology bunlardan sonra freeze edilsin.
- Yüksek güvenli büyük kusurlar/engellerle başlanmalı. Milimetre çatlak/aşınma, line-scan optiği ve gerçek sensor MTF/pixel pitch ölçülmeden “gerçekçi” sayılmamalıdır.
- Kamera pose, ray gauge, travers spacing ve obje penetrasyonu her seed’de otomatik fiziksel gate almalıdır.
- Outdoor gap’in baskın kaynakları asset dağılımı, ballast/metal materyali, bitki ve hava/ışık dağılımıdır; yalnız procedural geometri yetmez.
- 50–100 kare POC’de label hatası, geometri geçerliliği ve render maliyeti ölçülmeden büyük üretim yapılmamalıdır.

Blender’ın avantajı annotation kontrolü; riski büyük outdoor dünyanın elle/prosedürel asset kalitesidir. Genel statik frame üretiminde en kısa baseline olma ihtimali yüksektir, fakat bu henüz test edilmedi.

## Unreal-EBIS — kanıt-temelli

UE 5.8.1 hazır Linux build'i RTX 3090 SSD'ye kuruldu. Epic'in deneysel resmi `ModelContextProtocol` eklentisi `127.0.0.1:8000`, protocol `2025-11-25` ile hem tarihsel v1 hem güncel fiziksel r5 sahnesinde gerçek initialize/toolset/build/validate/render turunu tamamladı. Güncel tur 1080p RGB, benzersiz EXR depth ve 5/5 visible–amodal instance ile validator PASS aldı; sunucu tur sonunda kapatıldı. Proje toolset'i `ToolsetRegistry` üzerinden üçüncü taraf Unreal-MCP olmadan keşfedildi.

### Ne işe yaradı?

- Aynı deterministik scene generator'ın batch ve MCP tarafından çağrılması, MCP'yi üretim engine'i değil bounded kontrol/inceleme katmanı yaptı.
- Scene actor'larındaki `EBIS_INSTANCE` kimliği multipart beton/RFID geometry'sini tek fiziksel instance altında tuttu.
- Aynı SceneCapture2D ile visible pass ve yalnız target'ın kaldığı isolated amodal pass, fully-occluded/plate-gap politikasını Blender proxy'sinden daha doğrudan yaptı.
- Worst-visible-instance kararıyla `standard/hard/exclude` fiziksel dizinleri oluşturuldu; birleşik semantic bbox kullanılmadı.
- 16-kare pilotta 16 RGB, 16 benzersiz OpenEXR depth, 65 visible ve 65 amodal maske; iki kamera/iki şekil ve dört bbox hücresi PASS verdi.
- Seed 58203 iki bağımsız editor koşusunda RGB, EXR, decoded mask pikselleri ve YOLO label için aynı build/driver/3090'da bit-exact çıktı.
- Mevcut pipeline gözlenen 1280×720 maliyetinde yaklaşık 1,32 s/kareydi; bu Cycles baseline'ından hızlıdır fakat renderer/pass eşit olmadığı için engine benchmark'ı değildir.

### Kritik uygulama dersleri

- Precompiled Linux editor, yeni açılışta unlit mask material shader map'i hazır olmadan default beyaz çizebildi. Basit mask materyallerini synchronous recompile etmek sessiz all-white ground-truth hatasını giderdi.
- Rapid render-target değişiminde export önceki pass'i kopyalayabiliyordu. Bir piksel GPU readback'i render-thread fence olarak gerekli oldu.
- Depth capture source proxy güncellemesi synchronous editor tick'te gecikebildi. RGB ve bütün maskeler önce, depth en son capture edildi; depth'ten sonra pass çalıştırılmadı.
- PNG container SHA'sı encoder metadata/sıkıştırma yüzünden değişebilirken decoded mask pikselleri aynıydı. Determinism kanıtı file hash ve pixel hash'i ayırmalıdır.
- Lumen, PBR parametreleri ve ray tracing kendi başına gerçekçilik üretmedi. Ölçüsüz basic primitives/procedural materyaller Unreal çıktısını mevcut Blender hero'sundan daha CG gösterdi.
- Işık revizyonu clipping'i bounded tuttu fakat bazı profillerde platen/LED beyazı ve siyah crush sürüyor. CAD, bevel, gerçek surface scan ve sensor response daha yüksek getirili.
- Prosedürel sahne her seed'de yeniden kurulduğunda tek SceneCapture, Lumen/TSR
  history'sini beslemiyor. RGB'ye sekiz sabit warm-up, mask/depth'e sıfır
  warm-up kullanmak annotation'ı değiştirmeden gren ve first-frame sapmasını
  azalttı.
- Powder-coat metallic değildir. Gri/mavi sacı dielectric yapmak, AO'yu 18
  cm'den 3,5 cm'ye indirmek ve direct LED:diffuse-return oranını ayrı tutmak
  exposure'u tek başına kısmaktan daha güvenliydi.

### Bugünkü karar

Unreal'ın teknik annotation ve throughput hattı kullanışlıdır; görsel kalite bakımından Blender'ı geçtiği ve detection metriğini artırdığı gösterilmedi. Büyük Unreal dataset'e geçmeden aynı CAD/PBR/camera calibration ile 100-kare QC ve `R+B-1N` / `R+U-1N` üç-seed gerçek-test ablation yapılmalıdır. Unreal'ın EBIS değeri ileride dinamik kapı/operatör/physics veya Unreal-tren asset altyapısı reuse edilirse artabilir.

## Unreal-tren — plan-temelli, deneysel sonuç değildir

Landscape, spline, PCG, foliage, hava ve büyük dünya streaming nedeniyle ana Unreal adayı trendir. En sade yol:

- Template-first `RailCorridorGenerator`: spline’dan rail mesh, sleepers, ballast, terrain cut ve camera path.
- PCG graph değişiklikleri MCP ile küçük adımlarda yapılmalı; her adımdan sonra viewport screenshot ve property dump.
- Randomization: güneş/hava, wetness, pas, ballast tonu, bitki yoğunluğu, engel tipi/pose ve kamera yüksekliği/hızı.
- Semantic segmentation ilk annotation hedefidir; instance ve optical flow ancak temel label doğruluğundan sonra.
- Her seed’de gauge/spacing, mesh overlap, floating asset, terrain penetration ve camera clearance gate’i.
- İlk kapı: 20 seed × dört kontrol noktası geometri screenshot’ı. İkinci kapı: 50–100 label QC. Sonra Blender ile eşit gerçek-test ablation.
- İnce rail crack/aşınma için Unreal Nanite/material detail tek başına yeterli değildir; gerçek sensor sampling ve ölçülü defect geometry gerekir.

Unreal büyük/dinamik outdoor dünya için güçlü adaydır; MCP/PCG otomasyonu ve güvenilir ground-truth export entegrasyon riski taşır. Bu risk henüz deneyle ölçülmedi.

## Tarım simülasyonuna taşınacaklar

Plan-temelli not: crop/weed/soil üretiminde EBIS’ten taşınacak ana ilke instance ontolojisi ve gerçek dağılım audit’idir. Bitki asset çeşitliliği, büyüme evresi, occlusion, sıra geometrisi, toprak nemi ve sensör yüksekliği gerçek veriden ölçülmeden procedural scatter yeterli olmaz. Önce küçük gerçek-only baseline ve 1N sentetik ablation; biyolojik çeşitlilik yatırımı yalnız slice bazında fayda gösterirse büyütülmelidir.

## Multi-repeat gerçekçilik pass 6/6 final refinement — 2026-07-30

- Task 9–14 içindeki altı kamera-task grubundan üçer zaman quantile'ı
  alan 18 fresh LED kare ve 18 REF makine-kamera grubunun tamamından 18
  fresh IR kare açılınca ortak, güvenli lokal fark betonun üst yük
  bölgesiydi: gerçek numunede üst tabla altında ochre/koyu, pitted ve
  yönlü yük artığı var; sentetik gövde fazla homojen temizdi.
- IR yapısal/tonal invariance için yararlı, RGB renk hedefi için yanlış
  kaynaktır. Renk/materyal kararı LED RGB'den, değişmeyen tabla-temas
  ilişkisi iki modaliteden birlikte çıkarılmalıdır.
- İki motor aynı profil adı, independent RNG, rejim-bağımlı count ve
  açık belirsizlik statüsü taşıdı; ancak renderer'a uygun realization
  farklı kaldı. Blender dithered-alpha mikro-yamayı kaldırırken Unreal
  translucency depth-sort “sabun köpüğü” ürettiği için sığ opaque disc
  kullandı. Ortak fiziksel sözleşme, aynı shader tekniği demek değildir.
- Unreal'da translucent sphere ve opaque sphere; Blender'da iri opaque
  blob actual-pixel incelemede reddedildi. Küçültme ve kümelendirme,
  “daha çok detay” eklemekten daha gerçekçi sonuç verdi.
- Ayrı `top-load-weathering-v1` RNG'si sahne kararlarını korudu. Blender
  same-seed audit'inde 12/12 label ve 60/60 mask pikseli; Unreal'da
  12/12 label ve 208/208 mask bbox aynı kaldı. Unreal'da değişen dört
  concrete mask yalnız tek seed'in yük-bölgesi iç pikselleriydi.
- Kontrollü değişiklik seçilen karelerde beton üst %28'e kapandı:
  top/lower mean-absolute RGB fark oranı Blender'da `484×–1154×`,
  Unreal'da `4103×–7129×`. Bu oran domain yakınlığı, fotogerçekçilik
  veya model metriği değildir; yalnız değişiklik lokalizasyonudur.
- Final pilotlar Blender'da `12/12`, Unreal'da `12/12` validator PASS;
  current-source BlenderMCP ve Epic resmi Unreal MCP ayrıca gerçek
  loopback build/validate/render turu aldı. Her iki listener/editor ve
  port tur sonunda kapatıldı.
- Final matched sheet hâlâ daha yüksek değerli boşlukları gösteriyor:
  gerçek geniş/yönlü load streak ve aggregate kırığı, makineye özgü
  panel/kapak topolojisi, gri-mavi alan oranı, operator/hand dağılımı,
  ölçülmüş fisheye/sensor response ve çelik/powder-coat/concrete BRDF.
  Sonraki adım daha fazla procedural noise değil; polarize ölçekli
  yakın plan/scan, CAD/ölçü, checkerboard, grey-card, empty-chamber ve
  diffuser açık/kapalı capture'dır.
- Kanonik karar kaydı
  [MULTI_REPEAT_PASS_6_FINAL_REFINEMENT_2026-07-30.md](MULTI_REPEAT_PASS_6_FINAL_REFINEMENT_2026-07-30.md),
  görsel kıyas
  [multi_repeat_pass6final_matched_comparison.png](reports/qc/multi_repeat_pass6final_matched_comparison.png)
  ve annotation/piksel denetimi
  [multi_repeat_pass6final_pixel_audit.json](reports/qc/multi_repeat_pass6final_pixel_audit.json)
  dosyalarıdır. YOLO faydası hâlâ ölçülmedi; frozen gerçek test
  multi-seed ablation olmadan kazanç iddia edilmez.

## EBIS realism-v2 clean-assets pass 1/6 — 2026-07-30

- Zaman yayılı LED ile bütün REF makine×kamera gruplarını yeniden açmak,
  “daha fazla noise” yerine gerçek ölçekli cast pore ve load-zone rejimini
  hedeflemeyi sağladı. Aynı gerçek korpusta temiz ve ağır hasarlı numune
  birlikte bulunduğu için ağır roughness bütün sentetiğe yayılmamalıdır.
- Blender'da küçük-ağırlıklı radius dağılımı ve fiziksel pore geometrisi,
  dış texture'ı güçlendirmekten daha kontrollüydü. Poly Haven Rough Concrete
  CC0 ve ölçekli olmasına rağmen same-seed iki ROI'de yalnız
  `4.78–4.94/255` fark verdi; güçlü karışım plaster karakteri taşıyacaktı.
  Lisans/provenance temizliği fiziksel uygunluk değildir.
- Unreal Noise node ölçeğini küçültmek hücreleri küçültmedi; daha büyük
  mermer bulutları üretti. V24 cellular ve V25 cloudy albedo yerine constant
  neutral cast BRDF + küçük fiziksel pore/edge/residue daha güvenliydi.
- LED proxy'nin fiziksel cover'ı ile aydınlatma katkısı ayrılmalıdır.
  Proxy/contact shadow'larını kapatmak siyah gölgeyi azalttı, fakat Unreal
  r59'daki geniş keskin planar light band'leri tamamen çözmedi. Sonraki iş
  texture değil, light transport/exposure/camera eşlemesidir.
- Sabit `output/current_samples` yalnız dört review hücresini, label,
  metadata, visible/amodal mask ve portable `CURRENT.json` hashlerini taşır.
  Yerelde üretilip 3090 `.current_samples.next` altında doğrulanarak atomik
  terfi ettirilmesi font/Pillow/absolute-path hash sapmasını kapattı.
- Cleanup allowlist'i release/current/final QC/MCP'yi koruyup V7/r56–r58 ve
  V25–V29 ara renderlarını `gio-trash` ile kaldırdı. A/B'nin ham 1.660+ dosyası
  yerine karar vermeye yeten tek compact sheet tutuldu.
- Actual-pixel eşlenik sheet hâlâ net: Blender beton fazla aydınlık/temiz,
  Unreal ışık/shading fazla planar, iki motorun sample occupancy/fisheye
  yakınlığı gerçek kameradan zayıf. Bu gap kapanmadan fotogerçekçilik; frozen
  gerçek test ablation olmadan YOLO faydası iddia edilemez.
- Güncel pass kaydı:
  [EBIS_REALISM_V2_PASS1_2026-07-30.md](reports/qc/EBIS_REALISM_V2_PASS1_2026-07-30.md).

## EBIS pass-11 loaded-edge / cleanup / handoff — 2026-07-30

- Online PBR, scalar roughness ve daha fazla noise tek başına gerçekçilik
  üretmedi. Blender same-seed strength adayında concrete-mask farkı yalnız
  `0.311489/255` ve görsel kazanç yoktu; aday reddedildi. Siluet, occlusion
  veya contact shadow değiştiren hasar geometri olmalıdır.
- Bağımsız detection still’inde spall tarafını görünür kameraya göre seçmek
  dataset coverage’i artırdı; fakat senkron iki-kamera üretiminde tek
  fiziksel state paylaşılmalıdır. Kamera-koşullu augmentation’ın fiziksel
  state sözleşmesi açık yazılmalıdır.
- Unreal’daki büyük fracture block’larını küçültmek yetmedi; retained
  fracture wall/floor içine gömmek yüzen/yapışmış taş ipucunu azalttı.
  Yine de rectilinear notch fracture mechanics değildir. Sonraki yatırım
  daha fazla primitive değil scan edilmiş fracture/aggregate library’dir.
- Kamera×şekil framing’i toplu ortalamayla değil dört hücreyle izlemek,
  cam-11 cube x-offset’i gibi lokal hatayı açığa çıkardı. +2 cm bounded
  target fit gate’i kapattı ama intrinsics/calibration yerine geçmedi.
- Unreal Lumen’i kapatmak poligonal light field’i çözmedi; renderer toggle
  yerine RectLight extent/placement/source-angle, material normals ve camera
  response debug pass’leri birlikte ayrıştırılmalıdır.
- Gerçek LED ile sentetik actual pixels yan yana açıldığında iki motorun
  baskın ortak açığı concrete aggregate/kırılma kuyruğu oldu. Gerçek ağır
  hasarlı örneği tüm sentetiğe kopyalamak da doğru değildir; rejim ağırlığı
  gerçek korpustan ölçülmelidir.
- Stable `output/current_samples` inceleme ergonomisini ciddi iyileştirdi.
  Aktif output’ta yalnız current + bir immutable release tutup eski
  diagnostic/release’leri hash’li, geri alınabilir trash’e taşımak hem
  kalabalığı azalttı hem provenance’ı korudu.
- Blender batch için CLI/Cycles hattı daha sade ve deterministik; BlenderMCP
  current-source scene/read/render doğrulaması için değerlidir. Unreal
  resmi MCP de aynı şekilde bounded control plane’dir; büyük dataset batch
  wrapper’dan üretilmelidir.
- Tren için aktarım: ince rail defect’i shader normal ile “varmış” gibi
  göstermek depth/occlusion ground truth’u bozar. Silueti/depth’i değiştiren
  kusur geometri, geniş outdoor dağılımı Unreal spline/PCG veya Blender
  Geometry Nodes ile; her iki durumda gerçek sensor sampling’i ölçülmelidir.
- Tarım için aktarım: soil/plant texture çeşitliliği dosya sayısı değil,
  fiziksel state ve prevalence çeşitliliğidir. Controlled single-factor
  A/B, scaled PBR/scan, instance identity ve frozen-real slice ablation aynı
  şekilde uygulanmalıdır.
- Kanonik karar:
  [EBIS_REALISM_PASS11_2026-07-30.md](reports/qc/EBIS_REALISM_PASS11_2026-07-30.md).
  Fotogerçekçilik, engine üstünlüğü ve YOLO faydası hâlâ iddia edilmez.

## Blender hero-concrete guide audit ve v15 — 2026-07-31

- On bounded pass'in bitmesi guide'ın bitmesi değildir. Doğru ayrım:
  `PROCEDURAL_PASS_SERIES_EXHAUSTED=true`,
  `GUIDE_EXHAUSTED=false`, `HERO_ACCEPTED=false`.
- Beauty'deki bir hata clay materyalinde de görünüyorsa texture/roughness
  ayarıyla gizlenmemelidir. v11'in yıldız katlanması, geniş Boolean
  damage n-gonlarının subdivision/displacement topolojisiydi.
- Güvenli sıra `damage-face retessellation → SIMPLE subdivision →
  role-bounded relief → clay grazing → PBR` oldu. Bu sıra v13–v15'te
  yıldız/origami artefaktını kaldırdı; teknik build PASS yine görsel kabul
  yerine kullanılmadı.
- Dataset etiketi veya “heavy spall” adı hasar ontolojisi değildir. Gerçek
  cam-10 crop yeniden açıldığında baskın cue geniş mağara değil, yoğun
  cast pore + granüler edge-ravel çıktı. v14/v15 bu nedenle mağara ve uzun
  dekoratif çatlakları kaldırdı.
- Periyodik büyük edge-chip, gerçek kırık değil “cookie bite” gibi okunur.
  Daha küçük, sığ, kısmen örtüşen ve tek evidence-backed kenarla sınırlı
  micro-ravel daha güvenliydi.
- Fracture UV artefaktı yüzünden bütün specimen bump'ını kapatmak cast yüzünü
  düz tebeşire çevirdi. Relief kararı material-role bazında verilmelidir:
  v15 cast/end micro-bump'ı korurken fracture/aggregate'i retessellated
  geometry authority'ye bıraktı.
- Unmatched gerçek/sentetik luma farkı materyali kör karartma gerekçesi
  değildir. v15 deployed medianı iki kamerada düştü, fakat intrinsics,
  framing, exposure/WB, diffuser ve sensor response eşlenik olmadığı için
  G4 açık kaldı.
- [Guide audit](ebis-blender/docs/HERO_CONCRETE_GUIDE_EXHAUSTION_AUDIT.md)
  ve [native 1:1 v11–v15 paneli](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v2_20260731/review/spalled_cube_topology_ab/SPALLED_CUBE_TOPOLOGY_AB_1TO1.png)
  sonraki beton çalışmasının karar pin'leridir. v15 1K development adayıdır;
  4K/current promotion, Unreal transferi veya YOLO kazancı değildir.

## Simulation Codex oturum fark denetimi ve pitted v2 — 2026-08-01

- `Simulation` oturumunun `2026-08-01 09:17 +03` kesiti, mevcut kanonik
  belge ve repo manifestleriyle karşılaştırıldı. Tekrarlanan anlatılar
  çoğaltılmadı; yalnız yukarıdaki koordinat/rol, face-order/UV, displacement
  ölçeği, çözünürlük-eşlenik validator, crop, rare-state ve execution
  dersleri kanonik bölümlere taşındı.
- En kritik validator düzeltmesi eşik değişikliği değil birim düzeltmesiydi:
  4K tangent hata sayısı 4K occupancy ile bölündü; kırık silindir sonucu
  `%0.728` bounded repair olarak manifestlendi. Hatalı v1.12.1 çıktı
  `rejected/` altında kaldı, fresh v1.12.2 build üretildi.
- Pitted v2 yalnız pitted profilini değiştiren A/B'de daha görünür bir üretim
  adayı oldu; 4K teknik build ve altı-state audit geçti. Human visual
  decision, matched-camera G4, stable current promotion ve hero kabulü açık
  bırakıldı. Küçük pit/silüet ilerlemesine rağmen iri void/aggregate
  kontrastı ve kamera-yönlü kırık görünürlüğü açık blocker olarak kaldı.
- İlk bbox-merkezli deployed panel üst damage bandını dışarıda bıraktığı için
  karar kanıtı sayılmadı. Üst bbox landmark'ına anchored native crop ve
  `gerçek/clean/adayı` üçlüsüyle 12 vaka yeniden üretildi; sonuç hâlâ staging
  PASS + insan kararıdır, dijital ikiz veya model faydası değildir.

## Hero Asset Build v4 final audit — 2026-08-01

- `4K`, 16-bit map, non-overlap UV, high-poly ve render-mesh kapılarının
  birlikte geçmesi önemli altyapıdır; görsel hero kabulü değildir. Altı asset
  teknik olarak tamamlandığı halde actual pixels generic betonun fazla açık,
  düzgün ve düşük petrology kontrastlı olduğunu gösterdi.
- Yüzey detayı deployed çözünürlükte gözlenmelidir. Pitted v2'de bounded
  radius/depth artışı pore'u görünür yaptı; yalnız 4K macro veya shader node
  sayısına bakmak aynı sonucu kanıtlamaz.
- Büyük hasar için doğru soru “asset fractured mı?” değil “hasar bu kamera ve
  yaw'da gerçekten gözleniyor mu?”dur. Aynı asset yaw=0'da clean'e yakın,
  yaw=180'de belirgin çıktı. Dataset'e `fractured_visible` ve
  `fractured_not_observable` partition/metadata ayrımı eklenmelidir.
- Orientation diagnostic'te top/lower A/B MAE oranı cube için `1.05→9.82`,
  cylinder için `1.30→3.85` oldu. Bu distance-to-real metriği değildir; fakat
  kamera-görünürlük sözleşmesi olmadan damage coverage iddiasının neden yanlış
  olduğunu ölçülebilir hale getirir.
- Geometri görünür olduğunda yeni blocker saklanmadı: cube upper fracture ince
  dalgalı kabuk/katman, cylinder patch sığ ve simetrik okunuyor. Daha fazla
  noise bu topoloji borcunu çözmez; volumetrik gerçek damage patch'i,
  photogrammetry/scan ve retopo gerekir.
- Teknik determinism yalnız iki kolay örnekte bırakılmadı. Altı state × iki
  kamera bağımsız `96 spp` tekrarında mask ve stabil metadata `12/12 exact`,
  beauty farkı en fazla `1/255`, üstü `0` çıktı. Bu G5 frozen-library
  güvenliğini güçlendirir; G4 gerçekçilik kapısını etkilemez.
- Instance maskesinden bbox üretmek yetmez; validator yazılmış PNG'nin hashini,
  scene-linear otorite bbox'ını, bağımsız decode bbox'ını, contact ve debris
  ownership politikasını birlikte denetlemelidir. v4 staging audit'i bunu
  12/12 vaka için yaptı.
- BlenderMCP batch renderer yerine current-source doğrulama control plane'i
  olarak en değerlidir: doğru semantic profile/version/material, scene count,
  OptiX render ve loopback endpoint doğrulandı; sonra exact Blender PID ve
  listener kapatıldı.
- Blender'ın otomatik `.blend1` dosyaları sessizce evidence ağacını şişirir.
  Obsolete cleanup yalnız exact hedef, byte/SHA envanteri ve korunan canonical
  karşılıkla yapılmalıdır. v4'te 13 yedek bu şekilde iki çalışma alanından
  temizlendi.
- Unreal'a aktarılacak en değerli şey primitive geometri değil, aynı FBX/PBR,
  semantic role, unit, normal convention ve acceptance debt sözleşmesidir.
  OpenGL normal green channel Unreal'da tam bir kez çevrilmeli; development
  contract G4/G6'yı otomatik kapatmamalıdır.
- En büyük sonraki kaldıraç artık kod/GPU değildir: cetvelli clean/heavy
  specimen capture, grazing/cross-polarized macro, en az bir volumetrik ağır
  kırık scan'i ve tek cam-10/cylinder karede photometric kalibrasyondur.
- Asset gerçekçiliği, detection annotation güvenliği ve YOLO faydası üç ayrı
  sonuçtur. İlk ikisi bile ayrı gate ister; YOLO kazancı yalnız frozen gerçek
  test ablation'ıyla söylenebilir.
- Kanonik handoff:
  [HERO_ASSET_BUILD_V4_HANDOFF.md](ebis-blender/docs/HERO_ASSET_BUILD_V4_HANDOFF.md)
  ve
  [v4 decision](ebis-blender/reports/qc/hero_concrete/runs/hero_asset_build_v4_20260801/decision.md).
