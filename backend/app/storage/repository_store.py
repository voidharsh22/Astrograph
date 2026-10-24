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
    user_id: Optional[str] = None,
    user_email: Optional[str] = None,
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
            INSERT INTO repositories (id, url, owner, name, branch, status, user_id, user_email, current_job_id, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 'pending', ?, ?, NULL, ?, ?)
            """,
            (repo_id, url, owner, name, branch, user_id or "", user_email or "", now, now),
        )
        return {
            "id": repo_id,
            "url": url,
            "owner": owner,
            "name": name,
            "branch": branch,
            "status": "pending",
            "user_id": user_id or "",
            "user_email": user_email or "",
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


def list_repositories(
    user_id: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """List indexed repositories with pagination, optionally isolated by user_id."""
    with get_db(db_path) as conn:
        if user_id:
            rows = conn.execute(
                "SELECT * FROM repositories WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (user_id, limit, offset),
            ).fetchall()
        else:
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
    initial_metrics = {
        "filesDiscovered": None,
        "filesParsed": None,
        "symbolsExtracted": None,
        "dependencyEdges": None,
        "graphNodes": None,
        "communitiesDetected": None,
        "stageDuration": None,
    }
    initial_logs = [
        {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": "INFO",
            "text": "Repository indexing queued in celestial pipeline.",
        }
    ]
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO jobs (id, repository_id, status, stage, progress, message, metrics_json, logs_json, started_at)
            VALUES (?, ?, 'queued', 'ingestion', 5, 'Validating repository...', ?, ?, ?)
            """,
            (job_id, repo_id, json.dumps(initial_metrics), json.dumps(initial_logs), now),
        )
        conn.execute(
            "UPDATE repositories SET status = 'queued', current_job_id = ?, updated_at = ? WHERE id = ?",
            (job_id, now, repo_id),
        )
    return {
        "id": job_id,
        "repository_id": repo_id,
        "status": "queued",
        "stage": "ingestion",
        "progress": 5,
        "message": "Validating repository...",
        "metrics": initial_metrics,
        "logs": initial_logs,
        "started_at": now,
        "completed_at": None,
        "error_message": None,
    }


def get_job(job_id: str, db_path: Optional[Path] = None) -> Optional[dict[str, Any]]:
    """Retrieve indexing job progress, stage, metrics, and logs by ID."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        if not row:
            return None
        data = dict(row)
        try:
            data["metrics"] = json.loads(data.get("metrics_json") or "{}")
        except Exception:
            data["metrics"] = {}
        try:
            data["logs"] = json.loads(data.get("logs_json") or "[]")
        except Exception:
            data["logs"] = []
        return data


def update_job_progress(
    job_id: str,
    stage: str,
    progress: int,
    status: str = "running",
    message: Optional[str] = None,
    metrics: Optional[dict[str, Any]] = None,
    log_entry: Optional[dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Update job stage, progress percentage, status, telemetry metrics, and logs."""
    with get_db(db_path) as conn:
        # Load existing metrics and logs to merge cleanly
        row = conn.execute("SELECT metrics_json, logs_json, message FROM jobs WHERE id = ?", (job_id,)).fetchone()
        existing_metrics = {}
        existing_logs = []
        current_msg = message or ""
        if row:
            try:
                existing_metrics = json.loads(row["metrics_json"] or "{}")
            except Exception:
                existing_metrics = {}
            try:
                existing_logs = json.loads(row["logs_json"] or "[]")
            except Exception:
                existing_logs = []
            if not message and row["message"]:
                current_msg = row["message"]

        if metrics:
            existing_metrics.update(metrics)

        if log_entry:
            existing_logs.append(log_entry)
            # Cap log history to most recent 250 entries to prevent database bloat
            if len(existing_logs) > 250:
                existing_logs = existing_logs[-250:]

        conn.execute(
            """
            UPDATE jobs
            SET stage = ?, progress = ?, status = ?, message = ?, metrics_json = ?, logs_json = ?
            WHERE id = ?
            """,
            (
                stage,
                progress,
                status,
                current_msg,
                json.dumps(existing_metrics),
                json.dumps(existing_logs),
                job_id,
            ),
        )


def complete_job(
    job_id: str,
    repo_id: str,
    metrics: Optional[dict[str, Any]] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Mark a job and repository as completed."""
    now = _now_iso()
    with get_db(db_path) as conn:
        row = conn.execute("SELECT metrics_json, logs_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        existing_metrics = {}
        existing_logs = []
        if row:
            try:
                existing_metrics = json.loads(row["metrics_json"] or "{}")
            except Exception:
                pass
            try:
                existing_logs = json.loads(row["logs_json"] or "[]")
            except Exception:
                pass

        if metrics:
            existing_metrics.update(metrics)

        completion_log = {
            "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
            "level": "READY",
            "text": "Your code universe is ready. Launching interactive galaxy.",
        }
        existing_logs.append(completion_log)

        conn.execute(
            """
            UPDATE jobs
            SET status = 'completed', stage = 'workspace_ready', progress = 100,
                message = 'Your code universe is ready.',
                metrics_json = ?, logs_json = ?, completed_at = ?
            WHERE id = ?
            """,
            (json.dumps(existing_metrics), json.dumps(existing_logs), now, job_id),
        )
        conn.execute(
            "UPDATE repositories SET status = 'ready', updated_at = ? WHERE id = ?",
            (now, repo_id),
        )


def fail_job(job_id: str, repo_id: str, error_message: str, db_path: Optional[Path] = None) -> None:
    """Mark a job and repository as failed."""
    now = _now_iso()
    fail_log = {
        "timestamp": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "level": "ERROR",
        "text": f"Pipeline halted: {error_message}",
    }
    with get_db(db_path) as conn:
        row = conn.execute("SELECT logs_json FROM jobs WHERE id = ?", (job_id,)).fetchone()
        existing_logs = []
        if row:
            try:
                existing_logs = json.loads(row["logs_json"] or "[]")
            except Exception:
                pass
        existing_logs.append(fail_log)

        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', stage = 'failed', message = ?, error_message = ?, logs_json = ?, completed_at = ?
            WHERE id = ?
            """,
            (f"Analysis failed: {error_message}", error_message, json.dumps(existing_logs), now, job_id),
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
