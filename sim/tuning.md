Sorularım: Gerçek fotoğraftan texture ve materyal transferi nasıl yapabilirim simlulasion engine'e?

Tamamen LLM kontrolünde gerçekçiliği arttırabilir miyim böylece otomatik müdahale etmeden, öyle bir iyileştirme yaklaşımına ihtiyacım var sanki. Tonlarca veri var elimde ledli ve infrared, iterative bir iyileştirme yapabilse bunlara bakarak epey yol katedilir aslında tahminim. Unreal mi mcp mi daha iyi blender mcp mi daha iyi bu yöntemle gerçekçiliği arttırmak için. 

Doğrusu unreal mcp ile de güzel bir noktaya gelebildi gibi. iki yaklaşım ile de elimde dataset olduğu durumda gerçekçiliği iterative mükemmel hale nasıl getirebilirim? Özellikle materyal texture, yansıtması, deformasyonu, yüzeyi vs. gibi özellilkeri (gerçek foto ile simulasyonu ayırt edilemez hale getirecek olan).






## Net cevap

Senin projelerinde en doğru hat şu:

```text
Gerçek fotoğraf
→ perspektif / renk / ışık düzeltme
→ PBR texture seti üretme
→ Blender/Unreal master material
→ fiziksel ölçek ayarı
→ kontrollü materyal varyasyonları
→ gerçek fotoğrafla render karşılaştırması
```

Buradaki temel darboğaz **fotoğrafı engine’e aktarmak değil, fotoğrafa gömülü ışık ve gölgeleri gerçek yüzey özelliğinden ayırmak**. Tek fotoğraf doğrudan `Base Color` olarak kullanılırsa fotoğraftaki gölgeyi Blender veya Unreal yeniden aydınlatır ve yüzey sahte görünür.

---

# 1. Önce neyi transfer ettiğini ayır

| Gerçek unsur                            | Doğru yöntem                                      |
| --------------------------------------- | ------------------------------------------------- |
| Toprak, beton, pas, taş yüzeyi, travers | Fotoğraftan tileable PBR materyal                 |
| RFID etiketi, logo, yazı, çatlak        | Decal veya alpha’lı texture                       |
| Taş, beton numunesi, makine parçası     | Photogrammetry veya CAD mesh + texture projection |
| Bitki yaprağı                           | Alpha’lı yaprak atlası + gerçek 3D geometri       |
| Tüm makine veya tren hattı              | Çok açılı photogrammetry / CAD rekonstrüksiyonu   |
| Ortam aydınlatması                      | HDRI / panorama çekimi                            |

Yani **materyal transferi geometri transferi değildir**. Düz veya tekrarlayan yüzeylerde texture yeterlidir; silueti, gölgeyi veya temas noktasını değiştiren ayrıntıların geometri olması gerekir.

---

# 2. En hızlı ve kaliteli yöntem: Substance 3D Sampler

Pratik başlangıç için:

```text
Fotoğraf
→ Substance 3D Sampler
→ Image to Material
→ PBR map düzeltmeleri
→ Blender / Unreal export
```

Substance 3D Sampler’ın güncel `Image to Material` aracı tek fotoğraftan Base Color, Normal, Height ve Roughness üretirken fotoğraftaki gölge ve parlaklıkları albedodan ayırmaya çalışıyor. AI yöntemi iyi bilinen yüzeylerde daha başarılı; B2M yöntemi daha geniş materyal çeşitlerinde çalışıyor fakat daha yaklaşık sonuç veriyor. ([Experience League][1])

Çıkarman gereken temel dosyalar:

```text
soil_01_basecolor.png
soil_01_normal.png
soil_01_roughness.png
soil_01_height.exr
soil_01_ao.png
soil_01_metallic.png       # yalnızca gerçekten metal bölgeler varsa
```

Ancak bunları “ground truth fiziksel ölçüm” olarak görme. Özellikle **roughness ve height tek fotoğraftan kesin olarak belirlenemez**; araç makul bir tahmin üretir. Görsel doğrulama gerekir.

Ücretsiz tarafta Material Maker; albedo, metallic, roughness, normal ve depth kanalları bulunan PBR materyalleri grafik tabanlı biçimde üretip oyun motorlarına aktarabiliyor. Fakat tek fotoğraftan otomatik ve temiz materyal çıkarma konusunda Substance Sampler kadar doğrudan değildir. ([Material Maker][2])

---

# 3. Fotoğrafı doğru çekmek çıktının yarısıdır

## Düz yüzey çekimi

Toprak, beton, paslı çelik veya travers için:

1. Kamerayı yüzeye mümkün olduğunca dik tut.
2. Geniş ve yumuşak ışık kullan.
3. Sert güneş, keskin gölge ve yansıma olmasın.
4. Kadraja bir cetvel veya bilinen ölçülü referans koy.
5. Mümkünse gri kart veya ColorChecker kullan.
6. RAW çek.
7. Tek kare yerine aynı yüzeyden birkaç komşu alan çek.
8. Yüksek çözünürlükte, motion blur olmadan çek.

İdeal koşul kapalı hava veya büyük softbox ışığıdır. Değişken gölge, glare ve yansıma hem photogrammetry eşleşmesini hem de texture görünümünü bozar; mat ve detaylı yüzeyler parlak veya saydam yüzeylerden daha kolay taranır. ([Epic Games Developers][3])

### Daha profesyonel çekim

Yansımalı malzemelerde **cross-polarization** çok faydalıdır:

```text
Işıkların önünde polarize film
+
Kamera lensinde döndürülebilir polarize filtre
```

Filtreyi bir konumda çekerek daha çok diffuse/albedo bilgisi, diğer konumda daha çok specular tepki toplayabilirsin. Özellikle:

* boyalı metal,
* yağlı makine yüzeyi,
* ıslak toprak,
* cilalı beton,
* plastik RFID etiketi

için ciddi fark yaratır.

---

# 4. Fotoğrafı PBR’ye hazırlama

## A. Perspektifi düzelt

Fotoğraf yüzeye tam dik değilse önce planar rectification uygula. Kare biçimli gerçek bir referansı kare olacak şekilde düzelt.

## B. Işığı kaldır: de-light

`Base Color` içinde şunlar bulunmamalı:

* yönlü gölge,
* güneş parlaması,
* specular highlight,
* ambient occlusion,
* koyu köşe vignette’i.

Bunlar materyale gömülü kalırsa engine’in ışığıyla iki kez uygulanır.

## C. Seamless yap

Düz yüzey materyali için kenarların tekrar edebilmesi gerekir:

```text
offset texture by 50%
→ orta kısımda oluşan dikişi temizle
→ tekrar test et
```

