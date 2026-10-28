"""Repository and job record persistence operations."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from app.storage.database import get_db


def current_utc_iso() -> str:
    """Return current UTC timestamp in ISO 8601 format."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RepositoryRecord:
    """Persistent database model for an indexed repository."""

    id: str
    url: str
    owner: str
    name: str
    branch: str
    status: str  # "queued", "running", "completed", "failed"
    current_job_id: Optional[str]
    created_at: str
    updated_at: str
    workspace_dir: str
    artifact_dir: str
    error_message: Optional[str] = None
    # GitHub user id that imported this repository via the GitHub App; NULL = public import (unrestricted).
    owner_github_user_id: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class JobRecord:
    """Persistent database model for an asynchronous repository indexing job."""

    id: str
    repository_id: str
    status: str  # "queued", "running", "completed", "failed"
    stage: str  # "queued", "downloading", "extracting", "scanning", "parsing_python", "parsing_javascript", "building_graph", "saving_results", "completed", "failed"
    progress: int  # 0 to 100
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    error_message: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def create_repository(
    repo_id: str,
    url: str,
    owner: str,
    name: str,
    branch: str,
    workspace_dir: str,
    artifact_dir: str,
    status: str = "queued",
    current_job_id: Optional[str] = None,
    db_path: Optional[Path] = None,
    owner_github_user_id: Optional[int] = None,
) -> RepositoryRecord:
    """Insert a new repository record."""
    now = current_utc_iso()
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO repositories (
                id, url, owner, name, branch, status, current_job_id,
                created_at, updated_at, workspace_dir, artifact_dir, error_message,
                owner_github_user_id
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                repo_id,
                url,
                owner,
                name,
                branch,
                status,
                current_job_id,
                now,
                now,
                workspace_dir,
                artifact_dir,
                None,
                owner_github_user_id,
            ),
        )

    return RepositoryRecord(
        id=repo_id,
        url=url,
        owner=owner,
        name=name,
        branch=branch,
        status=status,
        current_job_id=current_job_id,
        created_at=now,
        updated_at=now,
        workspace_dir=workspace_dir,
        artifact_dir=artifact_dir,
        error_message=None,
        owner_github_user_id=owner_github_user_id,
    )


