**Evet, doğru anlıyorsun.** 2026 itibarıyla hem Blender hem Unreal, MCP sayesinde eskisine kıyasla çok daha düşük uzmanlıkla yönlendirilebilir hâle geldi.

Artık gerçekçi çalışma döngüsü şu:

```text
Metinle sahneyi tarif et
+ referans görselleri göster
+ kullanılacak asset/materialleri belirt
+ fiziksel ve görsel kuralları ver
        ↓
Multimodal model sahneyi planlar
        ↓
MCP üzerinden Blender/Unreal’ı çalıştırır
        ↓
Viewport/render görüntüsü alır
        ↓
Sonucu referanslarla karşılaştırır
        ↓
Geometriyi, materyali, kamerayı ve ışığı düzeltir
```

## Kritik ayrım: MCP görüntüyü anlamıyor, modele “el ve göz” veriyor

Referans görselleri anlayan şey GPT/Claude gibi **multimodal model**. MCP ise modele şunları yapabilme yetkisi veriyor:

* Sahnedeki objeleri inceleme
* Geometri üretme ve değiştirme
* Asset import etme
* Materyal ve ışık ayarlama
* Python, Blueprint veya PCG işlemleri çalıştırma
* Viewport görüntüsü alıp sonucu yeniden değerlendirme

Dolayısıyla model artık sadece “Blender’da şöyle yapmalısın” demiyor; **Blender veya Unreal içinde gerçekten yapıyor ve sonucuna bakarak düzeltiyor.**

---

# Blender tarafında bu bugün gerçekten mümkün

Blender MCP doğrudan:

* Objeleri oluşturup değiştirebiliyor
* Materyal oluşturup uygulayabiliyor
* Blender Python kodu çalıştırabiliyor
* Viewport görüntüsü alabiliyor
* Poly Haven ve Sketchfab’den model, texture ve HDRI bulabiliyor
* Hunyuan3D ve Hyper3D gibi sistemlerden 3D model ürettirebiliyor

Projenin kendi örnekleri arasında açıkça **“referans görsel vererek bundan Blender sahnesi oluşturma”** akışı da bulunuyor. ([GitHub][1])

Örneğin şunu söylemek artık gayet gerçekçi:

> Bu dört tren yolu fotoğrafını görsel referans al.
> Ray geometrisini 1435 mm açıklıkta oluştur.
> Şu Poly Haven taş materyalini balast için kullan.
> Ahşap traverslerde ikinci görseldeki aşınma ve ıslaklık seviyesini hedefle.
> Üçüncü görseldeki bitki yoğunluğunu kullan.
> Kamerayı ray seviyesinden yerleştir.
> Render al, referanslarla karşılaştır ve benzerliği artırmak için iki kez iterasyon yap.

Model; curve, Geometry Nodes veya Python kullanarak rayları oluşturabilir, assetleri indirebilir, materyalleri bağlayabilir, render/viewport görüntüsünü inceleyip hataları düzeltebilir.

Bu nedenle **“referans görselden custom 3D sahneye hızlı gitme” konusunda Blender şu anda oldukça kullanılabilir.**

---

# Unreal tarafında da büyük ilerleme var

Unreal Engine 5.8’in resmî MCP sistemi; actor oluşturma, ışıklandırmayı ayarlama, material instance üretme, editör arayüzünü inceleme ve otomasyon testleri çalıştırma gibi işlemleri modele açıyor. Ayrıca kendi domain-specific MCP araçlarınızı eklemek de mümkün. Ancak Epic hâlâ özelliği **experimental** olarak tanımlıyor ve bazı yeteneklerin eksik veya değişken olduğunu belirtiyor. ([Epic Games Developers][2])

PCG tarafında ise LLM artık doğrudan procedural graph’ları inceleyip değiştirebiliyor. Epic’in resmî rehberi özellikle:

* Mevcut örnek graph’ları modele gösterin
* Kullanılacak assetleri seçin
* Referansları önce analiz ettirin
* İşlemleri küçük adımlarla yaptırın
* Görsel ve yapısal feedback loop kullanın

diyor. Yani senin söylediğin **“örnek göstererek ve istediğimizi tarif ederek üretme”**, Unreal’ın kendi önerdiği çalışma modeline dönüşmüş durumda. ([Epic Games Developers][3])

Örneğin önceden hazırlanmış bir `RailCorridorGenerator` varsa artık şöyle yönlendirmek oldukça gerçekçi:

> Referanslardaki Anadolu kırsal demiryolu görünümünü hedefle.
> Hat uzunluğu 3 km olsun.
> Kuru, hafif yeşil ve yoğun yeşil olmak üzere üç biome varyasyonu oluştur.
> Balast için `M_Ballast_Granite_02`, traversler için `SM_ConcreteSleeper_B` kullan.
> Her 50 metrede bitki yoğunluğunu randomize et.
> 20 farklı seed oluştur.
> Dört temsili noktadan screenshot al ve rayların terrain altında kalmadığını doğrula.

Unreal burada landscape, splines, PCG, foliage ve gerçek zamanlı ışıklandırmayı birlikte yönetebilir.

---

# Ama “tek prompt ile her şey kusursuz” seviyesinde değiliz

Şunlar oldukça kolaylaştı:

