Status: READY
Planner depth: 0
Parent plan: (root plan)

Spot-Spray Sensor/Optics Proof-Baseline Adaptive Plan
1. Amaç ve karar

Bu parçanın amacı, kontrollü gerçek veri toplamadan önce dondurulmuş tek-kamera Basler RGB/C23 proof baseline’ını; görünür monochrome, NIR, snapshot multispectral, thermal ve depth seçeneklerine karşı aynı fiziksel görev zarfında sınayan, kaynakları ve hesapları yeniden üretilebilir bir sensör/optik araştırma kararı üretmektir.

Birincil çıktı:

docs/research/SPOT_SPRAY_SENSOR_OPTICS_SURVEY_V1.md

Destekleyen yeniden üretilebilir çıktılar:

configs/research/spot_spray_sensor_optics_survey_v1.yaml

scripts/derive_spot_spray_sensor_optics_survey_v1.py

docs/results/spot_spray_sensor_optics_survey_v1.json

tests/test_derive_spot_spray_sensor_optics_survey_v1.py

Mevcut planlama kararı:

Dondurulmuş 1× Basler a2A2464-77ucPRO + C23-0824-5M-P RGB modülü araştırmanın kontrolü ve varsayılan proof baseline’ı olarak korunacaktır.

Araştırma açık uçlu kamera araması değil, bu baseline’ı çürütme girişimidir.

Desk research ve analitik hesap tek başına hiçbir challenger’ı fiziksel baseline olarak yükseltemez.

Survey yalnız şu üç sonuçtan birini üretebilir:

RETAIN_RGB_BASELINE

BOUNDED_CHALLENGER_AB_ELIGIBLE

REPLAN_REQUIRED

BOUNDED_CHALLENGER_AB_ELIGIBLE, satın alma veya donanım seçimi değildir; yalnız sonraki ayrı onaylı eşlenmiş bench A/B’sine adaylık verir.

Hiçbir challenger tüm hard screen’leri ve açık bir trigger’ı birlikte geçmezse sonuç RETAIN_RGB_BASELINE olur.

Mevcut PRE_REAL_NOT_READY durumu değişmez. Fiziksel A–E receipt, target-rig performansı, field GO ve chemical GO bu planın çıktısı değildir.

Repository context, temiz main HEAD’i 509aeef8189dfa50dbcba973e871b0d41febe239 olarak sabitler. 

tarım-projesi-part-spot-spray-s…

2. Birincil darboğaz

Birincil darboğaz katalogda daha gelişmiş sensör bulmak değildir. Darboğaz, farklı modalitelerin bugün farklı FOV, raster, band örnekleme, çalışma mesafesi, shutter, filtre, interface, kamera adedi ve maliyet varsayımlarıyla anlatılmasıdır.

Bu plan önce karşılaştırma zeminini eşitler:

aynı minimum action-safe swath;

aynı 20 mm ilk servis sınıfı;

aynı 10 mm optik witness;

aynı native örnekleme ilkesi;

aynı 1,0 m/s, 170 µs, 15 Hz zarfı;

aynı çalışma mesafesi ve hood sınıfı;

aynı trigger ve fail-closed sınırları;

kamera gövdesi yerine gerekli tam sensing stack maliyeti.

Ancak bundan sonra bir modalite fiyat/performans challenger’ı sayılabilir.

3. Kapsam
3.1 Hedefler

Dondurulmuş V2 RGB baseline’ını tek sayısal otorite olarak yeniden üretmek.

Monochrome, NIR, multispectral, thermal ve depth için yalnız credible exact adayları taramak.

Her modalite için en fazla bir birincil ve bir yedek exact SKU tutmak.

Adayları aynı iki geometri modunda karşılaştırmak:

drop-in mechanical envelope;

matched-performance envelope.

Kamera, lens, filtre, pencere, emitter, sync, interface ve kamera adedini birlikte hesaplamak.

Her factual claim’i doğrudan tarihli bir kaynağa bağlamak.

Fact, calculation, inference ve hypothesis ayrımını görünür yapmak.

Eksik decisive evidence için en küçük bounded discovery adımını ve sonucu karara çeviren kuralı tanımlamak.

Baseline’ı koruyan veya challenger A/B’sini açan ölçülebilir trigger’ları dondurmak.

Survey sonucunu yerel, ağsız ve deterministik hesapla yeniden üretilebilir yapmak.

3.2 Kapsam dışı

Kamera, lens, filtre, emitter veya başka donanım satın almak.

Supplier siparişi, production quantity veya owner purchase approval üretmek.

Fiziksel rig kurmak veya A–F bench çalıştırmak.

GPU inference, model eğitimi, fine-tune veya yeni checkpoint karşılaştırması.

Gerçek veya sentetik görüntü üretmek.

Field readiness, product readiness veya certified ingress/ruggedness iddiası.

Nozul, deposition, doz, crop injury, kill-rate veya chemical fire kararı.

Hood/aydınlatma mimarisini yeniden sahiplenmek; bu plan yalnız sensörle zorunlu spectral/interface uyumluluğunu belirtir.

Vendor recognition, placement, hit-rate veya minimum-visible-size sayılarını precision, recall, F1 ya da crop safety ile eşitlemek.

Pushbroom hyperspectral, filter-wheel sequential multispectral, rolling-shutter consumer camera veya unsynchronized multi-camera mimarisini optimize etmek.

Arbitrary ağırlıklı tek bir “kamera skoru” üretmek.

4. Otorite ve değişiklik sınırı
4.1 Kaynak önceliği

Çelişki halinde aşağıdaki sıra uygulanır:

configs/deploy/spot_spray_capture_optimization_v2.yaml

docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md

docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md

docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md

docs/SPOT_SPRAY_DEPLOY_SOZLESMESI_V1.md

Yeni survey kaynakları ve hesapları

V1 tarihsel niyettir; V2 tarafından sayısallaştırılmış bir alan V1’den geri alınamaz.

4.2 Değiştirilemeyecek baseline alanları

Survey aşağıdaki alanları yeniden seçmez:

kamera kontrolü: Basler a2A2464-77ucPRO, order 109779;

lens: Basler C23-0824-5M-P, order 2200000568;

renkli global shutter ve fabrika IR-cut;

raw raster 2448×2048;

merkez native ROI 2048×2048, offset (200, 0);

dijital full-frame resize yasağı;

ground FOV 474–484 mm, nominal 480 mm;

adjustable working distance 520–590 mm;

aperture f/5,6;

fokus düzlemi ground üstü 55 mm;

test düzlemleri 0/55/110 mm;

exposure 170 µs;

baseline acquisition 15 Hz;

comparison speed 1,0 m/s;

local GSD gate ≤0,243902439 mm/px;

10 mm ≥41 px;

20 mm ≥82 px;

dış 64 px action abstain halkası;

minimum tek-bay action-safe swath 444,375 mm;

dedicated USB3 root;

haricî 12–24 VDC baseline güç yolu;

tek kamera / mevcut RTX 3090 / 15 Hz destek sınırı;

fiziksel A–E olmadan controlled capture yasağı;

chemical fire yasağı.

Survey mevcut V2’yi değiştirmek yerine challengers’ı bu kontrole karşı ölçer. Araştırma V2’de bir aritmetik veya kaynak çelişkisi bulursa bunu sessizce düzeltmez; sonucu REPLAN_REQUIRED yapar.

5. Fact, calculation ve inference sözleşmesi

Survey’de her önemli satır aşağıdaki claim türlerinden birini taşır:

FACT_T1: üretici veya standardın doğrudan teknik gerçeği.

FACT_T2: hakemli araştırmadan görevle ilgili gözlem.

FACT_T3: tarihli distributor fiyatı, stok veya teslim bilgisi.

CALC: source-bound girdilerden deterministik türetim.

INFERENCE: birden fazla fact/calc’e dayalı mühendislik yorumu.

HYPOTHESIS: ancak ileride fiziksel veya target-rig A/B ile test edilebilecek iddia.

