# EBIS gerçekçilik multi-repeat — pass 6/6 final refinement

Tarih: 2026-07-30  
Kapsam: mevcut `multi-repeat-simulation-realism-6da1ae98b227` koşusunun
yalnız altıncı ve son bounded refinement pass'i.

## Sonuç

Fresh gerçek piksel incelemesinde iki motorun ortak, güvenle
düzeltilebilen en büyük lokal materyal farkı betonun üst tabla altında
yük alan bölgesiydi. Gerçek LED ve IR karelerde bu bölge numunenin geri
kalanından daha kirli, koyu/ochre, pitted ve yük izli; önceki sentetik
numunelerde ise yüzey çoğunlukla tekdüze temizdi.

Blender v1.7.15 ve Unreal pass-6e sahnesine aynı fiziksel niyeti taşıyan
bağımsız-seed'li
`clustered_submillimetre_embedded_ochre_dark_residue_v1` profili eklendi.
Değişiklik numune siluetini büyütmez, üst tablayı delmez, instance
kimliğini değiştirmez ve ölçülmüş kir prevalansı/BRDF iddiası taşımaz.

## Fresh referans örneklemesi

Dosya adından çıkarım yapılmadı; seçilen kareler ve sentetik çıktılar
orijinal çözünürlükte açıldı.

- LED RGB: task 9–14 içindeki altı kamera-task grubunun her birinden
  concrete-positive `q=0.13/0.47/0.81`; toplam 18 farklı zamanlı kare.
- IR/non-LED: mevcut 18 `REF-*_CAM*` makine-kamera grubunun tamamından,
  dönen `q=0.23/0.52/0.79`; toplam 18 concrete-positive gri kare.
- Seçim kaydı:
  [`multi_repeat_pass6final_reference_selection.json`](reports/qc/multi_repeat_pass6final_reference_selection.json).
- LED sheet SHA-256:
  `499072903ac1bb2daa4af4cd7a817f2301646e675ba47699f9fcb61a9b30d454`.
- IR sheet SHA-256:
  `5012588256817ea3c369c815cc8eb6b8c95911e1c4c51ad97740225495fa3dcf`.

IR yalnız değişmez geometri, temas ve tonal yapı kanıtı olarak
kullanıldı; gri IR pikseller RGB renk hedefi yapılmadı.

## Uygulanan değişiklik

### Blender

- `scripts/generate_ebis.py` → `SCRIPT_VERSION=1.7.15`.
- Ana sahne RNG'sinden ayrılmış `top-load-weathering-v1` RNG'si.
- `clean/pitted/edge_worn/spalled` rejimine bağlı, küçük ve çoğunlukla
  gömülü ochre/dark mikro-yama kümeleri.
- Dithered alpha, procedural alpha kırılması ve mikro bump; yama actor'ları
  betonla aynı `pass_index=2`, `semantic_class=concrete_sample`.
- Metadata ve validator hard gate:
  patch count, ochre/dark toplamı, profil ve açık belirsizlik durumu.
- Kanonik pilot:
  [`realism_v5_26_load_zone_release_p6g_54304`](ebis-blender/output/realism_v5_26_load_zone_release_p6g_54304).

### Unreal

- Aynı bağımsız RNG, profil ve rejim-bağımlı sınırlar iki motor arasında
  ortaklaştırıldı.
- Translucent sphere yaklaşımı depth sorting nedeniyle reddedildi.
  Nihai yüzey, mevcut doğrulanmış pore orientation'ıyla hizalı, sığ,
  küçük ve opaque disc kümeleridir; shadow kapalı, instance/semantic
  kimliği betondur.
- Metadata ve `build_visible_bboxes.py` validator'ına aynı hard gate'ler
  eklendi.
- Kanonik pilot:
  [`realism_r45_load_zone_release_p6e_58520`](unreal-ebis/output/realism_r45_load_zone_release_p6e_58520).

