# Çevrimiçi varlık A/B — 2026-07-30

## Eşlenik test

Aynı `camera_door`, seed `59020`, kapı açısı `52.64°`, 960×540 ve 32 spp
koşulunda yalnız mavi sabit duvar materyali değiştirildi:

- [Canonical procedural hammertone](asset_ab/wall_procedural_hammertone_seed59020.png)
- [Poly Haven Blue Metal Plate 2K](asset_ab/wall_polyhaven_blue_metal_seed59020_rejected.png)
- [Gerçek cam-10 karşılaştırma karesi](../../../260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/LED_RFIDTAG_230126/images/train/task_9_dataset_2026_01_22_15_01_12_yolo_1.1__İVEDİK_2026-01-21_cam-10_batch-1_frame-00340.png)

Sağ mavi duvar ROI ölçümünde procedural görüntünün ortalama RGB’si
`(53.94, 94.83, 129.83)`, Poly Haven’ın `(81.51, 106.19, 118.97)`, gerçek
karşılaştırmanın `(50.81, 103.34, 187.07)` oldu. ROI’ler eşlenik maskeler
değil; bu sayılar renk/tekstür yönünü gösteren QC ölçümüdür, BRDF kalibrasyonu
değildir.

## Karar

Poly Haven taraması:

- mavi doygunluğunu ve mikro-kontrastı daha da düşürüyor;
- gerçek tırtıklı/çekiçlenmiş boya yerine uzun dikey sac izleri gösteriyor;
- duvar/kabin ölçeğinde tekrarlanan birleşim çizgileri üretiyor.

Bu yüzden canonical yapılmadı. `procedural_hammertone_v2` daha doğru görsel
bazdır; sonraki doğru iyileştirme generic foto-tarama değil, gerçek boş hazne
makro çekiminden ölçülen tileable normal/roughness katmanıdır.

## Beton PBR A/B

Aynı `camera_angled`, seed `59221`, geometri, kapı, kamera, ışık ve 960×540
32 spp koşulunda yalnız beton materyali değiştirildi:

- [Procedural cast concrete](asset_ab/concrete_procedural_seed59221.png)
- [ambientCG Concrete003 düşük-oranlı box-projection hibrit](asset_ab/concrete_ambientcg_hybrid_seed59221.png)

Concrete görünür maskesinin 13 piksel içe aşındırılmış bölgesinde sekiz eş
karenin ortalaması:

| Profil | RGB ortalaması | Luma std | FIND_EDGES ort. | `Y≥240` |
| --- | --- | ---: | ---: | ---: |
| Procedural | `(192.69, 185.95, 180.31)` | `15.47` | `2.38` | `0` |
| ambientCG hibrit | `(182.86, 175.68, 170.04)` | `17.61` | `2.68` | `0` |

İki zaman/kamera ayrık gerçek numunenin bbox içi karşılaştırma ROI’ları yaklaşık
`RGB=(178.88,173.27,147.60), std=34.39, edge=9.00` ve
`RGB=(183.69,182.10,182.85), std=33.23, edge=3.94` verdi. Bunlar segmentasyon
maskesi veya BRDF ölçümü değildir; yalnız yön kontrolüdür. Hibrit, silhouette
ve procedural hasarı değiştirmeden tonu ve mikro-kontrastı her iki örneğe de
yaklaştırdığı için Blender’da canonical yapıldı. Foto-map tam replacement
değildir: renk etkisi `%34`, roughness etkisi `%38`, displacement bump
`0.55 mm` ile sınırlıdır ve box projection dikişi azaltır.

## Tam model taraması

`Simple Concrete Compression Machine` (Sketchfab, 9.8k triangle) indirilebilir
ve production için lisanslanmış bir kaynak göstermediği gibi iç hazne
topolojisi de EBİS ile uyuşmuyor. `Concrete Mix Test Cylinder W3` indirilebilir
CC-BY bir 2M-triangle tarama olsa da sıkıştırma sonrası hasarlı numunedir;
sağlam nizami silindir bazı olarak kullanılamaz. ambientCG
`PaintedMetal003` CC0’dır fakat yoğun boya kaybı/açık metal içerdiği için
reddedildi.

Kaynak ve SHA-256 kontratları:
`assets/external/polyhaven/blue_metal_plate_2k/SOURCE.json` ve
`assets/external/ambientcg/Concrete003_2K_JPG/SOURCE.json`.

## Pass-1 Rough Concrete 1K deneyi

Poly Haven `Rough Concrete` ayrıca resmi API'den 1K diffuse, roughness ve
displacement olarak alındı. Kaynak sayfa `1.23 m` fiziksel genişlik, lisans
`CC0 1.0`; API files hash'i
`38d884db7ce867ff2e6445a31abfe70aa5adc7b5`. Exact dosya SHA-256 ve import
ayarları
[`SOURCE.json`](../../assets/external/polyhaven/rough_concrete_1k/SOURCE.json)
içindedir.

Same-seed `59303` cylinder ve `59307` cube, `960×540 / 48 spp` testinde
yalnız beton finish'i değişti. Concrete bbox içi ortalama mutlak RGB farkı
sırasıyla `4.78/255` ve `4.94/255` oldu:

- [dört-panel actual-pixel A/B](asset_ab/polyhaven_rough_concrete_1k_trial_rejected.png)

Düşük oranlı güvenli blend EBİS'e özgü yararlı bir döküm izi eklemedi;
daha güçlü oran ise kaynağın dış ortam sıva/plaster karakterini taşıyacaktı.
Bu nedenle asset hak/provenance açısından güvenli, görsel karar açısından
`REJECTED`; production profilini değiştirmedi.
