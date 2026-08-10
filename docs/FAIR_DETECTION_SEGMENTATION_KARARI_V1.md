# Adil detection vs segmentation karari v1

## Kisa karar

**SEGMENTATION TABANI TERCIH EDILEBILIR.** Bu sonuc, iki modelin de ayni 1.407 gercek PhenoBench train goruntusunu ve ayni publisher bitki instance'larini gordugu eslenmis A/B'den gelir.

| Yontem | Precision | Recall | F1 | Crop temas riski |
|---|---:|---:|---:|---:|
| Detection → kutu merkezi | %69,0 | %60,9 | %64,7 | %1,5 |
| Segmentasyon → guvenli maske ici | %86,0 | %64,9 | %74,0 | %2,3 |
| Segmentasyon → kutu merkezi kontrol | %71,6 | %54,8 | %62,1 | %1,4 |

TP, bir weed'e yapilan ilk aksiyon noktasinin exact publisher weed dokusuna temasidir. Ayni weed'e ikinci aksiyon, toprak veya crop temasi FP'dir. Kismi bitkiler ignore edilir. Confidence esikleri yalniz validation'da secilip testten once dosyaya kilitlenmistir.

Validation'da secilen balanced-F1 confidence esikleri detection icin `0.48`, segmentation icin `0.49`'dir. Testte tekrar secim veya sweep yapilmadi.

## Kucuk weed sonucu

Boyut, native/model 1024 rasterda `sqrt(exact GT instance kutu alani)` olarak tanimlidir.

| Boyut | GT weed | Detection recall | Segmentation recall |
|---|---:|---:|---:|
| <14 px | 273 | %30,0 | %26,4 |
| 14–28 px | 501 | %60,9 | %54,7 |
| 28–56 px | 571 | %64,3 | %78,5 |
| ≥56 px | 409 | %77,0 | %84,4 |

## Standart ve maske metrikleri

- Detection box mAP50–95: %71,2
- Segmenter box mAP50–95: %70,6
- Segmenter mask mAP50–95: %51,9
- Segmenter weed/crop tissue IoU: %71,0 / %93,1; macro %82,1

Bu standart metrikler yardimci teshistir. Mimari kararin ana metrigi, iki model icin de ayni exact-doku one-to-one aksiyon F1/recall/crop temasidir.

## Neden adil?

- Ayni RGB kareleri, splitler ve uygun bitki instance'lari.
- Kutu ve poligon ayni publisher instance maskesinden turetildi.
- Ayni YOLO26s ailesi, native 1024 raster, 50 epoch, batch 8, seed 17 ve augmentation.
- Ikisi de hedef gercek train verisini gordu; zero-shot kol yok.
- Checkpoint iki kolda da sabit son epoch (`last.pt`).

PhenoBench resmi train bolgesinin 1.407 goruntusu train olarak kaldi. Resmi validation bolgesindeki P-parsel gruplari, her uc cekim tarihi iki tarafta da temsil edilecek bicimde 369 calibration ve 403 untouched test goruntusune ayrildi. Testte 1.754 uygun tam weed ve 2.654 uygun tam crop instance'i vardir. Train/val/test arasinda goruntu yolu cakismasi, val/test arasinda P-parsel cakismasi yoktur.

Task-eslesmis resmi COCO pretrained `yolo26s.pt` ve `yolo26s-seg.pt` baslangiclari kullanildi. Backbone olcegi aynidir; task head ve buna bagli parametre/FLOP farki gercek sistem maliyeti olarak tutulup latency ile raporlandi. Test batch-2 offline olcumunde framework + action toplamlarinin ham parcasi JSON'da bulunur: detection inference 4.85 ms, segmentation inference 6.58 ms; maske transferi ve deepest-interior islemi ayrica `action_postprocess_ms_per_image_mean` alanindadir.

Egitilmis modeller detection icin 9.95M, segmentasyon icin 11.44M parametredir. Duvar-saat egitim sureleri sirasiyla 23.9 ve 59.3 dakikadir. Ayni epoch/goruntu butcesi kullanildi; segmentasyonun daha buyuk head'i ve ek mask loss'u gercek pipeline maliyeti olarak saklandi.

Supervision ayni source instance'lara dayanir ama maskeler kutulardan daha zengin ve gercekte daha pahali etikettir. Bu nedenle deney adil bir target-trained task-pipeline A/B'sidir; esit annotation-dakikasi maliyet analizi degildir.

Paired 403 test-kare bootstrap'inda segment−detect F1 farkinin %95 araligi `[+7.02, +11.56]` puandir. Bu, test kareleri uzerindeki ornekleme belirsizligidir; tek-seed egitim varyansini kapsamaz.

## Sinir

Bu, PhenoBench UAV seker pancari domaininde temiz bir mimari/gorev kontroludur. Nihai robot kamerasi, video tracking, nozul footprint, deposition, kill rate ve crop injury olculmedi. Dolayisiyla saha atesleme onayi degildir.

Lisans siniri da vardir: PhenoBench `CC BY-NC-SA 4.0`, Ultralytics baseline ise `AGPL-3.0` veya enterprise lisanslidir. Bu agirliklar ticari deployment adayi degil, arastirma mimari kanitidir; urun modeli uygun lisansli kendi verimizle yeniden egitilmelidir.

Onceki WSD sonucu hedef kutularini gormus detector ile WSD'yi hic gormemis global segmenteri karsilastiriyordu. O sonuc, hedef-domain gercek veri gormenin etkisini kanitlar; saf detection-vs-segmentation karari degildir ve burada mimari gate'e dahil edilmedi.

## Dosyalar

- [Okunabilir PDF](results/FAIR_DETECTION_SEGMENTATION_KARARI_V1.pdf)
- [Dondurulmus metrik JSON](results/fair_detection_segmentation_metrics_v1.json)
- [Aciklamali ornekler](results/fair_detection_segmentation_gallery_v1/README.md)