UNKNOWN: kaynak tarafından desteklenmeyen alan.

UNKNOWN sıfır, varsayılan veya baseline değeriyle doldurulmaz.

Bir challenger’ın hard screen için gerekli alanlarından biri UNKNOWN ise:

aday fiyat/performans sıralamasına girmez;

SCREENED_OUT_MISSING_EVIDENCE olur;

eksik alan ve en küçük discovery adımı açıkça yazılır.

6. Kaynak ve citation kontratı
6.1 Kaynak seviyeleri
Tier 1 — teknik otorite

Hard spec için kabul edilen kaynaklar:

kamera üreticisi datasheet/manual;

sensör üreticisi datasheet ve spectral response/QE eğrisi;

lens üreticisi image-circle, focal length, MTF/resolution ve spectral transmission belgesi;

filtre/pencere üreticisi center wavelength, FWHM, blocking ve transmission belgesi;

emitter üreticisi spectral power ve pulse sınırı;

interface standardı veya üretici transport belgesi;

üreticinin exact model dimensional drawing ve trigger timing dokümanı.

Tier 2 — görev değeri

Modalitenin crop/weed ayrımı veya height/structure cue değeri için:

hakemli makale;

doğrudan teknik konferans yayını;

exact modality A/B’si içeren birincil araştırma.

Tier 2 çalışma şu alanları açıkça vermelidir:

görev;

crop/weed türleri;

sensing modality;

capture geometry veya çözünürlük;

split birimi;

karşılaştırılan kontrol;

metric semantiği;

yayın tarihi.

Aynı testte RGB kontrolü olmayan çalışma, challenger üstünlüğü değil yalnız yönsel hipotez sayılır.

Tier 3 — fiyat ve bulunabilirlik

üreticinin resmi shop sayfası;

yetkili distributor exact SKU sayfası;

tarihli non-binding quote.

Tier 3 teknik spec, Tier 1 yerine kullanılamaz.

Tier 4 — yönsel kaynak

vendor marketing;

blog;

reseller özeti;

ürün karşılaştırma sitesi;

sistem-level başarı iddiası.

Tier 4 yalnız candidate discovery veya context için kullanılabilir. Hard gate, modalite üstünlüğü veya ürün metriği kanıtlayamaz.

6.2 Doğrudan tarih zorunluluğu

Her source kaydı şu alanları taşır:

source_key

tier

publisher

title

url

document_version

published_or_released_on

checked_on

exact_model_or_scope

supported_claim_ids

archival_note

Kurallar:

Üretici dokümanında version/release date varsa ikisi de yazılır.

Web sayfası kendi tarihini vermiyorsa published_or_released_on: null, page_date_status: undated yazılır; yalnız checked_on kaydı sayfayı doğrudan tarihli teknik belgeye dönüştürmez.

Undated sayfa hard spec için ancak aynı üreticinin tarihli PDF/manual’iyle desteklenirse kullanılır.

Fiyat için checked_on zorunludur.

Search-result snippet, AI özeti veya URL başlığı kaynak değildir.

Bir citation yalnız desteklediği exact claim yanında bulunur.

“Güncel”, “stokta” veya “mevcut” ifadesi citation tarihinden ayrı yazılamaz.

Aynı spec farklı kaynaklarda çelişirse Tier 1 otorite korunur ve çelişki raporlanır.

6.3 Fiyat politikası

Ana karşılaştırma para birimi USD.

Kamu fiyatı landed quote değildir.

Tax, shipping, tariff, local stock ve FX ayrı belirsizliklerdir.

Challenger fiyat aralığı varsa challenger lehine alt sınır kullanılır.

Gerekli herhangi bir sensor-lane parçası fiyatlanmamışsa complete-stack price-performance kararı verilmez.

quote_required bir fiyat değildir.

Baseline’ın mevcut kamu kanıtı:

kamera 709 USD;

lens 136 USD;

camera+lens 845 USD;

tam proof modülü budgetary 3.115–6.545 USD, contingency ile 3.582–7.527 USD.

Yeni survey, eski fiyatları yeni tarihliymiş gibi sunmaz; mevcut V2 tarihini korur ve yeni challenger fiyatlarını kendi checked_on tarihleriyle gösterir.

7. Karşılaştırılacak minimum credible stack’ler
Modalite	Minimum credible stack	Baseline rolü	İlk disposition
RGB	1× Basler PRO + C23 + IR-cut	Kontrol ve action channel	BASELINE_FROZEN
Visible monochrome	1× global-shutter mono camera + tanımlı visible-pass/IR-block filter + matched lens	RGB replacement challenger	Koşullu
NIR-only	1× NIR-sensitive mono camera + exact bandpass + matched NIR illumination	RGB replacement; renk kaybeder	Safety kanıtına kadar diagnostic-only
RGB+NIR	Frozen RGB + 1× synchronized NIR lane	Additive spectral challenger	Koşullu
Snapshot multispectral	Tek anda band alan area-scan camera; görünür renk bilgisi yeterliyse replacement, değilse RGB’ye additive	Spectral challenger	Koşullu
Thermal	Frozen RGB + synchronized LWIR lane + thermal-compatible lens/window	Additive challenger	Thermal-only reddedildi
Depth	Aligned industrial RGB-D veya frozen RGB + hardware-synchronized on-device depth lane	Additive structure challenger	Koşullu
Passive host stereo	İki veya daha fazla camera + host disparity compute	GPU/compute kapsamını genişletir	Reddedildi
8. Açıkça reddedilen alternatifler

Aşağıdakiler survey candidate shortlist’ine alınmaz:

rolling-shutter camera;

shutter veya full-frame timing davranışı kaynaksız camera;

hardware trigger’sız sensing lane;

pushbroom hyperspectral;

filter-wheel veya sequential-band multispectral;

hareket sırasında bandlar arası zaman farkı belirsiz sensor;

yalnız demosaic edilmiş output raster’ı veren fakat raw per-band örnekleme düzenini açıklamayan multispectral sensor;

thermal-only action architecture;

host-side stereo veya yeni GPU yükü isteyen depth;

standart görünür cam arkasından LWIR çalıştığı varsayılan thermal stack;

IR-cut durumu veya spectral filter’i belirsiz visible/NIR camera;

focal length, image circle veya minimum working distance’i belirsiz lens;

Basler C23 lensin NIR, LWIR veya depth wavelength’inde otomatik uyumlu varsayılması;

consumer autofocus/auto exposure/auto white-balance yolu;

software upscale ile target pixel sayısını artırma;

vendor megapixel veya reconstructed band çözünürlüğünü bağımsız native sample sayısı gibi kullanma;

unsynchronized two-camera fusion;

yalnız camera-body fiyatıyla stack fiyatı kıyaslama;

recognition veya placement metriğini crop-safe track F1 yerine kullanma;

arbitrary weighted score ile farklı modalite metriklerini tek sayıya indirme.

9. Matched comparison kontratı

Her candidate iki ayrı modda hesaplanır.

9.1 Mode A — drop-in mechanical envelope

Candidate aşağıdakileri birlikte karşılamaya çalışır:

ground FOV 474–484 mm;

working distance 520–590 mm;

minimum 444,375 mm action-safe swath;

15 Hz;

170 µs veya daha kısa effective integration;

1,0 m/s;

hardware trigger;

mevcut hood içindeki spectral-compatible window;

minimum 20 mm action target;

minimum 10 mm optical witness.

Bu modu geçmeyen candidate, mevcut proof modülüne drop-in replacement değildir.

9.2 Mode B — matched-performance envelope

Drop-in modu geçmeyen candidate için şu soru hesaplanır:

candidate’ın native independent sampling’iyle GSD ≤0,243902439 mm/px sağlanırken tek camera’nın ulaşabildiği maksimum FOV nedir?

minimum 444,375 mm action-safe swath için kaç optical bay gerekir?

bay başına kaç camera body, lens, filter, emitter, interface lane ve window gerekir?

yeni WD veya hood geometry gerekir mi?

