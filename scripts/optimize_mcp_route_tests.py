"""Guarded MCP-only route-registration optimization for MCP connector tests."""
from pathlib import Path
p=Path("daemon/tests/test_mcp_connector.py")
s=p.read_text(encoding="utf-8")
anchor="from pathlib import Path\n"
assert s.count(anchor)==1
s=s.replace(anchor,anchor+"from unittest.mock import patch\nfrom fastapi import FastAPI\n",1)
anchor2="    app = build_app(storage, EventBus())\n"
assert s.count(anchor2)==1
replacement='''    # Exercise the real MCP router without compiling hundreds of unrelated REST
    # routes for every isolated test database. Production app remains unchanged.
    original_include_router = FastAPI.include_router

    def include_mcp_router_only(app, router, *args, **kwargs):
        if any(route.path.startswith("/mcp/") for route in router.routes):
            return original_include_router(app, router, *args, **kwargs)
        return None

    with patch.object(FastAPI, "include_router", include_mcp_router_only):
        app = build_app(storage, EventBus())
'''
p.write_text(s.replace(anchor2,replacement,1),encoding="utf-8")
print("APPLIED_TEST_ONLY")
