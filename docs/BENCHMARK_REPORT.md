# Gerçek-Veri Segmentasyon Benchmark Raporu

> Bu belge 2026-08-01'de kilitlenen real-only fazın sonuç raporudur.
> Sonraki SorghumWeed + CropCraft kontrollü ablation'ı eski final testlerini
> yeniden açmadan ayrı olarak
> [`SIMULATION_ABLATION_REPORT.md`](SIMULATION_ABLATION_REPORT.md) içinde
> raporlanır.

> Durum: **GERÇEK-VERİ SEMANTİK BENCHMARK'I TAMAMLANDI**
>
> Erişilebilir adaylar içindeki semantik checkpoint seçildi ve kilitli testler
> bir kez açıldı. Sonuç, ilaçlama/saha güvenliği onayı değildir: kaynak ve EWIS1
> worst-domain safe-weed recall değeri `0`, Carrot-Weed kuyruk güvenlik kapıları
> başarısızdır. Sentetik veri ve depth bu raporun kapsamı dışıdır.

## 1. Deney kimliği

| Alan | Değer |
|---|---|
| Rapor tarihi | 2026-08-01 |
| Kod sürümü / commit veya arşiv hash'i | git deposu yok; source-tree SHA-256 `733c4f49238d129fd3128effd09d7a50bd5d81d32e6b3978684cea087b9b42b4` |
| Benchmark matrisi ve SHA-256 | ekran `configs/benchmark/real_final_conditioning_screen.yaml`; `22fd95628045abd78216816d54db4fe316ccc24e90264806c006b26202fc51a0`; stage-4 probe `5c181a2bc90eb2102a29bf28e86bf5b60e812118118a65d1ba70ee21b6a24de2`; stage-4 tail `fed7df63f74c53266811df156dbd8e65d2c6540467101a58eab9780e7c9db214` |
| `real_core_final.csv` SHA-256 | `688bb985f5eb6950a37c078f1b20008c703d8ce60baa04d5409c8ad5adcb5987` |
| Ticari-fiziksel manifest SHA-256 | `commercial_core_we3ds.csv`; `a33a1eccba8d6bf67d0c3beb0a3855978cf929eda75f523ae4784c453e763ba0` |
| Final-test manifest SHA-256 değerleri | Carrot `5e68bfd4436ae2841259a6d24d6f77ee8a5001383efbafd351cad778d32859a2`; EWIS1 `1ba0665f9b7f6c8a1d5d17b48f053724be92dbd446305b990e99df9bcf180883` |
| Freeze makbuzu / SHA-256 | `processed/audits/real_segmentation_freeze_v1.json`; `8747f989a52da8c80ca52d53ca279ef6eec47a34808cdcedd293780f7e7604c8` |
| GPU / CUDA / PyTorch | RTX 3090 24 GB / CUDA 12.8 / PyTorch 2.11.0+cu128 |
| Model cache sürümü | DINOv2-Small revision `ed25f3a31f01632728cabb09d1542f84ab7b0056`; Transformers 4.57.6 |

Kapsam: gerçek RGB veride `background / target_crop / other_vegetation`
segmentasyonu ve güvenli yabancı ot püskürtme maskesi.

Kapsam dışı: simülasyon verisi üretimi veya eğitime etkisi, RGB-D/depth,
Jetson/robot üstü saha testi ve saha güvenlik sertifikasyonu. RTX 3090 üzerinde
kontrollü inference mikro-benchmark'ı yalnız verimlilik referansıdır.

## 2. Veri ve sızıntı kontrolü

