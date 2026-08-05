# Gerçek veri coverage matrisi — v2

Tarih: 2026-08-04

V1'in SHA-kilitli 18 dataset / 20.765 kayıt envanterine, kalite kapılarını
geçen `sugarbeets2016_multiclass_holdout_v1` eklendi. Güncel doğrulanmış
envanter:

```text
real records:                        21.048
datasets:                                19
capture groups:                         576
dataset-qualified fields:                58
common-semantic-compatible records:  18.993
partial-training-locked records:       2.055
external-calibration rows:             3.972
commercial-allowed records:            9.355
research-only records:                11.693
```

Yeni 283 kare, ardışık tek BoniRob oturumudur. Coverage sayacına 283 kayıt
ama yalnız bir capture group, bir field/session ve model skoruna bir dataset
oyu ekler. Eğitim kullanımı kapalıdır.

Kanonik makbuz:

```text
data/processed/audits/real_data_coverage_matrix_v2.json
SHA-256 c353d39c960242e3b9ad0e44115b2bf75590738c4b4b8b704932e9e903bbec2a
```

Bu artış auditi V1 makbuzunu değiştirmez; onun SHA-256'sını, yeni manifesti
ve holdout release receipt'ini doğrular. Piksel, external-test veya model
çıktısı okumaz.
