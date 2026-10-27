"""Database connection and lifecycle management for Astral Cartographer."""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Generator, Optional

from app.config import settings


def get_db_connection(db_path: Optional[Path] = None) -> sqlite3.Connection:
    """Create a new SQLite connection with appropriate pragmas."""
    target_path = db_path or settings.db_path
    target_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(
        str(target_path),
        timeout=30.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    # WAL journal mode for safe concurrency
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass
    return conn


@contextmanager
def get_db(db_path: Optional[Path] = None) -> Generator[sqlite3.Connection, None, None]:
    """Context manager providing a transactional SQLite connection."""
    conn = get_db_connection(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# Ordered, append-only list of schema migrations. Each entry is applied exactly once
# inside its own transaction and recorded in ``schema_migrations``. Never edit an
# applied migration; add a new one instead so existing user data is preserved.
MIGRATIONS: list[tuple[int, str, str]] = [
    (
        1,
        "baseline repositories and indexing_jobs",
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            branch TEXT NOT NULL,
            status TEXT NOT NULL,
            current_job_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            workspace_dir TEXT NOT NULL,
            artifact_dir TEXT NOT NULL,
            error_message TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);

        CREATE TABLE IF NOT EXISTS indexing_jobs (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            progress INTEGER NOT NULL,
            started_at TEXT,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_jobs_repository_id ON indexing_jobs(repository_id);
        CREATE INDEX IF NOT EXISTS idx_jobs_status ON indexing_jobs(status);
        """,
    ),
    (
        2,
        "analyses table with persisted metrics and parser diagnostics",
        """
        CREATE TABLE IF NOT EXISTS analyses (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            job_id TEXT NOT NULL UNIQUE,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            file_count INTEGER NOT NULL DEFAULT 0,
            symbol_count INTEGER NOT NULL DEFAULT 0,
            node_count INTEGER NOT NULL DEFAULT 0,
            edge_count INTEGER NOT NULL DEFAULT 0,
            import_edge_count INTEGER NOT NULL DEFAULT 0,
            unresolved_import_count INTEGER NOT NULL DEFAULT 0,
            graph_sha256 TEXT,
            diagnostics_json TEXT NOT NULL,
            FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
            FOREIGN KEY (job_id) REFERENCES indexing_jobs(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_analyses_repo_created
            ON analyses(repository_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_repositories_url_branch
            ON repositories(url, branch);
        """,
    ),
]


def _split_statements(script: str) -> list[str]:
    return [stmt.strip() for stmt in script.split(";") if stmt.strip()]


def init_db(db_path: Optional[Path] = None) -> None:
    """Create the migration ledger and apply any pending migrations in order."""
    try:
        conn = get_db_connection(db_path)
    except sqlite3.Error as exc:
        raise RuntimeError(f"Database is unavailable: {exc}") from exc
    try:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS schema_migrations ("
            "version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)"
        )
        conn.commit()
        applied = {r["version"] for r in conn.execute("SELECT version FROM schema_migrations")}
        for version, description, script in MIGRATIONS:
            if version in applied:
                continue
            try:
                conn.execute("BEGIN")
                for stmt in _split_statements(script):
                    conn.execute(stmt)
                conn.execute(
                    "INSERT INTO schema_migrations (version, description, applied_at) VALUES (?, ?, datetime('now'))",
                    (version, description),
                )
                conn.commit()
            except sqlite3.Error as exc:
                conn.rollback()
                raise RuntimeError(
                    f"Database migration {version} ('{description}') failed: {exc}"
                ) from exc
    finally:
        conn.close()


def schema_version(db_path: Optional[Path] = None) -> int:
    """Return the highest applied migration version (0 if none)."""
    with get_db(db_path) as conn:
        row = conn.execute("SELECT MAX(version) AS v FROM schema_migrations").fetchone()
        return int(row["v"] or 0)
