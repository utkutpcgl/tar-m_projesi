# Kontrollü spot-spray PoC sonucu

Buradan başlayın:

- [6 sayfalık sade karar PDF'i](BASLA_BURADAN_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Açıklamalı detaylı PDF](DETAYLI_KONTROLLU_SPOT_SPRAY_POC_V1.pdf)
- [Aranabilir detaylı rapor](DETAYLI_RAPOR.md)
- [Makine-okunur exact metrikler](metrics_summary.json)
- [Seçili self-sufficient görseller](figures/README.md)
- [Exact kamera/lens/ışık/hız/BOM baseline'ı](../../CONTROLLED_CAPTURE_OPTIMIZATION_V2.md)

Kısa karar: instance segmentation temel olarak kalıyor; mevcut model saha
ateşlemesi için **NO-GO**. Henüz gerçek target-rig sonucu yoktur. Tüketilmiş
PhenoBench UAV geliştirme panelinde ≥82 px frame-action F1 `%75,4`, tüketilmiş
tek-session BoniRob dış robot-view geliştirme panelinde `%9,0` oldu.
Seçilen model, eş bütçeli `80 V12 sentetik → 80 native ROSE robot crop'u`
deneyinin yönsel adayıdır; gerçek saha kanıtı değildir. Sıradaki
en etkili adım kontrollü kamera/aydınlatma rig'i ve aynı rig ile
field+session+track ayrık pilot veridir.
