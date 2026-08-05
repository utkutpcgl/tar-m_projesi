# RiceSEG gerçek-veri model katkı kapısı — v1

> **Takip notu (2026-08-03):** Bu rapor tek-global-checkpoint karışım
> kapısını anlatır ve ret kararı geçerlidir. Daha sonra ayrı parametreli,
> metadata-routed RiceSEG specialist seed `17/29/43`'te 3/3 robust galibiyetle
> kabul edildi; global fallback değişmedi. Güncel sistem kararı
> [`REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`](REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md)
> içindedir.

## Karar

RiceSEG **veri kalite/coverage kapısını geçti**, fakat test edilen üç global
karışım tarifinin hiçbiri mevcut tüm alanlarda non-inferiority kapısını
geçmedi. Bu nedenle kabul edilmiş paddy R5 kontrolü değiştirilmedi, seed
29/43 confirmation açılmadı ve büyük eğitim/refit yapılmadı.

Bu sonuç RiceSEG'in zayıf veri olduğunu göstermez. Tam tersine, yalnız 90–180
hedef draw/epoch ile bağımsız RiceSEG calibration mIoU'su yaklaşık
`0,290 → 0,613–0,626`, saf reproductive altküme `0,033 → 0,405–0,411`
çıktı. Red nedeni hedefi öğrenememek değil, tek global ortak-parametreli
modelde source/Sorghum/CropAndWeed gibi mevcut alanların gerilemesidir.

```text
data gate:                         PASS
global-mixture model gate:         FAIL (3/3 tarif)
RiceSEG specialist/adapter girdisi: ACCEPTED
accepted global checkpoint:        UNCHANGED
external/final test used:          NO
large refit / seed 29,43:           NOT OPENED
```

## Veri kontratı

- Release: `3.078` RGB + maske çifti, pinli commit `1a891ced...`.
- Uygun veri: `3.077`; tek çatışmalı same-train yakın kopya karantinada.
- Eğitim adayı: `2.473` kare / `16` field-session grubu.
- Development-only: `604` kare / `2` grup; eğitimde exposure `0`.
- Reproductive development görünümü: `100` kare.
- Alternatif `1.823 → 1.254` country-transfer split'i bu model kapısıyla
  birleştirilmedi.
- Veri hakkı research/fail-closed tutuldu; ticari kullanım iddiası yoktur.

## Üç dondurulmuş ekran

Tüm ekranlar seed `17`, epoch `8`, aynı DINOv2-Small FPN/head/loss ve aynı
development alanlarını kullandı. Her alan için azami mIoU gerilemesi `0,01`;
existing robust/macro gerilemesi yasaktı. DeBlur sharp/motion yalnız tanıydı,
seçici değildi.

| Ekran | Compute / RiceSEG | Akış kontratı | Ana başarısız kapılar | Karar |
|---|---|---|---|---|
| V1 | 3.780 / beklenen %4,7619 | eski draw hacmi beklenen 3.600 | CWFID, Sorghum | Red |
| V2 | 3.780 / %2,38095 | eşit-compute kontrol; eski draw 3.690 beklenen | kabul edilmiş kontrole karşı CWFID | Red |
| V3 | sabit 3.600 / tam %2,5 | 90 fixed replacement; kalan 3.510 indeks birebir | source, Sorghum, CropAndWeed, existing robust | Red |

### Kabul edilmiş kontrole karşı mIoU farkları

| Alan | V1 | V2 | V3 exact-index |
|---|---:|---:|---:|
| Source | -0,000652 | -0,003264 | **-0,012139** |
| CWFID | **-0,010639** | **-0,031108** | -0,006124 |
| Sorghum | **-0,013533** | +0,006785 | **-0,023556** |
| CropAndWeed | -0,006748 | -0,008937 | **-0,025475** |
| Early rice | +0,112756 | +0,159094 | +0,133092 |
| GrowingSoy | +0,005638 | +0,040939 | -0,002546 |
| WeedMap | +0,004492 | +0,007363 | -0,003355 |
| Tobacco | +0,002429 | +0,002589 | +0,002992 |
| RiceSEG | +0,335655 | +0,332777 | +0,323059 |
| RiceSEG reproductive | +0,374300 | +0,371747 | +0,378183 |
| Existing robust | +0,004492 | +0,007363 | **-0,003355** |
| Existing macro | +0,011718 | +0,021683 | +0,007861 |
| Expanded robust | +0,321439 | +0,324310 | +0,313592 |
| Expanded macro | +0,080370 | +0,087798 | +0,076413 |

Kalın negatifler ilgili `-0,01` per-domain sınırını veya sıfır-regresyon
aggregate sınırını kaybeder. V2, 3.780-draw matched-compute kontrole karşı
bütün kuralları geçti; ancak o compute kontrolün kendisi kabul edilmiş
3.600-draw koşuya göre CWFID'de `-0,047236` daha düşüktü. Bu nedenle V2'nin
eşit-compute kazanımı kabul edilmiş robust modeli değiştirmek için yeterli
değildi.

## Sampler denetimi ve V3 gerekçesi

Kod denetimi mevcut sampler'ın şu sırayla örneklediğini doğruladı:

```text
dataset -> field/session group (uniform) -> image
```

Dolayısıyla 600-karelik Laguna/Telangana grupları 60–100 karelik grupları
satır sayısıyla bastırmıyordu. V1'de 16 RiceSEG grubu sekiz epoch boyunca
grup başına `75–112`, V2'de `30–61` kez seçildi. Metadata-subset/cap ile
"grup dengeleme" yapmak gereksiz veri kaybı olurdu ve uygulanmadı.

