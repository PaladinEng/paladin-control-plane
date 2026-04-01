"""
Paladin Control Plane — FastAPI backend entrypoint.
"""

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.routes import events, health, projects, threads

app = FastAPI(title="Paladin Control Plane", version="0.1.0")

# CORS — allow all origins (service is Tailscale-only; Cloudflare OAuth added later)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
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
