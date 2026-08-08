# Gerçek EBIS veri pointer'ı

36 GB açılmış RGB/YOLO veri ve 31 GB arşiv bu teslim klasörüne kopyalanmadı. Aynı verinin iki kopyasını taşımak yerine path environment variable kullanılır.

Local:

```bash
export EBIS_REAL_DATA_ROOT=/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli
```

3090 üzerinde doğrulanmış detection kopyası:

```bash
export EBIS_REAL_DATA_ROOT="/home/ankaref/Documents/Projects/EBİS/ultralytics_classification/datasets/260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli"
```

Her iki doğrulanmış kökte beklenen içerik 2.960 adet 1920×1080 PNG ve aynı sayıda YOLO label’dır. Sınıflar gerçek sette `tag`, `concrete`, `apriltag`, `person`; sentetik paket yalnız ilk ikisini üretir.

Mevcut upstream train/val capture-safe değildir: yedi task/camera/batch grubu iki split’te de görünür. Ablation öncesi türetilmiş manifest ve iki-sınıflı label kopyaları ayrı bir çalışma dizininde oluşturulmalı; orijinal veri değiştirilmemelidir.

Audit:

```bash
python3 ../../scripts/analyze_detection_domain.py \
  --real-root "$EBIS_REAL_DATA_ROOT" \
  --json ../../reports/qc/real_led_detection_audit.json \
  --markdown ../../reports/qc/real_led_detection_audit.md
```
