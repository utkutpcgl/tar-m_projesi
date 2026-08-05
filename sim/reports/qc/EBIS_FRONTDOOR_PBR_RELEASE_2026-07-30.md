# EBIS front-door/PBR release raporu — 2026-07-30

## Sonuç

Blender ve Unreal EBIS sahneleri aynı güncel fiziksel sözleşmeye getirildi:
düz nominal cube/cylinder, iki `Ø400 mm` tabla, mavi sabit tırtıklı hazne
duvarları, sağ menteşeden dışa açılan dolu gri ön kapı ve ona parent gri
servis kapağı, üst tabla kotunda back/left/right boyunca tam boy ince opal
U-difüzör. Sürgülü/cam kapı, turuncu sabit hardware ve içbükey numune
dikey kenarı kaldırıldı.

Her yeni turda izlenecek değişmeyen girişler:

- [Blender current samples](../../ebis-blender/output/current_samples/contact_sheet.png)
- [Unreal current samples](../../unreal-ebis/output/current_samples/contact_sheet.png)
- [Gerçek–Blender–Unreal eşlenik QC](../../unreal-ebis/reports/qc/assets/real_blender_unreal_comparison.png)

`CURRENT.json` dosyaları source run, validation SHA-256, selection policy ve
kopyalanan bütün dosya hash'lerini taşır. Yerel ve 3090'daki sekiz current RGB
hash'i birebir aynıdır.

## Kanonik release ve teknik kanıt

| Kapı | Blender | Unreal 5.8.1 |
| --- | --- | --- |
| Kaynak run | `realism_v8_cast_pores_release_60100` | `realism_r59_neutral_cast_brdf_release_60160` |
| RGB | 12 × 1280×720, Cycles 64 spp | 16 × 1280×720, Lumen/HWRT |
| Kamera/şekil | 6+6 kamera; dört hücre mevcut | 8+8 kamera; 8+8 cube/cylinder |
| Annotation | 32 RFID; 56 visible binary maske | 70 visible + 70 isolated-amodal maske |
| Partition | 8 standard / 1 hard / 3 exclude | 5 standard / 2 hard / 9 exclude |
| Validator | `PASS`, `errors=[]`; depth bilinçli kapalı uyarısı | `ok=true`, `errors=[]`, `warnings=[]` |
| Bbox gate | instance-visible sözleşmesi PASS | dört camera×shape hücresi gerçek hedefe mutlak `≤0.06` |
| MCP | V8 wide-open scene, `163→163`, 1080p/128 spp OptiX `PASS` | r59 Epic MCP, 9-call build/validate/status, 1080p RGB+EXR+instance `PASS` |
| Listener | yalnız `127.0.0.1:9876`, tur sonunda kapalı | yalnız `127.0.0.1:8000`, tur sonunda editor/port kapalı |

Kaynak/3090 SHA eşliği:

| Dosya | SHA-256 |
| --- | --- |
| Blender generator | `b307680cdc54cc8d487da7ca6b8a1898c4772a8addfb9529a35ab623c8fbea12` |
| Blender config | `aecb07d4fd91a317046e02afa9a5f23584350973a0f2540de60ebbb77901670b` |
| Unreal generator | `086e3335fe48105b63f01b7f332897088b943ce629c043ea87ece1fa59ba97f8` |
| Unreal config | `e7f40c3b95ecdb51426c46473106bfc675eebeba10a60274db64e5c01b7e1eca` |

Kanıtlar:

- [Blender validation](../../ebis-blender/output/realism_v8_cast_pores_release_60100/validation.json),
  [MCP pins](../../ebis-blender/evidence/mcp/pins_v1_8_1.json),
  [MCP round-trip](../../ebis-blender/evidence/mcp/20260730-cast-pores-v8/roundtrip.json)
- [Unreal validation](../../unreal-ebis/output/realism_r59_neutral_cast_brdf_release_60160/validation.json),
  [Epic MCP round-trip](../../unreal-ebis/evidence/mcp/20260730-neutral-cast-r59-roundtrip.json)

