Aşağıya doğrudan mühendise verebileceğin şekilde, **basit ama ciddi** bir E2E plan yazıyorum.

---

# E2E Plan — EBIS + Tren Yolu Sentetik Veri Üretimi ve Ablation

## 1) Amaç

Amaç iki şeyi aynı anda ölçmek:

1. **MCP destekli Blender ve Unreal ile**, gerçek veriye benzer sentetik veri üretmek pratikte mümkün mü?
2. Bu sentetik veri, **küçük bir gerçek veri setiyle birlikte kullanıldığında**, basit bir vision modelinin gerçek test performansını iyileştiriyor mu?

Bu çalışmayı **iki domain** için yapacağız:

* **EBIS**: makine içi veri

  * sınıflar: en az `rfid_tag`, `concrete_sample`
  * görev: **detection** ile başla
* **Tren yolu / rail inspection**

  * sınıflar: en az `rail`, `sleeper/tie`, `ballast`, `foreign_object`
  * görev: mümkünse **segmentation**, olmazsa detection fallback

Ayrıca **ablation** için her iki domain’i de **hem Blender hem Unreal** ile üretmeye çalışacağız.

---

# 2) Net hipotez

## Ana hipotez

Küçük gerçek dataset + iyi ayarlanmış sentetik veri, **real-only baseline**’a göre iyileşme sağlar.

## Yardımcı hipotezler

* **EBIS** gibi daha kontrollü ve kapalı sahnelerde Blender daha hızlı sonuç verebilir.
* **Tren yolu** gibi büyük outdoor/procedural sahnelerde Unreal daha avantajlı olabilir.
* MCP, sahne kurma ve iterasyonu hızlandırır; ama asıl değer **generator + label pipeline + validation** tarafında ortaya çıkar.

---

# 3) Başarı kriterleri

## Teknik başarı kriterleri

En az bir domain’de aşağıdakilerden biri gerçekleşmeli:

* **Real-only baseline**’a göre gerçek test setinde anlamlı artış:

  * Detection için:

    * `mAP50` veya `mAP50-95` artışı
  * Segmentation için:

    * `mIoU` veya `mask mAP` artışı
* Özellikle **zor koşullarda** iyileşme:

  * farklı ışık
  * farklı açı
  * kısmi görünme
  * kir/occlusion
  * domain shift

## Pratik başarı kriterleri

Her engine/domain kombinasyonu için ölçülecek:

* İlk kabul edilebilir sahneye ulaşma süresi
* İlk 500/1000 labeled image üretme süresi
* Manual fix sayısı
* Label hatası oranı
* Kontrol edilebilirlik / varyasyon kalitesi

---

# 4) Kapsamı basit tut

İlk iterasyonda hedef **“mükemmel simülasyon” değil**, **“ölçülebilir fayda üreten sentetik veri pipeline’ı”**.

Bu yüzden ilk iterasyon:

* küçük sınıf seti
* tek model ailesi
* sınırlı ama kontrollü randomization
* kolay anlaşılır ablation

---

# 5) Deney matrisi

Her domain için aynı mantıkta çalış:

## Koşullar

1. **R** = sadece gerçek veri
2. **R + B** = gerçek + Blender sentetik
3. **R + U** = gerçek + Unreal sentetik
4. **R + B + U** = gerçek + iki engine’den sentetik
5. **B only** = sadece Blender sentetik *(opsiyonel sanity check)*
6. **U only** = sadece Unreal sentetik *(opsiyonel sanity check)*

## Karşılaştırma adil olsun

* Aynı gerçek split
* Aynı model
* Aynı eğitim epoch / seed sayısı
* Aynı synthetic image budget
* Aynı sınıflar
* Aynı eval metrikleri

---

# 6) Ortak metodoloji

## 6.1 Veri split kuralı

Her domain için:

* **Train**: gerçek verinin %60–70’i
* **Val**: %15–20
* **Test**: %15–20

**Test set sadece gerçek veri olacak.**
Asıl karar bunun üstünden verilecek.

Eğer veri azsa:

* test seti en az 50–100 görüntü olacak şekilde sabitle

## 6.2 Sentetik veri oranı

İlk pilotta şunu öneriyorum:

* gerçek train veri sayısı = `N`
* sentetik veri = `1N` ve `2N` olmak üzere iki seviye dene

Yani örnek:

* 300 gerçek train varsa
* 300 sentetik
* 600 sentetik

Böylece “çok sentetik basınca fayda artıyor mu bozuyor mu” da görünür.

## 6.3 Kalite kontrol

Üretilen her sentetik veri setinden rastgele 100 örnek manuel kontrol edilecek:

* label doğru mu?
* obje görünür mü?
* gerçek veri koşullarına benziyor mu?
* çok yapay artefact var mı?
* objeler mantıksız yerde mi?
* ışık çok saçma mı?
* kamera açısı gerçek veriyle uyumlu mu?

