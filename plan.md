# Tarım Vision Projesi — AI PoC ve Sentetik Veri Yol Haritası

> **2026-08-10 segmentasyon `%95+` saha kanıt planı:** Instance segmentation
> ana hat olarak kilitlendi. Başarı mask mIoU ile değil, session/tarla-ayrı
> videoda track-level weed action precision/recall/F1, crop collision,
> nozzle-footprint safe hit ve fiziksel knockdown ile ölçülecek. Minimum GO
> hedefleri sırasıyla `P≥0,97`, `R≥0,95`, `F1≥0,96`, crop action `≤0,005`,
> footprint safe hit `≥0,95` ve fiziksel knockdown `≥0,90`; güçlü hedef F1
> `≥0,97`dir. Minimum müdahale boyutu model sonucundan önce fiziksel mm,
> visible fraction ve safety mesafesiyle dondurulacak. PhenoBench post-hoc
> predicted-size tanısında en iyi `GT≥42 px` policy'si
> `P/R/F1 0,8852/0,8016/0,8413` verdi; yalnız küçükleri dışlamak `%95`e
> yetmedi. Küçük-set kapasite deneyi ise hedef-benzeri 126 aynı karede
> crop-safe action `P/R/F1 0,9968/0,9968/0,9968` ve sıfır crop hit ile `%98`
> kapısını geçti: kapasite var, yeni session genellemesi yok. Ortak farklı-parsel
> testinde base `0,9202/0,7744/0,8410`; agresif hedef-only
> `0,8841/0,7936/0,8364`; hedef+kaynak replay `0,8140/0,8544/0,8337` verdi.
> Replay recall'ı `+0,08` artırıp precision ve crop hit'i bozduğu için
> reddedildi. Basit excess-green crop-safe nokta, deepest-interior'a göre F1'ı
> `+0,0386` artırdı; confidence ve sıra prior'ları crop riskini recall'ı aşırı
> düşürmeden çözemedi. P0 sıra: geçici ana `d_min=20 mm`, stretch
> `10–20 mm` kontratı ve nozul footprint'i; aynı bitkide paired
> global-shutter/GSD + ambient-vs-LED/strobe + motion deneyi; session-dengeli
> crop-yakın hard-negative target fine-tune; native 4K tile
> 1024/1536/2048; ID-GT videoda single-frame-vs-tracking; sonra gerekirse bir
> büyük aynı-aile ve bir alternatif segmenter. Untouched saha testinde en
> az 2.000 uygun weed track ve crop-risk `%0,1` iddiası için en az 3.000
> crop-yakın fırsat hedeflenecek. Rakip taraması, Deere/Greeneye/ARA/Verdant/
> Carbon yanında ONE SMART SPRAY/Bilberry/WEED-IT'i de kapsıyor. Kamuya açık
> ceiling parçaları Greeneye recall `%95,7`, ARA minimum recognition `≥2 mm`
> fakat `6×6 cm` spray, Bilberry `≥5 cm` weed için `>%90` hit, Verdant `%99`
> atışın `2 mm` içinde ve Carbon hakemli `≥%97` weed-biomass azalmasıdır.
> Hiçbiri minimum boyut + P/R + crop hit + kill-rate sözleşmesinin tamamını
> aynı testte kamuya açık vermiyor.
> Ayrıntı: `docs/SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md`.

> **2026-08-10 adil detection–segmentation kararı:** Önceki WSD karşılaştırması
> target-trained detector ile zero-shot segmenteri eşlediği için saf mimari
> kararı olarak iptal edildi. PhenoBench'te detection ve instance-segmentation
> kolları aynı 1.407 gerçek train karesini, aynı publisher instance'larını,
> aynı YOLO26s/1024/50-epoch/seed-17 protokolünü gördü. Resmî validation
> parselleri model çıktısından önce 369 calibration ve parsel-ayrı 403 untouched
> test karesine bölündü; eşikler yalnız calibration'da seçilip JSON'a
> kilitlendikten sonra test açıldı. Exact weed-dokusu tek-bitki/tek-atış test
> F1'ı detection kutu-merkezinde `0,6473`, segmentasyon güvenli-iç-noktasında
> `0,7399` oldu; paired-image bootstrap farkı `+0,0924`, %95 GA
> `[+0,0702,+0,1156]` ve segmentasyonun üstün olma olasılığı `1,0`dır.
> Segmenter-kutu-merkezi kontrolü `0,6212` olduğundan maskenin aksiyon
> temsilinin ek değeri ayrıştırıldı. Instance segmentation genişletilebilir
> temel olarak seçildi; fakat recall `0,6494`, `<14 px` recall `0,2637`, tek
> training seed ve UAV domaini nedeniyle saha GO verilmedi. Sıradaki kapı kendi
> robot kamera/FOV/focus dağılımımızda session-ayrı instance-maskeli test,
> ardından tracking ve fiziksel nozzle/deposition/kill/crop-injury ölçümüdür.
> Okunabilir rapor:
> `docs/results/FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf`.

> **2026-08-02 segmentasyon fazı sonucu:** Gerçek-veri benchmark'ına resmi
> SorghumWeed train split'i ve %10 sampler exposure'lı, 100 karelik kontrollü
> CropCraft pilotu eklendi. Üç-seed robust semantik kazanan DINOv2-Small FPN
> stage-4, epoch 15, seed 43'tür. Tek-sefer Sorghum test mIoU 0,834852'dir;
> kuyruk crop-risk kapıları kaldığı için model field/spray-ready değildir.
> Ardından özel CC0 erken-sorgum asset tarifi stock asset'e karşı epoch-8
> gate'ini 3/3 seed ve ortalama `+0,020305` robust mIoU ile geçti. Bu asset
> kontrolü daha sonra 4 resmi CC0 texture-backed weed kaynağı ve üç crop
> albedo fenotipiyle güçlendirildi. V3 paket, v2 özel kontrole karşı 3/3 seed
> ve ortalama `+0,017015` robust mIoU ile ikinci asset gate'ini de geçti.
> CropAndWeed daha sonra 4.584 kabul edilmiş gerçek kareyle kalite/sızıntı
> kapılarını geçti; ancak %10/%20 ikame ve replay-preserving %10 additive
> ekranlarında CWFID worst-domain mIoU'yu düşürdü. Bu nedenle v3 kontrol
> korundu ve gereksiz üç-seed confirmation açılmadı.
> Ardından CC-BY-4.0 Rice Seedling and Weed verisinin 224 karosu
> fail-closed `raw0=ignore` ontolojisiyle kalite kapılarını geçti. Tek
> oturumdaki 28 ana fotoğrafın karoları yalnız train rolünde tutuldu.
> `%2,5` karışım robust mIoU'yu `+0,008422` artırdı fakat CropAndWeed
> non-inferiority sınırını `0,000125` ile kaçırdı; `%5` kol CWFID'de
> `-0,005679` robust regresyon yaptı. İki kol reddedildi. Unexposed kontrol
> Rice zero-shot mIoU `0,311910` ile yeni paddy sentetik-asset açığını
> nicel olarak gösterdi.
> Bu açık için 60 rice modeli/20 bağımsız geometri, 36 paddy weed,
> üç ıslak PBR, üç HDRI ve sığ-su profilli R5 paddy paketi geliştirildi.
> Beş başarısız/iyileştirilmiş asset iterasyonundan sonra static, smoke,
> 100-kare pilot, manuel görsel, mask, leakage ve gerçek Rice domain-gap
> kapıları geçildi. `%5 v3 + %5 paddy` tarifi v3 kontrole karşı seed
> 17/29/43'te 3/3 robust galibiyet ve ortalama `+0,048805` beş-domain
> worst-case mIoU sağladı; CWFID `+0,040521`, Rice `+0,048805`, macro
> `+0,017722` yükseldi. Paddy-only `%10` Rice'ta daha yüksek olsa da
> CropAndWeed screen gate'inde kaldı. R5 karışım kabul edildi.
> Sonraki soy çalışmasında 60 model/20 bağımsız geometri/5 evre/3 fenotip,
> 53 weed, üç soil PBR ve üç HDRI içeren V5 R3 paketinin semantic alpha
> hatası düzeltilip yüksek-weed/düşük-crop V6 R5 tamamlayıcı pilotu üretildi.
> Static, kompozisyon, manuel RGB-mask ve 12.618 gerçek referansa karşı
> leakage kapıları geçti. Buna rağmen dengeli 45 V5 + 45 stress draw'lı
> additive model GrowingSoy'u `+0,100142` yükseltirken CWFID'yi `-0,130207`,
> Rice/robust minimumu `-0,029398` ve macro'yu `-0,009288` düşürdü. Model
> gate'i reddedildi; seed 29/43 confirmation ve büyük batch açılmadı, kabul
> edilmiş `%5` dryland V3 + `%5` paddy R5 kontrolü korundu. Kanıt yeni bir
> haricî mesh'ten önce çok-tarlalı gerçek soy verisini ve daha sonra
> crop-koşullu specialist/adapter deneyini destekliyor.
> Gerçek-veri optimizasyonunda GrowingSoy'un 1.000 boylamsal karesi kalite
> kapısını geçti; `%5/%10` katkı kendi alanını `+0,284888 / +0,296242`
> artırsa da CWFID ve/veya CropAndWeed/Rice non-inferiority kapılarında
> kaldı. DeBlurWeedSeg'in 100 sharp/100 motion-blur development tanısı kabul
> edilmiş kontrolde üç-seed ortalama `-0,144855` mIoU kaybı gösterdi ve model
> seçmedi. WeedMap'in 4,48 GB arşivindeki ters validity-mask ve `10000=crop`
> release anomalileri 970 tile'ın tamamında doğrulandı; 424 train + 95
> calibration tile kalite/sızıntı kapılarını geçti. `%2,5/%5` katkılar
> WeedMap'i `+0,160505 / +0,177702` yükseltirken CWFID'yi
> `-0,050411 / -0,060024` düşürdü. İki kol reddedildi, confirmation açılmadı
> ve paddy R5 kontrolü korundu. Çok-ülkeli RiceSEG sıradaki en yüksek değerli
> gerçek kaynak olarak kaldı. Ardından CC BY 4.0 Tobacco Aerial'ın 2.520
> patch'i sekiz campaign-ayrık kalite kapısından geçti. `%4,7619` additive
> kol Tobacco'yu `+0,011261` artırdı; fakat CWFID/Rice/CropAndWeed ve macro
> non-inferiority kapılarında kaldı. Aday reddedildi, paddy R5 kontrolü
> korundu. RiceSEG erişim koşulu kabul edilip yerel Hugging Face oturumu
> açıldı; pinli `1a891ced...` repository'nin `1.564.399.537` baytlık altı
> dosyası indirildi. 3.078 RGB/maske çiftinin tamamı exact-set, SHA-256,
> archive-safety, tam CRC, `512x512` decode, altı-sınıf palette/piksel oranı,
> pairing, 19-subdataset ve manuel görsel kapılarından geçti. 17.688 önceki
> gerçek görüntüye karşı sızıntı yoktur. Aynı train rolündeki tek
> çatışmalı yakın kopya deterministik olarak karantinaya alındı; 3.077
> uygun örnek `2.473 train / 604 external_calibration` olur. Ayrı temiz
> country-transfer görünümü `1.823 China+Japan -> 1.254
> India+Tanzania+Philippines` olarak kilitlidir ve coverage split'iyle
> birleştirilmez. CampanetaWeeds2/AgriDataValue kutu etiketi,
> RafanoSet küçük partial track, BAWSeg/CWD30-S ise o tarama anında
> yayımlanmamış tam artifact nedeniyle RiceSEG'in yerine indirilmedi.
> Asset auditinde dryland V3/paddy R5 botaniğinin zaten güçlü olduğu, ölçülmüş
> en büyük sentetik açığın yönlü kamera hareketi olduğu görüldü. Bu açık için
> 32 linear/curved CC0 PSF ile 100 dryland + 100 paddy motion-blur RGB üretildi;
> static, manuel, manifest ve 15.857 gerçek referansa karşı leakage kapıları
> geçti. `%2,439` additive kol DeBlur motion mIoU'yu kabul/compute kontrollerine
> göre `+0,064939 / +0,069539`, sharp'ı `+0,023246 / +0,026579` artırdı. Ancak
> CWFID `-0,052882 / -0,025866`, WeedMap `-0,013881 / -0,016959` ve existing
> robust/macro geriledi. V7-R1 model gate'i reddedildi; R5 kontrol korundu.
> Ardından aynı RGB/PSF byte'larıyla blur-boundary confidence `<0,50`
> piksellerini ignore yapan V7-R2 üretildi. `%2,2551` yeni ignore oranı;
> otomatik, manuel ve manifest kapıları geçti. Eşit 3.600-draw bütçede
> yalnız `%0,625` exposure GrowingSoy'u `+0,050333` yükseltti; fakat hedef
> motion-blur `-0,004755`, CWFID `-0,072316` ve existing/expanded macro
> `-0,003716 / -0,003832` geriledi. V7-R2 de reddedildi, confirmation
> açılmadı ve R5 kontrol korundu. Motion asset paketi kalite gate'ini geçen
> stress/specialist girdisi olarak saklandı; RiceSEG/çok-tarlalı gerçek blur
> kanıtı gelmeden global sampler için yeni asset iterasyonu açılmayacak.
> Buna paralel CC-BY-4.0 WeedyRice-RGBMS-DB'nin 5,29 GB release'i indirildi.
> Dört uçuşa ait 734 RGB+maske; archive/CRC, metadata, piksel, görsel,
> uçuş-ayrık split ve 15.857 gerçek referansa karşı leakage kapılarını geçti.
> Yayıncının 438/148/148 görüntü split'i dört uçuşu da bütün rollere dağıttığı
> için reddedildi. Kaynak `255=weedy rice`, fakat `0` cultivated rice, su,
> toprak ve diğer negatifleri birleştirdiğinden 487 Thoaison karesi yalnız
> partial-label train adayı olarak kilitlendi; ortak modele açılmadı. Ayrı
> Longxuyen uçuşundaki 247 karede üç-seed zero-shot tanı, semantic argmax'ın
> görüntünün `%96,694`'ünü other-vegetation sayarak yanıltıcı `0,597835` IoU
> ürettiğini; source-frozen weed çıktısının IoU/recall'ının yalnız `0,000064`
> olduğunu gösterdi. Kabul edilmiş model değişmedi. Sonuç RiceSEG'i gerçek
> coverage'da, daha sonra positive-only specialist protokolünü önceliklendirir.
> RiceSEG oturumu beklerken CC-BY-4.0 CamelinaWeed v1'in 69,01 GB arşivi
> merkez-dizin + HTTP Range ile seçmeli alındı; tam arşivin yalnız 3,37 GB'ı
> ağdan aktarıldı. Exact release'teki 1.120 JPEG/12 JSON'dan 1.097 pozitif
> partial maske üretildi. 999 Thessaloniki train adayı ile konum-ayrık 98
> Chalkidiki calibration görüntüsü tam decode, poligon, görsel ve 16.591
> gerçek referansa karşı leakage kapılarını geçti. Crop/background exhaustive
> olmadığı için tüm non-polygon pikseller ignore ve ortak/positive-only eğitim
> ayrı loss protokolüne kadar kilitlidir. Güncel provenance matrisi toplam 17
> veri kümesi/17.688 kayıt, 15.633 ortak-semantik uyumlu ve 2.055 partial-kilitli
> kayıt doğrulamıştı. RiceSEG eklendikten sonra güncel matris 18 veri
> kümesi/20.765 kayıt, 18.710 ortak-semantik uyumlu ve 2.055 partial-kilitli
> kayıt doğruladı.
> RiceSEG'de kabul edilmiş paddy R5 paketinin en büyük açığı
> `late_reproductive_rice` olarak ölçüldü. Üç image-generation kaynak
> texture'ı, 48 model/24 geometri/dört evreli prosedürel R3 rice paketi ve
> 100-kare pilot üretildi. R1 seyrek boncuk/panicle, R2 açık radial iskelet
> morfolojisi nedeniyle manuel kapıda reddedildi; R3 statik, smoke, manuel,
> RiceSEG 6/6 dağılım, manifest ve 20.765 gerçek referansa karşı leakage
> kapılarını geçti. Eşit bütçeli `%5 dryland + %2,5 early paddy + %2,5
> reproductive` seed-17 kolu RiceSEG'i `+0,141180`, saf reproductive alt-kümeyi
> `+0,101863`, yedi-domain robust minimumu `+0,101863` artırdı. Buna karşın
> CWFID/CropAndWeed `-0,039529 / -0,016026` geriledi; dondurulmuş
> non-inferiority kapısı adayı reddetti, seed 29/43 açılmadı ve kabul
> edilmiş R5 kontrolü korundu. Asset specialist/daha düşük-doz araştırma
> girdisidir; global katkısı kanıtlanmış değildir.
> Gerçek RiceSEG katkısı ardından iki additive ve bir sabit-compute
> exact-index seed-17 ekranında ölçüldü. Üç tarif de RiceSEG/reproductive
> mIoU'yu yaklaşık `+0,32 / +0,37` artırdı; fakat mevcut-domain
> non-inferiority kapılarında kaldı. Deterministik sampler auditi RiceSEG'in
> zaten field/session dengeli olduğunu, ilk iki "replay" kolunun ise yalnız
> beklenen draw hacmini koruduğunu gösterdi. V3 her epoch 3.600 indeksin 90'ını
> RiceSEG ile değiştirip kalan 3.510 pozisyonu birebir korudu; CWFID
> `-0,006124` ile geçti, ancak source/Sorghum/CropAndWeed
> `-0,012139 / -0,023556 / -0,025475` geriledi. Global aday reddedildi,
> confirmation açılmadı; RiceSEG rice-conditioned specialist/adapter girdisi
> olarak kabul edildi.
> Ayrı parametreli crop-routed specialist ardından tamamlandı. Seed-17 sabit
> 30.240-draw `%2,38/%10/%25/%50` ekranında full RiceSEG'i `%50` en çok
> artırsa da early/full/reproductive robust minimumunu `%2,38` kazandı.
> Paired seed 17/29/43 confirmation'da specialist early/full/reproductive
> ortalamaları `0,522806 / 0,617404 / 0,413770`, fallback'e karşı farklar
> `+0,156047 / +0,328889 / +0,382517` ve robust galibiyet `3/3` oldu.
> `crop_id=12 / Oryza sativa` route'u specialist seed 29'a, diğer/bilinmeyen
> girdiler değişmemiş global seed-43 fallback'e gider. Otomatik görsel route
> veya saha/spray onayı değildir.
> RiceSEG sonrası taramada BAWSeg'in IEEE DataPort artifact'i artık
> `Multispectral Image Benchmark Dataset.zip (7.5 GB)` olarak görünürdür.
> Dört sezon/iki ticari barley paddock ve dense crop/weed/other kapsamı
> yüksek değerlidir. Kamu content-ID ve HDD kapasite kapısı geçti; indirme
> abonelik oturumu, merkez-dizin/CRC/iç-SHA ve paket içi lisans incelemesi
> bekler. Veri henüz coverage'a veya modele eklenmedi.
> Son tarla-bağımsızlığı dokunuşunda 14 CC0 soil ve 14 HDRI ailesini
> train/synthetic-val/synthetic-test arasında tamamen ayıran V10 surface/light
> paketi tamamlandı. Nem, dört tillage davranışı, clod makro-normal, güneş
> açısı/enerjisi, lokal gölge, kamera takipli robot ışığı ve opsiyonel sığ su
> randomize edilir. 48/12/12 karelik dryland pilot tüm üretim, RGB-mask,
> radyometri, asset/seed leakage ve ortak ontoloji kapılarını geçti;
> synthetic-val/test'in gerçek seçim skoru ağırlığı `0,0`'dır. Gerçek seçim
> için önce field/session sonra dataset macro alan, `%60` target-like + `%25`
> breadth + `%15` lower-tail ağırlıklı protokol donduruldu. Mevcut source
> validation'ın 4/6 field overlap'i nedeniyle strict v2 model replacement yeni
> field-disjoint gerçek holdout'u bekler. Ayrıca resmî CC-BY-SA-4.0 BoniRob
> Sugar Beets 2016 JAI-RGB akışından 31 adet 1296x966/1 Hz unseen robot karesi
> indirildi. Kabul edilmiş global seed-43 model tüm karelerde çalıştırıldı;
> geniş yapraklı bitki sınırları kuvvetli, ince/çimsi yapılarda crop-other ve
> unknown karışması görüldü. Etiket olmadığı için mIoU üretilmedi ve sekans
> seçim skoruna girmedi. V10 seed-17 model ekranının ilk denemesi challenger'a
> başlamadan, ortak GPU'daki ayrı Ollama sürecinin yaklaşık 20,1 GiB VRAM
> tutması nedeniyle fail-closed durdu; yarım sonuç kabul edilmedi ve mevcut
> global fallback değişmedi.
> Ardından aynı resmî kaynağın ayrı 10:37 oturumuna ait 283 publisher
> multiclass maskesi ve eş RGB sekansı bulundu. 1,69 GB tam RGB arşivi ve
> anotasyon ZIP'i safe-path/tam CRC/SHA, 283/283 pairing, 1296x966 decode,
> 18-renk exact palette, 12-pair görsel ve common-ontology kapılarını geçti.
> Eğitim manifestine ve önceki 20.765 gerçek kayda karşı exact/dHash≤2 eşleşme
> sıfırdır. Panel tek tarla/tarih/oturum oyu olarak eğitime kapalı target-like
> holdout'a alındı; strict üç-seed v3 protokolü model çıktısından önce
> donduruldu. R2 model ekranı GPU boşken kontrol BoniRob+Sorghum artifact'lerini
> tamamladı; Ollama yeniden yaklaşık 19 GiB yüklenince challenger öncesi
> kontrollü kesildi. Mevcut global fallback değişmedi.
> Güncel provenance coverage makbuzu böylece 19 dataset/21.048 gerçek kayıt,
> 18.993 common-semantic uyumlu ve 2.055 partial-kilitli kayıt doğrular. Yeni
> 283 ardışık kare toplamda yalnız bir capture group ekler.
> GPU boşken V10 R2 seed-17 ekranı daha sonra eksiksiz tamamlandı. Birleşik
> gerçek seçim skoru `+0,006884`, target-like makro `+0,003331` ve breadth
> `+0,014153` yükseldi; fakat CWFID `-0,048846`, mevcut gerçek çekirdek
> `-0,029437` ve en kötü field/session `-0,311180` geriledi. 111 alanın 21'i
> hard kapıyı kaybetti; aday reddedildi ve confirmation açılmadı.
> V10'daki bağımsız uç koşul/task-interference hipotezi için korelasyonlu
> `clear_day`, `overcast_moist`, `low_sun` ve `robot_light_low_ambient`
> profilli V11 geliştirildi. R1 crop-oranı/warmth-span, tam R2 ise iki train
> radyometri outlier'ı nedeniyle reddedildi; eşik gevşetilmedi. Yalnız bu iki
> kareyi nesnel karantinaya alan 78/16/16 karelik R2Q türevi veri kapısını
> geçti. Seed-17 A/B'de breadth `+0,002481` olsa da gerçek seçim skoru
> `-0,010073`, target-like makro `-0,015962`, SugarBeets `-0,059287` ve CWFID
> `-0,063426` oldu; 111 alanın 30'u hard kapıyı kaybetti. V11-R2Q reddedildi,
> seed 29/43 açılmadı ve frozen stop kuralı gereği bu asset hattında yeni
> model-güdümlü iterasyon yapılmayacak. Kabul edilmiş global seed-43 fallback
> değişmedi.
> Direct-mixture girişiminin kısa real-only recovery ile giderilip
> giderilemeyeceği son bir eş-hesap screen'de ölçüldü. Kontrol ve V10
> challenger aynı 4.066 gerçek train satırı, iki epoch × 3.600 draw, birebir
> sample stream/RNG ve fresh optimizer aldı; recovery'de sentetik satır
> kullanılmadı. Challenger primary/target/tail'i
> `+0,009635/+0,006222/+0,012870` artırsa da CWFID `-0,055998`, real-core
> field macro `-0,026588` ve CropAndWeed `-0,012004` geriledi. 111 alanın
> 23'ü `-0,025` hard sınırını aştı, en kötü fark `-0,312067` oldu. Target ve
> generalist screen reddedildi; seed 29/43 açılmadı ve fallback değişmedi.
> Unseen görsel kanıt ayrıca genişletildi. CC-BY-4.0 FarmBot Soy release'inin
> 659 adet 1600x1200 source karesi tam archive/decode kapısından geçti; gün
> 1-20'den modelden bağımsız seçilen 40 kare train'e exact eşleşmesiz ve
> minimum dHash mesafesi 12 ile nitel galeriye alındı. Naïo Oz resmî 1080p
> videosundan seçilen 10 karede minimum train dHash mesafesi 8'dir; lisans
> metadata'sı olmadığı için yalnız yerel, vegetation-union OOD incelemesidir.
> Kabul edilmiş global fallback ile FarmBot/Naïo/BoniRob; etiketli
> SugarBeets/RiceSEG/WeedMap ve asset/seed-ayrık V11 val/test galerileri
> tamamlandı. FarmBot'ta ileri soy evrelerinde crop→other kayması, Naïo'da
> yeşil robot→vegetation false positive, UAV/ince-weed panellerinde kaçırmalar
> görünürdür. RiceSEG global hatası ile kabul edilmiş seed-29 specialist ayrıca
> karşılaştırıldı. Kanonik galeri bütün otomatik kapıları geçti; nitel ve
> sentetik seçim ağırlığı `0,0`, spray/model kabulü ise yoktur.
> Bu asset seçimleri tarihsel epoch-15 modeli otomatik değiştirmez; yeni final
> saha testi gerektirir. Depth ve saha deployment'ı ayrı sonraki fazlardır.

