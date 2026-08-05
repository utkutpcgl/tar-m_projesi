# CropCraft soy asset V5 ve kompozisyon V6 kalite/gate raporu

## 1. Karar

`cropcraft_soy_robust_v5_r3` asset paketi statik, lisans, render, semantic
alpha, görsel ve duplicate kapıları açısından güçlü ve kullanılabilir bir
araştırma paketidir. Yeni `cropcraft_soy_stress_pilot_v6_r5` reçetesi de
önceden dondurulan 100-kare kompozisyon gate'ini geçti.

Ancak bu iki veri reçetesinin eşit karışımı, kabul edilmiş genel modele
eklendiğinde altı-gerçek-domain model gate'ini **geçmedi**. Bu nedenle:

- soy asset/data kalitesi kabul edilir;
- soy sentetiğinin mevcut tek ortak robust modele eklenmesi reddedilir;
- seed 29/43 confirmation açılmaz;
- kabul edilmiş `%5` dryland V3 + `%5` paddy R5 kontrolü korunur;
- büyük soy sentetik batch üretimi yapılmaz.

Seed-17 sabit epoch-8 sonucu:

| Kol | Source | CWFID | Sorghum | CropAndWeed | Rice | GrowingSoy | Robust min | Macro |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Kabul edilmiş kontrol | 0,801428 | 0,638260 | 0,819230 | 0,697676 | 0,384724 | 0,429324 | 0,384724 | 0,628440 |
| 3.690 compute kontrol | 0,804381 | 0,611244 | 0,825399 | 0,683525 | 0,369654 | 0,449623 | 0,369654 | 0,623971 |
| 45 V5 + 45 stress V6 draw | 0,790930 | 0,508053 | 0,825107 | 0,706030 | 0,355325 | 0,529466 | 0,355325 | 0,619152 |

Mix adayının kabul edilmiş kontrole farkı:

| Source | CWFID | Sorghum | CropAndWeed | Rice | GrowingSoy | Robust | Macro |
|---:|---:|---:|---:|---:|---:|---:|---:|
| -0,010498 | **-0,130207** | +0,005877 | +0,008354 | -0,029398 | **+0,100142** | -0,029398 | -0,009288 |

GrowingSoy kazancı, asset morfolojisinin yararlı soy sinyali taşıdığını
gösterir. CWFID/Rice/robust kayıpları ise darboğazın salt mesh ayrıntısı
değil, tek ortak modelde ürün-domain çakışması olduğunu gösterir.

Resmî karar makbuzu:
`data/processed/audits/cropcraft_soy_mix_additive_screen_selection_v6_r5.json`.

## 2. Paket ne kadar optimize edilmişti?

Paket zayıf veya stock bir başlangıç değildi:

| Özellik | V5 R3 |
|---|---:|
| Soy crop modeli | 60 |
| Bağımsız soy geometrisi | 20 |
| Evre / geometri varyantı / fenotip | 5 / 4 / 3 |
| Crop yüz sayısı min/medyan/max | 900 / 1.668 / 4.122 |
| Amaranthus viridis modeli | 16 |
| Cynodon dactylon modeli | 37 |
| Toplam weed modeli | 53 |
| Soil PBR / HDRI | 3 / 3 |
| Debris | 16 |
| Inventory | 331 dosya / 139.399.667 byte |

Soy modelleri cotyledon/unifoliolate/trifoliolate ilerlemesi, yaprak açısı,
gövde ve dal varyasyonu ile beş evreyi yaklaşıklar. Her bağımsız geometri
`healthy_dark`, `healthy_light` ve `field_stress` fenotiplerine ayrılır;
60 modelin 60 bağımsız mesh olduğu iddia edilmez.

Paket manifest SHA-256:
`d27df4d3c6fb7f8673deb87916af224a2ef890bdb4d3e8a71c316c95a80880c5`.
Inventory SHA-256:
`6535d3f817bfa7f9c20d6a7ab6a7f4a260c81a72da13c476b00b4f3ebf2db0d8`.

