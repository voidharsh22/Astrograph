"""
Asynchronous indexing service orchestrating repository ingestion, safe extraction,
AST parsing, graph building, 3D coordinate calculation, and persistence.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
import shutil
from typing import Optional

from app.config import settings
from app.schemas.graph_schema import AstralGraph
from app.services.archive_extractor import extract_archive_safely
from app.services.cartographer import build_graph
from app.services.downloader import download_github_archive, extract_github_owner_and_repo
from app.services.graph_store import set_active_graph_store, GraphStore
from app.services.ingestor import ingest_repository, ingest_local_directory, cleanup_clone
from app.storage.repository_store import (
    complete_job,
    fail_job,
    save_graph_artifact,
    update_job_progress,
)

logger = logging.getLogger(__name__)


async def run_indexing_pipeline(
    repo_id: str,
    job_id: str,
    url: str,
    branch: str = "main",
    use_git_clone: bool = False,
) -> None:
    """Execute complete repository indexing pipeline in background."""
    logger.info("Starting indexing pipeline for repo %s (job %s)", repo_id, job_id)
    work_dir = settings.data_dir / "repositories" / repo_id
    work_dir.mkdir(parents=True, exist_ok=True)
    source_dir = work_dir / "source"
    zip_path = work_dir / "archive.zip"

    try:
        # Stage 1: Download / Ingestion
        update_job_progress(job_id, stage="downloading", progress=15)
        if use_git_clone:
            repo_data = await ingest_repository(url, branch)
        else:
            try:
                await asyncio.to_thread(download_github_archive, url, branch, zip_path)
                update_job_progress(job_id, stage="extracting", progress=35)
                await asyncio.to_thread(extract_archive_safely, zip_path, source_dir)
                zip_path.unlink(missing_ok=True)
                # Ingest the extracted directory
                repo_data = await asyncio.to_thread(ingest_local_directory, source_dir, url, branch)
            except Exception as dl_err:
                logger.warning("Zip download failed (%s); falling back to shallow git clone", dl_err)
                repo_data = await ingest_repository(url, branch)

        # Stage 2: Parsing & Graph Building
        update_job_progress(job_id, stage="building_graph", progress=65)
        graph = await build_graph(repo_data, include_ai=False)

        # Stage 3: Persistence & Active Store
        update_job_progress(job_id, stage="saving_artifacts", progress=90)
        save_graph_artifact(repo_id, graph)

        # Update active in-memory store so Q&A and cluster agents work immediately
        set_active_graph_store(GraphStore(graph))

        # Stage 4: Completion
        complete_job(job_id, repo_id)
        logger.info("Indexing pipeline successfully completed for repo %s", repo_id)

    except Exception as exc:
        logger.exception("Indexing pipeline failed for repo %s: %s", repo_id, exc)
        fail_job(job_id, repo_id, str(exc))
    finally:
        # Cleanup temporary files
        zip_path.unlink(missing_ok=True)
