# Tarım Arazisi Gerçek + Kontrollü Sentetik Segmentasyon Benchmark'ı

Bu depo, RGB tarla görüntülerinde üç sınıflı semantik segmentasyon için
tekrarlanabilir bir benchmark içerir:

- `0`: arka plan / toprak
- `1`: hedef ürün
- `2`: hedef ürün dışındaki bitki örtüsü (yabancı ot)
- `255`: `ignore`; kayıp ve metrik hesaplarına katılmaz

Bu aşamanın amacı, gerçek veride dayanıklı bir ürün/yabancı ot segmentasyon
modeli seçmek ve ayrı, dondurulmuş A/B'lerle stock ve özel CropCraft
pilotlarının gerçek-domain etkisini ölçmektir. Sentetik veri ana corpus veya
gerçek testin yerine geçmez. Depth modeli bu faza bağlanmadı.

## Adil detection vs segmentation kararı — 2026-08-10

- [Önce bunu açın — 11 sayfalık sade ve görselli PDF](docs/results/FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf)
- [Exact metrikler ve deney sözleşmesi](docs/FAIR_DETECTION_SEGMENTATION_KARARI_V1.md)

Önceki WSD kıyası target-trained detector ile zero-shot segmenteri
karşılaştırdığı için mimari seçimde kullanılmadı. Yeni A/B'de iki kol da aynı
`1.407` gerçek PhenoBench train görüntüsünü, aynı bitki instance'larını, aynı
`1024 px / 50 epoch / seed 17` protokolünü gördü; confidence eşikleri yalnız
validation'da seçilip untouched testten önce kilitlendi.

Exact weed dokusuna tek-bitki/tek-atış metriğinde detection kutu-merkezi
precision/recall/F1 `%69,0/%60,9/%64,7`; segmentasyon maskesinin güvenli iç
noktası `%86,0/%64,9/%74,0` verdi. Eşleştirilmiş 403-kare bootstrap F1 farkı
`+9,3` puan, `%95 GA [+7,02, +11,56]`; segmentasyonun daha yüksek olma
olasılığı `1,00` oldu. Segmenter kutu-merkezi kontrolünün F1'ı `%62,1`
olduğundan kazanç yalnız farklı bir detector kutusundan değil, maskenin aksiyon
noktasını gerçek bitki dokusu içine taşımasından geliyor.

Bu nedenle genişletilebilir temel olarak **instance segmentation** seçildi.
Yine de test recall `%64,9`, `<14 px` recall `%26,4` ve yalnız tek training
seed'i vardır; UAV şeker pancarı sonucu nihai robot-kamera saha onayı değildir.
Deploy-benzeri session-ayrı test, tracking ve fiziksel nozul/kill/crop-injury
kapıları geçilmeden ilaç ateşleme yoktur.

## Tarihsel WSD sprey analizi — 2026-08-10

- [Önce bunu açın — 10 sayfalık sade PDF](docs/results/SPOT_SPRAY_MODEL_KARARI_V2.pdf)
- [Exact metrik, etiket kaynağı ve veri toplama kararı](docs/SPOT_SPRAY_MODEL_KARARI_V2.md)

Aynı WSD testinde hedef-domain kutularıyla eğitilmiş detection-only kutu
merkezi spot F1 `0,7655`; WSD'yi hiç görmemiş global segmentasyon 1024'te
`0,1928`, native 2048 tile'da `0,2455` verdi. Bu saf mimari A/B değil;
hedef-domain anotasyonu + task/model etkisidir. Pratik bulgu nettir: deploy
kamerasına benzer gerçek veri toplamak değerlidir.

WSD keypoint'leri uydurulmadı; yayıncı `points_labels` dosyalarından geldi.
Aynı pose modelinde kutu merkezi→keypoint spot F1 `0,7502→0,7493`, sıkı
stem F1 `0,6559→0,6591` oldu. Bu nedenle ilk kimyasal PoC'de etiket önceliği
weed/crop kutusu-instance'dır; keypoint lazer/mekanik fazına ertelenir.

`28–56 px` hedef recall'ı `0,8827` ile daha iyidir, fakat `≥28 px` hedeflere
koşullu test F1 yalnız `0,5714` kaldı. Sonuç: 28 px güçlü bir kamera alt-sınır
hipotezi, tek başına başarı garantisi değildir. P0; hedef-domain kutusu,
native high-resolution train/inference ve sonrasında basit video onayıdır.

## Detection-only spot-spray benchmark'ı — 2026-08-10

- [Önce bunu açın — 10 sayfalık basit PDF](docs/results/DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf)
- [Aranabilir exact sonuçlar ve kamera hesabı](docs/DETECTION_SPOT_SPRAY_BENCHMARK_V1.md)

Aynı WSD kareleri, tarih-ayrı split, 1024 px ve seed 17 ile eğitilen
detection-only modelin weed-kutusu merkez aksiyonu; iyimser spot-spray
proxy'sinde precision/recall/F1 `0,7496/0,7822/0,7655`, etiketli gövdeye
`≤%10` kutu diyagonali uzaklıktaki sıkı aksiyonda
`0,6452/0,6764/0,6604` verdi. Pose-keypoint kontrolünün F1'ları
`0,7493/0,6591` oldu. Detection-only ilk kimyasal spray PoC'si için daha basit
baseline seçildi; keypoint ana weed detection/classification darboğazını
çözmedi. Lazer/mekanik kol için stem/root/meristem keypoint yine gerekir.

`<14 / 14–28 / 28–56 px` detection-only spot recall'ları sırasıyla
`0,5385/0,7826/0,8827` oldu. Test weed kutularının 1024 girişte yalnız
`%14,8`i 28 px üstündedir. Kör 1536 inference, bu geometrik oranı `%79,0`a
çıkarırken spot F1'ı `0,7655→0,7179` düşürdü; bu nedenle dijital upscale
reddedildi. Native kamera GSD/FOV + focus/blur + eşleşen yüksek çözünürlüklü
eğitim birlikte test edilecek. `%95` F1 ve fiziksel spray kapıları geçilmedi.

## Noktasal müdahale PoC'si — 2026-08-08

- [Önce bunu açın — tek ve açıklamalı PDF](docs/results/BASLA_BURADAN_NOKTASAL_MUDAHALE_POC.pdf)
- [Aranabilir exact sonuçlar ve yöntem](docs/NOKTASAL_MUDAHALE_POC_V1.md)

768 uzman için raporlanan `%9,72`, botanik bitki-müdahale recall'ı değil;
`0,99` weed eşiği ve uncertainty/crop guard sonrası weed-pixel recall'ıydı.
Gerçek robot görüntüsünde uzman etiketli weed saplarıyla yeni bir
detection+keypoint PoC'si kuruldu. Mevcut en iyi 1536 fine-tune, ayrı çekim
tarihinde 10% weed-box-diagonal toleransında precision/recall/F1
`0,6335/0,7612/0,6915` verdi. `%95` offline perception kapısı geçilmedi;
bu nedenle saha ilaç/lazer ateşlemesi onaylı değildir.

Bu tarihsel keypoint PoC'sinin ardından 10 Ağustos'taki eşit koşullu A/B,
kimyasal spot spray için detection-only kutu-merkezinin yeterli araştırma
baseline'ı olduğunu gösterdi. Segmentasyon crop safety/context ve spray
footprint için korunur; lazer/mekanik noktasal aktüatör komutu ise instance
detection + stem/root keypoint'ten gelir.
Aynı-kare dedupe ve validation'da yeniden seçilen eşik, 1536 ham keypoint
F1'ını `0,6001 → 0,6915` yaptı. Video katmanı için kalibre zemin
koordinatında basit track, en az üç gözlem ve fire-once uygulaması eklendi;
ID-etiketli hedef videoda sayısal tracking kazanımı henüz ölçülmedi.

## Kamera, domain adaptation ve küçük-ot kararı — 2026-08-06

