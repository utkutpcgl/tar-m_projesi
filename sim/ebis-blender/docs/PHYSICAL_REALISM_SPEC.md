# EBİS fiziksel ve görsel gerçeklik sözleşmesi — Blender

Revision: `2026-07-30-r7`; generator: `v1.7.15`.

Bu dosya `REF-65218_IVEDIK_LED_TARGET` reference-fit sahnesinin kanonik
görsel tarifidir. Doğrudan ölçülmeyen değerler fallback’tir; CAD,
kalibrasyon veya fiziksel ölçüm gibi sunulmaz. IR görüntüler yalnız
topoloji, occlusion ve değişmeyen parça kanıtıdır; RGB albedo, exposure
ve white-balance kaynağı değildir.

## Kanıt önceliği

1. Makine üzerinde cetvel/kumpasla ölçüm ve ölçünün göründüğü fotoğraf.
2. Üretici CAD/teknik çizimi.
3. Cam-10/cam-11 checkerboard veya ChArUco kalibrasyonu.
4. Aynı makinenin iki kamera ya da çoklu açı görüntü oranları.
5. Aynı makinenin farklı tarihli LED RGB ve IR görüntülerinde tekrar eden
   yapı.
6. Tek kare görsel fit.
7. Artistik tercih.

Üst sıra alt sırayı geçersiz kılar. Yeni fiziksel ölçüler
`configs/ebis_physical_measurements_template.json` içine kaynak dosya
adıyla yazılır. Başka REF klasörlerindeki makine varyantları hedef
REF-65218 ile hibritlenmez.

## Hedef makine ve değişmeyen topoloji

- Hedef, kapısı olan kapalı bir press cabinet’tir; açık oda veya siyah
  sonsuz fon değildir.
- Arka ve sol shell gri hammertone/pebbled metal, sağ chamber paneli ve
  ön aperture çevresindeki lokal bölgeler cobalt-mavidir. Bu bölgeler
  seed başına bağımsız renk değiştirmez.
- Sol yandaki erişim açıklığında gerçek hinge pivot’a bağlı kapı bulunur.
  `0°` kapalı halde sol duvar boyunca, pozitif açı dışarı-sola açılır.
  Config dağılımı çoğunlukla `78–108°`, azınlıkla `28–68°`’dir.
- Kapı kanadı, metal frame, safety glass, siyah gasket, hinge ve handle
  ayrı malzeme/okunabilir parça olmalıdır. Kapı tamamen FOV dışında da
  kalabilir; `camera_door` kadrajında aperture/door daha sık görünür.
- Arka yüzde yuvarlatılmış açık gri servis kapağı, ayrı dar gri port
  plakası, koyu seam/gasket, dört vida ve küçük lens/slot elemanları
  korunur.
- Küçük kamera donanımı tek siyah disk değildir: bezel, lens glass,
  iç lens ve yakın port/slot katmanlarından oluşan rear/side stack
  geometrisidir.
- Workshop yalnız açık sol kapıdan gelen derinlik/renk ipucudur; hedef
  makinenin parçası değildir ve etiketlenmez.

Fallback iç hacim `620 × 560 × 760 mm`dir.

## Tabla ve beton teması

- Üst ve alt tablalar aynı eksenli, dairesel, kullanılmış machined steel
  disc’tir.
- Fallback tabla çapı `400 mm`dir. `180 mm` küp kenarına oranı
  `2.22×`, `126 mm` silindir çapına oranı `3.17×`’dir. Bu değerler
  kullanıcı oranı ve bbox görsel fit’idir; ölçülmüş CAD değildir.
- Beton alt ve üst yüzü tablalara temas eder. Floating gap veya görünür
  penetrasyon hard fail’dir.
- Üst tablanın kalınlığı/shaft stack’i ve alt tablanın kenarı kamerada
  dairesel metal olarak okunur; düz beyaz tavan ya da siyah bant
  olmamalıdır.
- Tabla generic chrome değildir: düşük genlikli radial machining,
  hairline scratch, çimento tozu/kir, tonal patch, hafif roughness ve
  küçük bevel gerekir. Aşırı bullseye, ayna yansıması veya kapsül biçimli
  leke reddedilir. Wave/ring texture doğrudan normal sürmez; 1080p’de
  tüm tabla/tavanı kaplayan periyodik halka üreten materyal reddedilir.
- Alt tablanın numuneyle temas eden üst yüzü, parlak ana platen
  gövdesinden ayrı ince used-steel bölgedir. Fallback çap `394 mm`,
  kalınlık `0.8 mm`, üst kot `241 mm` ve specimen gap `0`dır; bunlar
  measured CAD değildir. Fresh LED ve bütün REF machine-camera
  gruplarında görülen kuru/aşınmış, beton-tozlu ve nemli-kalıntılı
  görünüm `dry_used / dusty_used / damp_residue` bounded rejimleriyle
  kapsanır. Rejim, geometri ve temas her kare metadata/validator
  sözleşmesidir.
