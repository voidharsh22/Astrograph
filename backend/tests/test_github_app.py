"""GitHub App private-repository support, tested against mocked GitHub responses (no network)."""

from __future__ import annotations

import io
import json
from pathlib import Path
import sqlite3
import tempfile
import time
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
import zipfile

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt

from app.config import settings
from app.main import app
from app.services import github_app
from app.services.github_app import GitHubError
from app.storage import database
from app.storage.database import init_db
from app.storage.repository_store import create_repository, get_job, get_repository

_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
PRIVATE_PEM = _KEY.private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
).decode()
PUBLIC_KEY = _KEY.public_key()

USER_TOKEN = "ghu_user_token_secret"
INSTALL_TOKEN = "ghs_installation_token_secret"
SIGNED_QUERY = "token=SIGNED_CODELOAD_SECRET"


def make_zip(files: dict[str, str], wrapper: str = "octo-private-abc123") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel, content in files.items():
            zf.writestr(f"{wrapper}/{rel}", content)
    return buf.getvalue()


SAMPLE_FILES = {
    "main.py": "from util import helper\n\ndef run():\n    return helper()\n",
    "util.py": "def helper():\n    return 1\n",
}


class FakeGitHub:
    """Routes httpx requests to canned GitHub responses and records every call."""

    def __init__(self) -> None:
        self.calls: list[httpx.Request] = []
        self.user = {"id": 1001, "login": "octo", "avatar_url": "https://avatars/octo"}
        self.repo_status = 200
        self.repo_permissions: dict = {"pull": True}
        self.installed = True
        self.zipball_status = 302
        self.zip_bytes = make_zip(SAMPLE_FILES)
        self.rate_limited = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        url, path, host = str(request.url), request.url.path, request.url.host
        if host == "github.com" and path == "/login/oauth/access_token":
            return httpx.Response(200, json={"access_token": USER_TOKEN})
        if host == "codeload.github.com":
            return httpx.Response(200, content=self.zip_bytes)
        assert host == "api.github.com", url
        if self.rate_limited:
            return httpx.Response(403, headers={"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1893456000"})
        if path == "/user":
            return httpx.Response(200, json=self.user)
        if path == "/user/installations":
            return httpx.Response(200, json={"installations": [{"id": 77}]})
        if path == "/user/installations/77/repositories":
            return httpx.Response(200, json={"repositories": [
                {"id": 1, "full_name": "octo/private-repo", "owner": {"login": "octo"}, "name": "private-repo",
                 "private": True, "default_branch": "trunk", "description": "secret"},
                {"id": 2, "full_name": "octo/open", "owner": {"login": "octo"}, "name": "open",
                 "private": False, "default_branch": "main", "description": None},
            ]})
        if path == "/repos/octo/private-repo":
            if self.repo_status != 200:
                return httpx.Response(self.repo_status, json={"message": "Not Found"})
            return httpx.Response(200, json={
                "id": 1, "name": "private-repo", "full_name": "octo/private-repo", "private": True,
                "owner": {"login": "octo"}, "default_branch": "trunk", "permissions": self.repo_permissions})
        if path == "/repos/octo/private-repo/installation":
            if not self.installed:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(200, json={"id": 77})
        if path == "/app/installations/77/access_tokens":
            return httpx.Response(201, json={"token": INSTALL_TOKEN})
        if path == "/repos/octo/private-repo/branches":
            return httpx.Response(200, json=[{"name": "trunk", "commit": {"sha": "a" * 40}}])
        if path.startswith("/repos/octo/private-repo/zipball/"):
            if self.zipball_status == 404:
                return httpx.Response(404, json={"message": "Not Found"})
            return httpx.Response(302, headers={
                "location": f"https://codeload.github.com/octo/private-repo/legacy.zip/x?{SIGNED_QUERY}"})
        if path.startswith("/applications/") and path.endswith("/token"):
            return httpx.Response(204)
        return httpx.Response(404, json={"message": f"unmocked {path}"})

    def requests_to(self, host: str) -> list[httpx.Request]:
        return [r for r in self.calls if r.url.host == host]


class GitHubAppTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.orig = {
            k: getattr(settings, k)
            for k in (
                "data_dir", "github_app_id", "github_app_slug", "github_app_client_id",
                "github_app_client_secret", "github_app_private_key", "github_app_private_key_path",
                "allow_ai_on_private_repos", "frontend_url",
            )
        }
        settings.data_dir = Path(self.temp_dir.name).resolve() / "data"
        settings.ensure_directories()
        init_db()
        github_app.stores.clear()
        self.gh = FakeGitHub()
        github_app.set_transport_override(httpx.MockTransport(self.gh.handler))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        github_app.set_transport_override(None)
        github_app.stores.clear()
        for k, v in self.orig.items():
            setattr(settings, k, v)
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def configure_app(self) -> None:
        settings.github_app_id = "12345"
        settings.github_app_slug = "astrograph-test"
        settings.github_app_client_id = "Iv1.testclient"
        settings.github_app_client_secret = "client-secret-value"
        settings.github_app_private_key = PRIVATE_PEM
        settings.github_app_private_key_path = ""
        settings.allow_ai_on_private_repos = False

    def sign_in(self, user_id: int = 1001, login: str = "octo") -> str:
        """Run the real connect -> callback -> ticket exchange flow and return the session token."""
        self.gh.user = {"id": user_id, "login": login, "avatar_url": None}
        connect = self.client.post("/api/github/connect").json()
        state = parse_qs(urlparse(connect["authorize_url"]).query)["state"][0]
        cb = self.client.get(f"/api/github/callback?code=abc&state={state}", follow_redirects=False)
        ticket = parse_qs(urlparse(cb.headers["location"]).query)["gh_ticket"][0]
        res = self.client.post("/api/github/session", json={"ticket": ticket, "nonce": connect["nonce"]})
        self.assertEqual(res.status_code, 200, res.text)
        return res.json()["session_token"]

    @staticmethod
    def auth(token: str) -> dict[str, str]:
        return {"Authorization": f"Bearer {token}"}

    def wait_for(self, repo_id: str, timeout: float = 60.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            repo = get_repository(repo_id)
            if repo and repo.status in ("completed", "failed"):
                return repo.status
            time.sleep(0.05)
        self.fail("indexing did not finish")


class TestNotConfigured(GitHubAppTestBase):
    def test_status_reports_unconfigured_and_connect_is_503(self):
        settings.github_app_id = settings.github_app_client_id = ""
        settings.github_app_client_secret = settings.github_app_private_key = ""
        settings.github_app_private_key_path = ""
        body = self.client.get("/api/github/status").json()
        self.assertFalse(body["configured"])
        self.assertFalse(body["connected"])
        res = self.client.post("/api/github/connect")
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["detail"]["code"], "github_not_configured")

    def test_public_endpoints_unaffected_without_credentials(self):
        settings.github_app_id = settings.github_app_private_key = ""
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        listing = self.client.get("/api/repositories")
        self.assertEqual(listing.status_code, 200)
        self.assertIn("items", listing.json())
        self.assertEqual(self.client.get("/api/repositories/repo_missing").status_code, 404)

    def test_analyze_requires_a_session(self):
        self.configure_app()
        res = self.client.post("/api/github/analyze", json={"owner": "octo", "repo": "private-repo"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(res.json()["detail"]["code"], "github_not_connected")


class TestOAuthFlow(GitHubAppTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_app()

    def test_authorize_url_and_full_sign_in(self):
        connect = self.client.post("/api/github/connect").json()
        parsed = urlparse(connect["authorize_url"])
        self.assertEqual(parsed.netloc, "github.com")
        q = parse_qs(parsed.query)
        self.assertEqual(q["client_id"], ["Iv1.testclient"])
        self.assertTrue(q["redirect_uri"][0].endswith("/api/github/callback"))
        self.assertNotIn("client_secret", connect["authorize_url"])

        token = self.sign_in()
        status_body = self.client.get("/api/github/status", headers=self.auth(token)).json()
        self.assertTrue(status_body["connected"])
        self.assertEqual(status_body["login"], "octo")
        self.assertEqual(status_body["install_url"], "https://github.com/apps/astrograph-test/installations/new")
        # No GitHub credential is ever returned to the browser.
        self.assertNotIn(USER_TOKEN, json.dumps(status_body))

    def test_invalid_and_replayed_state_rejected(self):
        res = self.client.get("/api/github/callback?code=abc&state=bogus", follow_redirects=False)
        self.assertIn("gh_error=invalid_state", res.headers["location"])
        self.assertEqual(self.gh.requests_to("github.com"), [])  # code never exchanged

        connect = self.client.post("/api/github/connect").json()
        state = parse_qs(urlparse(connect["authorize_url"]).query)["state"][0]
        ok = self.client.get(f"/api/github/callback?code=abc&state={state}", follow_redirects=False)
        self.assertIn("gh_ticket=", ok.headers["location"])
        replay = self.client.get(f"/api/github/callback?code=abc&state={state}", follow_redirects=False)
        self.assertIn("gh_error=invalid_state", replay.headers["location"])

    def test_ticket_is_bound_to_browser_nonce_and_single_use(self):
        connect = self.client.post("/api/github/connect").json()
        state = parse_qs(urlparse(connect["authorize_url"]).query)["state"][0]
        cb = self.client.get(f"/api/github/callback?code=abc&state={state}", follow_redirects=False)
        ticket = parse_qs(urlparse(cb.headers["location"]).query)["gh_ticket"][0]
        wrong = self.client.post("/api/github/session", json={"ticket": ticket, "nonce": "not-my-nonce"})
        self.assertEqual(wrong.status_code, 400)
        # a failed attempt burns the ticket
        right = self.client.post("/api/github/session", json={"ticket": ticket, "nonce": connect["nonce"]})
        self.assertEqual(right.status_code, 400)

    def test_user_denied_authorization(self):
        res = self.client.get("/api/github/callback?error=access_denied&state=x", follow_redirects=False)
        self.assertIn("gh_error=access_denied", res.headers["location"])

    def test_sessions_expire(self):
        token = self.sign_in()
        sess = github_app.stores.get_session(token)
        sess.expires_at = time.time() - 1
        status_body = self.client.get("/api/github/status", headers=self.auth(token)).json()
        self.assertFalse(status_body["connected"])

    def test_disconnect_revokes_and_invalidates(self):
        token = self.sign_in()
        res = self.client.delete("/api/github/session", headers=self.auth(token))
        self.assertEqual(res.status_code, 204)
        self.assertFalse(self.client.get("/api/github/status", headers=self.auth(token)).json()["connected"])
        revoke = [r for r in self.gh.calls if r.method == "DELETE"]
        self.assertEqual(len(revoke), 1)

    def test_app_jwt_is_rs256_signed_with_app_id(self):
        decoded = jwt.decode(github_app.app_jwt(), PUBLIC_KEY, algorithms=["RS256"])
        self.assertEqual(decoded["iss"], "12345")
        self.assertLessEqual(decoded["exp"] - decoded["iat"], 11 * 60)

    def test_private_key_from_path_and_bad_key(self):
        key_file = Path(self.temp_dir.name) / "app.pem"
        key_file.write_text(PRIVATE_PEM)
        settings.github_app_private_key = ""
        settings.github_app_private_key_path = str(key_file)
        self.assertTrue(github_app.is_configured())
        jwt.decode(github_app.app_jwt(), PUBLIC_KEY, algorithms=["RS256"])
        settings.github_app_private_key_path = str(Path(self.temp_dir.name) / "missing.pem")
        self.assertFalse(github_app.is_configured())
        settings.github_app_private_key = "not a pem"
        with self.assertRaises(GitHubError) as ctx:
            github_app.app_jwt()
        self.assertEqual(ctx.exception.code, "github_not_configured")


class TestRepositoryAccessAndIngestion(GitHubAppTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.configure_app()

    def analyze(self, token: str, **body):
        payload = {"owner": "octo", "repo": "private-repo", **body}
        return self.client.post("/api/github/analyze", json=payload, headers=self.auth(token))

    def test_lists_authorized_repositories_with_visibility(self):
        token = self.sign_in()
        items = self.client.get("/api/github/repositories", headers=self.auth(token)).json()["items"]
        by_name = {i["full_name"]: i for i in items}
        self.assertTrue(by_name["octo/private-repo"]["private"])
        self.assertFalse(by_name["octo/open"]["private"])
        self.assertEqual(by_name["octo/private-repo"]["default_branch"], "trunk")
        self.assertNotIn(INSTALL_TOKEN, json.dumps(items))

    def test_branches_listed_after_server_side_permission_check(self):
        token = self.sign_in()
        body = self.client.get("/api/github/repositories/octo/private-repo/branches", headers=self.auth(token)).json()
        self.assertEqual(body["default_branch"], "trunk")
        self.assertEqual(body["items"][0]["name"], "trunk")

    def test_private_import_uses_shared_pipeline_and_scoped_token(self):
        token = self.sign_in()
        res = self.analyze(token)
        self.assertEqual(res.status_code, 202, res.text)
        repo_id = res.json()["repository_id"]
        self.assertEqual(self.wait_for(repo_id), "completed", get_repository(repo_id).error_message)

        record = get_repository(repo_id)
        self.assertEqual(record.owner_github_user_id, 1001)
        self.assertEqual(record.branch, "trunk")  # default branch resolved server-side
        self.assertEqual(record.url, "https://github.com/octo/private-repo")

        graph = self.client.get(f"/api/repositories/{repo_id}/graph", headers=self.auth(token))
        self.assertEqual(graph.status_code, 200)
        self.assertTrue(graph.json()["nodes"])
        self.assertTrue(graph.json()["edges"])

        # Installation token: minted with read-only, single-repo scope; sent only to api.github.com.
        mint = [r for r in self.gh.calls if r.url.path == "/app/installations/77/access_tokens"][0]
        body = json.loads(mint.content)
        self.assertEqual(body["repositories"], ["private-repo"])
        self.assertEqual(body["permissions"], {"contents": "read", "metadata": "read"})
        self.assertTrue(mint.headers["authorization"].startswith("Bearer eyJ"))  # App JWT
        for req in self.gh.requests_to("codeload.github.com"):
            self.assertNotIn("authorization", req.headers)
        zipball = [r for r in self.gh.calls if "/zipball/" in r.url.path][0]
        self.assertEqual(zipball.headers["authorization"], f"Bearer {INSTALL_TOKEN}")
        self.assertTrue(zipball.url.path.endswith("/zipball/trunk"))

    def test_private_graph_matches_public_pipeline_output(self):
        """Same archive through the public path and the private path yields identical graph structure."""
        token = self.sign_in()
        private_id = self.analyze(token).json()["repository_id"]
        self.assertEqual(self.wait_for(private_id), "completed")

        def fake_public_download(url, branch, dest_path, **_):
            Path(dest_path).write_bytes(self.gh.zip_bytes)

        with patch("app.services.indexing_service.download_github_archive", fake_public_download):
            pub = self.client.post("/api/repositories", json={"url": "https://github.com/octo/public-twin", "branch": "main"})
            self.assertEqual(pub.status_code, 202)
            public_id = pub.json()["repository_id"]
            self.assertEqual(self.wait_for(public_id), "completed")

        g_priv = self.client.get(f"/api/repositories/{private_id}/graph", headers=self.auth(token)).json()
        g_pub = self.client.get(f"/api/repositories/{public_id}/graph").json()
        self.assertEqual(set(g_priv.keys()), set(g_pub.keys()))
        self.assertEqual(g_priv["summary"], g_pub["summary"])
        self.assertEqual(len(g_priv["nodes"]), len(g_pub["nodes"]))
        self.assertEqual(len(g_priv["edges"]), len(g_pub["edges"]))

    def test_explicit_ref_is_used_and_invalid_refs_rejected(self):
        token = self.sign_in()
        res = self.analyze(token, ref="a" * 40)
        self.assertEqual(res.status_code, 202)
        self.wait_for(res.json()["repository_id"])
        self.assertTrue(any(r.url.path.endswith("/zipball/" + "a" * 40) for r in self.gh.calls))
        for bad in ("../etc/passwd", "-x", "a b", "x..y", "branch.lock", "a" * 101):
            r = self.analyze(token, ref=bad)
            self.assertIn(r.status_code, (400, 422), bad)

    def test_user_without_access_is_refused(self):
        token = self.sign_in()
        self.gh.repo_status = 404
        res = self.analyze(token)
        self.assertEqual(res.status_code, 403)
        self.assertEqual(res.json()["detail"]["code"], "github_access_denied")

    def test_user_without_read_permission_is_refused(self):
        token = self.sign_in()
        self.gh.repo_permissions = {"pull": False, "push": False, "admin": False}
        self.assertEqual(self.analyze(token).status_code, 403)

    def test_app_not_installed_is_reported(self):
        token = self.sign_in()
        self.gh.installed = False
        res = self.analyze(token)
        self.assertEqual(res.status_code, 404)
        self.assertEqual(res.json()["detail"]["code"], "github_not_installed")

    def test_rate_limit_surfaces_clear_error(self):
        token = self.sign_in()
        self.gh.rate_limited = True
        res = self.client.get("/api/github/repositories", headers=self.auth(token))
        self.assertEqual(res.status_code, 429)
        self.assertEqual(res.json()["detail"]["code"], "github_rate_limited")

    def test_other_users_and_anonymous_cannot_reach_private_repository(self):
        owner_token = self.sign_in()
        repo_id = self.analyze(owner_token).json()["repository_id"]
        job_id = get_repository(repo_id).current_job_id
        self.wait_for(repo_id)
        other_token = self.sign_in(user_id=2002, login="mallory")

        paths = [
            ("GET", f"/api/repositories/{repo_id}"),
            ("GET", f"/api/repositories/{repo_id}/graph"),
            ("GET", f"/api/repositories/{repo_id}/files"),
            ("GET", f"/api/repositories/{repo_id}/file?path=main.py"),
            ("GET", f"/api/repositories/{repo_id}/analytics"),
            ("GET", f"/api/repositories/{repo_id}/symbols?query=run"),
            ("GET", f"/api/repositories/{repo_id}/insights/health"),
            ("GET", f"/api/jobs/{job_id}"),
            ("DELETE", f"/api/repositories/{repo_id}"),
        ]
        for headers in ({}, self.auth(other_token)):
            for method, path in paths:
                res = self.client.request(method, path, headers=headers)
                self.assertEqual(res.status_code, 404, f"{method} {path} {headers!r}")
        # URL-based lookup cannot route around the check either.
        self.assertEqual(self.client.get("/api/repositories/private-repo").status_code, 404)

        listing_other = self.client.get("/api/repositories", headers=self.auth(other_token)).json()["items"]
        listing_anon = self.client.get("/api/repositories").json()["items"]
        listing_owner = self.client.get("/api/repositories", headers=self.auth(owner_token)).json()["items"]
        self.assertNotIn(repo_id, [i["id"] for i in listing_other])
        self.assertNotIn(repo_id, [i["id"] for i in listing_anon])
        self.assertIn(repo_id, [i["id"] for i in listing_owner])

        # Owner still has access, and the repository survived the denied delete attempts.
        self.assertEqual(self.client.get(f"/api/repositories/{repo_id}/graph", headers=self.auth(owner_token)).status_code, 200)
        src = self.client.get(f"/api/repositories/{repo_id}/file?path=main.py", headers=self.auth(owner_token))
        self.assertEqual(src.status_code, 200)
        self.assertEqual(self.client.get(f"/api/jobs/{job_id}", headers=self.auth(owner_token)).status_code, 200)

    def test_public_import_never_attaches_to_private_record(self):
        token = self.sign_in()
        repo_id = self.analyze(token).json()["repository_id"]
        self.wait_for(repo_id)
        with patch("app.services.indexing_service.IndexingService.submit_job"):
            res = self.client.post("/api/repositories", json={"url": "https://github.com/octo/private-repo", "branch": "trunk"})
        self.assertEqual(res.status_code, 202)
        self.assertNotEqual(res.json()["repository_id"], repo_id)
        self.assertEqual(get_repository(repo_id).status, "completed")

    def test_ai_features_blocked_for_private_unless_enabled(self):
        token = self.sign_in()
        repo_id = self.analyze(token).json()["repository_id"]
        self.wait_for(repo_id)
        for method, path in [
            ("POST", f"/api/repositories/{repo_id}/ai/chat"),
            ("POST", f"/api/repositories/{repo_id}/chat"),
            ("POST", f"/api/repositories/{repo_id}/clusters/summarize"),
            ("GET", f"/api/repositories/{repo_id}/workflows"),
        ]:
            res = self.client.request(method, path, headers=self.auth(token), json={"question": "hi"} if method == "POST" else None)
            self.assertEqual(res.status_code, 403, path)
            self.assertEqual(res.json()["detail"]["code"], "ai_disabled_for_private_repository")
        # deterministic insights stay available
        self.assertEqual(self.client.get(f"/api/repositories/{repo_id}/insights/health", headers=self.auth(token)).status_code, 200)
        # With the operator opt-in the gate lets the request through to the AI route. AI status is
        # stubbed as "not configured" so this test can never reach a real provider.
        settings.allow_ai_on_private_repos = True
        with patch("app.api.routes.astral_ai.ai_status", return_value={"configured": False, "reason": "stubbed"}):
            res = self.client.post(f"/api/repositories/{repo_id}/ai/chat", headers=self.auth(token), json={"question": "hi"})
        self.assertEqual(res.status_code, 503)
        self.assertEqual(res.json()["detail"]["code"], "ai_not_configured")

    def test_owner_can_delete_and_workspace_is_removed(self):
        token = self.sign_in()
        repo_id = self.analyze(token).json()["repository_id"]
        self.wait_for(repo_id)
        self.assertTrue(settings.get_repo_dir(repo_id).exists())
        res = self.client.delete(f"/api/repositories/{repo_id}", headers=self.auth(token))
        self.assertEqual(res.status_code, 204)
        self.assertIsNone(get_repository(repo_id))
        self.assertFalse(settings.get_repo_dir(repo_id).exists())

    def test_failed_download_cleans_up_and_leaks_no_secrets(self):
        token = self.sign_in()
        self.gh.zipball_status = 404
        tmp = Path(tempfile.gettempdir())
        before = set(tmp.glob("astral_dl_*"))
        res = self.analyze(token)
        repo_id = res.json()["repository_id"]
        self.assertEqual(self.wait_for(repo_id), "failed")
        record = get_repository(repo_id)
        self.assertIn("not found", record.error_message.lower())
        for secret in (INSTALL_TOKEN, USER_TOKEN, "client-secret-value", SIGNED_QUERY):
            self.assertNotIn(secret, record.error_message)
            self.assertNotIn(secret, json.dumps(get_job(record.current_job_id).to_dict()))
        self.assertEqual(set(tmp.glob("astral_dl_*")) - before, set())

    def test_oversized_archive_aborts_and_removes_partial_file(self):
        self.gh.zip_bytes = b"PK" + b"0" * 5000
        dest = Path(self.temp_dir.name) / "big.zip"
        with self.assertRaises(ValueError):
            github_app.download_private_archive(77, "octo", "private-repo", "trunk", dest, max_bytes=1000)
        self.assertFalse(dest.exists())

    def test_redirect_to_untrusted_host_is_refused(self):
        def handler(request: httpx.Request) -> httpx.Response:
            if request.url.path == "/app/installations/77/access_tokens":
                return httpx.Response(201, json={"token": INSTALL_TOKEN})
            return httpx.Response(302, headers={"location": "https://evil.example.com/steal"})

        github_app.set_transport_override(httpx.MockTransport(handler))
        dest = Path(self.temp_dir.name) / "x.zip"
        with self.assertRaises(GitHubError):
            github_app.download_private_archive(77, "octo", "private-repo", "trunk", dest)
        self.assertFalse(dest.exists())


class TestMigration(unittest.TestCase):
    def test_migration_adds_column_and_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            db = Path(tmp) / "old.db"
            conn = sqlite3.connect(db)
            conn.execute("CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, description TEXT NOT NULL, applied_at TEXT NOT NULL)")
            for version, desc, script in database.MIGRATIONS[:2]:
                for stmt in database._split_statements(script):
                    conn.execute(stmt)
                conn.execute("INSERT INTO schema_migrations VALUES (?, ?, 'now')", (version, desc))
            conn.execute(
                "INSERT INTO repositories VALUES ('repo_old','https://github.com/a/b','a','b','main','completed',NULL,'t','t','w','a',NULL)"
            )
            conn.commit()
            conn.close()

            init_db(db)

            repo = get_repository("repo_old", db_path=db)
            self.assertIsNotNone(repo)
            self.assertIsNone(repo.owner_github_user_id)  # legacy rows stay public
            self.assertEqual(database.schema_version(db), len(database.MIGRATIONS))
            init_db(db)  # idempotent
            create_repository("repo_new", "u", "o", "n", "main", "w", "a", db_path=db, owner_github_user_id=5)
            self.assertEqual(get_repository("repo_new", db_path=db).owner_github_user_id, 5)


if __name__ == "__main__":
    unittest.main()