Aynı audit, önceki “replay-preserving” ifadesinin yalnız **beklenen eski draw
hacmi** için doğru olduğunu gösterdi. Kabul edilmiş akışa karşı:

| Ekran | Eski draw | Aynı filtrelenmiş pozisyon | Multiset overlap |
|---|---:|---:|---:|
| V1 | 28.778 | 162 (`%0,563`) | 23.088 (`%80,167`) |
| V2 | 29.474 | 352 (`%1,222`) | 25.443 (`%88,344`) |

V3 bu belirsizliği kaldırdı: her epoch `3.600` indeksin tam `90`'ı eşit
aralıklı RiceSEG örneğiyle değiştirildi; diğer `3.510/3.510` pozisyon sekiz
epoch'un tamamında kabul edilmiş sampler akışıyla eşleşti. V3'te CWFID
gerilemesinin `-0,031108 → -0,006124` azalması, önceki büyük CWFID kaybının
önemli bölümünün sampler akış gürültüsü olduğunu doğrular. Ancak source,
Sorghum ve CropAndWeed kayıpları kaldığı için global red kararı değişmez.

## Sentetik reproductive R3 ile birlikte yorum

Late-reproductive R3 sentetik paketi asset/pilot kapılarını geçti ve hedef
RiceSEG/reproductive alanlarını `+0,141180 / +0,101863` iyileştirdi; fakat
CWFID/CropAndWeed `-0,039529 / -0,016026` geriledi. Gerçek RiceSEG, aynı
hedefi çok daha güçlü öğretiyor; buna rağmen global ortak head'de benzer
domain girişimi görülüyor. Dolayısıyla global gate kararı açısından:

- yeni benzer rice mesh/texture eklemek gerekçeli değildir;
- büyük gerçek veya sentetik rice batch global karışım için açılmamalıdır;
- RiceSEG gerçek verisi ayrı rice specialist'e, R3 asset'i ise kullanılmamış
  stress/ablation girdisine ayrılmalıdır;
- sonraki ilerleme veri oranı aramak değil, parametre/gradient izolasyonudur.

Bu rapor yazıldığında bir sonraki deney olarak tanımlanan parametre-izole
`target_crop_id=rice` specialist daha sonra tamamlandı ve kabul edildi; R3 bu
eğitime girmedi. Güncel karar
[`REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md`](REAL_DATA_RICESEG_SPECIALIST_GATE_V1.md)
içindedir.

## Kanonik kanıtlar

```text
RiceSEG quality gate
data/processed/audits/riceseg_quality_gate_v1.json
SHA-256 1653ebfed22e9b8920b88ddbb3460a8648729b0934f63018077d78e2b8ed4904

V1 selection
data/processed/audits/real_data_riceseg_additive_screen_selection_v1.json
SHA-256 1bd0ea754e9a810bc65ab79dbf34336d5d0b8e57d72418d5df21f209cf106be0

V2 selection
data/processed/audits/real_data_riceseg_lowdose_screen_selection_v2.json
SHA-256 c493dde9ab9cf9d439a21164dd07e53bb4db293e845da359177b9f6857db2e7b

Sampler stream audit
data/processed/audits/real_data_riceseg_sampler_stream_audit_v1.json
SHA-256 e49de16b34690a348147dec5b82effbbb10b9c02b3ba8f809ba161e4670721b5

V3 frozen protocol
configs/benchmark/real_data_riceseg_exact_replay_selection_protocol_v3.yaml
SHA-256 36e0ba4539126af9c21bd94d82fc31979bf83d3469dd6ebc08b14df3bf96bd3f

V3 exact-index training receipt
data/runs/realab_riceseg_exactreplay025_r5_e8_v3/seed_17/exact_replay_replacement_receipt.json
SHA-256 e89768ff7f7113476fdc6e6bca6296f4a10546fb636c7eec52bec6aa727c4ff5

V3 checkpoint (rejected; retained only as evidence)
data/runs/realab_riceseg_exactreplay025_r5_e8_v3/seed_17/last.pt
SHA-256 e8261b4b27f4264b5087ff601a66bc90213ec6496d52f1603eb3d50c9db847d0

V3 selection
data/processed/audits/real_data_riceseg_exact_replay_screen_selection_v3.json
SHA-256 114a03b0dc10afbd1cf43121db279caf7a97570ae0c269cf5fec2a9049df5971
```

Tekrar üretim komutları:

```bash
.venv/bin/python scripts/audit_riceseg_sampler_streams.py \
  --baseline data/runs/simab_real_sorghum_cropcraft_v3_05_paddy_v4_05_e8/seed_17/config.resolved.json \
  --candidate v1=data/runs/realab_riceseg_add05_replay_r5_e8_v1/seed_17/config.resolved.json \
  --candidate v2=data/runs/realab_riceseg_add025_compute3780_r5_e8_v2/seed_17/config.resolved.json \
  --output data/processed/audits/real_data_riceseg_sampler_stream_audit_v1.json

.venv/bin/python scripts/train_exact_replay_replacement.py \
  --matrix configs/benchmark/real_data_riceseg_exact_replay_screen_v3.yaml \
  --candidate realab_riceseg_exactreplay025_r5_e8_v3 --seed 17
```

İkinci komut var olan run dizininin üzerine yazmaz; bu, yanlışlıkla kanıt
artefaktını ezmeyi önleyen kasıtlı davranıştır.