- Alt tabla üstünde sınırlı kırıntı/toz olabilir; iri, parlak dekoratif
  taş dağılımı referans değildir.

## Tam boy üç-duvar LED

- Işık tek point/area light, tavan paneli veya iki kısa dikey bar
  değildir.
- İnce dikdörtgen channel üst tabla alt yüzüne yakın kotta back + left +
  right duvarı tam boy izler.
- Her segmentte aluminium housing, opal diffuser ve arkasında gizli
  emitter vardır. Ön kapı açıklığı boyunca dördüncü segment yoktur.
- Upper platen ve çevre geometri diffuser’ın önemli bölümünü fiziksel
  olarak örter. Bununla birlikte LED, betonun üst tabla ile temas
  bölgesinde dar spill/reflection ve chamber içinde yumuşak dolgu
  üretmelidir.
- LED modu chamber’ı mutlak siyah gölgeye düşürmez. World/interior
  bounce ve kapı açıklığı dolgu ışığı sınırlandırılmış biçimde korunur.
- Diffuser doğrudan görünürken küçük beyaz/cyan clip kabul edilebilir;
  geniş beton alanı veya tüm tabla clip olamaz.
- Fallback CCT profilleri `4300–6500 K` aralığındadır. Gerçek lux, CRI,
  CCT ve sabit exposure ölçülmeden enerji değerleri fiziksel ölçüm
  sayılmaz.

## İç sac ve PBR

- Panel düz renk değildir: mm ölçekli orange-peel/hammertone bump,
  daha büyük ölçekli mottling, toz/yağ tonal farkı ve grazing-angle
  rough specular gerekir.
- Bump silhouette’i bozmaz ve wallpaper gibi tekrar eden iri hücre
  üretmez.
- Gri ve mavi aynı rough powder-coat ailesinin iki ölçülü varyantıdır;
  bütün duvarı seed başına mavi/gri çevirmek yasaktır.
- Material randomization yalnız fiziksel olarak makul albedo,
  roughness, kir ve micro-normal aralığında yapılır. Hedef topoloji
  randomize edilmez.

## Beton

- Şekil dağılımı mevcut LED setinin gözlenen yaklaşık dağılımını izler:
  `cube=.42`, `cylinder=.58`.
- Küp fallback `180 × 180 × 180 mm`; silindir fallback `Ø126 × 201 mm`.
  Numuneler düzenli kalıp geometrisidir; her seed kırık kaya veya yamuk
  blob üretmez.
- Ana yüzey çok ölçeklidir: sparse pinhole/pore, açık mortar, az sayıda
  daha koyu aggregate, renk ve roughness heterojenliği birlikte gerekir.
- Scan gelene kadar dünya ölçeği fallback’i: pore `0.5–4 mm`,
  aggregate/mortar `2–12 mm`, edge chip/spall `3–20 mm`.
- Küp kenarları küçük bevel ve bounded chip taşır. Yüzeye yapıştırılmış
  boncuk gibi okunan iri aggregate geometri kullanılmaz. Cylinder side mould
  face ile uç yüzü ayrılmalıdır. Hasar silhouette’i ve bbox’u kontrolsüz
  bozmaz.
- Nem yalnız bounded albedo/roughness değişimidir; vernik veya ıslak
  plastik görünümü üretmez.
- Üst tabla altında yük alan üst bant, gövde ortasıyla zorunlu olarak
  aynı okunmaz. Fresh LED/IR'de görülen küçük ochre/koyu artık ve pitting
  bağımsız `top-load-weathering-v1` RNG'siyle, çoğunlukla gömülü ve
  numune siluetini büyütmeden kapsanır. Rejim-bağımlı count, profil ve
  belirsizlik metadata/validator sözleşmesidir. Bu procedural yama,
  ölçülmüş contamination prevalence, yönlü yük izi veya BRDF değildir;
  ölçekli/polarize crop ya da scan geldiğinde texture/decal/geometry ile
  değiştirilmelidir.
- En iyi sonraki kaynak lisanslı scan/photogrammetry, ölçülü normal/
  roughness crop ve ayrı kalıp/uç-yüz atlasıdır. Procedural beton geçici
  fallback’tir.

## Basılı kâğıt ve görsel RFID

- Kâğıt beton üzerine yapışan, kirli/kullanılmış basılı formdur; target
  sınıfı değildir ve semantic/pass index verilmez.
- Mevcut planar kâğıt yalnız küp yüzünde güvenlidir. Silindir için
  segmented/conformed mesh kalibre edilene kadar kâğıt üretmek yerine
  senaryoyu atlamak tercih edilir.
- Kâğıt RFID’den kameraya daha yakın gerçek geometri olmalıdır. Tag
  kısmen görünüyorsa yalnız görünür film pikselinden tight instance bbox
  çıkar; tamamen gizliyse YOLO satırı yoktur.
