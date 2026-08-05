# BAWSeg edinim ön-kontrolü — v1

## Sonuç

BAWSeg, RiceSEG sonrasında bulunan en yüksek değerli yeni dense gerçek-veri
adayıdır. Kamu sayfası ve disk kapasitesi kapıları geçti; veri henüz
indirilmedi. IEEE DataPort indirmesi oturum/abonelik istediği için güncel
durum `blocked_authentication`'dır. Bu durum veri kalitesi reddi değildir.

```text
public landing/content-id gate:       PASS
archive download capacity gate:       PASS
authenticated archive acquisition:    BLOCKED
ZIP central-directory/CRC/SHA gate:    NOT RUN
license review:                        NOT RUN
extraction/training authorization:     false / false
```

Veri coverage matrisine, ortak eğitime veya model seçimine eklenmedi;
external/final test okunmadı.

## Neden değerli

[Resmî makale](https://www.mdpi.com/2072-4292/18/6/915) ve
[IEEE DataPort kaydı](https://ieee-dataport.org/documents/multispectral-remote-sensing-weed-detection-west-australian-agricultural-lands),
dört sezon boyunca Batı Avustralya'daki iki ticari barley paddock'tan beş
bantlı multispektral veri ve dense `crop / weed / other` anotasyonu bildirir.
Within-plot, cross-plot ve cross-year protokolleri tek-saha rastgele karo
split'inden daha güçlü bir robustluk kontrolü sağlayabilir.

Kamu kaydında bildirilen maske değerleri için dondurulmuş ortak ontoloji:

| Kaynak | Anlam | Ortak |
|---:|---|---:|
| 0 | crop | 1 |
| 1 | weed | 2 |
| 2 | other/background | 0 |
| 255 | ignore | 255 |

Bu eşleme yalnız edinim sonrası piksel/README doğrulaması geçerse açılır.

## Kamu sayfası ve kapasite kanıtı

3 Ağustos 2026 ön-kontrolü şunları doğruladı:

- DOI `10.21227/f8e1-5934`, dataset ID `14627`, content ID `101935`;
- görünen dosya `Multispectral Image Benchmark Dataset.zip`, boyut `7.5 GB`;
- durum `Subscription Required`;
- sayfada `README_DATASET.txt`, `LICENSE.txt`, `manifest.csv` ve
  `checksums_sha256.txt` paket içeriği olarak bildiriliyor;
- HDD boş alanı `299.211.579.392` bayt (yaklaşık 279 GiB);
- dondurulmuş maksimum indirme `12.884.901.888` bayt (12 GiB) ve indirme
  sonrası asgari rezerv 100 GiB; indirme kapasite kapısı geçti.

Aynı kamu sayfası toplam hacmi `500 GB+`, indirilebilir ZIP'i ise `7.5 GB`
olarak tarif ediyor. Bu iki sayı extraction planı için birlikte güvenilir
değildir. Bu nedenle arşiv geldikten sonra ZIP merkez dizinindeki gerçek
uncompressed boyut ve HDD rezervi hesaplanmadan tek dosya bile çıkarılmaz.

Kanonik kamu/disk makbuzu:

```text
data/processed/audits/bawseg_remote_preflight_v1.json
SHA-256 d29a7effc8592f983dc47d9ec2e4540f6f2de5e9ea2555f680e453b93be2bb00
```

## Fail-closed edinim zinciri

Araç aşağıdaki sırayı zorunlu tutar:

1. Kamu landing/content-ID ve disk rezervi.
2. Kimlik doğrulamalı HTTPS indirme; 12 GiB hard limit ve Range-resume.
3. Extraction yapmadan safe-path, symlink, duplicate member, zorunlu kontrol
   dosyaları, manifest kolon/satır/boyut/hash ve merkez-dizin kapasite denetimi.
4. Ayrı tam ZIP CRC ve her iç checksum için streamed SHA-256.
5. `LICENSE.txt` insan incelemesi. İnceleme bitene kadar
   `commercial_allowed=false` ve `training_authorized=false`.
6. Ancak bundan sonra RGB/common-mask dönüşüm protokolü dondurulur;
   publisher split'leri field/year sızıntısı bakımından ayrıca audit edilir.

Araç ZIP'i otomatik çıkarmaz. Cookie veya imzalı URL'yi config'e, log'a ya
da makbuza yazmaz. Cookie dosyası proje dışında tutulmalı ve yalnız IEEE
DataPort alanına ait Netscape-format cookie'leri içermelidir.

```bash
# Anonim kamu/disk kapısı
.venv/bin/python scripts/acquire_bawseg.py --preflight

# IEEE oturumu olan kullanıcı tarafından; cookie yolu proje dışında
.venv/bin/python scripts/acquire_bawseg.py --download \
  --cookie-file /guvenli/proje-disi/ieee-dataport.cookies.txt

# Arşiv tarayıcıyla doğrudan HDD hedefine indirildiyse
.venv/bin/python scripts/acquire_bawseg.py --inspect-existing
.venv/bin/python scripts/acquire_bawseg.py --verify-existing
```

Tarayıcıyla manuel indirme hedefi root disk olmamalıdır; root'ta yalnız
yaklaşık 4,8 GiB boşluk vardır. Hazır HDD hedefi:

```text
/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/raw/bawseg/archives/Multispectral_Image_Benchmark_Dataset.zip
```

## Dondurulmuş kanıt

- Config: `configs/data/bawseg_acquisition_v1.yaml`, SHA-256
  `dc0d01e7c9923ae98e9ff465c83fe9ef05d62e3bc7b2b65070dcada769c05d73`
- Araç: `scripts/acquire_bawseg.py`, SHA-256
  `3511894000d2b764e88558d6af9824a90a2bd20bc344f4978f6e8e3c55d420b1`
- Test: `tests/test_acquire_bawseg.py`, SHA-256
  `f31c9e730772a58d6269d9264d57d55087b19d60acb8183964408cd4b2439c37`
- Hedef release'in arşiv SHA-256'sı henüz bilinmiyor; indirilmemiş dosya
  için hash veya lisans uygunluğu iddiası yapılmıyor.
