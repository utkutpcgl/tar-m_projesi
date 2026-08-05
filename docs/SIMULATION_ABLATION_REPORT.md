# Gerçek + sentetik crop segmentasyon ablation raporu

## 1. Kapsam ve karar sınırı

Bu faz yalnız RGB semantik segmentasyonu kapsar:

```text
0 background / soil
1 target crop
2 other vegetation / weed
255 ignore
```

Depth, 3B konumlama, actuator kontrolü, Unreal sahnesi ve custom botanik asset
üretimi bu benchmark'a dahil edilmedi. Amaç, mevcut gerçek-veri liderine küçük
ve kontrollü bir sentetik pilot eklemenin dokunulmamış gerçek geliştirme
domain'lerinde fayda sağlayıp sağlamadığını ölçmektir.

## 2. Önceki simülasyon çalışmasından uygulanan kurallar

Bu fazda [`previous_lessons_learned.md`](../previous_lessons_learned.md)
içindeki kanıt zinciri, fail-closed üretim, küçük-pilot ve frozen-real A/B
ilkeleri tarım görevine uyarlandı:

- Ontoloji ve split rolleri generation'dan önce donduruldu.
- Generator yalnız başarılı process exit'ine değil gerçek RGB/mask
  dosyalarına, boyutlara, renklere ve sınıflara bakarak fail-closed çalıştı.
- Scene seed'leri bağımsız tutuldu; train/validation aynı scene'i paylaşmadı.
- Önce 4 kare smoke, sonra 100 kare pilot üretildi; pilot geçmeden ölçek
  büyütülmedi.
- Her sahne ve release için config, kod/revision ve çıktı hash'leri makbuza
  yazıldı.
- A/B kolları aynı model, optimizer, augmentation ve örnekleme bütçesini
  kullandı. Oran ham dosya sayısı değil sampler exposure oranıdır.
- Sentetik validation model seçiminde kullanılmadı; kabul ölçütü gerçek
  source validation, CWFID ve SorghumWeed validation'dır.
- SorghumWeed `external_test`, tarif/seed/epoch/checkpoint kilitlenene kadar
  açılmadı.

## 3. Yeni veri ve provenance

