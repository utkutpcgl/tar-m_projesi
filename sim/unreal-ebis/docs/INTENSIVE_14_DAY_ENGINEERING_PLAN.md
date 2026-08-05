# Unreal-EBİS yoğun 14 günlük mühendislik ve YOLO planı

## Tek hedef

On dört gün sonunda şu soruyu ölç: aynı fiziksel CAD/PBR/kamera sözleşmesiyle düzeltilmiş Unreal-EBİS verisi, frozen gerçek testte en küçük YOLO modeline Blender’dan farklı veya ek bir değer sağlıyor mu?

Unreal r59 teknik annotation ve güncel görsel baseline’dır. Kapalı kutu,
sağ menteşeli dışa açılan dolu gri kapı, üç mavi sabit hammertone duvar,
üç-duvar U-difüzör ve tabla oranı artık kanonik sözleşmedir; fotogerçekçilik
ve model kazancı yine yalnız ayrı kanıtlarla kabul edilir.

## r59 / V27 devir zemini

Güncel teknik baseline `realism_r59_neutral_cast_brdf_release_60160`'tır:
16/16 validator `PASS`, dengeli iki kamera × iki shape, 70 visible + 70 amodal
instance maskesi, düşük-glare üst tabla, bounded spalled-cube gövdesi,
üst yük bölgesinde bounded ochre/koyu mikro-artık ve güncel resmî MCP
round-trip. V24 hücresel ve V25 mermerimsi albedo reddedilmiş; constant
neutral cast BRDF V27 + ölçekli küçük pore geometrisi canonical'dır. Bu baseline
depth için kamera-warp eşliği çözülemediğinde fail-closed davranır ve
fotogerçekçilik iddia etmez.

Blender V8 geri aktarımı üç önceliği kesinleştirir:

1. Çok parçalı prosedürel kırıklar CAD-benzeri kalabilir; aynı ölçekte
   taranmış düzenli/edge-worn/spalled küp ve silindir varyantları iki
   motorun ortak kaynak asset'i olmalıdır.
2. PBR ayarı yalnız scalar roughness değildir. Pebbled sac ve platen için
   gerçek mm texel scale, albedo/roughness/normal ayrımı ve cross-polarized
   capture gereklidir.
3. LED görünür emissive kapak ile gerçek aydınlatma katkısı ayrılmalı;
   lux/IES, grey-card ve empty-chamber exposure ölçülmeden “doğru ışık”
   denmez.

Procedural üst-yük lekesini daha fazla noise ile büyütmek öncelik
değildir. Ölçekli/polarize üst yüz yakın planı veya scan geldikten sonra
iki motorda aynı texture/decal/geometry kaynağı kullanılmalıdır.

## Değişmez sözleşme

- Sınıflar `0 rfid_tag`, `1 concrete_sample`; camera mapping değişmez.
- Kutunun sağ menteşeli, dolu gri, dışa açılan front door/frame’i vardır.
  Dar opal LED channel üst tabla seviyesinde yalnız back + left + right
  duvarı sarar; door opening boyunca ışıklı segment yoktur.
- Sabit back/left/right iç yüzeyler mavi ve mm ölçekli pebbled/girintilidir.
  Gri; hareketli kapı/servis kapağı, frame ve çıplak çelikle sınırlıdır.
  Sürgü rayı, glass leaf veya turuncu sabit hardware eklenmez.
- Üst/alt dairesel tablalar aynı eksende ve numuneye temaslıdır. Ölçü gelene kadar ortak karşılaştırma fallback çapı iki tabla için de `400 mm`, 18 cm küp kenarının `2.22×`ıdır.
- Her fiziksel target’ın multipart mesh’i aynı `EBIS_INSTANCE` tag’ini taşır.
- Visible/amodal/depth capture sırası ve annotation threshold’ları görsel iyileştirme uğruna değiştirilmez.
- Val/test yalnız gerçek; aynı checkpoint/environment/hyperparameter/seed seti.
- Train/val/test manifestleri, derived iki-sınıflı label inventory’si ve split-audit Day 1’de SHA-256 ile freeze edilir; test Day 13 toplu eval’a kadar sealed kalır.

