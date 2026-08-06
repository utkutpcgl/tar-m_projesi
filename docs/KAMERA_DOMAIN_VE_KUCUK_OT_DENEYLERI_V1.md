# Kamera, domain adaptation ve küçük-ot deneyleri V1

## Kısa karar

En büyük iki etken doğrulandı: (1) sahnede bitkinin kaç gerçek piksel kapladığı ve focus/motion kalitesi, (2) hedef koşula benzer gerçek veri görülmesi. Crop-row prior yardımcı bir safety katmanıdır; ana çözüm değildir.

Global generalist küçük-ot gate'i kontrolü korudu. Canvas768 iki seedde hedef-SugarBeets specialist kapısını geçti (ortalama +0,1301 mIoU), fakat ortalama CWFID farkı −0,0442 olduğu için yalnız hedef robot kamera koşuluna route edilmelidir. Gerçek holdout'ta kör 1,5×/2× inference upscale reddedildi.

## Kamera/optik

| Koşul | mIoU | Crop IoU | Weed IoU | Safe weed recall |
|---|---:|---:|---:|---:|
| resolution_256 | 0.555275 | 0.252522 | 0.438384 | 0.193610 |
| resolution_384 | 0.633823 | 0.360261 | 0.559982 | 0.253938 |
| reference_512 | 0.695161 | 0.465965 | 0.634016 | 0.333418 |
| resolution_768 | 0.775312 | 0.613937 | 0.721782 | 0.441553 |
| resolution_1024 | 0.824953 | 0.715777 | 0.766196 | 0.488220 |
| zoom_1p33 | 0.743955 | 0.569335 | 0.675029 | 0.357451 |
| zoom_1p67 | 0.778560 | 0.649158 | 0.698579 | 0.379394 |
| dim_no_led | 0.696819 | 0.470255 | 0.635446 | 0.358326 |
| dim_led_energy30 | 0.696357 | 0.465610 | 0.637541 | 0.316189 |
| dim_led_energy60 | 0.695805 | 0.465134 | 0.636164 | 0.304932 |
| dim_led_energy120 | 0.697405 | 0.469235 | 0.636648 | 0.295951 |
| defocus_sigma1p5 | 0.688817 | 0.450677 | 0.629789 | 0.339690 |
| defocus_sigma3p0 | 0.612601 | 0.312998 | 0.538911 | 0.268842 |
| motion_blur_7px | 0.683076 | 0.441241 | 0.622496 | 0.318464 |
| digital_input_256 | 0.557988 | 0.254842 | 0.443795 | 0.185915 |
| detail_loss_256_up512 | 0.694546 | 0.460478 | 0.637238 | 0.340618 |
| digital_upscale_1024 | 0.814356 | 0.696265 | 0.754515 | 0.529885 |

Bu 8 görülmemiş sentetik geometri × 2 karelik eşlenmiş tanı setidir. 1024/768 koşulları gerçek yeniden renderdır; interpolation değildir. Işık enerjisi simulator kontrolüdür, ölçülmüş lux/watt değildir.

### Sensör detayı ve model rasterını ayırma

| Girdi | Model rasterı | mIoU | Weed IoU | AMP core latency |
|---|---:|---:|---:|---:|
| 512 referans | 512 | 0.695161 | 0.634016 | 4.15 ms |
| 512→256 | 256 | 0.557988 | 0.443795 | 3.67 ms |
| 512→256→512 | 512 | 0.694546 | 0.637238 | 4.15 ms |
| 512→1024 (yeni detay yok) | 1024 | 0.814356 | 0.754515 | 22.34 ms |
| Native 1024 | 1024 | 0.824953 | 0.766196 | 22.34 ms |

Dijital 512→1024 kolu yeni optik bilgi eklemeden `11.92` mIoU puan kazandı; native 1024 ek olarak `1.06` puan verdi. Bu temiz sentetik holdout'ta model raster/token darboğazı baskındır. 1024 core forward 512'ye göre `5.38×` maliyetlidir. Latency 30 warm-up + 100 tekrarlı yalın model forward'dır; preprocessing, tiling ve safety policy dahil değildir.

### Gerçek holdout yazılımsal raster A/B

| Alan | Raster | mIoU | <14 px component hit | Crop risk | Safe weed recall | Perception ms/image |
|---|---:|---:|---:|---:|---:|---:|
| SugarBeets robot | 1.0× | 0.577247 | 0.002826 | 0.041017 | 0.084684 | 34.05 |
| SugarBeets robot | 1.5× | 0.362096 | 0.007267 | 0.651993 | 0.039388 | 95.05 |
| SugarBeets robot | 2.0× | 0.428179 | 0.017763 | 0.296019 | 0.186208 | 210.21 |
| WeedMap UAV | 1.0× | 0.349458 | 0.000211 | 0.001451 | 0.023574 | 8.97 |
| WeedMap UAV | 1.5× | 0.350475 | 0.001054 | 0.003153 | 0.037650 | 11.54 |
| WeedMap UAV | 2.0× | 0.349212 | 0.002318 | 0.002716 | 0.030325 | 16.11 |

