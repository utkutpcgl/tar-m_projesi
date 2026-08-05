# Simulation lessons learned

Bu belge workstream’ler arasında devredilecek kararları ayırır. EBIS Blender ve Unreal-EBIS bölümleri gerçek render/label kanıtına dayanır. Blender-tren ve Unreal-tren bölümleri plan-temellidir; deneysel sonuç veya engine benchmark’ı değildir.

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
- [Pass raporu](MULTI_REPEAT_PASS_1_2026-07-29.md),
  [piksel audit'i](reports/qc/multi_repeat_pass1_pixel_audit.json) ve
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
- [Pass raporu](MULTI_REPEAT_PASS_2_2026-07-29.md),
  [piksel audit'i](reports/qc/multi_repeat_pass2_pixel_audit.json) ve
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
- [Pass raporu](MULTI_REPEAT_PASS_3_2026-07-30.md),
  [piksel audit'i](reports/qc/multi_repeat_pass3_pixel_audit.json) ve
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
- [Pass raporu](MULTI_REPEAT_PASS_4_2026-07-30.md),
  [piksel audit'i](reports/qc/multi_repeat_pass4_pixel_audit.json) ve
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
- [Pass raporu](MULTI_REPEAT_PASS_5_2026-07-30.md),
  [piksel audit'i](reports/qc/multi_repeat_pass5_pixel_audit.json) ve
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