Tekrar deseninin görünmemesi için yalnızca tek texture kullanmak yerine:

* macro variation,
* ikinci ölçekli noise,
* random rotation,
* texture bombing,
* stochastic tiling

uygulamak daha doğrudur.

## D. Gerçek ölçeği kaydet

Örneğin fotoğrafın kapsadığı alan:

```json
{
  "material_id": "soil_dry_01",
  "physical_width_m": 0.80,
  "physical_height_m": 0.80,
  "capture_condition": "overcast",
  "moisture_class": "dry",
  "source": "ankaref_field_session_03"
}
```

Bu bilgi olmazsa aynı taş veya toprak tanesi sahnede bazen 2 cm, bazen 20 cm görünür. Synthetic data açısından bu ciddi domain-gap üretir.

---

# 5. Blender’a aktarım

Temel node bağlantısı:

```text
Base Color [sRGB]
    → Principled BSDF / Base Color

Roughness [Non-Color]
    → Principled BSDF / Roughness

Metallic [Non-Color]
    → Principled BSDF / Metallic

Normal [Non-Color]
    → Normal Map
    → Principled BSDF / Normal

Height [Non-Color]
    → Bump veya Displacement
```

Blender’da tangent-space normal texture’ın `Non-Color` olarak ayarlanması ve doğru UV koordinatlarıyla kullanılması gerekir. Gerçek displacement ise `Displacement` düğümü üzerinden Material Output’a bağlanabilir. ([Blender Docs][4])

### Yüzey ayrıntısı seviyesi

| Ayrıntı                        | Kullan                            |
| ------------------------------ | --------------------------------- |
| Çok küçük çizik, pütür         | Normal map                        |
| İnce yüzey kabartısı           | Bump                              |
| Taş, derin çatlak, ray balastı | Gerçek geometri veya displacement |
| Silueti değiştiren unsur       | Kesinlikle geometri               |

Synthetic dataset için önemli kural:

> Kamera açısından silueti, occlusion’ı, gölgeyi veya depth ground truth’u değiştirecek ayrıntıyı yalnızca normal map ile temsil etme.

Normal map görüntüde kabartı izlenimi verir ama gerçek depth, geometri ve temas gölgesi üretmez.

### Procedural yüzeylerde

Toprak, beton veya metal panel gibi yüzeylerde doğrudan UV yerine bazen **triplanar mapping** daha kolaydır. Böylece mesh UV’si kötü olsa bile texture üç eksenden yansıtılır. Fakat RFID etiketi, yazı veya belirli çatlak gibi konum bağımlı ayrıntılar UV/decal üzerinden verilmelidir.

---

# 6. Unreal Engine’e aktarım

Unreal Content Browser’a PNG, TIFF, EXR ve diğer desteklenen texture formatlarını sürükleyerek aktarabilirsin. Texture’lar materyal içinde Base Color, Normal, Roughness, Metallic ve Ambient Occlusion girişlerine bağlanır. ([Epic Games Developers][5])

Önerilen import ayarları:

| Map        |                        sRGB | Not                    |
| ---------- | --------------------------: | ---------------------- |
| Base Color |                        Açık | Renk verisi            |
| Normal     | Kapalı / Normal compression | Normal map olarak tanı |
| Roughness  |                      Kapalı | Sayısal veri           |
| Metallic   |                      Kapalı | Sayısal veri           |
| AO         |                      Kapalı | Sayısal veri           |
| Height     |                      Kapalı | Sayısal veri           |

Performans için AO, Roughness ve Metallic gibi gri tonlu haritalar tek bir RGB texture’ın kanallarına paketlenebilir. Unreal’ın resmi dokümantasyonu da materyal maskelerinin kanal paketlemesiyle tek texture üzerinden kullanılabileceğini belirtiyor. ([Epic Games Developers][6])

Örneğin:

```text
R = Ambient Occlusion
G = Roughness
B = Metallic
```

Bu sıralama zorunlu standart değildir; master material ile tutarlı olman yeterlidir.

## Normal map yönü

Blender/OpenGL hattından gelen normal map Unreal’da ters kabarıyor veya çukur görünüyorsa yeşil kanal yönü uyuşmuyor olabilir. Unreal Texture Asset Editor içinde `Flip Green Channel` seçeneği bulunuyor. ([Epic Games Developers][7])

---

# 7. Master Material kur

Her texture için sıfırdan yeni materyal oluşturma. Bir master material oluştur:

```text
M_RealSurface_Master
├── BaseColor texture
├── Normal texture
├── Packed ARM texture
├── Height texture
├── UV scale
├── UV rotation
├── BaseColor tint
├── Roughness multiplier
├── Normal strength
├── Height strength
├── Wetness
├── Dirt amount
└── Macro variation
```

Sonra Material Instance üret:

```text
MI_Soil_Dry_01
MI_Soil_Damp_01
MI_Soil_Wet_01
MI_Concrete_Clean_01
MI_Concrete_Dusty_01
MI_Rail_Rust_Light
MI_Rail_Rust_Heavy
```

Bu yaklaşım synthetic data generator’a çok uygundur. MCP veya Python scripti yalnızca parametreleri ve texture setini değiştirir; shader graph sabit kalır.

---

# 8. Tam objeyi aktarmak için photogrammetry

Bir taş, beton numunesi, makine parçası veya travers parçasının geometrisini de almak istiyorsan tek fotoğraf yerine:

```text
50–300 örtüşen fotoğraf
→ RealityCapture / RealityScan
→ yüksek çözünürlüklü mesh
→ temizleme
→ retopology / decimation
→ UV unwrap
→ texture bake
→ Blender / Unreal
```

Photogrammetry’de renkli, mat ve ayırt edici ayrıntıları bulunan yüzeyler daha iyi eşleşir; düz renkli, parlak, saydam ve yansıtıcı nesneler daha problemli olur. Epic’in önerileri arasında tutarlı yumuşak ışık ve gerektiğinde scanning spray kullanımı bulunuyor. ([Epic Games Developers][3])

Unreal tarafında RealityCapture’dan Unreal’a uzanan resmi photogrammetry iş akışları mevcut. ([Epic Games Developers][8])

### Photogrammetry sonrası doğrudan kullanma

Ham tarama genellikle:

* gereğinden fazla polygon,
* kötü topoloji,
* düzensiz UV,
* taramaya gömülmüş ışık,
* delikler,
* gereksiz arka plan geometrisi

içerir.

Doğru üretim hattı:

```text
High-poly scan
→ clean high-poly
→ low-poly / Nanite uygun mesh
→ temiz UV
→ albedo/normal/AO bake
→ fiziksel scale doğrulama
```

---

# 9. Senin üç kullanım alanına özel öneri

