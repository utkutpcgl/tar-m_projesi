# RFID ve concrete bbox / occlusion politikası

## Temel karar

Her fiziksel RFID ayrı `EBIS_INSTANCE` kimliği, visible maskesi ve isolated amodal maskesi alır. YOLO bbox yalnız visible instance maskesinin piksel sınırıdır. Birleşik `rfid_tag` semantic maskesinden bbox üretilmez.

## 640 model girişindeki eşikler

| Statü | Kural |
| --- | --- |
| `standard_positive` | kısa ≥4 px, uzun ≥12 px, foreground ≥40 px, visibility ≥.35, largest component ≥.65, edge margin ≥2 px |
| `hard_positive` | kısa ≥3 px, uzun ≥8 px, foreground ≥20 px, visibility ≥.15, largest component ≥.45 |
| `excluded_too_small_or_occluded` | görünür fakat hard eşiğinin altında; label yok ve kare exclude |
| `present_but_fully_occluded` | amodal >0, visible=0; label yok |
| `present_but_outside_frame` | amodal=0; label yok |

Ölçüler render çözünürlüğünden `model_input_px=640` ölçeğine çevrilir. Visibility `visible_pixels / amodal_in_frame_pixels` oranıdır. Amodal pass target dışındaki mesh’leri gizler fakat kadraj clipping’ini korur.

## Kare partition’ı

1. Herhangi bir görünür tag exclude ise görüntü `exclude`.
2. Exclude yok, en az bir hard varsa `hard_occlusion`.
3. Aksi halde `standard`.

Partition fiziksel dizindir; yalnız metadata flag’i değildir. Görünür fakat label alamayan küçük tag’in standard train’e sızmasını bu kural engeller.

## Concrete

Ana numune tek `concrete_00` instance’ıdır. Pore içleri ve üst-edge aggregate detayları aynı kimliği taşır; platen üstündeki arka plan kırıntıları class 1 değildir. Concrete visible bbox görüntü kenarında kırpılabilir; gerçek concrete kutularının yarıdan fazlası edge’e değdiği için edge contact reddedilmez.

## Neden union bbox değil?

- Birden çok tag arasındaki beton/plaka tek büyük kutuya girer.
- Occluder bir tag’i iki parçaya ayırırsa aradaki görünmeyen alan şişer.
- Tam örtülü fiziksel instance class-union içinde ayırt edilemez.
- En kötü instance’a göre güvenli partition verilemez.

## İnsan QC kapısı

Her yeni config/generator hash’inde 100 stratified kareyi iki kişi bağımsız kontrol etmelidir: iki kamera, iki şekil, dört ışık, 0/1/2–4/5+ tag, plate-gap ve üç partition. Normal train kapısı bbox yanlış/eksik oranı <%1 ve standard dizinde visible-unlabelled tag sızıntısı sıfırdır.