## 0. Güncel icra durumu

- [x] Spot-spray PoC için instance segmentation temeli ve gerçek saha aksiyon
      kapıları kilitlendi: track P/R/F1 `≥0,98/0,95/0,965`, crop-hit
      `≤0,005`, duplicate `≤0,01`; sentetik GO ağırlığı `0`.
- [x] Aynı `1.407` gerçek train karesi ve eşit `1.487 örnek/epoch` bütçesiyle
      gerçek-replay / gerçek+V12 sentetik A/B tamamlandı. PhenoBench `≥82 px`
      F1 `0,7042→0,7258`; `%95` bootstrap aralığı sıfırı kestiği için sonuç
      olumlu fakat kesin olmayan yön sinyalidir. Aynı sabit eşiklerle BoniRob
      F1 `0,0536`: ana açık target-camera domain uyumudur.
- [x] Dondurulmuş capture baseline V2 tamamlandı: bir Basler
      `a2A2464-77ucPRO`, C23 8 mm lens, native `2048²`, `474–484 mm` FOV,
      GSD `0,231–0,236 mm/px`, `170 µs`, `15 Hz`, kapalı `600×600 mm` hood,
      dört-zone diffuse strobe ve dış `64 px` no-fire. RTX 3090 p95 kanıtı
      tek kamera/15 Hz'i taşır; 20 Hz ve ikinci kamera geçmez. A–F optik,
      ışık, transport, hareket, registration ve nozzle kapıları fiziksel
      kabulden önce zorunludur.
- [x] Sade 6 sayfa + açıklamalı 19 sayfa kontrollü spot-spray rapor paketi,
      exact V2 donanım/BOM sayfaları ve self-sufficient gerçek/sentetik
      görsellerle yeniden üretildi. Yeni ROSE sonucu entegre edilen exact
      fingerprint `0b4503f339d9232553547217c7f83af2c9234b2deb8e031e0469e2586fde4f17`,
      aynı reviewer kimliğinde cycle 4 ile `Verdict: OLDU, TAMAM` aldı.
- [x] Matched native-detail ROSE challenger aynı koşuda batch 3 ile 8/8 epoch
      tamamlandı. Seçilen `last.pt` SHA-256
      `3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100`.
      Önceki V12-destekli adaya göre PhenoBench `≥82 px` F1
      `0,7258→0,7540`, BoniRob sabit eşik F1 `0,0536→0,0896`; Pheno %95
      eşleştirilmiş fark aralığı `[-0,0136; 0,0710]` ile sıfırı kesiyor.
      V12 sentetik holdout sabit eşik F1'ı `0,6341→0,0000` olduğundan
      sentetik karar ağırlığı sıfır ve `field_fire_go=false` korunuyor.
- [x] Kapanış: güncel rapor fingerprint'inde reviewer `Verdict: OLDU, TAMAM`;
      322 test, V2 reproducibility, receipt/hash ve görsel PDF kontrolleri
      geçti. Haricî vLLM servisi çalışma boyunca durdurulmadı ve kapanışta
      çalışır durumda doğrulandı; exact obsolete çıktılar temizlenip intentional
      repo paketi kontrollü olarak commit/push edildi.
- [x] Registry, disk kontrolü, sabit URL/boyut/checksum ve lisans rolleri.
- [x] PhenoBench, ACRE, WeedsGalore, WE3DS ve ROSE dönüşümü.
- [x] CWFID development; Carrot-Weed ve EWIS1 kilitli test dönüşümü.
- [x] Ortak 0/1/2/255 ontolojisi, audit, katmanlı görsel QC ve all-role
      dHash-256 Hamming≤2 sızıntı denetimi.
- [x] `real_core_final.csv`: 6.371 örnek, train/val/test 3.864/1.637/870.
- [x] `commercial_core_we3ds.csv`: 2.957 örnek, 1.722/615/620.
- [x] Aggregate crop-risk ≤0,5%, kare-başı p99 ≤0,5% ve ihlal oranı ≤1%
      hard-gate kontratı; deterministik eğitim ve strict sampler.
- [x] Beş veri kümesi/tüm crop-ID'leri kapsayan 20-crop overfit: mIoU
      0,984304; crop IoU 0,986437; weed IoU 0,978239.
- [x] Dokuz erişilebilir aday × seed 17 gerçek-veri taraması; 9/9 run
      tamamlandı ve manifest/mask/source provenance hash'leri eşleşti.
- [x] Her run için CWFID unknown-policy kalibrasyon receipt'i ve hash'li
      tanısal checkpoint; kilitli test kullanılmadı.
- [x] DINOv2 kalite lideri + flat/frozen ConvNeXt transfer kontrolü × seed
      17/29/43 tamamlandı. Hiçbir tanısal aday tüm-seed operasyonel selector'ü
      geçmedi; `selected_checkpoint=null` sonucu saklandı.
- [x] DINOv2-Small stage-4 epoch 15 × seed 17/29/43 tamamlandı; kaynak mIoU
      0,816684 ± 0,003385, CWFID mIoU 0,536813 ± 0,021890. Semantik seçim
      makbuzu seed 17 checkpoint'ini kilitledi; spray deployment statüsü uygun
      değil.
- [x] `real_core_final.test`, Carrot-Weed ve EWIS1 seçimden sonra yalnız bir kez
      açıldı; final threshold sweep yapılmadı. Hata galerileri, ONNX opset-18
      parity, 512×512 ve 5464×3640 tiled RTX 3090 latency tamamlandı. Latency
      sırasında GPU compute açısından near-idle olsa da sleeping vLLM 752 MiB
      ayırdığı için ölçüm tam boş GPU iddiası taşımaz.
- [x] SorghumWeed v1 resmi 202/25/25 split'i indirildi, dönüştürüldü;
      polygon/overlap/duplicate/QC ve manifest provenance denetimleri geçti.
- [x] Pinli CropCraft commit'i + Blender 4.5 ile 25 scene x 4 frame = 100
      kare stock pilot üretildi; scene-ayrık 80/20 manifest ve release
      hash'leri kilitlendi. Bu ilk ablation'da custom asset kullanılmadı.
- [x] Gerçek+Sorghum kontrol, %10, %25 ve sentetik-only screen tamamlandı.
      Eşit epoch-8 bütçesinde %10 kol CWFID robust mIoU'yu `+0,017412`
      artırdı ve 3/3 seed kazandı; %25 ve sentetik-only büyütülmedi.
- [x] %10 tarifin epoch 8/15 seed 17/29/43 confirmation'ı tamamlandı.
      Epoch 15 CWFID mIoU `0,569446 +/- 0,016727`, source
      `0,813674 +/- 0,001235`, Sorghum validation `0,838798 +/- 0,005602`;
      medyan robust seed 43 kilitlendi.
- [x] Sorghum `external_test`, seçimden sonra tek kez açıldı; mIoU
      `0,834852`, crop/weed IoU `0,795266 / 0,716867`. Threshold sweep yok;
      p99 crop-risk `0,043382` ve ihlal oranı `0,04` nedeniyle safety kaldı.
- [x] Yeni checkpoint için ONNX parity, RTX 3090 512×512 ve 6000×4000 tiled
      latency, CWFID/Sorghum development hata galerileri ve 39/39 test
      tamamlandı.
- [x] Özel CC0 asset paketi üretildi: 15 erken-dönem sorgum modeli, dört
      weed ailesinde 24 model, 16 residue, üç soil PBR ve üç HDRI. Statik,
      smoke, manuel RGB/mask ve 100-kare/25-scene pilot kapıları geçti.
- [x] Özel asset `%10` kolu stock `%10` kola karşı aynı epoch-8/28.800 örnek
      bütçesinde seed 17/29/43 ile doğrulandı. Robust minimum mIoU ortalama
      `0,541634 -> 0,561939` (`+0,020305`), 3/3 seed galibiyeti; kaynak ve
      Sorghum regresyonları `0,005930 / 0,005175` ile `0,01` sınırında geçti.
      `external_test` okunmadı; seçilen temsilci seed 43 epoch-8'dir.
- [x] V2 özel paket 15 bağımsız crop geometrisi × 3 albedo fenotipi ve dört
      resmi Poly Haven CC0 kaynağından 27 texture-backed weed ile v3'e
      genişletildi. Eksik materyalli R1 smoke ve texture-existence gate'inde
      kalan R2 reddedildi; R3 static/smoke/manuel/pilot/leakage kapılarını
      geçti. V2'ye karşı aynı epoch-8/28.800 örnek bütçesinde robust mIoU
      `0,561939 -> 0,578953` (`+0,017015`), 3/3 seed galibiyeti; kaynak ve
      Sorghum da `+0,000936 / +0,003643` yükseldi. Temsilci seed 43'tür;
      development safety pass rate `0,333333` olduğundan spray-ready değildir.
- [x] CropAndWeed resmî arşivleri indirildi; 8.034 kaynaktan fail-closed
      ontolojiyle 4.584 kare kabul edildi ve 3.667/917 oturum-ayrık
      train/calibration split'i üretildi. Audit, görsel QC ve 11.142 karelik
      all-role dHash-256 Hamming≤2 denetimi geçti.
- [x] CropAndWeed `%10/%20` eşit-bütçeli ikame ekranında yeni-domain mIoU
      `+0,027100 / +0,021255` arttı; fakat CWFID `-0,050332 / -0,034447`
      geriledi ve iki aday da robust gate'te kaldı.
