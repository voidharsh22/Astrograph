"""Signup, login, session and Google OIDC tests. Google is mocked at the HTTP layer (no network)."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import time
import unittest
from urllib.parse import parse_qs, urlparse

from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
import httpx
import jwt
from jwt.algorithms import RSAAlgorithm

from app.config import settings
from app.main import app
from app.services import auth_service, google_oidc
from app.storage import database, user_store
from app.storage.database import get_db, init_db

CLIENT_ID = "test-client.apps.googleusercontent.com"
ORIGIN = "http://localhost:5173"
_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
_JWK = json.loads(RSAAlgorithm.to_jwk(_KEY.public_key()))
_JWK.update({"kid": "k1", "alg": "RS256", "use": "sig"})
_OTHER_KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)

GOOD_PASSWORD = "correct horse"
HDR = {"Origin": ORIGIN}


class FakeGoogle:
    """Mocks Google's token and JWKS endpoints; id_token claims are configurable per test."""

    def __init__(self) -> None:
        self.sub, self.email, self.email_verified = "g-sub-111", "gus@example.com", True
        self.name = "Gus Google"
        self.overrides: dict = {}
        self.sign_key = _KEY
        self.token_status = 200
        self.calls: list[httpx.Request] = []
        self.nonce_from_auth_url = ""

    def make_id_token(self) -> str:
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": self.sub,
            "email": self.email, "email_verified": self.email_verified, "name": self.name,
            "iat": now, "exp": now + 3600, "nonce": self.nonce_from_auth_url,
            "picture": "https://lh3.googleusercontent.com/a/x",
        }
        claims.update(self.overrides)
        claims = {k: v for k, v in claims.items() if v is not None}
        return jwt.encode(claims, self.sign_key, algorithm="RS256", headers={"kid": "k1"})

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        if request.url.path == "/token":
            if self.token_status != 200:
                return httpx.Response(self.token_status, json={"error": "invalid_grant"})
            return httpx.Response(200, json={"id_token": self.make_id_token(), "access_token": "ya29.x"})
        if request.url.path == "/oauth2/v3/certs":
            return httpx.Response(200, json={"keys": [_JWK]})
        return httpx.Response(404)


class AuthTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.saved = {k: getattr(settings, k) for k in ("data_dir", "google_client_id", "google_client_secret", "_google_redirect_uri", "frontend_url")}
        settings.data_dir = Path(self.tmp.name).resolve() / "data"
        settings.ensure_directories()
        settings.frontend_url = ORIGIN
        settings.google_client_id, settings.google_client_secret = CLIENT_ID, "client-secret-xyz"
        settings._google_redirect_uri = ""
        init_db()
        auth_service.clear_rate_limits()
        google_oidc.clear_flows()
        self.google = FakeGoogle()
        google_oidc.set_transport_override(httpx.MockTransport(self.google.handler))
        self.client = TestClient(app)

    def tearDown(self) -> None:
        google_oidc.set_transport_override(None)
        google_oidc.clear_flows()
        for k, v in self.saved.items():
            setattr(settings, k, v)
        try:
            self.tmp.cleanup()
        except Exception:
            pass

    def signup(self, email="Dev@Example.com", password=GOOD_PASSWORD, name="Dev Eloper", client=None):
        return (client or self.client).post("/api/auth/signup", json={"email": email, "password": password, "name": name}, headers=HDR)

    def login(self, email="dev@example.com", password=GOOD_PASSWORD, client=None):
        return (client or self.client).post("/api/auth/login", json={"email": email, "password": password}, headers=HDR)

    @staticmethod
    def count_users(email=None) -> int:
        with get_db() as conn:
            if email:
                return conn.execute("SELECT COUNT(*) c FROM users WHERE email = ?", (email,)).fetchone()["c"]
            return conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]

    # --- Google helper: run start -> (Google) -> callback with a fresh client (own cookie jar)
    def google_login(self, client=None, **callback_overrides):
        c = client or TestClient(app)
        start = c.get("/api/auth/google/start", follow_redirects=False)
        self.assertEqual(start.status_code, 302)
        q = parse_qs(urlparse(start.headers["location"]).query)
        self.google.nonce_from_auth_url = q["nonce"][0]
        params = {"code": "auth-code", "state": q["state"][0]}
        params.update(callback_overrides)
        params = {k: v for k, v in params.items() if v is not None}
        cb = c.get("/api/auth/google/callback", params=params, follow_redirects=False)
        return c, cb