Mode B, mevcut proof baseline’ını değiştirme yetkisi vermez. Baseline’dan farklı mekanik zarf gerektiren candidate yalnız REPLAN_REQUIRED veya gelecekteki architecture challenger olabilir.

10. Deterministik hesap kontratı
10.1 Temel geometri

active_sensor_span_mm = active_pixels × pixel_pitch_um / 1000

Thin-lens pre-screen:

FOV_mm = sensor_span_mm × (working_distance_mm - focal_length_mm) / focal_length_mm

working_distance_mm = focal_length_mm × (1 + FOV_mm / sensor_span_mm)

required_focal_length_mm = sensor_span_mm × working_distance_mm / (FOV_mm + sensor_span_mm)

Thin-lens sonucu yalnız pre-screen’dir. Lens distorsiyonu, focal tolerance, chief-ray behavior, minimum focus ve spectral focus shift ayrı kaynak alanlarıdır.

10.2 GSD ve target pixel

GSD_mm_px = FOV_mm / independent_samples_across_FOV

target_px = target_size_mm / GSD_mm_px

Rapor en az şu boyutları taşır:

10 mm optical witness;

20 mm first service class.

5 mm yalnız re-plan diagnostic satırıdır; yeni servis vaadi değildir.

10.3 Baseline golden değerleri

Calculator aşağıdaki sonuçları V2 ile aynı üretmelidir:

active ROI span: 7,0656 mm;

474 mm FOV → 0,2314453125 mm/px;

480 mm FOV → 0,234375 mm/px;

484 mm FOV → 0,236328125 mm/px;

480 mm nominal FOV’da:

10 mm → 42,6667 px;

20 mm → 85,3333 px;

minimum local gates:

10 mm ≥41 px;

20 mm ≥82 px;

nominal 8,06 mm lens ve 480 mm FOV için WD yaklaşık 555,6143 mm;

focal tolerance ile required WD envelope yaklaşık 521,3314–588,1862 mm;

minimum action-safe width:

474 × 1920 / 2048 = 444,375 mm;

1,0 m/s × 170 µs = 0,17 mm physical smear;

FOV zarfında blur yaklaşık 0,719–0,735 px ve ≤0,75 px;

Bayer10 packed raw payload:

15 Hz → 629,1456 Mbit/s;

20 Hz → 838,8608 Mbit/s;

Bayer12 packed raw payload:

15 Hz → 754,97472 Mbit/s;

20 Hz → 1.006,63296 Mbit/s.

Bu golden değerlerden biri drift ederse challenger araştırması tamamlanmış sayılmaz.

10.4 Multispectral independent sample kuralı

Mosaic multispectral camera için vendor’ın reconstructed output raster’ı kullanılmaz.

Bir band, m_x × m_y tekrarlayan mosaic içinde bir native site alıyorsa:

independent_band_samples_x = floor(active_width_px / m_x)

independent_band_samples_y = floor(active_height_px / m_y)

band_GSD_x = FOV_x / independent_band_samples_x

Her decision-critical band için ayrı GSD ve 10/20 mm target pixel yazılır.

Demosaic, super-resolution veya spectral interpolation bağımsız sample sayısını artırmaz.

Bir multispectral camera raw band lattice’i açıklamıyorsa hard screen’i geçmez.

10.5 Action-safe FOV ve kamera sayısı

Baseline normalized edge exclusion:

edge_fraction_per_side = 64 / 2048 = 0,03125

Candidate için:

common_valid_FOV_mm = tüm gerekli kanalların kalibre ortak FOV kesişimi

safe_width_mm = common_valid_FOV_mm × (1 - 2 × candidate_edge_fraction)

Candidate daha büyük invalid border gerektiriyorsa büyük olan kullanılır.

Minimum overlap:

minimum_overlap_mm = 10

Maksimum bay pitch:

maximum_pitch_mm = 430

candidate_pitch_mm = min(430, safe_width_mm - 10)

bay_count = 1 + ceil(max(0, 444,375 - safe_width_mm) / candidate_pitch_mm)

total_camera_bodies = bay_count × camera_bodies_per_bay

Kurallar:

safe_width_mm ≤10 ise candidate geometry reddedilir.

Paired RGB+NIR, RGB+thermal veya RGB+depth stack’te common valid FOV kesişimi kullanılır.

Camera count yalnız optical bay sayısı değildir; toplam camera body ayrıca raporlanır.

Multi-camera compute kapasitesi varsayılmaz.

10.6 Motion, shutter ve zaman farkı

Global/snapshot exposure smear:

smear_mm = speed_m_s × 1000 × exposure_us × 10^-6

blur_px = smear_mm / GSD_mm_px

Rolling/readout distortion:

readout_displacement_px = speed_mm_s × frame_readout_s / GSD_mm_px

Cross-sensor veya cross-band skew:

temporal_skew_px = speed_mm_s × timestamp_skew_s / common_GSD_mm_px

Kurallar:

blur_px >0,75 ise replacement candidate elenir.

Full-frame timing davranışı bilinmiyorsa candidate elenir.

Sequential band acquisition elenir.

Additive multimodal lane hardware trigger ve deterministic timestamp sağlamalıdır.

Datasheet trigger desteği fiziksel sync PASS sayılmaz; yalnız bench eligibility verir.

Survey p95 ≤100 µs ve max ≤250 µs V2 zamanlama hedefleri altında beklenen spatial skew’u ayrı hesaplar.

10.7 Interface ve payload

raw_payload_Mbit_s = width × height × fps × effective_bits_per_pixel / 1.000.000

Birden fazla plane ayrı taşınıyorsa payload’lar toplanır.

required_link_with_headroom = raw_payload × 1,20

Hard screen:

required link, documented sustained payload sınırını geçemez;

her physical camera lane için dedicated root/controller veya ayrı network capacity gerekir;

compression yalnız lossless ve üretici tarafından deterministic timing ile belgelenmişse hesapta kullanılabilir;

host-side decompression veya fusion compute maliyeti survey dışında saklanamaz; compute_impact_unknown olarak işaretlenir;

yeni GPU gerektiren candidate bu parçanın proof baseline’ı olamaz.

10.8 Spectral throughput

Visible, NIR ve multispectral instrument throughput mümkün olduğunda şu zincirle raporlanır:

relative_signal ∝ ∫ emitter_SPD(λ) × lens_T(λ) × window_T(λ) × filter_T(λ) × sensor_QE(λ) dλ

Kurallar:

Scene reflectance ölçülmeden absolute crop/weed signal veya SNR iddiası yapılmaz.

Yalnız relative QE eğrisi varsa sonuç relative instrument sensitivity’dir.

Eksik lens, window veya filter transmission sıfır kayıpmış gibi alınmaz.

Visible mono camera mixed VIS+NIR açık bırakılmaz; exact visible-pass/IR-block state gerekir.

NIR candidate exact center wavelength, FWHM, blocking, emitter bandı ve lens/window transmission taşır.

Thermal, visible glass üzerinden hesaplanmaz.

Depth emitter wavelength’i ve window compatibility exact belirtilir.

10.9 Cost ve price-performance

Üç ayrı maliyet gösterilir:

camera_body_cost

sensor_lane_cost

complete_proof_stack_cost

sensor_lane_cost en az şunları içerir:

camera body;

lens;

mount/adapter;

optical filter;

spectral-compatible protective window;

required emitter veya active depth source;

sync/trigger accessory;

interface adapter/cable.

complete_proof_stack_cost ayrıca:

gerekli bay adedi;

bay başına camera body adedi;

calibration accessory;

modality-specific hood/window değişikliği;

ek controller/interface lane;

mevcut V2 common component allowance’larını içerir.

Çıktılar:

stack minimum/maximum USD;

cost completeness;

total camera body count;

action-safe swath;

USD / action-safe mm;

baseline’a karşı cost ratio;

unpriced required component listesi.

Gerekli parçası fiyatlanmamış stack için USD/action-safe mm veya “best price-performance” sonucu üretilmez.