- [x] Eski kaynak draw'larını koruyan 4.000-example additive takipte compute
      kontrol ve `%10` additive kol da CWFID nedeniyle reddedildi. Additive
      robust delta v3'e karşı `-0,059306`, compute kontrole karşı
      `-0,033724`; kabul edilmiş v3 kontrol değişmedi.
- [x] Rice Seedling and Weed Figshare v5 arşivi checksum ile indirildi. 224
      karo/28 ana fotoğraf/tek oturum yapısı nedeniyle tamamı train-only
      tutuldu; `raw0=ignore`, `raw1=crop`, `raw2=background`, `raw3=weed`
      haritası yayın piksel oranları ve görsel QC ile doğrulandı. Aday-içi
      ve mevcut 11.394 gerçek örneğe karşı exact/dHash≤2 eşleşme yoktur.
- [x] Rice `%2,5/%5` eşit-bütçeli katkı ekranı tamamlandı. `%2,5`
      robust `+0,008422` kazandı fakat CropAndWeed `-0,010125` ile `-0,01`
      kapısını çok dar kaçırdı; `%5` robust `-0,005679` geriledi. İki
      aday reddedildi, confirmation açılmadı ve v3 kontrol korundu.
- [x] Paddy R5 asset paketi tamamlandı: 60 rice modeli/20 bağımsız
      geometri/5 evre/3 fenotip, 3 türde 36 paddy weed, 3 ıslak PBR, 3
      paddy HDRI ve sığ-su profili. Static/smoke/100-kare pilot, 12-pair
      manuel RGB-mask, semantic palette, domain-gap ve 7.129-kare
      dHash≤2 leakage kapıları geçti; eşleşme `0`.
- [x] Paddy asset seed-17 screen ve seed 17/29/43 confirmation tamamlandı.
      `%5 v3 + %5 paddy` kolu beş-domain robust minimumu ortalamada
      `0,317954 -> 0,366759` (`+0,048805`) yükseltti ve 3/3 seed kazandı.
      CWFID/Rice/macro farkları `+0,040521 / +0,048805 / +0,017722`;
      source `+0,002556`, Sorghum/CropAndWeed `-0,001063 / -0,002210`
      ile non-inferiority sınırında geçti. Temsilci seed 43 epoch-8
      `last.pt`'dir; external test ve gerçek Rice training exposure yoktur.
- [x] Soy V5 R3 asset paketi kalite denetiminden geçti: 60 crop modeli/20
      bağımsız geometri/5 evre/3 fenotip, 53 weed, 3 soil PBR, 3 HDRI ve 16
      debris. Alpha-aware semantic patch görünmez texture-card alanındaki
      38.614 hatalı weed pikselini decoded RGB'yi değiştirmeden kaldırdı.
- [x] Dondurulmuş V6 stress kompozisyon gate'i R1-R4 fail-closed
      iterasyonlarından sonra R5'te geçti: 100 karede ortalama crop/weed
      `0,035113 / 0,050702`, crop-free `0`, exact/near duplicate `0`.
      45 V5 + 45 stress additive screen GrowingSoy'da `+0,100142` kazandı,
      fakat CWFID/Rice/robust/macro regresyonları nedeniyle reddedildi.
      Yeni mesh, confirmation veya büyük sentetik üretim açılmadı.
- [x] GrowingSoy gerçek-veri gate'i tamamlandı: 1.000 kare, boylamsal
      trajectory-ayrık 541 train / 459 calibration; exact/near leakage `0`.
      `%5/%10` seed-17 katkıları in-domain büyük kazanç verse de mevcut alan
      non-inferiority kapılarında kaldı; kontrol değişmedi.
- [x] DeBlurWeedSeg publisher-test'ten 100 sharp + 100 motion-blur kare,
      tek capture-group development tanısı olarak dönüştürüldü. Kabul edilmiş
      kontrol sharp `0,525724`, blur `0,380869` üç-seed ortalama mIoU aldı;
      `-0,144855` farkla tanısal kapı 0/3 geçti ve seçimde kullanılmadı.
- [x] WeedMap 4.480.204.702 bayt arşivi HDD alanı doğrulanarak indirildi;
      SHA-256/CRC/archive-safety, 970 indexed↔color, 167.616.000 validity-mask
      pikseli, manuel overlay ve 12.818 gerçek referansa karşı leakage
      kapıları geçti. Sabit `%5` valid tabanıyla 424 train + 95 calibration
      RGB tile üretildi; Sequoia CIR dışlandı.
- [x] WeedMap `%2,5/%5` eşit-bütçeli seed-17 ekranı tamamlandı. WeedMap mIoU
      `+0,160505 / +0,177702` arttı; CWFID `-0,050411 / -0,060024` düştü.
      `%2,5` CropAndWeed/mevcut-macro, `%5` ayrıca Rice/mevcut-robust
      kapılarını kaybetti. İki aday reddedildi ve üç-seed confirmation
      açılmadı; kabul edilmiş paddy R5 kontrolü korundu.
- [x] Tobacco Aerial v2'nin 3.194.827.845 baytlık dış arşivi ve iki nested
      release'i SHA-256/tam CRC ile doğrulandı. 2.520 patch, 8 campaign ve 210
      parent blok ortak ontolojiye çevrildi; 1.536 train / 984 calibration ve
      içerikten bağımsız dengeli 720/240 altküme üretildi. Campaign 1'in
      uyumsuz 1080p ağacı karantinaya alındı; patch ağacı iki release arasında
      byte-identical ve mekânsal tutarlı bulundu. Görsel QC, manifest ve
      13.337 gerçek referansa karşı exact/dHash≤2 leakage kapıları geçti.
- [x] Tobacco `%4,7619` replay-preserving additive ekranı kabul edilmiş ve
      3.780-draw eşit-hesap kontrollerine karşı tamamlandı. Tobacco mIoU
      `+0,011261 / +0,010009` arttı; ancak kabul edilmiş kontrole karşı
      CWFID/Rice/CropAndWeed `-0,045959 / -0,027045 / -0,021172`, mevcut
      macro `-0,011881` oldu. İki-kontrollü gate reddetti; seed 29/43 açılmadı
      ve paddy R5 kontrolü korundu.
- [x] RiceSEG resmî site/Hugging Face kaydı doğrulandı: 3.078 yüksek
      çözünürlüklü görüntü, 5 ülke, 12 kurum ve tam büyüme döngüsü en yüksek
      değerli coverage adayıdır. Kullanıcı erişim koşulunu kabul etti;
      commit `1a891ced...`, altı dosya ve `1.564.399.537` bayt remote preflight
      ile doğrulandı. Pinli acquisition config/script; exact-set, boyut,
      SHA-256, 50 GiB rezerv, archive-safe-path/symlink/full-CRC ve receipt
      kapılarıyla hazırlandı ve yerel kimlik doğrulamasından sonra tam release
      veri diskine indirildi.
- [x] RiceSEG 3.078 RGB/maske çifti için exact repository, SHA-256, archive/CRC,
      `512x512` decode, `0..5` palette, pairing, 19 subdataset, metadata ve
      95-hücre manuel görsel kapıları geçti. 17.688 önceki gerçe karşı
      exact/dHash≤2 eşleşme `0`; aynı-train tek çatışmalı yakın kopya
      karantinaya alındı. Kalite-kapılı coverage `2.473 train / 604
      calibration`, alternatif country-transfer `1.823/1.254` ve birbirinden
      ayrı tutulur.
- [x] RiceSEG `%4,7619` expected-volume additive ve `%2,38095` low-dose
      seed-17 ekranları hedef RiceSEG/reproductive alanını `+0,33/+0,37`
      düzeyinde iyileştirdi; kabul edilmiş kontrole karşı CWFID ve/veya Sorghum
      kapılarında kaldı. Eşikler gevşetilmedi, seed 29/43 açılmadı.
- [x] Sampler akış auditi dataset içinde field/session gruplarının uniform
      seçildiğini doğruladı; metadata cap/subset uygulanmadı. V1/V2 eski
      akış pozisyon eşleşmesi yalnız `162/28.778` ve `352/28.800` oldu.
- [x] V3 sabit 3.600-draw exact-index replacement ekranı her epoch 90 RiceSEG
      draw'u ve 3.510/3.510 birebir eski pozisyonla tamamlandı. RiceSEG/
      reproductive `+0,323059 / +0,378183`, CWFID `-0,006124` oldu; source,
      Sorghum, CropAndWeed ve existing-robust kapıları nedeniyle reddedildi.
      Kabul edilmiş global model değişmedi; yeni global oran araması kapatıldı.
- [x] WeedyRice-RGBMS-DB'nin 5.288.295.277 bayt dış ve 5.287.951.115 bayt
      nested arşivi SHA-256/tam CRC/archive-safety ile doğrulandı. 734 RGB,
      734 binary maske, 2.936 multispectral görüntü ve metadata sayımları
      release ile birebir eşleşti; görsel QC ve 15.857 gerçek referansa karşı
      exact/dHash<=2 leakage kapıları geçti. Dört uçuşu bütün publisher
      split'lerine dağıtan 438/148/148 listeleri reddedildi.
- [x] Weedy Rice ontolojisi fail-closed tutuldu: kaynak `255 -> common weed`,
      kaynak `0 -> ignore`. Üç Thoaison uçuşunun 487 karesi ayrı partial-label
      loss protokolü olmadan ortak eğitime kapalıdır; 247 Longxuyen karesi
      yalnız uçuş-ayrık binary external-calibration tanısıdır. Seed 17/29/43
      zero-shot sonuçlarında semantic IoU `0,597835` olsa da specificity
      `0,068876` ve predicted-positive `0,966940`; source-frozen weed IoU
      `0,000064` oldu. Model seçilmedi ve paddy R5 kontrolü değişmedi.
- [x] CamelinaWeed v1 merkez-dizin ile tarandı ve tam 69.007.560.436 bayt
      yerine yalnız annotated ZIP kayıtları range-fetched edildi. 1.120 JPEG,
      12 JSON ve 4.474 annotation exact release ağacıyla doğrulandı; 31
      açıklamasız `k` annotation ve iki boş polygon ignore edildi. 1.097
      pozitif partial maske, 999 Thessaloniki train adayı ve 98 konum-ayrık
      Chalkidiki calibration satırı içerik/görsel/leakage kapılarını geçti.
      Ortak ve positive-only eğitim ayrı frozen loss protokolüne kadar kapalıdır.
- [x] Güncel gerçek-veri coverage matrisi on hash-kilitli manifestten 18
      dataset/20.765 kayıt/575 capture group doğruladı. 18.710 kayıt
      common-semantic uyumlu, 2.055 kayıt partial-training-locked'tır; audit
      pixel/external-test/model çıktısı okumadı. RiceSEG global model gate'i
      daha sonra tamamlanıp reddedildi; yeni dense çok-saha artifact >
      crop/domain-conditioned specialist sırası donduruldu.
- [x] Sentetik asset kapsamı ölçülmüş açığa göre audit edildi: yeni rastgele
      botanik mesh yerine 32 prosedürel CC0 linear/curved camera-shake PSF ve
      200-kare dryland+paddy V7-R1 pilot üretildi. 18/18 otomatik kontrol,
      12-strata manuel review, 200/200 manifest ve 15.857 gerçek referansa
      exact/dHash≤2 leakage `0` ile geçti.
- [x] V7-R1 `%2,439` motion additive model screen'i eşit-hesap kontrolle
      tamamlandı. Motion-blur hedefi `+0,064939 / +0,069539`, matched sharp
      `+0,023246 / +0,026579` yükseldi; fakat CWFID/WeedMap ve existing
      robust/macro kapıları kaybedildi. Aday reddedildi, seed 29/43 açılmadı;
      asset stress/specialist girdisi olarak tutuldu ve R5 kontrol değişmedi.
- [x] V7-R2 aynı 200 motion RGB/PSF'sinde confidence `<0,50` blur-boundary
      uncertainty maskesi üretti; `%2,2551` piksel ignore oldu ve diğer valid
      pikseller relabel edilmedi. Otomatik/manuel/manifest kapıları geçti.
      `%0,625` eşit-compute screen GrowingSoy'da `+0,050333` sağladı; fakat
      motion-blur `-0,004755`, CWFID `-0,072316` ve macro kapıları kaldı.
      Aday reddedildi, seed 29/43 açılmadı ve R5 kontrol değişmedi.
- [x] Sentetik asset portföy v8 auditi dryland, paddy, soy/stress ve iki
      sensor-motion aşamasının 5/5 asset-quality gate'ini yeniden SHA-kilitledi.
      Yalnız dryland V3 ve paddy R5 globally useful kabul aşamasıdır; son üç
      kaliteli asset ortak model gate'inde reddedildi. RiceSEG gerçek strata
      auditi gelmeden kanıtsız yeni asset/büyük batch üretimi kapatıldı.
- [x] RiceSEG strata/semantik auditi kabul edilmiş paddy R5 paketinde en büyük
      açığı `late_reproductive_rice` olarak seçti. R1 ve R2 manuel morfoloji
      kapısında reddedildikten sonra R3; 48 model/24 geometri, 4 evre, 3
      generated-texture fenotipi ve 100-kare scene-ayrık pilotla statik,
      smoke, manuel, 6/6 RiceSEG düşük-mertebe dağılım, manifest ve 20.765
      gerçe karşı leakage kapılarını geçti.
- [x] R3 `%2,5` eşit-bütçeli seed-17 model ekranı tamamlandı. RiceSEG/saf
      reproductive/early-rice mIoU farkları `+0,141180 / +0,101863 /
      +0,132369`, source/Sorghum da `+0,009844 / +0,014379` oldu. CWFID ve
      CropAndWeed `-0,039529 / -0,016026` ile `-0,01` kapısını kaybetti;
      aday reddedildi, 3-seed confirmation açılmadı ve R5 kontrol korundu.
- [x] RiceSEG crop-routed specialist doz ekranı tamamlandı. `%2,38/%10/%25/
      %50` sabit-compute seed-17 kollarında robust early/full/reproductive
      minimumunu `%2,38` kazandı; daha yüksek dozlar full skoru artırsa da
      reproductive minimumu geçemedi.
- [x] RiceSEG specialist paired seed `17/29/43` confirmation'ı 5/5 kapı ve
      3/3 robust galibiyetle geçti. Temsilci specialist seed 29'dur; global
      seed-43 fallback byte düzeyinde değişmedi. Route yalnız kesin haricî
      `crop_id=12 / Oryza sativa` metadata'sıyla açılır.
- [x] BAWSeg resmî landing/content-ID ve disk ön-kontrolü geçti. Görünen
      `7.5 GB` arşiv 12 GiB hard limit ve 100 GiB indirme-sonrası rezerv
      içinde; HDD'de yaklaşık 279 GiB boşluk var. Extraction, merkez-dizin
      gerçek boyutu görülmeden açılmaz.
- [x] V10 field-robustness asset paketi 14 soil/14 HDRI ile tamamlandı.
      Train/val/test asset ve seed aileleri ayrık; nem, tillage, clod, doğal ve
      robot ışığı, lokal gölge parametreleri ölçümlü açıklık kapılarını geçti.
- [x] V10 split-aware pilot 48 train + 12 synthetic-val + 12 synthetic-test
      kareyle üretildi. 72/72 RGB-mask/palette/radyometri kontrolü, manuel
      contact-sheet incelemesi ve common 0/1/2 manifest dönüşümü geçti.
      Synthetic val/test gerçek seçim skorunda `0,0` ağırlıktadır.
- [x] Hedefe yakın gerçek datasetleri öne alan field/session→dataset macro
      scorer donduruldu: `%60` target-like, `%25` breadth, `%15` alt-kuyruk;
      dataset satır/piksel sayısı ağırlığı yasak. Yeni holdout sonrası tam
      seed `17/29/43` kümesini zorunlu kılan strict v3 de donduruldu.
- [x] CC-BY-SA-4.0 Sugar Beets 2016 BoniRob JAI-RGB 31-kare unseen sequence
      indirildi, gerçek 1 Hz MP4'e çevrildi ve global fallback ile çalıştırıldı.
      Görsel hata modu kaydedildi; etiketsiz olduğundan mIoU ve model seçimi yok.
- [x] V10 seed-17 sabit `%10` sentetik bütçeli model pre-screen tamamlandı.
      Gerçek skor `+0,006884` olmasına karşın CWFID/real-core ve 21/111 alan
      non-inferiority kapısını kaybetti; aday reddedildi, seed 29/43 açılmadı.
- [x] V11 profilli sentetik takip tamamlandı. R1 iki üretim gate'inde, tam R2
      iki train radyometri outlier'ında reddedildi. Eşik gevşetmeden yalnız
      bu iki kareyi karantinaya alan R2Q türevi 78 train + 16 val + 16 test
      kareyle tüm türetilmiş-veri kapılarını geçti; sentetik val/test'in
      gerçek skor ağırlığı `0,0` kaldı.
- [x] V11-R2Q seed-17 gerçek-domain A/B tamamlandı. Hedef makro
      `-0,015962`, birleşik skor `-0,010073`, CWFID `-0,063426` ve
      SugarBeets `-0,059287`; 30/111 alan hard kapıyı kaybetti. Aday
      reddedildi, confirmation açılmadı ve global seed-43 model korundu.
- [x] Eğitimle field/session örtüşmeyen gerçek robot-camera holdout: elle
      çizilecek 8–12 kare yerine resmî 283 exhaustive BoniRob RGB/multiclass
      çifti tüm release/leakage kapılarını geçti. Korelasyon nedeniyle tamamı
      tek field/session ve tek dataset oyudur; training ve deployment kapalıdır.