## EBİS beton kırma makinesi

En doğru ayrım:

* **Makine gövdesi:** CAD veya temiz modellenmiş mesh.
* **Boyalı metal/pas/kir:** fotoğraftan PBR materyal.
* **Beton numunesi:** photogrammetry ile birkaç gerçek örnek.
* **Beton kırıkları:** scan edilmiş 10–20 parça + random scale/rotation.
* **RFID tag:** ayrı ince mesh veya decal.
* **Yağ, toz, çizik:** shader layer/decal.

RFID etiketi makinenin base texture’ına gömülmemeli. Ayrı actor/mesh olması sayesinde:

* konumu,
* yönü,
* kirlenmesi,
* deformasyonu,
* occlusion’ı,
* boyutu,
* görünürlük oranı

kontrollü randomize edilebilir. Ayrıca detection ground truth doğrudan bu objeden çıkarılır.

## Tren hattı

* Ray geometrisi: parametrik/CAD.
* Paslı çelik: photo-derived PBR.
* Travers: scan veya ölçülü mesh + PBR.
* Balast taşları: photogrammetry taş kütüphanesi.
* İnce uzaktaki taş yüzeyi: tileable texture.
* Yakındaki büyük taşlar: gerçek mesh.
* Yağ ve su birikmesi: wetness/decal layer.
* Ray kusurları: displacement değil, gerektiğinde gerçek geometri.

## Tarım

* Toprak: 10–20 farklı gerçek PBR scan.
* Islaklık: ayrı wetness parametresi; yalnızca texture’ı karartma.
* Taş ve bitki artığı: photogrammetry objeleri.
* Yaprak: fotoğraftan alpha atlası + modellenmiş yaprak mesh’i.
* Bitkinin büyüme formu: texture ile değil, ayrı büyüme geometrileriyle.
* Çamur, puddle, iz: geometry + shader karışımı.

Burada tek “gerçek toprak fotoğrafını” tüm sahneye döşemek yerine, aynı tarladan birkaç fiziksel materyal sınıfı toplamak daha değerlidir:

```text
dry_loose
dry_compacted
damp
wet
muddy
stony
organic_debris
```

---

# 10. Synthetic data açısından doğrulama

Materyali yalnızca “güzel görünüyor” diye kabul etme. Aynı kamera parametreleriyle:

```text
Gerçek fotoğraf
vs.
Simülasyon renderı
```

karşılaştır.

Kontrol et:

* renk dağılımı,
* parlaklık dağılımı,
* lokal kontrast,
* edge yoğunluğu,
* roughness tepkisi,
* gölge sertliği,
* doku fiziksel ölçeği,
* tekrar paterni,
* farklı ışık açılarındaki davranış.

En faydalı test, materyali **en az üç nötr ışık koşulunda** görmek:

```text
diffuse overcast
low-angle sunlight
soft indoor light
```

Fotoğraftaki tek ışık koşulunda iyi görünen ama diğer ışıklarda bozulan materyal, gerçek bir PBR materyal değil; fotoğraf görünümünün taklididir.

---

# Sana önerdiğim en sade üretim hattı

```text
1. Gerçek yüzeyi ölçek referansıyla çek
2. Substance Sampler ile PBR set çıkar
3. Albedo’dan gölge/parlamayı temizle
4. Gerçek texture boyutunu metadata’ya yaz
5. Blender master material’a otomatik bağla
6. Nötr ışık altında gerçek fotoğrafla karşılaştır
7. Kabul edilen materyali asset library’ye ekle
8. MCP/Python ile varyasyonlarını üret
9. Label/depth açısından geometri olması gereken detayları ayır
```

Senin ekip için ilk PoC’de **3 toprak + 2 beton + 2 metal/pas + 1 RFID decal** üretmek yeterli olur. Önce bu küçük kütüphanenin gerçek fotoğrafa yaklaşıp yaklaşmadığını ölçmek, yüzlerce materyal toplamaktan daha yüksek ROI sağlar.

[1]: https://experienceleague.adobe.com/en/docs/substance-3d-sampler/using/filters/tools/image-to-material?utm_source=chatgpt.com "Image To Material | Adobe Substance 3D Sampler"
[2]: https://www.materialmaker.org/?utm_source=chatgpt.com "Material Maker"
[3]: https://dev.epicgames.com/documentation/realityscan-mobile/photogrammetry-objects-and-backgrounds?utm_source=chatgpt.com "Photogrammetry Objects and Backgrounds | Realityscan ..."
[4]: https://docs.blender.org/manual/en/latest/render/shader_nodes/displacement/normal_map.html?utm_source=chatgpt.com "Normal Map Node - Blender 5.2 LTS Manual"
[5]: https://dev.epicgames.com/documentation/unreal-engine/textures-in-unreal-engine?utm_source=chatgpt.com "Textures in Unreal Engine"
[6]: https://dev.epicgames.com/documentation/unreal-engine/using-materials-and-textures-in-unreal-engine-for-maya-users?utm_source=chatgpt.com "Using Materials and Textures in Unreal Engine for Maya ..."
[7]: https://dev.epicgames.com/documentation/unreal-engine/texture-asset-editor-in-unreal-engine?utm_source=chatgpt.com "Texture Asset Editor in Unreal Engine"
[8]: https://dev.epicgames.com/community/learning/tutorials/W4MR/realityscan-realitycapture-to-unreal-engine-beginner-s-guide-to-photogrammetry-workflow?utm_source=chatgpt.com "RealityCapture to Unreal Engine: Beginner's Guide ..."















Evet, teşhisin doğru. **GPT’nin ana zayıflığı görüntüye hiç bakamaması değil; tek bir screenshot’tan “fiziksel olarak ne kadar gerçekçi?” sorusuna güvenilir mutlak cevap verememesi.** Üstelik yaptığı değişikliğin açıklamasını da görüyorsa, görsel kanıttan ziyade mantıklı anlatıya ikna olabiliyor. OpenAI de görsel modellerde temel algı hataları ve denemeler arası güvenilirlik farkları bulunduğunu belirtiyor; güncel araştırmalar MLLM hâkimlerinin bazen görsel kanıt yerine makul görünen açıklamayı ödüllendirdiğini gösteriyor. ([OpenAI][1])

Bu yüzden çözüm öncelikle daha iyi bir model değil:

> **GPT’yi “gerçekçilik otoritesi” olmaktan çıkarıp, körlenmiş karşılaştırmalı hata bulucu ve parametre seçici hâline getirmek.**

## En yüksek ROI’li değişiklik: tek render yerine kontrollü A/B taraması

GPT’ye şunu sorma:

> “Bu gerçekçi olmuş mu?”