Bu kol aynı gerçek capture'ı yalnız yazılımla büyütür; yeni optik bilgi eklemez. Tahmin aynı native etiket grid'ine geri alınır ve dondurulmuş safety policy yeniden ayarlanmaz. SugarBeets'te 1,5×/2× mIoU ciddi düştü ve crop riski yükseldi; WeedMap mIoU yaklaşık sabit kalırken <14 px temas mutlak olarak %0,24'ün altında kaldı. Kör inference upscale reddedildi; raster değişimi native detay veya train–inference uyumuyla birlikte tasarlanmalıdır.

### Nesne boyutu darboğazı

| Weed semantik-proxy boyutu | Proxy sayısı | Herhangi temas | Proxy içi pixel recall |
|---|---:|---:|---:|
| <14 px | 334 | 0.023952 | 0.006773 |
| 14–28 px | 53 | 0.679245 | 0.163237 |
| 28–56 px | 21 | 1.000000 | 0.467291 |
| ≥56 px | 5 | 1.000000 | 0.468659 |

Boyut, bağlı GT semantik bileşen alanından hesaplanan eşdeğer daire çapıdır; botanik instance veya bounding-box boyutu değildir. 28 px üstündeki güçlü sonuç yalnız 26 proxy'ye dayanır. Yaklaşık 28 px kamera/GSD hedefi gerçek kamera bench'inde teyit edilmesi gereken bir başlangıç hipotezidir.

### Kamera ön-tasarım hesabı

Başlangıç formülü `GSD_max (mm/pixel) = hedef en küçük weed eşdeğer çapı (mm) / 28` şeklindedir. Örneğin 20 mm weed için yaklaşık 0,71 mm/pixel gerekir; bu 2048 yatay pixelde yaklaşık 1,46 m, 4096 pixelde 2,93 m yatay kapsama karşılık gelir. Bunlar sentetik tanıdan türetilmiş ön-tasarım sayılarıdır; gerçek sensör/lens/focus/motion bench'iyle doğrulanmalıdır. Native çözünürlüğü modele girmeden küçültmek fiziksel kamera avantajını silebilir.

### Gerçek alanlarda boyut dağılımı

| Alan | Weed proxy | <14 px payı | ≥56 px payı | Herhangi temas | mIoU |
|---|---:|---:|---:|---:|---:|
| Sorghum final test | 183 | 0.005464 | 0.978142 | 0.967213 | 0.827706 |
| SugarBeets robot | 5870 | 0.421976 | 0.080920 | 0.439693 | 0.577247 |
| WeedMap UAV | 5113 | 0.928222 | 0.002543 | 0.069822 | 0.349458 |

Boyut dağılımı performansla güçlü biçimde hizalanır; fakat domainler arasında tür, kamera, GSD ve hedef-veri exposure'ı da birlikte değiştiği için bu tablo tek başına nedensel ablation değildir.

## Domain-adaptation eğrisi

| Kol | Source mIoU | Sorghum calibration mIoU | Robust min |
|---|---:|---:|---:|
| domainadapt_sorghum_n000_e8_v1 | 0.812010 | 0.639178 | 0.335460 |
| domainadapt_sorghum_n010_e8_v1 | 0.808010 | 0.812193 | 0.344046 |
| domainadapt_sorghum_n025_e8_v1 | 0.790701 | 0.799409 | 0.346763 |
| domainadapt_sorghum_n050_e8_v1 | 0.801443 | 0.819070 | 0.347748 |
| domainadapt_sorghum_n100_e8_v1 | 0.800548 | 0.823624 | 0.344511 |
| domainadapt_sorghum_n202_e8_v1 | 0.791751 | 0.821982 | 0.341861 |

Dondurulmuş seçim kuralı: `domainadapt_sorghum_n010_e8_v1` (10 hedef karesi). Sorghum %45, SugarBeets %20, source validation %15, CWFID %10 ve WeedMap %10 ağırlıklıdır; breadth regresyonları hard-gate edilir ve 0,005 skor toleransında daha az veri seçilir.

Seçilen kolun Sorghum frozen-safe crop risk / weed recall değerleri `0.002679 / 0.266049`. Bunlar source-frozen eşiklerdir; target tuning yapılmadı.

Tüm kollar aynı seed, epoch, samples/epoch ve optimizer bütçesini kullanır. Hedef alt kümeler strict-nested ve yalnız resmi train RGB'lerinden seçildi. Evaluation resmi external_calibration'dır; external_test açılmadı.