## Kabul kapıları

| Kapı | Geçiş ölçütü | Fail davranışı |
| --- | --- | --- |
| U0 — kaynak | ölçü/CAD/PBR/camera/IES kaynağı, birimi, lisansı ve hash’i kayıtlı | fallback açıkça işaretlenir |
| U1 — geometri | iki kamera × iki sample clay grid owner PASS; U-LED ve kapı doğru; tabla temas/ratio PASS | PBR çalışması durur |
| U2 — render | debug pass’leri temiz, büyük clipping yok; kör owner ve operatör ayrı overall medyanları `≥3.0/5`, ortak geometri/materyal/ışık/kamera medyanlarının her biri `≥3.0/5`; açık blocker yok ve eski baseline’dan kötü değil | tek değişkenli bounded revizyon |
| U3 — annotation | 16-kare pilot validator PASS; RGB/depth/visible/amodal count ve uniqueness PASS | production yok |
| U4 — insan QC | 100 stratified kare iki kişi; standard görünür-unlabelled `0`; kritik bbox hata `0`; yüksek/orta toplam ≤ `%2` | generator düzeltilir |
| U5 — model | üç-seed frozen gerçek test GO eşiği | HOLD; 2N/10k yok |

## Compute disiplini

- UE 5.8.1/CL 56057345, driver 580.159.04 ve RTX 3090 pinleri değişirse yeni benchmark revizyonu açılır.
- MCP yalnız bounded build/validate/render kontrolüdür; büyük batch `run_remote_release.sh` ile yapılır.
- Blender render, Unreal render ve YOLO train aynı 3090’da eşzamanlı çalışmaz.
- Yeni calibration seed’leri `60220..60319`; kanonik `60160..60175`
  release seed’leri tekrar kullanılmaz. Model seed’leri `17/29/43`.
- Fresh run adı zorunlu; mevcut release overwrite edilmez.

## Gün 1 — baseline, install ve benchmark zemini

- UE/editor/plugin/config/generator ve mevcut v1 output hashlerini baseline manifestine al.
- Resmî MCP loopback start→describe→build→validate→render→stop smoke çalıştır; port dış bind etmez.
- Gerçek dataset capture-safe split ve iki-sınıflı derived label sözleşmesini Blender planıyla paylaş.
- Final `train.txt`, `val.txt`, `test.txt`; derived label göreli yol+dosya SHA inventory’si ve capture-group split audit JSON’u oluştur. Üç manifest, inventory ve audit SHA’larını tek `split_freeze.json` içinde Blender ile byte-identical pinle.
- `test_seal.json`; test manifest SHA’sı, `sealed_until_day=13`, izin verilen tek final-eval aşaması ve seal zamanını taşır. Day 13 öncesi test loader/test referansı hard fail; split değişikliği yeni experiment identity gerektirir.
- İzole Ultralytics environment/checkpoint SHA oluştur; ortak R 2-epoch ingest smoke.

Çıktı: baseline + MCP + environment manifestleri; hash’li train/val/test, derived-label inventory, split audit, `split_freeze.json` ve `test_seal.json`. Kapı: listener kapalı, split leakage yok, freeze hashleri yeniden eş ve test seal kapalı.

## Gün 2 — ortak fiziksel spec ve camera calibration