Tek bir ağırlıklı skor yoktur. Karar hard gates, Pareto dominance, trigger ve uncertainty ile verilir.

11. Modaliteye özgü kararlar ve challenger trigger’ları
11.1 Visible monochrome
Resolved decision

Visible monochrome, tek-camera replacement olarak araştırılabilir. Aynı sensor ailesinin mono varyantı bulunabiliyorsa ilk tercih odur; sensor, geometry ve interface değişkenlerini azaltır.

Mono camera:

global shutter;

hardware trigger;

native sampling baseline kadar iyi;

exact visible-pass/IR-block filter;

matched lens;

fixed exposure/gain;

15 Hz;

drop-in WD/FOV;

dated QE veya spectral response

sağlamalıdır.

Trigger

Mono ancak aşağıdakilerden biri gerçekleşirse gelecekteki bench A/B’sine aday olur:

RGB baseline, passing hood/light zarfında 170 µs exposure ile Stage-D 20 dB SNR kapısını sensor-intrinsic nedenle geçemez;

RGB aynı SNR için exposure veya light power sınırını aşmak zorunda kalır;

source-bound instrument throughput hesabı, aynı visible bandında en az yaklaşık 1,5× signal veya 3 dB SNR potansiyeli gösterir;

target-rig error analysis, başarısızlığın renk ayrımından değil düşük-photon/noise rejiminden geldiğini gösterir.

Promotion boundary

Mono, renk kaybının crop-safety etkisini ölçen paired target-rig A/B olmadan RGB’nin yerine seçilemez.

11.2 NIR
Resolved decision

NIR’nin safety-preserving varsayılan mimarisi RGB+NIR iki-lane stack’tir.

NIR-only:

renk bilgisini kaldırır;

crop/weed ayrımının korunacağına dair mevcut exact kanıt yoktur;

bu nedenle diagnostic replacement olarak hesaplanır fakat proof baseline recommendation olamaz.

RGB+NIR:

frozen RGB action channel’ı korur;

exact NIR bandpass ve emitter kullanır;

iki camera body, iki lens/filter path ve cross-sensor registration gerektirir.

Trigger

NIR yalnız aşağıdakilerden biriyle bounded A/B’ye aday olur:

RGB A–E geçmesine rağmen wet leaf/soil, chlorophyll veya düşük visible contrast kaynaklı belirgin hata sınıfı kalır;

Tier-2 paired RGB-vs-RGB+NIR çalışma, comparable crop/weed görevinde modaliteye atfedilebilir kazanım gösterir;

exact NIR bandında paired physical sample CNR’si RGB failure binine karşı anlamlı avantaj gösterir;

NIR lane tüm geometry, sync, filter, payload ve cost screen’lerini geçer.

NIR, genel “bitkiler NIR’de iyi görünür” ifadesiyle açılmaz.

11.3 Snapshot multispectral
Resolved decision

Yalnız simultaneous area-scan snapshot multispectral credible’dır.

Aday:

exact band centers/FWHM;

simultaneous exposure;

raw per-band lattice;

independent per-band sample count;

hardware trigger;

full-frame timing;

spectral-compatible lens/window;

15 Hz;

drop-in veya açıkça hesaplanmış multi-bay geometry

sağlamalıdır.

Görünür renk bilgisi baseline safety channel’ını yeterince temsil etmiyorsa multispectral camera additive sayılır ve RGB korunur.

Trigger

Multispectral ancak:

NIR veya başka spectral band ihtiyacı gerçek failure mode ile bağlıysa;

en az bir Tier-2 çalışma aynı crop/weed görevinde paired RGB kontrolüne karşı destek veriyorsa;

decision-critical her bandın raw native örneklemesi açıkça hesaplanabiliyorsa;

reconstructed output resolution kullanılmadan geometry screen geçiyorsa;

complete stack cost ve camera count biliniyorsa

bounded A/B’ye aday olur.

Pushbroom, filter-wheel ve sequential-band seçenekler terminal olarak reddedilir.

11.4 Thermal
Resolved decision

Thermal-only action architecture reddedilmiştir. Credible stack:

frozen RGB;

synchronized LWIR camera;

thermal lens;

LWIR-compatible dedicated window;

exact integration/full-frame timing;

common FOV calibration.

Thermal channel için ayrıca:

spectral band;

native raster;

NETD;

minimum focus;

operating temperature/calibration behavior;

frame rate;

hardware trigger veya deterministic sync;

radiometric/non-radiometric state

kaydedilir.

Trigger

Thermal yalnız:

intended capture koşullarında görünür contrast’ın fiziksel olarak çöktüğü bir failure bin’i varsa;

plant/soil thermal contrast aynı koşulda ölçülmüşse;

thermal channel’ın spatial sampling ve temporal behavior’ı source-bound ise;

dedicated thermal window ve total stack cost hesaba katılmışsa;

RGB action channel korunuyorsa

bounded A/B’ye aday olur.

NETD tek başına crop/weed classification kazanımı değildir.

11.5 Depth
Resolved decision

Depth replacement değildir; RGB’ye auxiliary structure cue’dur.

Credible seçenek:

aligned industrial RGB-D camera; veya

frozen RGB’ye hardware-synchronized, camera-side depth üreten industrial ToF/structured-light lane.

Host stereo bu parçada reddedilir.

Aday için:

depth technology;

native depth raster;

minimum/max range;

accuracy ve precision’in 520–590 mm aralığındaki değeri;

ambient/sunlight sınırı;

emitter wavelength;

confidence/invalid-pixel semantics;

frame rate;

hardware sync;

latency;

common FOV;

window compatibility

zorunludur.

Decisive missing evidence

Repository mevcut durumda height/structure feature’ın kullanılabilmesi için gerekli maksimum depth p95 error’ı dondurmamıştır.

En küçük bounded discovery:

downstream feature owner, tek bir maximum_useful_depth_error_p95_mm ve minimum_valid_depth_fraction değeri dondurur;

değer source veya task geometry ile gerekçelendirilir;

bu değer gelmeden depth CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD kalır.

Karar kuralı:

exact candidate, dondurulan threshold’u 520–590 mm ve intended ambient zarfında geçmiyorsa elenir;

threshold yoksa depth price-performance winner ilan edilemez;

threshold geçse bile target-rig A/B olmadan RGB baseline’ın yerini alamaz.

12. Hard screen’ler

Her exact candidate aşağıdaki kapılardan geçer.

H1 — Identity

exact manufacturer;

exact model;

order/SKU;

sensor;

color/mono state;

filter state;

lens;

interface;

price source;

source date.

Eksik identity: fail.

H2 — Capture timing

global/snapshot veya source-bounded full-frame timing;

hardware trigger;

15 Hz;

effective integration ≤170 µs veya motion blur ≤0,75 px.

Rolling/unknown: fail.

H3 — Native geometry

Replacement action channel için:

20 mm ≥82 independent native samples;

10 mm ≥41 independent native samples;

minimum action-safe swath 444,375 mm veya exact bay-count sonucu.

Auxiliary channel için target pixels raporlanır; utility threshold yoksa conditional kalır.

H4 — Optical feasibility

image circle yeterli;

focal length/WD/FOV çözülebilir;

minimum focus yeterli;

lens resolving power/pixel pitch uyumlu;

spectral transmission uygun;

protective window uygun.

Unknown veya incompatible: fail.

H5 — Spectral definition

visible filter state;

NIR bandpass;

multispectral bands;

thermal band/window;

depth emitter/filter.

Undefined mixed spectrum: fail.

H6 — Interface

raw payload;

20% link headroom;

dedicated lane;

deterministic timestamps;

required cable/adapter.

Unknown sustained transport: fail.

H7 — Multi-sensor registration

Additive stack için:

common valid FOV;

hardware trigger;

timestamp semantics;

calibration path;

total camera bodies;

no hidden GPU requirement.

Unsynchronized veya host-compute-dependent: fail.

H8 — Cost completeness

required optical/sensor-lane components priced;

price dates present;

unpriced components explicit;

camera count applied.

