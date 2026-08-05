# YOLO nano detection ablation planı

## Soru

Aynı frozen gerçek train/val/test ve aynı en küçük model altında güvenli Unreal verisi gerçek LED RFID detection sonucunu artırıyor mu; Blender baseline’ına göre ek değer getiriyor mu?

Başlangıç checkpoint’i `yolo11n.pt`, `imgsz=960`, seed `17/29/43`, 60 epoch ve patience 12’dir. Daha yeni nano seçilirse bütün koşullar aynı yerel checkpoint ve SHA-256’yı kullanır.

## Minimum matris

| Kod | Train | Amaç |
| --- | --- | --- |
| `R` | N gerçek | değişmez baseline |
| `R_B1N` | aynı N gerçek + N Blender standard | mevcut sentetik baseline |
| `R_U1N` | aynı N gerçek + N Unreal standard | Unreal katkısı |
| `R_U2N` | aynı N gerçek + 2N Unreal standard | yalnız U1N pozitifse doz |
| `U_only` | N Unreal, tek seed opsiyonel | ingest/domain sanity; başarı sonucu değil |

`N=min(1000, uygun gerçek train sayısı)`. Sentetik camera×shape×lighting×tag-count stratified seçilir. Hard yalnız ana sonuç pozitifse ayrı deney; exclude hiçbir koşulda yoktur.

## Sabit sözleşme

- Derived iki sınıf: `0 rfid_tag`, `1 concrete_sample`; gerçek `tag/concrete` ID’leri korunur, AprilTag/person satırları derived label’dan çıkarılır.
- Val/test yalnız gerçektir.
- Capture/session grupları split’ler arasında geçmez; ardışık frame random split yoktur.
- Gerçek train manifesti bütün koşullarda byte-identical’dır.
- Model, environment, imgsz, epoch, augmentasyon, optimizer ve seed seti aynıdır.
- Test bütün koşullar tamamlanmadan açılmaz.
- Üç seed medyanı ve dağılımı raporlanır; en iyi seed seçilmez.

## Önceden yazılmış GO eşiği

- RFID AP50-95 medyanı R’ye göre ≥+2,0 mutlak puan;
- en az 2/3 seed pozitif;
- RFID recall gerilemez;
- concrete AP50-95 medyan kaybı ≤1,0 puan;
- iki kamera slice’ında da yön negatif değil;
- standard partition’da visible-unlabelled tag yok;
- Unreal’ın Blender’a ek değeri ayrıca `R_U1N - R_B1N` ve maliyetle raporlanır.

Eşik sağlanmazsa HOLD; daha fazla sentetik yerine tiny/glare/plate-gap/hand/background/camera FP-FN analizi yapılır.

## Gün planı

1. Capture-safe gerçek split, iki sınıflı derived label ve manifest SHA freeze.
2. İzole Ultralytics venv, checkpoint/environment pin; R 2-epoch smoke.
3. R üç seed.
4. Unreal generator/config freeze ve 100-kare bbox QC.
5. Eşit N Blender/Unreal standard seçimi ve stratification audit.
6. R_B1N üç seed.
7. R_U1N üç seed.
8. Bütün best checkpoint’lere tek toplu gerçek-test eval.
9. 50 FP + 50 FN slice analizi; en fazla bir bounded generator düzeltmesi.
10. Median/IQR, camera/shape/person/tag-size slice ve compute maliyetli GO/HOLD raporu.

Runner yalnız train çalıştırır; test eval ayrı ve kayıtlı final aşamadır. Ayrıntı `experiments/yolo/README.md` içindedir.