Geometri prosedürel CC0-1.0, dış PBR/HDRI girdileri
[Poly Haven'ın CC0 kataloğundan](https://polyhaven.com/) gelir. Bermuda çimi
için kullanılan resmî kaynak
[Grass Bermuda 01](https://polyhaven.com/a/grass_bermuda_01)'dir. Lisans ve
kaynaklar paket manifestinde dosya bazında tutulur.

## 3. Semantic alpha düzeltmesi

R4 pilotu RGB açısından geçmesine rağmen texture-card arka planlarını weed
etiketine katıyordu. `0005-alpha-preserving-label-materials.patch` yalnız
semantic materyali alpha-aware yaptı:

- decoded RGB MAE maksimum: `0`;
- decoded RGB kanal farkı maksimum: `0`;
- görünmez card arka planından kaldırılan weed pikseli: `38.614`;
- kaldırılan crop pikseli: `0`;
- alpha altından doğru biçimde açığa çıkan piksel: `46`.

R4 bu nedenle manuel fail olarak korunur; R5'te RGB aynı kalırken maskeler
görünür yaprak/çim siluetleriyle hizalanır. Patch SHA-256:
`dec1da2c1b3a75e6084923f327eb19a399d14dfde8152b88d4d40783730ba700`.

## 4. İlk V5 pilotu ve teşhis

Kabul edilen ilk 25-scene/100-frame `soy_pilot_v5_r5` sonucu:

- ortalama crop fraction `0,160326`;
- ortalama weed fraction `0,010373`;
- crop-free `0`, weed-free `10`;
- 60/60 crop modeli, 3/3 soil ve 3/3 HDRI;
- exact RGB ve scene'ler arası exact mask duplicate `0`;
- automatic ve manuel visual/alpha gate: geçti.

Bu dağılım [GrowingSoy](https://github.com/raulsteinmetz/soy-segmentation-ds)
crop/weed oranına yakındı ve GrowingSoy transferini yükseltti. GrowingSoy
görüntü, maske, crop cutout veya texture'ları render ya da eğitim girdisi
olmadı; yalnız gerçek `external_calibration` değerlendirmesiydi.

İlk eşit-bütçeli ikame ekranlarında GrowingSoy `+0,087948` ile
`+0,107940` yükseldi. Buna karşılık CWFID `-0,108078` ile `-0,115345`, Rice
`-0,024580` ile `-0,037405` geriledi. İki aday da reddedildi.

Eski her kaynağın mutlak draw sayısını koruyup 90 V5 soy draw'ı ekleyen takip
de aynı örüntüyü verdi:

| Fark, kabul edilmiş kontrole | Source | CWFID | Sorghum | CropAndWeed | Rice | GrowingSoy | Robust | Macro |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| V5 add-90 | -0,009292 | -0,137710 | +0,005086 | +0,002818 | -0,039399 | +0,095432 | -0,039399 | -0,013844 |

Bu takip, kaybın yalnız paddy/dryland replay'inin yer değiştirmesi olmadığını
kanıtladı. Sonraki değişken mesh değil, sahne kompozisyonu olarak donduruldu.

## 5. V6 stress kompozisyon iterasyonları

Gate 100 kare için şu eşikleri sonuç görülmeden önce sabitledi:

- ortalama crop `0,015–0,090`, weed `0,030–0,100`;
- en az 60 karede weed fraction `>=0,03`;
- en az 75 karede crop fraction `0,005–0,12`;
- en az 50 karede weed/crop oranı `>=0,75`;
- crop-free `0`, weed-free en fazla `5`;
- exact duplicate `0`, exact palette ve manuel full-resolution review.

İterasyonlar fail-closed tutuldu:

| Sürüm | Sonuç | Crop band | Weed >=0,03 | Weed/crop >=0,75 | Crop-free |
|---|---|---:|---:|---:|---:|
| R1 | Asset-height uyumsuzluğu; 1 scene sonra durdu | — | — | — | — |
| R2 | Frame dağılım gate'i fail | 61/75 | 43/60 | 52/50 | 0 |
| R3 | Generator + frame gate fail | 69/75 | 50/60 | 53/50 | 2 |
| R4 | Hard fail görülünce 68 karede durduruldu | 64/68 | 43/68 | 53/68 | 1 |
| **R5** | **Tüm data gate'leri geçti** | **98/75** | **67/60** | **69/50** | **0** |

R5, ilk V5'in tüm-evre çeşitliliğini koruyan tamamlayıcısıdır. 5 stage-2,
15 stage-3 ve 5 stage-4 sahne; R2'nin crop görünürlüğü kanıtlanmış kamera/sıra
sınırları ve R4'ün yüksek-weed reçetesiyle birleştirildi. Başarısız
release'lerin hiçbiri training manifestine girmedi.

Makine-okunur iterasyon defteri:
`data/processed/audits/cropcraft_soy_stress_iteration_ledger_v6.json`.

## 6. R5 render, görsel ve leakage kapıları

Kabul edilen stress R5 pilotu:

| Kontrol | Sonuç |
|---|---:|
| Scene / RGB-mask çifti | 25 / 100 |
| Ortalama crop / weed fraction | 0,035113 / 0,050702 |
| Crop-free / weed-free kare | 0 / 4 |
| Crop fraction q10 / medyan / q90 | 0,011664 / 0,024813 / 0,068309 |
| Weed fraction q10 / medyan / q90 | 0,002454 / 0,044651 / 0,101780 |
| Exact RGB / cross-scene mask duplicate | 0 / 0 |
| Kullanılan crop modeli / soil / HDRI | 36 / 3 / 3 |

12 RGB/mask/overlay çifti ve altı tam çözünürlüklü uç örnek manuel
incelendi. Düşük/yüksek crop, düşük/yüksek weed, weed-free negatif kare,
üç soil, üç HDRI ve train/validation scene'leri kapsandı. Alignment, alpha,
palette, eksik/magenta texture ve stage morfolojisi geçti.

Yeni 100 kare ile 12.618 gerçek referansın SHA-256 + dHash-256 Hamming<=2
denetiminde:

- gerçek referansa exact/near eşleşme: `0`;
- sentetik train/val arası exact/near eşleşme: `0`;
- aday içi exact/near eşleşme: `0`.

## 7. Dengeli 200-kare mix ve düşük-seviye domain gap

İlk V5 ve stress V6 eşit 100+100 kareyle birleştirildi. Ortak piksel oranı:

- crop `0,097720`;
- weed `0,030538`.

Gerçek eğitim alanlarından dataset başına 80 örnekle yapılan sınırlı
istatistik denetiminde mix'in brightness, crop/weed fraction, saturation,
green-dominance ve texture-gradient medyanlarının tamamı gerçek pooled
q05–q95 aralığına girdi.

GrowingSoy'a karşı crop fraction medyanı aralık içindeydi. Sentetik
brightness (`0,362524`) ve texture-gradient (`0,018363`) medyanları gerçek
GrowingSoy q05 değerlerinin (`0,425165` ve `0,056467`) altında kaldı; weed
medyanı ise stress tasarımı nedeniyle daha yüksekti (`0,018457` vs gerçek
`0`). Bu düşük-seviye istatistikler yalnız gross mismatch tanısıdır; kabul
kriteri gerçek-domain model A/B'sidir.

## 8. Dondurulmuş mix model gate'i

Kontrol, compute kontrol ve aday aynı DINOv2-Small FPN, seed 17, epoch 8,
optimizer, augmentation ve source tree kullandı. Aday:

- kabul edilmiş her kaynağın 3.600-example mutlak draw sayısını korudu;
- toplam soy bütçesini önceki takipteki gibi 90 draw tuttu;
- yalnız bunu 45 V5 + 45 stress V6 olarak böldü;
- gerçek GrowingSoy ve gerçek Rice training exposure kullanmadı;
- external test veya external threshold sweep kullanmadı.

Aday GrowingSoy'u `+0,100142`, CropAndWeed'i `+0,008354` ve Sorghum'u
`+0,005877` yükseltti. Buna karşılık source `-0,010498`, CWFID
`-0,130207`, Rice/robust `-0,029398` ve macro `-0,009288` geriledi.

Compute kontrole karşı da CWFID `-0,103191`, Rice/robust `-0,014328`,
source `-0,013451` ve macro `-0,004819` oldu. İki referansa karşı da aynı
gate'ler kaldı. Aday reddedildi; sonuç görüldükten sonra eşikler gevşetilmedi.

## 9. Neden yeni haricî mesh eklenmedi?

Bu iterasyonda yeni haricî soy mesh'i pakete alınmadı. Nedeni maliyet değil,
kanıttır:

1. Aynı V5 morfolojisi üç ayrı tarifte GrowingSoy'u yaklaşık
   `+0,088–+0,108` yükseltti.
2. Stress düzeltmesinden sonra GrowingSoy kazanımı yine `+0,100` oldu.
3. Statik geometri, texture, semantic alpha, görsel ve leakage gate'leri
   geçti.
4. Buna rağmen CWFID kaybı `-0,130` kaldı.

Dolayısıyla yalnız daha yüksek polygon sayılı veya lisansı/morfolojisi daha
belirsiz bir model eklemek, gözlenen robustluk kaybının doğrudan çözümü
değildir. Mevcut kanıtta en etkili sonraki yatırım:

- daha çok tarladan gerçek, sahne-ayrık soy verisi;
- model fazında hedef-crop koşullu uzman/adapter veya ayrı soy specialist;
- ancak bundan sonra, ölçülmüş botanik/sensör açığına bağlı yeni asset A/B'si.

Bu karar asset aramasını sonsuza kadar kapatmaz; bu gate'te gereksiz bir mesh
değişkeni eklenmesini engeller.

## 10. Sınırlar ve doğru kullanım

- Soy ve Amaranthus morfolojileri prosedürel yaklaşık modellerdir, botanik
  scan değildir.
- Stress R5 sahneleri yüksek-weed orta-evre durumlarını bilerek fazla temsil
  eder; gerçek görülme sıklığı iddiası yoktur.
- Wind, ıslak yaprak, hastalık, motion blur ve ölçülmüş kamera response'u yoktur.
- GrowingSoy tek başına final/unseen-field kanıtı değildir ve yalnız
  development rolündedir.
- Asset/data gate'inin geçmesi, model gate'inin geçtiği anlamına gelmez.
- Paket soy-specialist/conditional model araştırmasında tutulabilir; mevcut
  ortak robust eğitim tarifine eklenemez.
- Bu seçim saha veya püskürtme onayı değildir.

## 11. Kanonik kanıtlar

- Asset static audit:
  `data/processed/audits/cropcraft_soy_asset_quality_v5_r3.json`
- Asset pack: `data/raw/synthetic_assets/cropcraft_soy_robust_v5_r3`
- İlk V5 release/visual receipt:
  `data/synthetic/cropcraft/soy_pilot_v5_r5/`
- Stress gate:
  `configs/simulation/cropcraft_soy_stress_gate_v6.yaml`
- Kabul edilen stress study:
  `configs/simulation/cropcraft_soy_stress_pilot_v6_r5.yaml`
- Stress release/visual receipt:
  `data/synthetic/cropcraft/soy_stress_pilot_v6_r5/`
- Stress composition audit:
  `data/processed/audits/cropcraft_soy_stress_composition_v6_r5.json`
- Stress duplicate audit:
  `data/processed/audits/cropcraft_soy_stress_vs_all_real_duplicates_v6_r5.json`
- 200-kare mix manifest:
  `data/processed/manifests/cropcraft_soy_robust_mix_v6_r5.csv`
- 6.103-kare training manifest:
  `data/processed/manifests/real_sorghum_cropcraft_robust_v3_paddy_soy_mix_trainval_v6_r5.csv`
- Screen matrix/protocol:
  `configs/benchmark/simulation_soy_mix_additive_screen_v6_r5.yaml` ve
  `configs/benchmark/simulation_soy_mix_additive_protocol_v6_r5.yaml`
- Fixed-epoch evaluator:
  `scripts/evaluate_growingsoy_fixed_epoch_development.py`
- Mix selector:
  `scripts/select_soy_synthetic_mix_additive.py`
- Formal model decision:
  `data/processed/audits/cropcraft_soy_mix_additive_screen_selection_v6_r5.json`
- Formal decision SHA-256:
  `5ca6292a6cf2caf7b95624a3cb75f653de030105b4b5e1dff9d14e43799b2e2d`