| Manifest | Rol | Split sayıları | Eksik / bozuk / şekil hatası | Yakın-kopya sonucu | Lisans kontrolü |
|---|---|---|---|---|---|
| `phenobench.csv` | araştırma-maksimum | 1.407 / 772 | temiz | cross-split dHash≤2: 0 | CC-BY-NC-SA-4.0 |
| `acre.csv` | çekirdek | 600 / 200 / 200 | temiz | cross-split dHash≤2: 0 | CC-BY-4.0 |
| `weedsgalore.csv` | yardımcı | 104 / 26 / 26 | temiz | cross-split dHash≤2: 0 | CC-BY-4.0 |
| `we3ds.csv` | çekirdek | 1.018 / 389 / 394 | temiz | cross-split dHash≤2: 0 | CC-BY-4.0 |
| `rose.csv` | araştırma-maksimum | 735 / 250 / 250 | temiz; 15+15 resmi paket anomalisi kayıtlı | cross-split dHash≤2: 0 | kayıt CC-BY-4.0; gömülü içerik incelemesi |
| `real_core_final.csv` | araştırma benchmark | 3.864 / 1.637 / 870 | temiz | cross-split dHash≤2: 0 | NC/ODbL incelemesi içerir |
| `commercial_core_we3ds.csv` | fiziksel ticari-temiz kaynak track | 1.722 / 615 / 620 | temiz | cross-split dHash≤2: 0 | satırlar `commercial_allowed=true` |
| `cwfid.csv` | geliştirme | calibration 60 | temiz | tek split | ticari olmayan |
| `carrot_weed.csv` | kilitli final | test 39 | temiz | tek split | ticari olmayan |
| `ewis1.csv` | kilitli final | test 88 / 39 grup | temiz | dHash≤2: 0 | CC-BY-4.0 |

Zorunlu kanıtlar:

- [x] Tüm etiket değerleri yalnızca `0, 1, 2, 255`.
- [x] Görüntü-maske eşleşmesi ve boyutları temiz.
- [x] Rastgele ve katmanlı etiket contact-sheet'leri insan gözüyle incelendi.
- [x] `dataset + field + session` grubu train ile val/test arasında kesişmiyor.
- [x] 6.558 all-role örnekte dHash-256 Hamming≤2 eşleşmesi 0; bunun sekans bağımsızlığını
      kanıtlamadığı not edildi.
- [x] Birincil track'in araştırma-only olduğu ve fiziksel ticari-temiz
      manifestin ayrı tutulduğu işaretlendi.

## 3. Ön-kontrol

### 20-crop ezberleme testi

| Alan | Değer |
|---|---|
| Run dizini | `data/runs/overfit20_real_final_stratified_v3/seed_17` |
| Checkpoint SHA-256 | `a0cea4f5e07e40a5d7057453b91c894a318cbc4c2330d951ce24b98bb925917f` |
| Son train loss | 0,0230861 |
| Crop IoU | 0,986437 |
| Weed IoU | 0,978239 |
| mIoU / worst-domain weed IoU | 0,984304 / 0,954325 |
| En düşük domain crop IoU | 0,957023 |
| Görsel kontrol | nicel geçiş sağlandı; galeri final modelde üretilecek |
| Karar | **geçti** |

Bu test genelleme sonucu değildir. Başarısızsa tam benchmark sonucu
yorumlanmadan veri, maske, dönüşüm, loss ve gradient akışı incelenmelidir.

## 4. Adaylar ve lisans kovaları

| Aday | Head / eğitim | Lisans kovası | Seed durumu |
|---|---|---|---|
| `rf2_convnext_stage4_mean1_drop05` | factorized / stage4 / dropout 0,5 / safety mean | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_stage4_nosafety_drop05` | factorized / stage4 / dropout 0,5 / no-safety | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_stage4_mean1_drop08` | factorized / stage4 / dropout 0,8 / safety mean | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_stage4_nosafety_drop08` | factorized / stage4 / dropout 0,8 / no-safety | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_frozen_mean1_drop05` | factorized / frozen / dropout 0,5 | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_flat_stage4_mean1` | flat / stage4 | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_convnext_flat_frozen_mean1` | flat / frozen | research data; ImageNet-weight terms review | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_dinov2_small_frozen_mean1_drop05` | factorized / frozen / dropout 0,5 | research data; model card Apache-2.0 | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf2_segformer_b2_mean1` | flat / all | research data; NVIDIA non-commercial weight license | seed 17 tamamlandı; source gate geçti, CWFID source-frozen geçmedi |
| `rf4_dinov2_small_stage4_mean1_drop05_probe` | factorized / stage4 / dropout 0,5 | research data; model card Apache-2.0 | sabit epoch 15, seed 17/29/43 tamamlandı; semantik seçim adayı |
| DINOv3 ConvNeXt-Tiny FPN | flat/factorized varyantlar | özel lisans + gated | ERİŞİM BEKLİYOR |