### 10-kare seed29 paired confirmation

| Seed | Source Δ | Sorghum Δ | CWFID Δ | SugarBeets Δ | WeedMap Δ | Gate |
|---|---:|---:|---:|---:|---:|---|
| 17 | -0.004001 | +0.173015 | +0.029740 | +0.104263 | +0.008587 | geçti |
| 29 | -0.014514 | +0.186296 | +0.026091 | +0.014878 | -0.014744 | geçti |
| ortalama | -0.009257 | +0.179656 | +0.027916 | +0.059571 | -0.003079 | geçti |

## Küçük-ot eğitim A/B

| Kol | Source | CWFID | Sorghum | SugarBeets | WeedMap | Robust min |
|---|---:|---:|---:|---:|---:|---:|
| smallobj_control_512_e8_v1 | 0.801428 | 0.638102 | 0.818929 | 0.556159 | 0.348903 | 0.348903 |
| smallobj_scaleup_512_e8_v1 | 0.792612 | 0.603554 | 0.807279 | 0.679054 | 0.347317 | 0.347317 |
| smallobj_replay10_512_e8_v1 | 0.803890 | 0.607126 | 0.816478 | 0.561938 | 0.356651 | 0.356651 |
| smallobj_replay10_scaleup_512_e8_v1 | 0.799819 | 0.508764 | 0.767908 | 0.665367 | 0.342541 | 0.342541 |
| smallobj_canvas768_e8_v1 | 0.797158 | 0.596309 | 0.815866 | 0.699704 | 0.356265 | 0.356265 |

Dondurulmuş global küçük-ot seçim kuralı: `smallobj_control_512_e8_v1`. SugarBeets ve WeedMap küçük-nesne tanısı toplam %50, diğer gerçek alanlar %50 ağırlık alır; tümünde sıkı non-inferiority kapıları vardır.

Global gate kontrolü korudu. Buna rağmen hedef-kamera adayı canvas768, seed17 SugarBeets mIoU'yu `0.556159` → `0.699704` yükseltti; CWFID `0.638102` → `0.596309` geriledi. İkinci seed hedef-specialist kapısını da geçti.

Replay yalnız train split'inden 4–28 px semantik weed bileşeni merkezli 512×512 kayıplardan oluşturuldu. Bunlar botanik instance değildir.

### 768 hedef-kamera adayı — paired seed teyidi

| Seed | Source Δ | CWFID Δ | Sorghum Δ | SugarBeets Δ | WeedMap Δ | Target gate |
|---|---:|---:|---:|---:|---:|---|
| 17 | -0.004270 | -0.041793 | -0.003063 | +0.143546 | +0.007363 | geçti |
| 43 | -0.006646 | -0.046678 | +0.007119 | +0.116648 | +0.006796 | geçti |
| ortalama | -0.005458 | -0.044235 | +0.002028 | +0.130097 | +0.007079 | geçti |

Hedef-specialist kapısı seed43 sonucu görülmeden donduruldu: SugarBeets en az +0,05; source −0,015, Sorghum −0,02, WeedMap −0,01 ve CWFID −0,06 altına düşmeyecek. Bu geçiş global CWFID −0,02 breadth kapısını geçersiz kılmaz.

### Müdahale-odaklı kontrol / 768 hedef adayı kıyası

| Alan / model | mIoU | Crop risk | Spray recall | <14 px hit | Merkez ≤1 yarıçap | ≥%50 coverage |
|---|---:|---:|---:|---:|---:|---:|
| SugarBeets robot / Global kontrol | 0.557436 | 0.044112 | 0.041522 | 0.001615 | 0.033731 | 0.002896 |
| WeedMap UAV / Global kontrol | 0.349823 | 0.001187 | 0.062893 | 0.003793 | 0.006063 | 0.003520 |
| SugarBeets robot / 768 hedef adayı | 0.700327 | 0.014503 | 0.097184 | 0.004037 | 0.096593 | 0.003748 |
| WeedMap UAV / 768 hedef adayı | 0.356379 | 0.000332 | 0.032430 | 0.000421 | 0.000782 | 0.000587 |

SugarBeets'te canvas768 crop riskini %4,41'den %1,45'e indirip spray recall'ı %4,15'ten %9,72'ye ve tüm-component hit'i %4,92'den %15,28'e yükseltti. WeedMap'te ise safe recall %6,29'dan %3,24'e, <14 px hit %0,38'den %0,04'e düştü. Bu nedenle 768 yalnız hedef robot kamerasına route edilen specialist; UAV/genel kullanımda kontrol fallback'tir.

Spray recall dondurulmuş güvenli aksiyonun weed pixellerini yakalama oranıdır. Merkez ve coverage metrikleri bağlı semantik weed bileşenlerinden türetilen proxy'lerdir; kök/meristem veya gerçek botanik instance doğrulaması değildir.