def get_repository(
    repo_id: str,
    db_path: Optional[Path] = None,
) -> Optional[RepositoryRecord]:
    """Retrieve repository by unique ID, canonical URL, or owner/name slug."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM repositories WHERE id = ?",
            (repo_id,),
        )
        row = cursor.fetchone()
        if row:
            return RepositoryRecord(**dict(row))

        # Check by exact canonical URL
        cursor = conn.execute(
            "SELECT * FROM repositories WHERE url = ? ORDER BY created_at DESC LIMIT 1",
            (repo_id,),
        )
        row = cursor.fetchone()
        if row:
            return RepositoryRecord(**dict(row))

        # Check by clean URL or owner/name
        clean_target = repo_id.rstrip("/").removesuffix(".git")
        cursor = conn.execute(
            """
            SELECT * FROM repositories 
            WHERE url LIKE ? 
               OR (owner || '/' || name) = ? 
               OR name = ? 
            ORDER BY created_at DESC LIMIT 1
            """,
            (f"%{clean_target}%", clean_target, clean_target),
        )
        row = cursor.fetchone()
        if row:
            return RepositoryRecord(**dict(row))
        return None


def get_repository_by_url_and_branch(
    url: str,
    branch: str,
    db_path: Optional[Path] = None,
    owner_github_user_id: Optional[int] = None,
) -> Optional[RepositoryRecord]:
    """Look up an existing repository record by canonical URL and branch.

    Public imports (owner_github_user_id=None) only ever match public records, so a URL import can
    never attach to, or re-queue, a private GitHub App import of the same repository.
    """
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM repositories WHERE url = ? AND branch = ? AND owner_github_user_id IS ?",
            (url, branch, owner_github_user_id),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return RepositoryRecord(**dict(row))


def list_repositories(
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
    viewer_github_user_id: Optional[int] = None,
) -> list[RepositoryRecord]:
    """List indexed repositories with pagination.

    Private (GitHub App) repositories are listed only for the GitHub user that imported them.
    """
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM repositories WHERE owner_github_user_id IS NULL "
            "OR owner_github_user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (viewer_github_user_id, limit, offset),
        )
        rows = cursor.fetchall()
        return [RepositoryRecord(**dict(r)) for r in rows]


def update_repository_status(
    repo_id: str,
    status: str,
    current_job_id: Optional[str] = None,
    error_message: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> None:
    """Update repository status, active job ID, and error message."""
    now = current_utc_iso()
    with get_db(db_path) as conn:
        if current_job_id is not None:
            conn.execute(
                """
                UPDATE repositories
                SET status = ?, current_job_id = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, current_job_id, error_message, now, repo_id),
            )
        else:
            conn.execute(
                """
                UPDATE repositories
                SET status = ?, error_message = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error_message, now, repo_id),
            )


def create_job(
    job_id: str,
    repo_id: str,
    db_path: Optional[Path] = None,
) -> JobRecord:
    """Create a new queued indexing job record."""
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO indexing_jobs (
                id, repository_id, status, stage, progress, started_at, completed_at, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (job_id, repo_id, "queued", "queued", 0, None, None, None),
        )

    return JobRecord(
        id=job_id,
        repository_id=repo_id,
        status="queued",
        stage="queued",
        progress=0,
        started_at=None,
        completed_at=None,
        error_message=None,
    )


def get_job(
    job_id: str,
    db_path: Optional[Path] = None,
) -> Optional[JobRecord]:
    """Retrieve job by unique ID."""
    with get_db(db_path) as conn:
        cursor = conn.execute(
            "SELECT * FROM indexing_jobs WHERE id = ?",
            (job_id,),
        )
        row = cursor.fetchone()
        if not row:
            return None
        return JobRecord(**dict(row))


def update_job(
    job_id: str,
    status: Optional[str] = None,
    stage: Optional[str] = None,
    progress: Optional[int] = None,
    error_message: Optional[str] = None,
    started: bool = False,
    completed: bool = False,
    db_path: Optional[Path] = None,
) -> None:
    """Update job status, stage, progress percentage, and timestamps."""
    updates = []
    params: list[Any] = []

    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if stage is not None:
        updates.append("stage = ?")
        params.append(stage)
    if progress is not None:
        updates.append("progress = ?")
        params.append(progress)
    if error_message is not None:
        updates.append("error_message = ?")
        params.append(error_message)
    if started:
        updates.append("started_at = ?")
        params.append(current_utc_iso())
    if completed:
        updates.append("completed_at = ?")
        params.append(current_utc_iso())

    if not updates:
        return

    params.append(job_id)
    with get_db(db_path) as conn:
        conn.execute(
            f"UPDATE indexing_jobs SET {', '.join(updates)} WHERE id = ?",
            tuple(params),
        )


def recover_interrupted_jobs(db_path: Optional[Path] = None) -> int:
    """Mark all jobs left in 'queued' or 'running' status as failed upon server startup."""
    now = current_utc_iso()
    with get_db(db_path) as conn:
        cursor = conn.execute(
            """
            SELECT id, repository_id FROM indexing_jobs
            WHERE status IN ('queued', 'running')
            """
        )
        interrupted = cursor.fetchall()
        for row in interrupted:
            job_id = row["id"]
            repo_id = row["repository_id"]
            conn.execute(
                """
                UPDATE indexing_jobs
                SET status = 'failed', error_message = 'Server was restarted while job was in progress', completed_at = ?
                WHERE id = ?
                """,
                (now, job_id),
            )
            conn.execute(
                """
                UPDATE repositories
                SET status = 'failed', error_message = 'Server was restarted while job was in progress', updated_at = ?
                WHERE id = ?
                """,
                (now, repo_id),
            )
        return len(interrupted)


MAX_ANALYSES_PER_REPOSITORY = 5


@dataclass
class AnalysisRecord:
    """Persistent summary of one completed analysis run, including parser diagnostics."""

    id: str
    repository_id: str
    job_id: str
    status: str
    created_at: str
    file_count: int
    symbol_count: int
    node_count: int
    edge_count: int
    import_edge_count: int
    unresolved_import_count: int
    graph_sha256: Optional[str]
    diagnostics: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _analysis_from_row(row: Any) -> AnalysisRecord:
    import json

    data = dict(row)
    diagnostics = json.loads(data.pop("diagnostics_json") or "{}")
    return AnalysisRecord(diagnostics=diagnostics, **data)


def complete_analysis(
    job_id: str,
    repo_id: str,
    analysis_id: str,
    graph_summary: dict[str, Any],
    graph_sha256: Optional[str],
    diagnostics: dict[str, Any],
    db_path: Optional[Path] = None,
) -> AnalysisRecord:
    """Atomically record the analysis, mark the job completed, and mark the repository completed.

    All three writes share one transaction: if any fails, none is applied and the caller
    must report the job as failed rather than reporting a saved analysis.
    """
    import json

    now = current_utc_iso()
    files = diagnostics.get("files", {})
    symbols = diagnostics.get("symbols", {})
    deps = diagnostics.get("dependencies", {})
    edges_by_type = graph_summary.get("edges_by_type", {}) or {}
    with get_db(db_path) as conn:
        conn.execute(
            """
            INSERT INTO analyses (
                id, repository_id, job_id, status, created_at, file_count, symbol_count,
                node_count, edge_count, import_edge_count, unresolved_import_count,
                graph_sha256, diagnostics_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                analysis_id,
                repo_id,
                job_id,
                "completed",
                now,
                int(files.get("discovered", 0)),
                int(symbols.get("extracted", 0)),
                int(graph_summary.get("node_count", 0)),
                int(graph_summary.get("edge_count", 0)),
                int(edges_by_type.get("IMPORTS", 0)),
                int(deps.get("imports_unresolved", 0)),
                graph_sha256,
                json.dumps(diagnostics),
            ),
        )
        conn.execute(
            """
            UPDATE indexing_jobs SET status = 'completed', stage = 'completed',
                progress = 100, completed_at = ? WHERE id = ?
            """,
            (now, job_id),
        )
        conn.execute(
            "UPDATE repositories SET status = 'completed', error_message = NULL, updated_at = ? WHERE id = ?",
            (now, repo_id),
        )
        # Bound history so repeated re-analysis cannot grow without limit.
        conn.execute(
            """
            DELETE FROM analyses WHERE repository_id = ? AND id NOT IN (
                SELECT id FROM analyses WHERE repository_id = ?
                ORDER BY created_at DESC, id DESC LIMIT ?
            )
            """,
            (repo_id, repo_id, MAX_ANALYSES_PER_REPOSITORY),
        )
    latest = get_latest_analysis(repo_id, db_path=db_path)
    if latest is None:
        raise RuntimeError("Analysis record was not persisted")
    return latest


