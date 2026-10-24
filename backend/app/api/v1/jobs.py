"""
Jobs API router — tracking background indexing job progress and streaming real-time telemetry.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from app.storage.repository_store import get_job

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get(
    "/{job_id}",
    summary="Get Indexing Job Status",
    description="Polls the background indexing pipeline progress percentage, stage, metrics, and logs.",
)
async def get_job_status(job_id: str) -> dict[str, Any]:
    """Retrieve indexing job status by ID."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")
    return job


@router.get(
    "/{job_id}/stream",
    summary="Stream Real-Time Job Progress (SSE)",
    description="Server-Sent Events endpoint streaming real-time repository analysis telemetry.",
)
async def stream_job_events(job_id: str):
    """Stream analysis events, stages, logs, and live graph metrics via SSE."""
    job = get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' not found")

    async def event_generator():
        last_progress = -1
        last_log_count = 0
        attempts = 0
        max_attempts = 600  # ~300 seconds max

        while attempts < max_attempts:
            current_job = get_job(job_id)
            if not current_job:
                yield f"data: {json.dumps({'error': 'Job not found', 'status': 'failed'})}\n\n"
                break

            current_status = current_job.get("status")
            current_progress = current_job.get("progress", 0)
            logs = current_job.get("logs", [])

            # Yield event on progress change, new logs, or at least every 2 seconds heartbeat
            if current_progress != last_progress or len(logs) != last_log_count or attempts % 4 == 0:
                payload = {
                    "jobId": current_job.get("id"),
                    "repositoryId": current_job.get("repository_id"),
                    "status": current_status,
                    "stage": current_job.get("stage"),
                    "progress": current_progress,
                    "message": current_job.get("message"),
                    "metrics": current_job.get("metrics", {}),
                    "logs": logs,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                last_progress = current_progress
                last_log_count = len(logs)

            if current_status in ("completed", "failed"):
                break

            await asyncio.sleep(0.5)
            attempts += 1

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
