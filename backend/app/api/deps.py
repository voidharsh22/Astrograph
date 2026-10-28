"""Shared FastAPI dependencies: per-repository authorization for private GitHub App imports."""

from __future__ import annotations

from typing import Optional

from fastapi import HTTPException, Request, status

from app.config import settings
from app.services.github_app import session_from_authorization
from app.storage.repository_store import get_job, get_repository

_AI_PATH_SUFFIXES = ("/chat", "/clusters/summarize", "/workflows", "/workflows/trace")


def _is_external_ai_path(path: str) -> bool:
    return "/ai/" in path or path.endswith(_AI_PATH_SUFFIXES)


def enforce_repository_access(request: Request) -> None:
    """Gate every route addressing a repository (or one of its jobs) by id.

    Public repositories (no owner) pass through untouched. A private GitHub App import is visible
    only to the GitHub user who imported it; everyone else gets the same 404 as for a missing id so
    existence is not disclosed. Resolution uses the same lookup the routes use, so a slug/URL
    cannot route around the check.
    """
    repo_ref: Optional[str] = request.path_params.get("repository_id")
    job_id: Optional[str] = request.path_params.get("job_id")
    if job_id:
        job = get_job(job_id)
        repo_ref = job.repository_id if job else None
    if not repo_ref:
        return

    repo = get_repository(repo_ref)
    if repo is None or repo.owner_github_user_id is None:
        return

    sess = session_from_authorization(request.headers.get("authorization"))
    if sess is None or sess.user_id != repo.owner_github_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Repository '{repo_ref}' not found, or you need to reconnect GitHub to access it",
        )

    if not settings.allow_ai_on_private_repos and _is_external_ai_path(request.url.path):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={
                "code": "ai_disabled_for_private_repository",
                "message": "AI features are disabled for private repositories so source code is never sent to an external AI provider.",
                "retryable": False,
            },
        )