- [x] V10 sonrası eş-hesap real-only recovery tamamlandı. Primary/target/tail
      ortalamaları artsa da CWFID, real-core field macro, CropAndWeed ve
      23/111 field non-inferiority kapısı kaybedildi. Target/generalist
      confirmation açılmadı ve global fallback değişmedi.
- [x] FarmBot Soy 2026 release'i archive/CRC/decode/metadata-karantina ve
      kapasite kapılarından geçti. Gün 1-20'den 40 near-nadir model-unseen kare
      train exact/dHash sızıntı kontrolüyle nitel galeriye alındı; dense mask
      olmadığı için accuracy ve training kapalıdır.
- [x] Naïo Oz resmî videosundan 10 model-unseen kare kilitlendi. Farklı ölçek,
      greenhouse/açık tarla, tool occlusion ve robot görünümü içerir; yalnız
      vegetation-union yorumu ve yerel analiz yetkilidir.
- [x] Kabul edilmiş modelin gerçek/sentetik unseen görsel galerisi tamamlandı:
      FarmBot 40, Naïo 10, BoniRob 31; SugarBeets/RiceSEG/WeedMap best-worst
      ve V11 val/test 16+16. Rice metadata route'u için seed-29 specialist
      companion galerisi de üretildi. Kanonik index tüm kapıları geçti.
- [x] Self-contained segmentasyon görsel raporu V2 tamamlandı. Altı
      seen-dataset validation/holdout tam-split metriği ve BEST/WORST uçları,
      RiceSEG specialist, 81 etiketsiz gerçek kare, üç etiketli transfer paneli
      ve V11 sentetik stres galerileri ortak legend'le tek klasörde toplandı.
      Paket 40 contact sheet + 313 tekil görsel içerir; etiketsiz accuracy
      kapalı, checkpoint/training-manifest hash'leri kilitli, yayın-içi yollar
      temiz ve 353 ana JPEG'in decode kapısı geçmiştir.
- [x] Obsolete depolama temizliği tamamlandı. Doğrulanmış archive/extracted
      duplikaları, 247 tarihsel/reddedilmiş checkpoint, sekiz eski ONNX,
      başarısız/superseded sentetik asset-render iterasyonları ve debug/cache
      çıktıları kalıcı silinerek `120.478.003.200` bayt geri kazanıldı. Yalnız
      kabul edilmiş global seed-43 ve Rice specialist seed-29 ağırlıkları
      korundu; 17.845 aktif manifest satırı, checkpoint hash'leri ve final
      görsel rapor silme sonrasında tekrar doğrulandı.
- [ ] BAWSeg kimlik doğrulamalı IEEE DataPort indirmesi. `Subscription
      Required`; arşiv gelince safe-path/symlink/manifest, full CRC, iç SHA,
      extraction kapasitesi ve `LICENSE.txt` insan incelemesi zorunludur.
      Bunlar geçmeden eğitim ve ticari kullanım kapalıdır.

Bu segmentasyon fazının tamamlanma kapsamına depth, Unreal/robot fiziği, büyük
sentetik batch üretimi, özel-asset epoch-15 confirmation, few-shot/SAM
insan-zamanı deneyi ve Jetson/TensorRT dahil değildir; her biri yeni test
kilidiyle ayrı fazdır.

Kanonik makbuzlar:

- real-only freeze: `data/processed/audits/real_segmentation_freeze_v1.json`
- sentetik oran seçimi:
  `data/runs/simulation_ablation_confirm_v1/ratio_selection.json`
- final tarif/checkpoint kilidi:
  `data/runs/simulation_winner_epoch15_confirm_v1/training_budget_selection.json`
- tek-sefer final erişimi:
  `data/runs/final_real_synthetic_v1/sorghum_weed_external_test_receipt.json`
- özel asset seçimi:
  `data/runs/simulation_asset_quality_selection_v2.json`
- texture-backed v3 asset seçimi:
  `data/runs/simulation_asset_quality_selection_v3.json`
- CropAndWeed ikame seçimi:
  `data/runs/real_data_cropandweed_screen_selection_v1.json`
- CropAndWeed additive seçimi:
  `data/runs/real_data_cropandweed_additive_screen_selection_v1.json`
- CropAndWeed nihai veri/model kararı:
  `data/runs/real_data_cropandweed_final_selection_v1.json`
- Rice screen seçimi:
  `data/runs/real_data_rice_seedling_weed_screen_selection_v2.json`
- Rice nihai veri/model kararı:
  `data/runs/real_data_rice_seedling_weed_final_selection_v1.json`
- Paddy R5 asset screen kararı:
  `data/processed/audits/cropcraft_paddy_asset_screen_selection_v4_r5.json`
- Paddy R5 asset confirmation kararı:
  `data/processed/audits/cropcraft_paddy_asset_confirmation_selection_v4_r5.json`
- Soy V6 stress iterasyon defteri:
  `data/processed/audits/cropcraft_soy_stress_iteration_ledger_v6.json`
- Soy V6 stress kompozisyon kararı:
  `data/processed/audits/cropcraft_soy_stress_composition_v6_r5.json`
- Soy V6 gerçek-veri leakage denetimi:
  `data/processed/audits/cropcraft_soy_stress_vs_all_real_duplicates_v6_r5.json`
- Soy V5+V6 additive model kararı:
  `data/processed/audits/cropcraft_soy_mix_additive_screen_selection_v6_r5.json`
- Soy asset kalite/gate raporu:
  `docs/SIMULATION_SOY_ASSET_QUALITY_REPORT_V5.md`
- GrowingSoy gerçek-veri screen kararı:
  `data/processed/audits/real_data_growingsoy_screen_selection_v1.json`
- DeBlurWeedSeg motion-blur tanısı:
  `data/processed/audits/deblurweedseg_motion_blur_diagnostic_v1.json`
- WeedMap conversion ve kalite makbuzu:
  `data/processed/manifests/weedmap_conversion.json`
- WeedMap dondurulmuş screen kararı:
  `data/processed/audits/real_data_weedmap_screen_selection_v1.json`
- Tobacco Aerial kalite/model gate raporu:
  `docs/REAL_DATA_TOBACCO_AERIAL_AUDIT_V1.md`
- Tobacco Aerial dondurulmuş screen kararı:
  `data/processed/audits/real_data_tobacco_aerial_screen_selection_v1.json`
- Sensor-motion asset/model gate raporu:
  `docs/SIMULATION_SENSOR_MOTION_ASSET_QUALITY_REPORT_V7.md`
- Sensor-motion dondurulmuş screen kararı:
  `data/processed/audits/cropcraft_sensor_motion_additive_screen_selection_v7_r1.json`
- Sensor-motion uncertainty R2 dondurulmuş screen kararı:
  `data/processed/audits/cropcraft_sensor_motion_uncertainty_screen_selection_v7_r2.json`
- RiceSEG pinli acquisition config/aracı:
  `configs/data/riceseg_acquisition_v1.yaml` ve
  `scripts/acquire_riceseg.py`
- RiceSEG pre-content split/release kapısı:
  `configs/data/riceseg_release_gate_v1.yaml`,
  `scripts/inspect_riceseg_release.py` ve
  `docs/REAL_DATA_RICESEG_PREFLIGHT_V1.md`
- RiceSEG nihai kalite/uygun manifest makbuzu:
  `data/processed/audits/riceseg_quality_gate_v1.json`
- RiceSEG gerçek-veri sampler/model gate raporu:
  `docs/REAL_DATA_RICESEG_MODEL_GATE_V1.md`
- RiceSEG exact-index V3 seçim makbuzu:
  `data/processed/audits/real_data_riceseg_exact_replay_screen_selection_v3.json`
- RiceSEG specialist doz ekranı ve üç-seed confirmation kararları:
  `data/processed/audits/riceseg_specialist_dose_screen_selection_v1.json` ve
  `data/processed/audits/riceseg_specialist_confirmation_selection_v1.json`
- RiceSEG specialist nihai raporu:
  `docs/REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`
- BAWSeg kamu/disk ön-kontrol makbuzu ve raporu:
  `data/processed/audits/bawseg_remote_preflight_v1.json` ve
  `docs/REAL_DATA_BAWSEG_PREFLIGHT_V1.md`
- BAWSeg fail-closed edinim config/aracı:
  `configs/data/bawseg_acquisition_v1.yaml` ve `scripts/acquire_bawseg.py`
- DINOv3 metadata/lisans/payload erişim ön-kontrolü:
  `docs/MODEL_DINOV3_ACCESS_PREFLIGHT_V1.md`
- RiceSEG-koşullu reproductive R3 asset/pilot nihai kapısı:
  `data/processed/audits/cropcraft_reproductive_final_gate_v9_r3.json`
- Reproductive R3 kalite/model karar raporu:
  `docs/SIMULATION_REPRODUCTIVE_RICE_ASSET_QUALITY_REPORT_V9.md`
- Reproductive R3 eşit-bütçeli seed-17 model kararı:
  `data/processed/audits/cropcraft_reproductive_asset_screen_selection_v9_r3.json`
- Weedy Rice nihai veri-kalite makbuzu:
  `data/processed/audits/weedy_rice_uav_quality_v1.json`
- Weedy Rice dondurulmuş zero-shot tanısı:
  `data/processed/audits/weedy_rice_uav_binary_diagnostic_v1.json`
- Weedy Rice edinim/ontoloji/split/model-karar raporu:
  `docs/REAL_DATA_WEEDY_RICE_UAV_AUDIT_V1.md`
- CamelinaWeed nihai veri-kalite makbuzu:
  `data/processed/audits/camelinaweed_quality_v1.json`
- CamelinaWeed seçmeli edinim/ontoloji/split raporu:
  `docs/REAL_DATA_CAMELINAWEED_AUDIT_V1.md`
- Hash-kilitli gerçek-veri coverage matrisi:
  `data/processed/audits/real_data_coverage_matrix_v2.json` ve
  `docs/REAL_DATA_COVERAGE_MATRIX_V2.md` (v1 tarihsel temel olarak korunur)
- Sentetik asset portföyü ve bir sonraki gate kilidi:
  `data/processed/audits/synthetic_asset_portfolio_v8.json` ve
  `docs/SYNTHETIC_ASSET_OPTIMIZATION_STATUS_V8.md`
- Potato Weed v2 dense-mask uygunluk ret makbuzu:
  `data/processed/audits/potato_weed_v2_candidate_screening.json`
- Güncel gerçek-veri coverage raporu:
  `docs/REAL_DATA_COVERAGE_AUDIT_V3.md`
- Tarla-bağımsızlığı, V10 sentetik stres ve unseen BoniRob audit raporu:
  `docs/FIELD_ROBUSTNESS_VALIDATION_V10.md`
- V10/V11 nihai model kapısı, R2Q karantina defteri ve domain sonuçları:
  `docs/FIELD_ROBUSTNESS_VALIDATION_V11.md`
- V10 sentetik release/visual/conversion makbuzları:
  `data/synthetic/cropcraft/field_robustness_pilot_v10_r1/release_receipt.json`,
  `data/synthetic/cropcraft/field_robustness_pilot_v10_r1/visual_review_receipt.json`
  ve
  `data/processed/manifests/cropcraft_field_robustness_pilot_v10_r1_conversion.json`
- Hedef-ağırlıklı strict v2 ve V10 prescreen protokolleri:
  `configs/benchmark/target_weighted_field_robustness_v2.yaml` ve
  `configs/benchmark/target_weighted_field_robustness_prescreen_v10_r2.yaml`
- V10/V11 nihai tek-seed skor makbuzları:
  `data/processed/audits/target_weighted_field_robustness_prescreen_v10_r2.json`
  ve
  `data/processed/audits/target_weighted_field_robustness_prescreen_v11_r2q.json`
- V11-R2Q kabul edilmiş türetilmiş manifest/conversion makbuzu:
  `data/processed/manifests/cropcraft_field_robustness_pilot_v11_r2q.csv` ve
  `data/processed/manifests/cropcraft_field_robustness_pilot_v11_r2q_conversion.json`
- BoniRob unseen-sequence model/audit makbuzları:
  `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/unseen_sequence_evaluation.json`
  ve
  `data/processed/audits/sugarbeets2016_bonirob_unseen_accepted_model_v1/manual_visual_review.json`
- Sentetik çeşitlilik sonrası real-only recovery protokolü ve kararları:
  `docs/SIMULATION_DIVERSITY_REAL_RECOVERY_V1.md`,
  `data/processed/audits/target_weighted_real_recovery_v1.json` ve
  `data/processed/benchmark/simulation_diversity_real_recovery_v1/selection_seed17.json`
- FarmBot/Naïo edinim, seçim ve unseen görsel galeri raporu:
  `docs/UNSEEN_VISUAL_GALLERY_V1.md`
- Kanonik unseen görsel galeri index'i ve manuel incelemesi:
  `data/processed/audits/unseen_visual_gallery_v1/gallery_index.json` ve
  `data/processed/audits/unseen_visual_gallery_v1/manual_prediction_review.json`
- Self-contained V2 görsel raporu, özet ve hash indeksi:
  `data/processed/audits/segmentation_visual_report_v2/README.md`,
  `data/processed/audits/segmentation_visual_report_v2/CONTACT_SHEETS/00_LEGEND_AND_INDEX.jpg`
  ve
  `data/processed/audits/segmentation_visual_report_v2/report_index.json`
- Kalıcı obsolete-veri temizliği makbuzu:
  `data/processed/audits/storage_cleanup_obsolete_v1.json`

## 1. Projenin temel amacı

İlk AI PoC’nin amacı, robot veya traktöre yakın üstten bakışlı RGB görüntülerden:

```text
soil/background
target crop
other vegetation/weed
unknown/no-spray
```

maskeleri üretmektir.

İlk ürün çıktısı:

```text
RGB görüntü
→ crop / weed / soil segmentasyonu
→ crop güvenlik alanı
→ güvenli weed bölgeleri
→ ilaçlama hedef pikselleri
```

olacaktır.

İlk aşamada:

* Hastalık sınıflandırması yapılmayacak.
* Her yabani ot türü ayrı ayrı tanınmayacak.
* Depth modeli segmentasyon modeline bağlanmayacak.
* Robot actuator kontrolü tamamlanmayacak.
* Tek veya en fazla iki kamera kullanılacak.
* Edge deployment hedefi maksimum Jetson Orin olacak.

Ana öncelik:

> **Yeni tarla, ürün evresi ve kamera koşullarında düşük crop hatasıyla genellenebilen segmentasyon.**

Depth ve gerçek XYZ koordinatı ikinci aşamadır.

---

# 2. Asıl teknik darboğaz

Asıl darboğaz en büyük veya en güçlü modeli bulmak değil:

> **Kamera, tarla, toprak, ışık, ürün, büyüme evresi ve yabani ot dağılımı değiştiğinde oluşan domain shift.**

Tek bir eğitimle bütün koşullarda kusursuz çalışacak model elde etmek zor olabilir. Ancak bu şu anlama gelmez:

```text
Her yeni arazi
→ sıfırdan yeni model eğit
```

Doğru saha akışı:

```text
Genel base model
    ↓
Yeni arazide kilitli test
    ├── yeterliyse → modeli değiştirme
    ├── yalnız confidence bozuksa → threshold kalibrasyonu
    └── crop/weed ayrımı yetersizse
           → 10/25/50 kaliteli görüntü
           → SAM ön etiketi
           → insan düzeltmesi
           → küçük adapter/decoder güncellemesi
```

Her arazi için yeniden eğitim zorunlu olmayacaktır. Aynı:

* hedef ürün,
* büyüme evresi,
* kamera sistemi,
* kamera yüksekliği,
* benzer coğrafi koşullar

içindeki farklı tarlaların ortak bir model veya adapter kullanması hedeflenmelidir.

PoC’nin önemli çıktılarından biri şu adaptasyon eğrisidir:

```text
0 etiket
10 düzeltilmiş görüntü
25 düzeltilmiş görüntü
50 düzeltilmiş görüntü
```

Bu eğri, sistemin gerçekten az veriyle adapte olup olmadığını gösterecektir.

---

# 3. Model mimarisi

## Ana model

Ana model peşinen ilan edilmedi. Bu fazda erişilebilir ve lisans durumu kayıtlı
dokuz aday aynı dondurulmuş veri/güvenlik protokolünde karşılaştırıldı:

```text
ConvNeXt-Tiny FPN: flat/factorized, frozen/stage4, safety/dropout ablation
DINOv2-Small FPN: frozen transfer kontrolü
SegFormer-B2: deploy-edilebilir transformer kontrolü
```

DINOv3 ConvNeXt-Tiny gated'dir. Hugging Face oturumu RiceSEG için geçerli
olsa da DINOv3 `config.json`/weight payload isteği `401/403` ile reddedildi;
ayrı model koşulları hesap sahibi tarafından henüz kabul edilmemiştir. Sonuç
ancak gerçekten çalıştırılan erişilebilir adaylar arasında geçerlidir;
DINOv3 ileride güncel accepted-control'a karşı ayrı, lisans/erişim kontrollü
ablation'dır.

Benchmark sonucu:

```text
DINOv2-Small FPN
+ factorized crop-conditioned head
+ backbone stage 4 fine-tuning
+ conditioning dropout 0.5
+ real core + Sorghum train + %10 CropCraft sampler exposure
+ epoch 15 / median robust seed 43 checkpoint
```