## Row prior

| Alan | Mod | mIoU | Crop risk | Safe weed recall |
|---|---|---:|---:|---:|
| sorghum_external_calibration | baseline | 0.826289 | 0.000177 | 0.368854 |
| sorghum_external_calibration | practical_guard | 0.826289 | 0.000177 | 0.324921 |
| sorghum_external_calibration | oracle_guard | 0.826289 | 0.000177 | 0.349771 |
| sorghum_external_calibration | practical_0p35 | 0.827032 | 0.000000 | 0.000136 |
| sorghum_external_calibration | practical_0p65 | 0.741390 | 0.000000 | 0.000136 |
| sorghum_external_calibration | oracle_0p35 | 0.831375 | 0.000000 | 0.050357 |
| sorghum_external_calibration | oracle_0p65 | 0.740398 | 0.000000 | 0.050357 |
| sugarbeets_robot_holdout | baseline | 0.576753 | 0.045480 | 0.078294 |
| sugarbeets_robot_holdout | practical_guard | 0.576753 | 0.040557 | 0.066005 |
| sugarbeets_robot_holdout | oracle_guard | 0.576753 | 0.020295 | 0.069813 |
| sugarbeets_robot_holdout | practical_0p35 | 0.572991 | 0.004229 | 0.005204 |
| sugarbeets_robot_holdout | practical_0p65 | 0.543335 | 0.004229 | 0.005204 |
| sugarbeets_robot_holdout | oracle_0p35 | 0.583272 | 0.004390 | 0.005807 |
| sugarbeets_robot_holdout | oracle_0p65 | 0.587464 | 0.004390 | 0.005807 |
| synthetic_v11_unseen_rows | baseline | 0.695791 | 0.000000 | 0.321473 |
| synthetic_v11_unseen_rows | practical_guard | 0.695791 | 0.000000 | 0.294020 |
| synthetic_v11_unseen_rows | oracle_guard | 0.695791 | 0.000000 | 0.242527 |
| synthetic_v11_unseen_rows | practical_0p35 | 0.696742 | 0.000000 | 0.000000 |
| synthetic_v11_unseen_rows | practical_0p65 | 0.646710 | 0.000000 | 0.000000 |
| synthetic_v11_unseen_rows | oracle_0p35 | 0.697165 | 0.000000 | 0.000000 |
| synthetic_v11_unseen_rows | oracle_0p65 | 0.633332 | 0.000000 | 0.000000 |

Oracle sonuç GT crop maskesinden yalnız sıra geometrisi çıkardığı için label-leaking üst sınırdır. Pratik sonuç model crop olasılığından fit edilir. Guard yalnız mevcut güvenli aksiyonu veto eder.

## Kanıt yolları

- Kamera metrikleri: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_optics_intervention_v1`
- Row-prior metrik/görselleri: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/crop_row_prior_v1`
- Domain curve: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/domain_adaptation_curve_v1/results.json`
- Küçük-ot A/B: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/small_object_training_ablation_v1/results.json`
- 768 hedef-specialist seed43 teyidi: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/small_object_canvas_confirm_v1/results.json`
- Gerçek holdout raster A/B: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_real_raster_intervention_v1`
- 768 hedef adayı müdahale metrikleri: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/small_object_selected_intervention_v1`
- Self-contained veri/receipt kökü: `/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/processed/audits/camera_domain_report_v1`

## Sınırlamalar

Tek seed ekranları eğitim varyansını tam ölçmez. Sentetik kamera eğrisi yön/duyarlılık kanıtıdır, gerçek sensör garantisi değildir. Sorghum adaptation aynı dataset/tek saha dağılımında olduğundan yeni-tarla performansı için iyimser olabilir. CWFID, SugarBeets ve WeedMap başka dataset dağılımlarıdır fakat bu panellerin her biri yalnız bir field/session capture group içerir; çok-çiftlik genellemesi kanıtlanmış değildir. Kesin donanım kararı gerçek kamera bench'i ve mm-kalibre actuator testi ister.

## Dış kaynaklar

- [Carbon Robotics LaserWeeder — kamera ve LED teknik bileşenleri](https://carbonrobotics.com/laserweeder) (üretici beyanı).
- [Milioto, Lottes ve Stachniss — görülmemiş tarlaya az verili yeniden eğitim](https://www.ipb.uni-bonn.de/wp-content/papercite-data/pdf/milioto2018icra.pdf).
- [Sa ve ark. — WeedMap; GSD ve downsampling etkisi](https://arxiv.org/abs/1808.00100).
- [LaserWeeder saha çalışması; yüksek çözünürlüklü görüntü ve erken weed hedefleme](https://pmc.ncbi.nlm.nih.gov/articles/PMC12268811/).
