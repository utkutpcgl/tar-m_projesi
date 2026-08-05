# Unreal-EBIS handoff guide

## Değiştirilmeyecek sözleşme

- Sınıflar: `0 rfid_tag`, `1 concrete_sample`.
- Kameralar: `camera_angled ↔ cam-10/Kamera 01`, `camera_door ↔ cam-11/Kamera 02`.
- Scene/config birimi santimetredir.
- Bbox kaynağı fiziksel instance visible maskesidir; semantic union değildir.
- Fully occluded ve kadraj dışı tag metadata’da kalır, label almaz.
- Exclude hiçbir detection train/val/test listesine girmez.
- Test split yalnız bütün ablation koşulları bittikten sonra açılır.

## Kaynak ve compute

Local klasör kaynak teslimdir. 3090 klasörü render mirror’ıdır. Kod/config değişikliğini localde yapıp 3090’a `rsync -a` ile gönderin; `output/`, `evidence/`, `Saved/`, `Intermediate/` ve DDC’yi kaynak sync’e katmayın. Remote generated `Content/EBIS` asset’lerini kanonik değişiklikten sonra local pakete geri alın.

Engine ve plugin pinleri `evidence/install/install_manifest.json` içindedir. Yeni engine minor/patch, driver veya plugin ile üretilen run aynı benchmark revizyonu sayılmaz; ayrı hash ve run adı almalıdır.

Kanonik teknik baseline
[`realism_r59_neutral_cast_brdf_release_60160/validation.json`](../output/realism_r59_neutral_cast_brdf_release_60160/validation.json),
güncel resmi MCP pini
[`20260730-neutral-cast-r59-verification-summary.json`](../evidence/mcp/20260730-neutral-cast-r59-verification-summary.json)
ve iki motorun son actual-pixel karar kaydı
[`EBIS_REALISM_V2_PASS1_2026-07-30.md`](../../reports/qc/EBIS_REALISM_V2_PASS1_2026-07-30.md)
dosyasıdır. Bunlar teknik `PASS` kanıtıdır; fotogerçekçilik veya YOLO
kazancı değildir.

## Güvenli geliştirme döngüsü

1. `configs/ebis_unreal_v1.json` ve/veya `Content/Python/ebis_scene.py` değişir.
2. `python3 -m py_compile Content/Python/*.py scripts/*.py` ve `python3 -m json.tool configs/ebis_unreal_v1.json` çalışır.
3. Dört calibration seed (`60220..60223`) yeni run adına render edilir.
4. `build_visible_bboxes.py` dört camera×shape hücresinde maksimum bbox farkını kontrol eder.
5. Işık/materyal görseli contact sheet ve gerçek kıyasla incelenir.
6. 16-kare pilot yeni run adına üretilir; mevcut release üzerine yazılmaz.
7. 100-kare stratified insan QC geçmeden production veya eğitim datası üretilmez.
8. Değişiklik model faydası hedefliyorsa frozen gerçek test üzerinde ablation tamamlanır.

## Sahne mimarisi

`ebis_scene.py`, Unreal basic primitives ve generated materyallerden content-only sahne kurar. Sahnedeki bütün yönetilen actor’lar `EBIS_MANAGED` tag’i taşır. Fiziksel hedefin bütün parçaları aynı `EBIS_INSTANCE=<key>` tag’ini taşır; örneğin beton gövde, pore shell ve aggregate parçaları tek `concrete_00` instance’ıdır.

RGB ve maskeler aynı `SceneCapture2D`, transform ve FOV’u kullanır. Visible pass’te target beyaz, bütün occluder’lar siyah kalır. Amodal pass’te target dışındaki mesh’ler gizlenir; kadraj clipping’i korunur. Depth en son capture edilir; UE proxy güncellemesi nedeniyle RGB/maskeden sonra başka pass çalıştırılmaz.

Mask materyalleri editor restart’ında synchronous recompile edilir. Bu satırları kaldırmayın: hazır Linux build’i shader map hazır olmadan default beyaz materyal gösterebilir ve bütün instance maskelerini sessizce aynı yapabilir.

## Release kapıları

- metadata/RGB/depth sayıları beklenen count ile aynı;
- visible/amodal maske sayısı fiziksel instance sayısıyla aynı;
- bütün EXR’ler geçerli OpenEXR magic taşır ve boş değildir;
- duplicate RGB veya duplicate non-empty visible mask yok;
- visible piksel sayısı amodal’dan anlamlı biçimde büyük değil;
- iki kamera ve iki şekil mevcut;
- dört concrete bbox hücresi gerçek hedefe mutlak `.06` kapıda;
- `validation.json: ok=true`, `errors=[]`;
- bbox’lu contact sheet insan tarafından incelenmiş;
- normal train manifestinde yalnız standard partition var.

## Bilinen sınırlamalar

- Kamera fit’i bbox medyanına göredir; checkerboard intrinsics/distorsiyon değildir.
- Makine ve kapı geometry proxy’dir; ölçülmüş CAD değildir.
- PBR materyaller prosedüreldir, gerçek surface scan/normal/roughness yoktur.
- Üst yük bölgesindeki ochre/koyu mikro-disc kümeleri gerçek piksellerden
  çıkarılmış bounded proxy'dir; gerçek kir prevalansı, yönlü yük izi ve
  BRDF ölçülmemiştir.
- Basic-shape cube bevel’i ve gerçek kırık yüz morfolojisi yetersizdir.
- Camera 02 gerçek verisi yoğun insan/el örtüşmesi içerir; simülasyonda insan yoktur.
- Timestamp, analog sharpening/noise, lens distortion ve sensor MTF simüle edilmez.
- RFID elektriksel UID/RSSI simülasyonu yoktur; yalnız görsel tag vardır.
- Mevcut Unreal hero, Blender hero’dan görsel olarak üstün kabul edilmemelidir.

## Acil geri dönüş noktaları

- Sahne boşsa `Content/EBIS/Maps/EBIS_Press.umap` ve startup logunu kontrol edin.
- RGB beyazsa LightUnits, exposure ve emissive değerlerini kontrol edin.
- Maskeler aynıysa synchronous mask material recompile ve GPU readback fence’i kontrol edin.
- MCP toolset görünmüyorsa `Content/Python/init_unreal.py` logunda `EBIS_MCP` arayın.
- Port doluysa rastgele process öldürmeyin; `evidence/mcp/unreal_editor.pid` içindeki command line eşleşmesini `stop_unreal_mcp.sh` doğrular.