---

# 7) Workstream A — EBIS

---

## A1) Hedef görev

### İlk iterasyon

**Detection** ile başla.

Sınıflar:

* `rfid_tag`
* `concrete_sample`

Opsiyonel daha sonra:

* `sample_tray`
* `sample_holder`
* `machine_inner_panel`

Ama ilk iterasyonda **2 sınıf yeterli**.

---

## A2) Gerçek veri girişi

Ben sana gerçek EBIS örneklerini vereceğim.
Mühendisin ilk işi:

1. Gerçek veri klasörünü incelemek
2. Sınıfları netleştirmek
3. Kamera dağılımını çıkarmak
4. Işık koşullarını çıkarmak
5. Tag boyutu, görünüşü, yerleşimi, beton numunesi tipi gibi kritik değişkenleri yazmak

### EBIS için çıkarılacak dağılımlar

* Kamera tipleri / açıları
* Makine içi arka plan
* Kapı açık/kapalı/açıklık miktarı
* İç ışık seviyesi
* Dış ortamdan gelen ışık
* RFID tag görünürlüğü
* Tag yönü / ön-arka farkı
* Beton numunesi şekli / renk / kir / ıslaklık

---

## A3) EBIS’te sentetik sahne tanımı

### Minimum sahne içeriği

* EBIS makinesi iç hacmi
* En az 2 kamera açısı

  * `camera_door`
  * `camera_angled`
* İç LED/strip light benzeri aydınlatma
* Makine iç yüzeyleri
* RFID tag’ler
* Beton numunesi

### Önemli not

Senin paylaştığın örneklerden anladığımız kadarıyla EBIS için şu baseline mantıklı:

* Kamera pozları sabit baseline olarak tutulmalı
* Işık baseline’ı sabit tutulmalı
* Sonra varyasyonlar şuralardan gelmeli:

  * kapı açıklığı
  * materyal tonları
  * dış dünya / arka plan
  * objelerin küçük yer değişimleri
  * ışık yoğunluğu / color temperature
  * kir / çizik / parlama

---

## A4) RFID tag modeli için minimum gereksinim

İlk POC için RFID tag’ı tam CAD doğruluğunda yapmaya gerek yok.

Yeterli POC özellikleri:

* yaklaşık boyut: **60 x 10 mm**
* çok ince etiket formu
* iki yüz farklı davranış:

  * ön yüz daha parlak / amber-turuncu
  * arka yüz daha mat / biraz daha koyu
* ortada küçük siyah IC
* çevrede bakır / desenimsi anten hissi
* yüzeye yapışık, hafif parlama veren davranış

Bu, vision POC için yeterli.

---

## A5) EBIS için Blender pipeline

### Neden?

EBIS kapalı, nispeten küçük, sahne kontrolü yüksek.
Bu yüzden Blender’la başlamak mantıklı.

### Pipeline

1. Gerçek referansları topla
2. Basit EBIS iç hacmini oluştur / import et
3. RFID tag ve beton numunesi assetlerini oluştur
4. Kamera ve ışık baseline’ını kur
5. Blender MCP ile iteratif düzelt:

   * kamera
   * materyal
   * ışık
   * tag yerleşimi
6. BlenderProc veya eşdeğer pipeline ile:

   * RGB
   * bbox / mask
   * metadata
7. Batch render üret
8. Label QC yap

### Randomization alanları

* Tag pozisyonu
* Tag orientation
* Tag’in görünen yüzü
* Parlama / roughness
* Beton numunesi pozisyonu
* Numune renk tonu / kir / ıslaklık
* Işık şiddeti
* Dışarıdan gelen ışık
* Kapı açıklığı
* Lens hafif blur / noise

---

## A6) EBIS için Unreal pipeline

Amaç “Unreal da bunu yapabiliyor mu?” sorusunu test etmek.

### Unreal’da da aynı hedef

* aynı sınıflar
* benzer kamera açıları
* benzer ışık koşulları
* benzer varyasyon dağılımı

### Pipeline

1. Basit EBIS iç hacmini Unreal’a kur
2. Tag ve numune assetleri ekle
3. Kamera + light baseline oluştur
4. MCP ile düzenle
5. Label output pipeline kur
6. 500–1000 image üret
7. QC yap

### Burada risk

EBIS için Unreal muhtemelen çalışır ama **Blender kadar hızlı/rahat olmayabilir**.
Ama zaten bunu ölçmek istiyoruz.

---

# 8) Workstream B — Tren yolu

---

## B1) Hedef görev

### Öncelik

Mümkünse **segmentation**.

Önerilen sınıflar:

* `rail`
* `sleeper` / `tie`
* `ballast`
* `foreign_object`

