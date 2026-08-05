# CropCraft Sensor-Motion V7 — Asset ve Model Gate Raporu

Tarih: 2026-08-03

## Sonuç

V7-R1 kamera-hareketi asset paketi kalite, kapasite, görsel, manifest ve
gerçek-veri leakage kapılarının tamamını geçti. Hedef tek-tarla
DeBlurWeedSeg motion-blur gelişim görünümünde güçlü ve nedensel olarak tutarlı
bir kazanç üretti:

- kabul edilmiş kontrole göre motion-blur mIoU: `+0,064939`,
- eşit-hesap kontrole göre motion-blur mIoU: `+0,069539`,
- sharp görünüm: `+0,023246 / +0,026579`.

Buna rağmen ortak robust model gate'i geçmedi. CWFID, Rice ve WeedMap
regresyonları ile mevcut-domain macro/robust kapıları kaybedildi. Bu nedenle
V7-R1 ortak eğitim tarifine alınmadı, seed 29/43 confirmation açılmadı ve
kabul edilmiş kontrol değişmedi:

`simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8`

Bu sonuçtan önceden dondurulan V7-R2, aynı RGB/PSF byte'larında fiziksel
boundary uncertainty maskesi ve `%0,625` sampling payı kullandı. Asset kalite
kapıları yine geçti; geçerli piksellerin `%2,2551`'i yalnız sınır belirsizliği
nedeniyle `ignore=255` oldu. Buna rağmen R2:

- motion-blur mIoU'da `-0,004755`,
- CWFID'de `-0,072316`,
- existing/expanded macro'da `-0,003716 / -0,003832`

geriledi; yalnız GrowingSoy'da `+0,050333` güçlü kazanç verdi. R2 de ortak
model gate'inde reddedildi, seed 29/43 açılmadı ve kabul edilmiş kontrol aynı
kaldı. Sonuç: motion asset'leri kalite açısından optimize edilmiş ve yararlı
bir stress/specialist girdisidir; mevcut ortak sampler'a eklenmeleri robust
modeli iyileştirmemektedir. RiceSEG ve çok-tarlalı gerçek blur coverage gelmeden
başka rastgele botanik veya sensör asset iterasyonu açılmayacaktır.

## 1. Neden bu asset seçildi?

Kabul edilmiş dryland V3 ve paddy R5 botanik paketleri zaten üç-seed gerçek
domain gate'lerini geçti. Soy'da daha fazla morfoloji hedef domain'i artırdığı
halde ortak CWFID/robust kapısını bozdu. Buna karşı ölçülmüş, henüz
modellenmemiş sensör açığı açıktı:

- kabul edilmiş seed-17 kontrolünde DeBlurWeedSeg sharp mIoU `0,542997`,
- aynı çiftlerin motion-blur mIoU'su `0,365268`,
- kayıp `-0,177729`.

Mevcut train transform yalnız aralıklı izotropik Gaussian blur içeriyordu;
yönlü exposure trajectory yoktu. Bu nedenle en küçük kanıta-dayalı değişiklik
botanik geometri değil, normalize kamera-shake PSF bankasıydı.

## 2. V7-R1 asset paketi

Paket:

- 32 adet `41x41` normalize, non-negative PSF,
- 16 linear + 16 smooth-curved trajectory,
- `5–25 px` arasında 10'dan fazla uzunluk ailesi,
- en az 8 açı bin'i,
- sub-pixel bilinear splat + `sigma=0,35` PSF raster filtresi,
- RGB convolution için `reflect_101` border,
- lossless PNG çıktı,
- lisans: prosedürel `CC0-1.0`.

Boyutlar:

- kernel/preview asset pack: `436 KiB`, 66 dosya,
- 200-kare release: `42 MiB`, 200 RGB,
- HDD'de build sonrası boş alan: `322.316.890.112` bayt.

Kaynaklar değiştirilmedi:

- 100 dryland V3 RGB/mask,
- 100 paddy R5 RGB/mask,
- 100 Sorghum crop-ID 4 + 100 Rice crop-ID 12,
- botanik geometri, soil, HDRI, density ve kaynak maskelerde değişiklik yok.

## 3. Split ve veri rolü

Kaynak scene birimiyle:

- scene `0–19`: 160 train kare / 40 grup,
- scene `20–24`: 40 `external_calibration` kare / 10 grup,
- train/calibration grup kesişimi: `0`.

Calibration 40 kare yalnız asset QC için kullanıldı. Model training'e ve model
seçimine girmedi. DeBlurWeedSeg'in hiçbir gerçek RGB/mask/kernel/fit edilmiş
parametresi asset veya training'e girmedi.

