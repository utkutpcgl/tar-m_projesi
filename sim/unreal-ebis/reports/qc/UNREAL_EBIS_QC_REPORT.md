# Unreal-EBIS tarihsel v1 teknik ve görsel QC raporu

> Bu dosya `pilot_release_v4`, `mcp_hero` ve aynı dönemin determinizm turunu
> belgeleyen tarihsel v1 baseline'dır. Güncel fiziksel r5 kanıtı
> [`REALISM_REVISION_2026-07-29.md`](REALISM_REVISION_2026-07-29.md), güncel
> release pini
> [`realism_r5_full_58200_manifest.json`](../../evidence/release/realism_r5_full_58200_manifest.json)
> ve güncel MCP pini
> [`realism_r5_verification_summary.json`](../../evidence/mcp/realism_r5_verification_summary.json)
> altındadır.

## Sonuç

UE 5.8.1 üzerinde EBIS sahne üretimi, resmi MCP kontrol yolu, RGB/depth export ve instance-aware detection annotation teknik olarak PASS’tir. Mevcut prosedürel görsel, gerçek LED görüntüye veya Blender v1.5.2 hero’ya göre fotogerçekçilik üstünlüğü göstermemiştir. YOLO eğitimi çalıştırılmadı; model kazancı bilinmiyor.

## Bu tarihsel v1 raporunun kanonik pilotu

`output/pilot_release_v4`:

| Ölçüm | Sonuç |
| --- | ---: |
| Çözünürlük / kare | 1280×720 / 16 |
| Süre | 21,09 s toplam; 1,318 s/kare |
| Kamera | 8 angled + 8 door |
| Sample | 8 cube + 8 cylinder |
| Fiziksel target instance | 65 = 16 concrete + 49 RFID |
| Visible / amodal mask | 65 / 65 |
| Depth | 16 geçerli, 16 benzersiz OpenEXR |
| Partition | 6 standard, 1 hard, 9 exclude |
| RFID statüsü | 15 standard, 2 hard, 14 below-hard, 14 fully occluded, 4 outside |
| Validator | `ok=true`, `errors=[]`, `warnings=[]` |

Exclude oranı bilerek yüksektir: seed tablosu plate-gap, tiny ve tam örtülü tag’leri zorlar. Bu görüntüleri normal train’e sokmak yerine fiziksel partition ile ayırmak annotation güvenliği açısından doğru davranıştır.

## Camera×shape bbox fit

Gerçek concrete medyanlarına en büyük normalize farklar:

| Hücre | En büyük fark | `.06` görsel kapı |
| --- | ---: | --- |
| angled × cube | .0249 | PASS |
| angled × cylinder | .0243 | PASS |
| door × cube | .0254 | PASS |
| door × cylinder | .0168 | PASS |

Bu sonuç intrinsics kalibrasyonu değildir; yalnız bbox framing fit’idir.

## Görsel QC

- [16-kare pilot contact sheet](assets/pilot_release_v4_contact_sheet.png)
- [4-kare 1080p hero contact sheet](assets/hero_release_contact_sheet.png)
- [Gerçek / Blender / Unreal karşılaştırması](assets/real_blender_unreal_comparison.png)

v3 sonrası concrete albedo, metal roughness, LED emissive/lumen ve manual exposure revize edildi. Pilot v4’te clipped-highlight oranı kare bazında `%4,66–%19,42`; hard fail eşiği `%35` altında. Buna rağmen bazı LED/platen yüzeyleri hâlâ düz beyaz, gölgeler sert ve workshop proxy geometrisi yalın. Concrete V6 yüzeyi ve üç katmanlı RFID daha okunaklıdır, fakat CAD/bevel/surface scan eksikliği belirgindir.

## Instance/occlusion QC

Visible pass target beyazken bütün occluder’ları siyah bırakır. Amodal pass yalnız target mesh parçalarını gösterir. Validator:

- beklenen her fiziksel instance için iki maskeyi;
- çözünürlük eşliğini;
- visible ≤ amodal toleransını;
- duplicate non-empty mask ve duplicate RGB’yi;
- OpenEXR magic/size/hash’i;
- config ve engine pinini;
- partition ve camera×shape dağılımını kontrol eder.

Tam örtülü RFID’nin bbox almaması ve tiny visible RFID bulunan karenin exclude olması contact sheet/metadata’da gözlendi.

## Tarihsel v1 resmî MCP

Epic MCP `127.0.0.1:8000`, protocol `2025-11-25`, session `019faca5415e7f05819c51a0fbc922ce` ile dokuz HTTP çağrısını hatasız tamamladı. Toolset build/validate/status ve 1080p RGB/depth/mask render çalıştı; tarihsel `output/mcp_hero/validation.json` PASS. Ayrı SSH shell başlat/çağır/durdur smoke'u session `019faca7bde77ba0a0c5c0ffff3cf4f2` ile ayrıca PASS; server testten sonra durduruldu. Bu paragraf güncel r5 MCP kanıtı değildir.

## Tekrar üretilebilirlik

Seed 58203 iki bağımsız editor batch’inde, aynı UE build/driver/3090 üzerinde:

- stable senaryo alanları eşit;
- RGB piksel/dosya SHA bit-exact;
- depth EXR bit-exact;
- visible/amodal decoded mask pikselleri bit-exact;
- yayımlanmış YOLO label bit-exact.

PNG container SHA’larının 9/10’u encoder metadata/sıkıştırma nedeniyle farklıdır; decoded pixel SHA’ları aynıdır. Farklı GPU, driver veya UE build’i için bit determinizmi iddia edilmez.

## Açık riskler

- CAD, ölçü ve intrinsics yok.
- Unreal basic primitive ve generated material’ler gerçek digital twin değil.
- İnsan/el ve gerçek kapı arkası domain’i yok.
- Sensor noise/distortion/overlay yok.
- Lumen scene-capture sonucu viewport/MRQ kalite kıyası değildir.
- Pilot yalnız 16 kare; 100-kare iki kişilik bbox QC yapılmadı.
- Model faydası ölçülmedi.
