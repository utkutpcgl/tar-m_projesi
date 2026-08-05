# YOLO nano ablation çalışma alanı

Bu dizin, kanonik
[`INTENSIVE_14_DAY_ENGINEERING_PLAN.md`](../../docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
G5/G6 sözleşmesinin çalıştırılabilir ince katmanıdır. Eski
`R/R+B-1N/R+B-2N`, sabit 60 epoch ve `patience=12` tasarımı
**kullanımdan kaldırılmıştır**.

## Değişmez ana matris

| Koşul | Train içeriği |
| --- | --- |
| `R_ONLY` | frozen gerçek train |
| `R_S025` | aynı gerçek train + `0.25N` standard Blender |
| `R_S050` | aynı gerçek train + `0.50N` standard Blender |
| `R_S100` | aynı gerçek train + `1.00N` standard Blender |
| `R_Sbest_HARD` | en iyi standard dozdaki sentetik sayısı sabit; bunun `%20`si QC-geçmiş hard ile değiştirilmiş |

Beş koşulun her biri seed `17`, `29`, `43` ile çalışır: toplam 15 ana
run. `exclude` hiçbir manifeste giremez. Hard görüntüler standard
görüntülere **eklenmez**; sayıyı/dozu sabit tutarak onların yerini alır.
`R_ONLY` dışındaki standard subsetler nested ve deterministic seçilir.

Val ve sealed test yalnız gerçek capture gruplarından oluşur. Aynı
capture’ın ardışık kareleri train/val/test’e rastgele dağıtılmaz.
`names` her derived YAML’da tam olarak
`{0: rfid_tag, 1: concrete_sample}` olur. Upstream class 2 `apriltag` ve
class 3 `person` satırları derived iki-sınıflı label’a yazılmaz.

## Sabit optimizer-update sözleşmesi

Dataset boyu büyüdükçe daha fazla optimizer update alma karıştırıcısını
önlemek için bütün koşullar aynı `EBIS_YOLO_TARGET_UPDATES` değerini
kullanır. Runner:

- YAML içindeki tek `train:` yolunu verilen flat manifeste bağlar;
- class map'i tam `{0: rfid_tag, 1: concrete_sample}` olarak doğrular,
  sealed `test:` alanını training YAML'ında reddeder ve aynı flat
  real-val manifestini bütün koşullarda hash-pinler;
- `image_path,source,partition` composition CSV'sini train manifest
  sırasıyla birebir eşler;
- manifestte duplicate, relative veya eksik dosyada durur;
- tek GPU ve `nbs=batch` ile gradient accumulation'ı `1`e sabitler;
- en yakın integer epoch sayısını hesaplar;
- hedef update farkı `%1`den büyükse eğitim başlamadan durur;
- `patience=0` ile early stopping'i kapatır;
- checkpoint/environment/common hyperparameter ve condition-manifest
  hash'lerini aynı `RUNS_ROOT` altında kilitler;
- ana karşılaştırma checkpoint'i olarak sabit bütçe sonundaki `last.pt`yi
  pinler.

Standard koşullarda composition audit; `R_ONLY/R_S025/R_S050/R_S100`
dozlarını, aynı real set hash'ini ve yalnız `standard` sentetik
partition'ını zorlar. Hard koşulunda ayrıca seçilmiş standard
composition istenir; real setlerin eşitliğini, toplam sentetik sayının
değişmediğini, kalan standardların Sbest altkümesi olduğunu ve tam
`%20` yeni `hard_occlusion` replacement yapıldığını fail-fast doğrular.
Exact integer dozlar için frozen gerçek `N`, `20`ye bölünebilir seçilir;
bu, kullanılabilir gerçek setten en fazla 19 görüntünün önceden
stratified biçimde ayrılması demektir. Böylece üç standard sentetik
sayısı da `5`e bölünür ve hard replacement tam `%20` olabilir.
`freeze_standard_matrix.py`, dört composition hash'ini ve
`R_S025 ⊂ R_S050 ⊂ R_S100` sentetik set ilişkisini tek immutable
matrix lock içinde kanıtlar. Runner bu lock olmadan başlamaz.

`best.pt`, koşullar farklı epoch uzunluklarında real-val'i farklı update
aralıklarında gördüğü için ana model-selection checkpoint'i değildir.
Val trendi teşhis için tutulur; sealed test bütün 15 koşul bittikten sonra
`last.pt` üzerinde tek toplu değerlendirme turunda açılır.

Day 1'de dört standard manifestin `%1` tolerans içinde ulaşabildiği
ortak bir update bütçesi seçilir. Day 13 hard manifesti de aynı bütçeyi
geçmek zorundadır. Bir manifest değişirse aynı `RUNS_ROOT` devam
ettirilmez.

## Beklenen dataset düzeni

```text
<experiment-data>/
├── manifests/
│   ├── R_ONLY_train.txt
│   ├── R_S025_train.txt
│   ├── R_S050_train.txt
│   ├── R_S100_train.txt
│   └── R_Sbest_HARD_train.txt
├── compositions/
│   ├── R_ONLY.csv
│   ├── R_S025.csv
│   ├── R_S050.csv
│   ├── R_S100.csv
│   └── R_Sbest_HARD.csv
├── labels_2class/
├── data_R_ONLY.yaml
├── data_R_S025.yaml
├── data_R_S050.yaml
├── data_R_S100.yaml
├── data_R_Sbest_HARD.yaml
├── standard_matrix_lock.json
├── standard_val_metrics.csv
└── sbest_selection.json
```

Her YAML’ın `train:` alanı ilgili absolute flat manifeste gider; `val:`
aynı frozen real-val manifestidir. Test yolu train YAML’ında kullanılmaz.
Image/label kopyaları yerine mümkünse salt-okunur derived kök ve
hash'lenmiş manifest kullanılır.

Her composition CSV satırı train manifestiyle aynı sırada olmalıdır:

```csv
image_path,source,partition
/abs/real_0001.png,real,real
/abs/sim_0001.png,synthetic,standard
```

`hard_occlusion` yalnız `R_Sbest_HARD` CSV'sinde geçebilir.

## Çalıştırma

İlk önce proje dışı izole Ultralytics ortamı oluştur. 28 Temmuz 2026
denetiminde 3090 varsayılan ortamında çalışan bir `yolo` CLI yoktu; sistem
Python’una paket kurma. Model indirildikten/kopyalandıktan sonra bir kez
hash'le:

```bash
./freeze_standard_matrix.py \
  --r-only /absolute/experiment-data/compositions/R_ONLY.csv \
  --r-s025 /absolute/experiment-data/compositions/R_S025.csv \
  --r-s050 /absolute/experiment-data/compositions/R_S050.csv \
  --r-s100 /absolute/experiment-data/compositions/R_S100.csv \
  --output /absolute/experiment-data/standard_matrix_lock.json

export EBIS_YOLO_MODEL=/absolute/pinned/yolo11n.pt
export EBIS_YOLO_MODEL_SHA256="$(sha256sum "$EBIS_YOLO_MODEL" | awk '{print $1}')"
export EBIS_YOLO_TARGET_UPDATES=12000
export EBIS_YOLO_IMGSZ=960
export EBIS_YOLO_BATCH=16
export EBIS_YOLO_DEVICE=0
export EBIS_YOLO_STANDARD_MATRIX_LOCK=/absolute/experiment-data/standard_matrix_lock.json

./run_ablation.sh \
  R_ONLY 17 \
  /absolute/experiment-data/data_R_ONLY.yaml \
  /absolute/experiment-data/manifests/R_ONLY_train.txt \
  /absolute/experiment-data/compositions/R_ONLY.csv \
  /absolute/runs/ebis_nano_g5
```

`12000` yalnız komut örneğidir; frozen standard manifestler için preflight
hesabından sonra Day 1 karar kaydına yazılan tek ortak değer
kullanılmalıdır. Aynı mutlak `RUNS_ROOT`, checkpoint, batch, image size,
optimizer, LR schedule ve environment bütün çağrılarda korunur.

Model ortamını veya output'u açmadan yalnız composition/manifest/update
hesabını denemek için aynı komuta `EBIS_YOLO_PREFLIGHT_ONLY=1` ekle.
Day 11'de yalnız dört standard koşul
(`R_ONLY/R_S025/R_S050/R_S100`) preflight/freeze edilir ve Day 12'de
çalıştırılır. Frozen real-val medianıyla `Sbest` seçildikten sonra Day
13'te hard composition oluşturulur.

Day 12 sonunda `last.pt` ile yapılan frozen real-val eval’ları şu exact
12-satırlı CSV’ye yazılır:

```csv
condition,seed,rfid_ap50_95,rfid_recall,run_contract
R_ONLY,17,0.412,0.601,/absolute/runs/ebis_nano_g5/contracts/R_ONLY_seed17.json
```

CSV; dört koşul × üç seed'in tamamını içerir. Sbest kullanıcı tarafından
elle yazılmaz; script 12 `PASS` contract/`last.pt` hash'ini doğrular ve
önceden yazılmış median AP → median recall → düşük doz tie-break kuralını
uygular:

```bash
./select_sbest.py \
  --metrics-csv /absolute/experiment-data/standard_val_metrics.csv \
  --matrix-lock /absolute/experiment-data/standard_matrix_lock.json \
  --output /absolute/experiment-data/sbest_selection.json
```

Sonra yalnız hard koşulu, seçilmiş composition ve selection ledger ile
preflight edilir ve üç seed çalıştırılır:

```bash
export EBIS_YOLO_SBEST_SELECTION=/absolute/experiment-data/sbest_selection.json
export EBIS_YOLO_SBEST_COMPOSITION=/absolute/experiment-data/compositions/R_S050.csv

EBIS_YOLO_PREFLIGHT_ONLY=1 ./run_ablation.sh \
  R_Sbest_HARD 17 \
  /absolute/experiment-data/data_R_Sbest_HARD.yaml \
  /absolute/experiment-data/manifests/R_Sbest_HARD_train.txt \
  /absolute/experiment-data/compositions/R_Sbest_HARD.csv \
  /absolute/runs/ebis_nano_g5
```

`R_S050.csv` yalnız örnektir; `sbest_selection.json` içindeki gerçek
koşulun matrix-locked composition'ı kullanılır. Runner ledger'ı yeniden
hesaplar, 12 standard run contract/checkpoint hash'ini tekrar doğrular ve
verilen composition kazanan koşula ait değilse durur. Hard composition,
en iyi doz bilinmeden hazırlanmaz.

Runner'ın yazdığı kanıt:

```text
<RUNS_ROOT>/
├── environment/
│   ├── model.sha256
│   ├── software.json
│   ├── training_contract.json
│   ├── standard_matrix_lock.sha256
│   ├── real_train_set.sha256
│   ├── real_val_manifest.sha256
│   └── condition_pins/*.sha256
├── contracts/<CONDITION>_seed<SEED>.json
├── contracts/<CONDITION>_seed<SEED>.composition.json
└── <CONDITION>_seed<SEED>/weights/last.pt
```

Smoke test (`imgsz=640`, küçük update bütçesi) ayrı `RUNS_ROOT` kullanır
ve ana kıyas sonucu değildir. Ana run'lar üzerinde `exist_ok` veya resume
ile overwrite yapılmaz.

Runner/composition fail-fast sözleşmesinin dependency-free preflight
self-test'i:

```bash
./test_contract_preflight.sh
```

## Sonuç disiplini

GO/HOLD eşikleri, slice listesi, frozen split ve iki haftalık gün gün
akış kanonik plandadır. Özetle sentetik kazanç ancak aynı real-only
sealed testte üç seed medianı, en az 2/3 pozitif seed, gerilemeyen RFID
recall, en fazla `1.0` puan concrete kaybı ve her iki kamera slice'ında
negatif sürpriz olmamasıyla raporlanır. CI sıfırı keserse sonuç
`promising/inconclusive` olur; kazanç denmez.