## 4. Otomatik kalite sonuçları

18/18 otomatik kontrol geçti:

- beklenen sample/split/domain/kernel sayıları,
- her kernel'in kullanılması,
- linear/curved dengesi,
- kernel normalizasyonu ve non-negativity,
- maksimum centroid hatası `0,002924 px`,
- tüm 200 RGB'nin değişmesi,
- üretilen RGB'ler arasında exact duplicate `0`,
- median mutlak RGB değişimi `0,016431`,
- q05/q95 mutlak değişim `0,005365 / 0,042437`,
- median gradient oranı `0,428625`,
- q05/q95 gradient oranı `0,265059 / 0,663000`,
- p95 maksimum kanal-ortalama kayması `0,0000387`,
- maksimum kanal-ortalama kayması `0,0000733`,
- gerçek DeBlurWeedSeg pixel exposure `0`.

## 5. Manuel görsel gate

Dryland ve paddy için `5/9/13/17/21/25 px` deterministic strata contact sheet'i
ile iki adet tam-çözünürlüklü 25 px endpoint incelendi.

Geçen kontroller:

- yönlü motion görünür ve uzunlukla artıyor,
- brightness/renk korunuyor,
- black/reflect seam, alpha/magenta veya kanal bozulması yok,
- latent sahne maskesi semantik olarak doğru kaynağa bağlı,
- 25 px örnekler ağır ama tanınabilir stress endpoint'i.

Önemli sınırlama: RGB hareket boyunca smear olurken R1 maskesi latent sahnenin
sert sınırını aynen korur. Bu registration bug değildir, fakat güçlü blur
bölgelerinde label uncertainty yaratır. R2'nin temel düzeltme hedefi budur.

## 6. Manifest ve leakage

Manifest audit:

- 200/200 geçerli,
- missing file `0`, invalid mask `0`, shape mismatch `0`,
- train 160 / calibration 40.

15.857 erişilebilir gerçek referansa karşı SHA-256 + dHash-256 Hamming≤2:

- sentetik→gerçek exact/near match `0`,
- sentetik-içi match `0`,
- sentetik train↔calibration match `0`,
- en yakın gerçek dHash mesafesi min/median/max `54 / 92 / 99`.

## 7. Model screen tasarımı

Seed 17, epoch 8 ve `last.pt` sabitlendi. Mimari, optimizer, loss ve diğer
hyperparameter'lar değişmedi.

| Kol | Samples/epoch | Motion payı | Rol |
|---|---:|---:|---|
| Kabul edilmiş kontrol | 3.600 | 0 | seçim kontrolü |
| Eşit-hesap kontrol | 3.690 | 0 | nedensel kontrol, seçilemez |
| V7-R1 challenger | 3.690 | 90 draw = `%2,439` | aday |

Challenger eski reçeteden beklenen 3.600 draw'ı koruyup 90 motion draw ekledi.
Toplam sentetik sampling payı `%12,195` oldu. Aday hem kabul edilmiş kontrole
hem eşit-hesap kontrole karşı tüm kapıları geçmek zorundaydı.

## 8. Seed-17 sonuçları

| Domain | Kabul | Compute | V7-R1 | Δ kabul | Δ compute |
|---|---:|---:|---:|---:|---:|
| Source | 0,801428 | 0,804381 | 0,803871 | +0,002443 | -0,000510 |
| CWFID | 0,638260 | 0,611244 | 0,585378 | -0,052882 | -0,025866 |
| Sorghum | 0,819230 | 0,825399 | 0,810998 | -0,008232 | -0,014401 |
| CropAndWeed | 0,697676 | 0,683525 | 0,691986 | -0,005690 | +0,008461 |
| Rice | 0,384724 | 0,369654 | 0,366282 | -0,018441 | -0,003371 |
| GrowingSoy | 0,429324 | 0,449623 | 0,462554 | +0,033230 | +0,012931 |
| WeedMap | 0,349823 | 0,352902 | 0,335943 | -0,013881 | -0,016959 |
| Tobacco | 0,451498 | 0,451082 | 0,454814 | +0,003316 | +0,003732 |
| DeBlur sharp | 0,542997 | 0,539664 | 0,566242 | +0,023246 | +0,026579 |
| DeBlur motion | 0,365268 | 0,360669 | 0,430207 | +0,064939 | +0,069539 |

Aggregate:

| Aggregate | Kabul | Compute | V7-R1 | Δ kabul | Δ compute |
|---|---:|---:|---:|---:|---:|
| Existing robust | 0,349823 | 0,352902 | 0,335943 | -0,013881 | -0,016959 |
| Existing macro | 0,571495 | 0,568476 | 0,563978 | -0,007517 | -0,004498 |
| Expanded robust | 0,349823 | 0,352902 | 0,335943 | -0,013881 | -0,016959 |
| Expanded macro | 0,548581 | 0,545386 | 0,549115 | +0,000534 | +0,003728 |

Blur gap `-0,177729`dan `-0,136035`e daraldı; buna rağmen ortak robust minimum
WeedMap nedeniyle düştü.

## 9. Formal karar

Geçen hedef kontroller:

- motion-blur gain,
- matched-sharp non-inferiority,
- source, CropAndWeed, GrowingSoy ve Tobacco guard'ları,
- expanded macro.

Kalan kontroller:

- her iki kontrole karşı CWFID,
- her iki kontrole karşı WeedMap,
- kabul edilmiş kontrole karşı Rice,
- compute kontrole karşı Sorghum,
- existing macro ve robust,
- expanded robust.

Sonuç:

- `challenger_accepted=false`,
- `confirmation_required=false`,
- seçilen model kabul edilmiş R5 kontrolü,
- V7-R1 ortak training mix'e eklenmez,
- V7-R1 asset pack silinmez; bounded stress test/specialist araştırma girdisi
  olarak tutulur.

## 10. Provenance amendment

Kabul edilmiş artefaktları byte-for-byte reuse preflight'ında iki manifest
sarmalayıcı yol farkı bulundu:

- WeedMap: full manifestten seçilen 95 calibration satırı ile calibration-only
  dosyası her `SampleRecord` alanında ve sırada aynı,
- Tobacco: balanced full manifestten seçilen 240 calibration satırı ile
  balanced-calibration dosyası aynı.

İki preflight de karar receipt'i üretmeden durdu. Protokol, önceki artefaktın
gerçek provenance SHA'sını kilitleyecek biçimde idari amendment aldı. Evaluated
satır, rol, checkpoint, eşik, acceptance kuralı veya training girdisi değişmedi.

## 11. V7-R2 boundary uncertainty asset'i

R2, R1 sonucundan sonra ve model sonucuna bakılmadan önce yalnız iki değişkenle
donduruldu:

1. PSF ile convolve edilmiş orijinal-sınıf one-hot olasılığı `<0,50` olan
   pikselleri `ignore=255` yaparak hard latent-mask çelişkisini azaltmak.
2. Motion sampling'i 22,5 draw/epoch'e, yani sekiz epoch'ta yaklaşık 180 draw
   ve 160 train asset'i başına `1,125` beklenen geçişe indirmek.

`0,50–0,75` sentetik-only eşik taramasında en az tahrip edici `0,50` eşiği
model sonucu görülmeden seçildi. RGB'ler R1 ile exact byte-identical/hardlink;
geçerli hiçbir piksel başka sınıfa relabel edilmedi. Yalnız belirsiz piksel
ignore oldu.

Kalite sonucu:

- 200 kare; 160 train / 40 external calibration,
- split grup kesişimi `0`,
- yeni ignore pikseli `1.182.325 / 52.428.800 = %2,2551`,
- background/crop/weed retention `0,992630 / 0,792276 / 0,848365`,
- dryland/paddy ortalama ignore `%0,8346 / %3,6756`,
- missing, invalid mask ve shape mismatch `0`,
- otomatik, manifest ve manuel contact-sheet kapıları geçti.

## 12. V7-R2 model screen'i

R2 adayı kabul edilmiş kontrolle aynı 3.600 sample/epoch ve sekiz epoch
bütçesinde koştu. Eski veri ağırlıkları `0,99375` ile ölçeklendi ve motion
uncertainty payı `%0,625` oldu. Sentetik calibration seçimde kullanılmadı.

| Domain | Kabul | V7-R2 | Δ kabul |
|---|---:|---:|---:|
| Source | 0,801428 | 0,796992 | -0,004436 |
| CWFID | 0,638260 | 0,565943 | -0,072316 |
| Sorghum | 0,819230 | 0,823673 | +0,004443 |
| CropAndWeed | 0,697676 | 0,690315 | -0,007361 |
| Rice | 0,384724 | 0,385124 | +0,000401 |
| GrowingSoy | 0,429324 | 0,479657 | +0,050333 |
| WeedMap | 0,349823 | 0,349169 | -0,000654 |
| Tobacco | 0,451498 | 0,451361 | -0,000137 |
| DeBlur sharp | 0,542997 | 0,536100 | -0,006896 |
| DeBlur motion | 0,365268 | 0,360513 | -0,004755 |

