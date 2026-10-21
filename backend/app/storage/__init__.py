"""Storage package — persistent SQLite database and repository artifact manager."""

from app.storage.database import get_db, get_db_connection, init_db
from app.storage.repository_store import (
    complete_job,
    create_job,
    create_or_get_repository,
    fail_job,
    get_job,
    get_repository,
    list_repositories,
    load_graph_artifact,
    save_graph_artifact,
    update_job_progress,
    update_repository_status,
)

__all__ = [
    "complete_job",
    "create_job",
    "create_or_get_repository",
    "fail_job",
    "get_db",
    "get_db_connection",
    "get_job",
    "get_repository",
    "init_db",
    "list_repositories",
    "load_graph_artifact",
    "save_graph_artifact",
    "update_job_progress",
    "update_repository_status",
]
