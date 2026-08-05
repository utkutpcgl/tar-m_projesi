# RFID ve concrete bbox / occlusion politikası

## Temel karar

YOLO kutuları semantic sınıf-union maskesinden değil, her fiziksel RFID instance’ının RGB ile aynı geometrik warp’ı paylaşan görünür maskesinden türetilir. Gerçek LED annotasyonunda plakayla beton arasından yalnız bir şerit görünen tag’ler de yeterli piksel varsa pozitif kutulanmıştır; tam örtülü tag kutulanmamıştır.

## 640 model girişindeki eşikler

| Partition | RFID kuralı |
| --- | --- |
| standard | kısa kenar ≥4 px, uzun ≥12 px, foreground ≥40 px, visibility proxy ≥0.35, en büyük component ≥0.65, görüntü kenarına ≥2 px |
| hard_occlusion | kısa ≥3 px, uzun ≥8 px, foreground ≥20 px, visibility proxy ≥0.15, component ≥0.45; kenar teması serbest |
| exclude | hard eşiğinin altında kalan görünür instance |
| fully_occluded | visible pixel yok; YOLO satırı yok |
| outside_frame | projection kadraj dışında; YOLO satırı yok |

Render çözünürlüğü ne olursa olsun eşikler `model_input_px=640` ölçeğine çevrilir. 1920×1080 gerçek RFID medyanı yaklaşık 118×40 px; 640 letterbox’ta yaklaşık 39×13 px’tir. En küçük gerçek tag’ler 640’ta yaklaşık 7×4 px’e iner, bu nedenle küçük-object recall için eğitimde `imgsz=960` ayrıca denenir.

## Partition güvenliği

Görüntü partition’ı en kötü görünür instance tarafından belirlenir:

1. herhangi bir exclude → tüm görüntü `exclude`;
2. yoksa herhangi bir hard → `hard_occlusion`;
3. aksi halde → `standard`.

`standard`, `hard_occlusion` ve `exclude` ayrı fiziksel image/label dizinleridir. Normal deney yalnız standard kullanır. Hard ancak adı açık bir ablation kolunda eklenir. Exclude hiçbir train/val/test manifest’ine girmez.

## Neden segmentation-union bbox kullanılmıyor?

- İki tag aynı maskede birleşirse aradaki beton/plakayı kapsayan tek dev kutu oluşur.
- Bir occluder tek tag’i iki parçaya ayırırsa union kutu aradaki görünmeyen alanı kapsar.
- Beton parçalandığında uzak molozlarla ana numune tek kutuya şişebilir.
- Lens warp kenar interpolasyonu birkaç pikseli yanlış foreground yapabilir.

Semantic `rfid_tag` maskesi QC içindir. Training label’ın source of truth’u `rfid_tags[].visible_annotation` ve yayımlanmış instance maskeleridir.

## Concrete politikası

- Tek hedef, kırılmadan önceki ana numunedir; arka plan kırıntıları class 1 değildir.
- Görünür bbox görüntü sınırında kırpılabilir. Gerçek concrete kutularının yarıdan fazlası bir sınıra değdiği için edge contact reddedilmez.
- Minimum kısa/uzun kenar 64 px, normalize bbox alanı için operasyonel hedef ≥%3’tür.
- Numune gerçekten ayrı büyük parçalara kırılacaksa class-union yerine instance ontolojisi yeniden tanımlanmalıdır.

## İnsan kontrol örneklemesi

Her yeni config hash’inde 100 karelik stratified QC seçin:

- iki kamera × iki sample şekli;
- standard/hard/exclude;
- 0, 1, 2–4 ve 5+ tag;
- üst/alt plate gap ve sample yüzü;
- dört ışık profili.

En az iki kişi 100 kareyi bağımsız kontrol eder. Her tag için `doğru kutu`, `eksik`, `fazla`, `partition yanlış` işaretlenir. Normal train kapısı: yanlış/eksik bbox oranı <%1; tek bir visible-unlabelled exclude nesnesinin standard dizinine sızması hard fail’dir.

