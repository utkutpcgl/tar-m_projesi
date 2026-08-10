# Spot spray model kararı v2

## Kısa cevap

Bugün için en mantıklı kimyasal spot-spray PoC hattı:

```text
weed/crop detection veya instance
        ↓
kutu merkezi aksiyon adayı
        ↓
segmentasyon crop-maskesi / no-fire safety
        ↓
basit video onayı + fire-once
```

Keypoint etiketi sprey için şu aşamada maliyetini haklı çıkarmadı. Lazer veya
mekanik sökme için daha sonra stem/root/meristem keypoint gerekir.

[10 sayfalık sade ve görselli karar PDF'i](results/SPOT_SPRAY_MODEL_KARARI_V2.pdf)

## Aynı WSD testindeki sonuç

| Yaklaşım | Spot precision | Spot recall | Spot F1 | Sıkı stem F1 |
|---|---:|---:|---:|---:|
| Global segmentasyon, WSD zero-shot, 1024 | 0,2299 | 0,1661 | 0,1928 | 0,0205 |
| Global segmentasyon, WSD zero-shot, native 2048 tile | 0,2799 | 0,2187 | 0,2455 | 0,0398 |
| **Detection-only, kutu merkezi, 1024** | **0,7496** | 0,7822 | **0,7655** | **0,6604** |
| Pose modeli, kutu merkezi, 1024 | 0,7011 | **0,8067** | 0,7502 | 0,6559 |
| Pose modeli, yayıncı stem keypoint'i, 1024 | 0,6994 | **0,8067** | 0,7493 | 0,6591 |

Spot metriği, aksiyon noktasının bir GT weed bounding rectangle içine girmesidir.
Kutu toprak içerebildiği için bu iyimser bir sprey proxy'sidir; damla teması,
doz veya kill-rate değildir.

## Kıyasın kritik sınırı

Bu, saf mimari A/B değil; pratik **hedef-domain veri + model/task** A/B'sidir:

- detector 211 WSD train karesi ve 1.437 weed kutusu gördü;
- pose modeli aynı splitte 1.435 yayıncı stem noktası da gördü;
- global segmenter WSD'den sıfır kare gördü;
- WSD semantik maske yayımlamadığı için eşit hedef-eğitimli segmentasyon
  kolu bugün kurulamaz.

Dolayısıyla `0,7655 - 0,1928` farkını yalnız detection mimarisine yazmak
yanlış olur. Fakat kullanıcı kararı açısından çok net bir bulgudur: aynı
kamera/toprak/crop görünümünden gerçek etiket toplamak büyük değer taşıyor.

## Keypoint nereden geldi ve değdi mi?

Keypoint uydurulmadı. WSD yayıncısının
`labelled/points_labels` dosyaları, aynı satırdaki box etiketiyle eşlendi:

- train: 1.435 görünür weed stem noktası;
- validation: 1.549;
- test: 1.097;
- toplam 34 weed kutusunda geçerli nokta yoktu ve sıkı nokta metriğinden
  dışlandı.

Aynı pose modelinin kutu merkezi ile tahmin keypoint'i arasında spot F1
`0,7502 → 0,7493`, sıkı stem F1 `0,6559 → 0,6591` oldu. Sprey için
marj ihmal edilebilir; ana sorun weed'i doğru bulmak/sınıflandırmaktır.

## 28 px sonucu

Buradaki boyut, `1024` model girişinde `sqrt(GT weed kutu alanı)`dır;
gerçek bitki maskesi çapı veya fiziksel mm değildir.

| GT weed boyutu | n | Detection recall |
|---|---:|---:|
| `<14 px` | 65 | 0,5385 |
| `14–<28 px` | 874 | 0,7826 |
| `28–<56 px` | 162 | 0,8827 |
| `≥56 px` | 1 | ölçülemez; tek örnek kaçtı |

Boyut önemli; ama `28 px` tek başına yeterli koşul değil. Validation'da
yeniden seçilen eşikle, testteki `163` adet `≥28 px` hedefe koşullu
precision/recall/F1 `0,4415 / 0,8098 / 0,5714` oldu. Daha büyük hedeflerin
recall'ı iyileşse de arka plan, crop ve tekrar aksiyon FP'leri devam etti.

Native 2048 tiled segmentasyon F1'ı `0,1928 → 0,2455` yükseltti ama hedef-domain
detector seviyesine yaklaşmadı. Bu nedenle başarı koşulu:

1. hedeflerin yeterli **gerçek optik pikseli**;
2. doğru focus/DOF, shutter, motion blur ve aydınlatma;
3. aynı kamera/toprak/crop evresinden **hedef-domain gerçek veri**;
4. train–inference raster uyumu;
5. videoda birden çok kare onayı ve tek-sefer aksiyon

bileşimidir. Kamera tasarımında 28 px alt sınır hipotezi korunabilir; blur ve
perspektif marjıyla `42–56 px` daha güvenli başlangıç hedefidir.

## Gerçek veri toplama kararı

En yüksek ROI sırası:

1. weed + crop kutusu/instance ve ham video zamanı/kamera metadata'sı;
2. adil segmentasyon kıyası ve crop safety için 50–100 stratified maskelik
   küçük audit alt-kümesi;
3. ancak lazer/mekanik fazında stem/root/meristem keypoint;
4. sayısal tracking kazanımı için sınırlı ID-GT video audit'i.

Minimum ikna edici pilot 3–4 deploy-benzeri tarla/session içermeli; train,
validation ve tamamen untouched test session'ları ayrı tutulmalıdır. Mevcut
`%76,6` F1 gerçek veri toplamanın umut verici olduğunu, fakat `%95` saha
hedefine henüz yaklaşmadığımızı gösterir.

## Bugünün kararı

- **Kimyasal spot spray araştırma baseline'ı:** detection-only/instance +
  kutu merkezi, segmentasyon crop-safety/footprint.
- **Semantic segmentasyon tek başına:** WSD zero-shot'ta yeterli değil;
  hedef-domain maskeli pilot olmadan tamamen terk de edilmiyor.
- **Keypoint:** kimyasal sprey için ertelenir; lazer/mekanik için saklanır.
- **Sonraki P0 deney:** hedef-domain kutulu veri + native high-resolution
  train/inference; sonra basit video confirmation A/B.
- **Saha ateşlemesi:** NO-GO. Offline track P/R/F1 `≥0,95`, fiziksel
  deposition/kill ve crop injury kapıları ayrıca geçilmelidir.

## Exact artefaktlar

- Segmentasyon–detection receipt:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_segmentation_spot_spray_v1/segmentation_vs_detection_metrics.json`
- 28 px koşullu analiz:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_spot_success_conditions_v1/detection_gt_size_conditioned.json`
- Toplu paket:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/spot_spray_model_decision_v2/`

Ultralytics baseline AGPL-3.0 araştırma PoC kapsamındadır; ürün lisansı
ayrıca çözülmelidir.