- [`ebis_physical_measurements_template.json`](../configs/ebis_physical_measurements_template.json) doldurulur.
- [`USER_SUPPORT_AND_REVIEW.md`](USER_SUPPORT_AND_REVIEW.md) içindeki board inner-corner satır/sütun, square mm, print scale, basılmış-square ölçümü ve source-file SHA alanlarını taşıyan `camera_calibration_target.json` freeze edilir.
- Blender ile aynı millimetre kaynak spec’i kullanılır; Unreal config’e santimetre dönüşümü otomatik/testli yapılır.
- Checkerboard intrinsics/distortion ve chamber landmark’ları çözülür; yoksa bbox visual fit proxy olarak kalır.
- CAD ekseni/pivotu: Z-up, sample/platen ortak merkez ve kapı hinge pivotu tanımlanır.

Çıktı: shared measurement hash, camera calibration ve coordinate diagram. Kapı: mm→cm ve iki engine bounding box eşliği.

## Gün 3 — box press, kapı ve tabla geometrisi v2

- Chamber gerçek kapalı kutu hacmine çevrilir; door opening/frame/leaf ve dış workshop görüşü ayrı mesh olur.
- Back/left/right pebbled sac paneller, floor/roof, servis kapağı/conta/dört vida eklenir.
- Üst/alt tablalar ölçülü radius/thickness/bevel ve ram bağlantısıyla yeniden kurulur.
- Sample iki tablaya temas eder; overlap/gap validatorı ve debug marker eklenir.
- LED channel ve opal cover üç ayrı segmenttir; büyük beyaz panel proxy kaldırılır.
- Unlit/clay 2×2 camera×shape render alınır.

Çıktı: v2 map/generated asset ve clay contact sheet. Owner checkpoint A. Kapı: U1 PASS.

## Gün 4 — ortak CAD import ve asset bütünlüğü

- CAD varsa Datasmith/FBX/glTF import yolu test edilir; scale, normals, tangent, smoothing ve UV audit edilir.
- Aynı source mesh’in Blender/Unreal bounding dimensions ve SHA/asset provenance tablosu çıkarılır.
- Gereksiz tessellation temizlenir; Nanite yalnız silhouette veya dense scan için açılır.
- Instance target meshleri import sonrası `EBIS_INSTANCE` kimliğini kaybetmez; decorative meshler target olmaz.

Çıktı: import manifesti ve cross-engine dimension test. Kapı: silhouette ve target identity PASS.

## Gün 5 — PBR materyal v2

- Pebbled painted sheet: gerçek texel scale, normal/roughness, micro-scratch/dust; mavi renk yalnız lokal referans panelinde.
- Upper/lower used steel: radial machining, scratch/grease/cement contamination, bounded metallic/roughness.
- Concrete: mould face, aggregate/pore ve broken edge ayrı scale katmanları; TAA shimmer yapmayacak yoğunluk.
- RFID: film/copper/chip/adhesive ve bounded edge lift; tiny renderda okunabilir ama neon görünmez.
- BaseColor/Roughness/Normal debug renderları alınır; texture sRGB/channel import ayarları otomatik audit edilir.

Çıktı: material instances, provenance ve texel-scale raporu. Owner checkpoint B.

## Gün 6 — fiziksel U-LED, exposure ve Lumen

- Opal diffuser emissive görünümü ile gerçek rect/area light contribution ayrılır.
- Back/left/right segmentler ayrı kontrol edilir fakat aynı fixture profile’a bağlanır.
- CCT/lumen fallback’leri gerçek lux/IES gelince fiziksel profile çevrilir.
- Manual exposure gerçek no-person reference percentile’ına kalibre edilir; auto exposure production’da kapalı/pinli kalır.
- Lumen HWRT, reflection, shadow bias ve emissive leak debug edilir. Diffuser clip olabilir; tabla/beton geniş alanı clip olamaz.
- LED neutral/cool/door-daylight/warm-dirty fixed seed grid’i üretilir.

Çıktı: light profile manifesti ve clipping raporu. Owner checkpoint C’nin ışık bölümü.

## Gün 7 — lens, SceneCapture ve sensor görünümü

