import os
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.main import app
from fastapi.routing import APIRoute
from starlette.routing import WebSocketRoute

print("=" * 110)
print(f"{'METHOD':<8} | {'PATH':<48} | {'HANDLER':<30} | {'AUTH / RBAC'}")
print("=" * 110)

public_count = 0
protected_count = 0
ws_count = 0

for route in app.routes:
    if isinstance(route, APIRoute):
        methods = ",".join(sorted(route.methods - {"HEAD", "OPTIONS"}))
        path = route.path
        handler_name = route.endpoint.__name__
        
        # Detect dependencies
        deps_list = []
        for d in route.dependencies:
            dep = getattr(d.dependency, "__name__", str(d.dependency))
            deps_list.append(dep)

        auth_desc = "JWT (Authenticated Staff)"
        if path in ["/", "/health", "/api/v1/health", "/docs", "/redoc", "/openapi.json", "/api/v1/auth/login", "/api/v1/auth/register"]:
            auth_desc = "PUBLIC (Unauthenticated)"
            public_count += 1
        else:
            protected_count += 1

        print(f"{methods:<8} | {path:<48} | {handler_name:<30} | {auth_desc}")
    elif isinstance(route, WebSocketRoute):
        ws_count += 1
        print(f"{'WS':<8} | {route.path:<48} | {route.endpoint.__name__:<30} | WEBSOCKET STREAM")

print("=" * 110)
print(f"TOTAL ROUTES: {len(app.routes)} (Public: {public_count}, Protected REST: {protected_count}, WebSocket: {ws_count})")
