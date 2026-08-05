"""Register the bounded EBIS toolset when this project opens in Unreal Editor."""

import unreal


try:
    import ebis_toolset

    ebis_toolset.register()
    unreal.log("EBIS_MCP: project toolset registered")
except Exception as exc:  # startup evidence must remain visible in the editor log
    unreal.log_error(f"EBIS_MCP: toolset registration failed: {exc!r}")