Incomplete cost: technical row kalabilir, price-performance sıralamasından çıkar.

H9 — Evidence of task value

En az:

bir applicable Tier-2 source; veya

repository’de açık baseline failure trigger’ı

gerekir.

Yalnız vendor marketing: challenger A/B eligibility vermez.

H10 — Safety boundary

Candidate:

20 mm service class’ı sessizce düşüremez;

outer abstain’i kaldıramaz;

physical A–E’yi bypass edemez;

chemical fire iddiası üretemez;

RGB crop-safety channel’ını kanıtsız kaldıramaz.

Herhangi biri ihlal edilirse fail.

13. Karar algoritması

Her modality için:

En fazla iki exact candidate bulunur.

Source-tier ve date audit yapılır.

H1–H10 uygulanır.

Her hard fail terminal gerekçeyle yazılır.

Geçen candidate için Mode A ve Mode B hesaplanır.

Camera count, interface ve complete-stack cost hesaplanır.

Modalite-specific trigger değerlendirilir.

Trigger yoksa sonuç CONDITIONAL_CHALLENGER_NO_TRIGGER.

Trigger var fakat decisive spec/utility eksikse CONDITIONAL_CHALLENGER_MISSING_EVIDENCE.

Tüm screen ve trigger’lar geçerse BOUNDED_CHALLENGER_AB_ELIGIBLE.

Survey hiçbir candidate’ı doğrudan baseline’a promote etmez.

Hiçbir modality eligible değilse overall RETAIN_RGB_BASELINE.

V2’nin kendi baseline hesabı veya safety contract’ı çelişirse overall REPLAN_REQUIRED.

Baseline’ın “best price-performance” sayılması için weighted score gerekmez. Aşağıdaki Pareto kuralı yeterlidir:

challenger bütün hard gates’i geçmeli;

baseline’ın açık bir failure mode’unu hedeflemeli;

en az bir task-relevant capability’de source-bound avantaj göstermeli;

gerekli stack cost, camera count ve integration yükü tam görünür olmalı;

safety veya geometry’de kayıp yaratmamalı.

Bu koşullar yoksa daha fazla band, daha yüksek megapixel veya daha pahalı camera tek başına değer değildir.

14. Veri ve kontrol akışı

configs/deploy/spot_spray_capture_optimization_v2.yaml

→ baseline parser ve source SHA doğrulaması

→ configs/research/spot_spray_sensor_optics_survey_v1.yaml

→ source/candidate schema validation

→ deterministic geometry, blur, payload, camera-count ve cost calculations

→ docs/results/spot_spray_sensor_optics_survey_v1.json

→ insan-okunur claim/citation tablosu

→ docs/research/SPOT_SPRAY_SENSOR_OPTICS_SURVEY_V1.md

Kurallar:

Script internete çıkmaz.

Source retrieval manuel ve reviewable’dır.

Script yalnız local normalized inputs’i hesaplar.

Report sonuçları JSON’dan kopyalanır; ayrı elle hesap yapılmaz.

Result JSON baseline config SHA-256, survey config SHA-256 ve script SHA-256 taşır.

Report aynı üç hash’i metadata bölümünde gösterir.

Source değişince config ve result yeniden üretilmeden report güncel sayılmaz.

15. Candidate veri sözleşmesi

Her candidate kaydı en az şu alanları içerir:

Identity

candidate_id

modality

stack_role

manufacturer

model

order_number

status

Sensor

sensor_model

native_resolution_px

active_resolution_px

pixel_pitch_um

sensor_size_mm

sensor_format

shutter_type

frame_readout_us

maximum_frame_rate_hz

bit_depths

raw_formats

Spectrum

spectral_range_nm_or_um

band_centers

band_fwhm

raw_band_mosaic

IR_cut_state

filter_model

filter_transmission_source

lens_transmission_source

window_transmission_source

emitter_model

emitter_spectrum_source

Optics

lens_model

mount

image_circle

focal_length_mm

focal_tolerance

aperture

minimum_working_distance_mm

rated_pixel_pitch_or_MTF

drop_in_FOV_feasible

drop_in_WD_feasible

Timing/interface

hardware_trigger

timestamp_semantics

sync_output_or_input

interface

documented_sustained_payload

power

host_compute_required

Depth/thermal-specific

depth_accuracy_by_range

depth_precision_by_range

minimum_valid_depth_fraction

ambient_limit

emitter_wavelength

thermal_NETD

thermal_calibration_behavior

radiometric_state

Cost

camera_price

lens_price

filter_price

window_price

emitter_price

sync_interface_price

price_currency

price_checked_on

cost_completeness

Evidence

source_keys

tier1_complete

tier2_task_value_source

unknown_fields

screen_failures

trigger_ids

16. Target report yapısı

docs/research/SPOT_SPRAY_SENSOR_OPTICS_SURVEY_V1.md şu yapıyı kullanır:

Status ve evidence date

Yönetici kararı

Safety ve scope sınırı

V2 baseline source lock

Baseline golden calculations

Evidence hierarchy ve citation policy

Matched comparison method

Candidate shortlist

RGB baseline

Visible monochrome

NIR-only ve RGB+NIR

Snapshot multispectral

RGB+thermal

RGB+depth

FOV/GSD/target-pixel comparison

WD/lens/filter/window comparison

Blur/shutter/sync comparison

Interface/payload comparison

Camera-count ve action-safe swath comparison

Cost completeness ve price-performance

Hard-screen sonuçları

Challenger trigger ledger

Facts vs inferences

Uncertainties ve missing decisive evidence

Final disposition

Re-plan triggers

Source register

Reproduction commands

Yönetici özeti şu sınırı açıkça söylemelidir:

“Araştırma, mevcut baseline’ı fiziksel olarak geçirmiş değildir.”

“Survey satın alma veya controlled-capture readiness üretmez.”

“Eligible challenger varsa yalnız ayrı paired bench A/B’si önerilir.”

“Physical A–E, field GO ve chemical fire kapalıdır.”

17. Ordered implementation ledger
Paket 1 — Source ve baseline kilidi

Bağımlılık: yok.

 - [ ] Repository base’i main@509aeef8189dfa50dbcba973e871b0d41febe239 olarak kaydet.

 - [ ] configs/deploy/spot_spray_capture_optimization_v2.yaml dosyasının SHA-256’sını hesapla ve survey config’e pinle.

 - [ ] docs/CONTROLLED_CAPTURE_OPTIMIZATION_V2.md dosyasının SHA-256’sını hesapla ve report metadata’ya pinle.

 - [ ] docs/SPOT_SPRAY_PRODUCT_IMAGING_DECISION_V1.md ve docs/SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md identity’lerini kaydet.

 - [ ] V2 baseline alanlarını survey config’e elle kopyalamak yerine source config’den oku.

 - [ ] Survey overall state’ini PRE_REAL_RESEARCH_ONLY olarak dondur.

 - [ ] purchase_authorized, physical_ready, field_go, chemical_go ve gpu_work_performed alanlarını false olarak dondur.

Acceptance evidence:

Result JSON exact source paths ve SHA-256’ları taşır.

Baseline source eksik veya hash beklenmedikse script non-zero çıkar.

Report source lock olmadan üretilemez.

Paket 2 — Survey schema ve deterministic calculator

Bağımlılık: Paket 1.

 - [ ] configs/research/spot_spray_sensor_optics_survey_v1.yaml için schema version ve required fields tanımla.

 - [ ] Source register, candidate, stack, cost ve trigger yapılarını ekle.

 - [ ] scripts/derive_spot_spray_sensor_optics_survey_v1.py içinde yalnız pure deterministic hesaplar uygula.

 - [ ] Network erişimi, web scraping veya live price fetch ekleme.

 - [ ] Thin-lens pre-screen, GSD, target pixel, blur, payload, safe swath, bay count ve cost ratio hesaplarını uygula.

 - [ ] Multispectral raw per-band sampling hesabını reconstructed output’tan ayır.

 - [ ] Additive stack’te common-valid-FOV kesişimini uygula.

 - [ ] Missing decisive field’in candidate’ı fail-closed screen etmesini uygula.

 - [ ] Price incomplete candidate için price-performance sıralamasını engelle.

 - [ ] Result JSON’da input ve script hash’lerini üret.

