"""
Database connection and lifecycle management for Astral Cartographer.
"""

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
    try:
        conn.execute("PRAGMA journal_mode = WAL;")
    except sqlite3.OperationalError:
        pass

    # Ensure schema exists
    cursor = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='repositories';")
    if not cursor.fetchone():
        _create_tables(conn)
    else:
        # Run backwards-compatible column migrations
        _migrate_columns(conn)

    return conn


def _migrate_columns(conn: sqlite3.Connection) -> None:
    """Ensure newly added columns exist in older databases."""
    for col, col_type in [
        ("user_id", "TEXT DEFAULT ''"),
        ("user_email", "TEXT DEFAULT ''"),
    ]:
        try:
            conn.execute(f"ALTER TABLE repositories ADD COLUMN {col} {col_type};")
        except sqlite3.OperationalError:
            pass

    for col, col_type in [
        ("message", "TEXT DEFAULT ''"),
        ("metrics_json", "TEXT DEFAULT '{}'"),
        ("logs_json", "TEXT DEFAULT '[]'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_type};")
        except sqlite3.OperationalError:
            pass
    conn.commit()


def _create_tables(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS repositories (
            id TEXT PRIMARY KEY,
            url TEXT NOT NULL,
            owner TEXT NOT NULL,
            name TEXT NOT NULL,
            branch TEXT NOT NULL,
            status TEXT NOT NULL,
            user_id TEXT DEFAULT '',
            user_email TEXT DEFAULT '',
            current_job_id TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            error_message TEXT
        );

        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            repository_id TEXT NOT NULL,
            status TEXT NOT NULL,
            stage TEXT NOT NULL,
            progress INTEGER NOT NULL DEFAULT 0,
            message TEXT DEFAULT '',
            metrics_json TEXT DEFAULT '{}',
            logs_json TEXT DEFAULT '[]',
            started_at TEXT NOT NULL,
            completed_at TEXT,
            error_message TEXT,
            FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_repositories_url ON repositories(url);
        CREATE INDEX IF NOT EXISTS idx_jobs_repo_id ON jobs(repository_id);
        """
    )
    _migrate_columns(conn)


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


def init_db(db_path: Optional[Path] = None) -> None:
    """Initialize database tables and indexes."""
    with get_db(db_path) as conn:
        _create_tables(conn)