```text
Referans → kaba sahne
Referans → benzer kompozisyon
Hazır assetler → sahne yerleşimi
Materyal referansı → shader/material ayarı
Sahne → farklı ışık ve hava varyasyonları
Hazır generator → yüzlerce procedural varyasyon
```

Şunlar hâlâ zor:

```text
Tek fotoğraftan mühendislik açısından doğru 3D geometri
Hiç template olmadan güvenilir kompleks PCG sistemi
Özel endüstriyel makinenin birebir modellenmesi
Bir prompt ile kusursuz topology, UV ve materyal
Domain kurallarının model tarafından kendiliğinden bilinmesi
Her seed'de hatasız ve fiziksel olarak geçerli sahne
```

Referans fotoğraf, görünen yüzeyi ve genel görünümü anlatır; görünmeyen geometriyi, gerçek ölçüleri veya parçaların mekanik ilişkisini anlatmaz. Örneğin EBİS beton kırma makinesini yalnızca birkaç fotoğrafla **görsel olarak benzer** yapmak mümkün olabilir; fakat mekanik olarak doğru ve farklı açılardan tutarlı model için ölçüler, ek fotoğraflar, CAD veya en azından parça şeması gerekir.

---

# Asıl darboğaz artık motoru elle kullanmak değil

Asıl darboğazlar şunlar:

1. **Kaliteli asset ve PBR materyaller**
2. **Domain kurallarını içeren temel generator**
3. **Sonucu değerlendiren otomatik validator**
4. **Doğru çeşitlilik dağılımı**
5. **Dataset anotasyonlarının güvenilirliği**

MCP bunların kurulmasını çok hızlandırıyor. Fakat kötü assetten veya yanlış domain kurallarından iyi veri çıkaramıyor.

Özellikle synthetic vision verisinde en doğru kullanım şu:

```text
MCP ile generator'ı geliştir
        ↓
Referans görsellerle görünümü ayarla
        ↓
Viewport/render ile iteratif doğrula
        ↓
Generator parametrelerini sabitle
        ↓
Seed'li ve deterministik batch üretim yap
        ↓
RGB + mask + depth + metadata doğrula
```

Her görüntüyü MCP’ye serbestçe yeniden yaptırmak yerine, **bir kez sağlam procedural sistem kurup MCP’ye bu sistemin parametrelerini yönettirmek** gerekir.

---

# Blender–Unreal farkı artık eskisi kadar büyük değil

Ben değerlendirmeyi şöyle güncellerdim:

| İş                                                    | Daha rahat seçenek           |
| ----------------------------------------------------- | ---------------------------- |
| Referans görselden hızla custom sahne çıkarma         | **Blender**                  |
| Materyal, geometri ve kamera üzerinde hızlı iterasyon | **Blender**                  |
| Python ile serbestçe her şeyi değiştirme              | **Blender**                  |
| Büyük terrain ve kilometrelerce dünya                 | **Unreal**                   |
| Çok yoğun foliage ve büyük outdoor sahne              | **Unreal**                   |
| Gerçek zamanlı hava, ışık, tren ve kamera hareketi    | **Unreal**                   |
| Hazır PCG template’i doğal dille çeşitlendirme        | **Unreal**                   |
| Baştan sona vision anotasyonu ve offline dataset      | **Blender stack daha kolay** |

Yani artık mesele:

> “Unreal çok zor, Blender kolay” değil.

Daha doğru ayrım:

> **Blender, AI’ın serbestçe sahne yazması ve düzeltmesi için daha açık bir çalışma alanı. Unreal ise temel procedural sistem hazırlandıktan sonra daha büyük ve gerçek zamanlı dünyaları doğal dille yönetmekte daha güçlü.**

## Sizin hedefiniz açısından net sonuç

**Evet, bugün istediğiniz ortamı tarif ederek, referans fotoğrafları göstererek, belirli materyal ve assetleri işaret ederek üretmek makul derecede mümkün.** Başlangıç uzmanlığı gereksinimi ciddi biçimde düştü.

Ancak en yüksek ROI şu yapıdan gelir:

```text
Blender/Unreal bilgisi çok az olan kullanıcı
        +
güçlü multimodal agent
        +
MCP
        +
hazır asset/material kütüphanesi
        +
küçük bir domain generator
        +
viewport verification
```

Sadece genel görüntüler ve statik vision dataset’i için **Blender MCP daha doğrudan**; tren yolu gibi çok büyük ve dinamik outdoor dünya için ise bir kez temel rail/terrain generator kurulduktan sonra **Unreal MCP çok güçlü ve giderek daha mantıklı** hâle geliyor.

[1]: https://github.com/ahujasid/blender-mcp "GitHub - ahujasid/blender-mcp: Open-source MCP to use Blender with any LLM · GitHub"
[2]: https://dev.epicgames.com/documentation/unreal-engine/unreal-mcp-in-unreal-editor "Unreal MCP in Unreal Editor | Unreal Engine 5.8 Documentation | Epic Developer Community"
[3]: https://dev.epicgames.com/documentation/unreal-engine/working-with-pcg-and-llms-using-unreal-mcp-in-unreal-engine "Working with PCG and LLMs Using Unreal MCP in Unreal Engine | Unreal Engine 5.8 Documentation | Epic Developer Community"
