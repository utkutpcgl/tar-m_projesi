# CropCraft paddy asset v4 R5 kalite ve gerçek-domain gate raporu

## 1. Karar

`cropcraft_paddy_robust_v4_r5` paketi ve `%5` kabul edilmiş v3 + `%5` paddy
sentetik karışımı, önceden dondurulan beş-gerçek-domain gate'ini
**geçti**. Kontrol ve challenger'lar aynı DINOv2-Small FPN, hiperparametre,
epoch-8, `3.600` örnek/epoch, toplam `28.800` örnek ve `%10` sentetik
exposure kullandı. Gerçek Rice verisi hiçbir kola eğitim girdisi olmadı.

Seed `17/29/43` paired confirmation sonucu:

| Metrik, üç-seed ortalama | v3 kontrol | v3 `%5` + paddy `%5` | Fark |
|---|---:|---:|---:|
| Kaynak validation mIoU | 0,798458 | 0,801014 | +0,002556 |
| CWFID mIoU | 0,578953 | 0,619474 | **+0,040521** |
| Sorghum mIoU | 0,821966 | 0,820903 | -0,001063 |
| CropAndWeed mIoU | 0,700818 | 0,698608 | -0,002210 |
| Rice mIoU | 0,317954 | 0,366759 | **+0,048805** |
| Beş-domain macro mIoU | 0,643630 | 0,661352 | **+0,017722** |
| Beş-domain robust minimum | 0,317954 | 0,366759 | **+0,048805** |

Robust minimum üç seed'in üçünde de yükseldi. Rice ortalama kazanımı
`0,01` eşiğinin çok üstündedir; mevcut dört alanın ortalama
regresyonlarının tamamı `0,01` sınırı içindedir. Resmî confirmation
makbuzu
`data/processed/audits/cropcraft_paddy_asset_confirmation_selection_v4_r5.json`
dosyasındadır.

Medyan-seed kuralıyla seçilen araştırma checkpoint'i seed 43 epoch-8
`last.pt`'dir. SHA-256:
`b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f`.

Bu sonuç paddy R5 asset tarifini ve `%5 v3 + %5 paddy` karışımını
gelecek kontrollü sentetik deneyler için kabul eder. Tarihsel epoch-15 genel
modeli otomatik değiştirmez; final-test veya saha/püskürtme onayı değildir.

## 2. Önceki paket ne kadar optimizeydi, hangi boşluk kaldı?

V3 kuru-tarla paketi zaten zayıf bir baseline değildi:

- 15 bağımsız erken-sorgum geometrisi, 5 evre ve 3 albedo fenotipiyle 45
  crop modeli;
- 4 yabani ot ailesinde toplam 51 model; bunların 27'si dört resmî Poly
  Haven CC0 model kaynağından texture-backed;
- 16 residue, 3 soil PBR ve 3 HDRI;
- fail-closed statik, smoke, görsel, maske, duplicate ve gerçek-domain A/B
  kapıları;
- v2'ye karşı 3/3 seed ve ortalama `+0,017015` robust mIoU.

Eksik olan kısım paddy fiziği ve morfolojisiydi: Oryza seedling/tiller,
Sagittaria ve sucul geniş-yapraklı yabani ot, ıslak PBR zemin, sığ su ve
suya uygun HDRI yoktu. Unexposed v3 kontrolün gerçek Rice mIoU'su
`0,311910` bu boşluğu sayısal olarak doğruladı.

## 3. R5 asset paketi

Kabul edilen paket:

| Özellik | R5 |
|---|---:|
| Rice crop modeli | 60 |
| Bağımsız rice geometrisi | 20 |
| Büyüme evresi / albedo fenotipi | 5 / 3 |
| Crop yüz sayısı min/medyan/max | 1.996 / 3.082 / 5.782 |
| Weed tipi / toplam model | 3 / 36 |
| Sagittaria / paddy-grass / aquatic-broadleaf | 12 / 12 / 12 |
| Islak zemin PBR / paddy HDRI | 3 / 3 |
| Debris | 16 |
| Inventory | 298 dosya / 207.665.332 byte |

Rice geometrileri 2–5 tiller, 11–32 blade, distichous/clumped yerleşim ve
dar yaprak oranlarıyla erken-dönem siluetini hedefler. Her crop geometrisi
`healthy_dark`, `healthy_light` ve `field_stress` fenotiplerine ayrılır;
60 modelin 60 bağımsız geometri olduğu iddia edilmez.

Islak zeminler Poly Haven CC0 `aerial_mud_1`, `brown_mud_03` ve
`muddy_tracks`; ortamlar `pond`, `mud_road_puresky` ve
`cloudy_vondelpark`'tır. `shallow_paddy_v4` profili `2–8 mm` su derinliği,
`0,45–0,95` su kapsamı ve `0,16–0,38` roughness aralığı kullanır.
Su semantic olarak background kalır.

