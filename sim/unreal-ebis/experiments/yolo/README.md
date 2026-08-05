# YOLO nano Unreal/Blender ablation workspace

Bu dizin yalnız deney sözleşmesi ve runner tutar; büyük gerçek/sentetik dataset, checkpoint ve run ağırlıkları paket dışında kalır.

Beklenen frozen data:

```text
<experiment-data>/
├── manifests/{train_real,val_real,test_real}.txt
├── labels_2class/
├── data_R.yaml
├── data_R_B1N.yaml
├── data_R_U1N.yaml
└── data_R_U2N.yaml             # yalnız U1N pozitifse
```

Her YAML aynı gerçek val/test’i kullanır; sentetik yalnız train listesine eklenir. Unreal’dan yalnız `output/<production>/partitions/standard`, Blender’dan yalnız standard kullanılır. Hard açık isimli ayrı ablation; exclude hiçbir listeye girmez.

Derived sınıf sözleşmesi:

```yaml
names:
  0: rfid_tag
  1: concrete_sample
```

Gerçek upstream `tag/concrete` ID 0/1 olarak kalır. Class 2 AprilTag ve class 3 person satırları derived label’a yazılmaz; orijinaller değişmez.

## İzole ortam

3090 varsayılan Python’unda 29 Temmuz 2026’da çalışır Ultralytics paketi yoktu; `ultralytics` yalnız version/file içermeyen namespace olarak göründü. Sistem Python’una kurmayın. Proje dışı venv/conda oluşturup Python, PyTorch, CUDA ve Ultralytics sürümünü pinleyin.

## Çalıştırma

```bash
export EBIS_YOLO_MODEL=/absolute/pinned/yolo11n.pt
export EBIS_YOLO_MODEL_SHA256="$(sha256sum "$EBIS_YOLO_MODEL" | awk '{print $1}')"
export EBIS_YOLO_IMGSZ=960
export EBIS_YOLO_EPOCHS=60
export EBIS_YOLO_BATCH=16

./run_ablation.sh R 17 /absolute/data_R.yaml /absolute/runs
./run_ablation.sh R_B1N 17 /absolute/data_R_B1N.yaml /absolute/runs
./run_ablation.sh R_U1N 17 /absolute/data_R_U1N.yaml /absolute/runs
```

Seed seti `17 29 43`. Bütün çağrılar aynı `RUNS_ROOT` kullanır. Runner checkpoint hash’i ve software environment pininden saparsa eğitime başlamaz. Test eval yapmaz; test yalnız bütün koşullar tamamlanınca ayrı final komut ve raporla açılır.

2-epoch/640 tek-seed smoke yalnız ingest doğrular; sonuç tablosuna girmez. GO/HOLD eşiği `docs/YOLO_NANO_ABLATION_2_WEEKS.md` içindedir.