class TestSignup(AuthTestBase):
    def test_creates_account_with_hashed_password_and_no_session(self):
        res = self.signup()
        self.assertEqual(res.status_code, 201, res.text)
        self.assertEqual(res.json()["email"], "dev@example.com")  # normalized
        self.assertNotIn("password", json.dumps(res.json()).lower())
        self.assertNotIn("astral_session", res.cookies)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        stored = user_store.get_user_by_email("dev@example.com").password_hash
        self.assertTrue(stored.startswith("scrypt$"))
        self.assertNotIn(GOOD_PASSWORD, stored)
        # Salted: the same password hashes differently per account.
        self.signup(email="other@example.com")
        self.assertNotEqual(stored, user_store.get_user_by_email("other@example.com").password_hash)

    def test_duplicate_email_rejected_with_exact_message_in_any_casing(self):
        self.assertEqual(self.signup().status_code, 201)
        for variant in ("dev@example.com", "DEV@EXAMPLE.COM", "  Dev@Example.com  "):
            res = self.signup(email=variant, password="another pass")
            self.assertEqual(res.status_code, 409, variant)
            self.assertEqual(res.json()["detail"]["message"], "An account with this email already exists. Please log in instead.")
            self.assertNotIn("astral_session", res.cookies)
        self.assertEqual(self.count_users(), 1)
        # The original password still works, so the duplicate attempt changed nothing.
        self.assertEqual(self.login().status_code, 200)

    def test_database_enforces_uniqueness_independently_of_the_api(self):
        user_store.create_user("a@example.com", "A", "hash")
        with self.assertRaises(user_store.DuplicateEmailError):
            user_store.create_user("a@example.com", "A2", "hash2")
        with self.assertRaises(sqlite3.IntegrityError):
            with get_db() as conn:
                conn.execute("INSERT INTO users (id,email,name,created_at) VALUES ('x','a@example.com','n','t')")

    def test_concurrent_duplicate_signups_create_exactly_one_user(self):
        results: list[int] = []
        barrier = threading.Barrier(8)

        def worker() -> None:
            c = TestClient(app)
            barrier.wait()
            results.append(self.signup(email="race@example.com", client=c).status_code)

        threads = [threading.Thread(target=worker) for _ in range(8)]
        [t.start() for t in threads]
        [t.join() for t in threads]
        self.assertEqual(results.count(201), 1, results)
        self.assertEqual(results.count(409), 7, results)
        self.assertEqual(self.count_users("race@example.com"), 1)

    def test_invalid_input_rejected(self):
        cases = [
            dict(email="not-an-email"), dict(email=""), dict(password="123"), dict(password=""),
            dict(password="x" * 129), dict(name="a"), dict(name=""),
        ]
        for case in cases:
            res = self.signup(**case)
            self.assertEqual(res.status_code, 400, case)
        self.assertEqual(self.count_users(), 0)

    def test_signup_is_rate_limited(self):
        codes = [self.signup(email=f"u{i}@example.com").status_code for i in range(12)]
        self.assertEqual(codes[:10], [201] * 10)
        self.assertEqual(codes[10:], [429, 429])

    def test_cross_origin_signup_is_rejected(self):
        res = self.client.post("/api/auth/signup", json={"email": "x@example.com", "password": GOOD_PASSWORD, "name": "Xx"},
                               headers={"Origin": "https://evil.example"})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(self.count_users(), 0)


