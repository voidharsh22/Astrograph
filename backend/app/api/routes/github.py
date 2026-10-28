"""GitHub App routes: connect (OAuth), list authorized repositories, and import them for analysis."""

from __future__ import annotations

import logging
import time
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Header, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app.api.schemas import RepositorySubmitResponse
from app.config import settings
from app.services import github_app
from app.services.github_app import GitHubError, GitHubSession
from app.services.github_import import submit_github_app_repository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/github", tags=["github"])


class SessionRequest(BaseModel):
    ticket: str = Field(..., min_length=1, max_length=200)
    nonce: str = Field(..., min_length=1, max_length=200)


class GithubAnalyzeRequest(BaseModel):
    owner: str = Field(..., max_length=100)
    repo: str = Field(..., max_length=100)
    ref: Optional[str] = Field(default=None, max_length=100, description="Branch name or commit SHA")


def _http_error(err: GitHubError) -> HTTPException:
    return HTTPException(status_code=err.status_code, detail=err.to_dict())


def _require_session(authorization: Optional[str]) -> GitHubSession:
    sess = github_app.session_from_authorization(authorization)
    if sess is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "github_not_connected", "message": "Connect GitHub to continue."},
        )
    return sess


def _frontend_redirect(**params: str) -> RedirectResponse:
    return RedirectResponse(f"{settings.frontend_url}/dashboard?{urlencode(params)}", status_code=302)


@router.get("/status", summary="GitHub App configuration and connection state")
def github_status(authorization: Optional[str] = Header(default=None)) -> dict:
    sess = github_app.session_from_authorization(authorization)
    return {
        "configured": github_app.is_configured(),
        "install_url": github_app.install_url(),
        "connected": sess is not None,
        "login": sess.login if sess else None,
        "avatar_url": sess.avatar_url if sess else None,
        "ai_on_private_repos": settings.allow_ai_on_private_repos,
    }


@router.post("/connect", summary="Begin GitHub authorization")
def github_connect() -> dict:
    """Return the GitHub authorize URL plus a nonce the browser must present to finish the sign-in."""
    try:
        github_app.require_configured()
    except GitHubError as err:
        raise _http_error(err) from err
    state, nonce = github_app.stores.begin_flow()
    return {"authorize_url": github_app.build_authorize_url(state), "nonce": nonce}


@router.get("/callback", include_in_schema=False)
def github_callback(
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    installation_id: Optional[str] = None,
    setup_action: Optional[str] = None,
) -> RedirectResponse:
    """OAuth redirect target. Validates state, exchanges the code, then hands the browser a one-time ticket."""
    if not code and not state and not error:
        # GitHub's post-installation Setup URL without user authorization: just send the user back.
        return _frontend_redirect(gh_installed="1")
    if error:
        return _frontend_redirect(gh_error="access_denied")
    nonce_hash = github_app.stores.consume_state(state or "")
    if not nonce_hash or not code:
        return _frontend_redirect(gh_error="invalid_state")
    try:
        user_token = github_app.exchange_code_for_user_token(code)
        user = github_app.get_authenticated_user(user_token)
    except GitHubError as err:
        logger.warning("GitHub callback failed: %s", err.code)
        return _frontend_redirect(gh_error=err.code)
    session_token = github_app.stores.create_session(
        GitHubSession(
            user_id=user["id"],
            login=user["login"],
            avatar_url=user.get("avatar_url"),
            user_token=user_token,
            expires_at=github_app.new_session_expiry(),
        )
    )
    ticket = github_app.stores.create_ticket(session_token, nonce_hash)
    return _frontend_redirect(gh_ticket=ticket)


@router.post("/session", summary="Exchange the one-time login ticket for an Astral session token")
def github_session(req: SessionRequest) -> dict:
    token = github_app.stores.redeem_ticket(req.ticket, req.nonce)
    sess = github_app.stores.get_session(token) if token else None
    if not token or sess is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_ticket", "message": "Sign-in expired or was started in another browser. Try again."},
        )
    return {
        "session_token": token,
        "login": sess.login,
        "avatar_url": sess.avatar_url,
        "expires_in": max(0, int(sess.expires_at - time.time())),
    }


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT, summary="Disconnect GitHub")
def github_disconnect(authorization: Optional[str] = Header(default=None)) -> None:
    token = github_app.bearer_token_from_header(authorization)
    sess = github_app.stores.delete_session(token or "")
    if sess is not None:
        github_app.revoke_user_token(sess.user_token)


@router.get("/repositories", summary="Repositories you can access that the GitHub App is installed on")
def github_repositories(authorization: Optional[str] = Header(default=None)) -> dict:
    sess = _require_session(authorization)
    try:
        return {"items": github_app.list_user_repositories(sess.user_token)}
    except GitHubError as err:
        if err.code == "github_auth_expired":
            github_app.stores.delete_session(github_app.bearer_token_from_header(authorization) or "")
        raise _http_error(err) from err


@router.get("/repositories/{owner}/{repo}/branches", summary="Branches of an authorized repository")
def github_branches(owner: str, repo: str, authorization: Optional[str] = Header(default=None)) -> dict:
    sess = _require_session(authorization)
    try:
        info = github_app.authorize_repository_access(sess.user_token, owner, repo)
        return {
            "default_branch": info["default_branch"],
            "items": github_app.list_branches(info["installation_id"], info["owner"], info["name"]),
        }
    except GitHubError as err:
        raise _http_error(err) from err


@router.post(
    "/analyze",
    response_model=RepositorySubmitResponse,
    status_code=status.HTTP_202_ACCEPTED,
    summary="Analyze a repository through the GitHub App",
)
def github_analyze(
    req: GithubAnalyzeRequest, authorization: Optional[str] = Header(default=None)
) -> RepositorySubmitResponse:
    sess = _require_session(authorization)
    try:
        repo_rec, job_rec = submit_github_app_repository(sess, req.owner, req.repo, req.ref)
    except GitHubError as err:
        raise _http_error(err) from err
    except ValueError as err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(err)) from err
    except Exception as err:
        logger.exception("Failed to queue GitHub App repository: %s", type(err).__name__)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal error queueing repository indexing",
        ) from err
    return RepositorySubmitResponse(
        repository_id=repo_rec.id,
        job_id=job_rec.id,
        status=job_rec.status,
        message="Repository indexing has been queued.",
    )
