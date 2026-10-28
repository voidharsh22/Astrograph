"""Asynchronous indexing job orchestration service."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import logging
import os
from pathlib import Path
import shutil
import tempfile
import uuid
from typing import Callable, Optional

from app.config import settings
from app.services.archive_extractor import extract_archive_safely
from app.services.downloader import download_github_archive
from app.parsers.registry import analysis_paths
from app.services.analysis_pipeline import run_analysis
from app.storage.repository_store import (
    complete_analysis,
    update_job,
    update_repository_status,
)

logger = logging.getLogger(__name__)


def _safe_unlink(path: Optional[Path]) -> None:
    """Safely unlink a file, handling Windows file-lock and permission errors gracefully."""
    if not path:
        return
    try:
        if path.exists():
            try:
                import stat
                path.chmod(stat.S_IWRITE)
            except Exception:
                pass
            path.unlink(missing_ok=True)
    except (PermissionError, OSError) as exc:
        logger.warning("Could not unlink %s (file locked or syncing): %s", path, exc)
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.truncate(0)
        except Exception:
            pass


class IndexingService:
    """Manages background indexing job execution using a bounded thread pool."""

    def __init__(self, max_workers: Optional[int] = None) -> None:
        workers = max_workers or settings.max_concurrent_jobs
        self.executor = ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="astral-indexer",
        )

    def submit_job(
        self,
        repo_id: str,
        job_id: str,
        url: str,
        branch: str,
        archive_path: Optional[Path] = None,
        archive_fetcher: Optional[Callable[[Path], None]] = None,
    ) -> None:
        """Schedule a background indexing task.

        ``archive_fetcher`` (e.g. the private GitHub App download) replaces the public
        download step; everything after the archive exists is the shared pipeline.
        """
        self.executor.submit(
            self._execute_indexing_pipeline,
            repo_id,
            job_id,
            url,
            branch,
            archive_path,
            archive_fetcher,
        )

    def _execute_indexing_pipeline(
        self,
        repo_id: str,
        job_id: str,
        url: str,
        branch: str,
        archive_path: Optional[Path] = None,
        archive_fetcher: Optional[Callable[[Path], None]] = None,
    ) -> None:
        """Run the complete multi-stage analysis pipeline."""
        source_dir = settings.get_repo_source_dir(repo_id)
        artifact_dir = settings.get_repo_artifact_dir(repo_id)

        source_dir.mkdir(parents=True, exist_ok=True)
        artifact_dir.mkdir(parents=True, exist_ok=True)

        inventory_file = artifact_dir / "repository_inventory.json"
        analysis_files = analysis_paths(artifact_dir)
        code_graph_file = artifact_dir / "code_graph.json"
        graph_analytics_file = artifact_dir / "graph_analytics.json"

        temp_zip_file: Optional[Path] = None

        try:
            logger.info("Starting indexing job %s for repo %s", job_id, repo_id)
            update_job(job_id, status="running", started=True)
            update_repository_status(repo_id, status="running")

            # ----------------------------------------------------
            # Stage A: Downloading / Archive Preparation
            # ----------------------------------------------------
            if archive_path and archive_path.exists():
                temp_zip_file = archive_path
                update_job(job_id, stage="extracting", progress=20)
            else:
                update_job(job_id, stage="downloading", progress=10)
                temp_fd, temp_zip_str = tempfile.mkstemp(suffix=".zip", prefix="astral_dl_")
                os.close(temp_fd)
                temp_zip_file = Path(temp_zip_str)

                if archive_fetcher is not None:
                    archive_fetcher(temp_zip_file)
                else:
                    download_github_archive(
                        url=url,
                        branch=branch,
                        dest_path=temp_zip_file,
                    )

            # ----------------------------------------------------
            # Stage B: Extracting
            # ----------------------------------------------------
            update_job(job_id, stage="extracting", progress=25)
            # Invalidate cached in-memory graphs
            from app.services.repository_graph_cache import repository_graph_cache
            repository_graph_cache.invalidate(repo_id)

            # Clear any preexisting source files and stale artifacts
            shutil.rmtree(source_dir, ignore_errors=True)
            source_dir.mkdir(parents=True, exist_ok=True)

            for stale_file in [
                inventory_file,
                *analysis_files,
                code_graph_file,
                graph_analytics_file,
                artifact_dir / "cluster_summaries.json",
                artifact_dir / "workflows.json",
                artifact_dir / "ai_architecture.json",
                artifact_dir / "diagnostics.json",
            ]:
                _safe_unlink(stale_file)

            extract_archive_safely(
                zip_path=temp_zip_file,
                target_source_dir=source_dir,
            )

            # Delete temporary archive download promptly
            if temp_zip_file and temp_zip_file.exists():
                _safe_unlink(temp_zip_file)
                temp_zip_file = None

            # ----------------------------------------------------
            # Stages C-G: scan, parse, resolve, build graph, analytics, diagnostics
            # ----------------------------------------------------
            def _progress(stage: str, pct: int) -> None:
                update_job(job_id, stage=stage, progress=pct)

            diagnostics = run_analysis(
                source_dir=source_dir,
                artifact_dir=artifact_dir,
                progress=_progress,
                repository_id=repo_id,
            )

            for path, name in [
                (inventory_file, "repository inventory"),
                *[(f, f"{f.stem} artifact") for f in analysis_files],
                (code_graph_file, "code graph"),
                (graph_analytics_file, "graph analytics"),
            ]:
                if not path.exists():
                    raise RuntimeError(f"Expected artifact '{name}' was not created")

            graph_bytes = code_graph_file.read_bytes()
            graph_data = json.loads(graph_bytes)
            # One transaction: analysis record + job + repository status.
            complete_analysis(
                job_id=job_id,
                repo_id=repo_id,
                analysis_id=f"analysis_{uuid.uuid4().hex[:12]}",
                graph_summary=graph_data.get("summary", {}),
                graph_sha256=hashlib.sha256(graph_bytes).hexdigest(),
                diagnostics=diagnostics,
            )
            logger.info("Indexing job %s for repo %s completed successfully", job_id, repo_id)

        except Exception as err:
            logger.exception("Indexing job %s failed: %s", job_id, err)
            err_msg = str(err)
            update_job(
                job_id,
                status="failed",
                stage="failed",
                error_message=err_msg,
                completed=True,
            )
            update_repository_status(
                repo_id,
                status="failed",
                error_message=err_msg,
            )
        finally:
            if temp_zip_file and temp_zip_file.exists():
                temp_zip_file.unlink(missing_ok=True)

    def shutdown(self, wait: bool = False) -> None:
        """Shut down the thread pool."""
        self.executor.shutdown(wait=wait)


# Global indexing service singleton
indexing_service = IndexingService()