Paket manifest SHA-256:
`95f4bdb04fcebab3ac3aed2b7db957ca3e91d4e2e5d6347bed84d7ee50368712`.
Inventory SHA-256:
`cdfc76d9cca4070954cc00d7ed1cb9a70dbd55864f683d075310264e3612467b`.

## 4. Haricî yüksek kaliteli asset taraması

Mevcut resmî CC0 PBR/HDRI kaynakları korundu. Poly Haven kataloğunda
uygun erken Oryza/Sagittaria modeli bulunmadı. İncelenen Sketchfab adayları
da ya olgun panicle morfolojisi, ya CC-BY-NC lisansı, ya da tek filizlenmiş
tane olduğu için hedef kamera/evre ve lisans gate'ini geçmedi.

Bu nedenle yalnız "daha detaylı" göründüğü için yanlış evre veya
uygunsuz lisanslı model eklenmedi. Paddy bitkileri domain'e uygun prosedürel
geometri ve 1024×1024 albedo/normal haritalarıyla üretildi; provenance ve
lisans paket içinde kaydedildi. Bunlar botanik scan değildir.

## 5. Başarısız iterasyonlar ve lessons learned

- R1 fazla karanlı/ayna benzeri su ve seyrek crop nedeniyle reddedildi;
  ortalama crop fraction `0,03284` idi.
- R2 crop fraction'ı `0,288`'e çıkarıp aşırı yoğun, radyal/palm benzeri
  morfoloji üretti; weed-free oranı da `%8,3` oldu.
- R3 sayısal dağılımı iyileştirdi (`crop 0,1481`, `weed 0,0634`) fakat
  radyal morfoloji kaldı.
- R4 distichous ve clumped morfolojiyi iyileştirdi; crop fraction
  `0,0211` ile alt gate'in altına düştü.
- R5 morfoloji ve kapsamı birlikte dengeledi.

Su dokusunu artırmak için ayrı multiscale-ripple A/B'si yapıldı. Aynı
12/12 maskede texture-gradient medyanı `0,013254412 → 0,013252905`
değişti; ölçülebilir kazanç olmadığı için patch reddedildi. RNG akışını
değiştiren ilk confounded koşu karar dışı bırakıldı. Korunan sahne
patch'i `0003-paddy-water-profile-r2.patch`'tir.

## 6. Static, smoke, pilot, görsel ve leakage kapıları

Statik audit'teki 25 kontrolün tamamı geçti. Kabul edilen 25-scene/100-frame
pilot sonucu:

| Kontrol | Sonuç |
|---|---:|
| Crop / weed ortalama fraction | 0,082018 / 0,061364 |
| Crop-free / weed-free kare | 0 / 2 |
| Exact RGB duplicate | 0 |
| Scene'ler arası exact mask duplicate | 0 |
| Kullanılan crop modeli | 60/60 |
| Kullanılan ıslak zemin / HDRI | 3/3 / 3/3 |

Beş büyüme evresi, üç zemin, üç HDRI, düşük/yüksek crop ve su
kapsamından 12 RGB/mask çifti manuel incelendi. RGB/mask alignment,
materyal çözümleme, tiller morfolojisi, su yansıması/turbidity ve semantic
palette kontrollerinin tamamı geçti.

V3+paddy 200 sentetik train karesi ile izin verilen 6.929 gerçek geliştirme
karesi arasındaki 7.129 örnekli dHash-256 Hamming≤2 denetiminde eşleşme
`0`'dır. Kilitli test split'leri bu denetime veya seçime alınmadı.

## 7. Domain-gap sonucu

80 sentetik ve 224 gerçek Rice karesinde sentetik brightness, brightness
std, crop/weed fraction, saturation ve green-dominance medyanları gerçek
q05–q95 aralığındadır. Sentetik texture-gradient medyanı `0,011405`, gerçek
q05 `0,013510` değerinin altındadır. Sentetik ignore fraction `0`; gerçek
verideki ignore alanı dataset ontolojisinin sonucudur.

Bu bilinen texture açığı sonuç görüldükten sonra ayarlanmadı. Ripple
ablation'ı ölçülebilir iyileşme getirmedi; acceptance gerçek-domain model
A/B'sine bırakıldı.

## 8. Seed-17 screen