Opsiyonel:

* `fastener`
* `vegetation`
* `switch`
* `joint`

Ama ilk iterasyon için **4 sınıf yeterli**.

### Eğer segmentation dataset bulunmazsa

Fallback:

* detection veya instance segmentation
* ama öncelik segmentation

---

## B2) Gerçek dataset bulma görevi

Mühendisin ilk işi:

1. Railway inspection için **uygun kamuya açık dataset** bulmak
2. Lisansını doğrulamak
3. Etiket formatını incelemek
4. Gerçek görüntü dağılımını analiz etmek

### Aranacak özellikler

* Ray hattı görünür
* Sleepers/ties görünür
* Ballast görünür
* Obstacle / foreign object sınıfı varsa çok iyi
* Mümkünse segmentation label
* Farklı hava ve ışık koşulları varsa daha iyi

### Dataset seçim kriteri

Tercih sırası:

1. segmentation labels
2. yeterli veri sayısı
3. görsel kalite
4. açık lisans
5. gerçek inspection benzerliği

---

## B3) Tren sahnesi için minimum sentetik hedef

İlk iterasyonda devasa network yapmaya gerek yok.

### Minimum scene

* düz veya hafif kıvrımlı tek ray hattı
* sleepers
* ballast alanı
* çevre zemin
* az miktarda bitki
* birkaç foreign object varyasyonu
* 2–3 kamera tipi:

  * önden ray ekseni boyunca
  * yukarıdan hafif açı
  * yan / oblique açı

---

## B4) Unreal pipeline (tren için ana aday)

### Neden?

Terrain + spline + procedural corridor + outdoor görünüm için daha doğal.

### Pipeline

1. Basit terrain oluştur
2. Spline ile ray hattı oluştur
3. Ray + sleeper + ballast koridoru kur
4. Çevresel assetler ekle
5. Kamera rotaları / sabit kameralar tanımla
6. MCP ile şu döngü:

   * referansa bak
   * sahneyi düzelt
   * screenshot al
   * tekrar düzelt
7. Label output al
8. Batch render üret

### Randomization alanları

* hava durumu
* güneş açısı
* bulutluluk
* ballast yoğunluğu / renk
* sleeper aşınması
* ray paslanma seviyesi
* bitki yoğunluğu
* foreign object tipi ve yeri
* kamera yüksekliği / pitch / yaw
* hafif motion blur / lens noise

---

## B5) Blender pipeline (tren için ablation)

Amaç, aynı tren görevini Blender’da da üretmeye çalışmak.

### Minimum hedef

* tek ray koridoru
* basit terrain
* sleepers
* ballast
* foreign objects

### Pipeline

1. Curve + Geometry Nodes veya benzeri ile ray koridoru
2. Terrain displacement / procedural ground
3. Asset scattering
4. Kameralar
5. MCP ile iteratif düzeltme
6. Label render
7. Batch üretim

### Not

Tren için Blender muhtemelen çalışır; ama procedural outdoor scale tarafında Unreal daha doğal olabilir. Yine de ölçmek önemli.

---

# 9) MCP kullanım şekli

## Kural

**MCP’yi tek tek görüntü üretmek için değil, generator geliştirmek için kullan.**

Doğru kullanım:

1. referansları modele ver
2. sahneyi kurdur
3. viewport/render ile kontrol ettir
4. generator’ı stabilize et
5. batch render’ı script/config ile çalıştır

Yanlış kullanım:

* her görüntüyü doğal dille tek tek yaptırmak
* label üretimini LLM’e bırakmak
* manual ve tekrarlı prompt zinciriyle büyük dataset üretmeye çalışmak

---

# 10) Model eğitimi planı

## EBIS

* model: **YOLO detect** (küçük model, ör. n/s boyutu)
* sınıflar:

  * `rfid_tag`
  * `concrete_sample`

### Metrikler

* mAP50
* mAP50-95
* precision / recall
* class-wise AP

## Tren

### Tercih

* **YOLO seg** veya benzeri basit segment modeli

### Metrikler

* mAP mask
* mIoU
* per-class IoU

### Eğer detection fallback olursa

* mAP50 / mAP50-95

---

# 11) Eğitim deneyleri

Her domain için şu minimum deneyler yapılacak:

## EBIS

1. real-only
2. real + Blender synth
3. real + Unreal synth
4. real + Blender + Unreal synth

## Tren

1. real-only
2. real + Blender synth
3. real + Unreal synth
4. real + Blender + Unreal synth

Opsiyonel:

* synth-only sanity check

---

# 12) Ölçülecek ek şeyler

Sadece model metriğine bakma. Şunları da tabloya koy:

## Üretim kolaylığı

