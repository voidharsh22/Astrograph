"""
Jobs API router — tracking background indexing job progress.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException

from app.storage.repository_store import get_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    summary="Get Indexing Job Status",
    description="Polls the background indexing pipeline progress percentage and current stage.",
)
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieve indexing job status by ID."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job