- [10 sayfalık kısa karar PDF'i](docs/results/BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf)
- [23 sayfalık açıklamalı detaylı PDF](docs/results/KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf)
- [Aranabilir exact sonuçlar ve yöntem](docs/KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md)

En büyük iki etken doğrulandı, fakat kamera ekseni ikiye ayrıldı: native
optik/GSD–focus–motion kalitesi ve modelin işlediği raster/token bütçesi.
Temiz sentetik holdout'ta 512→1024 dijital raster `+11,92` mIoU puanı verdi;
aynı kör upscale gerçek SugarBeets holdout'ta mIoU'yu `0,5772 → 0,3621/0,4282`
düşürüp crop riskini büyüttü. Bu nedenle interpolasyon reddedildi; gerçek
sensör detayı, native tiling ve train–inference raster uyumu birlikte
tasarlanmalıdır. `<14 px` weed proxy safe hit yalnız `%2,4` olduğundan yaklaşık
`28 px` eşdeğer-çap hedefi gerçek kamera bench'i için başlangıç hipotezidir.

Global generalist gate'i 512 kontrolü korudu. 768 px eğitim kolu ise iki seed
ortalamasında SugarBeets'i `+0,13010`, WeedMap'i `+0,00708` yükseltirken source
`-0,00546`, Sorghum `+0,00203`, CWFID `-0,04424` değiştirdi. Bu nedenle yalnız
doğrulanmış hedef robot kamera profilinde route edilen koşullu specialist'tir;
CWFID/UAV/genel kullanımda kontrol fallback kalır. SugarBeets müdahale
tanısında 768 kolu crop riskini `%4,41 → %1,45`, safe spray recall'ı
`%4,15 → %9,72` ve semantic-component hit'i `%4,92 → %15,28` yaptı; WeedMap
safe recall gerilediği için routing şartı önemlidir.

Hedef-benzer gerçek veri etkisi daha da büyüktür: strict-nested
`0/10/25/50/100/202` eğrisinde 10 Sorghum karesi seçildi ve iki seed paired
ortalamasında Sorghum `+0,17966` mIoU kazandı. Crop-row prior ana sınıflandırıcı
değil, opsiyonel safety veto'dur; SugarBeets'te pratik guard crop riskini
`%4,55 → %4,06` indirirken weed recall'ı `%7,83 → %6,60` düşürdü.

Self-contained yerel paket:
`/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_domain_report_v1/`.

## Bitki müdahalesi karar raporları — 2026-08-05

mIoU'yu robotun gerçek müdahale ihtiyacına çeviren yeni değerlendirme:

- [Anlaşılır detaylı PDF — önerilen ana rapor](ANLASILIR_DETAYLI_MUDAHALE_RAPORU.pdf)
- [Kısa karar PDF'i](docs/results/BASLA_BURADAN_MUDAHALE_RAPORU.pdf)
- [Aynı detaylı PDF'in sonuç klasörü kopyası](docs/results/DETAYLI_BITKI_MUDAHALE_RAPORU.pdf)
- [Aranabilir teknik metin eki](docs/INTERVENTION_EVALUATION_V1.md)

Önerilen ana PDF `48` sayfadır; her sayfa yalnız bir ana fikir veya bir saha
örneği taşır. Onlu contact-sheet kullanılmaz. Ground truth–tahmin panelleri
büyük gösterilir ve her örneğin altında “ne görüyoruz / hangi metrik önemli?”
yorumu bulunur. ROSE, WE3DS, SugarBeets, WeedMap, RiceSEG, etiketsiz BoniRob
video ve V11 sentetik unseen holdout örnekleri ayrı sayfalardadır. Sentetik
holdout güçlü/zor örnekleri ile 16-kare toplu performans özeti de ayrıca
verilir; gerçek saha kanıtı gibi yorumlanmaz.

Rapor; spot spray için weed üstü action point, crop false action ve footprint
hassasiyetini; mekanik/lazer için center/coverage proxy'lerini; küçük weed
apparent-size binlerini ve kamera GSD/focus/exposure planını birlikte verir.
Sonuç bir production/spray onayı değildir: root/crown/meristem, mm kalibrasyon
ve gerçek aktüatör outcome'u henüz yoktur. RiceSEG 604-kare paneli training
yollarıyla çakışmaz, fakat geçmiş specialist seçiminde kullanıldığı için
development/calibration'dır; untouched final test değildir.

Kısa özet: seen semantic weed-component hit `%66,4`, frozen safe-action hit
`%27,5`; `<14 px` weed hit `%24,1` ve safe hit `%2,0`'dır. Hedefe yakın
SugarBeets robot transferinde safe hit `%8,0`, crop-point hit `%18,2` olduğu
için saha gate'i geçilmedi. RiceSEG calibration crop IoU `%80,2`, weed IoU
`%22,2`, safe hit `%0,73`'tür. 2× software upscale küçük hit'i artırdı ancak
crop-point hatası ve latency'yi kötüleştirdiği için reddedildi.

Ham JSON, A/B makbuzları ve açıklamalı görsellerle self-contained yerel paket:
`data/processed/audits/crop_intervention_report_v1/`.

## Self-contained görsel sonuç paketi

Kabul edilmiş modelin validation, transfer, unseen gerçek video ve sentetik
stres sonuçları tek ve kolay okunan raporda toplandı:

- [9 sayfalık kısa sonuç PDF'i](docs/results/BASLA_BURADAN_SEGMENTASYON_SONUCLARI.pdf)
- [Model kimlikleri ve repo kapsamı](docs/results/README.md)

Yüksek çözünürlüklü tam galeri yerel veri diskinde tutulur; GitHub'a ham
veri, çalıştırma çıktıları veya model ağırlıkları yüklenmez.

Etiketli görseller `RGB | ground truth | model tahmini | safety`; etiketsiz
görseller `RGB | model tahmini | safety` düzenindedir. Yeşil hedef mahsul,
kırmızı diğer bitki/weed, mor ground-truth ignore'dur. Etiketsiz sayfalarda
renkler yalnız model tahminidir; accuracy/mIoU iddiası üretilmez.

## 2026-08-04 tarla-bağımsızlığı V10/V11 sonucu

V10 asset hattı 14 CC0 soil ve 14 HDRI ailesini train/synthetic-val/
synthetic-test arasında tamamen ayırır; soil moisture, tillage/clod makro
normal, güneş açısı/enerjisi, lokal gölge ve kamera takipli robot ışığını
randomize eder. 48/12/12 karelik pilot otomatik, manuel, radyometri ve ortak
ontoloji kapılarını geçti. Sentetik val/test gerçek model seçiminde kullanılmaz
ve ağırlığı tam `0,0`'dır.

Gerçek benchmark için önce field/session, sonra dataset macro alan hedef-ağırlıklı
scorer eklendi. Skor `%60` hedefe yakın domain, `%25` breadth ve `%15` gerçek
field/session alt-kuyruğudur; büyük datasetler satır veya piksel sayısıyla
diğer alanları bastıramaz. Mevcut source validation'daki 4/6 field overlap
açığı için resmî Sugar Beets 2016 kaynağından eğitimle çakışmayan 283 karelik
tek-oturum robot-camera holdout'u model çıktısı görülmeden donduruldu. Strict
v3 üç-seed seçimi bu paneli bir field/session ve bir dataset oyu olarak kullanır.

Ayrıca resmî CC-BY-SA-4.0 Sugar Beets 2016 BoniRob JAI-RGB akışından 31 adet
1296×966, yaklaşık 1 Hz unseen robot karesi alındı. Kabul edilmiş global fallback
tüm karelerde çalıştırıldı. Geniş yapraklı bitki sınırları iyi görünürken ince/
çimsi yapılarda crop-other/unknown karışması gözlendi. Kareler etiketsiz olduğu
için mIoU üretilmedi ve sekans model seçim skoruna sokulmadı. Ayrı 10:37
oturumundaki 283 resmî RGB/multiclass maske çifti ise full CRC, exact palette,
12-pair görsel ve 5.951 training + 20.765 prior-real leakage kapılarını geçti;
eğitime kapalı target-like holdout olarak kabul edildi. Tek tarla/tarih/oturum
olduğu için deployment kanıtı değildir. Tam durum,
artifact yolları ve yeniden çalıştırma kontratı tarihsel
[`docs/FIELD_ROBUSTNESS_VALIDATION_V10.md`](docs/FIELD_ROBUSTNESS_VALIDATION_V10.md)
raporundadır.

V10 seed-17 ekranı daha sonra tamamlandı. Birleşik gerçek skor
`+0,006884` ve target-like makro `+0,003331` artmasına karşın CWFID
`-0,048846`, mevcut gerçek çekirdek `-0,029437` ve en kötü alan
`-0,311180` geriledi; aday paired non-inferiority'de reddedildi. Bağımsız
uç koşulları azaltıp `clear_day / overcast_moist / low_sun /
robot_light_low_ambient` profillerini kullanan V11 takip hattında R1 iki
üretim kapısını, tam R2 iki train radyometri kapısını kaybetti. Yalnız bu
iki outlier'ı karantinaya alan R2Q türevi 78/16/16 kareyle kabul edildi.
Ancak V11-R2Q model adayı gerçek seçim skorunu `-0,010073`, hedef makroyu
`-0,015962` düşürdü ve 111 alanın 30'unda hard regresyon sınırını kaybetti.
Seed 29/43 açılmadı; kabul edilmiş global seed-43 fallback değişmedi.
Tam gate defteri ve domain tablosu
[`docs/FIELD_ROBUSTNESS_VALIDATION_V11.md`](docs/FIELD_ROBUSTNESS_VALIDATION_V11.md)
içindedir.

Sentetik çeşitliliğin direct-mixture yerine kısa real-only recovery sonrasında
korunup korunmadığı da eş-hesap kontrolle sınandı. İki kol aynı 4.066 gerçek
train kaydı, aynı 2×3.600 draw, aynı örnek/RNG akışı ve fresh optimizer aldı.
Challenger primary/target/tail skorlarını `+0,009635/+0,006222/+0,012870`
artırdı; fakat CWFID `-0,055998`, real-core field macro `-0,026588` ve
CropAndWeed `-0,012004` geriledi. 111 field/session'ın 23'ü hard sınırı aştı;
target ve generalist confirmation kapıları reddedildi. Seed 29/43 açılmadı,
global fallback değişmedi. Ayrıntılar
[`docs/SIMULATION_DIVERSITY_REAL_RECOVERY_V1.md`](docs/SIMULATION_DIVERSITY_REAL_RECOVERY_V1.md)
içindedir.

Farklı dağılımdaki görsel çıktılar ayrıca görünür hale getirildi. CC-BY-4.0
FarmBot Soy release'inden gün 1-20'yi kapsayan 40 model-unseen near-nadir
kare, Naïo Oz resmî videosundan 10 model-unseen OOD kare ve önceki 31-kare
BoniRob sekansı etiketsiz nitel galeride yer alır. SugarBeets session holdout,
RiceSEG country transfer, WeedMap UAV ve V11-R2Q asset/seed-ayrık val/test için
RGB-ground-truth-prediction-safety best/worst sayfaları üretildi. RiceSEG'de
global fallback ile kabul edilmiş metadata-routed specialist ayrı ayrı
gösterilir. Etiketsiz ve sentetik panellerin seçim ağırlığı `0,0`'dır. Galeri,
açık hata listesi ve doğrudan dosya yolları
[`docs/UNSEEN_VISUAL_GALLERY_V1.md`](docs/UNSEEN_VISUAL_GALLERY_V1.md)
içindedir.

## Tamamlanan benchmark sonucu

Gerçek-veri aday taraması, SorghumWeed ek gerçek veri fazı, 100 karelik
CropCraft pilotu, eşit-bütçeli sentetik A/B ve seed 17/29/43 eğitim-bütçesi
doğrulaması tamamlandı. Erişilebilir/test edilen tariflerde robust semantik
kazanan:

```text
DINOv2-Small FPN + factorized crop-conditioned head
backbone: stage 4 trainable
conditioning dropout: 0.5
train: real core + 202 Sorghum + %10 CropCraft sampler exposure
checkpoint: epoch 15, median robust seed 43
```

Yeni tarifin üç-seed sonucu source mIoU `0,813674 ± 0,001235`, CWFID mIoU
`0,569446 ± 0,016727` ve Sorghum validation mIoU
`0,838798 ± 0,005602`'dir. Eşit 28.800-example epoch-8 A/B'de %10
CropCraft kolu real+Sorghum kontrole göre robust CWFID mIoU'yu ortalama
`+0,017412` artırdı ve 3/3 seed kazandı. %25 seed-17'de daha kötüydü;
sentetik-only model Sorghum'a genellenmedi.

Sonraki özel-asset çalışmasında 15 erken-dönem sorgum modeli, dört yabancı ot
ailesi, 16 tarla artığı ve üçer CC0 soil/HDRI ailesi içeren 100-karelik pilot,
stock `%10` kola karşı aynı epoch-8 bütçesinde sınandı. Robust minimum mIoU
`0,541634 → 0,561939` (`+0,020305`) ve 3/3 seed galibiyetiyle özel asset gate'i
geçti. Kaynak ve Sorghum mIoU ortalamaları sırasıyla `-0,005930` ve
`-0,005175` geriledi; ikisi de önceden tanımlı `0,01` non-inferiority sınırı
içindedir. Ayrıntılar
[`docs/SIMULATION_ASSET_QUALITY_REPORT.md`](docs/SIMULATION_ASSET_QUALITY_REPORT.md)
içindedir. Bu epoch-8 asset seçimi, aşağıdaki tarihsel epoch-15 checkpoint'ini
eşit-bütçeli confirmation olmadan otomatik değiştirmez.

V2 kontrolü daha sonra 15 bağımsız crop geometrisi × 3 albedo fenotipi ve dört
resmi Poly Haven CC0 kaynağından 27 texture-backed weed ile genişletildi.
Eksik materyalli iki ara paket reddedildikten sonra R3 static, smoke, manuel,
100-kare pilot ve leakage kapılarını geçti. V2 özel kontrole karşı robust mIoU
`0,561939 → 0,578953` (`+0,017015`) ve 3/3 seed galibiyetiyle v3 asset gate'i
geçti; kaynak ve Sorghum ortalamaları da sırasıyla `+0,000936` ve `+0,003643`
yükseldi. Development safety pass rate yalnız `0,333333` olduğundan sonuç
semantik araştırma seçimi, saha/püskürtme onayı değildir. Ayrıntılar
[`docs/SIMULATION_ASSET_QUALITY_REPORT_V3.md`](docs/SIMULATION_ASSET_QUALITY_REPORT_V3.md)
içindedir.

CropAndWeed'in 4.584 kalite-kapılı gerçek karesi ayrı bir dondurulmuş
ablation'da sınandı. `%10/%20` eşit-bütçeli ikame kolları CropAndWeed
mIoU'yu `+0,027100 / +0,021255` artırdı; fakat worst-domain CWFID'yi
`-0,050332 / -0,034447` düşürdü. Eski kaynakların mutlak draw sayısını
koruyan additive takip de robust gate'i geçmedi (`-0,059306` vs v3). Bu
nedenle kabul edilmiş v3 kontrol korunur; ayrıntılar
[`docs/REAL_DATA_COVERAGE_AUDIT_V2.md`](docs/REAL_DATA_COVERAGE_AUDIT_V2.md)
içindedir.

CC-BY-4.0 Rice Seedling and Weed verisinin 224 karosu da kalite kapılarını
geçti. Yayındaki 224 karonun yalnızca 28 ana fotoğraftan gelmesi nedeniyle
tamamı tek `train` oturumunda tutuldu; rastgele karo split'i yapılmadı. Ham
`0` sınıfı, yayın oranları ve görsel sınır kanıtıyla `ignore` olarak
korundu. `%2,5` global karışım robust mIoU'yu `+0,008422` artırdı fakat
CropAndWeed non-inferiority sınırını `0,000125` ile kaçırdı; `%5` kol ise
CWFID nedeniyle robust metriği `-0,005679` düşürdü. İki kol da reddedildi,
v3 kontrol korundu. Rice'a maruz kalmamış kontrolün zero-shot mIoU'su
`0,311910` oldu; bu, sonraki sentetik deneyi paddy su/yansıma ve erken
rice/Sagittaria assetlerine yönlendiriyor. Ayrıntılar
[`docs/REAL_DATA_RICE_PADDY_AUDIT_V1.md`](docs/REAL_DATA_RICE_PADDY_AUDIT_V1.md)
içindedir.

Bu açığı hedefleyen Paddy R5 paketi 60 rice modeli/20 bağımsız geometri,
36 paddy weed, üç ıslak PBR, üç HDRI ve sığ-su profiliyle static, smoke,
100-kare pilot, manuel RGB-mask, leakage ve gerçek-domain kapılarını geçti.
`%5` dryland V3 + `%5` paddy R5 tarifi, v3 kontrole karşı seed 17/29/43'te
3/3 robust galibiyet ve ortalama `+0,048805` beş-domain worst-case mIoU
sağladı. Bu development seçiminin temsilci epoch-8 seed-43 checkpoint'i
`data/runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt`
ve SHA-256'sı
`b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f`'dir.
Bu seçim aşağıdaki tarihsel epoch-15 checkpoint'ini otomatik değiştirmez ve
external-test/saha onayı değildir.

Soy için daha ileri asset optimizasyonu da tamamlandı. 60 crop modeli/20
bağımsız geometri/5 evre/3 fenotip ve 53 weed içeren V5 R3 paketindeki
semantic-alpha sorunu giderildi; tamamlayıcı yüksek-weed/düşük-crop V6 R5
pilotu static, kompozisyon, manuel görsel ve 12.618 gerçek referansa karşı
leakage kapılarını geçti. Ancak dengeli 45 V5 + 45 stress draw'lı aday
GrowingSoy'u `+0,100142` yükseltirken CWFID'yi `-0,130207` ve Rice/robust
minimumu `-0,029398` düşürdü. Model gate'i reddedildi; büyük batch ve
seed-29/43 confirmation açılmadı, kabul edilmiş paddy kontrolü korundu.
Asset kalitesi ile ortak-model kabulünü ayıran kanıt zinciri
[`docs/SIMULATION_SOY_ASSET_QUALITY_REPORT_V5.md`](docs/SIMULATION_SOY_ASSET_QUALITY_REPORT_V5.md)
içindedir.

Gerçek-veri coverage takibi daha sonra GrowingSoy, DeBlurWeedSeg ve WeedMap
ile genişletildi. GrowingSoy'un `%5/%10` kolları kendi alanını
`+0,284888 / +0,296242` artırdı; fakat CWFID ve/veya CropAndWeed/Rice
non-inferiority kapılarını geçemedi. DeBlurWeedSeg tek-saha tanısında kabul
edilmiş kontrolün sharp→motion-blur mIoU farkı üç seed ortalamasında
`-0,144855` oldu; bu set model seçmedi.

WeedMap'in 4,48 GB arşivi disk bütçesi doğrulandıktan sonra research-only
alana indirildi. Arşivdeki ters validity-mask açıklaması ve `10000=crop`
etiket anomalisi 970 tile'ın tamamında gözlenen RGB/renk-label kanıtıyla
çözüldü; sabit `%5` valid-pixel tabanından sonra 424 train + 95
development-only tile kalite ve sızıntı kapılarını geçti. `%2,5/%5` katkı
WeedMap mIoU'yu `+0,160505 / +0,177702` yükseltti, fakat CWFID'yi
`-0,050411 / -0,060024` düşürdü; iki aday da reddedildi ve kabul edilmiş
paddy kontrolü korundu. Tobacco Aerial'ın 2.520 patch'i de campaign-ayrık
kalite gate'ini geçti; `%4,7619` additive aday Tobacco'da küçük kazanımına
rağmen CWFID/Rice/CropAndWeed ve macro non-inferiority kapılarında kaldı.

CC-BY-4.0 WeedyRice-RGBMS-DB'nin 734 RGB+binary maskesi archive, metadata,
piksel, uçuş-ayrık split, görsel QC ve 15.857 gerçek referansa karşı sızıntı
kapılarını geçti. Kaynak `0` etiketi cultivated rice ile arka planı
ayırmadığından 487 Thoaison karesi yalnız partial-label train adayıdır ve
ortak eğitime kilitlidir. Ayrı 247-kare Longxuyen uçuşundaki üç-seed zero-shot
tanıda semantic argmax IoU `0,597835` görünse de specificity `0,068876` ve
predicted-positive oranı `0,966940` oldu; source-frozen weed IoU yalnız
`0,000064`'tür. Mevcut model cultivated-rice/weedy-rice ayrımını geçemedi ve
değiştirilmedi. Ayrıntılar
[`docs/REAL_DATA_WEEDY_RICE_UAV_AUDIT_V1.md`](docs/REAL_DATA_WEEDY_RICE_UAV_AUDIT_V1.md)
içindedir.

CC-BY-4.0 CamelinaWeed v1'in 69,01 GB bölünmüş arşivi merkez-dizin + HTTP
Range ile tarandı; yalnız COCO-referenced 1.120 JPEG ve 12 JSON indirildi.
1.097 pozitif içeren görüntü içerik, tam JPEG decode, poligon, konum-ayrık
999 Thessaloniki train-adayı / 98 Chalkidiki calibration, 21 örnekli görsel
ve 16.591 gerçek referansa karşı sızıntı kapılarını geçti. Crop/background
exhaustive olmadığı için tüm poligon-dışı pikseller `ignore` ve veri ortak
eğitime kilitlidir. Ayrıntılar
[`docs/REAL_DATA_CAMELINAWEED_AUDIT_V1.md`](docs/REAL_DATA_CAMELINAWEED_AUDIT_V1.md)
içindedir.

Güncel hash-kilitli coverage matrisi 19 veri kümesi / 21.048 kabul edilmiş
gerçek kayıt bulur. Bunların 18.993'ü ortak-semantik uyumlu, 2.055'i
partial-training-locked track'tedir. Matris, gerçek train satırı ile ortak
loss'a gerçekten açılabilen satırı ayırır; kalite-kapılı RiceSEG de artık bu
envanterdedir. Yeni 283 BoniRob karesi yalnız bir capture-group artırır.
Ayrıntılar
[`docs/REAL_DATA_COVERAGE_MATRIX_V2.md`](docs/REAL_DATA_COVERAGE_MATRIX_V2.md)
içindedir.

Sentetik portföyün konsolide v8 auditi beş önceki asset aşamasının 5/5 kalite
gate'ini geçtiğini, fakat yalnız dryland V3 ve paddy R5 aşamalarının ortak
modelde kabul edildiğini doğruladı. RiceSEG geldikten sonra ölçülen en büyük
eksik faktör için 48 model/24 geometri ve dört geç-üreme evreli R3 paketi
geliştirildi. Asset, smoke ve 100-kare pilot kapıları geçti; `%2,5` eşit
bütçeli model kolu RiceSEG'i `+0,141180`, saf reproductive alt-kümeyi
`+0,101863` artırdı, fakat CWFID/CropAndWeed'i `-0,039529 / -0,016026`
düşürdüğü için reddedildi. Büyük batch ve 3-seed confirmation açılmadı.
Ayrıntılar
[`docs/SYNTHETIC_ASSET_OPTIMIZATION_STATUS_V8.md`](docs/SYNTHETIC_ASSET_OPTIMIZATION_STATUS_V8.md)
ve
[`docs/SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md`](docs/SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md)
içindedir.

Çok-ülkeli RiceSEG'in pinli `1a891ced...` release'i indirildi ve doğrulandı.
3.078 RGB/maske çiftinin tamamı decode/palette/pairing/CRC, 19-subdataset
görsel inceleme ve 17.688 önceki gerçek görüntüye karşı sızıntı kapılarından
geçti. Aynı train rolündeki tek çatışmalı yakın kopya upstream'de korundu
ama eğitimden karantinaya alındı. Net coverage split'i `2.473 train / 604
external_calibration`; ayrı temiz country-transfer görünümü `1.823 -> 1.254`.
Bu iki split protokolü birleştirilmez. Ardından gerçek RiceSEG katkısı
üç dondurulmuş seed-17 ekranında sınandı. Hedef RiceSEG/reproductive
mIoU her tarifte yaklaşık `+0,32 / +0,37` arttı; fakat global karışımlar
mevcut-domain kapılarını geçmedi. En kontrollü sabit-3.600-draw exact-index
kol, eski 3.510 pozisyonu epoch başına birebir koruyup CWFID kapısını geçti;
source/Sorghum/CropAndWeed `-0,012139 / -0,023556 / -0,025475` geriledi.
Bu nedenle kabul edilmiş global model değişmedi; RiceSEG specialist/adapter
girdisi olarak kabul edildi. Ayrıntılı karar
[`docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md`](docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md)
içindedir. Yeniden doğrulama komutları:

```bash
.venv/bin/python scripts/acquire_riceseg.py
.venv/bin/python scripts/inspect_riceseg_release.py
.venv/bin/python scripts/finalize_riceseg_quality_gate.py
```

Ayrıntılar
[`docs/REAL_DATA_RICESEG_PREFLIGHT_V1.md`](docs/REAL_DATA_RICESEG_PREFLIGHT_V1.md)
ve [`docs/REAL_DATA_COVERAGE_MATRIX_V1.md`](docs/REAL_DATA_COVERAGE_MATRIX_V1.md)
içindedir.

Global girişimi parametre izolasyonuyla çözen crop-routed RiceSEG specialist
daha sonra kabul edildi. Sabit 30.240-draw seed-17 ekranında `%2,38/%10/%25/
%50` oranları karşılaştırıldı; full RiceSEG `%50` ile `0,648486`'ya çıksa da
robust early/full/reproductive minimumunu `%2,38` kazandı. Paired seed
17/29/43 confirmation'da specialist'in early/full/reproductive ortalamaları
`0,522806 / 0,617404 / 0,413770`, fallback'e göre ortalama farklar
`+0,156047 / +0,328889 / +0,382517` ve robust galibiyet `3/3` oldu. Rice
temsilcisi seed 29, SHA-256
`ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7`;
non-rice/unknown route mevcut seed-43 fallback'i aynı hash'le korur. Route
yalnız dışarıdan kesin `crop_id=12 / Oryza sativa` metadata'sıyla açılır;
otomatik görsel router veya saha onayı değildir. Ayrıntılar
[`docs/REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`](docs/REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md)
içindedir.

RiceSEG sonrası güncel kaynak taramasında BAWSeg'in resmî IEEE DataPort
artifact'i görünür oldu: dört sezon/iki ticari barley paddock, beş bant ve
dense crop/weed/other etiketi bildiriyor. Kamu/content-ID ve disk kapısı
geçti; `7.5 GB` görünen ZIP için HDD'de yaklaşık 277 GiB boşluk var. Ancak indirme
`Subscription Required` durumunda ve paket lisansı henüz okunamadı. Bu
nedenle BAWSeg henüz coverage/model havuzuna eklenmedi; kimlik doğrulamalı
indirmeden sonra extraction öncesi merkez-dizin, tam CRC/iç SHA ve lisans
kapıları çalışacak. Ayrıntılar
[`docs/REAL_DATA_BAWSEG_PREFLIGHT_V1.md`](docs/REAL_DATA_BAWSEG_PREFLIGHT_V1.md)
içindedir.

Tarihsel epoch-15 benchmark checkpoint'i ve SHA-256:

```text
data/runs/simab_real_sorghum_cropcraft10_e15_v1/seed_43/last.pt
97c81bcda10f1e7d01cb03e63af411b9ad7b65d202d72880efe702ff5eca092e
```

Tarif/checkpoint kilitlendikten sonra Sorghum resmi 25-kare external test'i
yalnız bir kez açıldı: mIoU `0,834852`, crop IoU `0,795266`, weed IoU
`0,716867`. Threshold sweep yapılmadı. Aggregate crop-spray risk
`0,000340` olsa da kare-başı p99 `0,043382` ve ihlal oranı `0,04` ile safety
kapısı kaldı.

Bu nedenle model **saha/ilaçlama onaylı değildir**. Sorghum testi tek isimli
çiftlikten gelir; unseen-field kanıtı değildir. Sonuç global SOTA değil,
yalnız erişilebilir/test edilen adaylar içindeki en iyi robust semantik
araştırma modelidir. Ayrıntılar
[`docs/SIMULATION_ABLATION_REPORT.md`](docs/SIMULATION_ABLATION_REPORT.md),
korunan eski real-only faz ise
[`docs/BENCHMARK_REPORT.md`](docs/BENCHMARK_REPORT.md) içindedir.

## Hızlı başlangıç

Python 3.10+ ve CUDA destekli PyTorch gerekir. Eğitim ve checkpoint
değerlendirmesi CPU üzerinde çalıştırılmayı reddeder.

```bash
python3 -m venv --system-site-packages .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e '.[dev,export]'
.venv/bin/python -c 'import torch; print(torch.__version__, torch.cuda.is_available())'
.venv/bin/python -m pytest
```

Veriler bu makinede `data` sembolik bağlantısı üzerinden
`/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data` altında tutulur. Başka bir
makinede `configs/datasets.yaml` içindeki `data_root` ile eğitim ve benchmark
YAML dosyalarındaki mutlak yollar birlikte güncellenmelidir. İndirmeden önce:

```bash
.venv/bin/agri-seg disk-check
```

Kontrol, kayıtlı arşivlerin toplamına ek olarak 20 GiB boş alan arar. Tekil bir
indirme de arşiv açma ve checkpoint alanı için koruma payı bırakır.

## Veri kümeleri, roller ve lisanslar

Kaynak URL, beklenen arşiv boyutu ve mevcutsa checksum değerlerinin kanonik
kaydı [`configs/datasets.yaml`](configs/datasets.yaml) dosyasındadır.

| Veri kümesi | Benchmark rolü | Kanonik split | Örnek | Lisans / kısıt |
|---|---|---:|---:|---|
| [PhenoBench](https://www.phenobench.org/dataset.html) | Araştırma-maksimum eğitim | yayıncı mekânsal train 1.407 / val 772 | 2.179 | CC-BY-NC-SA-4.0 |
| [ACRE](https://zenodo.org/records/8102217) | Çekirdek eğitim | oturum-ayrık train 600 / val 200 / test 200 | 1.000 | CC-BY-4.0 |
| [WeedsGalore](https://doi.org/10.5880/GFZ.1.4.2024.001) | Yardımcı eğitim | yayıncı mekânsal train 104 / val 26 / test 26 | 156 | CC-BY-4.0 |
| [WE3DS](https://zenodo.org/records/7457983) | Çekirdek eğitim | tarih/oturum-ayrık train 1.018 / val 389 / test 394 | 1.801 | CC-BY-4.0 |
| [ROSE](https://data.mendeley.com/datasets/x8brgg2j28/2) | Araştırma-maksimum eğitim | train 735 / val 250 / test 250 | 1.235 | kayıt CC-BY-4.0; gömülü içerik ODbL incelemesi |
| [CWFID](https://github.com/cwfid/dataset) | İlan edilmiş bilinmeyen-ürün kalibrasyonu | `external_calibration` 60 | 60 | yalnız ticari olmayan araştırma |
| [Sugar Beets 2016](https://www.ipb.uni-bonn.de/data/sugarbeets2016/index.html) | Eğitime kapalı robot-camera development holdout | tek tarla/tarih/oturum `external_calibration` 283 | 283 RGB+multiclass maske | CC-BY-SA-4.0; V10/V11 karşılaştırmasında tüketildi, deployment kanıtı değil |
| [Carrot-Weed](https://github.com/lameski/rgbweeddetection) | Kilitli dış test | `external_test` 39 | 39 | yalnız ticari olmayan araştırma |
| [EWIS1](https://data.mendeley.com/datasets/6j5pxgf437/1) | Kilitli dış test | 39 çekim grubunda `external_test` | 88 | CC-BY-4.0 |
| [SorghumWeed](https://data.mendeley.com/datasets/y9bmtf4xmr/1) | Yeni gerçek train / development / kilitli test | resmi 202 / 25 / 25 | 252 | CC-BY-4.0; tek isimli çiftlik |
| [CropAndWeed](https://github.com/cropandweed/cropandweed-dataset) | Research-max gerçek-veri ablation | oturum-ayrık train 3.667 / calibration 917 | 4.584 kabul / 8.034 kaynak | yalnız ticari olmayan araştırma; yeniden dağıtım yok |
| [Rice Seedling and Weed](https://doi.org/10.6084/m9.figshare.7488830.v5) | Paddy/rice train-only katkı ablation | tek tarla/oturum; 28 ana fotoğrafın 224 karosu yalnız train | 224 | CC-BY-4.0 |
| [GrowingSoy](https://github.com/raulsteinmetz/soy-segmentation-ds) | Boylamsal gerçek-veri ablation | trajectory B train 541 / trajectory A calibration 459 | 1.000 | MIT |
| [DeBlurWeedSeg](https://doi.org/10.17632/k4gvsjv4t3.1) | Sharp/motion-blur geliştirme tanısı | publisher-test; 100 sharp + 100 blur, tek capture group | 200 | MIT; train/val kullanılmadı |
| [WeedMap](https://doi.org/10.3929/ethz-c-000788571) | UAV gerçek-veri ablation | map 000/001/002/004 train 424 / map 003 calibration 95 | 519 kabul / 970 RedEdge kaynak tile | In Copyright - Non-Commercial Use Permitted |
| [Tobacco Aerial](https://data.mendeley.com/datasets/5dpc5gbgpz/2) | Campaign-ayrık gerçek-veri ablation | campaign 2/3/5/6/7/8 train 1.536 / campaign 1/4 calibration 984 | 2.520 | CC-BY-4.0 |
| [WeedyRice-RGBMS-DB](https://data.mendeley.com/datasets/vt4s83pxx6/1) | Partial-label train adayı + uçuş-ayrık binary tanı | Thoaison 487 train-kilitli / Longxuyen 247 calibration | 734 RGB+maske | CC-BY-4.0; kaynak negatif sınıf ortak crop/background değildir |
| [RiceSEG](https://huggingface.co/datasets/PheniX-Lab/RiceSEG) | Çok-ülkeli full-semantic rice specialist + development | kalite-kapılı coverage: 2.473 train / 604 calibration; ayrı country-transfer: 1.823 / 1.254 | 3.077 uygun / 3.078 release | global mix reddedildi; metadata-routed specialist 3-seed kabul edildi; research-only license reconciliation |
| [CropCraft](https://github.com/Romea/cropcraft) | Stock sentetik ablation | scene-ayrık 80 / 20 pilot | 100 | kod Apache-2.0; bundled asset kapsamı nedeniyle research-only |
| CropCraft özel erken-sorgum paketi | Asset-quality ablation | scene-ayrık 80 / 20 pilot | 100 | prosedürel geometri CC0-1.0; Poly Haven girdileri CC0-1.0 |
| CropCraft texture-backed v3 paketi | V2'ye karşı asset-quality ablation | scene-ayrık 80 / 20 pilot | 100 | prosedürel crop + dört resmi Poly Haven bitki kaynağı; CC0-1.0 |

`real_core_final.csv`, beş eğitim kaynağını birleştirir: train 3.864,
val 1.637 ve test 870 olmak üzere 6.371 gerçek görüntü. Araştırma-only
robustness benchmark'inin kanonik manifesti budur. Fiziksel olarak ticari
kullanıma izinli işaretlenmiş ACRE + WeedsGalore + WE3DS alt kümesi
`commercial_core_we3ds.csv` içinde train 1.722 / val 615 / test 620, toplam
2.957 örnektir. CWFID final test değil, yalnız `external_calibration` rolündedir;
Carrot-Weed ve EWIS1 kilitli dış testlerdir.

WE3DS split'i tarih/oturum ayrıdır fakat parsel ayrıklığı kanıtlanmış
değildir. ROSE 2019 train/val robotları ayrı olsa da Montoldre sahasını
paylaşır. PhenoBench ve WeedsGalore holdout'ları da tek başına yeni-oturum
genellemesi kanıtı değildir. `all_roles_audit.csv`, eğitim/geliştirme/kilitli
test rollerindeki 6.558 görüntüyü ortak sızıntı denetimine sokar.

GrowingSoy, WeedMap ve Tobacco Aerial artık ertelenmiş aday değildir: ayrı,
dondurulmuş ablation'larda sınandılar ve ortak-model kapısında reddedildiler.
DeBlurWeedSeg yalnız development stress tanısıdır. Weedy Rice kalite gate'ini
geçmiştir, fakat ontolojisi partial-label loss gerektirdiği için ortak-model
eğitimine açılmamıştır. SugarBeets2016 artık 283-kare resmî
multiclass holdout olarak kalite kapılarını geçmiştir; korelasyon nedeniyle
tek field/session oyudur ve V10/V11 development karşılaştırmasında
tüketilmiştir. VegAnn vegetation-only partial-label loss gereksinimiyle
ertelenmiştir. RiceSEG release ve kalite
kapılarını geçmiştir. 2.473 train adayının iki additive ve bir exact-index
fixed-compute ortak-model ekranı tamamlandı; hepsi mevcut-domain
non-inferiority nedeniyle reddedildi. 604 calibration satırı eğitime
sokulmadı; country-transfer görünümü de coverage split'iyle birleştirilmedi.
Ardından ayrı crop-routed `%2,38095` specialist paired üç-seed kapısını
geçti; global fallback değişmedi. Otomatik router/deployment ayrı kalır.
Bu kaynakların hiçbiri ayrı, hash'li ablation olmadan ana corpusa eklenmez.

`commercial_allowed` manifest alanı ve `commercial_only: true` filtresi,
yanlışlıkla ticari olmayan veriyi eğitime sokmayı önleyen teknik bir kontroldür;
hukuki görüş değildir. Birincil `base_real_final.yaml` PhenoBench ve ROSE
içerdiği için araştırma amaçlıdır. `base_commercial_we3ds.yaml` yalnız eğitim
verisi kapsamını temiz tutar. CWFID ticari olmayan olduğundan onunla kalibre
edilen checkpoint de ticari-temiz sayılamaz; ticari hat için ayrı source-only
seçim protokolü gerekir. Veri, kod ve ön-eğitim ağırlığı lisansları dağıtımdan
önce ayrı ayrı incelenmelidir.

### İndirme ve dönüştürme

```bash
.venv/bin/agri-seg download phenobench
.venv/bin/agri-seg download acre
.venv/bin/agri-seg download weedsgalore
.venv/bin/agri-seg download we3ds
.venv/bin/agri-seg download rose
.venv/bin/agri-seg download cwfid
.venv/bin/agri-seg download carrot_weed
.venv/bin/agri-seg download sorghum_weed
.venv/bin/agri-seg download cropandweed_annotations
.venv/bin/agri-seg download cropandweed_images1of4
.venv/bin/agri-seg download cropandweed_images2of4
.venv/bin/agri-seg download cropandweed_images3of4
.venv/bin/agri-seg download cropandweed_images4of4
.venv/bin/agri-seg download rice_seedling_weed
.venv/bin/agri-seg download cropcraft

.venv/bin/agri-seg convert phenobench
.venv/bin/agri-seg convert acre
.venv/bin/agri-seg convert weedsgalore
.venv/bin/agri-seg convert we3ds
.venv/bin/agri-seg convert rose
.venv/bin/agri-seg convert cwfid
.venv/bin/agri-seg convert carrot_weed
.venv/bin/agri-seg convert sorghum_weed
.venv/bin/agri-seg convert cropandweed \
  --gate-config configs/data/cropandweed_real_gate_v1.yaml
.venv/bin/agri-seg convert rice_seedling_weed

.venv/bin/agri-seg combine-manifests \
  data/processed/manifests/phenobench.csv \
  data/processed/manifests/acre.csv \
  data/processed/manifests/weedsgalore.csv \
  data/processed/manifests/we3ds.csv \
  data/processed/manifests/rose.csv \
  --output data/processed/manifests/real_core_final.csv

.venv/bin/agri-seg combine-manifests \
  data/processed/manifests/acre.csv \
  data/processed/manifests/weedsgalore.csv \
  data/processed/manifests/we3ds.csv \
  --output data/processed/manifests/commercial_core_we3ds.csv
```

EWIS1 iki bileşenden oluşur ve ikisi de tamamlanmadan dönüştürülmemelidir:

```bash
.venv/bin/agri-seg download ewis1_images
.venv/bin/agri-seg download ewis1_masks
.venv/bin/agri-seg convert ewis1
```

WeedsGalore dönüştürücüsü RGB bantlarını kayıplı 8-bit görüntüye çevirmeden
16-bit `.npy` olarak korur. ACRE'deki güvenilmeyen/bilinmeyen veya çakışan
poligonlar ve CWFID'deki türü belirtilmemiş bitki pikselleri `255` yapılır.
WE3DS'de 2.568 kaynaktan hedef ürün bulunmayan 765 ve birden fazla hedef
ürün içeren 2 görüntü fail-closed olarak dışlanır. ROSE resmi v2 paketindeki
Bipbip/Haricot anomalisinde 15 maskesiz görüntü ile 15 orphan/misplaced maize
maskesi yalnız tam dosya-kökü kesişimiyle dışlanır; konumsal eşleştirme yapılmaz.
ROSE renkleri `black=background`, `white=crop`, `pink=weed` ve bitki görünümü
programatik/görsel olarak doğrulanan `orange=other_vegetation/weed` biçiminde
normalize edilir.

CropAndWeed dönüştürücüsü hedef kimliğini tahmin etmez: semantik maskede tam
bir resmî hedef ürün grubu bulunan 4.584 kareyi kabul eder; hedef ürünsüz 3.341
ve birden çok hedef ürünlü 109 kareyi dışlar. Ham `255` belirsiz vegetation ve
resmî crop/weed üst ontolojisinin dışındaki türler `ignore` olur. Annotation-only
MILP ile model eğitiminden önce dondurulan 350/87 oturum, 3.667 `train` ve 917
`external_calibration` görüntüsü üretir. Tam coverage, lisans, split ve QC
raporu [`docs/REAL_DATA_COVERAGE_AUDIT_V2.md`](docs/REAL_DATA_COVERAGE_AUDIT_V2.md)
içindedir.

Rice dönüştürücüsü 224/224 eşleşmeyi, `912×1024` boyutu, ham
etiket kümesini ve aggregate piksel sayılarını fail-closed doğrular. Ham
`0` unlabeled bitki sınırıdır ve `ignore` olur; `1/2/3` sırasıyla
crop/background/weed'dir. 28 ana fotoğraf kimliği release'te bulunmadığı
için 224 karo yalnız train rolünde tutulur ve Rice-eğitimli adaylar aynı
karolarda değerlendirilmez.

Model katkısı ekranlarını tekrar üretmek için:

```bash
.venv/bin/agri-seg benchmark \
  configs/benchmark/real_data_cropandweed_screen_v1.yaml
.venv/bin/python scripts/select_real_data_cropandweed.py \
  --protocol configs/benchmark/real_data_cropandweed_selection_protocol_v1.yaml \
  --control-benchmark data/runs/simulation_asset_quality_confirm_v3/benchmark_results.json \
  --control-development data/runs/simab_real_sorghum_cropcraft_robust10_e8_v3/development_fixed_epoch8_evaluations.json \
  --control-cropandweed-pattern 'data/runs/simab_real_sorghum_cropcraft_robust10_e8_v3/seed_{seed}/development/cropandweed_real_gate_v1.json' \
  --challenger-benchmark data/runs/real_data_cropandweed_screen_v1/benchmark_results.json \
  --stage screen \
  --output data/runs/real_data_cropandweed_screen_selection_v1.json

.venv/bin/agri-seg benchmark \
  configs/benchmark/real_data_cropandweed_additive_screen_v1.yaml
.venv/bin/python scripts/select_real_data_cropandweed_additive.py \
  --protocol configs/benchmark/real_data_cropandweed_additive_selection_protocol_v1.yaml \
  --control-benchmark data/runs/simulation_asset_quality_confirm_v3/benchmark_results.json \
  --control-development data/runs/simab_real_sorghum_cropcraft_robust10_e8_v3/development_fixed_epoch8_evaluations.json \
  --control-cropandweed-pattern 'data/runs/simab_real_sorghum_cropcraft_robust10_e8_v3/seed_{seed}/development/cropandweed_real_gate_v1.json' \
  --challenger-benchmark data/runs/real_data_cropandweed_additive_screen_v1/benchmark_results.json \
  --stage screen \
  --output data/runs/real_data_cropandweed_additive_screen_selection_v1.json

.venv/bin/agri-seg benchmark \
  configs/benchmark/real_data_rice_seedling_weed_screen_v1.yaml
.venv/bin/python scripts/select_real_data_rice_seedling_weed.py \
  --protocol configs/benchmark/real_data_rice_seedling_weed_selection_protocol_v1.yaml \
  --benchmark data/runs/real_data_rice_seedling_weed_screen_v1/benchmark_results.json \
  --stage screen \
  --output data/runs/real_data_rice_seedling_weed_screen_selection_v2.json
```

Her dönüştürmeden sonra dosya/şekil/sınıf denetimi, split'ler arası yakın kopya
araması ve etiket görsel kontrolü yapılmalıdır:

```bash
AGRI_DATA_ROOT=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data

.venv/bin/agri-seg audit \
  data/processed/manifests/real_core_final.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --output data/processed/audits/real_core_final.json

.venv/bin/agri-seg duplicate-audit \
  data/processed/manifests/all_roles_audit.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --max-hamming 2 \
  --output data/processed/audits/all_roles_duplicates.json

.venv/bin/agri-seg visualize-labels \
  data/processed/manifests/real_core_final.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --count 30 \
  --output data/processed/qc/real_core_final_labels_30.jpg
```

Bu koşunun immutable girdi/kanıt zinciri
`data/processed/audits/real_segmentation_freeze_v1.json` içindedir. Makbuz;
arşiv checksum'larını, CWFID commit'ini, manifest ve normalize maske
hash'lerini, audit/duplicate/QC kapılarını ve disk kapasitesini birlikte kilitler.

Yakın-kopya denetiminin temiz çıkması sekans bağımsızlığını kanıtlamaz;
`dataset_id + field_id + session_id` grupları da train ile değerlendirme
split'leri arasında ayrı tutulur.

## SorghumWeed + CropCraft kontrollü fazı

Bu fazın ayrıntılı sonuç ve sınırlamaları
[`docs/SIMULATION_ABLATION_REPORT.md`](docs/SIMULATION_ABLATION_REPORT.md)
içindedir. Üretim/QC kararları
[`previous_lessons_learned.md`](previous_lessons_learned.md) içindeki kalıcı
simülasyon derslerini uygular. Kabul edilen pilotu ve role-safe manifestleri
yeniden üretmek için:

```bash
AGRI_DATA_ROOT=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data

.venv/bin/python scripts/generate_cropcraft_pilot.py \
  configs/simulation/cropcraft_pilot_v1.yaml \
  --output "$AGRI_DATA_ROOT/synthetic/cropcraft/pilot_v1_accepted_r2"

.venv/bin/python scripts/convert_cropcraft_release.py \
  "$AGRI_DATA_ROOT/synthetic/cropcraft/pilot_v1_accepted_r2" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/processed/manifests/cropcraft_stock_pilot_v1.csv"

.venv/bin/python scripts/build_simulation_ablation_manifests.py \
  --real "$AGRI_DATA_ROOT/processed/manifests/real_core_final.csv" \
  --sorghum "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --synthetic "$AGRI_DATA_ROOT/processed/manifests/cropcraft_stock_pilot_v1.csv" \
  --output-dir "$AGRI_DATA_ROOT/processed/manifests"

.venv/bin/python scripts/analyze_simulation_domain_gap.py \
  --real "$AGRI_DATA_ROOT/processed/manifests/real_core_final.csv" \
  --synthetic "$AGRI_DATA_ROOT/processed/manifests/cropcraft_stock_pilot_v1.csv" \
  --data-root "$AGRI_DATA_ROOT" --per-dataset 30 \
  --output "$AGRI_DATA_ROOT/processed/audits/cropcraft_stock_pilot_domain_gap_v1.json"
```

Oran taraması, paired-seed confirmation ve sabit-epoch makbuzları:

```bash
.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_ablation_screen_v1.yaml
.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_ablation_confirm_v1.yaml

for CANDIDATE in \
  simab_real_sorghum_control_e8_v1 \
  simab_real_sorghum_cropcraft10_e8_v1
do
  .venv/bin/python scripts/evaluate_fixed_epoch_development.py \
    "$AGRI_DATA_ROOT/runs/$CANDIDATE" \
    --seeds 17 29 43 --fixed-epoch 8 \
    --data-root "$AGRI_DATA_ROOT" \
    --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
    --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv"
done

.venv/bin/python scripts/select_simulation_ablation_checkpoint.py \
  --protocol configs/benchmark/simulation_ablation_selection_protocol_v1.yaml \
  --runs-root "$AGRI_DATA_ROOT/runs" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --output "$AGRI_DATA_ROOT/runs/simulation_ablation_confirm_v1/ratio_selection.json"
```

%10 oran kabul edilirse epoch-15 bütçesi ayrı protokolle karşılaştırılır;
Sorghum `external_test` bu seçim tamamlanana kadar açılmaz:

```bash
.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_winner_epoch15_confirm_v1.yaml

.venv/bin/python scripts/evaluate_fixed_epoch_development.py \
  "$AGRI_DATA_ROOT/runs/simab_real_sorghum_cropcraft10_e15_v1" \
  --seeds 17 29 43 --fixed-epoch 15 \
  --data-root "$AGRI_DATA_ROOT" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv"

.venv/bin/python scripts/select_simulation_ablation_checkpoint.py \
  --protocol configs/benchmark/simulation_training_budget_selection_protocol_v1.yaml \
  --runs-root "$AGRI_DATA_ROOT/runs" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --output "$AGRI_DATA_ROOT/runs/simulation_winner_epoch15_confirm_v1/training_budget_selection.json"

.venv/bin/python scripts/evaluate_locked_simulation_final.py \
  --selection "$AGRI_DATA_ROOT/runs/simulation_winner_epoch15_confirm_v1/training_budget_selection.json" \
  --manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/runs/final_real_synthetic_v1/sorghum_weed_external_test.json" \
  --receipt "$AGRI_DATA_ROOT/runs/final_real_synthetic_v1/sorghum_weed_external_test_receipt.json"
```

Final evaluator mevcut output veya receipt görürse tekrar çalışmayı reddeder.

### Özel asset kalite gate'leri

Özel paketin tam sonucu ve başarısız ara iterasyonları
[`docs/SIMULATION_ASSET_QUALITY_REPORT.md`](docs/SIMULATION_ASSET_QUALITY_REPORT.md)
içindedir. Kabul edilen pilotun manifesti ve aynı-bütçeli A/B şu komutlarla
yeniden doğrulanır:

```bash
.venv/bin/python scripts/convert_cropcraft_release.py \
  "$AGRI_DATA_ROOT/synthetic/cropcraft/agri_early_pilot_v2_r2" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/processed/manifests/cropcraft_agri_early_pilot_v2.csv" \
  --dataset-id cropcraft_agri_early_pilot_v2 \
  --metadata-config configs/simulation/cropcraft_agri_pilot_v2.yaml

.venv/bin/python scripts/build_asset_ablation_manifest.py \
  --base "$AGRI_DATA_ROOT/processed/manifests/real_sorghum_trainval_v1.csv" \
  --synthetic "$AGRI_DATA_ROOT/processed/manifests/cropcraft_agri_early_pilot_v2.csv" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/processed/manifests/real_sorghum_cropcraft_agri_trainval_v2.csv" \
  --receipt "$AGRI_DATA_ROOT/processed/audits/cropcraft_agri_ablation_manifest_v2.json" \
  --expected-synthetic-dataset cropcraft_agri_early_pilot_v2

.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_asset_quality_confirm_v2.yaml

.venv/bin/python scripts/select_simulation_ablation_checkpoint.py \
  --protocol configs/benchmark/simulation_asset_quality_selection_protocol_v2.yaml \
  --runs-root "$AGRI_DATA_ROOT/runs" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --output "$AGRI_DATA_ROOT/runs/simulation_asset_quality_selection_v2.json"
```

Texture-backed v3 challenger, v2 seçilmiş özel paketi kontrol olarak tutar.
Paket/pilot ve aynı-bütçeli A/B şu komutlarla yeniden oluşturulur:

```bash
.venv/bin/python scripts/enhance_cropcraft_assets_v3.py \
  --base-pack "$AGRI_DATA_ROOT/raw/synthetic_assets/cropcraft_agri_early_v2_r3" \
  --output "$AGRI_DATA_ROOT/raw/synthetic_assets/cropcraft_agri_robust_v3_r3"

.venv/bin/python scripts/audit_cropcraft_assets.py \
  --stock-repository "$AGRI_DATA_ROOT/raw/cropcraft/repository" \
  --stock-release "$AGRI_DATA_ROOT/synthetic/cropcraft/pilot_v1_accepted_r2" \
  --asset-pack "$AGRI_DATA_ROOT/raw/synthetic_assets/cropcraft_agri_robust_v3_r3" \
  --gate configs/simulation/cropcraft_agri_asset_gate_v3.yaml \
  --output "$AGRI_DATA_ROOT/processed/audits/cropcraft_asset_quality_v3_r3.json"

.venv/bin/python scripts/generate_cropcraft_pilot.py \
  configs/simulation/cropcraft_agri_pilot_v3.yaml \
  --output "$AGRI_DATA_ROOT/synthetic/cropcraft/agri_robust_pilot_v3_r1"

.venv/bin/python scripts/convert_cropcraft_release.py \
  "$AGRI_DATA_ROOT/synthetic/cropcraft/agri_robust_pilot_v3_r1" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/processed/manifests/cropcraft_agri_robust_pilot_v3.csv" \
  --dataset-id cropcraft_agri_robust_pilot_v3 \
  --metadata-config configs/simulation/cropcraft_agri_pilot_v3.yaml

.venv/bin/python scripts/build_asset_ablation_manifest.py \
  --base "$AGRI_DATA_ROOT/processed/manifests/real_sorghum_trainval_v1.csv" \
  --synthetic "$AGRI_DATA_ROOT/processed/manifests/cropcraft_agri_robust_pilot_v3.csv" \
  --data-root "$AGRI_DATA_ROOT" \
  --output "$AGRI_DATA_ROOT/processed/manifests/real_sorghum_cropcraft_robust_trainval_v3.csv" \
  --receipt "$AGRI_DATA_ROOT/processed/audits/cropcraft_robust_ablation_manifest_v3.json" \
  --expected-synthetic-dataset cropcraft_agri_robust_pilot_v3

.venv/bin/agri-seg benchmark \
  configs/benchmark/simulation_asset_quality_confirm_v3.yaml

.venv/bin/python scripts/evaluate_fixed_epoch_development.py \
  "$AGRI_DATA_ROOT/runs/simab_real_sorghum_cropcraft_robust10_e8_v3" \
  --seeds 17 29 43 --fixed-epoch 8 \
  --data-root "$AGRI_DATA_ROOT" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv"

.venv/bin/python scripts/select_simulation_ablation_checkpoint.py \
  --protocol configs/benchmark/simulation_asset_quality_selection_protocol_v3.yaml \
  --runs-root "$AGRI_DATA_ROOT/runs" \
  --cwfid-manifest "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --sorghum-manifest "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --output "$AGRI_DATA_ROOT/runs/simulation_asset_quality_selection_v3.json"
```

Sorghum `external_test` bu seçimde okunmadı ve tekrar kullanılamaz; özel asset
tarifinin yeni final iddiası için yeni, dokunulmamış saha testi gerekir.

Export, development galerileri ve latency referansları:

```bash
BEST_CHECKPOINT="$AGRI_DATA_ROOT/runs/simab_real_sorghum_cropcraft10_e15_v1/seed_43/last.pt"
FINAL_DIR="$AGRI_DATA_ROOT/runs/final_real_synthetic_v1"

.venv/bin/agri-seg export "$BEST_CHECKPOINT" "$FINAL_DIR/model.onnx" \
  --image-size 512 --opset 18

.venv/bin/python scripts/benchmark_inference.py "$BEST_CHECKPOINT" \
  --output "$FINAL_DIR/latency_rtx3090_fp16_512.json" \
  --image-size 512 --warmup 30 --repeats 100 --crop-id 4

.venv/bin/python scripts/benchmark_tiled_inference.py "$BEST_CHECKPOINT" \
  --output "$FINAL_DIR/latency_rtx3090_fp16_sorghum_validation_native_tiled.json" \
  --reference-image "$AGRI_DATA_ROOT/raw/sorghum_weed/repository/SorghumWeedDataset_Segmentation/Validate/ValidateSorghumWeed (1).JPG" \
  --tile-size 1024 --tile-overlap 128 --warmup 3 --repeats 10 --crop-id 4

.venv/bin/agri-seg error-gallery "$BEST_CHECKPOINT" \
  "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --data-root "$AGRI_DATA_ROOT" --split external_calibration \
  --output "$FINAL_DIR/cwfid_development_gallery"

.venv/bin/agri-seg error-gallery "$BEST_CHECKPOINT" \
  "$AGRI_DATA_ROOT/processed/manifests/sorghum_weed.csv" \
  --data-root "$AGRI_DATA_ROOT" --split external_calibration \
  --output "$FINAL_DIR/sorghum_development_gallery"
```

## Model seçme protokolü

Bu bölüm ilk real-only fazın korunmuş model-tarama protokolüdür. Güncel
real+Sorghum+sentetik seçimi yukarıdaki ayrı sabit-oran/bütçe protokolüyle
yapıldı; eski kilitli testler yeni seçimde yeniden kullanılmadı.

Önce aynı 20 sabit crop üzerinde ezberleme testi çalıştırılır. Bu bir başarı
sonucu değil, veri/etiket/loss/model hattının öğrenebildiğini gösteren tanı
testidir:

```bash
.venv/bin/agri-seg train configs/train/overfit20_real_final_stratified.yaml
```

Ardından erişilebilir adayların tek-seed taraması çalıştırılır:

```bash
.venv/bin/agri-seg benchmark configs/benchmark/real_final_conditioning_screen.yaml
```

Matris dokuz erişilebilir adayı kapsar: ConvNeXt-Tiny FPN için
factorized stage4 safety/no-safety × conditioning dropout 0,5/0,8;
factorized frozen; flat stage4 ve flat frozen kontrolleri; DINOv2-Small frozen
ve SegFormer-B2. DeepLab eski zayıf tarama sonucu nedeniyle bu matrise
alınmamıştır. Tarama yalnız aday elemek için kullanıldı. DINOv2 frozen ve
ConvNeXt flat/frozen seed 17/29/43 koşularında hiçbir tarif tüm seed'lerde
operasyonel selector'ü geçmedi. Semantik kalite lideri DINOv2 üzerinde stage-4
epoch 15, seed 17/29/43 çalıştırıldı; her run için CWFID kalibrasyon makbuzu ve
tüm seed'leri birlikte doğrulayan ayrı semantik seçim makbuzu üretildi.

SegFormer'ın yayıncı lisansı ticari olmayan kullanımla sınırlıdır; DINOv2 model
kartı Apache-2.0 belirtir. Torchvision ImageNet ön-eğitim ağırlıkları için veri
ve ağırlık koşulları ayrıca incelenir. Bu ayrım benchmark artifact'inde veri
lisansı kapsamından ayrı bir alan olarak saklanır.

### Güvenli püskürtme politikası

Semantik tahmin doğrudan püskürtme maskesi değildir. Varsayılan politika:

1. güven düşükse, ilk iki sınıf marjı küçükse veya normalize entropi yüksekse
   pikseli `unknown` yapar;
2. ürün olasılığı eşiğini geçen alanı 5 piksel genişleterek ürün koruma alanı
   oluşturur;
3. yabancı ot olasılığı seçilen eşiği geçiyor ve ürün olasılığından büyükse
   yabancı ot adayı üretir;
4. `safe_weed = weed_candidate - crop_guard - unknown` uygular.

Güvenlik kontratı üç ayrı hard gate uygular: her domain'de aggregate
`crop_spray_risk <= 0,5%`, kare-başı risk dağılımında `p99 <= 0,5%` ve
`crop_spray_risk > 0,5%` olan kare oranı `<= 1%`. Uygun eşikler arasından
önce en kötü çekim grubundaki, sonra gruplar arası makro güvenli yabancı ot
recall'ı en yüksek olan seçilir. Bilinen crop-ID eşikleri yalnız kaynak
validation'dan gelir. Bilinmeyen crop eşiği, kaynak unknown eğrisi ile ilan
edilmiş CWFID development eğrisinin seçtiği eşiklerin maksimumudur ve aynı
eşik her iki kümede üç kapıyı da geçmelidir. Kilitli final testte hiçbir
eşik taraması yapılmaz.

Temel metrikler:

- `crop_spray_risk`: güvenli püskürtme maskesine giren hedef ürün pikseli /
  tüm hedef ürün pikselleri.
- `safe_weed_recall`: güvenli püskürtme maskesine giren gerçek yabancı ot /
  tüm yabancı ot pikselleri.
- `safe_weed_precision`: güvenli maskede doğru yabancı ot / güvenli maskenin
  tüm geçerli pikselleri.
- `crop_as_weed_rate_raw`: belirsizlikten elenmiş, fakat ürün koruma alanı henüz
  uygulanmamış yabancı ot adaylarına düşen ürün oranı.
- `unknown_rate`: güvenli karar verilmeyen geçerli piksel oranı.
- sınıf IoU, worst-domain yabancı ot IoU ve mIoU: ikincil semantik kalite
  ölçüleri.
- kare başına crop-spray risk p95/p99/maksimum ve ihlal oranı: piksel
  ortalamasında gizlenebilecek tehlikeli kuyrukları gösterir.
- küçük/orta/büyük bağlı yabancı ot bileşeni recall'ı ile gelişim evresi, ürün,
  platform ve sensör kırılımları: büyük bitkilerin piksel metriğini domine
  etmesini görünür kılar.

Benchmark sıralaması önce kaynak ve ilan edilmiş geliştirme kümelerinde tüm
güvenlik sınırlarının sağlanmasını, sonra bu kümelerdeki en düşük
çekim-grubu `safe_weed_recall` değerini, sonra makro recall ve en düşük
worst-domain yabancı ot IoU değerini kullanır. Sınırı geçemeyen adaylarda
yüksek recall değil, önce en düşük crop-spray riski tercih edilir.

Sabit 5 piksel koruma yarıçapı fiziksel bir mesafe değildir. Dış değerlendirme
aynı dondurulmuş eşikte 0/5/10/20 piksel hassasiyetini birlikte raporlar; GSD
bilgisi olmadan santimetre cinsinden saha güvenlik marjı iddia edilmez.

## Dış değerlendirme, galeri ve ONNX

`real_final_conditioning_screen.yaml`, CWFID'i önce kaynakta dondurulmuş
unknown politikayla tanısal olarak değerlendirir. Yetkili sıralamadan önce her
run için ilan edilmiş development kalibrasyonu ayrı ve hash'li bir checkpoint
ile makbuz üretir:

```bash
AGRI_DATA_ROOT=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data
RUN="$AGRI_DATA_ROOT/runs/ADAY_ADI/seed_17"

.venv/bin/python scripts/calibrate_unknown_policy.py \
  "$RUN/best.pt" \
  "$AGRI_DATA_ROOT/processed/manifests/cwfid.csv" \
  --data-root "$AGRI_DATA_ROOT" \
  --output-checkpoint "$RUN/best.devcal.pt" \
  --receipt "$RUN/development/cwfid_unknown_calibration.json"

.venv/bin/python scripts/select_final_checkpoint.py \
  "$AGRI_DATA_ROOT/runs/real_final_conditioning_screen_v2_tail/benchmark_results.json" \
  --development-name cwfid \
  --expected-seeds 17 \
  --output "$AGRI_DATA_ROOT/runs/real_final_conditioning_screen_v2_tail/screen_selection.json"
```

İlk real-only tanısal selector hiçbir aday tüm-seed güvenlik kontratını sağlamadığı için
`selected_checkpoint: null` yazdı. Bu sonuç korunmuştur; tanısal temsilci
deployment kazananı değildir. Ayrı semantik selector, sabit epoch-15 stage-4
real-only koşularında tüm teknik risk makbuzlarını doğrulayıp medyan seed
17'yi, eski final testleri okumadan kilitledi. `real_core_final.test`,
Carrot-Weed ve EWIS1 bundan sonra yalnız bir kez çalıştırıldı:

```bash
AGRI_DATA_ROOT=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data

.venv/bin/python scripts/select_semantic_checkpoint.py \
  "$AGRI_DATA_ROOT/runs/rf4_dinov2_small_stage4_mean1_drop05_probe" \
  --candidate-name rf4_dinov2_small_stage4_mean1_drop05_probe \
  --seeds 17 29 43 \
  --fixed-epoch 15 \
  --output "$AGRI_DATA_ROOT/runs/real_final_dinov2_stage4_multiseed_tail_v1/semantic_selection.json"

BEST_CHECKPOINT="$AGRI_DATA_ROOT/runs/rf4_dinov2_small_stage4_mean1_drop05_probe/seed_17/last.semantic.devcal.pt"

.venv/bin/agri-seg evaluate \
  "$BEST_CHECKPOINT" \
  data/processed/manifests/real_core_final.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --split test \
  --output "$AGRI_DATA_ROOT/runs/final/real_core_final_test.json"

.venv/bin/agri-seg evaluate \
  "$BEST_CHECKPOINT" \
  data/processed/manifests/carrot_weed.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --split external_test \
  --output "$AGRI_DATA_ROOT/runs/final/carrot_weed.json"

.venv/bin/agri-seg evaluate \
  "$BEST_CHECKPOINT" \
  data/processed/manifests/ewis1.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --split external_test \
  --output "$AGRI_DATA_ROOT/runs/final/ewis1.json"

.venv/bin/agri-seg error-gallery \
  "$BEST_CHECKPOINT" \
  data/processed/manifests/carrot_weed.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --split external_test \
  --output "$AGRI_DATA_ROOT/runs/final/carrot_weed_gallery"

.venv/bin/agri-seg error-gallery \
  "$BEST_CHECKPOINT" \
  data/processed/manifests/ewis1.csv \
  --data-root "$AGRI_DATA_ROOT" \
  --split external_test \
  --output "$AGRI_DATA_ROOT/runs/final/ewis1_gallery"

.venv/bin/agri-seg export \
  "$BEST_CHECKPOINT" \
  "$AGRI_DATA_ROOT/runs/final/model.onnx" \
  --image-size 512 \
  --opset 18

.venv/bin/python scripts/benchmark_inference.py \
  "$BEST_CHECKPOINT" \
  --output "$AGRI_DATA_ROOT/runs/final/latency_rtx3090_fp16_512.json" \
  --image-size 512 --warmup 30 --repeats 100

.venv/bin/python scripts/benchmark_tiled_inference.py \
  "$BEST_CHECKPOINT" \
  --output "$AGRI_DATA_ROOT/runs/final/latency_rtx3090_fp16_ewis_native_tiled.json" \
  --reference-image "$AGRI_DATA_ROOT/raw/ewis1/images/images/Aholfing_20220525_Sorghum_008.png" \
  --tile-size 1024 --tile-overlap 128 --warmup 3 --repeats 10 --crop-id 4
```

Galeri, dondurulmuş politika ile en iyi 10 ve en kötü 10 örneği seçer ve
checkpoint/manifest hash'lerini `index.json` içinde saklar. ONNX çıktısı ancak
yanındaki `.parity.json` raporunda `pass: true` ise kabul edilir; doğrulama kare
batch-1 ile dikdörtgen batch-2 girişleri ve factorized modelde bilinen/bilinmeyen
ürün kimliklerini kapsar. ONNX yalnız semantik olasılık ağını içerir; tiling ve
safety policy uygulama paketinde ayrıca sağlanmalıdır.

Final sonuç özeti: kaynak test mIoU `0,720475`, Carrot-Weed `0,290652`, EWIS1
`0,719594`. ONNX parity geçti. RTX 3090 AMP FP16 latency 512×512'de ortalama
`4,0968 ms`; 5464×3640 ve 24 tiled EWIS boyutunda `535,394 ms`'dir. İkinci
ölçüm preprocessing/safety içermez; GPU compute near-idle olsa da sleeping vLLM
752 MiB ayırdığı için tam boş-GPU ölçümü değildir.

## DINOv3 erişim durumu

Planlanan `facebook/dinov3-convnext-tiny-pretrain-lvd1689m` ağırlıkları
gated'dir. Hugging Face oturumu artık geçerli ve RiceSEG'e erişiyor; fakat
DINOv3 metadata'sı görünse de gerçek `config.json`/weight isteği `401/403`
ile reddedildi. Hesap sahibi
[model sayfasındaki ayrı koşulları](https://huggingface.co/facebook/dinov3-convnext-tiny-pretrain-lvd1689m)
kabul etmelidir. Sonrasında önce küçük dosyayla erişim doğrulanır:

```bash
HF_HOME=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/cache/huggingface \
  .venv/bin/hf download \
  facebook/dinov3-convnext-tiny-pretrain-lvd1689m config.json \
  --revision 10d30274b4d445111e2d5bf75ac93bbd94db274b
```

Token repoya veya YAML dosyasına yazılmaz. Erişim açılsa bile tarihsel
`dinov3_gated.yaml` doğrudan koşturulmaz; güncel accepted-control ile eşit
veri/compute protokolü önce dondurulur. DINOv3 çalışmadan sonuç yalnız
erişilebilir/test edilen adaylar için geçerlidir. Ayrıntılı erişim/lisans
kanıtı
[`docs/MODEL_DINOV3_ACCESS_PREFLIGHT_V1.md`](docs/MODEL_DINOV3_ACCESS_PREFLIGHT_V1.md)
içindedir.

## Çıktı düzeni

```text
data/
├── raw/<dataset>/                     indirilen ve açılmış kaynaklar
├── processed/
│   ├── <dataset>/common_masks/        ortak 0/1/2/255 maskeleri
│   ├── manifests/*.csv                örnek, domain, split ve lisans kaydı
│   ├── audits/*.json                  bütünlük ve piksel sayımları
│   └── qc/*.jpg                       etiket temas sayfaları
├── cache/                             model ağırlığı/cache
└── runs/
    ├── <experiment>/seed_<n>/
    │   ├── config.resolved.json
    │   ├── run_metadata.json          donanım, sürüm, parametre ve manifest hash'i
    │   ├── history.jsonl
    │   ├── best.pt / last.pt
    │   ├── metrics.json / summary.json
    │   └── development/cwfid.json ve calibration receipt
    ├── real_final_conditioning_screen_v2_tail/
    │   ├── benchmark_results.json
    │   └── screen_selection.json
    ├── simulation_ablation_confirm_v1/  oran seçim makbuzu
    ├── simulation_winner_epoch15_confirm_v1/
    │   └── training_budget_selection.json
    ├── simulation_asset_quality_selection_v2.json
    ├── simulation_asset_quality_selection_v3.json
    ├── real_data_cropandweed_screen_selection_v1.json
    ├── real_data_cropandweed_additive_screen_selection_v1.json
    ├── real_data_cropandweed_final_selection_v1.json
    └── final_real_synthetic_v1/          yeni final/export/latency/galeri
```

Real-only rapor
[`docs/BENCHMARK_REPORT.md`](docs/BENCHMARK_REPORT.md), kontrollü sentetik
fazın kanonik raporu ise
[`docs/SIMULATION_ABLATION_REPORT.md`](docs/SIMULATION_ABLATION_REPORT.md),
özel asset kalite raporu ise
[`docs/SIMULATION_ASSET_QUALITY_REPORT.md`](docs/SIMULATION_ASSET_QUALITY_REPORT.md),
texture-backed v3 devamı ise
[`docs/SIMULATION_ASSET_QUALITY_REPORT_V3.md`](docs/SIMULATION_ASSET_QUALITY_REPORT_V3.md)
dosyasındadır.

## Dürüst yorumlama kuralları

- mIoU yüksekliği, ürün üzerine püskürtmenin güvenli olduğunu göstermez.
- `unknown`, abstention mekanizmasıdır; doğrulanmış OOD tespiti değildir.
- CWFID geliştirmede kullanıldığı için final genelleme kanıtı sayılamaz.
- Carrot-Weed 39 görüntülük tek sekans ve ticari olmayan bir kümedir; tek
  başına saha genellemesi veya üretim güvenliği kanıtı değildir.
- Tek seed, tek split veya en iyi checkpoint seçimi belirsizliği gizler.
- “En iyi” ifadesi yalnız gerçekten koşulan adaylar, seed'ler, veri sürümleri ve
  önceden tanımlanmış sıralama kuralı içinde kullanılmalıdır.
- Test sonuçlarına bakarak eşik, augmentasyon, loss veya model seçilirse test
  kilidi bozulur; yeni ve dokunulmamış bir final test gerekir.
- Bu benchmark güvenlik-dostu model seçimi sağlar; saha püskürtme sistemi için
  bağımsız doğrulama, sensör/latency testi ve fail-safe tasarımı yerine geçmez.