| Kaynak | Rol | Adet | Lisans / kısıt | Sabitleme |
|---|---:|---:|---|---|
| [SorghumWeed](https://data.mendeley.com/datasets/y9bmtf4xmr/1) | train / calibration / kilitli test | 202 / 25 / 25 | CC-BY-4.0; tek isimli çiftlik | Mendeley v1, arşiv SHA-256 `cfd40ddf...` |
| [CropCraft](https://github.com/Romea/cropcraft) | sentetik pilot | 80 train / 20 val | kod Apache-2.0; bundled asset lisansları upstream'de tek tek belirtilmediği için research-only | commit `7128cd2acade50cc4a5a1761210b55989ab62527` |

SorghumWeed resmi 202/25/25 image split'i korundu. Dönüştürme VIA
polygon etiketlerini kullandı: `Sorghum -> crop`, `Grass/BLweed -> weed`,
çakışma -> `ignore`. Kaynakta gözlenen 5.051 polygon ile README'deki
5.555 iddiası arasındaki 504 fark raporlandı; 4 out-of-bounds vertex clip
edildi ve 52.089 crop/weed çakışma pikseli ignore'a gitti.

Kanonik Sorghum manifest SHA-256:
`f28f5914090b8ee28cd26b9e742ec958105db61f68b743963a3729468d263540`.
252/252 mask geçerli, eksik/shape mismatch yok ve split'ler arasında
dHash-256 Hamming <= 2 eşleşmesi yoktur. Resmi split tek çiftlikten geldiği
için bu test gerçek bir unseen-field kanıtı değildir.

Kapasite kontrolünden sonra büyük dosyalar root yerine `data` symlink'inin
hedefindeki HDD'ye yazıldı. Faz sonunda raw SorghumWeed 5,7 GiB, raw CropCraft
checkout 70 MiB ve tüm CropCraft sentetik çıktıları 99 MiB kullanırken veri
diskinde yaklaşık 347 GiB boş alan kaldı.

## 4. CropCraft pilotu

CropCraft, Blender `4.5.12` ile pinli checkout'un geçici arşiv kopyasında
çalıştı. Uyumluluk patch'i iki gerçek hatayı düzeltti:

1. Blender 4.5'te kaldırılan `BLENDER_EEVEE` enum'u yerine
   `BLENDER_EEVEE_NEXT`.
2. Kayıtlı `.blend` dosyasının `//` dizinine giden relative render path yerine
   açık absolute output dizini.

Kabul edilen release:
`data/synthetic/cropcraft/pilot_v1_accepted_r2`.

- 25 bağımsız scene x 4 frame = 100 RGB/mask çifti.
- Seed aralığı 171000--171024; 100/100 beklenen çift mevcut.
- Crop-free kare 0; weed-free kare 3 (%3); bütün quality gate'ler geçti.
- Piksel sayıları: background 21.269.841, crop 3.884.795, weed 1.059.764.
- Manifest 80/20 scene-disjoint; 100/100 mask geçerli; cross-split yakın
  duplicate 0.
- Release makbuzu SHA-256:
  `5bfa68cb3006ae2ef723ad0e62306035f291a1f5d9bfc523eaa841c9fb724738`.

30 sentetik ve her gerçek dataset'ten en fazla 30 örnekle yapılan sınırlı
domain-gap kontrolünde sentetik medyan; parlaklık, kontrast, saturation,
green-dominance, basit texture gradient, crop ve weed fraction için pooled
gerçek q05--q95 aralığında kaldı. Bu yalnız gross mismatch kapısıdır;
gerçek A/B sonucunun yerine geçmez.

Pilotun bilinçli limitleri stock low-poly mısır morfolojisi, küçük weed
asset havuzu, tek soil/environment ailesi ve ayrıntılı olmayan bundled asset
lisanslarıdır.

## 5. Eğitim manifestleri ve deney kontrolü

| Manifest | Train | Gerçek val | SHA-256 |
|---|---:|---:|---|
| real + Sorghum train | 4.066 | 1.637 | `a28e67d1f7ff21f2e7674de9c13feab9dc70b11472283dc4a102aafce89b933d` |
| real + Sorghum train + CropCraft | 4.166 | 1.637 | `16d738f1b7bf2cc219bd45a03604a9239de1c870c5343d069a867d70718dc153` |
| CropCraft-only | 80 | 20 sentetik | `2a7a6eeb31e9f8d0483b737287806d640d8abbfbb35b0721367c92fc0b1d550b` |

Bütün oran taraması DINOv2-Small FPN, stage-4 fine-tuning, factorized
crop-conditioned head, conditioning dropout 0,5 ve seed 17 kullandı. Her kol
8 epoch x 3.600 = 28.800 sampled örnek gördü. Sorghum calibration/test ve eski
kilitli testler train manifestlerine girmedi.

Önceki `real_core_final`-only epoch-15 seed-17 checkpoint'i Sorghum validation'a
zero-shot uygulandığında mIoU 0,675894, crop IoU 0,701533 ve weed IoU
0,336599 verdi. Yeni A/B'nin iki kolu da 202 Sorghum train karesini kullandığı
için sentetiğin nedensel etkisi bu eski checkpoint'ten değil, aynı bütçeli
real+Sorghum kontrol ile %10/%25 kolları arasından hesaplanır.

## 6. Seed-17 oran taraması

| Kol | Source mIoU | CWFID mIoU | CWFID crop / weed IoU | Sorghum val mIoU | Sorghum crop / weed IoU |
|---|---:|---:|---:|---:|---:|
| real-only kontrol | 0,794185 | 0,496535 | 0,161744 / 0,352171 | 0,809437 | 0,817428 / 0,619222 |
| + %10 CropCraft | **0,807244** | **0,568430** | 0,213342 / **0,516988** | **0,823000** | 0,828995 / **0,648036** |
| + %25 CropCraft | 0,805455 | 0,534303 | **0,214608** / 0,411178 | 0,822384 | **0,829977** / 0,645745 |
| CropCraft-only | 0,716641 (sentetik val) | 0,536534 | 0,089851 / 0,545451 | 0,478028 | 0,327400 / 0,146834 |

Bu tablo screen `best.pt` checkpoint'lerini gösterir; kontrolün safety-first
selector'ü epoch 4'ü, %10/%25 kolları epoch 8'i seçti. Bu nedenle kesin A/B,
sabit epoch 8 `last.pt` ve seed 17/29/43 ile ayrı yürütülür.

Sentetik-only model sentetik validation'da başarılı görünüp Sorghum'da
0,478028'e düştü. Stock sentetik veri gerçek verinin yerine geçemez. %25'in
CWFID'de %10'dan daha kötü olması da sentetik exposure'ın doza duyarlı
olduğunu gösterir.

Safety-first benchmark sıralamasında dört kolun da en az bir gerçek
development kapısı kaldı. Buradaki semantic kazanım spray/field readiness
iddiası değildir.

Karar kuralları confirmation sonuçlarından önce ayrı dosyalarda donduruldu:

| Artifact | SHA-256 |
|---|---|
| seed-17 screen matrisi | `f1f9a7b957b644485927e90e04a3175fc221530ac5124d98f2d67087aaa7411a` |
| screen sonucu | `5d1b9066dfcd7d8364c837870698d0409baa888db0b61d3d3823b117126b69fa` |
| epoch-8 confirmation matrisi | `683c191584a93ffb9ab907231ca69ef62f6eadcaa745cf3119603f8488699e49` |
| oran seçim protokolü | `1b11649b527dcce02dc891399b66a1d57cd7a8925683c0c3ec9491417301bed4` |
| epoch-15 bütçe matrisi | `faef2387862e101cf62090b8122460a5a0df33714b37b1e55869f7e5f3a8b334` |
| eğitim-bütçesi seçim protokolü | `439d5bee73c59a10c1b1022c710d8571eae008e299cd8c89c7831e830d248b2e` |

Oran challenger'ının kabulü için üç seed'de ortalama robust mIoU
farkının pozitif, seed kazanımının en az 2/3 ve source ile Sorghum ortalama
mIoU gerilemesinin en fazla 0,01 olması gerekir. Robust skor her seed için
`min(source, CWFID, Sorghum mIoU)` olarak tanımlıdır.

## 7. Sabit epoch-8, üç-seed paired confirmation

| Gerçek metrik | real+Sorghum kontrol | + %10 CropCraft | Ortalama fark |
|---|---:|---:|---:|
| Source mIoU | 0,799932 +/- 0,006055 | **0,803451 +/- 0,003287** | **+0,003519** |
| CWFID mIoU / robust skor | 0,524221 +/- 0,017275 | **0,541634 +/- 0,026358** | **+0,017412** |
| CWFID crop IoU | 0,171953 +/- 0,026217 | **0,190929 +/- 0,020591** | **+0,018976** |
| CWFID weed IoU | 0,425898 +/- 0,035100 | **0,459054 +/- 0,058074** | **+0,033157** |
| Sorghum val mIoU | **0,826279 +/- 0,007588** | 0,823498 +/- 0,003431 | -0,002781 |
| Sorghum crop IoU | **0,827911 +/- 0,014315** | 0,826755 +/- 0,003053 | -0,001156 |
| Sorghum weed IoU | **0,659562 +/- 0,009605** | 0,652223 +/- 0,008756 | -0,007339 |

Birincil paired farklar seed 17/29/43 için sırasıyla +0,032276,
+0,011323 ve +0,008638'dir: %10 kol 3/3 seed kazandı. Source ortalaması
gerilemedi, +0,003519 arttı. Sorghum mIoU gerilemesi 0,002781 ile dondurulmuş
0,01 non-inferiority sınırının içinde kaldı. Dört kabul kapısı da geçti ve
%10 sentetik exposure oranı eğitim-bütçesi confirmation'ına taşındı.

Oran seçim makbuzu:
`data/runs/simulation_ablation_confirm_v1/ratio_selection.json`, SHA-256
`b2878172a608ced90c1350d3e16417f230cec2fae16968bc6426cbab1942b02e`.
Makbuz `external_test_used_for_selection=false` kaydeder. Epoch-8 için medyan
robust seed 43'tür; bu checkpoint final değil, epoch-15 karşılaştırmasının
kontrolüdür.

Kontrolün altı development seed/domain değerlendirmesinden yalnız biri,
%10 kolun ise hiçbiri tüm crop-risk aggregate+p99+ihlal kapılarını geçmedi.
Sentetik katkı semantik olarak gerçektir; mevcut threshold/safety policy ile
spray deployment uygunluğu sağlamaz.

## 8. Epoch-8 / epoch-15 eğitim-bütçesi seçimi

%10 kol, aynı seed'ler ve aynı sabit tarifle 28.800 exposure'lu epoch 8 ile
54.000 exposure'lu epoch 15 arasında karşılaştırıldı. Seçim kuralları
epoch-15 koşularından önce dondurulmuştu.

| Gerçek metrik | epoch 8 | epoch 15 | Ortalama fark |
|---|---:|---:|---:|
| Source mIoU | 0,803451 +/- 0,003287 | **0,813674 +/- 0,001235** | **+0,010223** |
| CWFID mIoU / robust skor | 0,541634 +/- 0,026358 | **0,569446 +/- 0,016727** | **+0,027812** |
| CWFID crop IoU | 0,190929 +/- 0,020591 | **0,226659 +/- 0,013785** | **+0,035730** |
| CWFID weed IoU | 0,459054 +/- 0,058074 | **0,506602 +/- 0,064453** | **+0,047548** |
| Sorghum val mIoU | 0,823498 +/- 0,003431 | **0,838798 +/- 0,005602** | **+0,015300** |
| Sorghum crop IoU | 0,826755 +/- 0,003053 | **0,842720 +/- 0,011974** | **+0,015964** |
| Sorghum weed IoU | 0,652223 +/- 0,008756 | **0,681768 +/- 0,006379** | **+0,029545** |

Seed 17/29/43 paired robust farkları sırasıyla +0,012357, +0,034500 ve
+0,036579'dur. Epoch 15 3/3 seed kazandı; source veya Sorghum gerilemesi
oluşmadı. Dört kabul kapısı da geçti. Buna karşın epoch 15'in altı
CWFID/Sorghum seed-domain safety değerlendirmesinden yalnız 2/6'sı bütün
kuyruk kapılarını geçti.

Medyan-seed kuralı seed 43'teki epoch-15 `last.pt` checkpoint'ini kilitledi:

```text
data/runs/simab_real_sorghum_cropcraft10_e15_v1/seed_43/last.pt
SHA-256 97c81bcda10f1e7d01cb03e63af411b9ad7b65d202d72880efe702ff5eca092e
```

Eğitim-bütçesi seçim makbuzu
`data/runs/simulation_winner_epoch15_confirm_v1/training_budget_selection.json`,
SHA-256
`3a68e21b80dbcee41eafb3fc2904723d71b1d83637127ca8d80c3b5b08a4f82c`'dir.
Makbuz `selection_status=locked_for_one_time_external_test` ve
`external_test_used_for_selection=false` kaydeder.
Sabit-epoch development materialization receipt SHA-256
`1979f074b2f9df759e00905ca9dd5d770db92d6ac196ae5bcace6d959e5d61c8`,
epoch-15 benchmark sonucu SHA-256
`cbd02d1e7cd6df089cb67cd8820c86661a78d596d81cc849d0f85a98a607b257`'dir.

## 9. Eski real-only modele göre model evrimi

Bu kıyas sentetiğin nedensel etkisi değildir; yeni model aynı zamanda 202
Sorghum train karesi ve farklı sampler/bütçe kullanır. Yalnız ulaşılan
modelin eski baseline'a göre nerede durduğunu gösterir.

| Üç-seed validation | Eski real-only epoch 15 | Yeni real+Sorghum+%10 sentetik epoch 15 | Fark |
|---|---:|---:|---:|
| Source mIoU | **0,816684 +/- 0,003385** | 0,813674 +/- 0,001235 | -0,003010 |
| CWFID mIoU | 0,536813 +/- 0,021890 | **0,569446 +/- 0,016727** | **+0,032632** |
| Sorghum val mIoU | 0,636873 +/- 0,033928 | **0,838798 +/- 0,005602** | **+0,201926** |

Eski Sorghum zero-shot sonuçları üç seed'in tamamı için checkpoint'in
tam kaynak snapshot'ı yeniden kurularak hesaplandı; external test
kullanılmadı. Sentetiğin izole katkısı için geçerli sonuç hâlâ Bölüm
7'deki eşit-bütçeli `+0,017412` CWFID farkıdır.

## 10. Tek-sefer Sorghum external test

Tarif, epoch, seed ve checkpoint kilitlendikten sonra resmi 25 karelik
`external_test` split'ine yalnız bir performans erişimi yapıldı. Threshold
sweep yapılmadı.

| Final test metriği | Sonuç | Kapı |
|---|---:|---:|
| mIoU | **0,834852** | semantik |
| background IoU | 0,992423 | semantik |
| crop IoU | **0,795266** | semantik |
| weed IoU | **0,716867** | semantik |
| aggregate crop-spray risk | 0,000340 | <= 0,005: geçti |
| kare-başı crop-risk p99 | 0,043382 | <= 0,005: **kaldı** |
| crop-risk ihlal oranı | 0,040000 | <= 0,01: **kaldı** |
| safe-weed recall | 0,622192 | tanısal |

Global risk düşük olsa da tek bir ağır kuyruk örneği maksimum crop-risk'i
0,055564'e çıkardı. Bu nedenle final safety sonucu `false` ve model
ilaçlama/saha kullanımına uygun değildir.

Final metrik SHA-256:
`45910ba573944e123d3ccbcdae51b30c55c2e1ab5be3e4410d0105c619fe160a`.
Tek-sefer erişim makbuzu SHA-256:
`a629f929a22170a8b3ebafb2cb9b2ec5729f8925a0f4fe9d436038114b6a07de`.
Sorghum resmi split'i tek isimli çiftlikten geldiği için bu skor
image-disjoint'tir ama unseen-field kanıtı değildir.

## 11. Export, hız ve hata galerileri

Seçilen model 23.586.818 parametreye sahiptir; eğitimde 6.855.938 parametre
trainable'dır. ONNX opset-18 export 94.661.982 byte'tır. Crop-conditioning
girdisi grafikte kaldı; iki parity vakasında argmax agreement 1,0 ve en büyük
mutlak fark `1,55e-6` oldu. Parity `pass=true`:

| Artifact | SHA-256 |
|---|---|
| `model.onnx` | `adaa654d65e8fe8eddebed5bf337c8acb452d40b1737535a823d6721aa246224` |
| `model.parity.json` | `9701b775035c150b70e9bfecd857f044cb4353fb59757360f6642ae00b1c2820` |

RTX 3090, PyTorch 2.11.0+cu128, batch 1, AMP FP16 referansı:

| Girdi | Tiling | Ortalama / p95 | Throughput | Incremental peak allocation |
|---|---:|---:|---:|---:|
| 512x512 | yok | 4,116 / 4,430 ms | 242,98 image/s | 46.850.048 byte |
| 6000x4000 Sorghum validation boyutu | 35 x 1024, overlap 128 | 779,23 / 779,88 ms | 1,283 image/s | 977.551.360 byte |

Latency JSON hash'leri sırasıyla
`b242be1b5a7499b7d271d3043a0891a63c9adc05021d14dbb8992d1cf76eac74`
ve `13f81292f2e290bcd773560a78e2fa67fe8773e047da8ef98029a2748cfe76b9`'dır.

512 testi eğitim sonrası GPU 50 C ve %4 utilization'a soğuduktan sonra
çalıştı. Her iki mikro-benchmark preprocessing ve safety policy'yi;
512 testi ayrıca tiling'i içermez. Sleeping vLLM compute kullanmazken 752 MiB
GPU belleği ayırmıştı; sonuç tam boş GPU iddiası taşımaz.

CWFID ve Sorghum `external_calibration` için ayrı 10-best/10-worst overlay
galerileri üretildi; final test galeriye sokulmadı. CWFID'in en kötü ucunda
ince yaprak/overlap crop-weed karışması ve kare bazında %65,3 crop riski;
Sorghum'un zor ucunda küçük fideler ve yoğun küçük otlar görüldü. Galeri
index hash'leri sırasıyla
`2ded4df67ec421652a53f369193c3478bda47cbf19d850d0e4b3bfed14f46abb`
ve `f6ca586365f1066ff86ca35254bfd6ef48f7119ac70819260d6d173127ed1faf`'tır.

## 12. Karar ve sonraki simülasyon yatırımı

Stock CropCraft pilotunun %10 exposure faydası üç-seed gerçek-veri
doğrulamasında teyit edildi. Sonraki simülasyon işi daha fazla aynı stock
kare üretmek değil, hedef ürünün gerçek büyüme evreleri, daha iyi
weed morfoloji aileleri, soil/lighting çeşitliliği ve camera geometry için
kontrollü custom asset A/B'sidir.

Bu önerilen A/B daha sonra tamamlandı: 15 erken-dönem sorgum modeli ve
genişletilmiş weed/soil/HDRI kapsamlı özel paket, stock `%10` kola karşı
epoch-8 robust minimum mIoU'yu ortalama `+0,020305` artırdı ve 3/3 seed
kazandı. Ayrı karar ve kanıt zinciri
[`SIMULATION_ASSET_QUALITY_REPORT.md`](SIMULATION_ASSET_QUALITY_REPORT.md)
içindedir. Bu sonuç tarihsel epoch-15 checkpoint'ini eşit-bütçeli yeni bir
confirmation olmadan otomatik değiştirmez.

Unreal bu offline segmentasyon pilotunda çalıştırılmadı. Blender/CropCraft
deterministik RGB+mask hattı ihtiyacını karşıladı; Unreal'ın ek maliyetini
haklı çıkaracak robot hareketi, fizik, büyük arazi veya real-time sensor
gereksinimi bu fazın kapsamında yoktu.

Nihai tarif, gerçekten çalıştırılan ve erişilebilen adaylar içindeki en iyi
**robust semantik araştırma modeli**dir; DINOv3 gated olduğu için global en
iyi model iddiası yoktur. Veri ve stock asset kapsamı modeli research-only
yapar. Development ve final kuyruk safety kapıları tutarlı geçmediğinden
model field/spray-ready değildir. Depth, custom simülasyon üretimi ve unseen-
field saha validasyonu bu sonuca karıştırılmadı; ayrı fazlardır.