Bu tarif erişilebilir/test edilen adaylar içindeki **robust semantik kalite
lideridir**. Sorghum external test mIoU 0,834852'dir; ancak aynı testte
kare-başı crop-risk p99 0,043382 ve ihlal oranı 0,04'tür. Eski Carrot-Weed
başarısızlığı, CWFID hata kuyruğu ve Sorghum'un tek çiftlik olması da
korunmuş sınırlardır. Bu nedenle operasyonel ilaçlama modeli, global en iyi
model veya unseen-field kanıtı diye etiketlenmez.

Decoder yalnızca standart operatörler kullanmalıdır:

* Conv2D,
* 1×1 ve 3×3 convolution,
* bilinear upsampling,
* concatenation veya addition,
* standart activation ve normalization.

Ağır transformer decoder, deformable attention veya özel CUDA operatörleri kullanılmayacaktır.

Bu tercih:

* az öğrenilen parametre,
* küçük veride daha düşük overfit riski,
* kolay ONNX export,
* kolay TensorRT FP16 deployment

sağlar.

## Crop-conditioned yapı

`weed` tek başına görsel bir kategori değildir. Aynı bitki bir tarlada ürün, başka bir tarlada yabani ot olabilir.

Bu nedenle model:

```text
RGB + target_crop_id
```

almalıdır.

Önerilen iki-head yapı:

```text
DINOv2-Small features
       │
       ├── Vegetation head
       │     vegetation / background
       │
       └── Crop-conditioned head
             target crop / other vegetation
```

Nihai karar:

```text
weed = vegetation AND NOT target_crop
```

Model güvenli karar veremiyorsa:

```text
unknown / no-spray
```

üretir.

Bu yapı farklı datasetleri daha doğru biçimde ortak çatı altında toplamayı kolaylaştırır.

---

# 4. Transfer learning ve teacher–student ayrımı

İlk sistemin doğru adı klasik teacher–student değildir.

İlk kullanılacak akış:

```text
SAM
→ otomatik maske önerisi
→ insan hataları düzeltir
→ düzeltilmiş verilerle benchmark'ta seçilen backbone decoder/adapter'ı eğitilir
```

Bu:

> **Model destekli anotasyon + supervised transfer learning**

akışıdır.

Gerçek teacher–student daha sonra kullanılabilir:

```text
Eğitilmiş güvenilir model = teacher
→ etiketsiz görüntülere yüksek güvenli pseudo-label
→ gerçek + pseudo-label verileri
→ student eğitimi
```

Ancak pseudo-label aşaması ilk PoC’ye eklenmeyecektir. Önce 10/25/50 gerçek düzeltilmiş görüntüyle supervised adaptasyonun çalışması gerekir.

Güncelleme sırası:

```text
1. Crop embedding + decoder
2. Gerekirse ConvNeXt stage 4
3. Gerekirse stage 3
4. Tüm backbone yalnızca son seçenek
```

---

# 5. Gerçek dataset stratejisi

Amaç bütün datasetleri körlemesine birleştirmek değil:

> **Bağımsız tarla, kamera, ülke, ürün ve büyüme evresi çeşitliliğini mümkün olduğunca kapsamak.**

## Ana gerçek eğitim havuzu

```text
PhenoBench
ACRE
WeedsGalore
WE3DS
ROSE
```

Gerçekleşen kanonik araştırma manifesti `real_core_final.csv`, bu beş
kaynaktan 6.371 görüntüdür. `commercial_core_we3ds.csv`, fiziksel olarak
`commercial_allowed=true` olan ACRE + WeedsGalore + WE3DS satırlarından 2.957
görüntülük ayrı bir track'tir. Bu teknik bayrak hukuki onay değildir.

Kontrollü ikinci fazda SorghumWeed resmi split'i ayrı bir ablation olarak
eklendi: 202 train, 25 `external_calibration` ve tarif/checkpoint kilidinden
sonra tek sefer açılan 25 `external_test`. Bu veri tek isimli çiftlikten
geldiği için resmi test ayrı görüntülerden oluşsa da unseen-field kanıtı
sayılmaz.

Bu kaynaklar:

* robot veya yakın saha perspektifi,
* farklı ürün türleri,
* farklı yabani ot morfolojileri,
* büyüme evreleri,
* gerçek ışık ve toprak

açısından mevcut ana çekirdeği oluşturur.

## Yeni gerçek-veri kaynaklarının güncel durumu

| Kaynak | Durum / karar |
|---|---|
| SugarBeets2016 | Tamamlandı: ayrı 10:37 BoniRob oturumundaki 283 resmî RGB/multiclass çifti release/leakage kapılarını geçti; tek field/session ve tek dataset oyu olarak eğitime kapalı development holdout'a alındı. V10/V11 karşılaştırmasında tüketildi; deployment kanıtı değil |
| VegAnn | Ertelendi: vegetation-only kısmi etiketler için partial-label loss ablation'ı gerekli |
| BAWSeg | Kimlik doğrulama bekliyor: 7.5 GB resmî IEEE DataPort ZIP/content-ID ve disk kapısı doğrulandı; `Subscription Required`. Merkez-dizin/CRC/iç-SHA/lisans geçmeden extraction ve eğitim yok |
| CWD30-S | Beklemede: resmî sayfada semantic release hâlâ `Coming Soon` |
| Weeds-Banana | İndirilmeden elendi: 272 patch tek uçuş/tek orthomosaic weed-only kaynağıdır; 4,32 GB paket bağımsız-domain coverage sağlamaz |
| CoFly-WeedDB | Ertelendi: 201 kare tek cotton field/mission ve yalnız weed türleri; crop sınıfı olmayan partial-label tekrar |
| Potato Weed v2 | Elendi: 813 RGB+etiket arşivi CRC geçti, fakat 6.014 anotasyonun tamamına yakını box/dört-köşe dikdörtgen; dense semantic maske değildir |
| GrowingSoy | Tamamlandı: trajectory-ayrık kalite gate'i geçti; `%5/%10` ortak-model kolları CWFID ve diğer alan regresyonları nedeniyle reddedildi |
| DeBlurWeedSeg | Tamamlandı: publisher-test sharp/blur yalnız tek-saha development tanısı; model seçmedi |
| WeedMap | Tamamlandı: 424 train + 95 calibration kalite gate'i geçti; `%2,5/%5` ortak-model kolları CWFID/CropAndWeed/Rice etkileri nedeniyle reddedildi |
| Tobacco Aerial | Tamamlandı: 1.536 train + 984 campaign-ayrık calibration kalite gate'i geçti; `%4,7619` additive kol cross-domain non-inferiority nedeniyle reddedildi |
| WeedyRice-RGBMS-DB | Tamamlandı: 734 RGB+binary maske ve uçuş-ayrık rol kalite gate'ini geçti; 487 partial-label train adayı loss protokolü bekliyor, 247 Longxuyen zero-shot tanısı mevcut modelin cultivated-rice/weedy-rice ayrımını geçemediğini gösterdi |
| RiceSEG | Tamamlandı: 3.077 uygun; 2.473 train + 604 grup-ayrık calibration kalite gate'ini geçti; 3 global-mixture ekranı reddedildi; ayrı `%2,38095` metadata-routed specialist 3-seed kabul edildi |

Hiçbir kaynak ana benchmark'a sessizce eklenmez. Veri-kalite kapısını geçmek,
ortak-model katkı kapısını geçmiş sayılmaz; her katkı ayrı ve hash'li bir
ablation gerektirir.

## Vegetation yardımcı verisi — ertelendi

```text
VegAnn
```

VegAnn doğrudan crop/weed ayrımı öğretmek yerine:

```text
vegetation / background
```

head’ini güçlendirmek için kullanılacaktır.

## Multiscale ve domain çeşitliliği

```text
WeedMap
PhenoBench
WeedsGalore
çok-sahalıklı patates segmentation verisi
```

Bu listedeki PhenoBench ve WeedsGalore mevcut havuzda domain-balanced sampler
ile kullanılır. WeedMap ayrı ablation'da sınanmış ve global karışım için
reddedilmiştir; specialist/adapter verisi olarak ileride yeniden ele
alınabilir. Adı belirtilen diğer kaynaklar ayrı ablation olmadan eklenmez.

## Geliştirme ve kilitli external testler

```text
CWFID       -> external_calibration, final test değil
SorghumWeed -> resmi train 202 / external_calibration 25 / kilitli test 25
Carrot-Weed -> kilitli external_test, 39 görüntü
EWIS1       -> kilitli external_test, 88 görüntü / 39 grup
real_core_final.test -> kilitli kaynak-domain test, 870 görüntü
```

CWFID base model eğitimine dahil edilmez; yalnız bilinmeyen crop-ID eşiğini
ilan edilmiş development verisinde kalibre eder. SorghumWeed validation da
yeni fazın ilan edilmiş development girdisidir. `real_core_final.test`,
Carrot-Weed ve EWIS1 real-only fazda seçimden sonra yalnız bir kez açıldı ve
yeni model seçiminde yeniden kullanılmadı. SorghumWeed `external_test` ise
yeni tarif/seed/epoch/checkpoint kilitlenene kadar performans açısından
kapalı tutuldu.

Amaç:

```text
real-only model taraması
→ CWFID development calibration
→ üç-seed semantic baseline
→ Sorghum train + kontrollü sentetik A/B
→ CWFID + Sorghum validation ile tarif/checkpoint kilidi
→ yeni Sorghum external_test'e tek performans erişimi
```

deneyini dürüst biçimde yapmaktır. 0/10/25/50-shot adaptasyon bu kilitli
test sonuçlarıyla aynı fazda optimize edilmez; ileride yeni bir test kilidiyle
ayrı çalışmadır.

## Research-only veri

```text
CropAndWeed
ticari olmayan lisanslı diğer kaynaklar
```

İki ayrı checkpoint ailesi tutulmalıdır:

```text
commercial_clean
research_max
```

`research_max`, teorik performans üst sınırını ölçmek için kullanılabilir; ticari modele taşınmamalıdır.

## Dataset birleştirme kuralları

Her görüntü için ortak manifest:

```text
image_path
mask_path
dataset_id
field_id
session_id
capture_date
platform
sensor
target_crop_id
crop_species
weed_species_optional
growth_stage
annotation_exhaustive
license_status
commercial_allowed
```

Ortak maskeler:

```text
0   background / soil
1   target crop
2   other vegetation
255 ignore
```

Kritik kural:

> Etiketlenmemiş bir bitki background yapılmayacak; `ignore` yapılacaktır.

Aynı video veya çekim oturumunun komşu kareleri train ve test arasında bölünmeyecektir.

Sampling:

```text
önce dataset/domain seç
→ sonra field/session
→ sonra görüntü
```

şeklinde olacaktır. Büyük bir dataset diğerlerini ezmeyecektir.

---

# 6. Başarı metrikleri

Ana metrik yalnızca mIoU değildir.

Öncelik sırası:

1. **Crop-as-weed false positive**
2. **Sabit crop hata seviyesinde weed recall**
3. **Worst-domain weed IoU**
4. **Growth-stage bazında sonuç**
5. **Unknown/no-spray oranı**
6. **0/10/25/50-shot adaptasyon eğrisi**
7. **Jetson batch-1 latency**
8. **Yeni domain başına insan düzeltme süresi**

Gerçek ürün metriği:

> Model weed recall’u artırırken crop’u weed olarak işaretlememelidir.

PoC için örnek güvenlik mantığı:

```text
safe_weed =
    high_confidence_weed
    AND NOT dilated_crop_mask
    AND NOT uncertain_region
```

Spot ilaçlama hedefi için ilk aşamada gövde/kök keypoint modeli zorunlu değildir.

Maskenin güvenli iç bölgesinde distance transform maksimumu gibi basit bir yöntemle hedef seçilebilir.

Lazer veya mekanik kazıma aşamasında:

```text
stem / root keypoint
```

ayrı ve daha kritik bir problem olacaktır.

---

# 7. Depth stratejisi — gelecek bağımsız faz, uygulanmadı

Segmentasyon şu anda birinci önceliktir. Depth modeli ilk altı haftalık segmentasyon PoC’sine dahil edilmeyecektir.

Fakat yazılım kontratı baştan hazır olacaktır:

```python
Segmenter(rgb, target_crop_id)
    -> crop_probability
    -> weed_probability
    -> vegetation_probability
    -> uncertainty
    -> target_pixels_uv
```

Daha sonra:

```python
DepthProvider(rgb_or_stereo)
    -> depth_map
```

ve:

```python
Projector(
    target_pixels_uv,
    depth_map,
    calibration
)
    -> XY / XYZ
```

eklenecektir.

Spot ilaçlama ve yaklaşık düz zemin için ilk etapta:

```text
pixel
→ camera calibration
→ ground-plane homography
→ ground XY
```

yeterli olabilir.

Lazer, kazıma veya robotik kol gibi hassas müdahalelerde stereo/RGB-D veya doğrulanmış metric depth gerekecektir.

WE3DS ve SB20, ileride depth benchmark’ı için saklanacaktır.

---

# 8. Sentetik veri stratejisi — kontrollü stock pilot tamamlandı

Sentetik veri gerçek verinin yerine geçmeyecektir.

Doğru rolü:

* eksik büyüme evrelerini üretmek,
* nadir crop–weed yerleşimlerini artırmak,
* farklı weed yoğunlukları oluşturmak,
* sert gölge ve ışık varyasyonu üretmek,
* kamera açısı ve yüksekliğini kontrollü değiştirmek,
* az gerçek örneği bulunan kombinasyonları tamamlamak,
* gerçek veri ihtiyacını yüzlerce görüntüden onlarca görüntüye düşürmek.

Sentetik veri ana corpus değil:

> **Kontrollü domain-gap tamamlama verisi**

olacaktır.

Gerçek-only baseline kilitlendikten sonra 100 karelik scene-ayrık stock
CropCraft pilotu üretildi. Aynı DINOv2-Small tarifinde, eşit 28.800 örnekleme
bütçesi ve sabit epoch 8 ile gerçek+Sorghum kontrolü; %10, %25 ve
sentetik-only kollarla karşılaştırıldı. Üç-seed paired confirmation'da
%10 kolu CWFID robust mIoU'yu ortalama `+0,017412` artırdı, 3/3 seed kazandı
ve ilan edilmiş source/Sorghum non-inferiority kapılarını geçti. %25
seed-17'de %10'dan daha kötüydü; sentetik-only ise Sorghum'da belirgin
sim-to-real çöküşü gösterdi.

Bu nedenle gerçekleşen ilk oran:

```text
%90 gerçek exposure
%10 stock sentetik exposure
```

olarak kabul edildi. Nedensel sentetik katkı iddiası yalnız eşit-bütçeli
epoch-8 kontrolü için geçerlidir; Sorghum train verisinin ayrı katkısı buna
karıştırılmaz. Mevcut stock pilot daha fazla aynı kareyle büyütülmez.
Ayrıntılı protokol ve sonuçlar `docs/SIMULATION_ABLATION_REPORT.md`
içindedir.

---

# 9. Blender hattı — uygulanan pilot ve gelecek faz referansı

Bu fazda yalnız pinli CropCraft commit'i ve Blender 4.5 uyumluluk patch'iyle
25 scene x 4 frame stock pilot çalıştırıldı. Custom botanik asset,
BlenderProc/depth ve yeni büyük batch üretilmedi. Aşağıdaki ayrıntılar,
%10 faydasının ardından yapılacak bağımsız custom-asset A/B'si için korunur.

## Temel stack

```text
CropCraft fork
+ Blender Python
+ gerektiğinde Geometry Nodes
+ Blender MCP
+ native RGB/semantic renderer
+ daha sonra BlenderProc
```

## Roller

### CropCraft

* tarla ve sıra yerleşimi,
* crop ve weed scattering,
* kamera ayarları,
* seed tabanlı tekrar üretim,
* RGB ve semantic mask üretimi.

### Blender Python

* generator’ın source of truth’u,
* scenario config,
* asset seçimi,
* metadata,
* batch üretimi,
* validator’lar.

### Geometry Nodes

* bitki ve taş scattering,
* toprak mikrogeometrisi,
* yüksek sayıda instance,
* kontrollü deformasyon.

### Blender MCP

* generator kodunu geliştirmek,
* Blender Python yazmak,
* asset import ve cleanup yapmak,
* Geometry Nodes kurmak,
* viewport/render incelemek,
* clipping ve materyal sorunlarını düzeltmek,
* asset compiler oluşturmak.

MCP dataset üretiminin runtime dependency’si olmayacaktır.

Doğru akış:

```text
MCP
→ generator kodunu geliştirir

CLI / CI
→ sabit commit + config + seed
→ batch dataset üretir
```

### BlenderProc

İlk semantic segmentation deneyi için zorunlu değildir.

Şunlar gerektiğinde eklenir:

* metric depth,
* instance segmentation,
* surface normals,
* optical flow,
* stereo,
* kamera intrinsic/extrinsic,
* standart dataset writer’ları.

## Asset stratejisi

### Smoke test

```text
mevcut CropCraft assetleri
Quaternius geçici crop assetleri
Poly Haven soil / stone / HDRI
```

Bunlar pipeline’ı doğrulamak içindir; nihai biyolojik gerçeklik kaynağı değildir.

### Hedef crop

Sentetik verinin katkısı kanıtlandıktan sonra:

```text
1 hedef crop
× 2–3 gerçek büyüme evresi
× evre başına 3–4 anchor varyant
```

hazırlanacaktır.

Olası kaynaklar:

* Helios/PyHelios,
* özel 3D modelleme,
* gerçek bitki taraması,
* fotogrametri + cleanup,
* gerçek point-cloud referansları.

Olgun bitkiyi küçültmek genç bitki sayılmayacaktır. Her stage:

* yaprak sayısı,
* kotiledon,
* yaprak açıları,
* canopy biçimi,
* yükseklik/genişlik oranı

bakımından gerçekten farklı olmalıdır.

### Weed assetleri

İlk aşamada botanik olarak bütün türleri modellemek yerine:

```text
dar yapraklı / grass
geniş yapraklı dik
rozet / yatık
```

gibi morfolojik ailelerle başlanabilir.

Hedef crop asseti daha yüksek doğrulukta olacaktır; çünkü crop’un weed olarak işaretlenmesi daha pahalı hatadır.

---

# 10. Unreal hattı

Unreal, Blender’a alternatif değil; farklı güçlü yönleri olan ikinci bir deney hattıdır.

Bu offline RGB+mask benchmark'inda Unreal çalıştırılmadı. CropCraft
gereken deterministik annotation hattını sağladı; robot hareketi, fizik,
büyük arazi veya real-time sensör gereksinimi olmadığı için motor kıyasının
maliyeti bu fazda haklı çıkmadı. Unreal ancak bu gereksinimlerden biri
somutlaştığında ayrı bir deney olarak açılır.

## Unreal’ın test edileceği alanlar

* büyük açık arazi,
* gerçek zamanlı render,
* procedural terrain,
* PCG tabanlı nesne dağılımı,
* kamera hareketi,
* robot titreşimi,
* hareket bulanıklığı,
* fizik,
* ileride çoklu sensör ve robot entegrasyonu.

İlk Unreal deneyi tam tarım simulator’ı olmayacaktır.

Amaç:

> Aynı dar sahne tanımıyla, hazır Unreal araçları ve mümkün olan MCP/otomasyon katmanları kullanılarak ne kadar hızlı RGB + semantic-mask veri üretilebildiğini görmek.

## Aynı sahne spesifikasyonu

Blender ve Unreal aynı minimum senaryoyu üretmelidir:

```text
1 target crop
2 growth stage
2 weed morphology
2 soil profile
2 lighting condition
sınırlı kamera height/pitch/roll varyasyonu
```

Her iki motor da:

```text
RGB
semantic mask
seed
camera metadata
scene parameters
```

üretmelidir.

Depth bu karşılaştırmada zorunlu değildir; fakat ileride üretilebilir olması artı puan olarak kaydedilir.

## Unreal değerlendirme kriterleri

* İlk çalışan batch’e ulaşma süresi,
* 100/1000 görüntü üretme hızı,
* semantic mask doğruluğu,
* seed/reproducibility,
* procedural kontrol,
* asset entegrasyon maliyeti,
* LLM/MCP ile düzenleme kolaylığı,
* headless veya otomatik batch üretim kolaylığı,
* görsel gerçekçilik,
* kamera hareketi ve fizik hazırlığı,
* depth ve sensor stack’e genişleme kolaylığı.

## Muhtemel uzun vadeli rol dağılımı

```text
Blender / CropCraft
→ hızlı, kontrollü, offline segmentation dataset üretimi

Unreal
→ robot hareketi, büyük sahne, fizik, sensör ve gerçek zamanlı simülasyon
```

Ancak bu karar varsayılmayacak; altı haftalık deneyle ölçülecektir.

---

# 11. Sentetik veri deney matrisi

Gerçekleşen ilk karşılaştırmalar:

```text
A — Public real + Sorghum train, %0 sentetik

B — Aynı gerçek havuz + %10 stock CropCraft

C — Aynı gerçek havuz + %25 stock CropCraft (seed-17 doz kontrolü)

D — %100 stock CropCraft (sim-to-real negatif kontrol)
```

Henüz çalıştırılmayan sonraki bağımsız kollar:

```text
E — Public real + custom Blender/CropCraft
F — Public real + custom Unreal
G — Public real + 2D real cut-paste composite
```

Hepsi aynı:

* erişilebilir model taramasında kazanan DINOv2-Small tarifi,
* training budget,
* seed düzeni,
* gerçek veri,
* external test,
* metrikler

ile karşılaştırılır. Gerçekleşen A–D screen'i ve A/B confirmation'ı
bu kontrata uyar; E–G mevcut kapsamda ertelenmiştir.

2D composite önemli bir kontrol grubudur. Gerçek bitki texture’larını farklı gerçek soil arka planlarına yerleştirerek 3D asset geliştirme maliyeti olmadan augmentation sağlar.

## Sentetik data için devam eşiği

Bir sentetik yol ancak aşağıdakilerden en az birini sağlarsa büyütülecektir:

* Worst-domain weed IoU yaklaşık `+2` veya daha fazla artar.
* Aynı crop-as-weed seviyesinde weed recall yaklaşık `+3 yüzde puanı` artar.
* Sentetik destekli 25-shot model, real-only 50-shot seviyesine ulaşır.
* Belirli bir büyüme evresindeki performans açığı belirgin azalır.

Sentetik görüntü güzel görünse bile gerçek external testte fayda sağlamıyorsa o hat büyütülmeyecektir.

---

# 12. Blender ve Unreal seçim kararı

Mevcut dar karar: stock CropCraft/Blender verisi %10 exposure'da ölçülebilir
semantic fayda verdi; bu nedenle deterministik offline segmentation pilotu
için Blender hattı korunur. Bu sonuç Unreal'dan daha iyi olduğunu kanıtlamaz;
Unreal bu fazda çalıştırılmadı ve real-time/fizik ihtiyacına ertelendi. Stock
asset kapsamı aynı biçimde büyütülmez; bir sonraki simülasyon testi ancak
custom morfoloji/soil/light/camera A/B'si olarak açılır.

Gelecek genişletilmiş motor/asset kıyasının karar dalları:

## Blender açık ara daha verimliyse

```text
Blender/CropCraft ana synthetic-data hattı
Unreal robot/sensor aşamasına ertelenir
```

## Unreal belirgin daha gerçekçi veya esnekse

```text
Unreal ana outdoor/robot simulation hattı
Blender asset hazırlama ve offline kontrollü render aracı
```

## İkisi farklı alanlarda güçlüyse

```text
Blender
→ segmentation ve kontrollü annotation

Unreal
→ hareket, fizik, kamera ve sensor simulation
```

## İkisi de gerçek performansı artırmıyorsa

```text
3D sentetik yatırım durdurulur
→ public real data
→ SAM-assisted annotation
→ 10/25/50-shot adaptation
→ gerekirse 2D composite
```

---

# 13. Tarihsel 6 haftalık yol haritası — mevcut icra durumu değil

Bu bölüm ilk kapasite/takvim taslağı olarak korunur. Güncel ve bağlayıcı
durum, dosyanın başındaki **Güncel icra durumu** checklist'idir. Özellikle
Hafta 3–6 maddeleri gerçekleşmiş iş listesi değildir. Gerçek-veri benchmark'ı,
100 kare stock CropCraft pilotu, kontrollü sentetik A/B ve RTX 3090
export/latency tamamlandı; custom simülasyon, few-shot, Jetson/TensorRT ve
depth ayrı sonraki fazlara ertelendi.

Kapasite:

```text
Hakan: haftada 8 saat
Hasan: haftada 8 saat
Toplam: haftada 16 kişi-saat
```

## Hafta 1 — Gerçek veri ve model hattı

### Hakan

* Ana dataset registry’sini kurar.
* Core datasetlerden örnekleri indirir.
* Ortak `background / crop / other vegetation / ignore` converter’ını başlatır.
* Field/session split hazırlar.
* 30 örnek görselleştirir.

### Hasan

* DINOv3 ConvNeXt-Tiny yükler.
* Hafif FPN decoder kurar.
* 20 görüntüyü overfit eder.
* ONNX export smoke test yapar.
* PyTorch ve ONNX çıktısını karşılaştırır.

### Teslim

```text
çalışan dataset loader
çalışan model
20-image overfit
ONNX smoke test
```

---

## Hafta 2 — Real-only baseline

### Hakan

* Core dataset converter’larını tamamlar.
* Dataset-balanced sampler hazırlar.
* Crop-as-weed, weed recall, IoU ve unknown metriklerini yazar.
* Kilitli external testleri ayırır.

### Hasan

* Frozen DINOv3 + decoder real-only modelini eğitir.
* Gerekirse yalnız stage 4’ü açarak ikinci kontrollü koşu yapar.
* External test error gallery üretir.

### Teslim

```text
real-only checkpoint
fixed split
metrics.json
10 iyi + 10 kötü örnek
```

---

## Hafta 3 — Blender ve Unreal hızlı generator spike

### Hakan — Blender

* CropCraft fork veya hazır CropCraft pipeline’ını çalıştırır.
* Blender MCP’yi izole ortamda kurar.
* Mevcut assetlerle aynı dar senaryodan 100–200 RGB/mask üretir.
* Seed, mask alignment ve asset manifestini doğrular.

### Hasan — Unreal

* Hazır Unreal procedural/PCG araçlarıyla aynı sahne kapsamını kurar.
* Mümkün olan otomasyon/MCP katmanını kullanır.
* 100–200 RGB/semantic-mask görüntüsü üretir.
* Kurulum süresi, render süresi ve sorunları kaydeder.

### Teslim

```text
Blender batch
Unreal batch
aynı class mapping
aynı kamera aralığı
engine-comparison notu
```

---

## Hafta 4 — Sentetik A/B

### Hakan

* Blender ve Unreal çıktılarında otomatik QA yapar.
* Duplicate, class-ratio, clipping ve mask hatalarını raporlar.
* Basit 2D real cut-paste kontrol datası üretir.

### Hasan

Aynı modelle:

```text
A — real only
B — real + Blender
C — real + Unreal
D — real + 2D composite
```

koşularını gerçekleştirir.

### Teslim

```text
external test karşılaştırması
worst-domain sonuç
crop-as-weed / weed-recall eğrisi
sentetik go/no-go kararı
```

---

## Hafta 5 — Few-shot adaptasyon ve edge

### Hakan

* SB20 veya başka kilitli domain’den çeşitli 10/25/50 görüntü seçer.
* SAM ile ön etiket üretir.
* İnsan düzeltme süresini kaydeder.
* Ayrı final test görüntülerini kilitler.

### Hasan

* 0/10/25/50 görüntüyle decoder/crop embedding adaptasyonu yapar.
* Gerekirse ConvNeXt stage 4’ü açar.
* En iyi modeli ONNX → TensorRT FP16 aktarır.
* Jetson veya eşdeğer hedefte batch-1 latency ölçer.

### Teslim

```text
adaptasyon eğrisi
insan dakika maliyeti
TensorRT FP16 model
edge latency
```

---

## Hafta 6 — Dikey demo ve motor kararı

### Hakan

* Blender ve Unreal veri üretim maliyetlerini karşılaştırır.
* Asset, lisans, provenance ve reproducibility raporunu tamamlar.
* Sentetik data fayda sağladıysa sonraki asset kapsamını belirler.

### Hasan

Tek demo hattını tamamlar:

```text
RGB
→ DINOv3 segmentation
→ uncertainty/no-spray
→ crop safety dilation
→ safe weed mask
→ hedef pikseller
```

PyTorch, ONNX ve TensorRT sonuçlarını karşılaştırır.

### Nihai teslim

```text
çalışan demo
real-only checkpoint
en iyi synthetic-supported checkpoint
0/10/25/50-shot sonuç
Blender vs Unreal kararı
Jetson deployment sonucu
sonraki 6–12 haftalık öneri
```

---

# 14. Her hafta zorunlu çalışma standardı

Her görev şu teslimleri içermelidir:

```text
tek çalıştırma komutu
README
config dosyası
metrics.json
10 başarılı örnek
10 başarısız örnek
harcanan insan saati
go / revise / stop kararı
```

“Biraz araştırdım” tek başına teslim kabul edilmemelidir.

Her hafta sonunda yalnızca şu sorular yanıtlanmalıdır:

```text
Ne çalıştı?
Ne çalışmadı?
Hangi metrik değişti?
Bir sonraki en küçük deney ne?
```

---

# 15. Bilgi durumu ve açık sorular

Bu segmentasyon fazında yanıtlananlar:

1. DINOv3 metadata'sı görünür, fakat geçerli Hugging Face oturumunda bile
   ayrı model koşulları kabul edilmediği için payload `401/403` ile kapalıdır;
   bu nedenle performans iddiası yoktur. Erişilebilir dokuz adayda
   DINOv2-Small semantik liderdir.
2. DINOv2-Small için yalnız frozen backbone yeterli olmadı; stage-4
   fine-tuning üç seed'de teyit edildi.
3. Public gerçek veride domain shift serttir. Eski Carrot-Weed sonucu ve
   CWFID crop IoU, yüksek source skorunun unseen-field robustluğu anlamına
   gelmediğini gösterdi.
4. Hazır CropCraft verisi, eşit-bütçeli %10 exposure'da CWFID robust
   mIoU'yu üç seed'in tamamında artırdı. %25 daha iyi değildi ve
   sentetik-only gerçeğe genellenmedi.
5. ONNX opset-18 export ve RTX 3090 FP16 referansı çalıştı; bu Jetson/
   TensorRT doğrulaması değildir.
6. Aynı stock simülasyonun körlemesine büyütülmesi desteklenmez. Yalnız
   custom morfoloji/soil/light/camera için küçük, frozen-real A/B yatırımı
   gerekçelidir.
7. GrowingSoy ve WeedMap kaliteli gerçek kaynaklar olsa da global sampler'a
   doğrudan eklenmeleri robustluğu otomatik artırmadı. Büyük in-domain
   kazançlar CWFID/CropAndWeed/Rice forgetting'iyle birlikte geldi; veri
   kabulü ile model katkısı ayrı kapılardır.
8. Motion blur kabul edilmiş kontrolde büyük ve tutarlı bir açıktır
   (`-0,144855` üç-seed mIoU). V7-R1 bu tek-saha blur hedefini iyileştirse
   de global domain'leri bozdu; V7-R2 düşük doz ve uncertainty maskesiyle
   hedef kazanımı tekrarlamadı. Asset'ler stress/specialist için yararlı,
   global mix için reddedilmiştir. DeBlurWeedSeg tek saha olduğu için sonraki
   gereksinim yeni çok-tarlalı gerçek blur coverage'dır.
9. RiceSEG edinim/kalite ve üç global model katkı kapısı tamamlandı. Veri
   hedef alanı kuvvetle öğretti; global ortak parametrelerde source/Sorghum/
   CropAndWeed girişimi kaldı. 604 calibration ve alternatif country-transfer
   rolleri eğitimden ayrı kaldı. Ayrı crop-routed specialist daha sonra
   `%2,38` dozla seed 17/29/43'te 3/3 robust galibiyet ve ortalama
   `+0,382517` rice-target robust farkıyla kabul edildi; global fallback
   değişmedi.
10. WeedyRice-RGBMS-DB veri kalitesi ve uçuş çeşitliliği bakımından yararlıdır,
    fakat negatif sınıfı cultivated rice ile arka planı ayırmaz. Semantic
    argmax IoU'su yüksek-prevalence nedeniyle yanıltıcıdır; çok düşük
    specificity ve source-frozen weed recall mevcut global modelin mature
    rice ayrımını çözmediğini gösterir. Ortak loss'a sessizce eklemek yerine
    veri partial-label specialist protokolü için kilitlenmiştir.
11. BAWSeg artık byte-level resmî artifact adı/content-ID ile görünür ve
    indirme kapasitesi yeterlidir; erişim abonelik oturumunda, extraction ise
    kamu sayfasındaki `7.5 GB / 500 GB+` hacim çelişkisi nedeniyle ZIP merkez
    dizini ve lisans incelemesinde fail-closed bekler.
12. Sentetik çeşitlilik sonrası iki-epoch real-only recovery geniş ortalama,
    target-like ve lower-tail skorlarını artırdı; buna rağmen CWFID ve
    real-core field macro regresyonunu gideremedi. Pooled source mIoU'nun
    yükselirken eşit field macro'nun düşmesi, geniş validation ve field-first
    skorlamanın neden gerekli olduğunu doğrudan doğruladı.
13. Model-unseen FarmBot/Naïo/BoniRob görselleri genel vegetation boundary
    kabiliyetini doğrularken ileri soy evresinde crop-identity kayması, yeşil
    robot false positive'i ve yüksek confidence altında OOD hata gösterdi.
    Frozen safety policy korumacı fakat safe-weed alanı çok düşük olduğundan
    bu görseller model veya spray-ready kabulü değildir.

Bu kullanıcı kapsamında bilinçli olarak sonraya bırakılanlar:

1. SAM anotasyon-zamanı deneyi. `0/10/25/50/100/202` strict-nested
   adaptasyon eğrisi ve seçilen 10-kare kolun ikinci-seed teyidi 2026-08-06'da
   tamamlandı.
2. RiceSEG specialist için otomatik görsel router, yanlış-metadata stress,
   iki-checkpoint latency/VRAM ve deployment paketi. Metadata-routed benchmark
   ve global fallback protokolü tamamlandı.
3. Weedy Rice için positive-only/partial-label loss ve uçuş-ayrık specialist
   ablation'ı; global replay/non-inferiority kontrolü olmadan ana modele ekleme yok.
4. Rice dışı yeni domainler için replay-balanced sampler veya ayrı
   crop/domain-conditioned specialist/adapter; rice metadata-routed specialist
   tamamlandı.
5. Unreal'ın real-time/fizik/sensör gereksinimindeki maliyet-faydası.
6. 2D real cut-paste kontrolü.
7. Jetson Orin TensorRT FP16 entegrasyonu ve cihaz üstü latency/termal test.
8. Depth veri/model benchmark'ı, kamera kalibrasyonu ve metric XY/XYZ.

