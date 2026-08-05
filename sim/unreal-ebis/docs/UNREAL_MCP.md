# Epic resmi Unreal MCP kullanımı

## Pin ve kapsam

UE 5.8.1 hazır Linux build’indeki Epic `ModelContextProtocol` ve `ToolsetRegistry` eklentileri kullanılır. Üçüncü taraf Unreal-MCP kurulmamıştır. Plugin hashleri `evidence/install/install_manifest.json` içindedir.

Sunucu:

```text
http://127.0.0.1:8000/mcp
protocol: 2025-11-25
transport: Streamable HTTP / JSON-RPC
```

Resmi server üç meta-tool sunar. Proje `ebis_toolset.EBISTools` toolset’ini ToolsetRegistry üzerinden kaydeder:

- `build_scene`
- `validate_scene`
- `get_status`
- `render_current`

Batch üretim doğrudan deterministik Python/config ile yapılır; MCP sahne kurma, inceleme, bounded render ve doğrulama katmanıdır.

## Başlat / doğrula / durdur

README’deki üç komutluk akışı kullanın. Başlangıçtan sonra şu kontrol yalnız loopback göstermelidir:

```bash
ss -ltnp 'sport = :8000'
```

`start_unreal_mcp.sh` mevcut aynı proje/editor PID’sini tekrar başlatmaz ve dolu portta durur. `stop_unreal_mcp.sh` PID command line’ı engine + proje ile eşleşmeden process’e sinyal göndermez.

## Güncel fiziksel r59 için kanıtlanan tur

[`20260730-neutral-cast-r59-verification-summary.json`](../evidence/mcp/20260730-neutral-cast-r59-verification-summary.json)
güncel fiziksel sahnenin pinidir;
[`20260730-neutral-cast-r59-roundtrip.json`](../evidence/mcp/20260730-neutral-cast-r59-roundtrip.json)
ham dokuz HTTP kaydını içerir:

1. initialize ve protocol negotiation;
2. initialized notification;
3. tools/list;
4. list/describe toolset;
5. standard release seed `60175`, angled/cylinder sahne build;
6. sahne validator ve status;
7. 1920×1080 RGB, depth, visible/amodal render.

Sonuç scene validator `ok=true`, `errors=[]`: bir `1920×1080` RGB, bir EXR
depth ve concrete + 2 RFID için üç visible + üç amodal instance maskesi
vardır. Test sonrası server/editor durdurulmuş ve port kapanmıştır. Eski
`realism_r5_*`, `official_mcp_*` ve front-door r56 kayıtları tarihsel
kanıttır; güncel r59 yerine kullanılmaz.

## Güvenlik ve EULA

Plugin deneysel ve auth’suzdur. `0.0.0.0`, LAN veya SSH reverse/public tunnel kullanmayın. Editor logu Unreal EULA kapsamında LLM’e aktarılan Licensed Technology sorumluluğunu ayrıca bildirir. Proje içeriğini yalnız kurumun onayladığı LLM/veri politikasına göre gönderin.

MCP PASS, CAD doğruluğu, fotogerçekçilik veya YOLO kazancı anlamına gelmez; yalnız resmi komut yolunun gerçek sahneyi sorgulayıp render edebildiğini kanıtlar.