Kova adları hukuki onay değildir. Kullanılan veri, kod ve ağırlık lisansları
dağıtımdan önce birlikte incelenmelidir.

## 5. Kilitli seçim kuralı

Bilinen crop-ID operating point'leri kaynak doğrulamada seçilir:

1. Her kaynak domain'inde aggregate `crop_spray_risk <= 0,005`.
2. Kare-başı crop-risk `p99 <= 0,005`.
3. Aggregate sınırı aşan kare oranı `<= 0,01`.
4. Uygun eşikler arasında en yüksek worst-capture-group `safe_weed_recall`;
   sonra domain-makro recall ve daha düşük kuyruk riski.

Bilinmeyen crop-ID eşiği için kaynak unknown eğrisi ile ilan edilmiş CWFID
development eğrisi ayrı ayrı taranır; iki seçimin maksimum eşiği dondurulur.
Bu ortak eşik kaynakta ve CWFID'de yukarıdaki üç kapıyı birlikte geçmelidir.
Kalibrasyon checkpoint'i ve receipt'i kaynak `best.pt`, CWFID manifest/mask,
script ve çıktı hash'lerini saklar.

Mimari sıralaması kaynak doğrulama ve önceden ilan edilen CWFID geliştirme
değerlendirmesinde:

1. tüm güvenlik sınırlarını sağla;
2. kümeler arasındaki minimum capture-group `safe_weed_recall` değerini
   maksimize et;
3. minimum makro recall ve worst-domain weed IoU değerlerini maksimize et.

CWFID ilan edilmiş development kalibrasyonudur; final test değildir. Carrot,
EWIS1 veya `real_core_final.test` üzerinde eşik taraması yapılmaz. Hiçbir aday
tüm kapıları geçmezse selector `selected_checkpoint=null` üretir; tanısal
temsilci field-safe veya deployment-ready sayılmaz.

## 6. Tarama sonuçları

Kaynak artifact:
`data/runs/real_final_conditioning_screen_v2_tail/benchmark_results.json`
(SHA-256 `2bbf6f03801517bf7a5f60ed34d72abea6bceadb4216d6e12f604541ed325890`).

Kalibrasyon sonrası seçim makbuzu:
`data/runs/real_final_conditioning_screen_v2_tail/screen_selection.json`
(SHA-256 `45966021c386f7db9b054805b26fe8738bdcc4ce4d64d388a713362bca2f30a3`).

| Sıra | Aday | Seed | Tüm sınırlar sağlandı mı? | Robust safe-weed recall | Robust worst-domain weed IoU | Run dizini |
|---:|---|---:|---|---:|---:|---|
| 1 | `rf2_convnext_flat_frozen_mean1` | 17 | evet | 0,000000 | 0,000000 | `data/runs/rf2_convnext_flat_frozen_mean1/seed_17` |
| 2 | `rf2_convnext_stage4_nosafety_drop08` | 17 | evet | 0,000000 | 0,000000 | `data/runs/rf2_convnext_stage4_nosafety_drop08/seed_17` |
| 3 | `rf2_convnext_stage4_nosafety_drop05` | 17 | evet | 0,000000 | 0,000000 | `data/runs/rf2_convnext_stage4_nosafety_drop05/seed_17` |
| 4 | `rf2_convnext_flat_stage4_mean1` | 17 | evet | 0,000000 | 0,000000 | `data/runs/rf2_convnext_flat_stage4_mean1/seed_17` |
| 5 | `rf2_dinov2_small_frozen_mean1_drop05` | 17 | evet | 0,000000 | 0,000000 | `data/runs/rf2_dinov2_small_frozen_mean1_drop05/seed_17` |
| 6 | `rf2_convnext_stage4_mean1_drop08` | 17 | hayır | 0,000000 | 0,000000 | `data/runs/rf2_convnext_stage4_mean1_drop08/seed_17` |
| 7 | `rf2_convnext_stage4_mean1_drop05` | 17 | hayır | 0,000000 | 0,000000 | `data/runs/rf2_convnext_stage4_mean1_drop05/seed_17` |
| 8 | `rf2_convnext_frozen_mean1_drop05` | 17 | hayır | 0,000000 | 0,000000 | `data/runs/rf2_convnext_frozen_mean1_drop05/seed_17` |
| 9 | `rf2_segformer_b2_mean1` | 17 | hayır | 0,000000 | 0,000000 | `data/runs/rf2_segformer_b2_mean1/seed_17` |

