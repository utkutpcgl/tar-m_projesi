# Sentetik çeşitlilik sonrası real-only recovery V1

## Hipotez

V10 sentetik çeşitlilik modeli birleşik gerçek skoru artırmış olsa da CWFID ve
mevcut gerçek çekirdekte sert regresyon yaptığı için doğrudan reddedildi.
Buradaki basit takip hipotezi şudur: sentetik pretraining'in kazandırdığı
çeşitlilik, kısa ve düşük öğrenme oranlı yalnız-gerçek recovery ile target
interference azaltıldıktan sonra korunabilir.

Bu deney V10'a daha fazla compute verip kontrolü sabit bırakmaz. İki kol da
aynı ek gerçek compute'u alır:

- kontrol başlangıcı: kabul edilmiş V3+Paddy R5 seed-17 checkpoint;
- challenger başlangıcı: V10 field-robustness seed-17 checkpoint;
- recovery: 2 epoch, epoch başına 3.600 draw, yalnız gerçek veri;
- aynı 4.066 train kaydı, dataset ağırlıkları, örnek sırası, augmentasyon RNG,
  batch/accumulation ve fresh optimizer/schedule;
- öğrenme oranı `3e-5`, backbone multiplier `0,1`;
- 1.637 görüntülük aynı real-only source validation yalnız epoch 2 sonunda;
- sentetik train satırı `0`.

Epoch draw-stream SHA-256 değerleri her iki kolda da:

1. `5fec54d58fd9bb0cad53431f4f15b135c593e5e3ab143d7ed4b9187a20de6935`
2. `5a1692896803dba4e341bf071dc95258d0c8887d1b3fd6b61ab4f6735574e25e`

Kanonik freeze makbuzu:
`data/processed/benchmark/simulation_diversity_real_recovery_v1/freeze_receipt.json`.

## Değerlendirme

Gerçek skor 12 dataset/domain oyundan oluşur. Her artifact önce field/session
macro, sonra dataset macro alınır; görüntü veya piksel sayısıyla büyük dataset
üstünlüğü yasaktır.

Hedef-base ekranı önceki strict tarife sadıktır:

- `%60` target-like domain macro;
- `%25` breadth domain macro;
- `%15` domain-balanced gerçek field lower-tail;
- hard domain ve her-field non-inferiority kapıları.

Generalist-base ekranı daha sade ve genişlik odaklıdır:

- `%80` eşit 12-real-domain macro + `%20` gerçek field lower-tail;
- minimum primary kazanç `+0,002`;
- target-like kayıp en fazla `0,010`;
- lower-tail kayıp en fazla `0,015`;
- CWFID/SugarBeets kaybı ayrı ayrı en fazla `0,030`;
- `-0,025`'ten fazla gerileyen field oranı en fazla `%20`.

V11 sentetik val/test yalnız tanısal raporlanır ve gerçek selection ağırlığı
tam `0,0`'dır. FarmBot, Naïo ve BoniRob etiketsiz galeriler de seçim skoruna
girmez.

Seed 17 yalnız ekrandır. Herhangi bir geçiş ancak seed 29/43 paired
confirmation'ı açar; tek başına target veya generalist base'i değiştirmez.

## Sonuç

İki recovery kolu da tamamlandı ve aynı 12 gerçek-domain matrisi üzerinde
değerlendirildi. Challenger geniş ortalamalarda anlamlı sinyal taşıdı:

| Ölçüm | Eş-hesap kontrol | V10 + real recovery | Fark |
|---|---:|---:|---:|
| hedef-ağırlıklı primary | 0,503471 | 0,513106 | +0,009635 |
| target-like domain macro | 0,540139 | 0,546361 | +0,006222 |
| breadth domain macro | 0,444719 | 0,460606 | +0,015887 |
| field/session lower-tail | 0,454717 | 0,467587 | +0,012870 |
| eşit real-domain macro | 0,508332 | 0,517776 | +0,009444 |
| generalist primary | 0,497609 | 0,507738 | +0,010129 |

Bu artış robust base kabulü için yeterli değildir. CWFID
`0,647254 -> 0,591257` (`-0,055998`), real-core field macro
`0,730422 -> 0,703834` (`-0,026588`) ve CropAndWeed
`0,614695 -> 0,602692` (`-0,012004`) geriledi. Buna karşılık
SugarBeets holdout `+0,018676`, Rice Seedling `+0,076904`, RiceSEG country
transfer `+0,028120`, sharp/motion blur sırasıyla `+0,036854/+0,037641`
yükseldi. Aggregate crop IoU `+0,041232` artarken weed IoU `-0,014912`
düştü; kazanımın önemli bölümü crop lehine sınıf kaymasıdır.

Pooled source-validation mIoU'nun `0,796856 -> 0,806044` yükselmesine rağmen
eşit field/session ağırlıklı real-core sonucun gerilemesi, büyük ve kolay
alanların mikro ortalamayı maskeleyebildiğini doğrudan gösterir. Toplam 111
field/session'ın 23'ü `-0,025`'ten fazla geriledi (`%20,72`; izin `%20`) ve
en kötü alan farkı `-0,312067` oldu.

Son karar:

- strict target ekranı: **ret**; paired non-inferiority geçmedi;
- generalist ekranı: **ret**; CWFID kritik-domain ve field-regression-oranı
  kapıları geçmedi;
- seed 29/43 confirmation: **açılmadı**;
- kabul edilmiş global seed-43 fallback: **değişmedi**.

Bu sonuç sentetik çeşitliliğin bazı dağılımlarda yararlı olduğunu, fakat kısa
real-only recovery'nin hedef koşullardaki girişimi yeterince temizlemediğini
gösterir. Daha karmaşık recovery taraması bu development panellerini daha çok
tüketeceği için bu fazda durduruldu.

Kanonik karar makbuzları:

- `data/processed/audits/target_weighted_real_recovery_v1.json`
- `data/processed/benchmark/simulation_diversity_real_recovery_v1/selection_seed17.json`
- kontrol checkpoint SHA-256: `2fcf9bddbc519bd7a8b57e1ee501ff3a5eaccb2d82cd7dd9f400a8c7dd523094`
- challenger checkpoint SHA-256: `d1cced6df0ba0815308d998ca5698ec68fb0635f2b5299f63894aced60841a03`

## Yeniden çalıştırma

```bash
.venv/bin/python scripts/train_real_only_recovery.py \
  --candidate recovery_control_real_e2_v1

.venv/bin/python scripts/train_real_only_recovery.py \
  --candidate recovery_v10_diversity_real_e2_v1

.venv/bin/python scripts/evaluate_real_only_recovery.py \
  --candidate recovery_control_real_e2_v1

.venv/bin/python scripts/evaluate_real_only_recovery.py \
  --candidate recovery_v10_diversity_real_e2_v1

.venv/bin/python scripts/score_target_weighted_field_benchmark.py \
  --protocol configs/benchmark/target_weighted_real_recovery_v1.yaml \
  --benchmark configs/benchmark/target_weighted_real_recovery_matrix_v1.yaml \
  --output data/processed/audits/target_weighted_real_recovery_v1.json
```
