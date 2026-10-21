"""API v1 router — aggregates all v1 sub-routers."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.analyze import router as analyze_router
from app.api.v1.chat import router as chat_router
from app.api.v1.graph import router as graph_router
from app.api.v1.health import router as health_router
from app.api.v1.jobs import router as jobs_router
from app.api.v1.repositories import router as repositories_router

router = APIRouter(prefix="/api/v1")
router.include_router(health_router)
router.include_router(graph_router)
router.include_router(chat_router)
router.include_router(analyze_router)
router.include_router(repositories_router)
router.include_router(jobs_router)