Her aday için ayrıca doldur:

| Aday | Kaynak crop spray risk | Kaynak safe-weed recall | CWFID crop spray risk | CWFID safe-weed recall | Weed IoU | Crop IoU | Unknown rate |
|---|---:|---:|---:|---:|---:|---:|---:|
| `rf2_convnext_stage4_mean1_drop05` | 0,004063 | 0,000000 | 0,001476 | 0,003229 | 0,345928 | 0,113033 | 0,021125 |
| `rf2_convnext_stage4_nosafety_drop05` | 0,004651 | 0,003182 | 0,000000 | 0,000000 | 0,418934 | 0,081754 | 0,017313 |
| `rf2_convnext_stage4_mean1_drop08` | 0,004577 | 0,000208 | 0,001149 | 0,002239 | 0,352942 | 0,119651 | 0,020794 |
| `rf2_convnext_stage4_nosafety_drop08` | 0,004903 | 0,003395 | 0,000000 | 0,000006 | 0,418631 | 0,079272 | 0,017414 |
| `rf2_convnext_frozen_mean1_drop05` | 0,003913 | 0,005683 | 0,003078 | 0,003901 | 0,253930 | 0,130237 | 0,019175 |
| `rf2_convnext_flat_stage4_mean1` | 0,002605 | 0,010697 | 0,000000 | 0,000000 | 0,358675 | 0,096667 | 0,017629 |
| `rf2_convnext_flat_frozen_mean1` | 0,004921 | 0,008359 | 0,000000 | 0,001995 | 0,233736 | 0,137571 | 0,018413 |
| `rf2_dinov2_small_frozen_mean1_drop05` | 0,000949 | 0,000000 | 0,000000 | 0,000000 | 0,379109 | 0,127258 | 0,016782 |
| `rf2_segformer_b2_mean1` | 0,003561 | 0,000000 | 0,005771 | 0,001531 | 0,253028 | 0,160744 | 0,018909 |

Beş aday üç risk kapısını teknik olarak geçti; buna karşın tüm
adaylarda robust minimum recall ve robust worst-domain weed IoU sıfırdır.
Selector'ün teknik seçimi `rf2_convnext_stage4_nosafety_drop05` olup
birincil metrikler eşitlendikten sonra kuyruk-risk tie-break'iyle belirlenmiştir.
Bu checkpoint pratikte abstain ettiğinden saha-başarılı veya final model diye
yorumlanamaz. Kaynak segmentasyon kalite lideri DINOv2'dir: mIoU 0,804672,
weed IoU 0,617419, crop IoU 0,815945.

Diskalifiye/başarısız run'lar silinmemeli; hata nedeni, tamamlanan epoch ve
artifact konumu burada belirtilmelidir.

## 7. Çok-seed doğrulaması ve semantik seçim

İlk tanısal devam koşusu iki tarifi seed 17/29/43 üzerinde eksiksiz çalıştırdı.
Artifact `benchmark_results.json` SHA-256 değeri
`60723c8e4068281d03a068e3f2d55ecd7a6ed7768518ee401c4f159ac9eed9c9`,
seçim makbuzu SHA-256 değeri
`c7d218b1a7055c085e98a303c6424550a50b2ead9068f48c931aea080def9590`'dır.

