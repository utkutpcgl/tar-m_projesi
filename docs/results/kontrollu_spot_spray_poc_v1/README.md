# Kontrollü spot-spray PoC sonucu

Buradan başlayın:

- [6 sayfalık sade karar PDF'i](BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Açıklamalı detaylı PDF](DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Aranabilir detaylı rapor](DETAYLI_RAPOR.md)
- [Makine-okunur exact metrikler](metrics_summary.json)
- [Seçili self-sufficient görseller](figures/README.md)
- [Exact kamera/lens/ışık/hız/BOM baseline'ı](../../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md)
- [Fiziksel A–F rig kabul runbook'u](../../SPOT_SPRAY_RIG_ACCEPTANCE_RUNBOOK_V1.md)
- [Capture/annotation/split sözleşmesi](../../SPOT_SPRAY_DATA_CAPTURE_AND_ANNOTATION_V1.md)
- [Fail-closed fine-tune ve track-action hattı](../../SPOT_SPRAY_TARGET_RIG_MODEL_PIPELINE_V1.md)

Kısa karar: instance segmentation temel olarak kalıyor; mevcut model saha
ateşlemesi için **NO-GO**. Henüz gerçek target-rig sonucu yoktur. Tüketilmiş
PhenoBench UAV geliştirme panelinde ≥82 px frame-action F1 `%75,4`, tüketilmiş
tek-session BoniRob dış robot-view geliştirme panelinde `%9,0` oldu.
Seçilen model, eş bütçeli `80 V12 sentetik → 80 native ROSE robot crop'u`
deneyinin yönsel adayıdır; SHA-256
`3aba4b19b69455c0532edf0ff81622b2499fab376d7b5c8854b644027af73100` ile yalnız fine-tune
foundation'ıdır. Fiziksel A–E receipt, gerçek `capture_manifest_v1`, target-rig
fine-tune checkpoint'i ve track-action sonucu yoktur; bu yüzden pipeline
`PRE_REAL_NOT_READY` kalır. Sıradaki tek unblock, physical A–E PASS'tir;
ardından en az 3 tarla / 4 field-session, deterministic field split ve ayrı
track-action testi gelir. A–F yalnız nonchemical dry-marker açabilir; chemical
fire frozen V2'de unsupported ve kapalıdır.