class TestLogin(AuthTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.signup()

    def test_correct_credentials_establish_session_that_survives_reload(self):
        res = self.login(email="DEV@example.com")
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()["user"]
        self.assertEqual(body["email"], "dev@example.com")
        self.assertNotIn("hash", json.dumps(body).lower())
        self.assertNotIn("password_hash", body)
        cookie = res.headers["set-cookie"].lower()
        self.assertIn("httponly", cookie)
        self.assertIn("samesite=lax", cookie)
        self.assertNotIn("secure", cookie)  # http dev origin; Secure is enforced for https origins
        me = self.client.get("/api/auth/me")  # "page refresh": the cookie jar is the only state
        self.assertEqual(me.status_code, 200)
        self.assertEqual(me.json()["user"]["email"], "dev@example.com")

    def test_secure_cookie_flag_for_https_deployments(self):
        settings.frontend_url = "https://astrograph.example"
        c = TestClient(app, base_url="https://astrograph.example")
        res = c.post("/api/auth/login", json={"email": "dev@example.com", "password": GOOD_PASSWORD},
                     headers={"Origin": "https://astrograph.example"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("secure", res.headers["set-cookie"].lower())

    def test_wrong_password_and_unknown_email_get_identical_generic_error(self):
        wrong = self.login(password="wrong-password")
        unknown = self.login(email="nobody@example.com")
        for res in (wrong, unknown):
            self.assertEqual(res.status_code, 401)
            self.assertEqual(res.json()["detail"]["message"], "Invalid email or password.")
            self.assertNotIn("set-cookie", res.headers)
        self.assertEqual(wrong.json(), unknown.json())
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)

    def test_missing_credentials_rejected(self):
        for payload in ({}, {"email": "dev@example.com"}, {"password": GOOD_PASSWORD}, {"email": "", "password": ""}):
            res = self.client.post("/api/auth/login", json=payload, headers=HDR)
            self.assertEqual(res.status_code, 400, payload)
            self.assertNotIn("set-cookie", res.headers)

    def test_google_only_account_cannot_log_in_with_empty_or_arbitrary_password(self):
        self.google_login()
        self.assertIsNone(user_store.get_user_by_email("gus@example.com").password_hash)
        for pw in ("", "anything", "None", "null"):
            res = self.login(email="gus@example.com", password=pw)
            self.assertIn(res.status_code, (400, 401), repr(pw))
            self.assertNotIn("set-cookie", res.headers)

    def test_stored_hash_is_never_plain_and_bad_hash_never_verifies(self):
        self.assertFalse(auth_service.verify_password("x", None))
        self.assertFalse(auth_service.verify_password("", None))
        self.assertFalse(auth_service.verify_password("x", "plaintext"))
        self.assertTrue(auth_service.verify_password(GOOD_PASSWORD, user_store.get_user_by_email("dev@example.com").password_hash))

    def test_brute_force_is_rate_limited_per_account(self):
        codes = [self.login(password=f"guess{i}").status_code for i in range(6)]
        self.assertEqual(codes[:5], [401] * 5)
        self.assertEqual(codes[5], 429)
        # Even the correct password is refused while locked out (no oracle for the attacker).
        res = self.login()
        self.assertEqual(res.status_code, 429)
        self.assertIn("retry-after", res.headers)

    def test_successful_login_resets_failure_counter(self):
        for i in range(4):
            self.login(password=f"bad{i}")
        self.assertEqual(self.login().status_code, 200)
        self.assertEqual([self.login(password="bad").status_code for _ in range(4)], [401] * 4)

    def test_logout_invalidates_the_server_side_session(self):
        self.login()
        token = self.client.cookies.get("astral_session")
        self.assertEqual(self.client.post("/api/auth/logout", headers=HDR).status_code, 204)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        # Replaying the old cookie value must not work: the session row is gone.
        replay = TestClient(app)
        replay.cookies.set("astral_session", token)
        self.assertEqual(replay.get("/api/auth/me").status_code, 401)

    def test_expired_and_forged_sessions_are_rejected(self):
        self.login()
        with get_db() as conn:
            conn.execute("UPDATE auth_sessions SET expires_at = ?", (time.time() - 1,))
        self.assertEqual(self.client.get("/api/auth/me").status_code, 401)
        forged = TestClient(app)
        forged.cookies.set("astral_session", "not-a-real-token")
        self.assertEqual(forged.get("/api/auth/me").status_code, 401)

    def test_logout_requires_same_origin(self):
        self.login()
        self.assertEqual(self.client.post("/api/auth/logout", headers={"Origin": "https://evil.example"}).status_code, 403)
        self.assertEqual(self.client.get("/api/auth/me").status_code, 200)


class TestGoogleOIDC(AuthTestBase):
    def test_start_redirects_to_google_with_account_chooser_pkce_and_state(self):
        res = TestClient(app).get("/api/auth/google/start", follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        url = urlparse(res.headers["location"])
        self.assertEqual((url.scheme, url.netloc, url.path), ("https", "accounts.google.com", "/o/oauth2/v2/auth"))
        q = {k: v[0] for k, v in parse_qs(url.query).items()}
        self.assertEqual(q["prompt"], "select_account")
        self.assertEqual(q["response_type"], "code")
        self.assertEqual(q["scope"], "openid email profile")
        self.assertEqual(q["client_id"], CLIENT_ID)
        self.assertEqual(q["code_challenge_method"], "S256")
        self.assertEqual(q["redirect_uri"], f"{ORIGIN}/api/auth/google/callback")
        for required in ("state", "nonce", "code_challenge"):
            self.assertTrue(q[required])
        self.assertNotIn("client_secret", res.headers["location"])
        self.assertIn("httponly", res.headers["set-cookie"].lower())
        self.assertEqual(self.google.calls, [])  # nothing authenticated just by clicking

    def test_unconfigured_google_never_signs_anyone_in(self):
        settings.google_client_id = ""
        self.assertFalse(self.client.get("/api/auth/config").json()["google"])
        res = TestClient(app).get("/api/auth/google/start", follow_redirects=False)
        self.assertIn("auth_error=google_not_configured", res.headers["location"])
        self.assertNotIn("accounts.google.com", res.headers["location"])

    def test_valid_callback_verifies_server_side_then_creates_user_and_session(self):
        c, cb = self.google_login()
        self.assertEqual(cb.status_code, 302)
        self.assertTrue(cb.headers["location"].endswith("/dashboard"))
        self.assertEqual(c.get("/api/auth/me").json()["user"]["email"], "gus@example.com")
        exchange = [r for r in self.google.calls if r.url.path == "/token"][0]
        form = parse_qs(exchange.content.decode())
        self.assertEqual(form["client_secret"], ["client-secret-xyz"])  # secret used only server-side
        self.assertIn("code_verifier", form)
        user = user_store.get_user_by_identity("google", "g-sub-111")
        self.assertIsNotNone(user)

    def test_repeated_google_login_resolves_to_same_user_even_if_email_changes(self):
        c1, _ = self.google_login()
        first = c1.get("/api/auth/me").json()["user"]["id"]
        self.google.email = "renamed@example.com"
        c2, _ = self.google_login()
        self.assertEqual(c2.get("/api/auth/me").json()["user"]["id"], first)
        self.assertEqual(self.count_users(), 1)

    def test_same_email_different_google_subject_is_not_linked_by_email(self):
        self.signup(email="gus@example.com")  # existing password account for that email
        c, cb = self.google_login()
        self.assertIn("auth_error=google_email_in_use", cb.headers["location"])
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.count_users(), 1)
        self.assertIsNone(user_store.get_user_by_identity("google", "g-sub-111"))

    def test_invalid_state_and_missing_cookie_rejected_without_contacting_google(self):
        c, cb = self.google_login(state="forged-state")
        self.assertIn("auth_error=google_invalid_state", cb.headers["location"])
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual([r for r in self.google.calls if r.url.path == "/token"], [])
        # Valid state but from a different browser (no state cookie) = login CSRF -> rejected.
        start = TestClient(app).get("/api/auth/google/start", follow_redirects=False)
        state = parse_qs(urlparse(start.headers["location"]).query)["state"][0]
        victim = TestClient(app)
        cb2 = victim.get("/api/auth/google/callback", params={"code": "c", "state": state}, follow_redirects=False)
        self.assertIn("auth_error=google_invalid_state", cb2.headers["location"])
        self.assertEqual(victim.get("/api/auth/me").status_code, 401)

    def test_state_cannot_be_replayed(self):
        c = TestClient(app)
        start = c.get("/api/auth/google/start", follow_redirects=False)
        q = parse_qs(urlparse(start.headers["location"]).query)
        self.google.nonce_from_auth_url = q["nonce"][0]
        params = {"code": "c", "state": q["state"][0]}
        first = c.get("/api/auth/google/callback", params=params, follow_redirects=False)
        self.assertTrue(first.headers["location"].endswith("/dashboard"))
        # Same state again with the state cookie still present (attacker replays the callback URL).
        c.cookies.set("astral_oauth_state", q["state"][0], path="/api/auth")
        replay = c.get("/api/auth/google/callback", params=params, follow_redirects=False)
        self.assertIn("auth_error=google_invalid_state", replay.headers["location"])

    def test_bad_id_tokens_are_rejected(self):
        cases = {
            "expired": ({"exp": int(time.time()) - 3600, "iat": int(time.time()) - 7200}, "google_token_expired"),
            "wrong audience": ({"aud": "someone-else"}, "google_invalid_token"),
            "wrong issuer": ({"iss": "https://evil.example"}, "google_invalid_token"),
            "wrong nonce": ({"nonce": "attacker-nonce"}, "google_invalid_token"),
            "unverified email": ({"email_verified": False}, "google_email_unverified"),
            "no subject": ({"sub": None}, "google_invalid_token"),
            "no email": ({"email": None}, "google_invalid_token"),
        }
        for label, (overrides, code) in cases.items():
            self.google.overrides = overrides
            c, cb = self.google_login()
            self.assertIn(f"auth_error={code}", cb.headers["location"], label)
            self.assertEqual(c.get("/api/auth/me").status_code, 401, label)
        self.assertEqual(self.count_users(), 0)

    def test_token_signed_with_wrong_key_or_alg_none_is_rejected(self):
        self.google.sign_key = _OTHER_KEY
        c, cb = self.google_login()
        self.assertIn("auth_error=google_invalid_token", cb.headers["location"])
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        unsigned = jwt.encode({"iss": "https://accounts.google.com", "aud": CLIENT_ID, "sub": "x", "email": "x@example.com",
                               "email_verified": True, "exp": int(time.time()) + 600, "iat": int(time.time())}, None, algorithm="none")
        with self.assertRaises(google_oidc.GoogleAuthError):
            google_oidc.verify_id_token(unsigned, "n")

    def test_provider_errors_and_cancellation_do_not_sign_in(self):
        c, cb = self.google_login(code=None, error="access_denied")
        self.assertIn("auth_error=google_cancelled", cb.headers["location"])
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        c, cb = self.google_login(code=None, error="server_error")
        self.assertIn("auth_error=google_failed", cb.headers["location"])
        self.google.token_status = 400
        c, cb = self.google_login()
        self.assertIn("auth_error=google_exchange_failed", cb.headers["location"])
        self.assertEqual(c.get("/api/auth/me").status_code, 401)
        self.assertEqual(self.count_users(), 0)


class TestMigrationAndRegression(AuthTestBase):
    def test_users_migration_is_additive_and_idempotent(self):
        before = database.schema_version()
        init_db()
        self.assertEqual(database.schema_version(), before)
        with get_db() as conn:
            tables = {r["name"] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"users", "oauth_identities", "auth_sessions", "repositories", "analyses"} <= tables)

    def test_existing_public_api_still_works_without_a_login(self):
        self.assertEqual(self.client.get("/api/health").status_code, 200)
        self.assertEqual(self.client.get("/api/repositories").status_code, 200)
        self.assertEqual(self.client.get("/api/auth/config").status_code, 200)


if __name__ == "__main__":
    unittest.main()
