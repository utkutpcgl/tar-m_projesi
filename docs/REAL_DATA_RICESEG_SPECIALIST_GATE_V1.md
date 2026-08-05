# RiceSEG crop-routed specialist model kapısı — v1

## Sonuç

RiceSEG'i ortak global parametrelere karıştıran üç tarif reddedildikten sonra
parametre izolasyonlu en küçük sistem denendi. Sonuç başarılıdır:

- kabul edilmiş global fallback checkpoint'i byte düzeyinde değişmedi;
- dışarıdan kesin olarak `target_crop_id=12` ve `Oryza sativa` bildirilen
  girdiler ayrı RiceSEG specialist checkpoint'ine gider;
- diğer veya bilinmeyen tüm crop girdileri global fallback'e gider;
- specialist, paired seed `17/29/43`'te rice-target robust mIoU'yu 3/3 artırdı
  ve dondurulmuş beş acceptance kapısının tamamını geçti.

Kabul edilen araştırma sistemi:

```text
known rice route:
  realab_riceseg_add025_compute3780_r5_e8_v2
  representative seed: 29
  checkpoint: data/runs/realab_riceseg_add025_compute3780_r5_e8_v2/seed_29/last.pt
  SHA-256: ad42ac49d34a723e69f74b6b4f2b59241eb0d21c12b58540e0ae7ab340b671c7

unknown/non-rice route:
  simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8
  representative seed: 43
  checkpoint: data/runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_43/last.pt
  SHA-256: b97618224621950e46bd47136bad43f51e417c11121674bc1849a9f7322b3d9f
```

Bu, tek bir yeni universal checkpoint değil; metadata-routed iki-checkpoint
araştırma sistemidir. Otomatik görsel crop classifier denenmedi ve pikselden
route tahmini yasaktır. Yanlış `crop_id` verilirse non-inferiority garantisi
yoktur.

## Neden specialist

Gerçek RiceSEG'in `%4,7619`, `%2,38095` ve exact-index `%2,5` global
ekranları hedefi yaklaşık `+0,32 / +0,37` iyileştirdi, fakat source,
Sorghum, CWFID ve/veya CropAndWeed kapılarında kaldı. Veri kalitesinden çok
ortak parametre girişimine işaret eden bu sonuçtan sonra oran eşiği
gevşetilmedi. Bunun yerine rice girdisinin ayrı checkpoint'e yönlendirilmesi
global forgetting'i yapısal olarak izole etti.

Specialist'in training tabanı, kabul edilmiş `%5 dryland V3 + %5 paddy R5`
sentetik karışımı ve kalite-kapılı gerçek çekirdektir. RiceSEG 2.473 train
satırı dataset/session-balanced sampler'da `%2,38095` exposure alır. Reddedilen
sentetik reproductive R3, early-rice calibration, 604 RiceSEG calibration veya
external/final test eğitime girmedi.

## Seed-17 doz ekranı

Specialist rolü global non-inferiority'den ayrıldıktan sonra toplam
`3.780 draw/epoch × 8 epoch = 30.240` sabit bütçede `%2,38 / %10 / %25 /
%50` RiceSEG exposure karşılaştırıldı. Yüksek dozlar eski draw'ları ikame
etti; compute eklemedi. Seçim sırası sonuçlardan önce donduruldu:

1. early/full/reproductive gerçek rice görünümlerinin minimum mIoU'su;
2. üç görünümün macro mIoU'su;
3. full RiceSEG mIoU;
4. tam eşitlikte daha düşük exposure.

| RiceSEG exposure | Early rice | RiceSEG | Reproductive | Target robust | Target macro |
|---:|---:|---:|---:|---:|---:|
| fallback `%0` | 0,384724 | 0,290154 | 0,032876 | 0,032876 | 0,235918 |
| `%2,38095` | **0,543817** | 0,622931 | **0,404623** | **0,404623** | 0,523791 |
| `%10` | 0,536200 | 0,643577 | 0,402313 | 0,402313 | **0,527363** |
| `%25` | 0,513266 | 0,639593 | 0,375667 | 0,375667 | 0,509509 |
| `%50` | 0,525555 | **0,648486** | 0,392631 | 0,392631 | 0,522224 |

Daha fazla target exposure full RiceSEG'i en fazla `+0,025555` daha
yükseltti, fakat en zor reproductive görünümü iyileştirmedi. Robust selector
bu nedenle en düşük dozu seçti. `%10/%25/%50` modelleri kalite hatası
nedeniyle reddedilmedi; dondurulmuş robust hedefi kazanamadıkları için
confirmation'a açılmadı.

