# YOLO nano ablation — kanonik plana yönlendirme

> Durum (2026-07-29): Bu dosyanın eski `R/R+B-1N/R+B-2N`,
> sabit 60 epoch ve `patience=12` tasarımı **superseded** edilmiştir.
> Ayrıntılı ve kanonik iki haftalık sözleşme
> [`INTENSIVE_14_DAY_ENGINEERING_PLAN.md`](INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
> içindeki G5/G6 kapılarıdır. Çalıştırılabilir eş
> [`experiments/yolo/README.md`](../experiments/yolo/README.md) ve
> [`run_ablation.sh`](../experiments/yolo/run_ablation.sh) dosyalarındadır.

Bu kısa dosya yalnız hızlı yönlendirme içindir; sayı veya yöntem
çelişkisinde kanonik plan geçerlidir.

## Dondurulmuş ana sözleşme

- En küçük, tek hash'li nano checkpoint: varsayılan `yolo11n.pt`.
- Tek derived class map:
  `{0: rfid_tag, 1: concrete_sample}`.
- Leakage'siz capture/session split; val ve sealed test yalnız gerçek.
- Koşullar:
  `R_ONLY`, `R_S025`, `R_S050`, `R_S100`, `R_Sbest_HARD`.
- Seed'ler: `17`, `29`, `43`; toplam 15 ana run.
- Aynı real-train manifesti bütün mix koşullarında byte-identical kalır.
- Standard sentetik dozlar sırasıyla `0`, `0.25N`, `0.50N`, `1.00N`.
- Exact integer dozlar ve tam `%20` hard replacement için frozen gerçek
  `N`, `20`ye bölünebilir seçilir.
- Hard ablation, en iyi standard dozun toplam sentetik sayısını
  değiştirmeden başlangıçta `%20` standardı hard ile değiştirir.
- `exclude` hiçbir train/val/test manifeste girmez.
- Bütün koşullar aynı checkpoint, environment, image size, batch,
  augmentasyon, optimizer/LR schedule ve
  `target_optimizer_updates` kullanır.
- Ana matriste early stopping kapalıdır (`patience=0`).
- Integer epoch granularity hedef update bütçesini `%1` içinde
  karşılayamıyorsa run başlamaz.
- Ana kıyas checkpoint'i sabit update bütçesinin sonundaki `last.pt`dir.
  Böylece farklı dataset boylarında epoch başına real-val cadence'i
  model seçimini karıştırmaz.
- Sealed gerçek test, bütün koşullar bittikten sonra bir kez açılır.
- Day 11'de yalnız `R_ONLY/R_S025/R_S050/R_S100` manifestleri freeze ve
  preflight edilir. `R_Sbest_HARD`, Day 12 frozen real-val sonucuyla
  Sbest seçildikten sonra Day 13'te oluşturulur.
- Dört standard composition'ın SHA'ları, aynı real seti ve
  `R_S025 ⊂ R_S050 ⊂ R_S100` nesting ilişkisi immutable matrix lock'ta
  doğrulanır.
- Sbest, dört koşul × üç seed `PASS` contract/`last.pt` hash'ine bağlı
  exact real-val metrics CSV'den kural ile hesaplanır; selection ledger
  olmadan hard preflight geçmez.
- Hard composition audit; aynı real seti, Sbest ile aynı sentetik
  toplamı, Sbest'ten kalan standard altkümesini ve tam `%20`
  `hard_occlusion` replacement'ı zorlar.

## Günlere göre karar özeti

| Gün | Çıktı | Eğitime geçiş şartı |
| ---: | --- | --- |
| 1 | hedef kapsamı, frozen capture split, test seal, model/environment pin | G0 ve split hash PASS |
| 2 | ölçü ve cam-10/cam-11 kalibrasyon ledger'ı | belirsizlikler/fallback'ler görünür |
| 3 | chamber/door/camera/platen/LED/sample-contact clay kilidi | G1 |
| 4 | gri-mavi panel ve iki platen PBR debug pass'leri | ölçek/tiling artefaktı yok |
| 5 | cube/cylinder, paper ve RFID placement/occlusion | mask-bbox unit PASS |
| 6 | üç-duvar LED, contact spill, shadow floor ve exposure | clipping/black-crush PASS |
| 7 | kamera intrinsics/fallback, distortion ve door prior | RGB/mask aynı warp PASS |
| 8 | placement prior ve standard/hard/exclude dağılımı | görünür-unlabelled standard `0` |
| 9 | kör real/old/new owner + operatör review | G2 |
| 10 | 16-senaryo determinism ve 100-kare iki-person bbox QC | G3 + G4 |
| 11 | QC-geçmiş pool ve dört standard frozen train/composition manifesti | nested matrix lock + hash/coverage + dört preflight PASS |
| 12 | dört standard-doz koşulu × üç seed | 12 PASS `last.pt` + val-only Sbest ledger; G5 |
| 13 | val-only Sbest sonrası ayrı hard manifest/preflight; `%20` replacement × üç seed; FP/FN slice | hard composition audit + adaylar frozen |
| 14 | bütün `last.pt`ler için tek sealed real-test eval | G6 GO/HOLD |

## Önceden yazılmış GO kapısı

GO ancak aşağıdakilerin hepsi sağlanır:

- `R_ONLY`a göre RFID AP50-95 üç-seed medyan farkı en az `+2.0` mutlak
  puan;
- seed'lerin en az `2/3`ünde RFID AP50-95 pozitif;
- RFID recall medianı gerilemez;
- concrete AP50-95 kaybı `1.0` puanı aşmaz;
- cam-10 ve cam-11 slice'larının ikisinde de anlamlı negatif yön yok;
- tiny/plate-gap kritik slice'ında yeni mutlak FN artışı yok;
- standard partition'da görünür fakat etiketsiz RFID sızıntısı yok.

Üç seed median/IQR, bootstrap confidence interval, per-camera,
cube/cylinder, tag-size, paper-under-tag, plate-gap, door ve
operator/hand slice'ları raporlanır. CI sıfırı keserse sonuç
`promising/inconclusive`dur; kazanç değildir. Eşikler sonuç görüldükten
sonra değiştirilmez.

## Yapılmayacaklar

- Tek seed artışını başarı saymak.
- Ardışık frame'leri rastgele train/val/test'e bölmek.
- Sentetik val/test kullanmak.
- Daha büyük mix datasetine daha fazla optimizer update vermek.
- `best.pt`yi farklı update cadence'i altında ana kıyas checkpoint'i
  yapmak.
- Hard görüntüyü dozu artıracak şekilde standard sete eklemek.
- Görsel gerçekçilik puanını detection metriği yerine kullanmak.
- Sonuç negatifken hatayı incelemeden daha fazla sentetik üretmek.