Şunu yaptır:

```text
Gerçek referans: R

A: roughness = 0.35
B: roughness = 0.50
C: roughness = 0.65
D: roughness = 0.80

Diğer bütün parametreler aynı.

R'ye en yakın adayı seç.
Sadece highlight genişliği, highlight yoğunluğu ve yüzeyin
grazing-angle davranışını değerlendir.
```

Modelin **mutlak fiziksel değer tahmini** zayıf olabilir; fakat aynı sahnenin kontrollü varyantlarını karşılaştırması çok daha kullanılabilir olur. Sonraki turda örneğin `0.45–0.60` aralığını daraltırsın.

Aynı yöntem şunlara uygulanabilir:

```text
texture scale       0.75 / 1.00 / 1.25 / 1.50
roughness           0.30 / 0.45 / 0.60 / 0.75
normal strength     0.25 / 0.50 / 0.75 / 1.00
displacement        0 / 2 mm / 5 mm / 10 mm
soil moisture       dry / damp / wet
sun elevation       15° / 30° / 60°
camera blur         0 / low / medium
```

Bu, “GPT bir şey yaptı ama doğru yaptığını anlayamadı” döngüsünü **ölçülü parametre aramasına** çevirir.

---

# Önerdiğim doğrulama mimarisi

```text
Builder agent
    ↓
Kontrollü render varyantları
    ↓
Otomatik metrikler + diagnostic görüntüler
    ↓
Körlenmiş GPT verifier
    ↓
Kararlı mı?
 ├─ Evet → kabul / sonraki parametre
 └─ Hayır → insan veya ikinci bağımsız judge
    ↓
Gerçek holdout üzerinde downstream test
```

## 1. Builder ile verifier’ı ayır

Verifier’a builder’ın şunları söylediğini gösterme:

```text
“Roughness sorununu çözdüm.”
“Texture artık gerçek fotoğrafa çok yakın.”
“Yeni sonuç daha gerçekçi.”
```

Bunlar ciddi anchoring oluşturur. Verifier yalnızca şunları görsün:

```text
R = gerçek referans
A = aday 1
B = aday 2
diagnostic passes
sayısal metrikler
değerlendirme rubric’i
```

Hatta `A` ve `B`nin hangisinin eski/yeni olduğunu bilmesin.

Aynı karşılaştırmayı ikinci kez, A/B sırasını değiştirerek çalıştır:

```text
Run 1: A solda, B sağda
Run 2: B solda, A sağda
Run 3: crop sırası değiştirilmiş
```

Üç değerlendirmeden en az ikisi uyuşmuyorsa:

```json
{
  "decision": "UNCERTAIN",
  "action": "human_review"
}
```

Bu, verifier’ın pozisyon veya anlatı bias’ını çok hızlı yakalar.

---

## 2. Tek beauty render verme; “verification pack” üret

Her iterasyonda otomatik olarak şu paketi çıkar:

```text
01_real_reference.png
02_candidate_beauty.png
03_before_after_reference.png
04_closeup_center.png
05_closeup_failure_region.png
06_neutral_diffuse_light.png
07_grazing_light_left.png
08_grazing_light_right.png
09_albedo_pass.png
10_normal_pass.png
11_roughness_pass.png
12_depth_pass.png
13_edge_comparison.png
14_difference_heatmap.png
```

### Neden çoklu ışık şart?

Bir materyal tek bir HDRI altında iyi görünüp fiziksel olarak tamamen yanlış olabilir.

| Görüntü                 | Ne doğrular?                               |
| ----------------------- | ------------------------------------------ |
| Nötr diffuse ışık       | Base color, baked shadow, renk dağılımı    |
| Grazing light           | Normal, bump, mikro-geometri               |
| Hareketli noktasal ışık | Roughness ve specular davranış             |
| Siluet/depth pass       | Gerçek displacement ve geometri            |
| Geniş açı               | Texture tekrarı ve ölçek                   |
| Yakın crop              | Detay, plastik görünüm, sampling sorunları |

GPT’ye yalnızca viewport screenshot’ı verme. Final renderı kayıpsız PNG olarak üret; overview yanında kritik bölgeleri ayrıca crop olarak gönder. API kullanıyorsan GPT-5.6’da `detail: original` kullanılabiliyor ve `auto`/varsayılan davranış da `original` ile aynı; yine de büyük bir contact sheet’e her şeyi sıkıştırmak yerine ayrıntılı crop’ları ayrı görüntüler olarak vermek daha güvenlidir. ([OpenAI Developers][2])

---

## 3. “Gerçekçilik” puanını alt faktörlere böl

Tek bir `8/10 realistic` skoru neredeyse işe yaramaz. Bunun yerine:

| Boyut                | GPT’nin bakacağı somut kanıt                 |
| -------------------- | -------------------------------------------- |
| Geometri             | Ölçek, kalınlık, temas, penetrasyon, siluet  |
| Base color           | Renk tonu, kontrast, baked shadow            |
| Roughness/specular   | Highlight genişliği, yoğunluğu, hareketi     |
| Normal/bump          | Işığa bağlı mikro-yüzey tepkisi              |
| Displacement         | Siluet, occlusion ve depth değişimi          |
| Texture ölçeği       | Taş, tane, çatlakların fiziksel boyutu       |
| Tiling               | Tekrarlanan motif ve yön                     |
| Aydınlatma           | Gölge yönü, sertliği, renk sıcaklığı         |
| Kamera               | Perspektif, lens, blur, noise, exposure      |
| Sahne yapısı         | Yoğunluk, nesne yerleşimi, temas ilişkileri  |
| Görevsel gerçekçilik | Modelin göreceği RFID/tag/ot/taş özellikleri |

İnce ve ayrıştırılmış değerlendirme, tek bir bütünsel skordan daha teşhis edilebilir sonuç verir; güncel MLLM-judge çalışmaları da değerlendirmeyi ayrı gözlenebilir faktörlere bölmenin insan yargısıyla uyumu artırdığını gösteriyor. ([arXiv][3])

Her faktör için şu formatı zorunlu tut:

```json
{
  "factor": "roughness",
  "decision": "candidate_too_glossy",
  "evidence": [
    {
      "image": "07_grazing_light_left.png",
      "region": "upper-right concrete surface",
      "observation": "highlight is narrower and brighter than reference"
    }
  ],
  "severity": 2,
  "confidence": 0.78,
  "parameter_change": {
    "parameter": "roughness",
    "direction": "increase",
    "magnitude": "small"
  }
}
```

Görselden anlaşılamayan şeylerde zorunlu cevap:

```json
{
  "decision": "NOT_OBSERVABLE"
}
```