## Actual-pixel seçim süreci

Kodun çalışması kabul ölçütü yapılmadı. Aşağıdaki tanılar render edilip
tek tek açıldı:

- Blender opaque blob → fazla kahverengi/yapışık; reddedildi.
- Blender alpha/mottle → yumuşadı fakat tekil dekor lekesi okudu;
  kümelendirilip küçültüldü.
- Unreal translucent spheres → “sabun köpüğü”/depth-sort artefaktı;
  reddedildi.
- Unreal opaque spheres → dışa şişen oyuk/kabarcık okudu; reddedildi.
- Unreal büyük disc → doğru yüzey yönü fakat fazla ayrı/iri;
  mikro-kümeye indirildi.

Final 12-kare contact sheet'lerde üst tabla penetrasyonu, transparan
halo, kabarcık, specimen-top taşması veya yeni unlabeled hedef
görülmedi. Eşleştirilmiş son görsel:
[`multi_repeat_pass6final_matched_comparison.png`](reports/qc/multi_repeat_pass6final_matched_comparison.png).

## Teknik doğrulama

### Blender

- 12/12 `PASS`; `1280×720`, 64 spp, iki kamera `6+6`.
- Partition: `7 standard / 4 hard / 1 exclude`.
- Yüzey: `4 clean / 5 pitted / 2 edge / 1 spalled`.
- 12 yük-bölgesi kontrolü, toplam 127 mikro-yama.
- 36 fiziksel RFID, 60 binary instance/semantic maske.
- Hata yok; depth'in bilinçli kapalı olması ve hard/exclude varlığı
  beklenen uyarılardır.
- Render toplam `76.781 s`, ortalama `6.398 s/kare`.
- Manifest:
  [`realism_v5_26_load_zone_release_p6g_54304_manifest.json`](ebis-blender/evidence/release/realism_v5_26_load_zone_release_p6g_54304_manifest.json).

### Unreal

- 12/12 `PASS`; `1280×720`, iki kamera `6+6`, şekil `6 cube + 6 cylinder`.
- Partition: `4 standard / 2 hard / 6 exclude`.
- 52 visible + 52 amodal instance maskesi.
- 12 yük-bölgesi kontrolü, toplam 150 mikro-yama.
- Dört camera×shape concrete bbox hücresi gerçek hedefe `abs≤0.06`.
- Hata ve uyarı yok; batch camera-warped depth fail-closed kapalı.
- Engine capture `71.991 s`.
- Manifest:
  [`realism_r45_load_zone_release_p6e_58520_manifest.json`](unreal-ebis/evidence/release/realism_r45_load_zone_release_p6e_58520_manifest.json).

## Eş-seed annotation ve lokalizasyon denetimi

Tam kayıt:
[`multi_repeat_pass6final_pixel_audit.json`](reports/qc/multi_repeat_pass6final_pixel_audit.json).

- Blender: önceki pass-6f ile 12/12 YOLO label ve 60/60 decoded mask
  pikseli aynı; 60/60 mask bbox aynı.
- Unreal: önceki pass-6d ile 12/12 YOLO label aynı; 204/208 decoded mask
  aynı. Değişen dört dosya yalnız seed 58531 betonunun visible/amodal
  pre/post-camera varyantlarıdır; 208/208 mask bbox aynıdır.
- Seçilen iki Blender karede top-%28 RGB farkı alt-%55 farkının
  `484×–1154×`; Unreal'da `4103×–7129×` katıdır. Bu yalnız kontrollü
  değişikliğin yük bölgesine lokal olduğunu gösterir; perceptual kalite,
  domain mesafesi veya YOLO faydası ölçüsü değildir.

## MCP doğrulaması

### BlenderMCP

- Pinned commit `da4e16d2069ce5154eaa2535bf995e843caf5c73`.
- Yalnız `127.0.0.1:9876`; scene-info `147→147` nesne, nonce execute,
  viewport ve `1920×1080`, 128 spp OptiX render `PASS`.