---

# Nihai stratejik karar

Tamamlanan segmentasyon fazından çıkan ana hat:

```text
kaliteli public gerçek data
+
yalnız kalite ve cross-domain katkı kapılarını geçen hedef-domain gerçek veri
+
frozen-real A/B ile kanıtlanmış %5 dryland V3 + %5 paddy R5 sentetik exposure
+
DINOv2-Small stage-4 (erişilebilir robust semantik lider)
+
crop-conditioned hafif decoder
+
3-seed kabul edilmiş metadata-routed RiceSEG specialist + değişmemiş global
fallback
```

mevcut kabul edilmiş araştırma sistemidir. Weedy Rice partial-label specialist
ve SAM destekli az-veri adaptasyonu ayrı gelecek deneylerdir. DINOv3 ancak
erişim/lisans koşulları kullanıcı tarafından ayrıca
çözüldüğünde yeni, dondurulmuş bir ablation olarak kıyaslanabilir; üstünlüğü
varsayılmaz. Yeni DINOv2 modeli de kuyruk crop-risk kapıları, eski
Carrot-Weed açığı ve bağımsız unseen-field testi giderilmeden saha modeli
sayılmaz.

Blender ve Unreal yardımcı veri üretim hatlarıdır. Değerleri yalnızca:

```text
gerçek external testte performans artışı
veya
daha az gerçek etiket ihtiyacı
```

sağladıkları ölçüde kabul edilecektir. Stock CropCraft bu kapıyı %10'da
geçti; aynı stock dağılımın daha yüksek dozda veya gerçeğin yerine
kullanılması kapıyı geçmedi.

En muhtemel uzun vadeli yapı:

```text
Blender + CropCraft + MCP
→ hızlı, deterministik, offline segmentation verisi

Unreal
→ büyük saha, hareket, robot, fizik ve sensör simülasyonu

Gerçek saha verisi
→ final few-shot calibration ve güvenlik doğrulaması
```

Blender offline segmentation rolü bu pilotla desteklendi; Unreal rolü henüz
ölçülmedi ve real-time/fizik/sensör gereksinimine ertelendi.

Temel prensip:

> **Önce en küçük çalışan deneyi kur, gerçek holdout’ta ölç, yalnızca ölçülebilir katkı veren hattı büyüt.**

---

# 2026-08-05 — Müdahale-odaklı benchmark ve rapor tamamlandı

Bu faz mIoU'yu removal başarısı diye yorumlamayı bıraktı ve kabul edilmiş iki
checkpoint'i değiştirmeden method-specific proxy'lerle yeniden değerlendirdi:

- global seed 43: `b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f`;
- RiceSEG specialist seed 29: `ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7`.

Toplam `2.868` etiketli görüntü native-resolution ve source-frozen safety
policy ile işlendi; dış panellerde threshold/model retune yapılmadı:

```text
source validation       1.637
Sorghum test                25
SugarBeets robot           283
WeedMap UAV                 95
RiceSEG calibration        604
early-rice development     224
```

Yeni metrikler semantic connected-component any-hit, coverage@10/50/90,
apparent-size binleri, canopy-center proxy, component içi deepest action point,
weed/crop/background point sonucu ve 0/5/10/20 px crop-footprint collision'dır.
Connected component true plant instance; canopy center root/crown/meristem;
px footprint fiziksel nozzle/tool/beam değildir.

Ana sayısal sonuç:

- seen mIoU `0,8049`; semantic weed-component hit `%66,42`;
- frozen safe-action hit `%27,54`, point precision `%82,76`;
- pooled crop-point hit `%0,48`, fakat worst seen WE3DS `%4,61`; safety
  ortalamayla geçirilmedi;
- `<14 px` semantic hit `%24,14`, tüm boyutlarda `%66,42`; küçük safe hit
  yalnız `%2,00`;
- hedefe yakın SugarBeets robot: safe hit `%8,02`, point precision `%67,00`,
  crop-point `%18,18`;
- WeedMap UAV: crop IoU `0,0001`, weed IoU `0,1251`, safe hit `%0,12`;
- RiceSEG calibration: crop IoU `0,8015`, weed IoU `0,2224`, safe hit `%0,73`;
- early-rice development: weed IoU `0,1315`, safe hit `%0,29`.

Sonuç: semantic model araştırma için yararlı bir base'tir; hiçbir removal
yöntemi production gate'ini geçmedi. En kısa doğrulanabilir MVP mikro/spot
spray'dir. Birincil saha ölçüsü effective deposition/treatment ve crop
injury'dir; offline action-point/footprint yalnız proxy'dir. Mekanik sökme
için root/crown keypoint + depth + mm P50/P95 + removal outcome; lazer için
meristem/stem keypoint + beam/energy + kill/collateral outcome zorunludur.
Tam mask lazer için yalnız raster-treatment tasarımında birincildir.

Küçük-weed software scale A/B, aynı 224 early-rice development karesinde:

| Scale | Weed IoU | `<14 px` semantic hit | Crop-point hit | Perception ms/image |
|---:|---:|---:|---:|---:|
| `1,0×` | `0,1315` | `%19,58` | `%14,81` | `24,64` |
| `1,5×` | `0,1857` | `%26,45` | `%22,46` | `59,27` |
| `2,0×` | `0,2265` | `%29,38` | `%30,52` | `144,81` |

Interpolation ölçek darboğazını doğruladı, ancak crop guard ve latency'yi
kötüleştirdiği için kabul edilmedi. Native tiling zaten açıktır. Sıradaki
basit deney optik GSD/focus/exposure tasarımı ve eş-hesap small-object
oversampling + larger-crop/multi-scale training A/B'sidir.

RiceSEG split erratum'u kapatıldı: eski 1.254-kare country-transfer specialist
galerisi training coverage ile path düzeyinde `1.254/1.254` çakışır ve yalnız
train-seen diagnostic'tir. Yeni 604-kare Guangdong+Tokyo panelinin training
overlap'ı `0/604`'tür; fakat geçmiş specialist doz/seed seçiminde kullanıldığı
için training-held-out development/calibration'dır, untouched final test
değildir.

Teslimler:

- kısa PDF: `BASLA_BURADAN_MUDAHALE_RAPORU.pdf`;
- detaylı PDF: `docs/results/DETAYLI_BITKI_MUDAHALE_RAPORU.pdf`;
- aranabilir rapor: `docs/INTERVENTION_EVALUATION_V1.md`;
- self-contained yerel paket:
  `data/processed/audits/crop_intervention_report_v1/`;
- ham evaluator ve A/B configleri:
  `configs/benchmark/intervention_metrics_v1.yaml` ve
  `configs/benchmark/intervention_resolution_ablation_v1.yaml`.

Sıradaki P0/P1 işleri:

1. Removal yöntemi/aktüatör, minimum öldürülebilir weed mm, footprint, hız ve
   kabul edilebilir crop injury maliyetini dondur.
2. Kamera intrinsics/extrinsics, çalışma düzlemi GSD, focus/depth-of-field,
   motion blur ve perception-to-actuation latency'yi ölç.
3. 3–4 bağımsız tarla ve küçük-weed strata içeren untouched final test ile
   ayrı method/crop safety-calibration split'i topla.
4. Spot spray seçilirse deposition paper/fluorescent dye ile action proxy'yi
   gerçek effective treatment/crop injury sonucuna bağla.
5. Mekanik/lazer seçilirse semantic maskeyi zorlamak yerine doğrudan
   root/crown/meristem + depth + mm + kill/removal etiketi topla.

---

# 2026-08-05 — Okunabilir detaylı rapor revizyonu tamamlandı

Önceki detaylı PDF teknik olarak tam olsa da sayfa başına fazla bilgi ve
10'lu contact-sheet içerdiği için takip edilmesi zordu. Sonuçlar değiştirilmeden
sunum baştan kuruldu:

- `48` sayfa; ana bölümde her sayfa tek ana fikir taşır;
- görsel sayfalarda yalnız bir örnek ve iki büyük panel kullanılır;
- her örneğin altında sade bulgu ve ilgili efektif başarı metriği vardır;
- mIoU, semantic hit, safe hit, action-point ve crop-footprint farkı görsel
  akışla anlatılır;
- spot spray, mekanik sökme ve lazer için gerekli gerçek saha metriği ayrı
  şemalarla gösterilir;
- exact dataset tabloları ve policy değerleri ana hikâyeden teknik eke taşınır.

V11 asset/seed-ayrık sentetik unseen holdout da genişletildi:

- güçlü ve zor örnek ayrı sayfalarda gösterilir;
- 16 karenin 14'ünde GT weed vardır;
- macro crop IoU `%41,8`, weed bulunan karelerde macro weed IoU `%56,1`;
- micro safe-weed recall `%33,3`, safe pixel precision `%96,7`, crop-spray
  pixel risk `%0,0`;
- bu değerler açıkça sentetik-domain performansı olarak etiketlenir ve gerçek
  saha kanıtı sayılmaz.

Teslimler:

- repo kökü: `ANLASILIR_DETAYLI_MUDAHALE_RAPORU.pdf`;
- sonuç kopyası: `docs/results/DETAYLI_BITKI_MUDAHALE_RAPORU.pdf`;
- self-contained paket: `data/processed/audits/crop_intervention_report_v1/`;
- paketteki `QUALITATIVE/`, eski yoğun contact-sheet kopyaları yerine raporda
  kullanılan dokuz tekil örneği içerir.

Doğrulama:

- PDF `48` sayfa, başlık metadata'sı doğru ve üç kopyanın SHA-256 değeri
  aynıdır: `8a12ebca834d8c731f544ec49b1accc6cee5b14f79696176ebc70873ff4894a4`;
- tüm sayfalar overview olarak, ana karar/görsel/teknik-ek sayfaları ayrıca
  tam çözünürlükte görsel kontrolden geçirildi; taşma veya üst üste binme yok;
- tam test paketi `192/192` geçti ve `git diff --check` temizdir.

---

# 2026-08-06 — Kamera, domain adaptation, küçük-ot ve crop-row deneyleri

Bu faz iki ana hipotezi ayrı ölçtü:

1. fiziksel acquisition ve model raster/token bütçesi küçük-weed başarısını
   sınırlar;
2. hedef koşula benzer az miktarda gerçek veri domain uyumunu belirgin artırır.

## Kamera/optik tanı sonucu

Sekiz asset/seed-ayrık V11 unseen geometri × iki karede model/eşik sabit
tutuldu. Native çözünürlük eğrisi:

| Raster | mIoU | Crop IoU | Weed IoU | Safe weed recall |
|---:|---:|---:|---:|---:|
| 256 | 0,5553 | 0,2525 | 0,4384 | 0,1936 |
| 384 | 0,6338 | 0,3603 | 0,5600 | 0,2539 |
| 512 | 0,6952 | 0,4660 | 0,6340 | 0,3334 |
| 768 | 0,7753 | 0,6139 | 0,7218 | 0,4416 |
| 1024 | 0,8250 | 0,7158 | 0,7662 | 0,4882 |

512 capture'ı yalnız dijital olarak 1024'e büyütmek `+0,11920` mIoU verdi;
native 1024 bunun üstüne yalnız `+0,01060` ekledi. Bu temiz sentetik panelde
model raster/token darboğazı baskındır. Ancak gerçek holdout aynı sonucu
tekrarlamadı:

| Alan | Inference raster | mIoU | `<14 px` safe hit | Crop risk | Perception ms |
|---|---:|---:|---:|---:|---:|
| SugarBeets | 1,0× | 0,5772 | 0,00283 | 0,0410 | 34,05 |
| SugarBeets | 1,5× | 0,3621 | 0,00727 | 0,6520 | 95,05 |
| SugarBeets | 2,0× | 0,4282 | 0,01776 | 0,2960 | 210,21 |
| WeedMap | 1,0× | 0,3495 | 0,00021 | 0,00145 | 8,97 |
| WeedMap | 1,5× | 0,3505 | 0,00105 | 0,00315 | 11,54 |
| WeedMap | 2,0× | 0,3492 | 0,00232 | 0,00272 | 16,11 |

Kör inference interpolation reddedildi. Native sensör/GSD, native tiling ve
train–inference raster uyumu birlikte tasarlanmalıdır. Defocus `σ=3`, aynı
sahnede mIoU'yu `-0,0826`; 7 px motion blur `-0,0121` değiştirdi. Sabit düşük
ışık sweep'inde E0–E120 mIoU yaklaşık düz kaldı; simülatör enerji değeri
lux/watt değildir. Işık short-shutter/exposure/focus sistemi olarak gerçek
bench'te kalibre edilmelidir.

512 referansta `<14 px` bağlı weed proxy safe hit `%2,4`, 14–28 px `%67,9`,
28 px üstü `%100` oldu. Üst iki grupta yalnız 26 proxy bulunduğundan yaklaşık
28 px kesin eşik değil, GSD ön-tasarım hipotezidir. Başlangıç hesabı:
`GSD_max = hedef minimum weed eşdeğer çapı (mm) / 28`.

## Domain-adaptation eğrisi

Sorghum resmî train karelerinden RGB-thumbnail çeşitlilik sırasıyla
strict-nested `0/10/25/50/100/202` alt kümeleri kuruldu. Epoch, samples/epoch,
optimizer ve sampler oranı eşitti. Seed17 dondurulmuş target-ağırlıklı,
breadth-gated seçim 10 kareyi seçti; seed29 yalnız kontrol+10-kare paired
teyidiydi.

İki-seed ortalama 10-kare farkları:

- source `-0,00926`;
- Sorghum `+0,17966`;
- CWFID `+0,02792`;
- SugarBeets `+0,05957`;
- WeedMap `-0,00308`.

Her iki seed de dondurulmuş kapıyı geçti. Bu, hedef koşula benzer az miktarda
etiketli gerçek verinin en güçlü basit kaldıraç olduğunu doğrular. Sorghum
aynı dataset/tek saha olduğundan bu sonuç multi-farm deployment kanıtı değildir.

## Küçük-ot eğitim A/B ve iki-model kararı

Eşit 8×3.600 örnek bütçesinde kontrol, scale-up, `%10` küçük-component replay,
replay+scale ve 768 canvas sınandı. Global kapı source/CWFID/Sorghum/
SugarBeets/WeedMap non-inferiority istedi. Tüm challenger'lar CWFID kapısını
aştığı için global 512 kontrol korundu.

Canvas768 seed17'de SugarBeets'i `+0,14355`, WeedMap'i `+0,00736` artırırken
source `-0,00427`, Sorghum `-0,00306`, CWFID `-0,04179` değiştirdi. Sonuç
görülmeden seed43 hedef-specialist kapısı donduruldu: SugarBeets en az `+0,05`;
source `≥-0,015`, Sorghum `≥-0,02`, WeedMap `≥-0,01`, CWFID `≥-0,06`.
Seed43 farkları `-0,00665/-0,04668/+0,00712/+0,11665/+0,00680` oldu ve kapı
geçti. İki-seed ortalama:

- source `-0,00546`;
- CWFID `-0,04424`;
- Sorghum `+0,00203`;
- SugarBeets `+0,13010`;
- WeedMap `+0,00708`.

Karar: `512 control` global generalist/fallback; `canvas768` yalnız doğrulanmış
hedef robot kamera profiline route edilen conditional specialist. CWFID/UAV
alanına otomatik genellenmez.

Seed17 full intervention tanısında SugarBeets kontrol→canvas768:

- mIoU `0,5574 → 0,7003`;
- crop risk `%4,41 → %1,45`;
- safe spray recall `%4,15 → %9,72`;
- tüm semantic-component hit `%4,92 → %15,28`;
- `<14 px` safe hit `%0,16 → %0,40`;
- merkez ≤1 eşdeğer yarıçap `%3,37 → %9,66`.

WeedMap'te mIoU hafif yükselirken safe recall `%6,29 → %3,24` ve `<14 px`
hit `%0,38 → %0,04` düştü. Bu sonuç routing/fallback gereğini doğrudan
doğrular. Connected component botanik instance; center kök/meristem değildir.

## Crop-row prior

Practical prior model crop olasılığından sıra fit eder; oracle yalnız sıra
geometrisini GT'den aldığı için label-leaking teorik tavandır. `0,65` posterior
prior reddedildi. Row guard yeni aksiyon yaratmaz, yalnız veto eder.
SugarBeets'te pratik guard crop riskini `%4,55 → %4,06` indirirken safe weed
recall `%7,83 → %6,60` düştü. In-row weed bulunduğundan `sıra içi=crop`
mutlak kuralı güvenli değildir. RTK/planter çizgisi veya temporal fit daha
değerli bir sonraki prior kaynağıdır.

## Teslimler ve sonraki gerçek saha kapısı

- kısa PDF: `docs/results/BASLA_BURADAN_KAMERA_DOMAIN_KARARI.pdf` (`10` sayfa);
- detaylı PDF: `docs/results/KAMERA_DOMAIN_VE_KUCUK_OT_DENEY_RAPORU.pdf`
  (`23` sayfa);