| Kol | Source | CWFID | Sorghum | CropAndWeed | Rice | Robust | Macro |
|---|---:|---:|---:|---:|---:|---:|---:|
| v3 kontrol | 0,801456 | 0,604038 | 0,816028 | 0,694439 | 0,311910 | 0,311910 | 0,645574 |
| v3 `%5` + paddy `%5` | 0,801428 | 0,638260 | 0,819230 | 0,697676 | 0,384724 | 0,384724 | 0,668264 |
| paddy `%10` | 0,805832 | 0,596248 | 0,822541 | 0,667636 | 0,416989 | 0,416989 | 0,661849 |

Paddy-only kol Rice'ta daha yüksek olsa da CropAndWeed'i `-0,026803`
düşürdü ve `-0,01` non-inferiority gate'inde kaldı. Karışık kol bütün
screen kontrollerini geçti; robustness hedefi nedeniyle screen winner oldu.

## 9. Üç-seed confirmation

| Seed | Kontrol robust | R5 karışık robust | Fark |
|---:|---:|---:|---:|
| 17 | 0,311910 | 0,384724 | +0,072814 |
| 29 | 0,307981 | 0,337951 | +0,029970 |
| 43 | 0,333973 | 0,377603 | +0,043631 |
| **Ortalama** | **0,317954** | **0,366759** | **+0,048805** |

Kabul kontrolleri:

- pozitif ortalama robust delta: geçti;
- minimum 2/3 robust galibiyet: 3/3 ile geçti;
- ortalama Rice delta en az `+0,01`: `+0,048805` ile geçti;
- source/CWFID/Sorghum/CropAndWeed ortalama regresyonu en fazla `0,01`:
  dördü de geçti;
- external test kullanımı: yok;
- Rice train exposure: yok;
- external threshold sweep: yok.

## 10. Sınırlar ve doğru kullanım

- Rice ve paddy weed geometrileri prosedüreldir; botanik scan değildir.
- Aquatic broadleaf varlıkları stilize kalır.
- Sentetik texture dağılımının düşük kuyruğu gerçekten daha düşüktür.
- Wind, ıslak-yaprak damlası, hastalık, motion blur ve ölçülmüş kamera
  response'u modellenmedi.
- Gerçek Rice seti 28 ana fotoğraf/tek oturumdan gelen 224 karodur. Model
  buna hiç eğitilmedi; yine de bu bir yeni çiftlik/final-test kanıtı değildir.
- Paddy-only tarifin Rice kazanımı daha büyüktür; ancak CropAndWeed
  gerilemesi, tek-domain optimizasyonunun robustluk hedefiyle çeliştiğini
  gösterir.
- Seçim safety/deployment metriği kullanmaz. Yeni dokunulmamış, tercihen
  çok tarlalı paddy + kuru tarla testi olmadan saha/püskürtme iddiası yoktur.
- Bu gate 100-kare pilotla asset tarifini seçti. Kör büyük sentetik batch
  üretimi ayrı miktar/etki ablation'ına ertelenir.

## 11. Kanonik kanıtlar

- Gate: `configs/simulation/cropcraft_paddy_asset_gate_v4.yaml`
- R5 builder: `scripts/refine_cropcraft_paddy_assets_v4_r5.py`
- Asset pack: `data/raw/synthetic_assets/cropcraft_paddy_robust_v4_r5`
- Static audit:
  `data/processed/audits/cropcraft_paddy_asset_quality_v4_r5.json`
- Pilot release:
  `data/synthetic/cropcraft/paddy_pilot_v4_r5/release_receipt.json`
- Visual receipt:
  `data/synthetic/cropcraft/paddy_pilot_v4_r5/visual_review_receipt.json`
- Leakage audit:
  `data/processed/audits/synthetic_v3_paddy_vs_allowed_real_duplicate_audit_v4_r5.json`
- Domain-gap:
  `data/processed/audits/cropcraft_paddy_pilot_rice_domain_gap_v4_r5.json`
- Screen matrix/protocol:
  `configs/benchmark/simulation_paddy_asset_screen_v4_r5.yaml` ve
  `configs/benchmark/simulation_paddy_asset_selection_protocol_v4_r5.yaml`
- Confirmation matrix/freeze:
  `configs/benchmark/simulation_paddy_asset_confirm_v4_r5.yaml` ve
  `configs/benchmark/simulation_paddy_asset_confirmation_freeze_v4_r5.yaml`
- Fixed-epoch evaluator: `scripts/evaluate_paddy_fixed_epoch_development.py`
- Selector: `scripts/select_paddy_asset.py`
- Screen receipt:
  `data/processed/audits/cropcraft_paddy_asset_screen_selection_v4_r5.json`
- Confirmation receipt:
  `data/processed/audits/cropcraft_paddy_asset_confirmation_selection_v4_r5.json`
- Confirmation receipt SHA-256:
  `3f4f62c79cd99afbc7bbc149f0d798cda0053c96a106f187d3a9514ce376f50b`
