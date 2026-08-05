# Dış varlık ve çevrimiçi model değerlendirmesi

Canonical sahne, ölçüsü denetlenebilen procedural geometriyi kullanır.
Lisansı ve fiziksel uygunluğu doğrulanmayan hiçbir çevrimiçi model eğitim
verisine girmez. Fotoğraf tabanlı haritalar ancak aynı-seed piksel A/B’sinden
sonra sınırlı bir procedural katmana karıştırılır.

## İndirilen kontrollü PBR deneyi

Poly Haven `Blue Metal Plate` 2K diffuse, roughness ve OpenGL/DirectX normal
haritaları `assets/external/polyhaven/blue_metal_plate_2k/` altındadır.
Kaynak, lisans, fiziksel ölçek ve SHA-256 değerleri yanındaki `SOURCE.json`
dosyasındadır. Varlık CC0’dır; kaynak sayfa yüzeyi 2,5 m genişliğinde tanımlar.

`machine.blue_wall_material_profile =
polyhaven_blue_metal_plate_2k_trial` yalnız A/B içindir. Taramadaki uzun çizik
ve geniş sac birleşimleri gerçek EBİS iç duvarında sürekli görünmediği için
canonical profil `procedural_hammertone_v2` olarak kalır.

Poly Haven `Rough Concrete` 1K diffuse/roughness/displacement haritaları
`assets/external/polyhaven/rough_concrete_1k/` altındadır. Kaynak `CC0`,
beyan edilen genişlik `1.23 m`, resmi files hash'i ve her dosyanın kaynak
MD5/SHA-256 değeri yanındaki `SOURCE.json` içindedir. Same-seed
`59303/59307` actual-pixel testinde düşük-oranlı blend bbox içinde yalnız
`4.78–4.94/255` ortalama mutlak RGB farkı verdi; daha güçlü oran dış ortam
plaster karakteri taşıdığı için canonical değildir.

ambientCG `Concrete003` 2K color, roughness, displacement ve iki normal haritası
`assets/external/ambientcg/Concrete003_2K_JPG/` altındadır. Kaynak, CC0 lisans,
indirme URL’si ve SHA-256 değerleri `SOURCE.json` içindedir. Same-seed A/B’de
düşük oranlı box-projection hibrit gerçek numune ton/mikro-kontrast yönüne
ilerlediği için `sample.material_profile =
ambientcg_concrete003_hybrid_v1` canonical oldu. Harita ana silueti, gözenek
geometrisini, nemi veya hasar rejimini değiştirmez.

## İncelenen fakat alınmayan modeller

- Sketchfab `Simple Concrete Compression Machine`: genel bir pres modeli;
  değerlendirilen sayfada üretim kullanımı için doğrulanabilir indirme/lisans
  kanıtı yok ve hazne/kapı/plaka yerleşimi gerçek EBİS ile uyuşmuyor.
- Sketchfab `Concrete Mix Test Cylinder W3`: CC-BY ve çok yoğun bir tarama,
  fakat kırılmış/sıkıştırılmış numuneyi temsil ediyor. Sağlam nizami deney
  silindiri için yanlış baz; yalnız biçim/hasar çalışması referansı olabilir.
- ambientCG `PaintedMetal003`: CC0 olsa da önizleme yoğun boya kaybı ve açık
  metal içeriyor; gerçek mavi tırtıklı iç yüzeye göre aşırı yıpranmış.

Sonuç: çevrimiçi tam makine modelini “hazır gerçekçilik” diye içeri almak
yerine, gerçek piksele göre kurulan geometriyi korumak ve yalnız hakları açık,
ölçeği belli PBR katmanlarını kontrollü A/B olarak denemek daha güvenli.
