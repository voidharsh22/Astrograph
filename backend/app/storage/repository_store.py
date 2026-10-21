"""
Data access layer for repositories, background indexing jobs, and graph artifacts.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import logging
from pathlib import Path
from typing import Any, Optional
import uuid

from app.config import settings
from app.schemas.graph_schema import AstralGraph
from app.storage.database import get_db

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_or_get_repository(
    url: str,
    owner: str,
    name: str,
    branch: str = "main",
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Create a new repository record or retrieve existing one by URL."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM repositories WHERE url = ?", (url,)
        ).fetchone()
        if row:
            return dict(row)

        repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        now = _now_iso()
        conn.execute(
            """
            INSERT INTO repositories (id, url, owner, name, branch, status, current_job_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', NULL, ?, ?)
            """,
            (repo_id, url, owner, name, branch, now, now),
        )
        return {
            "id": repo_id,
            "url": url,
            "owner": owner,
            "name": name,
            "branch": branch,
            "status": "pending",
            "current_job_id": None,
            "created_at": now,
            "updated_at": now,
            "error_message": None,
        }


def get_repository(repo_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Retrieve repository metadata by ID."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        return dict(row) if row else None


def list_repositories(limit: int = 50, offset: int = 0, db_path: Optional[Path] = None) -> list[dict[str, Any]]:
    """List all indexed repositories with pagination."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM repositories ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()
        return [dict(r) for r in rows]


def update_repository_status(
    repo_id: str,
    status: str,
    current_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Update status, current job ID, and error message for a repository."""
    now = _now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            UPDATE repositories
            SET status = ?, current_job_id = COALESCE(?, current_job_id),
                error_message = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, current_job_id, error_message, now, repo_id),
        )


def create_job(repo_id: str, db_path: Optional[Path] = None) -> dict[str, Any]:
    """Create a new background indexing job in 'queued' status."""
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    now = _now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, repository_id, status, stage, progress, started_at)
            VALUES (?, ?, 'queued', 'queued', 0, ?)
            """,
            (job_id, repo_id, now),
        )
        conn.execute(
            "UPDATE repositories SET status = 'queued', current_job_id = ?, updated_at = ? WHERE id = ?",
            (job_id, now, repo_id),
        )
    return {
        "id": job_id,
        "repository_id": repo_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "started_at": now,
        "completed_at": None,
        "error_message": None,
    }


def get_job(job_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Retrieve indexing job progress and stage by ID."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def update_job_progress(
    job_id: str,
    stage: str,
    progress: int,
    status: str = "running",
    db_path: Optional[Path] = None,
) -> None:
    """Update job stage, progress percentage, and status."""
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET stage = ?, progress = ?, status = ? WHERE id = ?",
            (stage, progress, status, job_id),
        )


def complete_job(job_id: str, repo_id: str, db_path: Optional[Path] = None) -> None:
    """Mark a job and repository as completed."""
    now = _now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'completed', stage = 'completed', progress = 100, completed_at = ? WHERE id = ?",
            (now, job_id),
        )
        conn.execute(
            "UPDATE repositories SET status = 'ready', updated_at = ? WHERE id = ?",
            (now, repo_id),
        )


def fail_job(job_id: str, repo_id: str, error_message: str, db_path: Optional[Path] = None) -> None:
    """Mark a job and repository as failed."""
    now = _now_iso()
    with get_db(db_path) as conn:
        conn.execute(
            "UPDATE jobs SET status = 'failed', stage = 'failed', error_message = ?, completed_at = ? WHERE id = ?",
            (error_message, now, job_id),
        )
        conn.execute(
            "UPDATE repositories SET status = 'failed', error_message = ?, updated_at = ? WHERE id = ?",
            (error_message, now, repo_id),
        )


def save_graph_artifact(repo_id: str, graph: AstralGraph) -> Path:
    """Persist full 3D AstralGraph JSON artifact to disk for instant multi-tenant reload."""
    target_dir = settings.data_dir / "repositories" / repo_id / "artifacts"
    target_dir.mkdir(parents=True, exist_ok=True)
    out_file = target_dir / "astral_graph.json"
    out_file.write_text(graph.model_dump_json(indent=2), encoding="utf-8")
    return out_file


def load_graph_artifact(repo_id: str) -> Optional[AstralGraph]:
    """Load cached 3D AstralGraph JSON artifact from disk if present."""
    target_file = settings.data_dir / "repositories" / repo_id / "artifacts" / "astral_graph.json"
    if not target_file.exists():
        return None
    try:
        raw = json.loads(target_file.read_text(encoding="utf-8"))
        return AstralGraph.model_validate(raw)
    except Exception as exc:
        logger.warning("Failed to load cached graph artifact for %s: %s", repo_id, exc)
        return None
