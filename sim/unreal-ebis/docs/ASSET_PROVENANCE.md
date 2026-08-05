# Asset provenance ve çevrimiçi model değerlendirmesi

Canonical Unreal sahnesinde dış Fab/Bridge/Megascans modeli kullanılmaz.

- Geometri: Unreal Engine basic cube/cylinder/sphere/cone primitives; `ebis_scene.py` ile santimetre ölçeğinde birleştirilir.
- Materyaller: canonical profilde proje scriptinin ürettiği
  constant/noise tabanlı `.uasset` materyaller.
- RFID: generated film, copper antenna ve chip primitives; marka/UID içeriği yok.
- Referans: kurum içi gerçek LED dataset yalnız ölçüm/görsel QC için yerinde okunur, Unreal paketine kopyalanmaz.
- Engine content ve plugin’ler Unreal Engine EULA kapsamındadır; `Content/EBIS` generated project asset’idir.

## Kontrollü PBR adayı

Poly Haven `Blue Metal Plate` 2K haritaları
`assets/external/polyhaven/blue_metal_plate_2k/` altında saklanır. Kaynak URL,
CC0 lisansı, 2,5 m fiziksel genişlik beyanı ve dosya SHA-256 değerleri
`SOURCE.json` içindedir. Geniş sac birleşimleri/uzun çizikleri ve basic cube UV
ölçeği EBİS pikseliyle eşleşmediğinden canonical Unreal materyaline import
edilmedi; yalnız sonraki kontrollü world-aligned A/B deneyi için tutulur.

ambientCG `Concrete003` 2K haritaları da
`assets/external/ambientcg/Concrete003_2K_JPG/` altında, CC0/SHA-256 kontratıyla
tutulur. Aynı seed `59200–59203` direct-UV Unreal A/B’sinde basic cylinder
üzerinde yatay gerilme ve cube üzerinde aşırı koyu agrega kontrastı oluştu:
[procedural](../reports/qc/asset_ab/concrete_procedural_seed59203.png),
[reddedilen direct-UV](../reports/qc/asset_ab/concrete_ambientcg_direct_uv_seed59203_rejected.png).
Bu nedenle Unreal canonical profil `procedural_cast_concrete_v2` olarak kaldı.
İçe alınmış texture/material `.uasset`leri yalnız deney kanıtıdır; ölçülmüş
world-aligned düşük-oranlı blend olmadan dataset’e sokulmaz.

Blender tarafında ayrıca Poly Haven `Rough Concrete` 1K kontrollü test edildi.
CC0/provenance/`1.23 m` ölçek kontratı temiz olmasına rağmen same-seed iki
karede EBİS'e özgü yeni bir cast izi vermedi; daha güçlü kullanım plaster
karakteri taşıyacaktı. Unreal'a import edilmedi. Bu engine'ler arası karar,
lisans güvenliğinin tek başına fiziksel uygunluk anlamına gelmediğini ve aynı
asset'i iki kez gereksiz `.uasset` kopyalamamamız gerektiğini kaydeder.

Unreal'ın yeni compact procedural A/B'si
[`procedural_concrete_v24_v29_ab.png`](../reports/qc/asset_ab/procedural_concrete_v24_v29_ab.png)
V24 hücresel ve V25 geniş mermerimsi albedo noise'unu reddeder. Canonical V27
constant cast BRDF'dir; ölçekli görünürlük küçük pore/edge/residue
geometrisinden gelir.

## İncelenen fakat alınmayan modeller

- Sketchfab `Simple Concrete Compression Machine`: genel pres geometrisi
  gerçek hazne, sağ menteşeli kapı, iki 40 cm plaka ve kamera düzeniyle
  uyuşmuyor; değerlendirilen sayfada doğrulanabilir production indirme/lisans
  kanıtı yok.
- Sketchfab `Concrete Mix Test Cylinder W3`: CC-BY ve yoğun bir hasarlı tarama;
  sağlam nizami deney silindirinin canonical bazı olamaz.
- ambientCG `PaintedMetal003`: CC0, fakat boya kaybı/açık metal yoğunluğu gerçek
  mavi tırtıklı hazneden belirgin fazla.

Sonraki mühendis CAD, PBR texture veya backplate eklediğinde kaynak URL/kurum,
lisans, indirme tarihi, dosya SHA-256 ve izin verilen kullanım alanını buraya
eklemelidir. Lisansı belirsiz asset production dataset’ine giremez.