- Camera FOV/transform calibration’a bağlanır; distortion gerekiyorsa RGB ve masks aynı mapping’i paylaşır.
- SceneCapture ile editor viewport/MRQ farkı ölçülür; production yolu teklenir.
- Camera noise, sharpening, white-balance ve compression gerçek sensor ölçüsüne dar randomization olarak eklenir; label maskelerine uygulanmaz.
- TSR ghosting/shimmer RFID tiny edges ve pebbled normal üzerinde test edilir.
- Camera×shape concrete bbox medyanları `±0.06` mevcut gate, hedef olarak `±0.03` içinde tutulur.

Çıktı: camera/sensor calibration grid. Kapı: RGB-mask registration ve depth PASS.

## Gün 8 — RFID placement ve occlusion stres testi

- Front/side/loose/top-gap/bottom-gap oranları gerçek dağılıma göre güncellenir.
- Plate-gap tag fiziksel olarak iki yüzey arasında, kısmen görünen ama penetrasyonsuz yerleşir.
- Standard/hard/below-hard/fully-occluded/outside örnekleri deterministic test seed’leriyle üretilir.
- GPU readback fence ve synchronous mask material compile editör restart sonrası yeniden test edilir.
- Connected component, visibility, edge clipping ve worst-instance partition insan review ile doğrulanır.

Çıktı: occlusion unit matrix ve validator log. Kapı: visible-unlabelled standard sızıntısı yok.

## Gün 9 — 16-kare realism pilotu ve MCP doğrulaması

- İki kamera × iki shape × dört light profili fresh `realism_v2_pilot` run’ında üretilir.
- RGB/depth/visible/amodal count, uniqueness, camera/shape coverage ve bbox gate validatorla kontrol edilir.
- Aynı scene generator resmî MCP üzerinden bir 1080p hero render üretir; loopback transcript alınır ve server durdurulur.
- Gerçek/old Blender/new Blender/old Unreal/new Unreal karşılaştırması hazırlanır.

Çıktı: pilot, MCP transcript, contact sheet. Kapı: U2–U3 PASS.

## Gün 10 — kör review ve bounded düzeltme

- Engine isimleri kapalı grid owner + EBİS operatörüne verilir.
- Geometri, material, light, camera ve overall 1–5 puanlanır; [`USER_SUPPORT_AND_REVIEW.md`](USER_SUPPORT_AND_REVIEW.md) formatı kullanılır.
- Ortak blocker/yüksek en fazla üç sorun düzeltilir. Engine’e özel süs için shared CAD/PBR sözleşmesi bozulmaz.
- Dört fixed seed yeni hash’le tekrar edilir; önceki pilot korunur.

Generator/config/map/material hash’i değişirse Gün 9’daki ayrı 16-kare U3 pilotu da fresh adla yeniden üretilip validator PASS alır; yalnız dört fixed seed yeni annotation release kanıtı sayılmaz.

Çıktı: blind review, reviewer-bazlı medyanlar ve bounded revision log. Kapı: owner ve operatör ayrı overall medyanları `≥3.0/5`, dört ortak alt-eksen medyanı `≥3.0/5`, yeni Unreal eski Unreal’dan kötü değil, açık blocker yok ve revizyon sonrası U3 PASS güncel.

## Gün 11 — 100-kare insan QC ve production freeze

- Camera×shape×light×tag-count×placement stratified 100 kare fresh run.
- İki bağımsız reviewer bbox/visible/amodal ve rendering artefaktlarını işaretler.
- Standard kritik hata varsa generator düzeltilir ve fresh 100 kare tekrar edilir.
- PASS olduğunda config/generator/map/material/plugin hashes production revision olarak freeze edilir.

Çıktı: 100-kare QC, reviewer agreement, production manifest. Kapı: U4 PASS.

## Gün 12 — eşit-N üretim ve nano eğitim

