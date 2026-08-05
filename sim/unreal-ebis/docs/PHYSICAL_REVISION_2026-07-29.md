# Unreal EBİS fiziksel revizyonu — 2026-07-29

Bu revizyon kullanıcının son tarifini kanonik geometri kabul eder.
`output/pilot_release_v4`, `output/hero_release` ve `output/mcp_hero` tarihsel
pre-revision çıktılardır. Güncel kaynak RTX 3090 üzerinde
`output/realism_r5_full_58200` ile 16-kare RGB + benzersiz EXR depth +
visible/amodal instance release validation'ından geçti. Aynı kaynak resmî
Unreal MCP ile `output/mcp_realism_r5_58203` altında 1080p RGB+depth olarak
yeniden build/validate/render edildi. Bu teknik PASS'ler production,
fotogerçekçilik veya YOLO faydası kanıtı değildir.

## Uygulanan fiziksel düzeltmeler

- Basın artık açık erişim açıklığı, 90° açık metal çerçeveli büyük safety-glass
  pencereli kapı, dört taraflı siyah conta, menteşe ve kulpla kapılı bir kutudur.
  Cam background-only'dir; detection target değildir.
- Üç iç duvar koyu/gri, dielectric ve prosedürel albedo-roughness değişimli
  sacdır. Küçültülmüş/düzensiz sığ stipple geometrisi noktalı/girintili
  karakter için geçici proxy'dir. Mavi renk
  iç duvarlardan kaldırıldı ve dış çerçeve/kapı aksanıyla sınırlandı.
- Arka servis kapağı yuvarlatılmış siluet, katmanlı yüzey ve dört görünür vida
  başıyla modellenmiştir.
- 18 cm küp için alt/üst ana tabla çaplarının ikisi de 40 cm'dir (`2.22×`).
  Blender kontrol sahnesiyle aynı değer kullanılır; önceki 61/68.4 cm diskler
  kaldırılmıştır.
- LED büyük beyaz panel değildir. Üst tabla seviyesinde arka, sol ve sağ duvarı
  saran dar U-biçimli metal kanal + opal diffuser olarak altı ayrı mesh'tir.
  Üç fiziksel `RectLight` toplam lümeni kanal uzunluğuna yakın oranlarla
  paylaşır. Off-screen Lumen'in eksik diffuse dönüşü iki geniş ve düşük enerjili,
  config kontrollü bounce kartıyla açıkça modellenir; gizli point-light yoktur.
- Steel, powder coat ve iç sac materyallerine world-space albedo/roughness
  varyasyonu eklendi. Concrete V8 iki ölçekli aggregate tonu, değişken
  roughness ve mevcut aynı-instance pore/aggregate geometrisini kullanır.
- Opal emissive değeri azaltıldı; ışığı esas olarak üç lumen kontrollü alan
  ışığı üretir. Manual exposure, bloom, mm'ye yakın AO ve hafif vignette
  config'e taşındı. RGB için sekiz deterministic Lumen/TSR warm-up karesi
  kullanılır; mask/depth single-frame kalır.
- Unreal LDR PNG byte'ı korunarak yalnız RGB'ye audit edilebilir CCTV black
  pedestal/gamma uygulanır. `raw/images_pre_sensor`, config/script/output
  hashleri sensor manifestinde kayıtlıdır; mask ve bbox değişmez.

## Değişmeyen annotation sözleşmesi

Semantic aktör/tag yapısı değiştirilmedi. Beton gövde, pore ve aggregate
detayları hâlâ `EBIS_INSTANCE=concrete_00`; her RFID'nin dört parçası kendi
`EBIS_INSTANCE=rfid_NN` kimliğini paylaşır. Yeni kapı, duvar, dimple, vida,
tabla ve LED aktörlerinin semantic instance'ı yoktur. Böylece visible pass'te
gerçek occluder, amodal pass'te gizlenen non-target olarak davranırlar. RGB,
visible mask, amodal mask ve depth capture kodu değiştirilmedi.

## Ölçülmesi gereken belirsizlikler