| Aday | Güvenlik geçişi | Kaynak mIoU ort. ± ss | Crop IoU ort. ± ss | Weed IoU ort. ± ss | Worst-domain safe recall / weed IoU |
|---|---:|---:|---:|---:|---:|
| DINOv2-Small frozen | 2/3 | 0,800695 ± 0,009359 | 0,813248 ± 0,009942 | 0,608598 ± 0,017611 | 0 / 0 |
| ConvNeXt-Tiny flat/frozen | 1/3 | 0,727139 ± 0,009096 | 0,749133 ± 0,009165 | 0,450918 ± 0,017792 | 0 / 0 |

Hiçbir aday tüm seed'lerde ilan edilmiş aggregate ve kuyruk risk kapılarını
geçmedi. Makbuz bu nedenle `selected_checkpoint=null` üretti; DINOv2 seed 29
yalnız tanısal temsilciydi. Özellikle `worst-domain=0`, metrik yazılım hatası
değildir: weed içeren bazı WE3DS oturumlarında model hiç güvenli weed pikseli
üretmemiştir.

Semantik kalite lideri üzerinde yalnız DINOv2-Small'ın son bloğunu açan stage-4
iyileştirmesi yapıldı. Seed 17 probe'da epoch 15 kaynak semantik sonuçlarına
bakılarak sabitlendi; seed 29/43 başlamadan önce checkpoint kuralı donduruldu.
Kilitli test bu kararda okunmadı.

| Sabit epoch-15 stage-4 sonuçları | Seed 17/29/43 ort. ± ss |
|---|---:|
| Kaynak mIoU | 0,816684 ± 0,003385 |
| Kaynak crop IoU | 0,823733 ± 0,005698 |
| Kaynak weed IoU | 0,645519 ± 0,004155 |
| Kaynak worst-domain weed IoU | 0,022090 ± 0,038260; minimum 0 |
| CWFID mIoU | 0,536813 ± 0,021890 |
| CWFID crop IoU | 0,210221 ± 0,017006 |
| CWFID weed IoU | 0,423303 ± 0,051728 |
| CWFID safe-weed recall | 0,003098 ± 0,002628 |
| Teknik risk kapısı geçişi | 3/3 |
| Kaynak worst-domain safe-weed recall | 0/3 seed'de sıfırdan büyük |

Stage-4, frozen DINOv2 ortalamasına göre kaynak mIoU'yu `+0,015989`, crop
IoU'yu `+0,010485`, weed IoU'yu `+0,036920`; CWFID mIoU'yu `+0,023942`, CWFID
crop IoU'yu `+0,057793` ve CWFID weed IoU'yu `+0,007929` artırdı.

Semantik seçim makbuzu
`data/runs/real_final_dinov2_stage4_multiseed_tail_v1/semantic_selection.json`
(SHA-256 `ac270d344399b8b0e07a6aa87addd0edb55f55e4d2f76b480ec632fc86e87c05`)
tüm seed risk makbuzlarını ve sabit epoch'u doğrular. `min(kaynak mIoU, CWFID
mIoU)` değerinin medyan seed'i olan seed 17 seçildi:

```text
data/runs/rf4_dinov2_small_stage4_mean1_drop05_probe/seed_17/
  last.semantic.devcal.pt