def get_latest_analysis(
    repo_id: str,
    db_path: Optional[Path] = None,
) -> Optional[AnalysisRecord]:
    """Return the most recent analysis for a repository, if any."""
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM analyses WHERE repository_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
            (repo_id,),
        ).fetchone()
        return _analysis_from_row(row) if row else None


def list_analyses(
    repo_id: str,
    limit: int = 10,
    db_path: Optional[Path] = None,
) -> list[AnalysisRecord]:
    """List analyses for a repository, newest first."""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT * FROM analyses WHERE repository_id = ? ORDER BY created_at DESC, id DESC LIMIT ?",
            (repo_id, limit),
        ).fetchall()
        return [_analysis_from_row(r) for r in rows]


def get_repository_exact(
    repo_id: str,
    db_path: Optional[Path] = None,
) -> Optional[RepositoryRecord]:
    """Look up a repository by exact primary key only (no fuzzy URL/name matching)."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,)).fetchone()
        return RepositoryRecord(**dict(row)) if row else None


def delete_repository_records(
    repo_id: str,
    db_path: Optional[Path] = None,
) -> bool:
    """Delete a repository and (via ON DELETE CASCADE) its jobs and analyses."""
    with get_db(db_path) as conn:
        cursor = conn.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
        return cursor.rowcount > 0
