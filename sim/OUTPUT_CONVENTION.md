# EBIS çıktı convention’ı

İnsan review’unda sabit giriş noktaları:

- Blender: [`ebis-blender/output/current_samples/contact_sheet.png`](ebis-blender/output/current_samples/contact_sheet.png)
- Unreal: [`unreal-ebis/output/current_samples/contact_sheet.png`](unreal-ebis/output/current_samples/contact_sheet.png)

Her klasörde cam-10/cam-11 × cube/cylinder olmak üzere dört RGB, YOLO label,
metadata ve görünür instance maskeleri vardır. `CURRENT.json`; immutable kaynak
run’ı, seçilen stem/partition’ı, validation SHA-256’sını ve kopyalanan dosya
hash’lerini pinler. `engine_root` yalnız taşınabilir engine kimliğidir
(`ebis-blender` veya `unreal-ebis`); makineye özgü absolute path manifesti
kirletmez.

30 Temmuz 2026 Pass-1 pinleri:

- Blender source: `realism_v8_cast_pores_release_60100`;
- Unreal source: `realism_r59_neutral_cast_brdf_release_60160`;
- yerel ve 3090 `current_samples` ağaçları sırasıyla 30 ve 51 dosyada
  byte-for-byte SHA eşidir.

## Yeni run yayınlama

Önce yeni adlı run üretilir ve kendi validator’ı temiz `PASS` vermelidir.
Ardından repository kökünde:

```bash
python3 scripts/promote_ebis_current_samples.py \
  --engine-root ebis-blender \
  --source-run ebis-blender/output/RUN_ADI

python3 scripts/promote_ebis_current_samples.py \
  --engine-root unreal-ebis \
  --source-run unreal-ebis/output/RUN_ADI
```

Promotion dört hücreyi `standard > hard_occlusion > exclude`, sonra lexical
stem sırasıyla seçer ve `current_samples` klasörünü atomik değiştirir. 3090
mirror önce `.current_samples.next` altında bütün `files_sha256` girdilerini
doğrular, sonra tek `mv` ile yayınlanır; aynı contact sheet yerelden
kopyalandığı için Pillow/font farkı hash'i değiştirmez. Bu klasör elle
düzenlenmez. Kaynak run yalnız provenance ve yeniden audit için tutulur.

## Saklama ve temizlik

Normal durumda her engine için yalnız:

1. `output/current_samples/`;
2. onun işaret ettiği son immutable release;
3. gerçekten gerekli küçük, ayrı `reports/qc/asset_ab/` kanıtları;
4. yalnız güncel MCP round-trip/render kanıtı

tutulur. Eski calibration/pilot/hero render’ları source değildir. Temizlik
önce dry-run, sonra geri alınabilir desktop trash ile yapılır:

```bash
python3 scripts/cleanup_ebis_obsolete.py \
  --keep-blender BLENDER_RELEASE \
  --keep-unreal UNREAL_RELEASE

python3 scripts/cleanup_ebis_obsolete.py \
  --keep-blender BLENDER_RELEASE \
  --keep-unreal UNREAL_RELEASE \
  --apply
```

Gerçek dataset, config, generator, PBR kaynakları, docs, validation ve nested
reference-forensics klasörleri bu scriptin hedef alanında değildir. Script
yalnız immediate output run/log, root generated QC PNG ve güncel allowlist
dışındaki image-bearing MCP evidence klasörlerini hedefler.