* ilk çalışan sahneye süre
* ilk 100 render’a süre
* ilk 1000 render’a süre
* ilk temiz label setine süre

## Mühendislik sürtünmesi

* kaç kez pipeline bozuldu
* kaç manuel düzeltme gerekti
* engine-specific workaround sayısı
* label export zorluğu

## Görsel kalite

* gerçek veriye benzerlik
* ışık benzerliği
* materyal benzerliği
* açı dağılımı benzerliği
* artefact yoğunluğu

---

# 13) Çıktı klasör yapısı

Öneri:

```text
project/
  ebis/
    real/
      images/
      labels/
    synth_blender/
      images/
      labels/
      configs/
      metadata/
    synth_unreal/
      images/
      labels/
      configs/
      metadata/
    experiments/
      real_only/
      real_plus_blender/
      real_plus_unreal/
      real_plus_both/
  rail/
    real/
      images/
      labels/
    synth_blender/
      images/
      labels/
      configs/
      metadata/
    synth_unreal/
      images/
      labels/
      configs/
      metadata/
    experiments/
      real_only/
      real_plus_blender/
      real_plus_unreal/
      real_plus_both/
  reports/
    qc/
    metrics/
    final/
```

---

# 14) Her engine/domain için beklenen deliverable

Her kombinasyon için:

## 1. Scene package

* sahne dosyası
* asset listesi
* kamera tanımı
* ışık tanımı
* randomization parametreleri

## 2. Dataset package

* en az 500–1000 sentetik görüntü
* label dosyaları
* metadata / seed bilgisi

## 3. QC raporu

* 100 örneklik manuel kontrol
* başlıca hata türleri

## 4. Kısa engine raporu

* ne kolaydı
* ne zordu
* ne kadar kontrol edilebildi
* tekrar üretilebilir mi

---

# 15) Zaman planı

## Hafta 1 — Hazırlık

* EBIS gerçek veri analizi
* Railway dataset bulma ve seçme
* sınıf ve metrik tanımı
* experiment repo yapısı

## Hafta 2 — POC sahneler

* EBIS Blender POC
* EBIS Unreal POC
* Rail Unreal POC
* Rail Blender POC
* her kombinasyonda ilk 50–100 görüntü

## Hafta 3 — Stabilizasyon

* label export düzeltmeleri
* randomization tuning
* QC
* ilk 500–1000 görüntü setleri

## Hafta 4 — Eğitim ve ilk ablation

* real-only
* real + Blender
* real + Unreal
* real + both

## Hafta 5 — İkinci iterasyon

* başarısız kombinasyonlarda iyileştirme
* domain gap azaltma
* ek sentetik veri gerekiyorsa üretme

## Hafta 6 — Final rapor

* performans tabloları
* engine karşılaştırması
* önerilen sonraki yol

---

# 16) Karar kuralı

Finalde şu sorular cevaplanmalı:

1. **EBIS için hangi engine daha hızlı ve faydalı?**
2. **Tren için hangi engine daha mantıklı?**
3. **Sentetik veri gerçekten katkı sağladı mı?**
4. **Hangi sentetik veri tipi en faydalıydı?**
5. **Bir sonraki yatırım Blender’a mı, Unreal’a mı yapılmalı?**

---

# 17) Beklentiyi doğru koy

Mühendise şunu net söyle:

> Hedef “kusursuz dijital ikiz” değil.
> Hedef, kontrollü biçimde üretilmiş sentetik verinin küçük gerçek dataset yanında gerçekten fayda sağlayıp sağlamadığını ölçmek.

Yani ilk başarı kriteri:

* pipeline çalışsın
* label’lar doğru olsun
* gerçek veriye benzer dağılımlar yakalansın
* model tarafında ölçülebilir etki görülsün

---

# 18) En kısa görev özeti

Mühendise tek paragraf kısa görev özeti olarak şunu verebilirsin:

> EBIS ve tren yolu için, hem Blender hem Unreal kullanarak gerçek veriye benzer sentetik veri üret. EBIS tarafında benim paylaşacağım gerçek veri ve referansları kullan; tren tarafında uygun kamuya açık gerçek dataset bul ve hedef dağılımı ona göre çıkar. Her domain için küçük ama kontrollü bir sentetik dataset üret, ardından basit YOLO detection/segmentation modelleriyle real-only ve real+synthetic ablation çalıştır. Hem model performansını hem de üretim kolaylığını raporla. Amaç, hangi engine’in hangi problemde daha iyi pratik ROI verdiğini görmek.

---

İstersen bir sonraki mesajda bunu daha da pratikleştirip sana şu formatta da hazırlayabilirim:

1. **mühendise atılacak görev metni**
2. **haftalık checklist**
3. **ablation tablo şablonu**
4. **final rapor şablonu**

İstersen direkt bu 4 parçayı hazırlayayım.