Screen kararı:

```text
data/processed/audits/riceseg_specialist_dose_screen_selection_v1.json
SHA-256 a802d6f16b1c9bdd1744963d884f75b46e552db28928f9358f61c0b8fe63c8df
```

## Üç-seed confirmation

Seed 29/43, seed 17 ile aynı mimari, optimizer, augmentasyon, train manifest,
30.240 draw ve `%2,38095` RiceSEG exposure ile eğitildi. Source validation
specialist selector olmadığından yeni seed'lerde 64 deterministik lifecycle
smoke satırıyla sınırlandı. Bu limit son optimizer adımından sonra okunur;
model ağırlıklarını etkilemez. Seçim her seed'de tam frozen rice
manifestleriyle yapıldı.

| Seed | Fallback robust | Specialist early | Specialist full | Specialist reproductive/robust | Robust Δ |
|---:|---:|---:|---:|---:|---:|
| 17 | 0,032876 | 0,543817 | 0,622931 | 0,404623 | +0,371747 |
| 29 | 0,018524 | 0,515254 | 0,615530 | 0,418043 | +0,399519 |
| 43 | 0,042360 | 0,509348 | 0,613750 | 0,418645 | +0,376285 |

Üç-seed ortalama ± population SD:

```text
specialist early rice:       0,522806 ± 0,015051
specialist full RiceSEG:     0,617404 ± 0,003976
specialist reproductive:     0,413770 ± 0,006473
specialist target robust:    0,413770 ± 0,006473

paired mean delta, early:          +0,156047
paired mean delta, full:           +0,328889
paired mean delta, reproductive:   +0,382517
paired mean delta, target robust:  +0,382517
target robust wins:                 3 / 3
```

Beş confirmation kapısının tamamı geçti. Median target-robust kuralı
seed 29'u temsilci specialist olarak seçti.

Kanonik confirmation kararı:

```text
data/processed/audits/riceseg_specialist_confirmation_selection_v1.json
SHA-256 1bd5ec6143eb3bc73501bdff2a41c1c3139e8cf5500a03de54f4b65725b0b27d
```

## İddia sınırı

- Non-rice model skorları yeniden eğitilmiş bir modelden gelmez; aynı hash'li
  fallback çalıştığı için yapısal olarak aynıdır.
- Rice sonuçları development/calibration'dır. RiceSEG external/final test
  tanımlanmadı ve yeni saha sonucu yoktur.
- Early Rice kısmi ontolojili bir development tanısıdır; full RiceSEG ile
  aynı kanıt gücünde raporlanmaz.
- Otomatik route classifier, yanlış metadata dayanıklılığı, latency/VRAM,
  ONNX/TensorRT ve saha/spray safety bu kapıda test edilmedi.
- Sonuç `field-ready` veya `spray-ready` değildir.

## Dondurulmuş provenance

- Screen matrix: `configs/benchmark/riceseg_specialist_dose_screen_v1.yaml`,
  SHA-256 `b072290f46198331c63e25580cdcf35f82f61b94baf7b6ac27be0c84d4b0d93e`
- Screen protocol: `configs/benchmark/riceseg_specialist_dose_selection_protocol_v1.yaml`,
  SHA-256 `8e57d39750922eed954b208b1164b284e312eb2fcc075194363b2502f42da0c9`
- Confirmation matrix: `configs/benchmark/riceseg_specialist_confirmation_v1.yaml`,
  SHA-256 `9763f3faa7a2caba3315d9e970e5b6a9ecb9feff93609fca59abb5f37307f324`
- Confirmation protocol:
  `configs/benchmark/riceseg_specialist_confirmation_protocol_v1.yaml`,
  SHA-256 `9e8fefb55959309626c52f61bb928eac2c1e354b9589592b05feede783f266ba`
- Target evaluator: `scripts/evaluate_riceseg_specialist_targets.py`, SHA-256
  `866dbc8471cfc9d39c86d091590930fb4455a4f19dc08a392c181a75d87ce507`
- Confirmation selector: `scripts/select_riceseg_specialist_confirmation.py`,
  SHA-256 `c2cb99a7149ef18efe803d2dccbf11888445dd8bbfb185345eefdd64aa9e10ec`
- Source tree SHA-256:
  `fda1a1c4b715601b6d66bfdaa28637db43154ccf2f01cc2f63669119dc3142eb`
