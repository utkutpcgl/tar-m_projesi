# Weedy Rice UAV gerçek-veri kalite ve zero-shot tanı raporu — v1

## Sonuç

[WeedyRice-RGBMS-DB](https://data.mendeley.com/datasets/vt4s83pxx6/1)
CC-BY-4.0 verisi indirildi; dış ve iç ZIP, metadata, RGB–maske eşleşmesi,
ontoloji, uçuş-ayrık rol, exact/dHash sızıntı ve görsel inceleme kapılarının
tamamını geçti. Kabul edilen ortak model değiştirilmedi.

Veri, 734 UAV RGB görüntüsü ve weedy-rice pozitif maskesi içerir. Kaynak
`0`, cultivated rice, toprak, su ve diğer negatif içeriği tek sınıfta
birleştirdiği için ortak `background/crop` etiketi değildir. Normalize
maskelerde yalnız şu fail-closed dönüşüm yapıldı:

```text
source 255 (weedy rice) -> common 2 (other vegetation / weed)
source   0 (not annotated as weedy rice) -> common 255 (ignore)
```

Bu nedenle 487 Thoaison görüntüsü kaliteli bir partial-label eğitim adayıdır,
ancak ayrı bir positive-only/partial-label loss protokolü olmadan mevcut ortak
model eğitimine açılamaz. Tamamen ayrı Longxuyen uçuşunun 247 görüntüsü yalnız
binary `external_calibration` tanısında kullanıldı.

## Immutable edinim

```text
outer archive:
  bytes:   5.288.295.277
  SHA-256: 62c9a168122e3076c750bfc928906d3d76d27848ad0f2b03b23a9743aed6aff3
  CRC:     pass

nested WeedyRice-RGBMS-DB.zip:
  bytes:   5.287.951.115
  SHA-256: e1cf031bc912da195ed61b7c0ea9016c8cffaf587ed82b5fd8b20ef06f386395
  members/files: 5.151 / 5.145
  compressed/uncompressed: 5.286.201.691 / 5.310.553.901 bytes
  full CRC: pass
  unsafe paths/symlinks: 0 / 0
```

Outer arşivin tek üyesi iç ZIP'tir. Yeniden çalıştırma durumunda yalnız boyut
değil, outer-member akış SHA-256'sı ile mevcut iç ZIP byte'ları da birebir
karşılaştırılır. Edinim makbuzu:
`data/processed/audits/weedy_rice_uav_acquisition_v1.json`.

HDD rezerv kapısı korundu. Dış+iç arşiv, kaynak-korumalı RGB/mask/metadata
altkümesi ve türetilmiş maskelerden sonra veri diskinde yaklaşık 290 GB boş
alan kaldı; kök diske büyük payload yazılmadı.

## Release envanteri ve metadata

| İçerik | Dosya |
|---|---:|
| RGB JPEG | 734 |
| Binary PNG mask | 734 |
| Multispectral TIFF | 2.936 (`G/R/RE/NIR`, her biri 734) |
| Publisher overlay JPEG | 734 |
| Metadata CSV | 2 × 3.670 satır |
| Metadata README | 1 |
| Root README | 1 |
| Publisher split listesi | 3 |

`filename_mapping.csv` ile `image_metadata.csv` primary-key kümeleri birebir
eşittir. 3.670 standardize ad, release'teki 734 RGB + 2.936 MS dosyasını tam
olarak kapsar. RGB metadata'sı dört uçuş için yayın tablosunu yeniden üretir:

| Tarih | Konum | RGB | Bizim rol |
|---|---|---:|---|
| 2024-06-02 | Thoaison | 115 | train adayı |
| 2024-06-04 | Thoaison | 331 | train adayı |
| 2024-09-30 | Thoaison | 41 | train adayı |
| 2025-01-15 | Longxuyen | 247 | external calibration |

Metadata irtifası `11,899–20,537 m` aralığındadır ve bildirilen 12/20 m
uçuşlarını destekler. Makale uçuş zamanını 09:30–15:30 olarak bildirirken CSV
minimumu 09:14:40'tır; bu küçük yayın/metadata uyuşmazlığı makbuza kaydedildi,
fakat örnek kimliği veya rol kararını değiştirmez.

## Publisher split'i neden reddedildi

Release, görüntü düzeyinde 438/148/148 train/val/test listeleri de içerir.
Her rol her uçuş tarihini içerir:

| Publisher rolü | 02 Haz | 04 Haz | 30 Eyl | 15 Oca |
|---|---:|---:|---:|---:|
| train | 62 | 200 | 23 | 153 |
| val | 25 | 63 | 12 | 48 |
| test | 28 | 68 | 6 | 46 |

Uçuşlar `%70` ön ve yan bindirmeyle çekildiğinden bu bölme komşu, güçlü
örtüşen kareleri bütün rollere dağıtır. Listeler release provenance olarak
saklandı ama eğitim, geliştirme veya test rolü üretmekte kullanılmadı.
İçerik görülmeden dondurulan bizim protokolümüz, her tarih+konum uçuşunu tek
role atar; train/calibration group overlap `0`'dır. Haricî test oluşturulmadı.

## Piksel ve görsel kalite kapısı

Tüm 734 RGB ve maskede:

- çözünürlük `1280×960`, RGB format/mode `JPEG/RGB`, mask `PNG/L`;
- stem eşleşmesi `734/734`, MS başına tam dört band ve overlay eşleşmesi;
- maske paleti yalnız `{0,255}` ve her maskede iki değer de mevcut;
- boş maske `0`, coverage `>=90%` olan maske `0`;
- coverage minimum/ortalama/medyan/maksimumu
  `0,002729 / 0,317087 / 0,240011 / 0,896001`;
- yayınlanan sekiz coverage-bin sayısı `71/88/171/79/66/151/43/65` ile
  birebir eşleşir.

Dört uçuş × sekiz coverage dilimi matrisi ve uçuş başına büyük ayrıntı
sayfaları incelendi. Pozitif poligonlar görünür açık/yoğun, farklı dokulu
weedy-rice kümelerini izledi; sistematik spatial offset, bozuk görüntü veya
bariz RGB–maske kayması görülmedi. Bu bounded QC, bağımsız uzman yeniden
etiketlemesi değildir.

15.857 mevcut gerçek görüntüye karşı SHA-256 exact + dHash-256 Hamming `<=2`
denetimi:

```text
candidate -> existing-real exact/near: 0
within-candidate exact/near:           0
cross-role exact/near:                 0
nearest existing-real Hamming:         min 59 / median 87 / max 101
```

Nihai veri kalite makbuzu:
`data/processed/audits/weedy_rice_uav_quality_v1.json`, SHA-256
`f1591d82ac6f0d3878a682df4bb49b432a9498c22b6a3ac4d65edd06d4d33baf`.

## Kabul edilmiş modelde Longxuyen zero-shot tanısı

Seed `17/29/43`, epoch-8 `last.pt`, source-tree ve tüm checkpoint artifact
hash'leri değerlendirmeden önce donduruldu. Model `eval()` modunda çalıştı;
source-validation eşikleri değişmedi, Longxuyen üzerinde threshold sweep veya
model seçimi yapılmadı.

247 karede pozitif piksel prevalence'i `%58,5205`'tir. Üç-seed ortalaması:

| Çıktı | IoU | Precision | Recall | Specificity | Pred. positive |
|---|---:|---:|---:|---:|---:|
| Semantic argmax | 0,597835 | 0,600645 | 0,992327 | 0,068876 | 0,966940 |
| Source-frozen weed candidate | 0,000064 | 0,410112 | 0,000064 | 0,999928 | 0,000067 |
| Source-frozen safe weed | 0,000064 | 0,410112 | 0,000064 | 0,999928 | 0,000067 |

Semantic argmax balanced accuracy yalnız `0,530602`'dir. IoU, pozitif
coverage arttıkça `0,211856 -> 0,835709` yükselirken specificity
`0,206922 -> 0,007795` düşer. Dolayısıyla `0,597835` IoU iyi bir weedy-rice
ayrımı anlamına gelmez; model görüntünün neredeyse tamamını genel
`other vegetation` olarak işaretleyerek yüksek-prevalence skoru elde eder.

Threshold-free weed-probability sıralaması daha bilgi vericidir:

```text
approx AP:    0,669793 +/- 0,022433
approx AUROC: 0,657294 +/- 0,024041
AP - prevalence baseline: +0,084588
```

Model bir miktar sıralama sinyali taşır, fakat cultivated-rice/weedy-rice
ayrımı zayıftır. Kaynaktan dondurulmuş `0,995` güvenlik eşiği ise bu yeni
UAV/mature-rice alanında neredeyse tüm pozitifleri bastırır. Bu, hem semantik
domain gap'i hem de crop/domain-koşullu kalibrasyon ihtiyacını gösterir.

Kanonik tanı:
`data/processed/audits/weedy_rice_uav_binary_diagnostic_v1.json`, SHA-256
`1a9fd3cb3339afd3804047cd45584f02d79a7e36c3822e88d38643b7d8a3417d`.

## Karar ve sonraki sıra

1. Kabul edilmiş ortak checkpoint değişmez; bu veri hiçbir modeli seçmedi.
2. Weedy Rice verisi kaliteli ve lisansı açıktır, fakat ortak üç-sınıf
   supervision için ontolojisi eksiktir. 487 train adayı şimdilik kilitlidir.
3. Bir sonraki en yüksek değerli gerçek veri hâlâ çok-ülkeli, altı sınıflı
   RiceSEG'dir. Erişim koşulu kabul edildi; pinli indirme yalnız bu makinedeki
   yerel Hugging Face tokenını bekler.
4. Gerçek-veri kapsamı tamamlandıktan sonra, Weedy Rice için ayrı dondurulmuş
   positive-only/partial-label specialist protokolü; ardından replay ve
   mevcut-domain non-inferiority kapıları değerlendirilebilir.

Kaynak makale ve veri kaydı:
[Nguyen et al., Data in Brief 2025](https://pmc.ncbi.nlm.nih.gov/articles/PMC12670920/),
[Mendeley Data v1](https://data.mendeley.com/datasets/vt4s83pxx6/1).
