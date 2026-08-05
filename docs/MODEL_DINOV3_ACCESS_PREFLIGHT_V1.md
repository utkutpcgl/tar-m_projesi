# DINOv3 ConvNeXt-Tiny erişim ön-kontrolü — v1

## Sonuç

Hugging Face oturumu `utkutpcgl` hesabı için geçerlidir ve RiceSEG gated
release'ine erişir. DINOv3 repository metadata'sı görülebilse de gerçek
`config.json`/weight isteği `GatedRepoError` (`401/403`) ile reddedildi. Bu,
[ayrı DINOv3 koşullarının](https://huggingface.co/facebook/dinov3-convnext-tiny-pretrain-lvd1689m)
hesap tarafında henüz kabul edilmediğini gösterir.

```text
Hugging Face login:       PASS
RiceSEG repository:       PASS
DINOv3 metadata:          VISIBLE
DINOv3 gated payload:     BLOCKED
DINOv3 weights downloaded: false
DINOv3 benchmark run:      false
```

Metadata'da pinlenen model commit'i
`10d30274b4d445111e2d5bf75ac93bbd94db274b`, weight dosyası
`model.safetensors`, bildirilen boyut `111.299.216` bayt ve LFS SHA-256
`bd30a9459d6149564ef53af6e8a1999980953b009b94cde836ac1bac4d339cb2`'dir.
Bu metadata, payload erişim kanıtı sayılmadı; küçük `config.json` için
gerçek authenticated download ayrıca denendi ve reddedildi.

Public model kartı ve DINOv3 lisans metni HDD'ye alındı:

```text
raw/dinov3_convnext_tiny/license/LICENSE.md
SHA-256 25d122eb8f5b880fd23c736fb6ea8018ee45c12237e00b8a86d14c653904999e

raw/dinov3_convnext_tiny/license/README.md
SHA-256 34016e50ef360f3aaeb44098a03fe6edb13ed92299c21d43c121df40efd3fcd1
```

Lisans Apache-2.0 değil, Meta'nın ayrı DINOv3 Agreement'ıdır; kullanım,
dağıtım, yayın atfı ve trade-control koşulları korunmalıdır. Bu rapor
hukukî/ticari uygunluk onayı vermez.

## Erişim açılırsa

Kullanıcı model sayfasında koşulları kabul ettikten sonra ilk test yalnız
küçük dosyayı istemelidir:

```bash
HF_HOME=/media/ankaref/HDD-MNT-500GB_1/tarim_vision_data/cache/huggingface \
  .venv/bin/hf download \
  facebook/dinov3-convnext-tiny-pretrain-lvd1689m config.json \
  --revision 10d30274b4d445111e2d5bf75ac93bbd94db274b
```

Bu geçerse 111 MB weight HDD cache'ine indirilir, forward-shape smoke testi
çalışır ve ancak sonra kabul edilmiş DINOv2 ile aynı veri/epoch/draw/seed
bütçesinde model ekranı dondurulur. Eski `dinov3_gated.yaml` tarihsel ilk
real-core tarifi olduğu için güncel accepted-control karşılaştırması olarak
doğrudan çalıştırılmaz.