- Kısmi görünür uç hedef aralığı config’te `0.15–0.50`’dir. Bu oran
  doğrudan bbox eşiği değildir; render sonrası görünür maske yine policy
  gate’inden geçer.
- Nominal RFID yaklaşık `60 × 10 × 0.09 mm`; ince amber/copper film,
  rounded epoxy IC, trace/notch ve çok hafif edge lift taşır. Kalın neon
  kırmızı kart veya havada yüzen etiket olmaz.
- Sample face/side, loose plate surface ve upper/lower plate gap
  yerleşimleri desteklenir. Bir film iki parçaya occlude olsa bile tek
  fiziksel instance’tır; largest-component/visibility policy onu
  standard, hard veya exclude’a yönlendirir.

## Kamera, fisheye ve görüntü zinciri

- `camera_angled = Kamera 01 / cam-10`; chamber’a daha doğrudan bakar.
- `camera_door = Kamera 02 / cam-11`; sol kapı açıklığı/workshop’u daha
  fazla görür.
- Kaynak 1920×1080 küçük CCTV sensörüdür. Güncel generator her kamera için ayrı,
  seed’li ama dar lens, position, target, roll, focus, distortion,
  chromatic dispersion ve exposure aralığı yazar.
- Bu model gerçek fisheye kalibrasyonu değildir: Blender perspective
  camera + compositor radial distortion yaklaşımıdır. Metadata bunu
  açıkça `not calibrated fisheye` olarak taşır.
- RGB ile semantic/instance maskeler aynı geometric lens warp’ını
  paylaşır. Noise, sharpen veya bloom hiçbir zaman maskeye uygulanmaz.
- Güncel config’te `vignette.enabled=false`,
  `sensor_sharpen.enabled=false` ve `highlight_bloom.enabled=false`.
  Bu efektler yalnız gerçek kameradan ölçülmüş profil gelirse açılır;
  “daha sinematik” görüntü için açılmaz.
- Timestamp/`Kamera 01/02` overlay sentetiğe bake edilmez.

## Bounded randomization sözleşmesi

Seed ile değişebilir:

- kapı açısı seçili profile içinde;
- cube/cylinder, küçük pozisyon/yaw, bounded hasar/nem;
- RFID sayısı, fiziksel placement ve paper ilişkisi;
- LED profili/enerjisi/door fill;
- kamera mount jitter, lens, distortion, focus, roll ve exposure;
- micro dirt, scratch ve concrete yüzey seed’i.

Bağımsız detection still profili, gerçek LED bbox medyanını bozulmamış
küp ölçüsüyle yakalamak için küp yaw’ını kameraya koşullar:
`camera_angled=-42…-28°`, `camera_door=-35…20°`. Bu yalnız **unpaired**
stiller içindir. Senkron iki-kamera üretiminde tek numune için bir yaw
çekilir ve aynı fiziksel sahne iki kameradan render edilir; kamera başına
numune pozu değiştirilmez.

Seed ile değişmez:

- hedef REF-65218 panel renk haritası;
- chamber ve access-door topolojisi;
- tabla ekseni/çap sözleşmesi;
- üç segment LED’in duvar güzergâhı;
- kamera kimliği ve sınıf id’leri;
- görünür-maskeden bbox ve partition policy.

Ölçülmemiş bir değişken için dağılım konabilir; fakat aralık fiziksel
olarak açıklanmalı, metadata’ya yazılmalı ve gerçek veri histogramı
geldiğinde daraltılmalıdır.

## Kabul kapıları

1. Fresh source/config SHA ile scene contract ve validator PASS.
2. Dört sabit seed’de iki kamera × cube/cylinder, kapı ve üst/alt temas
   görsel kontrolü.
3. Paper-under-tag, fully-hidden, disconnected visible tip, frame-edge
   ve multi-tag örneklerinde instance mask/YOLO/partition kontrolü.
4. 1280×720 pilot, ardından 1920×1080 production-candidate render.
5. 100-kare, iki kişilik QC: geometri, material, lighting, bbox ve
   partition ayrı puanlanır.
6. Güncel `.blend` üzerinde BlenderMCP scene-info + viewport + Cycles
   round-trip pinlenir.
7. Frozen gerçek test split’inde real-only, synthetic-only,
   real+synthetic-standard ve adlandırılmış hard-occlusion ablation.

Mevcut v5.1 32-kare düşük çözünürlüklü framing dağılım kapısı, `1280×720`
görsel pilotu, üç `1920×1080` hero ve güncel BlenderMCP turu ilk teknik
kapıları doğrular; 32-kare `1920×1080` production pilotu ve 100-kare iki
kişilik QC hâlâ gereklidir. İdeal sonuç; bu sözleşmeyi karşılayan
production render, güvenli annotation ve gerçek-test model sonucudur.
Bir contact sheet veya MCP turu tek başına fotogerçekçilik ya da model
faydası kanıtlamaz.