## Actual-pixel ve çevrimiçi asset kararları

Zaman/makine yayılı LED RGB ve `REF*` IR/non-LED kareleri birlikte kullanıldı.
IR yalnız değişmeyen topoloji/kamera/kapı/occlusion kanıtıdır; renk veya BRDF
hedefi değildir.

- Poly Haven `Blue Metal Plate` 2K aynı-seed Blender testinde doygunluğu
  düşürdü; gerçek hammertone yerine uzun çizik ve geniş seam tekrarı
  gösterdi. İki engine'de canonical yapılmadı.
- ambientCG `Concrete003` 2K Blender'da düşük-oranlı box-projection
  hibrit olarak tone/micro-contrast yönünde iyileşti ve canonical oldu.
  Procedural gözenek/hasar ve silhouette ana kaynak kalır.
- Poly Haven `Rough Concrete` 1K lisans/provenance açısından temizdi; ancak
  same-seed iki concrete ROI'de yalnız `4.78–4.94/255` ortalama mutlak RGB
  farkı ve yanlış plaster karakteri verdiği için canonical yapılmadı.
- Aynı asset Unreal direct-UV testinde silindirde yatay gerilme ve cube'da
  aşırı koyu agrega kontrastı üretti; reddedildi. Unreal V24 hücresel ve V25
  mermerimsi procedural albedo denemeleri de reddedildi; canonical concrete
  nötr constant cast BRDF V27 + ölçekli küçük pore/edge/residue geometrisidir.
- Sketchfab genel compression-machine modeli EBIS hazne/kapı/tabla düzenine
  uymadı ve doğrulanabilir production indirme/lisansı görülmedi. Hasarlı
  scanned concrete cylinder ise sağlam nominal specimen bazı değildir.

Kompakt A/B:
[Blender karar raporu](../../ebis-blender/reports/qc/ONLINE_ASSET_AB_2026-07-30.md),
[Blender provenance](../../ebis-blender/docs/ASSET_PROVENANCE.md),
[Unreal provenance](../../unreal-ebis/docs/ASSET_PROVENANCE.md).
İndirilen Poly Haven ve ambientCG haritalarının 18/18 manifest SHA kontrolü
geçmiştir.

Yeni actual-pixel sheet'te gerçek numunenin üst-yük kırığı, kir/aggregate
kontrastı ve fisheye yakınlığı iki sentetikten de belirgin güçlüdür. Blender
fazla temiz/aydınlık; Unreal r59'da önceki cellular/marble doku yoktur fakat
geniş keskin ışık bantları sürer. Bu kayıt kalite iddiası değil, sonraki
refinement hedefidir.

## Temizlik ve output convention

[`OUTPUT_CONVENTION.md`](../../OUTPUT_CONVENTION.md) source of truth'tur.
`scripts/promote_ebis_current_samples.py` doğrulanmış run'dan dört hücreyi
atomik yayınlar. `scripts/cleanup_ebis_obsolete.py` dry-run zorunlu ve
varsayılan olarak geri alınabilir `gio trash` kullanır.

| Alan | Taşınan hedef | Dosya | Boyut | Sonuç |
| --- | ---: | ---: | ---: | --- |
| Yerel output/root-QC | 290 | 11.190 | 2,848 GiB | `all_targets_absent=true` |
| Yerel eski MCP image/log turu | 14 | 34 | 0,023 GiB | `all_targets_absent=true` |
| 3090 output/root-QC/eski MCP | 334 | 13.188 | 3,324 GiB | `all_targets_absent=true` |
| Pass-1 yerel V7/r56–r58/current/QC | 11 | 1.102 | 0,357 GiB | `gio-trash`, `all_targets_absent=true` |
| Pass-1 3090 ara V25–V29 + V7/r56–r58/QC | 23 | 1.660 | 0,539 GiB | `gio-trash`, `all_targets_absent=true` |

Gerçek dataset, generator/config, docs, PBR kaynakları, nested
`reference_forensics`, compact `asset_ab` ve güncel MCP kanıtı hedef
değildi. Manifestler:

- [`CLEANUP_MANIFEST_2026-07-30.json`](../cleanup/CLEANUP_MANIFEST_2026-07-30.json)
- [`CLEANUP_MANIFEST_2026-07-30_EVIDENCE_PASS.json`](../cleanup/CLEANUP_MANIFEST_2026-07-30_EVIDENCE_PASS.json)
- [`CLEANUP_MANIFEST_3090_2026-07-30.json`](../cleanup/CLEANUP_MANIFEST_3090_2026-07-30.json)
- [`CLEANUP_MANIFEST_PASS1_2026-07-30.json`](../cleanup/CLEANUP_MANIFEST_PASS1_2026-07-30.json)
- [`CLEANUP_MANIFEST_3090_PASS1_2026-07-30.json`](../cleanup/CLEANUP_MANIFEST_3090_PASS1_2026-07-30.json)

## Kalan maddi domain gap

1. Ölçülü chamber/door/platen/camera-mount CAD'i yok.
2. Mavi boya, gri kapı sacı, kullanılmış tabla ve nominal/hasarlı beton için
   scale-referanslı cross-polarized color/normal/roughness scan'i yok.
3. Cam-10/cam-11 intrinsics/distortion, fixed exposure response, white
   balance, video noise/sharpening ve LED lux/IES ölçülmedi.
4. Unreal'da geniş keskin ışık bantları ve sentetik planar shading; Blender'da
   aşırı temiz/aydınlık beton kalır. Gerçek ağır hasarlı örneklerin rough edge,
   load-zone kir/aggregate ve camera-near fisheye kuyruğu tam kapanmaz.
5. Gerçek görüntülerdeki el/operatör, workshop backplate ve değişken kir/debris
   yalnız bounded augmentation veya omission'dır.
6. 100-kare iki kişilik insan QC, aynı-senaryo blind engine study ve frozen
   gerçek test YOLO ablation'ı yapılmadı.

Bu nedenle “daha gerçekçi yönde iyileşti” actual-pixel gözlemidir; dijital
ikiz veya model kazancı iddiası değildir.

## Kullanıcıdan en yüksek değerli destek

İş şu sırayla hızlanır:

1. Cam-10 ve cam-11'den boş hazne: kapı yaklaşık `5° / 30° / 70°`, LED
   açık/kapalı; auto exposure/white balance kapalıysa değerleriyle. Her
   koşulda gri kart ve ColorChecker içeren 3–5 kare.
2. Chamber iç genişlik/derinlik/yükseklik, iki tabla çap/kalınlık/aralık,
   kapı leaf/pivot/menteşe tarafı ve U-difüzör kesit/konum ölçüsü; basit
   metreli foto veya kaba CAD yeterli.
3. Mavi tırtıklı duvar, gri kapı, üst/alt çelik temas yüzü, temiz/pitted/
   edge-worn/spalled cube ve cylinder için cetvelli yakın plan. Mümkünse
   aynı açıdan polarizer paralel/çapraz çifti.
4. İki kamera için ChArUco/checkerboard: board spec, gerçek basım kare mm,
   tam çözünürlükte 20+ açı ve lens/focus sabit bilgisi.
5. İki `current_samples/contact_sheet.png` üzerinde yalnız şu işaretler:
   “olmayan parça”, “yanlış renk/yüzey”, “kapı açısı yanlış”, “kamera
   kadrajı yanlış”, “LED fazla/az”. Beğeni puanından daha değerlidir.
6. Gerçek detection split'i için capture/session kimlikleri ve staged
   elde/duvarda tag'lerin hedef pozitif sayılıp sayılmayacağı kararı.

Ayrıntılı iki haftalık çalışma/eğitim sırası:
[Blender planı](../../ebis-blender/docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
ve
[Unreal planı](../../unreal-ebis/docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md).
Model deneyi aynı nano checkpoint/hyperparameter ve seed `17/29/43` ile
`R`, `R+B-1N`, `R+U-1N`, gerekirse `R+B+U-1N`; validation/test yalnız gerçek
ve capture-safe split üzerinde yapılmalıdır.
