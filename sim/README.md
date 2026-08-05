# Simulation çalışma alanı

> GitHub kopyası; ayar, kaynak kod ve lessons-learned belgelerini içerir.
> Ham datasetler, render outputları, kanıt görselleri, indirilen texture'lar
> ve Unreal map/material binary'leri boyut nedeniyle repo dışındadır.

Bu kökteki güncel EBİS detection teslimleri:

- [`ebis-blender/`](ebis-blender/README.md): Blender 4.5.12/Cycles,
  kanonik `realism_v8_cast_pores_release_60100`;
- [`unreal-ebis/`](unreal-ebis/README.md): Unreal Engine 5.8.1/Lumen,
  kanonik `realism_r59_neutral_cast_brdf_release_60160`.

Yeni görselleri izlemek için immutable run adlarını aramayın. Sabit review
girişleri:

- [Blender current samples](ebis-blender/output/current_samples/contact_sheet.png)
- [Unreal current samples](unreal-ebis/output/current_samples/contact_sheet.png)
- [Gerçek–Blender–Unreal eşlenik QC](unreal-ebis/reports/qc/assets/real_blender_unreal_comparison.png)
- [Front-door/PBR release ve temizlik raporu](reports/qc/EBIS_FRONTDOOR_PBR_RELEASE_2026-07-30.md)
- [Realism-v2 Pass 1 actual-pixel/cleanup kaydı](reports/qc/EBIS_REALISM_V2_PASS1_2026-07-30.md)

Convention, atomik promotion ve geri alınabilir temizlik komutları
[`OUTPUT_CONVENTION.md`](OUTPUT_CONVENTION.md) içindedir. Eski pilot/hero/A-B
output ve generated QC görselleri temizlenmiştir; kaynak run olarak yalnız
iki kanonik release tutulur. `reports/qc/asset_ab/`,
`reports/qc/reference_forensics/` ve güncel MCP kanıtları ayrı, küçük audit
artefaktlarıdır.

## Güncel fiziksel sözleşme

- `cam-10 / Kamera 01 = camera_angled`;
  `cam-11 / Kamera 02 = camera_door`;
- iki `Ø400 mm` sıkıştırma tablası arasında düz nominal `180 mm` küp veya
  `Ø126 × 201 mm` silindir;
- sabit back/left/right yüzeyler mavi tırtıklı/hammertone boyalı sac;
- dışarıdan sağ menteşeli, dışa açılan dolu gri ön kapı ve kapıyla birlikte
  dönen gri servis kapağı;
- üst tabla hizasında back/left/right boyunca ince, tam boy opal U-difüzör;
- basılı kağıt altında tam/kısmi gizlenebilen ve tabla aralığında yalnız ucu
  görünebilen görsel RFID;
- bbox semantic union'dan değil görünür instance maskesinden; tam gizli/frame
  dışı RFID label almaz, `hard` ve `exclude` normal train'e girmez.

Blender V8 release 12/12 `PASS`, 32 fiziksel RFID ve 56 visible binary
maskedir; güncel BlenderMCP turu `163→163` nesne ve 1080p/128 spp OptiX
render ile `PASS`tir. Unreal r59 release 16/16 `PASS`, 70 visible + 70
isolated-amodal maskedir; dört kamera×şekil bbox hücresi gerçek hedefe
`≤0.06` ve güncel Epic MCP turu 9-call `PASS`tir. Her iki listener doğrulama
sonunda kapalıdır.

## Gerçek veri ve sınırlar

Gerçek LED referans/detection verisi yerinde tutulur:

```text
260312_EBIS_RFID_DATASET/210126_EBIS_TAG/ledli/
```

`REF*` IR/non-LED görüntüler renk hedefi değil, değişmeyen topoloji, kamera,
kapı ve occlusion kanıtıdır. Ölçülü CAD, kamera intrinsics/response curve,
cross-polarized mavi boya/çelik/beton PBR scan'i ve gerçek lux/IES henüz
yoktur. Bu nedenle iki release teknik/görsel QC adayıdır; fotogerçekçi dijital
ikiz veya YOLO kazancı sayılmaz.

İki haftalık uygulama/eğitim planları:

- [Blender planı](ebis-blender/docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)
- [Unreal planı](unreal-ebis/docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md)

Motorlar arası ve tren/tarım için çıkarımlar:
[`lessons_learned.md`](lessons_learned.md).
YOLO faydası yalnız capture-safe sabit gerçek test split'inde aynı nano
checkpoint/hyperparameter ve seed `17/29/43` ile yapılacak ablation sonrasında
iddia edilebilir.