Acceptance evidence:

Aynı input byte’ları aynı canonical JSON’u üretir.

Unknown alanlar sessiz default almaz.

Candidate screen status’ü gerekçe listesiyle üretilir.

Calculator hiçbir readiness veya purchase durumu üretemez.

Paket 3 — Baseline golden validation

Bağımlılık: Paket 2.

 - [ ] Baseline active span’i 7,0656 mm olarak yeniden üret.

 - [ ] 474/480/484 mm FOV için exact GSD sonuçlarını üret.

 - [ ] 10/20 mm target pixel sonuçlarını üret.

 - [ ] 8,06 mm nominal lens ve focal tolerance WD zarfını üret.

 - [ ] Minimum action-safe swath’i 444,375 mm olarak üret.

 - [ ] 1,0 m/s, 170 µs blur zarfını üret ve ≤0,75 px doğrula.

 - [ ] Bayer10/Bayer12 payload sonuçlarını 15/20 Hz için üret.

 - [ ] Existing V2 JSON ile aynı alanlarda numeric comparison yap.

 - [ ] Drift varsa challenger araştırmasını durdur ve REPLAN_REQUIRED üret.

Acceptance evidence:

Golden testler exact veya önceden tanımlı floating tolerance içinde geçer.

Report baseline tablosu result JSON’dan türetilir.

Baseline drift’i reportta warning değil terminal decision olur.

Paket 4 — Visible monochrome ve NIR discovery

Bağımlılık: Paket 1–3.

 - [ ] Baseline sensor ailesinin exact monochrome eşini önce araştır.

 - [ ] Aynı aile uygun değilse en fazla bir vendor-diverse mono backup seç.

 - [ ] Her mono candidate için QE/spectral response ve exact visible-pass/IR-block filter bul.

 - [ ] Mono candidate’ın C23 ile optical/spectral uyumluluğunu varsayma; source ile doğrula.

 - [ ] En fazla bir NIR camera primary ve bir backup seç.

 - [ ] NIR candidate için IR-cut removal state, bandpass, lens, window ve emitter zincirini tamamla.

 - [ ] NIR-only ve RGB+NIR stack’lerini ayrı camera-count/cost satırları olarak modelle.

 - [ ] Tier-2 crop/weed RGB-vs-mono veya RGB-vs-NIR evidence ara; comparable olmayan metric’i yönsel olarak etiketle.

 - [ ] Trigger yoksa candidate’ı CONDITIONAL bırak.

Acceptance evidence:

Her tutulan exact SKU H1–H10 sonucu taşır.

Mixed visible+NIR spectrum belirsiz kalmaz.

NIR stack’te filter/emitter/window maliyeti gizlenmez.

İkiden fazla SKU tutulmaz.

Paket 5 — Snapshot multispectral discovery

Bağımlılık: Paket 1–3.

 - [ ] Yalnız simultaneous area-scan snapshot adayları ara.

 - [ ] Pushbroom ve sequential filter-wheel adaylarını terminal reject listesine koy.

 - [ ] En fazla bir primary ve bir backup exact multispectral SKU seç.

 - [ ] Raw band lattice ve independent sample count’u Tier-1 kaynaktan çıkar.

 - [ ] Her decision-critical band için matched-FOV GSD ve 10/20 mm target pixel hesapla.

 - [ ] Vendor reconstructed raster’ını native band sampling olarak kullanma.

 - [ ] Visible color safety yeterliliğini belirle; belirsizse frozen RGB’yi additive stack’te koru.

 - [ ] Lens, window, filter ve band-specific transmission alanlarını tamamla.

 - [ ] Tier-2 paired RGB control evidence yoksa task-value trigger’ını kapalı bırak.

Acceptance evidence:

Her band için raw independent samples görünürdür.

Sequential capture candidate bulunmaz.

Camera-count sonucu per-band geometry’ye dayanır.

“Multispectral” adı tek başına promotion üretmez.

Paket 6 — Thermal ve depth discovery

Bağımlılık: Paket 1–3.

 - [ ] Thermal-only architecture’ı rejected olarak kaydet.

 - [ ] En fazla bir primary ve bir backup industrial LWIR candidate seç.

 - [ ] Thermal lens ve LWIR-compatible window’u ayrı exact parçalar olarak kaydet.

 - [ ] Native raster, NETD, frame timing, integration, focus, trigger ve price alanlarını tamamla.

 - [ ] RGB+thermal common FOV, camera count ve sync hesaplarını üret.

 - [ ] En fazla bir integrated RGB-D ve bir on-device depth backup seç.

 - [ ] Host-side stereo adaylarını rejected olarak kaydet.

 - [ ] Depth accuracy/precision’i exact 520–590 mm aralığında ara.

 - [ ] Ambient/sunlight, emitter wavelength, confidence semantics ve valid-pixel bilgisini kaydet.

 - [ ] Downstream depth utility threshold eksikse CONDITIONAL_CHALLENGER_MISSING_UTILITY_THRESHOLD üret.

Acceptance evidence:

Thermal stack standard visible glass üzerinden modellenmez.

Thermal-only winner sonucu üretilemez.

Depth hidden GPU workload taşımaz.

Depth threshold eksikliği açık ve terminal conditional state’tir.

Paket 7 — Matched geometry, interface ve camera-count tablosu

Bağımlılık: Paket 4–6.

 - [ ] Her candidate için Mode A drop-in hesaplarını üret.

 - [ ] Mode A başarısız candidate için Mode B matched-performance hesabını üret.

 - [ ] Her replacement action channel için 10/20 mm target pixels’i doğrula.

 - [ ] Her auxiliary channel için target pixels’i raporla fakat RGB action channel ile karıştırma.

 - [ ] Additive stack common valid FOV kesişimini hesapla.

 - [ ] Bay count, bodies per bay ve total camera bodies’i ayrı göster.

 - [ ] Raw payload ve 20% headroom hesapla.

 - [ ] Trigger/timestamp desteği olmayan candidate’ı ele.

 - [ ] Yeni GPU veya host fusion yükünü unknown/out-of-scope olarak görünür kıl.

 - [ ] Working-distance veya hood değişikliği gereken candidate’ı drop-in sayma.

Acceptance evidence:

Bütün candidate’lar aynı 444,375 mm required safe swath’a normalize edilmiştir.

Tek camera body fiyatı camera-count etkisini gizlemez.

Mode A ile Mode B sonuçları karışmaz.

Interface hesapları source-bound raw format kullanır.

Paket 8 — Complete-stack cost ve Pareto decision

Bağımlılık: Paket 7.

 - [ ] Camera body, lens, filter, window, emitter, sync ve interface maliyetlerini ayrı göster.

 - [ ] Additive modality için frozen RGB maliyetini stack’te koru.

 - [ ] Multi-bay candidate için parça adetlerini bay count ile çarp.

 - [ ] Dated lower-bound price ile challenger lehine hesap yap.

 - [ ] Required unpriced component varsa cost completeness’i false yap.

 - [ ] USD/action-safe mm ve baseline cost ratio’yu yalnız complete cost için üret.

 - [ ] Arbitrary weighted score ekleme.

 - [ ] Her candidate için Pareto sonucu üret:

dominated;

non-dominated but no trigger;

bounded A/B eligible;

re-plan required.

 - [ ] Daha pahalı modaliteyi yalnız “daha fazla bilgi” gerekçesiyle seçme.

Acceptance evidence:

Baseline ve challenger aynı cost boundary’de karşılaştırılır.

Missing price winner üretmez.

Range lower-bound challenger lehine uygulanır.

Decision her candidate için machine-readable gerekçe taşır.

Paket 9 — Trigger ve failure-attribution ledger

