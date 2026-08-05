# EBIS Blender / Unreal güncel kıyası

## Karar

[`real_blender_unreal_comparison.png`](assets/real_blender_unreal_comparison.png)
gerçek LED, Blender V8 ve Unreal r59'un güncel sabit örneklerini yan yana
gösterir. Kareler aynı an/seed değildir; sheet bir ölçüm veya kör kullanıcı
çalışması değil, domain-gap QC girişidir.

Bugünkü actual-pixel incelemede iki motor da önceki clean/cellular concrete
uçlarından gerçek döküm yönüne ilerledi. Blender küçük gözenek ve ışık
geçişinde daha doğal; fakat gerçek numuneden fazla temiz ve geniş görüşlüdür.
Unreal'ın V24 hücresel/V25 mermerimsi tonu kalktı; r59 nötr V27 BRDF kullanır,
ancak geniş keskin ışık bantları ve daha sentetik planar shading açık farktır.
Unreal'ın Blender'dan daha gerçekçi olduğu veya iki motorun YOLO'yu
iyileştirdiği gösterilmedi.

## Kanonik artefaktlar

| Alan | Blender | Unreal 5.8.1 |
| --- | --- | --- |
| Sabit review | [`current_samples`](../../../ebis-blender/output/current_samples/contact_sheet.png) | [`current_samples`](../../output/current_samples/contact_sheet.png) |
| Kaynak release | `realism_v8_cast_pores_release_60100` | `realism_r59_neutral_cast_brdf_release_60160` |
| RGB | 12 × 1280×720, Cycles 64 spp | 16 × 1280×720, Lumen/HWRT |
| Kamera/şekil | 6+6 kamera; dört hücre mevcut | 8+8 kamera; 8+8 cube/cylinder |
| Annotation | 56 visible binary maske | 70 visible + 70 isolated-amodal |
| Validator | `PASS`, `errors=[]` | `ok=true`, `errors=[]`, `warnings=[]` |
| Beton | düşük-oranlı ambientCG + 79–141 küçük görünür pore | neutral constant cast BRDF V27 + 54–92 küçük pore |
| MCP | güncel V8 sahnesi BlenderMCP ile `163→163`, 1080p OptiX PASS | güncel r59 sahnesi Epic MCP ile 9-call PASS |

Unreal satırındaki depth kapalıdır; fisheye RGB warp ile eşleşmeyen depth
üretmek yerine fail-closed davranılmıştır. Güncel MCP tek-kare teknik turu
ayrıca EXR depth üretmiştir; bu, batch r59'a depth atfetmez.

## Kapanan farklar

- Küp ve silindirin nominal dikey kenarları düz; içbükey silhouette yok.
- Kapı sağ menteşeli dolu gri leaf olarak ön açıklıktan dışa açılır; sürgü
  rayı, cam leaf ve turuncu sabit makine objesi yoktur.
- Back/left/right sabit yüzeyler mavi tırtıklı hammertone; gri yalnız
  hareketli kapı/servis kapağı ile çıplak çelik parçalardadır.
- `Ø400 mm` iki tabla ve üst tabla hizasında back/left/right boyunca ince
  opal U-difüzör iki engine'de aynı fiziksel sözleşmeyi taşır.
- Unreal ilk-frame checker fallback'i aynı seed re-renderında giderilmiştir.

## Kalan en yüksek değerli farklar

1. Ölçülü boş-hazne foto seti ve kapı/tabla/chamber CAD'i yok.
2. Mavi boya, çelik tabla ve beton için gerçek yüzeyden color/normal/roughness
   scan'i yok; mevcut roughness/BRDF görsel-fit'tir. Unreal'da keskin geniş
   light bands, Blender'da aşırı temiz/aydınlık concrete ana materyal farkıdır.
3. Kamera intrinsics/distortion, fixed exposure response, white balance,
   temporal/video noise ve overlay ölçülmemiştir.
4. Eşlenik sheet'teki gerçek cylinder/cube üst-yük bölgesi sentetikten çok
   daha rough, kirli ve aggregate görünür; rejim prevalence'i gerçek korpusta
   sayılmalı, ağır örnekler tüm sentetiğe uygulanmamalıdır.
5. Eş senaryo 100-kare kör insan QC ve aynı frozen-real-test YOLO ablation'ı
   yapılmamıştır.

## Adil sonraki deney

1. Aynı ölçülü CAD/PBR ve aynı camera calibration iki engine'e verilir.
2. Aynı scenario tablosuyla eşit 100 `standard` kare üretilir.
3. İki kişi kör gerçekçilik/label QC yapar; uyuşmazlıklar raporlanır.
4. Aynı nano checkpoint/hyperparameter ve seed `17/29/43` ile `R`,
   `R+B-1N`, `R+U-1N`, gerekirse `R+B+U-1N` eğitilir.
5. Yalnız capture-safe gerçek test metriği, üretim süresi, disk/VRAM ve
   manuel düzeltme maliyeti birlikte karar verir.
