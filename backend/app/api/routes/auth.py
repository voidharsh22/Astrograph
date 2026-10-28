"""Account authentication routes: email/password signup + login, Google sign-in, session, logout."""

from __future__ import annotations

import logging
from typing import Any, Optional
from urllib.parse import urlencode, urlparse

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from app.config import settings
from app.services import auth_service as auth
from app.services import google_oidc
from app.storage import user_store
from app.storage.user_store import DuplicateEmailError, UserRecord

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

INVALID_LOGIN = "Invalid email or password."
OAUTH_COOKIE = "astral_oauth_state"


class SignupRequest(BaseModel):
    name: str = ""
    email: str = ""
    password: str = ""


class LoginRequest(BaseModel):
    email: str = ""
    password: str = ""


def _err(status_code: int, code: str, message: str, headers: Optional[dict[str, str]] = None) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message}, headers=headers)


def _client_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _allowed_origins() -> set[str]:
    return {settings.frontend_url, *settings.cors_origins}


def require_same_origin(request: Request) -> None:
    """CSRF guard for cookie-authenticated, state-changing requests.

    Browsers always send Origin on cross-site POST/DELETE; reject any that is not ours. Combined with
    SameSite=Lax cookies and JSON-only bodies (which force a CORS preflight), forged requests fail.
    """
    origin = request.headers.get("origin")
    if origin is None:
        referer = request.headers.get("referer")
        if referer:
            p = urlparse(referer)
            origin = f"{p.scheme}://{p.netloc}"
    if origin is not None and origin not in _allowed_origins():
        raise _err(status.HTTP_403_FORBIDDEN, "csrf_rejected", "Request origin is not allowed.")


def _public_user(user: UserRecord) -> dict[str, Any]:
    """Never includes the password hash."""
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name,
        "picture": user.picture,
        "has_password": user.password_hash is not None,
        "providers": user_store.list_identity_providers(user.id),
    }


def _set_session_cookie(response: Response, user: UserRecord) -> None:
    token, max_age = auth.start_session(user.id)
    response.set_cookie(
        auth.SESSION_COOKIE, token, max_age=max_age, httponly=True,
        secure=settings.cookies_secure, samesite="lax", path="/",
    )
    user_store.touch_login(user.id)


def _frontend_redirect(path: str, **params: str) -> RedirectResponse:
    query = f"?{urlencode(params)}" if params else ""
    resp = RedirectResponse(f"{settings.frontend_url}{path}{query}", status_code=302)
    resp.delete_cookie(OAUTH_COOKIE, path="/api/auth")
    return resp


# --------------------------------------------------------------------------------------
# Email / password
# --------------------------------------------------------------------------------------

@router.get("/config", summary="Which sign-in methods are available")
def auth_config() -> dict:
    return {"google": google_oidc.is_configured()}


@router.post("/signup", status_code=status.HTTP_201_CREATED, summary="Create an email/password account")
def signup(req: SignupRequest, request: Request) -> dict:
    require_same_origin(request)
    ip = _client_ip(request)
    wait = auth.signup_by_ip.retry_after(ip)
    if wait:
        raise _err(429, "rate_limited", "Too many attempts. Please wait a bit and try again.", {"Retry-After": str(wait)})
    auth.signup_by_ip.record(ip)
    try:
        email = auth.validate_email(req.email)
        name = auth.validate_name(req.name)
        password = auth.validate_password(req.password)
    except auth.ValidationError as err:
        raise _err(status.HTTP_400_BAD_REQUEST, "invalid_input", str(err)) from None

    duplicate = _err(
        status.HTTP_409_CONFLICT, "email_exists", "An account with this email already exists. Please log in instead."
    )
    if user_store.get_user_by_email(email):
        raise duplicate
    try:
        # The unique index is the real guarantee; the check above only avoids hashing for obvious dupes.
        user = user_store.create_user(email, name, auth.hash_password(password))
    except DuplicateEmailError:
        raise duplicate from None
    # No session is issued here: the user proceeds to log in.
    return {"id": user.id, "email": user.email, "name": user.name}