- Scene generator v1.7.15 ve kanonik config ile fresh kuruldu.
- Process durduruldu, port kapandı.
- Kanıt:
  [`pins_v1_7_15.json`](ebis-blender/evidence/mcp/pins_v1_7_15.json),
  [`roundtrip.json`](ebis-blender/evidence/mcp/20260730-pass6g-load-zone/roundtrip.json).

### Epic resmi Unreal MCP

- Yalnız `http://127.0.0.1:8000/mcp`, protocol `2025-11-25`.
- Dokuz çağrı: initialize, tools/list, toolset list/describe,
  build/validate/status ve `1920×1080` RGB + EXR depth +
  7 visible/7 amodal instance render.
- Seed 58523 sahnesinde 11 yük-bölgesi yaması metadata'da mevcut ve scene
  validator `ok=true`.
- Editor durduruldu, port kapandı.
- Kanıt:
  [`verification summary`](unreal-ebis/evidence/mcp/realism_p6e_load_zone_verification_summary.json),
  [`roundtrip`](unreal-ebis/evidence/mcp/realism_p6e_load_zone_roundtrip.json).

## Komut özeti

```bash
# Blender validator — RTX 3090
blender -b --factory-startup --python scripts/generate_ebis.py -- \
  --config configs/ebis_led_v2.json --action validate \
  --output output/realism_v5_26_load_zone_release_p6g_54304 \
  --expected-count 12 --require-both-cameras --no-depth

# Unreal validator
python3 scripts/build_visible_bboxes.py \
  --root output/realism_r45_load_zone_release_p6e_58520 \
  --config configs/ebis_unreal_v1.json

# Unreal resmi MCP
./scripts/start_unreal_mcp.sh
python3 scripts/unreal_mcp_client.py \
  --config "$PWD/configs/ebis_unreal_v1.json" \
  --output "$PWD/output/mcp_load_zone_p6e_58523" \
  --evidence "$PWD/evidence/mcp/realism_p6e_load_zone_roundtrip.json" \
  --seed 58523 --camera camera_angled --shape cylinder --render
./scripts/stop_unreal_mcp.sh
```

## Kalan farklar ve sonraki en değerli refinement

Bu pass belirgin bir lokal materyal boşluğunu kapattı; dijital ikizi
tamamlamadı. Matched sheet'te hâlâ:

1. gerçek specimen üstünde geniş, yönlü yük izi/streak ve kırık agrega
   kuyruğu; sentetikte sınırlı procedural disk/yama;
2. makineye göre değişen gerçek iç panel/kapak/tabla kenarı topolojisi,
   mavi-gri alan oranı ve kapı önü/operatör;
3. ölçülmemiş çelik/powder-coat/concrete BRDF, LED diffuser/IES ve
   cam-10/11 intrinsics/response;
4. Unreal'da fazla sensör speckle, Blender'da fazla temiz/sakin bazı
   yüzeyler;
5. plate-gap tag görünür uçlarının gerçek prevalansı ve parlak amber
   görünümü

açıktır.

En yüksek değerli sonraki iş, yeni procedural noise eklemek değil:
aynı makinede gri kart + boş chamber + iki kamera checkerboard çekimi;
üst/alt tabla ve beton yük bölgesinin ölçekli, polarize yakın planları;
bir küp/bir silindir photogrammetry/scan'i; tabla çapı/mesafesi, kamera
pose/lens ve difüzör ölçüsüdür. Bunlarla shared texture/decal/scan ve
camera profile iki motora aynı anda pinlenebilir. İnsan/el/kapı dağılımı
ayrı explicit ablation kolu olmalıdır.

Model faydası ölçülmedi. Kabul yalnız frozen gerçek test split'li
`R_ONLY`, `R+B`, `R+U` çok-seed nano YOLO ablation'ından gelir.