Aggregate delta'lar:

- existing robust `-0,000654`,
- existing macro `-0,003716`,
- expanded robust `-0,000654`,
- expanded macro `-0,003832`.

## 13. V7-R2 formal kararı ve asset yorumu

Geçen tek-domain guard'lar source, Sorghum, CropAndWeed, Rice, GrowingSoy,
WeedMap, Tobacco ve matched-sharp'tır. CWFID non-inferiority, motion-blur gain
ve dört aggregate non-regression kapısı geçmedi.

Sonuç:

- `challenger_accepted=false`,
- `accepted_control_changed=false`,
- `confirmation_required=false`,
- R2 checkpoint'i ortak model olarak seçilmedi,
- R1/R2 asset'leri stress testi ve crop/domain-conditioned specialist için
  saklandı,
- global sampler için ek sensor-motion iterasyonu durduruldu.

R1'in büyük blur kazancı ile R2'nin kaybolan blur kazancı birlikte okunduğunda,
asset RGB fiziği yararlıdır fakat hard label sinyali ve dozu ortak modelde
domain trade-off yaratır. R2, sınır belirsizliğini düzeltmesine karşın bu
trade-off'u kaldırmadı. Bir sonraki kanıta-dayalı adım yeni mesh üretmek değil,
RiceSEG/gerçek çok-tarlalı coverage ve daha sonra specialist/adapter tasarımıdır.

## 14. Kanonik kanıtlar

- Asset gate config:
  `configs/simulation/cropcraft_sensor_motion_asset_gate_v7_r1.yaml`
- Asset kalite audit:
  `data/processed/audits/cropcraft_sensor_motion_asset_quality_v7_r1.json`
- Manuel review:
  `data/processed/audits/cropcraft_sensor_motion_manual_visual_review_v7_r1.json`
- Leakage audit:
  `data/processed/audits/cropcraft_sensor_motion_vs_all_real_duplicates_v7_r1.json`
- 200-kare manifest:
  `data/processed/manifests/cropcraft_sensor_motion_pilot_v7_r1.csv`
- 6.063-kare challenger manifest:
  `data/processed/manifests/real_sorghum_cropcraft_v3_05_paddy_v4_05_sensor_motion_trainval_v7_r1.csv`
- Screen matrix/protocol:
  `configs/benchmark/simulation_sensor_motion_additive_screen_v7_r1.yaml`
  ve
  `configs/benchmark/simulation_sensor_motion_additive_protocol_v7_r1.yaml`
- Benchmark:
  `data/runs/simulation_sensor_motion_additive_screen_v7_r1/benchmark_results.json`
- Formal model kararı:
  `data/processed/audits/cropcraft_sensor_motion_additive_screen_selection_v7_r1.json`
- Formal karar SHA-256:
  `8b78085b6ce6e4bc1a9bacc2d6437fc0c2ea859168421156b02e3502ab68c601`

V7-R2:

- Uncertainty gate config:
  `configs/simulation/cropcraft_sensor_motion_uncertainty_gate_v7_r2.yaml`
- Uncertainty kalite ve manuel review:
  `data/processed/audits/cropcraft_sensor_motion_uncertainty_quality_v7_r2.json`
  ve
  `data/processed/audits/cropcraft_sensor_motion_uncertainty_manual_visual_review_v7_r2.json`
- 200-kare manifest:
  `data/processed/manifests/cropcraft_sensor_motion_pilot_v7_r2.csv`
- 6.063-kare challenger manifest:
  `data/processed/manifests/real_sorghum_cropcraft_v3_05_paddy_v4_05_sensor_motion_uncertainty_trainval_v7_r2.csv`
- Screen matrix/protocol:
  `configs/benchmark/simulation_sensor_motion_uncertainty_screen_v7_r2.yaml`
  ve
  `configs/benchmark/simulation_sensor_motion_uncertainty_protocol_v7_r2.yaml`
- Benchmark ve evaluation receipt:
  `data/runs/simulation_sensor_motion_uncertainty_screen_v7_r2/benchmark_results.json`
  ve
  `data/runs/simab_sensor_motion_uncertainty_add00625_r5_e8_v7_r2/sensor_motion_development_fixed_epoch8_seeds_17.json`
- Formal model kararı:
  `data/processed/audits/cropcraft_sensor_motion_uncertainty_screen_selection_v7_r2.json`
- Formal karar SHA-256:
  `5133b07c9e08d88a8f5e0099442030076824a08454aa43e11f318b4410b018a1`

Bu screen bir dış test veya spray/deployment onayı değildir.
