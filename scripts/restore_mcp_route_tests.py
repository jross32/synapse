from pathlib import Path
p=Path("daemon/tests/test_mcp_connector.py")
s=p.read_text(encoding="utf-8")
s=s.replace("from unittest.mock import patch\nfrom fastapi import FastAPI\n","",1)
old='''    # Exercise the real MCP router without compiling hundreds of unrelated REST
    # routes for every isolated test database. Production app remains unchanged.
    original_include_router = FastAPI.include_router

    def include_mcp_router_only(app, router, *args, **kwargs):
        if any(route.path.startswith("/mcp/") for route in router.routes):
            return original_include_router(app, router, *args, **kwargs)
        return None

    with patch.object(FastAPI, "include_router", include_mcp_router_only):
        app = build_app(storage, EventBus())
'''
assert s.count(old)==1
p.write_text(s.replace(old,"    app = build_app(storage, EventBus())\n",1),encoding="utf-8")
print("RESTORED")
