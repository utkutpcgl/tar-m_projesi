# CropCraft texture-backed asset v3 kalite ve gerçek-domain A/B raporu

## 1. Karar

`cropcraft_agri_robust_v3_r3` paketi, v2 özel asset kontrolüne karşı önceden
dondurulan eşit-bütçeli gate'i **geçti**. Model, kod, epoch, örnekleme bütçesi
ve seed'ler değiştirilmedi; yalnız 100 karelik sentetik pilot/asset paketi
değiştirildi. Seed `17/29/43`, epoch `8` ve `3.600` örnek/epoch koşullarında
üç gerçek geliştirme alanının minimumu olan robust mIoU üç seed'in üçünde de
yükseldi:

| Seed | v2 özel asset | v3 texture-backed | Fark |
|---:|---:|---:|---:|
| 17 | 0,590082 | 0,604038 | +0,013956 |
| 29 | 0,535603 | 0,557064 | +0,021462 |
| 43 | 0,560132 | 0,575758 | +0,015626 |
| **Ortalama** | **0,561939** | **0,578953** | **+0,017015** |

Dondurulan dört kabul kontrolünün tamamı geçti: pozitif paired ortalama, en
az 2/3 seed galibiyeti (gerçekte 3/3), kaynak validation regresyonu en fazla
`0,01` ve Sorghum validation regresyonu en fazla `0,01`.

Kanonik seçim makbuzu
`data/runs/simulation_asset_quality_selection_v3.json` dosyasındadır.
Medyan-seed kuralıyla seçilen araştırma checkpoint'i seed 43 epoch-8
`last.pt`, SHA-256 değeri
`2fed7e2b4a3e42b183ffa3911d2014ed60e8088efc5532b7a79753d7356b3771`'dir.

Bu karar, bundan sonraki kontrollü sentetik üretimde v3 asset tarifini v2
tarifine tercih eder. Tarihsel epoch-15 genel modeli otomatik değiştirmez ve
saha/püskürtme onayı değildir.

## 2. V2 ne kadar optimizeydi, v3 neyi değiştirdi?

V2 hattı zaten deterministik üretim, scene-ayrık pilot, asset inventory,
statik geometri, RGB/mask, duplicate, domain-gap ve gerçek-veri A/B kapılarını
geçmişti. V3 bu çalışan pipeline'ı değiştirmeden iki içerik boşluğunu hedefledi:

| Özellik | v2 özel paket | v3 paket |
|---|---:|---:|
| Crop OBJ | 15 | 45 = 15 geometri × 3 albedo fenotipi |
| Bağımsız crop geometrisi | 15 | 15 |
| Crop büyüme evresi | 5 | 5 |
| Crop yüz sayısı, min/medyan/max | 356/676/1.156 | 356/676/1.156 |
| Weed modeli | 24 prosedürel | 24 prosedürel + 27 texture-backed |
| Resmi referans bitki kaynağı | 0 | 4 |
| Debris / soil PBR / HDRI | 16 / 3 / 3 | 16 / 3 / 3 |
| Paket boyutu | 71.906.159 byte | 127.882.101 byte |

Üç crop fenotipi `healthy_dark`, `healthy_light` ve `field_stress` olarak
donduruldu. Bu, 45 bağımsız morfoloji olduğu anlamına gelmez; gerçek morfoloji
sayısı dürüstçe 15'tir. Asset-only hipotezini izole etmek için v2 soil, HDRI,
debris, kamera ve sahne dağılımı korunmuştur.

## 3. Eklenen yüksek kaliteli assetler ve provenance

Resmi Poly Haven 2K GLTF paketlerinden dört CC0 kaynak kullanıldı:

- [Weed Plant 02](https://polyhaven.com/a/weed_plant_02),
- [Nettle Plant](https://polyhaven.com/a/nettle_plant),
- [Shrub Sorrel 01](https://polyhaven.com/a/shrub_sorrel_01),
- [Dandelion 01](https://polyhaven.com/a/dandelion_01).

Kaynaklar Blender ile authored varyant gruplarına ayrıldı, metre ölçeğinde
erken-yabancı-ot aralığına normalize edildi ve CropCraft'ın OBJ/MTL hattına
aktarıldı. Sonuç 27 texture-backed weed varyantıdır. Resmi metadata, yazar,
source URL, byte count/MD5 ve indirilen dosya SHA-256 değerleri `PACK.json`
içinde tutulur. Poly Haven girdileri [CC0 lisanslıdır](https://polyhaven.com/license);
prosedürel geometri ve crop albedo haritaları da CC0-1.0 olarak kaydedildi.

Paket kanıtları:

- pack ID: `cropcraft_agri_robust_v3_r3`;
- `PACK.json` SHA-256:
  `bc41b9b1a262eb886586d81e6d947c91cf24878c9df5a9962c46edfe6ba633b0`;
- inventory SHA-256:
  `05dc5d380f612d867e33248a559eca5b41238ff9da2f64d374e9dbbd904844e0`;
- inventory: 284 dosya, 127.882.101 byte;
- statik gate SHA-256:
  `8ebbffbf878ac7ed66b40fd5ba9ebb7a7a144c6e7e46af10dd1df41ba696350c`.

İndirme öncesi boş alan `368.615.645.184` byte, hesaplanan güvenli gereksinim
`1.285.484.864` byte ve ilan edilen yeni indirme toplamı `22.643.574` byte'tı;
kapasite gate'i geçti. Paket HDD-backed `data` köküne yazıldı.

Kaynak paketlerde diffuse/normal/ARM rolleri, CC0 metadata ve indirme hash'leri
doğrulandı; R3 MTL dosyalarının referans verdiği texture dosyaları ayrıca
varlık kontrolünden geçti. Bu, CropCraft renderer'ının bütün PBR kanallarını
fiziksel olarak eksiksiz simüle ettiğini kanıtlamaz; kabul edilen görünür
iyileştirme ve gerçek-domain etkisi ayrı kapılarla ölçülmüştür.

## 4. Başarısız iterasyonlar

Başarısız sürümler silinmedi ve eğitime alınmadı:

- `cropcraft_agri_robust_v3_r1` sayısal smoke gate'lerini geçti, fakat OBJ
  export MTL dosyalarına texture basename'i yazıp görselleri yanına
  kopyalamadığı için referans weed'ler mor veya beyaz render edildi. Manuel
  receipt `passed=false` ile paketi pilot öncesinde reddetti.
- `cropcraft_agri_robust_v3_r2` bu yol sorununu görünürde düzeltti, fakat yeni
  `reference_material_texture_files_exist` statik kontrolünde kaldı.
- `cropcraft_agri_robust_v3_r3` texture yollarını MTL konumuna göre çözdü;
  statik, smoke ve manuel gate'leri ancak bundan sonra geçti.

Bu iterasyon, yalnız geometri/metadata denetiminin materyal çözümlemesini
kanıtlamadığını gösterdi. Asset audit script'ine geometri-only hash, bağımsız
crop geometri sayımı, albedo/CC0 kaynak rolleri, texture-backed model sayımı
ve gerçek MTL texture-file existence kontrolleri kalıcı olarak eklendi.

## 5. Static, smoke, pilot ve leakage kapıları

R3 statik audit'inde 22 kontrolün tamamı geçti. Önemli sonuçlar:

- 45 crop OBJ, 15 bağımsız crop geometrisi, 5 büyüme evresi, 3 albedo fenotipi;
- 4 weed ailesinde toplam 51 model, bunların 27'si yeni texture-backed;
- 4 resmi CC0 model kaynağı;
- dejenere yüz `0`, beyan edilen crop yükseklik hatası `0`;
- 16 debris, 3 soil PBR ve 3 HDRI ailesi;
- inventory, download, lisans ve materyal texture dosyaları tam.

Kabul edilen smoke 3 sahne/12 karede crop-free ve weed-free kare, exact RGB
duplicate ve sahneler-arası exact mask duplicate üretmedi. RGB/mask hizası,
ölçek, ground contact, crop fenotip görünürlüğü ve eksik-texture rengi manuel
olarak da geçti.

Kabul edilen tam pilot `data/synthetic/cropcraft/agri_robust_pilot_v3_r1`
altındadır:

| Kontrol | Sonuç |
|---|---:|
| Bağımsız scene / kare | 25 / 100 |
| Renderer-QC train/val scene | 20 / 5 |
| Crop-free kare | 0 |
| Weed-free kare | 3 (%3) |
| Ortalama crop / weed piksel oranı | 0,009437 / 0,022089 |
| Exact RGB duplicate | 0 |
| Scene'ler arası exact mask duplicate | 0 |
| Kullanılan crop OBJ / soil / HDRI | 45 / 3 / 3 |

Yedi deterministik sahnede RGB/mask çiftleri manuel incelendi. Pilot receipt
SHA-256 değeri
`cb8d45c27bf45f65814843e3d14c62103968f31fe32ee9091c150e427b7a6e69`'dur.

Birleşik manifest 5.803 örnek, train/val `4.166/1.637` ve sentetik 100 örnek
içerir. Renderer-val sahneleri yalnız render QC rolündedir; model validation
değişmeden 1.637 gerçek görüntüdür. Sentetik karelerin tamamı `%10` sampler
exposure için train rolüne çevrildi. Manifest SHA-256
`1cff1814b5c667d3a3d2c51e9c5b1df347511effb90e4f97f67def34e5b6af3b`,
normalize maske ağacı SHA-256
`1fcd37429560e919802f20fae78eedaa4adc4095e2a810351a7522967949e2fe`'dir.
DHash-256 Hamming≤2 denetiminde 5.803 örnekte train/val eşleşmesi `0`'dır.

## 6. Domain-gap taraması

Gerçek altı eğitim kaynağından kaynak başına 80 ve v3 pilotundan 80
deterministik örnek kullanıldı. Brightness, brightness std, crop/weed oranı,
green dominance, saturation, texture gradient ve ignore oranı medyanlarının
tamamı gerçek pooled q05–q95 aralığındaydı.

V2'den v3'e belirgin düşük-seviye değişimler küçüktür. Weed-fraction medyanı
`0,024437 → 0,019772` (`-0,004665`) düştü; crop-fraction medyanı
`+0,000227`, saturation `+0,001810`, texture gradient `-0,000860` değişti.
Bu sapma sonuç görüldükten sonra ayarlanmadı; aksi halde dondurulmuş asset-only
hipotezi kirlenirdi. Low-order tarama yalnız kaba uyumsuzluk kontrolüdür;
gerçek geliştirme A/B'sinin yerine geçmez.

## 7. Eşit-bütçeli gerçek geliştirme sonucu

| Alan, üç-seed ortalama mIoU | v2 özel asset | v3 texture-backed | v3 − v2 |
|---|---:|---:|---:|
| Kaynak gerçek validation | 0,797521 | 0,798458 | +0,000936 |
| CWFID `external_calibration` | 0,561939 | 0,578953 | **+0,017015** |
| Sorghum `external_calibration` | 0,818323 | 0,821966 | +0,003643 |
| Robust minimum | 0,561939 | 0,578953 | **+0,017015** |

CWFID crop IoU ortalaması `0,217782 → 0,249657`, weed IoU ortalaması
`0,492573 → 0,512183` yükseldi. Sorghum crop/weed IoU ortalamaları da
`0,823226/0,640525 → 0,827606/0,646860` oldu. Kaynak ve Sorghum regresyon
değerleri sırasıyla `-0,000936` ve `-0,003643` olduğundan gerileme değil küçük
iyileşme vardır; iki non-inferiority kapısı da geçti.

Bütün v2/v3 koşuları aynı source-tree SHA-256
`4d08a822084321404609c3c43b5d32283249be7d93c1e3358ac02b449ac2e8f5`,
aynı model, epoch, örnekleme bütçesi ve seed'lerle üretildi. Sorghum
`external_test` görüntüleri seçimde değerlendirilmedi ve yeniden kullanılamaz.

## 8. Sınırlar ve doğru sonraki adım

- Referans weed'ler yüksek kaliteli authored assetlerdir, fakat olgun kaynak
  morfolojileri erken tarla boyutuna ölçeklenmiştir; gerçek erken-evre scan
  değildir.
- Crop hâlâ prosedüreldir; ölçülmüş/botanik scan değildir.
- Rüzgâr, ıslak yaprak, hastalık, motion blur, lens/sensör response'u ve
  ölçülmüş kamera renk pipeline'ı bu asset-only challenger'da yoktur.
- V3 pilotunun weed oranı v2'den biraz düşüktür. Model kazancının ne kadarının
  texture/morfolojiden, ne kadarının bu dağılım farkından geldiği bu tek
  challenger ile ayrıştırılamaz.
- Development safety pass rate `0,333333`'tür; semantik gate geçmesine rağmen
  model saha/püskürtme için uygun değildir.
- Epoch-8 sonucu tarihsel epoch-15 genel checkpoint'in yerine geçmez. Bunun
  için v3 tarifiyle önceden dondurulmuş eşit-bütçeli epoch-15 confirmation ve
  ardından yeni, dokunulmamış, tercihen çok tarlalı final set gerekir.
- Büyük sentetik batch üretmek şu aşamada kanıt değeri eklemez. Öncelik gerçek
  veri coverage boşlukları; sonra ayrı ablation'larla erken-evre gerçek scan,
  wet/wind/disease, motion/camera response ve sentetik miktar etkisidir.

Pratik karar: v3 R3 asset tarifi **kabul**, v2 tarif **kontrol olarak korunur**,
kör büyük-batch üretim **ertelenir**, saha/deployment iddiası **beklemede**.

## 9. Kanonik kanıtlar ve yeniden üretim

- Gate: `configs/simulation/cropcraft_agri_asset_gate_v3.yaml`
- Pack builder: `scripts/enhance_cropcraft_assets_v3.py`
- Blender converter: `scripts/prepare_polyhaven_plant_assets_blender.py`
- Asset audit: `data/processed/audits/cropcraft_asset_quality_v3_r3.json`
- Başarısız R2 audit: `data/processed/audits/cropcraft_asset_quality_v3_r2.json`
- Başarısız R1 görsel receipt:
  `data/synthetic/cropcraft/agri_robust_smoke_v3_r1/visual_review_receipt.json`
- Kabul edilen smoke: `data/synthetic/cropcraft/agri_robust_smoke_v3_r3`
- Kabul edilen pilot: `data/synthetic/cropcraft/agri_robust_pilot_v3_r1`
- Pilot release:
  `data/synthetic/cropcraft/agri_robust_pilot_v3_r1/release_receipt.json`
- Pilot görsel review:
  `data/synthetic/cropcraft/agri_robust_pilot_v3_r1/visual_review_receipt.json`
- Manifest audit:
  `data/processed/audits/cropcraft_robust_ablation_manifest_v3.json`
- Leakage audit:
  `data/processed/audits/cropcraft_robust_combined_duplicates_v3.json`
- Domain-gap:
  `data/processed/audits/cropcraft_agri_robust_pilot_domain_gap_v3.json`
- Training matrix:
  `configs/benchmark/simulation_asset_quality_confirm_v3.yaml`
- Fixed-epoch evaluation receipt:
  `data/runs/simab_real_sorghum_cropcraft_robust10_e8_v3/development_fixed_epoch8_evaluations.json`
- Selection protocol:
  `configs/benchmark/simulation_asset_quality_selection_protocol_v3.yaml`
- Selection receipt: `data/runs/simulation_asset_quality_selection_v3.json`
- Kod testleri: `39 passed`
