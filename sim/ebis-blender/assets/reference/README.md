# EBIS referans indeksi

Küçük doküman/makine referansları teslimin taşınabilir olması için `raw/` altında tutulur. 36 GB gerçek LED dataseti burada çoğaltılmaz; `data/real/README.md` içindeki pointer kullanılır.

## Kamera ve makine içi

- Gerçek LED kökü: `260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/` (paket dışında).
- Görsel karşılaştırmada kullanılan kesin kare: `160126-ivedik-ledli-part-1/images/train/vlcsnap-2026-01-16-16h18m18s208.png` (`Kamera 01`).
- `raw/kırım_makinesi_görselleri/`: pres tablası aşınması, beton yüzeyi, kırık kenar ve moloz yardımcı referansları.

## Cihaz ve RFID

- `raw/ebis.odt`: EBIS cihazı ile görsel RFID etiketinin ön/arka fotoğrafları; gömülü özgün görseller ODT arşivindeki `Pictures/` dizinindedir.
- `raw/ebis.pdf`: aynı çalışma notlarının PDF görünümü.

RFID için kullanılan yaklaşık görsel sözleşme 60×10×0.12 mm ince film, doygun amber ön yüz, koyu mat arka yüz, ortada siyah kapsül ve bakır anten kanatlarıdır. Bunlar üretici CAD’i veya RF ölçümü değildir.

## Kalibrasyon durumu

- Release config’te küp yaklaşık 180 mm; silindir yaklaşık 126 mm çap × 201 mm yüksekliktir. Ölçüler gerçek bbox medyanlarına görsel fit’tir, fiziksel ölçüm iddiası değildir.
- İki kamera profili 2.8 mm lens ve 5.8 mm sensor width kullanır; ölçülmüş intrinsics değildir.
- Lens distorsiyonu görsel tahmindir.
- Gerçek karelerdeki AprilTag ve insan sentetik iki-sınıflı generator’a dahil edilmez; hedef yalnız `rfid_tag` ve `concrete_sample` sınıflarıdır.