- exact Markdown: `docs/KAMERA_DOMAIN_VE_KUCUK_OT_DENEYLERI_V1.md`;
- self-contained yerel paket:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_domain_report_v1/`.

Sıradaki P0, daha fazla calibration-set deneyi değil gerçek kamera bench'idir:

1. minimum öldürülebilir weed çapı, yatay kapsama, çalışma yüksekliği/FOV ve
   target GSD dondur;
2. native sensor/tile ile focus/DOF, short shutter, robot hızında blur ve
   lux–mesafe–exposure sweep'i ölç;
3. 3–4 yeni tarla/kamera oturumu ve küçük-weed strata içeren untouched final
   test topla;
4. generalist/specialist routing'i kamera metadata'sı ve OOD fail-closed guard
   ile doğrula;
5. removal yöntemine göre deposition/removal/kill ve crop-injury sonucunu mm
   kalibre aktüatör testiyle ölç. Depth bundan sonra ele alınır.

# Noktasal müdahale PoC sonucu — 2026-08-08

## `%9,72` sonucunun düzeltilmiş yorumu

Canvas768 SugarBeets tanısındaki `%9,72`, gerçek bitki-instance veya
müdahale recall'ı değildir. `weed_threshold=0,99`, uncertainty ve crop guard
sonrası kalan weed **piksellerinin** recall'ıdır. Aynı 283 robot karesinde:

- mIoU `0,70033`;
- weed-pixel precision/recall/F1 `0,52994/0,54555/0,53763`;
- frozen safe-pixel precision/recall `0,65954/0,09718`.

Connected component botanik instance, maske merkezi de sap/kök/meristem
değildir. Bu nedenle lazer veya tek-nokta müdahale başarısı bu rakamdan
çıkarılamaz.

## Gerçek sap/keypoint PoC'si

Weed Stem Detection arşivindeki 2048×2048 gerçek robot kareleri tarih
ayrı `211/152/148` train/validation/test olarak hazırlandı. Testte `1.102`
weed kutusu, `1.097` geçerli sap noktası vardı. Her tahmin ve GT sap en fazla
bir kez eşleştirildi; threshold ve aynı-kare dedupe yarıçapı validation'da
seçildi.

1536 fine-tune + dedupe, 10% GT weed-box-diagonal toleransında:

- TP/FP/FN `835/483/262`;
- precision `0,63354`;
- recall `0,76117`;
- F1 `0,69151`;
- crop-as-weed false fire `0/1.318` aksiyon. Bu, crop canopy/yaralanma
  garantisi değil; yalnız GT crop kutusuyla IoU≥0,50 sınıf-hatası proxy'sidir.
- aksiyon noktasının herhangi bir GT crop bounding rectangle içinde kalma
  oranı `0,13657` oldu. Dikdörtgen canopy değildir; bu değer fiziksel crop
  injury olarak yorumlanamaz ve lazer safety kapısını kapatmaz.

Tolerans duyarlılığı: 5%/10%/20% kutu köşegeni F1
`0,48447/0,69151/0,76356`; 5/10/20 px F1
`0,66087/0,75694/0,77516`. Doğru pozitif nokta hatası p50 `2,35 px`, p95
`5,10 px` oldu; GSD olmadığı için bunlar mm iddiası değildir.

1024 taban + dedupe F1 `0,66164`; 1536 fine-tune yaklaşık `+0,030` F1
kazandırdı. Kör 768/1536/2048 inference rasterları monotonik kazanç
vermedi. Train–inference raster uyumu faydalı, fakat tek başına yeterli
değildir ve fine-tune deneyi equal-compute değildir. Aynı test tarihi
resolution/model kararında tekrar kullanıldığı için artık development
holdout'tur; yeni untouched final test gereklidir.

## Mimari karar

- Segmentasyon korunur: vegetation boundary, crop safety halo, OOD/context ve
  spray footprint.
- Noktasal komut detection/instance + weed stem/root keypoint'ten gelir.
- Bu WSD diliminde ham keypoint'in box-center'a farkı yalnız sıkı 5%
  toleransta `+0,0130` F1; ana darboğaz weed detection/classification'dır.
- Aynı-kare dedupe ve validation'da yeniden seçilen threshold, 1536 ham
  keypoint F1'ını `0,60008 → 0,69151` yaptı.
- Video için image-IoU yerine calibrated world-coordinate association,
  en az 3 gözlem, crop veto, ortalama nokta ve fire-once uygulanır. ReID
  ancak uzun occlusion/geri dönüş problemi ölçülürse eklenir.
- Crop-row bilgisi soft score/safety prior'dır. SugarBeets tanısında pratik
  guard crop riskini `%4,55 → %4,06`, weed recall'ı `%7,83 → %6,60`
  yaptı; `sıra içi=crop` hard kuralı reddedildi.

## `%95` kapısı ve sonraki P0

Mevcut en iyi development F1 `%69,15`; `%95` perception kapısı geçilmedi.
Bugün araştırma PoC'si `GO`, gerçek ilaç/lazer ateşlemesi `NO-GO`dur.

1. Hedef kamera/GSD, minimum weed mm ve fiziksel isabet toleransını dondur.
2. 3–4 yeni tarla/kamera oturumunda crop/weed instance + stem/root point ve
   video track ID etiketle.
3. Farm/session ayrı untouched testte track-level P/R/F1 `≥0,95`,
   crop-as-weed ve duplicate-shot safety kapılarını birlikte ara.
4. Sonra aktüatör bench'inde kill/removal `≥0,95` ve crop injury'yi ayrı
   ölç. Perception F1 kill başarısı değildir.

Teslimler:

- `docs/results/BASLA_BURADAN_NOKTASAL_MUDAHALE_POC.pdf` (`14` sayfa);
- `docs/NOKTASAL_MUDAHALE_POC_V1.md`;
- exact yerel paket:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/point_intervention_poc_v1/`;
- base checkpoint SHA-256
  `5c1afffae12ccc0d84f8188247e95d3579568925a3099cc8a85f213418d57e70`;
- 1536 checkpoint SHA-256
  `569b7c71995c3dc75cb2cf6a6bd81d87861cb4911965d1143d95037011116945`.

# Detection-only spot-spray A/B sonucu — 2026-08-10

## Tamamlanan işler

- [x] WSD pose etiketlerinin ilk beş alanından sıfır-kopya hard-link görüntülü
      detection-only türev üretildi; `211/152/148` tarih-ayrı üyelik korundu.
- [x] YOLO26s-detect, 1024 px, seed 17, pose baseline ile aynı veri ve
      augmentasyon kontratında eğitildi. 100 epoch isteği, önceden tanımlı
      patience 30 ile epoch 67'de tamamlandı.
- [x] Validation-only confidence/dedupe seçimi ve one-to-one test eşleşmesiyle
      weed-kutusu spot proxy'si ile `%10` kutu-diyagonali stem proxy'si ayrıldı.
- [x] Detection-only kutu merkezi, pose kutu merkezi ve pose keypoint aynı
      148-kare development holdout'ta karşılaştırıldı.
- [x] `<14 / 14–28 / 28–56 / ≥56 px` boyut stratification'ı ve 1024/1536
      inference kontrolü tamamlandı.
- [x] 10 sayfalık basit PDF, exact Markdown, self-contained yerel paket,
      karşılaştırma galerisi ve testler üretildi.

## Sonuç ve mimari karar

| Strateji | Spot P | Spot R | Spot F1 | Sıkı stem F1 |
|---|---:|---:|---:|---:|
| **Detection-only → kutu merkezi** | **0,7496** | 0,7822 | **0,7655** | **0,6604** |
| Pose → kutu merkezi | 0,7011 | **0,8067** | 0,7502 | 0,6559 |
| Pose → keypoint | 0,6994 | **0,8067** | 0,7493 | 0,6591 |

- İlk kimyasal spot-spray araştırma baseline'ı **detection-only +
  segmentasyon crop-safety/footprint** olacaktır. GT weed kutusu isabeti
  toprak içeren iyimser proxy'dir; field/spray-ready iddiası yoktur.
- Lazer ve mekanik nokta için detection + stem/root/meristem keypoint gerekir.
  Bu A/B'de keypoint ana weed proposal/classification darboğazını çözmedi.
- Recall-95 politikası test recall'ını `0,9428`e çıkardı; precision `0,3582`,
  F1 `0,5191` ve FP `1.862` oldu. `%95` F1 kapısı geçilmedi.
- Dengeli detection-only spot recall `<14 / 14–28 / 28–56 px` için
  `0,5385 / 0,7826 / 0,8827` oldu. `≥56 px` grubunda yalnız bir örnek vardı;
  sonuç genellenemez.
- 1024 girişte test weed kutularının yalnız `%14,8`i 28 px üstündedir.
  Geometrik 1536 görünümü bu oranı `%79,0`a çıkarsa da kör inference F1'ı
  `0,7655→0,7179` düşürdü. Native sensör detayı/FOV ve eşleşen eğitim gerekir.
- Önceki sentetik `≥28 px = %100`, yalnız 26 connected semantic component'te
  en az bir safe piksel örtüşmesiydi; gerçek müdahale başarısı değildi.

## Sonraki P0

1. Minimum müdahale weed çapı, gerçek nozul footprint'i, FOV/GSD ve
   focus–motion kamera bench'ini dondur.
2. 3–4 deploy-benzeri tarla/session'da weed/crop instance + stem + track ID
   etiketi topla; final session'ları tamamen untouched tut.
3. Detection-only'yi native tile/high-resolution train–inference uyumuyla
   test et; segmentasyon crop veto etkisini ayrı A/B yap.
4. World-coordinate association + ≥3 kare onay + fire-once ile track-level
   P/R/F1 ölç; ReID yalnız ölçülmüş uzun occlusion sorunu varsa ekle.
5. Track F1 `≥0,95` sonrasında fiziksel deposition/kill `≥0,95` ve crop injury
   kapılarını aktüatör bench'inde ayrı ölç.

Teslimler:

- `docs/results/DETECTION_SPOT_SPRAY_BENCHMARK_V1.pdf`;
- `docs/DETECTION_SPOT_SPRAY_BENCHMARK_V1.md`;
- `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_detection_spot_spray_benchmark_v1/`;
- detection checkpoint SHA-256
  `c101548c235aa064af691b79aa15353166ad1285d6c65e0ea12f6075e6484177`.

# Segmentasyon – detection – keypoint sprey kararı v2 — 2026-08-10

## Tamamlanan işler

- [x] Keypoint provenance doğrulandı: WSD yayıncısının
      `labelled/points_labels` etiketleri box satırlarıyla eşlendi; proje
      sentetik keypoint üretmedi. Train/val/test görünür nokta sayıları
      `1.435/1.549/1.097`; noktası eksik 34 weed sıkı metrikten dışlandı.
- [x] Kabul edilmiş global semantik segmenter, aynı WSD val/test karelerinde
      `1024` tam-kare ve native `2048`/1024-tile/128-overlap koşullarında
      değerlendirildi. Checkpoint'in eğitim kaynak snapshot'ı `a9abcfc8b679`
      ve source-tree hash'i `fda1a1c4...3142eb` birebir eşleştirildi.
- [x] Segmentasyon weed maskesinden connected-component deepest-interior ve
      distance-peak aksiyon adayları üretildi; minimum alan/skor/eşik yalnız
      validation'da tarandı ve testte donduruldu.
- [x] 28 px analizi GT-boyutuna koşullu hale getirildi: küçük weed'e doğru
      isabetler FP sayılmadı; arka plan/crop/duplicate aksiyonlar FP kaldı.
- [x] 10 sayfalık sade PDF, exact Markdown, self-contained yerel paket,
      provenance receipt'leri ve açıklamalı görseller üretildi.

## Sonuç

| Yaklaşım | Spot P | Spot R | Spot F1 | Sıkı stem F1 |
|---|---:|---:|---:|---:|
| Global segmentasyon, WSD zero-shot, 1024 | 0,2299 | 0,1661 | 0,1928 | 0,0205 |
| Global segmentasyon, WSD zero-shot, native 2048 tile | 0,2799 | 0,2187 | 0,2455 | 0,0398 |
| **Detection-only, kutu merkezi, 1024** | **0,7496** | 0,7822 | **0,7655** | **0,6604** |
| Pose, kutu merkezi | 0,7011 | **0,8067** | 0,7502 | 0,6559 |
| Pose, yayıncı keypoint | 0,6994 | **0,8067** | 0,7493 | 0,6591 |

- Bu saf mimari A/B değildir: detector 211 WSD train karesi/1.437 weed
  kutusu gördü, global segmenter WSD'den sıfır kare gördü. WSD semantik maske
  içermediği için eşit target-trained segmentasyon kolu yoktur. Sonuç pratik
  hedef-domain anotasyonu + task/model etkisini ölçer.
- Pose kutu merkezi→keypoint sıkı stem F1 farkı yalnız `+0,0032` oldu.
  Kimyasal spreyde önce kutu/instance; lazer/mekanikte keypoint kararı verildi.
- `28–56 px` detection recall'ı `0,8827`; `≥28 px` n=163 hedefe koşullu
  P/R/F1 `0,4415/0,8098/0,5714` oldu. 28 px gerekli kamera hipotezidir ama
  FP'leri ve domain açığını tek başına çözmez.
- Kimyasal PoC baseline'ı **detection/instance + kutu merkezi + segmentasyon
  crop-safety + basit video onayı**dır. `%95` offline ve fiziksel saha kapıları
  geçilmedi; saha ateşlemesi `NO-GO`.

## Sonraki P0

1. En az 3–4 deploy-benzeri tarla/session'da weed/crop kutusu-instance ve ham
   video/kamera metadata'sı topla; session-ayrı untouched test koru.
2. Segmentasyonun saf marjı ve crop safety için 50–100 stratified maskelik
   audit alt-kümesi ekle; tam keypoint kampanyasını lazer fazına ertele.
3. Detection'ı native high-resolution train/inference uyumuyla yeniden ölç;
   dijital upscale kullanma.
4. Kalibre zeminde `≥3` kare onay + fire-once A/B'sini ID-GT videoda ölç.

Teslimler:

- `docs/results/SPOT_SPRAY_MODEL_KARARI_V2.pdf`;
- `docs/SPOT_SPRAY_MODEL_KARARI_V2.md`;
- `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/spot_spray_model_decision_v2/`;
- `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_segmentation_spot_spray_v1/segmentation_vs_detection_metrics.json`;
- `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/wsd_spot_success_conditions_v1/detection_gt_size_conditioned.json`.

# Segmentasyon `%95+` kapasite ve genelleme kanıtı — 2026-08-10

## Tamamlanan deneyler

- [x] PhenoBench final segmenter için train/val/test ve `<14/14–28/28–56/≥56`
      apparent-size tanısı tamamlandı.
- [x] Validation'da prediction-size policy seçilip post-hoc `≥42 px` test
      sonucu donduruldu: `P/R/F1 0,8852/0,8016/0,8413`.
- [x] 126-kare source ve 126-kare target-like intentional-overfit kolları,
      `mask_ratio=1`, 120 epoch ve crop-safe action ile çalıştırıldı.
- [x] Maskede excess-green aksiyon noktası, predicted crop-mask safety halesi
      ve dört predicted crop-row bandı ortak val/testte ölçüldü.
- [x] Base/source126/target126 modelleri ortak 172-kare calibration ve
      403-kare testte karşılaştırıldı.
- [x] Eşit 126 target + 126 source replay, augmentation, düşük LR ve 30
      epoch challenger'ı eğitilip aynı ortak protokolde değerlendirildi.
- [x] Deere, Greeneye, Ecorobotix, ONE SMART SPRAY, Bilberry, WEED-IT,
      Verdant ve Carbon için recognition/placement/outcome iddiaları ayrıldı.

## Net sonuç

| Kanıt | Precision | Recall | F1 | Crop hit |
|---|---:|---:|---:|---:|
| Target-like 126, aynı-kare kapasite | `0,9968` | `0,9968` | `0,9968` | `0` |
| Ortak test base | `0,9202` | `0,7744` | **`0,8410`** | `0,0285` |
| Ortak test target-only agresif | `0,8841` | `0,7936` | `0,8364` | `0,0535` |
| Ortak test target+source replay | `0,8140` | **`0,8544`** | `0,8337` | `0,0564` |

Model aynı hedef dağılımda `%95+` yapabilir; farklı parselde yapamıyor.
Basit replay recall'ı `+8` puan artırdı ama precision/crop safety'yi bozdu;
reddedildi. Confidence-only güvenli replay policy'si
`P/R/F1 0,9890/0,2864/0,4442` oldu. Row prior `84 px` bantta crop hit'i
sıfırlarken recall'ı `0,5136`ya düşürdü; yalnız safety veto'dur.

Yazılım tarafında sıradaki tek basit challenger; crop-yakın hard-negative,
session-dengeli replay ve erken validation seçimidir. Asıl P0 fiziksel paired
kamera bench'i ve ID-etiketli videodur. Geçici ana PoC eligibility'si
`d_min=20 mm`, stretch `10–20 mm`; her uygun weed model girdisinde `≥42 px`
olmalıdır. 4K kare tam olarak 1024'e küçültülmez, native tile işlenir.

## Dondurulmuş kanıt

- okunabilir detay:
  `docs/SEGMENTASYON_95_SAHA_KANIT_PLANI_V1.md`;
- 15 sayfalık görsel karar raporu:
  `docs/results/SEGMENTASYON_95_VE_RAKIP_CEILING_RAPORU_V1.pdf`;
- repo özet JSON:
  `docs/results/phenobench_95_evidence_summary_v1.json`;
- target-capacity metric SHA-256:
  `1a54b1f55923efa6b8ac9d85e66eaf1c96138c50061c21994d9c383afe285850`;
- replay final checkpoint SHA-256:
  `0429ccb7b785da361d44fc1273c205c2ba140c51af41a52ad618689035eb4013`;
- ortak adaptation-v2 metric SHA-256:
  `95e4f035bbefdbddee73087ab36c24f0e7f7e0ae07fbf7e2e40ed2deacea7c8f`;
- yerel ortak metrik:
  `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/runs/phenobench_domain_adaptation_comparison_v2/domain_adaptation_metrics.json`.