Bu abstention yoksa GPT her boşluğu makul bir açıklamayla doldurma eğiliminde olur.

---

# 4. GPT’nin yanına sayısal verifier koy

GPT tek başına yeterli değil; ancak klasik metrikler de tek başına yeterli değil. İkisini birleştir.

## Kamera açısından eşleştirilmiş real–render çifti varsa

Önce kamera, crop, exposure ve white balance’ı mümkün olduğunca eşleştir. Sonra:

```text
ΔE / renk histogram farkı
LPIPS
SSIM
edge-density farkı
gradient orientation histogramı
yüksek frekans enerji farkı
lokal contrast farkı
shadow mask overlap
```

LPIPS, basit piksel farklarından farklı olarak derin görsel özellikleri kullanır ve orijinal çalışmasında insan perceptual-similarity kararlarıyla klasik metriklerden daha iyi uyuşmuştur. Yine de ışık veya kamera hizası farklıysa LPIPS de yanıltılabilir; bu nedenle yalnızca hizalanmış veya lokal crop’larda kullan. ([arXiv][4])

## Aynı kamera açısı bulunmuyorsa

Gerçek ve sentetik veri kümelerini koşullara göre ayır:

```text
dry soil / damp soil / wet soil
sunny / overcast / indoor
close / medium / far
clean / dusty / damaged
```

Sonra her grup için:

```text
DINOv2 embedding dağılımı
real→synthetic nearest-neighbor distance
synthetic→real nearest-neighbor distance
coverage
MMD veya KID benzeri distribution distance
```

DINOv2 genel amaçlı görsel özellikler üretmek üzere geliştirilmiştir ve görüntü/piksel seviyesinde birçok görevde kullanılabilir; KID ise örnek dağılımları arasındaki farkı ölçmek için geliştirilmiş bir ölçüttür. Bunları “gerçekçilik kanıtı” değil, **domain-gap alarmı** olarak kullanmak gerekir. ([arXiv][5])

DreamSim de daha bütünsel renk, layout ve nesne benzerliğinde yardımcı olabilir; ancak foreground ve semantik yapıya güçlü ağırlık verdiği için ince roughness veya mikro-texture doğrulamasının yerine geçmez. ([arXiv][6])

---

# 5. Materyal için özel fiziksel test sahnesi kur

Her materyali bütün EBİS veya tren sahnesinde doğrulamaya çalışma. Önce standart bir **material validation scene** kullan:

```text
1 düzlem
1 küre
1 yuvarlatılmış küp
ölçek referansı
nötr gri arka plan
kalibre edilmiş kamera
diffuse area light
hareketli küçük area light
standart HDRI
```

Her materyal için otomatik render:

```text
front diffuse
45° light
grazing light
backlight
rotating-light sequence
macro closeup
2 m viewing distance
10 m viewing distance
```

Bu testte:

* Base color yanlışsa diffuse renderda görülür.
* Roughness yanlışsa highlight genişliğinde görülür.
* Normal yanlışsa grazing light altında görülür.
* Displacement yanlışsa siluet/depth pass’te görülür.
* Texture scale yanlışsa cetvel/ölçek referansıyla görülür.
* Tiling yanlışsa geniş yüzeyde görülür.

Materyal bu unit test’i geçmeden kompleks sahneye eklenmez.

---

# 6. GPT verifier’ı kontrollü bozulmalarla test et

Bu muhtemelen en değerli mühendislik adımıdır.

Gerçek referansa yakın bir renderdan bilerek hatalı varyantlar üret:

```text
roughness × 0.5
roughness × 1.5
normal strength × 2
texture scale × 0.7
texture scale × 1.4
saturation +20%
exposure +0.5 EV
displacement × 3
visible texture tiling
incorrect light direction
wrong camera focal length
```

Sonra GPT’ye bunları gerçek referansa yakınlığa göre sıralat.

Beklenen sıra ile GPT sırası arasındaki uyumu ölç:

```text
pairwise accuracy
Spearman correlation
A/B order consistency
abstention correctness
```

Örneğin verifier roughness perturbasyonlarında yalnızca `%55` doğru sıralama yapıyorsa, roughness kararlarını ona bırakma. Texture ölçeğinde `%90` ise o alanda otomasyona izin ver.

Bu yaklaşım verifier’ı soyut biçimde “iyi mi?” diye değerlendirmek yerine, **senin EBİS/tren/tarım domain’inde gerçekten hangi kusurları görebildiğini** ölçer. Kontrollü perceptual perturbasyonlarla judge güvenilirliğini sınama fikri güncel multimodal-judge çalışmalarının da merkezinde bulunuyor. ([arXiv][7])

---

# 7. Nihai doğrulayıcı yine downstream performans olmalı

Senin sentetik veri kullanımında amaç Pixar kalitesinde render üretmek değil:

```text
Gerçek holdout üzerinde
detection / segmentation / depth performansını artırmak
```

Bu nedenle son kabul testi:

| Eğitim                     | Gerçek holdout testi              |
| -------------------------- | --------------------------------- |
| Yalnız gerçek veri         | Baseline                          |
| Yalnız sentetik veri       | Sim-to-real yeterliliği           |
| Gerçek + sentetik          | Sentetik verinin marjinal katkısı |
| Gerçek + kötü sentetik     | Negatif kontrol                   |
| Gerçek + seçilmiş sentetik | Verifier’ın gerçek faydası        |

Örneğin tarım projesinde:

```text
crop-hit rate
medium/large weed recall
unknown/no-spray calibration
mIoU
failure-gallery dağılımı
```

EBİS’te:

```text
RFID recall
concrete-sample detection
occlusion bucket performance
lighting bucket performance
false-positive rate
```

Eğer GPT’nin “daha gerçekçi” dediği versiyon gerçek holdout performansını düşürüyorsa, GPT yanlıştır veya görsel gerçekçilik görev açısından yanlış eksende optimize edilmiştir.

---

# Uygulanabilir minimum sistem

Başlangıçta fazla karmaşıklaştırmadan şunu kurardım:

```text
Her değişiklik için:

1 gerçek referans
1 önceki render
4 tek-parametreli yeni aday
2 yakın crop
2 farklı ışık renderı
1 albedo/normal/roughness diagnostic sheet
1 LPIPS + renk + edge raporu
3 körlenmiş GPT değerlendirmesi
```

Kabul kuralı:

```text
- GPT A/B sıralaması en az 2/3 tutarlı
- İlgili sayısal metrik kötüleşmemiş
- Kritik fiziksel rubric maddesi başarısız değil
- Emin olunamıyorsa insan incelemesi
- Dataset sürümü yalnızca gerçek holdout ablation sonrası kabul
```

