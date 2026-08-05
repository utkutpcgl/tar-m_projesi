# Unreal-EBIS detection teslim raporu

Date: 2026-07-30  
Engine: `5.8.1-56057345`  
Physical revision:
`front_hinged_door_blue_chamber_neutral_cast_brdf_pass8f_2026-07-30`

## Teslim kararı

Paket, RTX 3090 üzerinde tekrar üretilebilir RGB/instance detection release
candidate olarak devredilebilir. Production dataset, ölçülü dijital ikiz veya
kanıtlanmış YOLO iyileştirmesi değildir.

## Kanonik artefaktlar

- Sabit review:
  [contact sheet](../../output/current_samples/contact_sheet.png),
  [CURRENT.json](../../output/current_samples/CURRENT.json)
- Immutable release:
  [validation](../../output/realism_r59_neutral_cast_brdf_release_60160/validation.json),
  [QC sheet](../qc/assets/realism_r59_neutral_cast_brdf_release_60160_contact_sheet.png),
  [release manifest](../../evidence/release/realism_r59_neutral_cast_brdf_release_60160_manifest.json)
- Epic Unreal MCP:
  [round-trip](../../evidence/mcp/20260730-neutral-cast-r59-roundtrip.json),
  [summary](../../evidence/mcp/20260730-neutral-cast-r59-verification-summary.json),
  [1080p RGB](../../evidence/mcp/20260730-neutral-cast-r59-artifacts/raw/images/ebis_mcp_camera_angled_060175.png)
- Online asset:
  [provenance](../../docs/ASSET_PROVENANCE.md),
  [compact A/B](../qc/asset_ab/)
- Engine kıyası:
  [rapor](../qc/ENGINE_COMPARISON.md),
  [sheet](../qc/assets/real_blender_unreal_comparison.png)
- Ortak final rapor:
  [front-door/PBR release](../../../reports/qc/EBIS_FRONTDOOR_PBR_RELEASE_2026-07-30.md)

Release `ok=true`, 16/16; 8+8 kamera, 8+8 cube/cylinder, 70 visible +
70 isolated-amodal maske, `errors=[]`, `warnings=[]`. Dört camera×shape
concrete bbox hücresi gerçek hedefe mutlak `≤0.06` kapısındadır.

Epic MCP güncel standard seed `60175` üzerinde 9-call
build/validate/status/render `PASS`; 1080p RGB, EXR ve instance pass'leri
vardır. Tur sonunda editor durdu ve `127.0.0.1:8000` kapalıdır.

## Değişmeyen fiziksel sözleşme

- Sabit back/left/right yüzeyler mavi tırtıklı hammertone.
- Dolu gri ön kapı dışarıdan sağ menteşeli ve dışa açılır; servis kapağı
  leaf'e parent'tır.
- Sürgü rayı, glass leaf veya turuncu sabit machine hardware yoktur.
- `Ø400 mm` iki tabla arasında düz nominal `180 mm` cube veya
  `Ø126 × 201 mm` cylinder.
- Upper-platen kotunda back/left/right boyunca ince opal U-difüzör.
- Multipart hedefler tek `EBIS_INSTANCE`; bbox visible maskeden.
- `hard` yalnız açık ablation; `exclude` hiçbir train/val/test'e girmez.

## Materyal ve capture kararı

- Canonical concrete `procedural_cast_concrete_v2`, material revision `V27`.
- V24 hücresel ve V25 geniş bulut/mermer albedo noise'u reddedildi; V27 sabit
  nötr cast BRDF + 54–92 ölçekli küçük gözenek ve bounded edge/residue kullanır.
- LED/contact light proxy'lerinin görünür ama sahte keskin gölgeleri kapatıldı;
  r59 daha aydınlık yöndedir fakat kalan geniş düzlemsel bantlar henüz çözülmedi.
- ambientCG Concrete003 direct-UV gerilme/kontrast nedeniyle reddedildi.
- Poly Haven blue metal seam/çizik ve UV ölçeği nedeniyle reddedildi.
- r59 batch RGB/visible/amodal'dır; camera warp ile eşlenmemiş depth
  fail-closed kapalıdır. MCP'nin tek-kare EXR'i batch'e depth atfetmez.

## Sonraki mühendisin ilk iki günü

1. Current sheet ile gerçek LED/IR reference-forensics'i aç; somut
   yanlış-parça/yüzey/kadraj farklarını ledger'a yaz.
2. Engine, config, generator ve external asset hash'lerini pinle.
3. Fresh `60220..60235` pilotu `run_remote_release.sh` ile üret; validator ve
   actual-pixel 2×2 sheet'i kontrol et.
4. Materyal değişikliğinde same-seed tek-variable A/B; texture import olmuş
   diye değil final RGB düzgün diye kabul et.
5. Büyük batch'ten önce 100-kare QC; modelden önce capture-safe frozen real
   split ve shared Blender/Unreal experiment manifesti.

Detay:
[14 günlük plan](../../docs/INTENSIVE_14_DAY_ENGINEERING_PLAN.md),
[kullanıcı desteği](../../docs/USER_SUPPORT_AND_REVIEW.md),
[fiziksel spec](../../docs/PHYSICAL_REALISM_SPEC.md),
[YOLO planı](../../experiments/yolo/README.md).

## Çalışma kökleri

```text
Local source:
/home/utkutopcuoglu/Documents/utku/stajyerler/simulation/unreal-ebis

3090:
/home/ankaref/Documents/Projects/simulation/unreal-ebis

UE:
/home/ankaref/Documents/Projects/simulation/.tools/unreal-engine-5.8.1

DDC:
/media/ankaref/SSD-MNT-500GB/unreal-ddc
```

## Açık kabul kapıları

- ölçülü chamber/door/platen/camera-mount CAD;
- cross-polarized mavi boya/gri sac/çelik/concrete scan;
- cam-10/cam-11 intrinsics, response ve LED lux/IES;
- güncel same-seed determinism ve 100-kare iki kişilik QC;
- capture-safe frozen gerçek testte seed `17/29/43` YOLO nano ablation.

Unreal'ın Blender'ı geçtiği veya YOLO'ya faydalı olduğu bu kapılar olmadan
iddia edilmez.