Şimdiki sayılar fotoğrafa dayalı yaklaşık değerlerdir; CAD veya metreli çekim
değildir. En yüksek değerli kullanıcı girdileri şunlardır:

1. İç açıklığın en/boy/yüksekliği ve iki tabla çapı/kalınlığı (mm).
2. Alt tabla üst yüzeyinin zeminden yüksekliği ve iki tablanın merkez ekseni.
3. LED kanalının arka/yan uzunlukları, kanal/diffuser en-yüksekliği ve üst
   tabla alt yüzeyine göre düşey ofseti.
4. Kapı kanadı en/yükseklik/kalınlığı, menteşe tarafı ve iki kamera karesinde
   gerçek açık açı.
5. Servis kapağının en/yüksekliği, köşe yarıçapı, dört vida merkezi ve duvar
   referansına göre konumu.
6. Kameraların gerçek çözünürlük, yatay/dikey FOV veya checkerboard intrinsics,
   lens distortion ve white-balance/exposure davranışı.
7. Işık açık/kapalı aynı pozdan RAW veya mümkün olan en az sıkıştırılmış RGB;
   gri kart ve metal/beton yakın planları.

Bu ölçüler geldiğinde yalnız `configs/ebis_unreal_v1.json` güncellenmeli;
generator içinde bu fiziksel değerler tekrar hard-code edilmemelidir.

Primitive dimple'lar koyu ve çok sığ görsel proxy'dir; gerçek sacdaki concave
mikro-geometriyi fiziksel olarak tersine üretmez. Ölçekli macro/normal/roughness
scan geldiğinde proxy aktörleri tek bir tileable PBR materyalle değiştirmek hem
doğruluğu hem mask-render throughput'unu iyileştirir.

## Mevcut 3090 doğrulaması ve kalan kabul kapıları

`realism_r5_full_58200`; 16 × 1280×720 RGB, 16 geçerli/benzersiz EXR depth,
65 visible + 65 amodal maske, 7 standard + 7 hard_occlusion + 2 exclude ve
dört camera×shape concrete bbox hücresinde PASS verdi. Engine aşaması 49,184
saniyeydi. Sensör katmanı 16 ham Unreal PNG'sini byte-for-byte korur; kayıp
shadow detayı geri kazanılmış sayılmaz. Pinlenmiş kanıt
[`release manifest`](../evidence/release/realism_r5_full_58200_manifest.json)
altındadır.

Güncel resmî MCP turu protocol `2025-11-25` ile 9 çağrı/0 JSON-RPC error,
scene build/validate ve 1920×1080 RGB + benzersiz EXR depth üretiminde PASS
verdi. Endpoint yalnız `127.0.0.1:8000` idi ve tur sonunda kapatıldı; kanıt
[`MCP summary`](../evidence/mcp/realism_r5_verification_summary.json) altındadır.

Teknik release mevcut olsa da production/benchmark kabulü için kalan kapılar:

1. Aynı seed'i iki bağımsız editor run'ında RGB/depth/decoded-mask/YOLO piksel
   eşliğiyle yeniden doğrulamak.
2. Stratified 100 karede iki kişinin bağımsız geometri, materyal, ışık ve bbox
   QC'sini tamamlamak; blocker oranını raporlamak.
3. U-kanalın üç kolunu, kapı açıklığını, dört vidalı kapağı ve 40 cm fallback
   diskleri owner review'da gerçek referansla yan yana kabul etmek.
4. Fixed-exposure LED on/off, grey-card ve yüzey scan paketiyle geçici sensör,
   beton ve sac materyallerini ölçülmüş profile taşımak.
5. Frozen gerçek testte eşit bütçeli `R`, `R+B-1N`, `R+U-1N` üç-seed YOLO nano
   ablation'ını çalıştırmak; model sonucu olmadan engine üstünlüğü yazmamak.

Ham `raw/run_manifest.json` ve metadata içindeki `/home/ankaref/...` yolları
render provenance'ıdır. Taşınabilir tüketim output-relative `raw/`,
`partitions/` ve `manifests/` sözleşmesinden yapılır; güncel full run'daki tüm
mutlak kayıtların proje-relative dosya karşılığı teslim paketinde mevcuttur.