Verifier’a verilecek temel komut da şu olabilir:

```text
Sen körlenmiş bir simülasyon görsel doğrulayıcısısın.

R gerçek referanstır.
A, B, C ve D aynı sahnenin farklı simülasyon adaylarıdır.
Adayların nasıl üretildiğini veya hangisinin yeni olduğunu bilmiyorsun.

Yalnızca belirtilen değerlendirme faktörünü incele.
Görüntüde doğrudan gözlenemeyen özellikleri tahmin etme.
Her iddia için görüntü adı, bölge ve gözlenebilir kanıt belirt.
Kanıt yetersizse NOT_OBSERVABLE veya UNCERTAIN döndür.
Genel estetik veya etkileyicilik değerlendirmesi yapma.
Önce adayları R'ye yakınlık bakımından sırala.
Ardından yalnızca en belirgin parametre değişikliğini öner.
```

## Net önerim

**Model değiştirmeye başlamadan önce üç şeyi yap:**

1. Tek screenshot yerine standart çok-ışıklı verification pack üret.
2. “Gerçekçi mi?” yerine körlenmiş, tek-parametreli A/B/C sıralaması yaptır.
3. GPT’nin görebildiği kusurları kontrollü perturbasyon benchmark’ıyla ölç.

Bunlar yapıldığında GPT oldukça faydalı bir **iterasyon yönlendiricisine** dönüşür. Fakat son “gerçeğe yeterince yakın ve sentetik veri olarak faydalı” kararı, otomatik görsel metrikler ve gerçek holdout ablation ile verilmelidir.

[1]: https://openai.com/index/thinking-with-images/ "Thinking with images | OpenAI"
[2]: https://developers.openai.com/api/docs/guides/images-vision "Images and vision | OpenAI API"
[3]: https://arxiv.org/html/2602.13028v1 "Human-Aligned MLLM Judges for Fine-Grained Image Editing Evaluation: A Benchmark, Framework, and Analysis"
[4]: https://arxiv.org/abs/1801.03924 "[1801.03924] The Unreasonable Effectiveness of Deep Features as a Perceptual Metric"
[5]: https://arxiv.org/abs/2304.07193 "[2304.07193] DINOv2: Learning Robust Visual Features without Supervision"
[6]: https://arxiv.org/html/2306.09344v3 "DreamSim: Learning New Dimensions of Human Visual Similarity using Synthetic Data"
[7]: https://arxiv.org/html/2606.02578v1 "Mitigating Perceptual Judgment Bias in Multimodal LLM-as-a-Judge via Perceptual Perturbation and Reward Modeling"


















Evet, **Unreal MCP ile de**, **Blender MCP ile de** çok iyi noktaya gelebilirsin.
Ama “foto ile simülasyonu ayırt edilemez hale getirme” hedefinde en kritik ayrım şu:

> **Güzel görünmek** ile **ayırt edilemez olmak** aynı şey değil.
> İkincisi için “göz kararı shader tuning” değil, **ölçülü kapalı çevrim kalibrasyon sistemi** kurman lazım.

Ve açık konuşayım:

> **Tam “mükemmel” gerçekçilik** pratikte asimptot.
> Ama **belirli kamera + ışık + materyal koşullarında ayırt edilmesi çok zor** hale getirmek gayet mümkün.

---

# En doğru strateji

Benim önerim şu:

## En iyi genel yaklaşım

```text
Blender/Cycles veya Unreal Path Tracer
+ parametrik materyal sistemi
+ çoklu ışık / çoklu görünüm gerçek veri
+ otomatik metrikler
+ LLM outer-loop kontrolü
+ sayısal optimizer
+ accept / rollback
```

## Pratik karar

* **Materyal kalibrasyonu ve inverse-rendering benzeri döngü için:**
  **Blender daha rahat**
* **Final scene realism, büyük sahne, runtime ve asset orchestration için:**
  **Unreal çok güçlü**
* **Mümkünse hibrit:**
  **Blender’da kalibre et, Unreal’da ölçekle**

Ama sen “tek sistemle de olur mu?” diyorsan:
**Olur.** Unreal ile de olur, Blender ile de olur.
Fakat yöntem aynı kalmalı.

---

# Ana fikir: gerçekçiliği tek seferde değil, blok blok çöz

En büyük hata şu olur:

```text
Bütün materyal + ışık + kamera + noise + geometriyi
aynı anda optimize etmeye çalışmak
```

Bu durumda sistem sahte çözümler bulur.
Mesela:

* albedo yanlış,
* roughness yanlış,
* ışık gücü yanlış,

ama bunlar birbirini telafi eder, görüntü “güzel” görünür.
Bu iyi bir çözüm değildir.

Doğru yol:

---

# 1. Problemi 6 bloğa böl

## A. Kamera / sensör bloğu

Bunu ilk çöz.

* focal / intrinsics
* distortion
* exposure
* gain
* white balance
* gamma / response curve
* vignetting
* blur
* sharpening
* noise
* compression artifacts

Bunlar yanlışsa materyal optimizasyonu yanlış yöne gider.

---

## B. Işık bloğu

Özellikle LED verin varsa çok önemli.

* LED pozisyonu
* intensity
* beam shape
* falloff
* color / spectrum
* IR source behavior
* shadow softness

Materyal doğruluğu için ışığın doğru modellenmesi şart.

---

## C. Geometri bloğu

Burada amaç “mesh estetiği” değil; **yansıma, gölge, siluet ve teması etkileyen gerçek yüzey formunu** yakalamak.

* yüzey eğriliği
* kenar yuvarlaklığı
* kalınlık
* panel aralıkları
* beton kırık formu
* yüzey çukuru / çıkıntısı
* yüksek frekanslı displacement
* büyük deformasyonlar

Kritik kural:

> Sadece normal map ile çözülemeyecek her şey geometri veya displacement olmalı.

Özellikle:

* kırık kenarlar,
* çatlak derinliği,
* ezilme,
* bombe,
* kaynak izi,
* oyuk,
* büyük yüzey bozulması

yalnızca texture işi değildir.

---

## D. Materyal bloğu

Burada asıl kazanç var.

Her materyali tek texture gibi düşünme.
Şu bileşenlere ayır:

### 1) Base color / albedo

Ama içinde baked shadow, glare, highlight olmamalı.

### 2) Roughness

Çoğu gerçekçilik kaybı burada olur.
Hem **global roughness**, hem de **spatially varying roughness** gerekir.

Örnek:

* temiz boyalı metal başka,
* kenarları aşınmış metal başka,
* yağlı bölge başka,
* tozlu bölge başka.

### 3) Specular / reflectance

Özellikle plastik, boya, beton kaplama, etiket yüzeyi için önemli.

