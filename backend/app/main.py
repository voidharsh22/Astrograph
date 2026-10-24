"""
Astral Cartographer — FastAPI Application

Converts GitHub repositories into interactive 3D graph visualizations.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import router as v1_router
from app.config import settings


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — startup and shutdown hooks."""
    settings.clone_temp_dir.mkdir(parents=True, exist_ok=True)
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    from app.storage.database import init_db

    init_db()
    yield


app = FastAPI(
    title="Astral Cartographer API",
    description=(
        "Backend API for Astral Cartographer — ingests GitHub repositories "
        "and converts them into 3D graph visualizations (galaxies, solar systems, "
        "and celestial nodes)."
    ),
    version=settings.app_version,
    lifespan=lifespan,
)

# CORS — allow the 3D frontend (Vite dev server) to connect
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 4: tighten to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount versioned API
app.include_router(v1_router)


@app.get("/", include_in_schema=False)
async def root_redirect():
    """Redirect root path to interactive API docs."""
    from fastapi.responses import RedirectResponse

    return RedirectResponse(url="/docs")


# Mount built frontend at /app when available
from pathlib import Path
from fastapi.staticfiles import StaticFiles

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/app", StaticFiles(directory=str(FRONTEND_DIST), html=True), name="frontend")



