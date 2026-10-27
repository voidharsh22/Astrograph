"""Astral Cartographer FastAPI application entrypoint."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
from typing import AsyncGenerator

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.routes import astral_ai, health, jobs, repositories
from app.config import settings
from app.services.indexing_service import indexing_service
from app.storage.database import init_db
from app.storage.repository_store import recover_interrupted_jobs

# Configure basic application logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("astral.api")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application startup and shutdown lifecycle."""
    logger.info("Initializing Astral Cartographer API...")
    settings.ensure_directories()
    init_db()

    # Mark any stale jobs from previous unexpected terminations as failed
    recovered = recover_interrupted_jobs()
    if recovered:
        logger.warning("Recovered %d interrupted indexing jobs upon startup", recovered)

    logger.info("Astral Cartographer backend initialized successfully.")
    yield

    logger.info("Shutting down Astral Cartographer API...")
    indexing_service.shutdown(wait=False)


app = FastAPI(
    title="Astral Cartographer API",
    description="Multi-language codebase intelligence platform scanning repositories and constructing code graphs.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1|\[::1\])(:\d+)?$",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes under /api
app.include_router(health.router, prefix="/api")
app.include_router(repositories.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(astral_ai.router, prefix="/api")


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Safely catch unhandled exceptions without leaking internal server paths or stack traces."""
    logger.exception("Unhandled server exception processing %s %s: %s", request.method, request.url.path, exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "An unexpected internal server error occurred"},
    )


@app.get("/", tags=["root"], summary="API Root")
def root_info() -> dict[str, str]:
    """Root info endpoint providing API documentation link."""
    return {
        "name": "Astral Cartographer API",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/api/health",
    }