### 4) Metallic

Sadece gerçekten metal olan bölgelerde.

### 5) Normal

Mikro yüzey karakteri için.

### 6) Height / displacement

Orta ve büyük yüzey formu için.

### 7) Layered material

Gerçek dünya çoğu zaman tek materyal değildir:

```text
ana yüzey
+ boya
+ kir
+ toz
+ yağ
+ pas
+ çizik
+ edge wear
+ su / ıslaklık
```

Gerçekçilikte büyük sıçrama burada gelir.

---

## E. Yüzey varyasyonu / deformasyon bloğu

Foto-gerçek hissi çoğu zaman “ortalama görünümden” değil, **kusurlardan** gelir.

Özellikle ekle:

* edge wear
* chipped paint
* micro scratches
* dust accumulation
* oil smears
* rust spread
* concrete pores
* broken corner masks
* stain flow
* directional abrasion
* dents / bends
* local warping

Bunlar random olmamalı.
**Fiziksel mantığa göre oluşmalı.**

Örnek:

* toz yukarıda değil, yatay yüzeyde birikir
* pas su akış yönünde ilerler
* aşınma köşe ve temas bölgelerinde olur
* yağ, hareketli bağlantı yakınında olur
* beton çatlağı rastgele gürültü gibi davranmaz

---

## F. Sensor-domain bloğu

En sona bırak.

* noise
* bloom
* chromatic aberration
* motion blur
* denoise artifacts
* rolling shutter
* NIR sensor response

En büyük yanlışlardan biri:
**fiziksel olarak zayıf renderı noise ile “gerçekçi” göstermeye çalışmak**.

Bu son katman olmalı, ilk değil.

---

# 2. Hedefi “tek render güzelliği” olarak tanımlama

Gerçekçilik için metrik şöyle kurulmalı:

## Kötü hedef

```text
Bu screenshot güzel mi?
```

## Doğru hedef

```text
Aynı nesnenin
aynı kamera
aynı poz
aynı LED koşulları altındaki
gerçek görüntüsüne ne kadar benziyor?
```

Bunu da tek skorla değil, çoklu kayıpla ölç:

```text
L_total =
  L_color
+ L_highlight
+ L_texture
+ L_edge
+ L_geometry
+ L_multi_light_consistency
+ L_ir
+ L_sensor
+ L_regularization
+ L_task
```

### Örnek alt metrikler

* patch histogram difference
* edge density difference
* highlight width / intensity difference
* local contrast difference
* power spectrum / frequency content
* LPIPS benzeri perceptual fark
* silhouette mismatch
* shadow mismatch
* IR intensity mismatch
* ROI bazlı materyal hatası
* gerçek holdout görev performansı

---

# 3. En yüksek ROI: materyali iki ölçeğe böl

Bu çok önemli.

Bir materyal için tek texture yetmez.
Şunu ayır:

## Macro structure

* büyük lekeler
* kir dağılımı
* pas bölgeleri
* renk geçişleri
* beton ton farkları
* boya aşınma zonları

## Micro structure

* pürüz
* tanecik
* mikro çizik
* küçük çukur
* yüzey lifleri
* çok küçük roughness değişimi

Gerçek foto hissi genelde bu iki ölçeğin birlikte doğru olmasından gelir.

### Uygulama

```text
Base material
+ macro mask layer
+ micro normal layer
+ roughness breakup layer
+ edge wear mask
+ stain/dirt mask
```

Unreal’da da Blender’da da bunu yapabilirsin.

---

# 4. En kritik teknik: LED / IR dataset ile inverse fitting

Elinde tonlarca LED ve IR veri varsa bu büyük avantaj.

Bunu yalnızca “referans görsel” gibi kullanma.
Her capture set şu yapıda olmalı:

```text
same object / same pose / same camera
+ LED_01
+ LED_02
+ LED_03
+ ...
+ IR_01
+ maybe visible_all
```

Bu sayede sistem şunu öğrenir:

* hangi parça diffuse davranıyor,
* hangi parça specular davranıyor,
* roughness nasıl değişiyor,
* normal/displacement neleri açıklıyor,
* hangi farklar sensörden geliyor.

Bu veriyi kullanarak materyali şöyle fit et:

---

# 5. Stage-wise fitting plan

## Aşama 1 — Kamera ve ışık sabitle

Önce yalnızca:

* camera
* LED intensity / orientation
* global exposure
* noise

fit et.

Materyal basit olsun.

---

## Aşama 2 — Basit materyal fit

Her materyal için ilk turda:

* albedo
* roughness
* specular
* normal strength

fit et.

Henüz deformasyon, kir, pas vs. ekleme.

---

## Aşama 3 — Spatial variation fit

Şimdi ekle:

* roughness map
* albedo variation map
* dirt mask
* wear mask
* stain masks

Bu aşama gerçekçiliği ciddi artırır.

---

## Aşama 4 — Surface form fit

Burada:

* displacement
* bevel radius
* panel waviness
* dents
* chipped edges
* concrete pore depth

fit edilir.

Özellikle grazing light altında fark çok büyür.

---

## Aşama 5 — Layered defects fit

Burada:

* dust
* oil
* rust
* smears
* scratches
* peeling paint

eklenir.

---

## Aşama 6 — IR-specific fit

Görünür materyal ile IR davranışı aynı değildir.

Ayrı parametreler tanımla:

```text
visible_albedo
visible_roughness

nir_reflectance
nir_scatter_or_roughness
nir_response_offset
```

---

## Aşama 7 — Sensor look fit

En son:

* grain
* blur
* compression
* slight glare
* demosaic look

eklenir.

---

# 6. LLM burada tam olarak ne yapmalı?

LLM sayısal optimizer yerine geçmemeli.

## LLM’nin görevi

* baskın hata tipini teşhis etmek
* hangi blok optimize edilecek kararını vermek
* hangi parametrelerin serbest bırakılacağını seçmek
* optimizer budget ayarlamak
* iyileşme gerçekten genelleşti mi kontrol etmek
* kabul / rollback yapmak
* yapı değişikliği önermek

## Optimizer’ın görevi

* parametre değerlerini bulmak

### Örnek

LLM şöyle demeli:

```text
Dominant failure:
painted metal highlight too sharp under LED_03 and LED_04.

Next action:
optimize painted_metal block only.

Free params:
roughness_mean
roughness_variance
specular_level
clearcoat_strength

Freeze:
camera, LED, geometry, dirt layer

Budget:
64 candidates
```

Bu çok daha güvenilir.

---

# 7. Parametrik materyal şablonu kur

Her materyal için tek tek custom node spaghetti yapma.
Bir “master material schema” kur.