- `N=min(1000, uygun gerçek train sayısı)` kadar yalnız PASS standard Unreal görüntüsü stratified seçilir.
- `R+U-1N` seed `17/29/43`, `yolo11n.pt`, `imgsz=960`, 60 epoch, patience 12 ile eğitilir.
- Ortak `R` ve `R+B-1N` runları aynı environment/checkpoint/real manifestle kullanılır veya eksikse sırayla çalıştırılır.
- Test kapalı; val yalnız gerçek. Render ve train GPU zamanları ayrı raporlanır.

Çıktı: U1N manifest ve üç run; ortak benchmark registry.

## Gün 13 — frozen gerçek-test, slice ve maliyet

- Eval öncesi `split_freeze.json`, derived-label inventory ve üç manifest SHA yeniden doğrulanır. `test_seal.json` yalnız kayıtlı Day-13 toplu eval komutu için açılır; UTC zaman, operator, checkpoint listesi ve gerekçe append-only unseal kaydına yazılır.
- R, R+B-1N, R+U-1N best checkpoint’leri tek toplu gerçek-test eval ile açılır.
- RFID/concrete AP50-95, AP50, precision, recall; camera, shape, person, tag-size, plate-gap slice’ları çıkarılır.
- Üç seed median/IQR, train süresi, peak VRAM, render s/kare, disk ve manuel QC dakika/kare raporlanır.
- En az 50 FP + 50 FN geometry/material/light/hand/tiny/glare/background bucket’larına ayrılır.

Çıktı: engine-adil model ve maliyet tablosu.

## Gün 14 — GO/HOLD ve devir

- Unreal GO: R’ye karşı RFID AP50-95 median `≥+2.0`, 2/3 seed pozitif, recall gerilemez, concrete kaybı `≤1.0`, iki kamera yönü negatif değil.
- Blender’a ek değer `R+U-1N - R+B-1N` olarak ve güven aralığı/maliyetle raporlanır; tek seed kazanç sayılmaz.
- GO ise U2N yalnız doz ablation olarak planlanır. HOLD ise 10k üretim durur; baskın gap için ölçü/CAD/PBR/sensor işi seçilir.
- README/handoff/lessons learned/release hashes ve 3090 mirror güncellenir; MCP kapalı teslim edilir.

Çıktı: GO/HOLD raporu, release manifest, sonraki sprint için en fazla üç öncelik.

## Zorunlu model matrisi

| Koşul | Train | Seed | Karar rolü |
| --- | --- | --- | --- |
| `R` | N gerçek | 17/29/43 | ortak baseline |
| `R_B1N` | aynı N gerçek + N Blender standard | 17/29/43 | mevcut sentetik kıyas |
| `R_U1N` | aynı N gerçek + N Unreal standard | 17/29/43 | Unreal ana katkı |
| `R_U2N` | aynı N gerçek + 2N Unreal | 17/29/43 | yalnız U1N GO ise doz |
| `U_only` | N Unreal | tek seed opsiyonel | ingest sanity; başarı değil |

Hard ana matrise girmez; ana sonuç pozitifse açık isimli ayrı ablation olur. Exclude hiçbir train/val/test manifestine girmez.

## İki hafta sonunda zorunlu artefaktlar

- ölçü/calibration ve fallback listesi;
- kaynak/lisans/hashli ortak CAD/PBR/IES varlıkları;
- hash’li train/val/test manifestleri, derived-label inventory, split-audit, `split_freeze.json` ve Day-13 unseal kaydı;
- v2 config/generator/map/material hashes;
- 16-kare pilot + MCP render + validator PASS;
- iki kişilik 100-kare QC;
- frozen U1N ve ortak real manifest;
- üç-seed R/R+B1N/R+U1N sonuçları, slice ve maliyet;
- dürüst GO/HOLD kararı.

Bu artefaktlar olmadan “Unreal daha gerçekçi” veya “YOLO’yu iyileştirdi” iddiası yazılmaz.
