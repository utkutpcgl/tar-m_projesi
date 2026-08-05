# Tobacco Aerial gerçek-veri kalite ve model gate raporu

Tarih: 2026-08-03

## Sonuç

Tobacco Aerial verisi arşiv, ontoloji, görsel hizalama, grup ayrımı ve
duplicate kapılarını geçti. Buna rağmen test edilen `%4,7619` additive tarif
global robust model kapısını geçmedi. Aday Tobacco external-calibration
mIoU'sunu kabul edilmiş kontrole göre `+0,011261`, eşit-hesap kontrolüne göre
`+0,010009` artırdı; fakat kabul edilmiş kontrole karşı CWFID `-0,045959`,
Rice `-0,027045`, CropAndWeed `-0,021172` ve mevcut-domain macro
`-0,011881` geriledi.

Bu nedenle:

- aday reddedildi;
- seed 29/43 confirmation açılmadı;
- Tobacco verisi kabul edilmiş global eğitim tarifine eklenmedi;
- `simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8` kontrolü korundu;
- sonuç yalnız araştırma robustness kararıdır, external-test veya
  spray/deployment uygunluğu değildir.

## Kaynak ve lisans

Resmî kaynak [Mendeley Data v2](https://data.mendeley.com/datasets/5dpc5gbgpz/2)
ve kalıcı kimlik [DOI 10.17632/5dpc5gbgpz.2](https://doi.org/10.17632/5dpc5gbgpz.2)'dir.
Lisans CC BY 4.0'dır. Veri Mardan, Pakistan'daki sekiz tobacco tarla/kampanya
grubunu; yaklaşık 4 m irtifada DJI Mavic Mini ile alınmış 480×352 RGB
patch'lerini ve `background/crop/weed` maskelerini içerir.

İndirme ve arşiv kimliği:

| Nesne | Bayt | SHA-256 |
|---|---:|---|
| Dış v2 ZIP | 3.194.827.845 | `1c5d5bd2baf4d1d751b738b55c741a3573169514a9dc9fb52408e889107a8176` |
| İç v1 ZIP | 1.802.602.114 | `03672fc8a31ec2786de84586b2e1aba71988c694105e1c36371ce293966e70cd` |
| İç v2 ZIP | 1.411.318.059 | `9caa75ddad073a43600614b50f270849e0b522a14d31a222bda025cb60eced8a` |

Üç arşivde tam CRC ve path-safety denetimi geçti. İç v1/v2 sürümlerindeki
7.560 yetkili patch bileşeni byte-for-byte aynıdır.

## Ontoloji ve release anomalisi

Yetkili supervision kaynağı yalnız v2 `Patch images/data` RGB ve `mask`
ağaçlarıdır. Ham sınıflar ortak ontolojiye şu şekilde çevrildi:

```text
0 -> background
1 -> target_crop
2 -> other_vegetation
```

`maskref` yalnız görselleştirme kopyasıdır ve ground truth olarak kullanılmadı.
`Detected Vegetation` görüntüleri RGB kaynağına girmedi. 2.520 maskenin
tamamı yalnız `0/1/2` içerdi; shape mismatch, eksik dosya, geçersiz sınıf ve
ignore piksel sayıları sıfırdır.

Campaign 1'in ayrı paketlenmiş 1080p görüntüleri patch ağacıyla eşleşmiyor.
Bu ağaç supervision'dan karantinaya alındı. Campaign 1 patch'leri yine de:

- iki nested release arasında byte-identical;
- ardışık 12-patch parent bloklarında mekânsal olarak tutarlı;
- seam/internal MAD oranında median `1,049850`, maksimum `1,186187`;
- diğer campaign'lerde doğrulanan 12-patch parent kontratıyla uyumlu.

Bu nedenle Campaign 1 için yalnız patch ağacı kullanıldı; 1080p eşleşme
iddiası yapılmadı.

## Dondurulmuş split ve kalite kanıtı

Alan/kampanya grupları challenger eğitiminden önce ayrıldı:

```text
train:                 campaigns 2, 3, 5, 6, 7, 8
external_calibration:  campaigns 1, 4
external_test:         yok
```

Tam veri 2.520 patch, 8 grup ve 210 tam parent bloktur. Tam roller
`1.536 train / 984 calibration`'dır. İçerikten ve modelden bağımsız dengeli
seçim her campaign'i 120 patch ile sınırlar ve tam 12-patch parent bloklarını
korur: `720 train / 240 calibration`.

Ortak piksel sayıları:

| Background | Crop | Weed | Ignore |
|---:|---:|---:|---:|
| 281.474.369 | 60.190.590 | 84.114.241 | 0 |

Duplicate denetiminde 2.520 aday, 13.337 mevcut gerçek referansa karşı
exact/dHash-256 Hamming≤2 eşleşme üretmedi. Cross-role aday-içi eşleşme de
sıfırdır. Campaign 5 parent 2 ve 5 arasında 12 adet dHash-0 fakat byte-farklı,
aynı-train-role korelasyon uyarısı vardır; split veya cross-dataset leakage
değildir. Sekiz campaign'de low/median/high weed stratified overlay görsel
incelemesi geçti.

## Model ekranı

Üç kol seed 17, sabit epoch 8 ve `last.pt` ile karşılaştırıldı:

1. Kabul edilmiş kontrol: 3.600 draw/epoch; byte-for-byte yeniden kullanıldı.
2. Eşit-hesap kontrolü: 3.780 eski-veri draw/epoch.
3. Tobacco adayı: eski ağırlıklar `20/21`, Tobacco `1/21`; beklenen 3.600
   eski + 180 Tobacco draw/epoch.

Sampler deterministik fakat olasılıksaldır. “3.600 eski draw korunur” ifadesi
beklenen exposure içindir; kabul edilmiş kolun tam örnek sırası replay edilmez.
Bu nedenle aday hem kabul edilmiş kontrole hem eşit-hesap kontrolüne karşı
geçmek zorundaydı.

### Mutlak semantic mIoU

| Tarif | Source | CWFID | Sorghum | CropAndWeed | Rice | GrowingSoy | WeedMap | Tobacco |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Kabul edilmiş | 0,801428 | 0,638260 | 0,819230 | 0,697676 | 0,384724 | 0,429324 | 0,349823 | 0,451498 |
| Eşit-hesap | 0,804251 | 0,591024 | 0,824381 | 0,693058 | 0,333592 | 0,455725 | 0,349609 | 0,452750 |
| Tobacco `%4,7619` | 0,799839 | 0,592301 | 0,838343 | 0,676504 | 0,357679 | 0,424077 | 0,348556 | 0,462759 |

### Aday farkları ve karar

| Ölçüt | Kabul edilmiş kontrole Δ | Eşit-hesap kontrolüne Δ |
|---|---:|---:|
| Tobacco | +0,011261 | +0,010009 |
| Source | -0,001589 | -0,004412 |
| CWFID | -0,045959 | +0,001277 |
| Sorghum | +0,019113 | +0,013962 |
| CropAndWeed | -0,021172 | -0,016554 |
| Rice | -0,027045 | +0,024087 |
| GrowingSoy | -0,005247 | -0,031649 |
| WeedMap | -0,001267 | -0,001052 |
| Mevcut robust | -0,001267 | +0,014964 |
| Mevcut macro | -0,011881 | -0,002049 |
| Geniş macro | -0,008988 | -0,000542 |

Tobacco gain kapısı iki karşılaştırmada da geçti. Aday, kabul edilmiş kontrole
karşı CWFID/CropAndWeed/Rice non-inferiority ile robust ve macro kapılarını;
eşit-hesap kontrolüne karşı CropAndWeed/GrowingSoy non-inferiority ile macro
kapılarını kaybetti. İki kontrolün de bütün koşullarını sağlama kuralı
nedeniyle karar nettir: red.

DeBlurWeedSeg yalnız bilgi amaçlıydı. Adayda sharp `0,547996`, motion-blur
`0,371972`, fark `-0,176024` oldu ve seçimde kullanılmadı.

## Operasyonel not

Yerel Ollama `gemma4:26b` modeli iki development denemesi sırasında GPU'ya
yeniden yüklenerek CWFID değerlendirmesini fail-closed OOM ile durdurdu.
Yalnız bu iki eksik `cwfid.json` parçası kaldırıldı; tamamlanmış domain
artefaktları korunup hash/doğrulama ile yeniden kullanıldı. Son aday geçişinde
Ollama aynı model slotunda geçici `num_gpu=0` ile CPU'da tutuldu; final dokuz
artefaktın tamamı aynı RTX 3090 evaluator yolunda üretildi. Duvar-saat süresi
seçim ölçütü değildir. Sleeping vLLM sürecine dokunulmadı.

## Reprodüksiyon ve kilitler

```bash
.venv/bin/agri-seg benchmark \
  configs/benchmark/real_data_tobacco_aerial_additive_screen_v1.yaml

.venv/bin/python scripts/select_real_data_tobacco_aerial.py \
  --protocol configs/benchmark/real_data_tobacco_aerial_additive_selection_protocol_v1.yaml \
  --benchmark data/runs/real_data_tobacco_aerial_additive_screen_v1/benchmark_results.json \
  --output data/processed/audits/real_data_tobacco_aerial_screen_selection_v1.json
```

Ana SHA-256 kilitleri:

```text
selection protocol  d401f8baffa74176d58070405016f57022696bcb962ecc77d8008fc62bf6a5d5
screen matrix       05d1f026fbd3de173e11d2e999edc4435e989cd0e9b1aa8c0d63bd34dfab93e0
benchmark receipt   a252ab50576fb2670cc918fc6858376eac874cb141f4718e28af9dbf2074aa2a
selection receipt   ab8d066e5d431556ca20170e68270266a8ecdd9f6c7a06f8e24119c4acc38224
conversion report   813322454792b9a92260a9bee091acaba6e5511bcf28e04018d9a1b1998f16f8
```

Seçim makbuzu:
`data/processed/audits/real_data_tobacco_aerial_screen_selection_v1.json`.

## Sonraki karar

Bu sonuç Tobacco verisinin kötü olduğunu göstermez; `+0,0113` in-domain
kazanım vardır. Kanıt, tek global sampler karışımında anotasyon/kamera-domain
çatışması olduğunu gösterir. Aynı oranın küçük varyasyonlarını aramak düşük
değerlidir. Daha yüksek değerli sıralama:

1. erişim tokenı geldiğinde çok-ülkeli, tam-döngü RiceSEG gerçek-veri gate'i;
2. daha sonra domain-conditioned adapter/specialist veya gerçek-domain replay
   sampler deneyi;
3. yeni gerçek coverage ile doğrulandıktan sonra sentetik asset kapsamını
   hedef-domain açıklarına göre büyütmek.

