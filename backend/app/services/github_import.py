"""Queue a repository selected through the GitHub App into the shared indexing pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import uuid

from app.config import settings
from app.services import github_app
from app.services.indexing_service import indexing_service
from app.storage.repository_store import (
    JobRecord,
    RepositoryRecord,
    create_job,
    create_repository,
    get_job,
    get_repository,
    get_repository_by_url_and_branch,
    update_repository_status,
)


def submit_github_app_repository(
    session: github_app.GitHubSession,
    owner: str,
    repo: str,
    ref: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> tuple[RepositoryRecord, JobRecord]:
    """Verify access on the backend, register a user-owned repository record, and queue indexing.

    The record is owned by the GitHub user and is only reachable with their session. After the
    archive is fetched, the job runs the exact same extraction/parse/graph pipeline as public imports.
    """
    github_app.require_configured()
    info = github_app.authorize_repository_access(session.user_token, owner, repo)
    ref = ref or info["default_branch"]
    github_app.validate_repo_coordinates(info["owner"], info["name"], ref)

    canonical_url = f"https://github.com/{info['owner']}/{info['name']}"
    existing = get_repository_by_url_and_branch(
        canonical_url, ref, db_path=db_path, owner_github_user_id=session.user_id
    )
    if existing and existing.status in ("queued", "running") and existing.current_job_id:
        existing_job = get_job(existing.current_job_id, db_path=db_path)
        if existing_job:
            return existing, existing_job

    job_id = f"job_{uuid.uuid4().hex[:12]}"
    if existing:
        repo_id = existing.id
        update_repository_status(
            repo_id, status="queued", current_job_id=job_id, error_message=None, db_path=db_path
        )
        repo_record = get_repository(repo_id, db_path=db_path)
        if not repo_record:
            raise RuntimeError("Failed to retrieve updated repository record")
    else:
        repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        repo_record = create_repository(
            repo_id=repo_id,
            url=canonical_url,
            owner=info["owner"],
            name=info["name"],
            branch=ref,
            workspace_dir=str(settings.get_repo_source_dir(repo_id)),
            artifact_dir=str(settings.get_repo_artifact_dir(repo_id)),
            status="queued",
            current_job_id=job_id,
            db_path=db_path,
            owner_github_user_id=session.user_id,
        )
    job_record = create_job(job_id=job_id, repo_id=repo_id, db_path=db_path)

    installation_id, gh_owner, gh_name = info["installation_id"], info["owner"], info["name"]

    def fetch_archive(dest: Path) -> None:
        # Runs inside the job: the repo-scoped installation token is minted here and never stored.
        github_app.download_private_archive(installation_id, gh_owner, gh_name, ref, dest)

    indexing_service.submit_job(
        repo_id=repo_id,
        job_id=job_id,
        url=canonical_url,
        branch=ref,
        archive_fetcher=fetch_archive,
    )
    return repo_record, job_record