@router.post("/login", summary="Log in with email and password")
def login(req: LoginRequest, request: Request, response: Response) -> dict:
    require_same_origin(request)
    ip = _client_ip(request)
    email = auth.normalize_email(req.email)
    if not email or not req.password:
        raise _err(status.HTTP_400_BAD_REQUEST, "invalid_input", "Please enter your email and password.")

    wait = max(auth.login_by_email.retry_after(email), auth.login_by_ip.retry_after(ip))
    if wait:
        raise _err(429, "rate_limited", "Too many attempts. Please wait a bit and try again.", {"Retry-After": str(wait)})

    user = user_store.get_user_by_email(email)
    # Same work whether or not the account exists / has a password; one generic error for all failures.
    ok = auth.verify_password(req.password[: auth.MAX_PASSWORD_LENGTH + 1], user.password_hash if user else None)
    if not (user and ok and user.is_active):
        auth.login_by_email.record(email)
        auth.login_by_ip.record(ip)
        raise _err(status.HTTP_401_UNAUTHORIZED, "invalid_credentials", INVALID_LOGIN)

    auth.login_by_email.reset(email)
    _set_session_cookie(response, user)
    return {"user": _public_user(user)}


# --------------------------------------------------------------------------------------
# Session
# --------------------------------------------------------------------------------------

@router.get("/me", summary="The authenticated user (the backend is the source of truth)")
def me(request: Request) -> dict:
    user = auth.user_for_token(request.cookies.get(auth.SESSION_COOKIE))
    if user is None:
        raise _err(status.HTTP_401_UNAUTHORIZED, "not_authenticated", "Not signed in.")
    return {"user": _public_user(user)}


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Invalidate the session")
def logout(request: Request, response: Response) -> None:
    require_same_origin(request)
    auth.end_session(request.cookies.get(auth.SESSION_COOKIE))
    response.delete_cookie(auth.SESSION_COOKIE, path="/")


# --------------------------------------------------------------------------------------
# Google
# --------------------------------------------------------------------------------------

@router.get("/google/start", summary="Redirect to Google's account chooser")
def google_start() -> RedirectResponse:
    if not google_oidc.is_configured():
        return _frontend_redirect("/", auth_error="google_not_configured")
    state, url = google_oidc.begin_flow()
    resp = RedirectResponse(url, status_code=302)
    # Binds the flow to this browser so a forged callback (login CSRF) is rejected.
    resp.set_cookie(
        OAUTH_COOKIE, state, max_age=google_oidc.FLOW_TTL_SECONDS, httponly=True,
        secure=settings.cookies_secure, samesite="lax", path="/api/auth",
    )
    return resp


@router.get("/google/callback", include_in_schema=False)
def google_callback(
    request: Request,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
) -> RedirectResponse:
    if not google_oidc.is_configured():
        return _frontend_redirect("/", auth_error="google_not_configured")
    cookie_state = request.cookies.get(OAUTH_COOKIE)
    flow = google_oidc.pop_flow(state or "")
    if not state or not cookie_state or cookie_state != state or flow is None:
        return _frontend_redirect("/", auth_error="google_invalid_state")
    if error:
        # access_denied = the user cancelled / declined consent
        return _frontend_redirect("/", auth_error="google_cancelled" if error == "access_denied" else "google_failed")
    if not code:
        return _frontend_redirect("/", auth_error="google_failed")

    verifier, nonce = flow
    try:
        claims = google_oidc.verify_id_token(google_oidc.exchange_code(code, verifier), nonce)
    except google_oidc.GoogleAuthError as err:
        logger.warning("Google sign-in rejected: %s", err.code)
        return _frontend_redirect("/", auth_error=err.code)

    subject, email = str(claims["sub"]), auth.normalize_email(claims["email"])
    user = user_store.get_user_by_identity(google_oidc.PROVIDER, subject)
    if user is None:
        # Never link by email alone: that would let anyone who controls a Google address with the same
        # email take over a password account. The owner must log in with their password instead.
        if user_store.get_user_by_email(email):
            return _frontend_redirect("/", auth_error="google_email_in_use")
        name = " ".join(str(claims.get("name") or email.split("@")[0]).split())[:100] or email
        picture = claims.get("picture") if str(claims.get("picture", "")).startswith("https://") else None
        try:
            user = user_store.create_user_with_identity(email, name, picture, google_oidc.PROVIDER, subject)
        except DuplicateEmailError:
            return _frontend_redirect("/", auth_error="google_email_in_use")
    if not user.is_active:
        return _frontend_redirect("/", auth_error="google_failed")

    resp = _frontend_redirect("/dashboard")
    _set_session_cookie(resp, user)
    return resp