## Örnek materyal şablonu

```text
Material_X
├── base_albedo
├── albedo_macro_variation
├── roughness_mean
├── roughness_map
├── specular
├── metallic
├── normal_micro
├── normal_macro
├── height_map
├── displacement_strength
├── edge_wear_mask
├── dirt_mask
├── oil_mask
├── rust_mask
├── clearcoat
├── anisotropy(optional)
├── ir_reflectance
└── sensor-domain overrides(optional)
```

Bu şablon hem Blender’da hem Unreal’da uygulanabilir.

Böylece LLM / optimizer yalnızca parametre alanında gezer.

---

# 8. Gerçekçiliği en çok artıran özellikler

Sorunun özüne gelirsek, “ayırt edilemezlik” için en büyük katkıyı genelde bunlar verir:

## En büyük etkiler

1. **Doğru roughness ve roughness variation**
2. **Doğru normal/displacement**
3. **Layered dirt / wear / defects**
4. **Doğru highlight davranışı**
5. **Texture fiziksel ölçeği**
6. **Non-uniformity**
7. **Kenar, köşe ve temas bölgelerinin gerçek davranışı**
8. **Lighting model uyumu**
9. **Sensor look**
10. **IR response consistency**

## En sık hata

* texture çok temiz
* roughness tekdüze
* edge’ler fazla steril
* displacement eksik
* kir/pas rastgele noise gibi
* highlight plastik gibi
* texture ölçeği yanlış
* materyal her yerde aynı davranıyor

Gerçek dünya neredeyse hiçbir zaman “uniform” değildir.

---

# 9. Unreal ve Blender’da nasıl uygularsın?

## Unreal ile

Daha güçlü tarafları:

* layered materials
* decals
* PCG
* büyük sahneler
* güçlü material instances
* final synthetic generation
* runtime çeşitlilik

### Unreal’da ideal yaklaşım

* her materyali material instance tabanlı yap
* shader graph’i stabil tut
* optimizer yalnızca parametreleri oynasın
* deformasyon için geometry + displacement + decals birlikte kullan
* ground-truth calibration için mümkünse Path Tracer kullan
* final large-scale generation’ı raster/Lumen/Nanite tarafında ayrı çöz

### Unreal’da dikkat

Editor-centric yapı bazen yoğun iterasyonda ağır gelebilir.
Ama iyi kurulmuş toolchain ile gayet çalışır.

---

## Blender ile

Daha güçlü tarafları:

* headless batch
* Python ile tam kontrol
* node tree manipülasyonu rahat
* AOV/debug pass rahat
* geometry nodes
* calibration / fitting için doğal ortam

### Blender’da ideal yaklaşım

* Cycles ile truth render al
* BlenderProc ile batch varyantlar üret
* node groups ile parametrik materyal kur
* geometry nodes ile kir, parçacık, wear dağıt
* optimizer döngüsünü Python ile bağla

---

# 10. Bence en iyi pratik setup

Ben olsam şöyle yaparım:

## Eğer tek motor seçeceksem

### Materyal kalibrasyon/fitting için:

**Blender**

### Büyük synthetic dataset üretimi / scene assembly için:

**Unreal**

Yani:

```text
Gerçek veri
→ Blender’da materyal ve sensör kalibrasyonu
→ öğrenilmiş map/parametre/export
→ Unreal’da scene-level kullanım ve randomization
```

Bu hibrit setup en güçlü olanı.

Ama “tek yerde çözeceğim” diyorsan:

* daha araştırma ve fitting ağırlıklıysan **Blender**
* daha production ve large scene ağırlıklıysan **Unreal**

---

# 11. “İteratif mükemmelleştirme” için kabul mekanizması

Her değişiklik hemen kabul edilmemeli.

## Her iterasyonda

### Train-fit set

optimizer burada arama yapar.

### Validation set

kabul/ret burada verilir.

### Frozen holdout

hiç dokunulmaz. gerçekçilik genellemesi burada test edilir.

---

## Kabul kuralı

Bir aday ancak şu durumda kabul edilsin:

* RGB validation iyileşmiş
* IR validation iyileşmiş veya kötüleşmemiş
* LED koşullarının çoğunda iyileşme var
* texture/frequency/edge hatası kötüleşmemiş
* holdout’ta da iyileşme korunmuş
* downstream görev performansı düşmemiş

Aksi halde rollback.

---

# 12. En kritik son nokta: beauty realism değil, task realism

Senin amaç sadece “insan gözüne güzel görünmek” değilse,
özellikle detection / segmentation / perception için şunu ölç:

> **Bu yeni gerçekçilik iyileştirmesi gerçek görev performansına katkı sağlıyor mu?**

Bazen görüntü daha “sinematik” olur ama model için daha kötü olur.
Mesela:

* fazla blur,
* fazla noise,
* fazla stylized glare,
* dramatik contrast

insana daha gerçekçi gelebilir, ama görev için zarar verir.

Bu yüzden son metrik mutlaka:

```text
real holdout detection/segmentation/depth performance
```

olmalı.

---

# Sana en sade operasyon planı

## V1

1. 3 materyal seç:

   * boyalı metal
   * beton
   * etiket/plastik

2. Her biri için:

   * çoklu LED
   * IR
   * aynı poz capture setleri hazırla

3. Parametrik materyal master kur:

   * albedo
   * roughness
   * specular
   * normal
   * displacement
   * dirt/wear
   * IR reflectance

4. Şu sırayla fit et:

   * camera/sensor
   * LED
   * base material
   * roughness map
   * displacement
   * wear/dirt
   * IR behavior
   * sensor look

5. LLM’yi yalnızca:

   * dominant hata seçimi
   * experiment planning
   * accept/rollback
     için kullan

6. Optimizer ile küçük blokları çöz

7. Holdout’ta doğrula

8. Sonra bunu tüm asset library’ye yay

---

# Kısa cevap

**Evet, Unreal MCP ile de, Blender MCP ile de iterative olarak çok ileri gerçekçilik elde edebilirsin.**
Ama bunun anahtarı:

> **LLM’nin “shader ile oynaması” değil,
> parametrik materyal + çoklu ışık/IR veri + blok bazlı fitting + otomatik kabul/rollback sistemi** kurmaktır.

Ve özellikle şu dört şey en çok farkı yaratır:

1. **Spatially varying roughness**
2. **Displacement / gerçek yüzey formu**
3. **Layered defects: dirt, wear, oil, rust, chips**
4. **IR ve visible davranışını ayrı modellemek**

İstersen bir sonraki mesajda sana bunu
**Unreal için somut bir pipeline**,
veya **Blender için somut bir pipeline**
olarak adım adım, tool/tool yazayım.