Bağımlılık: Paket 4–8.

 - [ ] Supply/EOL trigger’ını tanımla.

 - [ ] Sensor-intrinsic SNR trigger’ını tanımla.

 - [ ] <20 mm, >1 m/s ve >444,375 mm requirement-change trigger’larını tanımla.

 - [ ] Visible glare/contrast trigger’ını tanımla.

 - [ ] Spectral-separability trigger’ını tanımla.

 - [ ] Thermal-contrast trigger’ını tanımla.

 - [ ] Depth utility threshold trigger’ını tanımla.

 - [ ] Her trigger için required evidence, decision owner ve next bounded step’i yaz.

 - [ ] Model/data failure’ın otomatik sensor trigger’ı olmadığını yaz.

 - [ ] Hood/light failure’ın otomatik camera upgrade trigger’ı olmadığını yaz.

 - [ ] Trigger oluşmayan modality için research stopping rule uygula.

Acceptance evidence:

Her candidate’ın zero veya daha fazla explicit trigger ID’si vardır.

“Belki faydalı” trigger değildir.

Baseline failure mode ile challenger capability arasında izlenebilir bağ vardır.

Trigger’lar safety sınırını gevşetmez.

Paket 10 — Report assembly ve citation audit

Bağımlılık: Paket 1–9.

 - [ ] Target reportu tanımlı bölüm sırasıyla oluştur.

 - [ ] Her factual table cell’i bir source key’e bağla.

 - [ ] Her source için tier, version/release date ve checked date yaz.

 - [ ] Undated page’i açıkça undated işaretle.

 - [ ] Fact, calculation, inference ve hypothesis’i ayrı etiketle.

 - [ ] Report numeric tablolarını result JSON’dan al.

 - [ ] Decision summary ile JSON overall decision’ın exact eşleşmesini doğrula.

 - [ ] Bütün unknown decisive alanları uncertainty bölümünde listele.

 - [ ] Bütün rejected alternatifleri tek gerekçeyle kapat.

 - [ ] No-purchase, no-physical-ready, no-field-GO ve no-chemical-GO sınırını giriş ve sonuçta tekrar et.

Acceptance evidence:

Naked factual claim kalmaz.

Citation yalnız desteklediği claim yanında bulunur.

Reportta elle türetilmiş farklı numeric değer bulunmaz.

Final disposition üç izinli overall status’ten biridir.

Paket 11 — Exact validation ve freeze

Bağımlılık: Paket 10.

 - [ ] pytest -q tests/test_derive_spot_spray_sensor_optics_survey_v1.py çalıştır.

 - [ ] Calculator’ı exact input ve output yollarıyla çalıştır.

 - [ ] İkinci çalıştırmada result JSON’un byte-equivalent canonical content ürettiğini doğrula.

 - [ ] Baseline golden sonuçlarını V2 ile karşılaştır.

 - [ ] Her candidate için H1–H10 status’ünün dolu olduğunu doğrula.

 - [ ] Her modality’nin exact disposition taşıdığını doğrula.

 - [ ] Report metadata hash’lerinin current local files ile eşleştiğini doğrula.

 - [ ] Source date alanlarında blank olmadığını doğrula; gerçek undated kaynakları null/undated olarak doğrula.

 - [ ] Price incomplete candidate’ın winner olmadığını doğrula.

 - [ ] Thermal-only, host stereo, pushbroom ve rolling shutter’ın rejected olduğunu doğrula.

 - [ ] Overall decision ve challenger listesi arasında contradiction olmadığını doğrula.

 - [ ] Final diff’in yalnız planın izin verdiği survey/config/script/result/test dosyalarını değiştirdiğini doğrula.

Acceptance evidence:

Focused test suite PASS.

Deterministic rerun PASS.

Baseline drift yok.

Citation audit temiz.

Report ve JSON aynı kararı taşır.

Hiçbir readiness veya purchase claim’i açılmamıştır.

18. Exact test vakaları

Test suite en az şu vakaları içermelidir:

Baseline

active sensor span golden test;

FOV/GSD golden test;

target-pixel golden test;

WD/focal-tolerance golden test;

action-safe swath golden test;

blur golden test;

payload golden test.

Candidate screening

missing model identity → fail;

missing source date → source audit fail;

rolling shutter → fail;

unknown frame timing → fail;

missing hardware trigger → fail;

15 Hz altı → fail;

replacement 20 mm <82 px → fail;

missing lens image circle → fail;

undefined IR-cut/filter state → fail;

NIR without lens/window transmission → fail;

multispectral reconstructed raster used as raw samples → fail;

sequential bands → fail;

thermal with visible-glass window → fail;

depth requiring host stereo/GPU → fail;

additive stack without common FOV → fail;

raw payload without headroom → fail;

unpriced required component → no price ranking;

no Tier-2 evidence and no failure trigger → conditional, not eligible.

Camera count

baseline minimum safe width → one bay;

narrower candidate → exact multi-bay count;

additive two-body lane → total bodies equals bay count × two;

common FOV crop reduces safe width and may increase bay count;

safe width ≤10 mm → fail.

Decision

hard fail + strong marketing claim → screened out;

all hard gates + no trigger → conditional;

trigger + complete evidence → bounded A/B eligible;

baseline drift → re-plan;

no eligible candidate → retain RGB baseline;

price incomplete candidate cannot be best price-performance.

Safety

purchase_authorized cannot become true;

physical_ready cannot become true;

field_go cannot become true;

chemical_go cannot become true;

gpu_work_performed cannot become true;

target size cannot silently change below 20 mm;

outer abstain cannot be removed.

19. Edge cases ve failure behavior
19.1 Aynı modelin farklı sensor veya filter varyantları

Exact order/SKU ayrı candidate sayılır. Color, mono, IR-cut veya power varyantları bir satırda birleştirilmez.

19.2 Fiyat var, teknik belge yok

Candidate cost appendix’te görünebilir fakat hard screen ve ranking dışıdır.

19.3 Teknik belge var, fiyat yok

Candidate technical feasibility satırında kalır; “price-performance” sonucu verilmez.

19.4 Vendor full-resolution multispectral output veriyor

Raw band lattice yoksa output raster independent samples sayılmaz ve candidate elenir.

19.5 Lens visible’da uyumlu, NIR’de belirsiz

Visible MTF/spec NIR’ye taşınmaz. Exact NIR transmission/focus evidence yoksa candidate elenir.

19.6 Thermal camera yüksek NETD performansı veriyor ama düşük raster

Thermal auxiliary channel olarak raporlanır. RGB action geometry korunur. Thermal-only veya native target-pixel üstünlüğü iddia edilmez.

19.7 Depth camera RGB output da veriyor

RGB channel, frozen baseline geometry/shutter/quality kapılarını ayrı geçmeden integrated RGB-D camera replacement sayılmaz.

19.8 Additive sensor common FOV’u küçültüyor

Safe swath common calibrated intersection’tan hesaplanır; baseline RGB full FOV’u kullanılarak camera count avantajı yazılamaz.

19.9 Candidate farklı WD istiyor

Mode B’de hesaplanır; drop-in değildir. Hood/clearance etkisi açık re-plan trigger’ıdır.

19.10 Candidate daha kısa exposure gerektiriyor

Required light/emitter power ve SNR etkisi cost/uncertainty’ye eklenir. Exposure düşürmenin tek başına değer olduğu varsayılmaz.

19.11 Candidate daha düşük frame rate sunuyor

15 Hz karşılaştırma baseline’ını geçmiyorsa elenir. 12 Hz minimum observation teorisi, daha yavaş candidate’ı price-performance winner yapmaz.

19.12 Tier-2 çalışmalar farklı metric kullanıyor

Aynı metric’e dönüştürülmez. Çalışma yönsel evidence olur; survey kendi F1 veya crop-hit sayısını türetmez.

19.13 Supply blocker

Basler supply blocker exact dated quote/lead-time ile doğrulanır. Spekülasyon challenger trigger’ı değildir.

20. Material riskler ve kontroller
Risk 1 — Katalog “resolution” sayısı bağımsız bilgi içeriğini abartır

Kontrol:

raw independent sampling kullan;

multispectral per-band lattice’i ayrı hesapla;

reconstructed output’u native detail sayma.

Risk 2 — Spectral stack’in lens, filter ve window kaybı gizlenir

Kontrol:

bütün optical path parçalarını required yap;

missing transmission’ı unknown/fail say;

Basler C23 veya visible AR glass’ı farklı wavelength’e otomatik taşıma.

Risk 3 — Camera body fiyatı multi-camera maliyetini gizler

Kontrol:

required safe swath’tan bay count üret;

total camera bodies ve complete stack cost göster;

additive RGB lane’i maliyetten çıkarma.

Risk 4 — Literature gain doğrudan bu rig’e taşınır

Kontrol:

Tier-2 applicability alanlarını yaz;

geometry, task veya control farklıysa hypothesis say;

desk evidence ile physical promotion yapma.

Risk 5 — Baseline failure yanlışlıkla sensor’a atfedilir

Kontrol:

hood/light/lens/window/interface failure’larını ayrı sınıflandır;

bir sensor challenger yalnız sensor-intrinsic veya modality-specific failure trigger’ıyla açılır.

Risk 6 — Depth veya thermal için utility threshold icat edilir

Kontrol:

missing downstream threshold’u açık conditional state yap;

arbitrary accuracy veya NETD cutoff üretme;

en küçük owner-bound discovery adımını yaz.

Risk 7 — Fiyat ve availability hızla bayatlar

Kontrol:

her fiyat için checked date;

satın alma öncesi yeniden quote gerektiğini belirt;

eski fiyatı yalnız tarihsel karşılaştırma olarak koru.

Risk 8 — Survey V2’yi sessizce yeniden tasarlar

Kontrol:

V2 source hash pin;

baseline drift terminal REPLAN_REQUIRED;

new geometry yalnız Mode B challenger olarak kalır.

Risk 9 — Fazla aday araştırması karar değerini düşürür

Kontrol:

modality başına en fazla iki exact SKU;

hard fail sonrası alternatif katalog taramasını durdur;

yeni candidate yalnız explicit re-plan trigger’ıyla açılır.

21. Rollback

Bu plan fiziksel donanım değiştirmediği için rollback karar seviyesindedir.

Survey source veya arithmetic audit’i geçmezse overall recommendation frozen RGB baseline’a döner ve challenger sonuçları unsupported sayılır.

Candidate source sonradan invalid veya stale bulunursa candidate ranking’den çıkarılır; eksik alan başka modality’den tahmin edilmez.

Multispectral per-band sampling yanlış yorumlanmışsa reconstructed sonuçlar silinir ve raw lattice üzerinden yeniden hesaplanır.

Additive stack common FOV veya cost hesabı hatalıysa baseline recommendation korunur.

Bir challenger trigger’ı sonradan geçersizleşirse status CONDITIONALa döner.

V2 source değişirse eski survey result ve report stale olur; affected baseline ve bütün matched calculations yeniden üretilir.

Hiçbir rollback physical A–E kanıtını, target-rig performansını veya chemical authority’yi taşımaz.

22. Stopping rules

Araştırma aşağıdaki durumlarda durur:

Bir modality’de primary ve backup exact candidate hard screen’i geçemez.

Candidate için decisive Tier-1 spec iki bounded aramada bulunamaz.

Raw multispectral band sampling açıklanmıyorsa ek reseller taraması yapılmaz.

Thermal lens/window chain tamamlanamıyorsa thermal candidate kapatılır.

Depth utility threshold yoksa daha fazla depth SKU taranmaz.

Candidate 15 Hz, hardware trigger veya matched geometry’yi geçemiyorsa fiyat araştırması genişletilmez.

Required stack cost incomplete ise candidate best-price-performance tartışması durur.

Baseline tüm hard gates’i korur ve hiçbir trigger oluşmazsa modality search kapanır.

Her modality explicit disposition aldıktan sonra yeni “belki daha iyi” SKU eklenmez.

Overall RETAIN_RGB_BASELINE oluştuğunda purchase, physical bench veya GPU işine genişlenmez.

Overall BOUNDED_CHALLENGER_AB_ELIGIBLE oluştuğunda bu plan yalnız exact challenger A/B handoff’u ile kapanır; A/B’yi yürütmez.

Baseline source drift veya contract contradiction varsa challenger araştırması durur ve REPLAN_REQUIRED çıkar.

23. Re-plan trigger’ları

Aşağıdakilerden biri yeni plan gerektirir:

V2 baseline config veya safety contract değişir.

Minimum servis boyutu <20 mm olur.

Required action-safe swath >444,375 mm olur.

Araç hızı >1,0 m/s olur.

Exposure 170 µs altında kalmak zorlaşır.

Working distance 520–590 mm dışına çıkar.

RGB baseline exact physical A–E’de sensor-intrinsic nedenle kalıcı fail verir.

PRO/C23 EOL veya dated supply blocker oluşur.

Production environment certified ingress, washdown, dust, shock veya vibration ister.

Downstream track-action hata analizi spectral, thermal veya height cue eksikliğini causal olarak gösterir.

Depth feature owner useful p95 error ve valid-depth threshold dondurur.

New modality host/GPU architecture değişikliği gerektirir.

Lens/window spectral path mevcut hood mimarisiyle uyumsuz çıkar.

Multi-camera stack yeni compute veya timing contract’ı gerektirir.

Nozzle/crop-safety contract minimum action size’ı değiştirir.

24. Tamamlanma kriteri

Bu plan yalnız aşağıdakilerin tamamında tamamlanmış sayılır:

docs/research/SPOT_SPRAY_SENSOR_OPTICS_SURVEY_V1.md oluşturulmuştur.

Survey current V2 source hash’lerine bağlıdır.

Baseline golden calculations exact geçmiştir.

Monochrome, NIR, multispectral, thermal ve depth ayrı disposition taşır.

Her modality’de en fazla iki exact SKU vardır.

Her factual claim source tier, release/version date ve checked date taşır.

Her candidate matched FOV, GSD, target pixels, WD, blur, shutter, filter, interface, cost ve camera count sonucuna sahiptir veya neden hesaplanamadığı açıkça yazılmıştır.

Multispectral raw per-band sampling kullanılmıştır.

Additive stack common valid FOV ve total camera body count kullanmıştır.

Complete cost olmayan candidate price-performance winner değildir.

Her challenger’ın trigger’ı açık veya kapalıdır.

Depth utility threshold eksikse conditional state açıkça korunmuştur.

Result JSON, report ve calculator aynı overall decision’ı taşır.

Focused tests ve deterministic rerun geçmiştir.

Sonuç yalnız:

RETAIN_RGB_BASELINE,

BOUNDED_CHALLENGER_AB_ELIGIBLE, veya

REPLAN_REQUIRED
değerlerinden biridir.

Satın alma, physical READY, field GO, product GO ve chemical GO iddia edilmemiştir.

25. Beklenen karar yönü

Mevcut evidence boundary altında beklenen default sonuç RETAIN_RGB_BASELINEdır:

Basler RGB/C23 mevcut geometry, shutter, trigger, interface, power ve maliyet sözleşmesine bağlı tek tam tanımlı proof stack’tir.

Visible monochrome yalnız düşük-photon/SNR failure trigger’ıyla anlamlı replacement challenger’dır.

NIR safety-preserving biçimde additive iki-camera stack’tir.

Multispectral ancak simultaneous raw per-band sampling ve task-specific paired evidence ile credible’dır.

Thermal, RGB’yi koruyan additive sensing lane’dir ve dedicated optics/window gerektirir.

Depth, utility accuracy threshold dondurulmadan price-performance winner olamaz.

Daha fazla modalite, daha fazla kamera veya daha yüksek fiyat tek başına ürün değeri değildir.

Survey’nin görevi bu yönü doğrulamak değil, exact source ve matched calculation ile çürütmeye çalışmaktır. Çürütemezse tek-camera Basler RGB/C23 proof baseline değişmeden kalır.