SHA-256: 4a3fcdb7e1d77992d134feaa6f1b397b6429bfea7969b2d3acc048c8a7ea04ca
```

Bu bir **semantik segmentasyon checkpoint seçimi**dir. Makbuzdaki ilaçlama
durumu açıkça
`not_operationally_eligible_zero_source_worst_domain_safe_weed_recall`'dır.

## 8. Kilitli final test

Mimari, epoch, seed, checkpoint ve eşikler kilitlendikten sonra üç final split
bir kez açıldı. Üç çıktıda da
`calibration_source.external_threshold_sweep_performed=false`; final sonuçtan
sonra threshold veya model tuning'i yapılmadı.

| Test | Global crop risk | Safe recall | Safe precision | mIoU | Weed IoU | Crop IoU | Unknown | Üç risk kapısı |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| `real_core_final.test` (870) | 0,000057 | 0,051657 | 0,974684 | 0,720475 | 0,367341 | 0,817669 | 0,005191 | geçti |
| Carrot-Weed (39) | 0,002426 | 0,001274 | 0,056264 | 0,290652 | 0,074148 | 0,020181 | 0,011962 | **kuyrukta kaldı** |
| EWIS1 (88) | 0,000022 | 0,057618 | 0,986957 | 0,719594 | 0,451618 | 0,719825 | 0,003513 | geçti |

| Test | Worst-domain crop risk | Kare-başı risk p95 / p99 / max | İhlal oranı | Worst-domain safe recall / weed IoU |
|---|---:|---:|---:|---:|
| `real_core_final.test` | 0,000129 | 0 / 0,000353 / 0,016277 | 0,001153 | 0 / 0 |
| Carrot-Weed | 0,002426 | 0,012440 / 0,020463 / 0,023117 | 0,230769 | 0,001274 / 0,074148 |
| EWIS1 | 0,000393 | 0,000279 / 0,000758 / 0,000839 | 0 | 0 / 0 |

Carrot-Weed aggregate risk sınırın altında görünse de p99 ve ihlal oranı hard
gate'lerini açık biçimde bozdu. Crop IoU `0,020181` ve safe-weed precision
`0,056264` olduğundan bu yeni domain'de ağır başarısızlıktır; 39 karelik tek
sekans oluşu sonucu iyileştirmez, yalnız genelleme kapsamını daraltır.

0/5/10/20 px crop-guard global `(risk, recall)` hassasiyeti şöyledir:

| Test | 0 px | 5 px (dondurulmuş) | 10 px | 20 px |
|---|---|---|---|---|
| Kaynak final | (0,000057; 0,051657) | (0,000057; 0,051657) | (0,000057; 0,051615) | (0,000053; 0,048947) |
| Carrot-Weed | (0,002426; 0,001274) | (0,002426; 0,001274) | (0,002426; 0,001274) | (0,002415; 0,001273) |
| EWIS1 | (0,000022; 0,057618) | (0,000022; 0,057618) | (0,000021; 0,057580) | (0,000020; 0,056969) |

GSD verilmediği için bu piksel yarıçapları fiziksel güvenlik mesafesi değildir.
Seçili güvenli maskede küçük/orta/büyük weed component'lerinin en az %50'sini
yakalama oranları sırasıyla kaynakta `0 / 0,000109 / 0,008045`, Carrot'ta
`0,000620 / 0 / 0`, EWIS1'de `0,000626 / 0,035345 / 0,018868`'dir. Bu değerler
ilaçlama faydasının hâlâ çok düşük olduğunu gösterir.

Final artifact SHA-256 değerleri:

- `real_core_final_test.json`:
  `3cf2bea71536b2bce90efa66c8d2a668f9f98afa4b059108ecb9f48f932fa4d4`
- `carrot_weed.json`:
  `0659557ba7f19a5b6287ba0d100d7e1161cfbff94ccac7e44d242ba3a6e973de`
- `ewis1.json`:
  `7d7bfc7f4cf9e08d6f54ffeeac08c52ec08f6e426d49fec858c89d347e7039c6`

## 9. Nitel hata analizi

| Artifact | Sonuç |
|---|---|
| Carrot-Weed en iyi/en kötü 10 | 20 görsel tamam; `index.json` SHA-256 `6f1d9e8c30a0b282e7e4c47b048c8c769aced8d235ec7be48bc38ef8dcd4a569` |
| EWIS1 en iyi/en kötü 10 | 20 görsel tamam; `index.json` SHA-256 `409ea08df4e61f0a321ba780cc0cba27b5e7741f5279713e595fbc9ecd1a3f7f` |
| Provenance | iki index de seçili checkpoint SHA'sını, doğru manifest SHA'sını, epoch 15'i, source-tree eşleşmesini ve `external_threshold_sweep_performed=false` alanını doğruluyor |

Galeriler `data/runs/final/carrot_weed_gallery` ve
`data/runs/final/ewis1_gallery` altındadır. Carrot galerisi yeni ürün/kamera
domain'inde crop/weed ayrımının çöktüğünü; EWIS galerisi yüksek semantik ortalama
yanında küçük bileşenlerin ve bazı çekim gruplarının kaçırıldığını görünür kılar.

## 10. Verimlilik ve dışa aktarma

| Alan | Değer |
|---|---|
| Toplam / eğitilebilir parametre | 23.586.818 / 6.855.938 |
| 512×512 PyTorch, batch 1 | RTX 3090, AMP FP16, 30 warm-up + 100 tekrar: ort. 4,0968 ms; p50 3,9700; p95 4,4340; 244,09 görüntü/sn |
| Native/tiled PyTorch | EWIS referans şekli 5464×3640, 1024 tile, 128 overlap, 24 tile, 3 warm-up + 10 tekrar: ort. 535,394 ms; p50 535,120; p95 537,085; 1,868 görüntü/sn |
| CUDA allocation | 512'de incremental peak 46.850.048 B (44,68 MiB); native/tiled'da 814.000.128 B (776,29 MiB), toplam peak allocated 1.156.992.512 B |
| ONNX | opset 18; 94.661.982 B (90,28 MiB); SHA-256 `fce56b9d90576881744b7bd9bc8f6c2003673443dc3e13bf0d3a7f73ce811a0b` |
| Kare batch-1 parity | max hata `7,15e-7`; mean `1,94e-8`; argmax 1,0 |
| Dikdörtgen batch-2 parity | bilinen + bilinmeyen crop-ID; max hata `1,073e-6`; mean `2,03e-8`; argmax 1,0 |
| `.parity.json` | `pass=true`; SHA-256 `434c365e5589fc90998acbc2a5e63b11ca7ec8bb48ac911212100f9793491776` |

512 latency makbuzu SHA-256
`ca34417ff5a007c00cf791e27103085e805230b2d29a78bcf53b50b4c9213310`,
native/tiled makbuzu SHA-256
`4e0c0c8497a3c07b134051a1dd7e18064b08fcfa2b65b26541e22eb71164df8c`'dır.
Ölçümler preprocessing ve safety policy içermez; native ölçüm seeded tensor ile
referans görüntü boyutunu kullanır. GPU hesap yükü ölçüm öncesi yaklaşık %3'tü,
ancak sleeping vLLM süreci 752 MiB ayırdığı için cihaz tam anlamıyla boş değildi.
Bu caveat karşılaştırmada korunmalıdır. ONNX grafiği tiling veya safety policy
içermez; bunlar uygulama katmanında ayrıca uygulanır.

## 11. Model kartı

### Seçilen semantik model

- Mimari: DINOv2-Small FPN, factorized crop-conditioned head, backbone stage 4
  açık, conditioning dropout 0,5.
- Checkpoint: epoch 15 / seed 17
  `last.semantic.devcal.pt`; SHA-256
  `4a3fcdb7e1d77992d134feaa6f1b397b6429bfea7969b2d3acc048c8a7ea04ca`.
- Seçim kapsamı: erişilebilir dokuz adayın taraması ve DINOv2 stage-4
  iyileştirmesi; kaynak validation + ilan edilmiş CWFID development; final test
  seçimde kullanılmadı.
- Eğitim verileri: PhenoBench, ACRE, WeedsGalore, WE3DS ve ROSE içeren
  `real_core_final.train`; CWFID yalnız threshold development. Bu checkpoint
  PhenoBench NC ve CWFID non-commercial kapsamı nedeniyle research-only'dir.
- Bilinen crop-ID'leri: `0, 2, 3, 5, 6, 7, 8, 9`. Diğer ID'ler unknown crop
  yolunu ve dondurulmuş `0,999` weed threshold'unu kullanır; bu doğrulanmış OOD
  tespiti değildir.
- Girdi: RGB `[0,1]`, ImageNet mean `(0,485, 0,456, 0,406)` ve std
  `(0,229, 0,224, 0,225)` ile normalize; eğitimde 512×512 crop. 4 milyon
  pikselden büyük değerlendirmede 1024 tile / 128 overlap.
- Çıktı: background, target crop ve other vegetation olasılıkları. Dondurulmuş
  abstention/crop-guard/safe-weed policy model grafiğinin dışındadır.

### Amaçlanan kullanım

Gerçek RGB tarla görüntülerinde araştırma benchmark'ı, insan denetimli anotasyon
yardımı ve yeni, dokunulmamış bir doğrulama setiyle yürütülecek sonraki
adaptasyon deneyleri. Kamera, irtifa, ürün ve gelişim evresi eşleşmeden sonuç
başka sahaya taşınmamalıdır.

### Amaçlanmayan kullanım

- İnsan denetimi ve fail-safe olmadan doğrudan kimyasal püskürtme kararı.
- Test edilmemiş ürün, kamera, spektrum, sezon veya coğrafyada güvenlik iddiası.
- `unknown` maskesini doğrulanmış OOD detektörü olarak kullanmak.
- Üç sınıflı maskeyi bitki türü teşhisi olarak yorumlamak.

### Bilinen sınırlamalar ve riskler

- Carrot-Weed'de crop IoU `0,020181`; p99 crop risk `0,020463` ve kare ihlal
  oranı `0,230769` olduğundan açık domain-shift başarısızlığı vardır.
- Kaynak ve EWIS1 worst-domain safe-weed recall ile worst-domain weed IoU
  sıfırdır. Yüksek mIoU, püskürtme faydası veya her domain'de robustness değildir.
- WE3DS split'i tarih/oturum ayrıdır; parsel ayrıklığı kanıtlanmış değildir.
- ROSE 2019 train/val robotları ayrı olsa da Montoldre sahasını paylaşır.
- Contact-sheet ve programatik audit etiket tamlığını matematiksel olarak
  kanıtlamaz; dHash denetimi de sekans/parsel bağımsızlığı kanıtı değildir.
- CWFID 60 karelik development, Carrot-Weed 39 karelik tek sekans ve EWIS1 88
  kare/39 gruptur; geniş tarla popülasyonu için güven aralığı sağlamaz.
- Küçük ot, crop/weed teması, yoğun örtüşme, sert gölge/parlama ve yeni
  kamera/toprak/ürün koşulları temel hata riskleridir.
- DINOv3 gated olduğu için çalıştırılmamıştır; sonuç yalnız erişilebilir/test
  edilen adaylar arasındadır.
- Simülasyon/sentetik veri ve depth bu benchmark'ta kullanılmamıştır.

## 12. Son karar

| Soru | Yanıt |
|---|---|
| Erişilebilir/test edilen adaylar arasındaki semantik kazanan | **DINOv2-Small FPN stage-4, factorized, epoch 15, seed 17** |
| DINOv3 dahil karşılaştırma tamamlandı mı? | Hayır — gated erişim/koşul kabulü yok |
| Geliştirme risk kapıları seçilen tarifte çok-seed sağlandı mı? | Evet, teknik olarak 3/3; fakat safe-weed recall çok düşük ve kaynak worst-domain 0 |
| Semantik çok-seed sonuç tutarlı mı? | Evet; kaynak mIoU ss 0,003385. İlaçlama robustness'ı tutarlı biçimde yetersiz |
| Kilitli final test yalnız seçimden sonra ve sweep olmadan değerlendirildi mi? | Evet; üç artifact'te `external_threshold_sweep_performed=false` |
| Tüm final domain'leri güvenlik kapılarını geçti mi? | Hayır; Carrot-Weed p99 ve ihlal oranında kaldı |
| ONNX parity geçti mi? | Evet; kare ve dikdörtgen/batch-2 bilinen-bilinmeyen ID vakaları geçti |
| Saha pilotuna hazır mı? | **Hayır** — doğrudan ilaçlama veya field-safe etiketi verilemez |

> DINOv2-Small FPN stage-4, erişilebilir/test edilen adaylar arasında,
> dondurulmuş `real_core_final`/CWFID sürümleri ve seed 17/29/43 için en iyi
> semantik kaliteyi verdi. Buna karşın worst-domain recall/IoU sıfırları ve
> Carrot-Weed kuyruk-güvenlik başarısızlığı nedeniyle robust crop segmentasyonu
> hedefi henüz tüm görülmemiş domain'lerde karşılanmış değildir; model saha
> güvenliği veya genelleme garantisi taşımaz.
