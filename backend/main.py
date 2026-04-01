"""
Paladin Control Plane — FastAPI backend entrypoint.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse as StarletteJSONResponse
from starlette.responses import RedirectResponse as StarletteRedirectResponse

from backend.routes import auth, events, health, projects, threads
from backend.services.auth_service import is_authenticated

app = FastAPI(title="Paladin Control Plane", version="0.1.0")

# CORS — allow all origins (service is Tailscale-only; Cloudflare OAuth added later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Auth middleware — runs after CORS (added after CORS so it executes first on inbound)
class AuthMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        path = request.url.path

        # Always allow: auth routes, health check, static assets
        if (path.startswith("/auth/")
                or path == "/health"
                or path.startswith("/static/")):
            return await call_next(request)

        # Check authentication
        if not is_authenticated(request):
            if path.startswith("/api/"):
                return StarletteJSONResponse(
                    {"detail": "Not authenticated"},
                    status_code=401,
                )
            return StarletteRedirectResponse(
                url=f"/auth/login?next={request.url.path}",
            )

        return await call_next(request)

app.add_middleware(AuthMiddleware)

# Include routers
app.include_router(auth.router)
app.include_router(health.router)
app.include_router(projects.router)
app.include_router(events.router)
app.include_router(threads.router)

# Serve frontend static files
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
FRONTEND_DIR.mkdir(parents=True, exist_ok=True)

app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
async def serve_index():
    """Serve the SPA shell."""
    index = FRONTEND_DIR / "index.html"
    return FileResponse(str(index))
