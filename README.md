# Astral Cartographer

Astral Cartographer is a multi-language codebase intelligence platform that analyzes repositories and constructs an explorable graph of files, classes, functions, imports, and cross-file dependencies.

---

## Architecture Overview

1. **Repository Ingestion & Scanner** (`app.ingestion.scanner`): Inventories repository files, detects languages, hashes files safely, skips sensitive tokens/keys/credentials, and records repository metadata into `repository_inventory.json`.
2. **Python AST Parser** (`app.parsers.python_parser`): Analyzes Python source code into classes, functions, methods, imports, and function calls into `python_analysis.json`.
3. **JavaScript / TypeScript Parser** (`app.parsers.javascript_parser`): Tree-sitter powered parser for JavaScript, JSX, TypeScript, and TSX into `javascript_analysis.json`.
4. **Symbol Resolution & Graph Builder** (`app.graph.graph_builder`, `app.graph.symbol_resolver`): Merges scanner and language analyses into a unified, language-neutral code graph saved to `code_graph.json`.
5. **FastAPI Backend & Indexing Engine** (`app.main`, `app.services.indexing_service`): Provides asynchronous repository ingestion, SQLite-persisted tracking (`astral.db`), secure streaming archive downloads, safe zip extraction, and high-performance REST APIs.

---

## Getting Started

### Prerequisites

- Python 3.10+ (tested on Python 3.10 through 3.14)
- Git

### Installation

Navigate to the `backend/` directory:

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate

# Linux / macOS
source .venv/bin/activate

pip install -r requirements.txt
```

### Configuration

Copy the example environment configuration:

```bash
# In the backend/ directory
copy .env.example .env     # Windows
cp .env.example .env       # Linux / macOS
```

Environment options:
- `ASTRAL_DATA_DIR`: Storage root for database and repository artifacts (default: `./data`).
- `ASTRAL_MAX_ARCHIVE_MB`: Maximum allowed size for downloaded archives (default: `100`).
- `ASTRAL_MAX_EXTRACTED_MB`: Maximum allowed extracted workspace size (default: `500`).
- `ASTRAL_MAX_FILES`: Maximum number of files permitted in an archive (default: `20000`).
- `ASTRAL_MAX_SOURCE_RESPONSE_MB`: Maximum file size served by source reader endpoint (default: `1`).
- `ASTRAL_MAX_CONCURRENT_JOBS`: Maximum concurrent background indexing workers (default: `2`).
- `ASTRAL_CORS_ORIGINS`: Comma-separated list of allowed CORS origins (default: `http://localhost:3000,http://localhost:5173`).

---

## Starting the API Server

From the `backend/` directory, start the server:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### Interactive API Documentation

Once the server is running, explore and test the endpoints interactively via Swagger UI:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

---

## API Endpoints & Usage Guide

### 1. Health Check
```bash
curl -X GET http://127.0.0.1:8000/api/health
```
Response:
```json
{
  "status": "ok",
  "version": "1.0.0",
  "database": "connected"
}
```

### 2. Submit a Public GitHub Repository
```bash
curl -X POST http://127.0.0.1:8000/api/repositories \
  -H "Content-Type: application/json" \
  -d '{"url": "https://github.com/pallets/flask", "branch": "main"}'
```
Response (`202 Accepted`):
```json
{
  "repository_id": "repo_4a8b75c192d3",
  "job_id": "job_1f3b890a5d21",
  "status": "queued",
  "message": "Repository indexing has been queued."
}
```

### 3. Check Job Status & Progress
```bash
curl -X GET http://127.0.0.1:8000/api/jobs/job_1f3b890a5d21
```
Response:
```json
{
  "id": "job_1f3b890a5d21",
  "repository_id": "repo_4a8b75c192d3",
  "status": "running",
  "stage": "parsing_python",
  "progress": 55,
  "started_at": "2026-10-21T12:00:05Z",
  "completed_at": null,
  "error_message": null
}
```

### 4. List Repositories
```bash
curl -X GET "http://127.0.0.1:8000/api/repositories?limit=10&offset=0"
```

### 5. Get Repository Details
```bash
curl -X GET http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3
```

### 6. List Repository Files (Inventory)
```bash
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/files?language=Python"
```

### 7. Read Source File
```bash
# Full file
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/file?path=src/flask/app.py"

# Line range
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/file?path=src/flask/app.py&start_line=1&end_line=50"
```

### 8. Retrieve Code Graph
Returns `409 Conflict` until indexing is completed.
```bash
# Complete graph
curl -X GET http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/graph

# Filter by node type or limit
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/graph?node_type=class&limit=50"
```

### 9. Search Symbols
```bash
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/symbols?q=Flask&limit=20"
```

### 10. Query Dependencies & Callers
```bash
# Outgoing calls/imports from symbol
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/dependencies?symbol_id=src/flask/app.py::Flask:class:1&direction=outgoing&depth=1"

# Incoming callers to symbol
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/dependencies?symbol_id=src/flask/app.py::Flask:class:1&direction=incoming&depth=2"
```

### 11. Impact Analysis
```bash
curl -X GET "http://127.0.0.1:8000/api/repositories/repo_4a8b75c192d3/impact?symbol_id=src/flask/app.py::Flask:class:1&max_depth=3"
```

---

## Security & Operational Safeguards

- **Zip Slip & Path Traversal Prevention**: Every entry in downloaded archives is checked before extraction. Traversal paths (`..`), absolute paths, and Windows drive references are strictly rejected.
- **Symlink Detection**: Symbolic links inside archives are identified via UNIX file attribute flags (`0o120000`) and skipped cleanly to prevent symlink traversal attacks.
- **Archive Bomb Mitigation**: Enforces limits on maximum archive byte size, maximum single file size (25MB), maximum total extracted size, and maximum file count (20,000 files).
- **Source File Isolation**: The source workspace (`data/repositories/<id>/source/`) and artifact directory (`data/repositories/<id>/artifacts/`) are strictly separated. The source file endpoint validates paths against the repository source root and blocks traversal and sensitive configuration files (`.env`, `.git`, `.pem`, etc.).
- **URL & Host Validation**: Ingestion accepts only public HTTPS URLs targeting `github.com`. Redirects are strictly constrained to GitHub archive servers (`codeload.github.com` and `github.com`).
- **No Code Execution**: Static AST analysis and Tree-sitter parsing are purely declarative. Analyzed source code, build files, and package scripts are never executed.
- **Thread Safety & Database Concurrency**: SQLite connections are created per-operation with Write-Ahead Logging (`WAL`) enabled and foreign keys strictly enforced.
- **Crash Recovery**: Interrupted jobs left in `queued` or `running` state upon server restart are automatically recovered and marked as `failed` during startup.

---

## Running the Test Suite

Run the complete test suite (108 tests) from the `backend/` directory:

```bash
python -m unittest discover -s tests -v
```

To run API integration tests specifically:

```bash
python -m unittest tests/test_api.py -v
```

---

## Storage & Artifact Layout

```text
backend/data/
├── astral.db                                     # SQLite persistence
└── repositories/
    └── <repository_id>/
        ├── source/                               # Extracted repository source files
        └── artifacts/
            ├── repository_inventory.json         # Scanner inventory
            ├── python_analysis.json              # Python AST extraction
            ├── javascript_analysis.json          # JS/TS Tree-sitter extraction
            └── code_graph.json                   # Unified language-neutral code graph
```

---

## Known Limitations & Future Roadmap

- **Public Repositories Only**: Private GitHub repository access and OAuth credentials are not supported in this version.
- **In-Process Worker**: Indexing jobs are executed using an in-process thread pool. Distributed worker queues (e.g., Celery/Redis) are planned for a subsequent phase.
- **Languages**: Python AST and JavaScript/TypeScript Tree-sitter parsing are supported. Additional language parsers (Go, Rust, Java) will be added in future steps.
- **Static Analysis Scope**: Dynamic imports and runtime monkey-patching are intentionally not reflected in static graph queries.


---

## Analysis, AI and graph tooling (2026-10 overhaul)

- **Parser**: tree-sitter is pinned to `<0.26` (0.26.0 crashes natively on real JS files). JavaScript now extracts CommonJS
  `require()`, dynamic `import()`, `module.exports`/`exports.x` and `obj.method = function` forms; `tsconfig.json`/`jsconfig.json`
  `baseUrl`/`paths` aliases are honoured; bare package names are never guessed from the repo root.
- **Diagnostics**: `GET /api/repositories/{id}/diagnostics` (persisted per analysis in the `analyses` table) and the Parser tab / Indexing Status tab.
- **Database**: SQLite with versioned migrations (`schema_migrations`); analysis completion is one transaction; `DELETE /api/repositories/{id}`.
- **AI**: configure `GEMINI_API_KEY` (or `ANTHROPIC_API_KEY`) in `backend/.env`. `GET /api/ai/status`, streaming `POST /api/repositories/{id}/ai/chat`,
  plus `/ai/architecture`, `/ai/onboarding`, `/ai/graph-query`, `/ai/advice`, `/ai/impact` and deterministic `/insights/{health,impact,path}`.
- **Tests**: `cd backend && python -m pytest`; `cd frontend && node --test src/services/graphView.test.mjs && npm run build`.


---

## Language support (JSX, TSX, Java, Kotlin, Rust)

Parsers are registered in `backend/app/parsers/registry.py` (one `ParserSpec` per language; the scanner decides the language,
each language has exactly one parser). Java, Kotlin and Rust are tree-sitter adapters built on `parsers/common.py`; resolution
lives in `graph/language_resolvers.py`; the graph builder is language-neutral. Install: `pip install -r backend/requirements.txt`.

| Capability | JSX | TSX | Java | Kotlin | Rust |
|---|---|---|---|---|---|
| Symbols with line/column ranges, deterministic IDs | yes | yes | yes | yes | yes |
| Imports (+ aliases / static / wildcard / `mod`) | yes | yes | yes (static, wildcard) | yes (aliases, wildcard) | yes (`use` trees, aliases, `mod x;`, `pub use` re-exports) |
| Cross-file import resolution | relative, index files, extensions, tsconfig aliases | same | package + FQN | package + FQN + alias | crate-relative module paths, `crate/self/super`, workspace crates via `Cargo.toml` |
| Calls | yes (JSX is **not** a call) | yes (types are not calls) | yes, overloads separated by arity | yes (functions, methods, extensions, companions/objects) | functions, `Type::assoc()`, `.method()` on typed receivers |
| Inheritance edges (`EXTENDS`/`IMPLEMENTS`) | `extends` (incl. `React.Component`) | + `implements`, interface `extends` | yes | yes (classified by the target's kind) | trait impls, supertraits |
| JSX component usage (`RENDERS`) | yes | yes | n/a | n/a | n/a |
| Unresolved / external references recorded | yes | yes | yes | yes | yes (macros never expanded) |

Graph additions: edge types `EXTENDS`, `IMPLEMENTS`, `RENDERS`; optional symbol fields `namespace`, `receiver_type`,
`end_col_offset` (present only for the new languages). Python/JS/TS output is unchanged.

Known limitations: resolution is syntactic (no type inference beyond declared types and `new Foo()` / `Foo::new()`), so calls on
chained or inferred receivers, lambdas, reflection, dependency injection, generated code and macros stay unresolved. Java/Kotlin
fields and properties are not graph nodes (only used for receiver types). Kotlin overloads with default arguments resolve by
argument count only when unambiguous. `tree-sitter-kotlin` 1.1.0 reports a syntax error for members written on the same line as the
class's opening brace (`class A { fun f() {} }`); such files are listed in diagnostics and still yield partial symbols. Python
classes do not yet emit `EXTENDS` edges. Rust: trait-provided/derived methods and generic-bound method dispatch are not modelled.


## Private repositories (GitHub App)

Public URL imports and ZIP uploads are unchanged and need no GitHub credentials. To analyse **private**
repositories, register a GitHub App once (this cannot be automated) and configure the backend.

### One-time GitHub App setup

1. GitHub -> Settings -> Developer settings -> GitHub Apps -> **New GitHub App**.
2. **Callback URL**: `<ASTRAL_PUBLIC_BACKEND_URL>/api/github/callback` (default `http://127.0.0.1:8000/api/github/callback`).
   Tick **Request user authorization (OAuth) during installation** and set the **Setup URL** to the same callback URL.
   Leave **Expire user authorization tokens** enabled. Untick **Webhook -> Active** (no webhooks are used).
3. **Repository permissions** (least privilege, read-only): **Contents: Read-only**, **Metadata: Read-only**. No other
   repository, organization or account permissions.
4. Create the app, then note the **App ID**, **Client ID** and the app **slug** (the name in `github.com/apps/<slug>`);
   **Generate a new client secret** and **Generate a private key** (a `.pem` download).
5. Put the values in `backend/.env` (see `.env.example`): `GITHUB_APP_ID`, `GITHUB_APP_SLUG`, `GITHUB_APP_CLIENT_ID`,
   `GITHUB_APP_CLIENT_SECRET`, and `GITHUB_APP_PRIVATE_KEY_PATH` (or `GITHUB_APP_PRIVATE_KEY` with `
` escapes).
   Set `ASTRAL_PUBLIC_BACKEND_URL` / `ASTRAL_FRONTEND_URL` if you do not run on the defaults.
6. `pip install -r requirements.txt` (adds `PyJWT[crypto]`, needed to sign the App JWT with RS256) and restart the backend.
7. **Install** the app on your account/organization and choose the repositories it may read.

### How it works

Dashboard -> **Connect GitHub** -> GitHub authorization (OAuth `state` validated, single use, 10 min) -> pick an
authorized repository (private/public shown) and branch or commit -> **Analyse**. The backend then:

1. verifies with the user's own GitHub token that they can read the repository, and with the App JWT that the App is installed on it;
2. mints a short-lived installation token limited to that one repository with `contents: read` + `metadata: read`;
3. downloads the zipball inside the indexing job, then runs the **same** safe extraction, parsing, graph and analytics pipeline as public imports
   (`/api/repositories/{id}/graph` etc. return the same shapes).

API: `GET /api/github/status`, `POST /api/github/connect`, `GET /api/github/callback`, `POST|DELETE /api/github/session`,
`GET /api/github/repositories`, `GET /api/github/repositories/{owner}/{repo}/branches`, `POST /api/github/analyze`.

### Security and data handling

- The App private key, client secret, GitHub user tokens and installation tokens never leave the backend process. The
  browser holds only an opaque Astrograph session token (sessionStorage, sent as `Authorization: Bearer`), obtained through
  a one-time ticket bound to the tab that started sign-in. Sessions are in memory: they end on backend restart, after
  `ASTRAL_GITHUB_SESSION_TTL_MINUTES`, or on **Disconnect** (which also revokes the GitHub token).
- A private import is owned by the GitHub user who created it. Every `/api/repositories/{id}/...`, `/api/jobs/{id}...` and
  AI route checks that owner (non-owners and anonymous callers get 404), and the repository list shows only your own. Public
  repositories are unrestricted exactly as before. A public URL import can never attach to a private record.
- Analysed code is never executed. Archive paths, symlinks, file counts and sizes are validated by the existing extractor/limits.
- **Persistence**: the archive is downloaded to a temp file that is deleted right after extraction (also on failure). The extracted
  **source tree and derived graph artifacts are stored on the server disk** under `ASTRAL_DATA_DIR/repositories/<id>/` (needed for the
  source viewer and graph), and metadata in SQLite. `DELETE /api/repositories/{id}` (owner only) removes the records and the whole
  workspace. Nothing is deleted automatically otherwise. Disconnecting GitHub does not delete already-imported repositories.
- **AI**: AI chat, cluster/workflow summaries and other AI routes are **disabled for private repositories** so source, symbol and path
  data are not sent to Gemini/Anthropic. Set `ASTRAL_ALLOW_AI_ON_PRIVATE_REPOS=true` to opt in knowingly.
- Logs and stored job errors contain fixed messages only (no tokens, signed URLs or source). GitHub API rate limits are reported to the user.


## Authentication (email/password + Google)

Sign-in is verified by the backend; the browser only holds an `HttpOnly` session cookie (`astral_session`) that
JavaScript cannot read. There is no demo mode, guest login or client-side credential check any more.

- **Signup** `POST /api/auth/signup`: emails are normalized (NFKC, trimmed, lower-cased) and a database **unique index**
  (`users.email`) guarantees one account per email even under concurrent requests. A duplicate returns 409
  "An account with this email already exists. Please log in instead." Signup does not sign anyone in; the UI moves to the login form.
  Password policy is unchanged: 6-128 characters.
- **Login** `POST /api/auth/login`: passwords are hashed with salted **scrypt** (N=2^15, r=8, p=1; stdlib, no new dependency) and compared in
  constant time. Unknown email, wrong password and Google-only accounts all return the same `Invalid email or password.`
  and cost the same CPU. Limits: 5 failures / 15 min per email and 30 / 15 min per IP (HTTP 429, `Retry-After`).
- **Sessions**: random token in an `HttpOnly`, `SameSite=Lax` cookie (`Secure` when `ASTRAL_FRONTEND_URL` is https); only its SHA-256 is stored in
  `auth_sessions`. `GET /api/auth/me` is how the UI learns who is signed in; `POST /api/auth/logout` deletes the row. State-changing
  auth requests reject a foreign `Origin` (CSRF guard).
- **Google** (`GET /api/auth/google/start` -> Google -> `GET /api/auth/google/callback`): authorization-code flow with PKCE (S256), `state`
  bound to the browser by a cookie, a `nonce`, and `prompt=select_account` so Google always shows the account chooser. The server exchanges the
  code with the client secret and verifies the ID token (RS256 signature against Google's JWKS, issuer, audience, expiry, nonce,
  `email_verified`). Accounts are keyed by Google's stable `sub` in `oauth_identities`; repeat logins resolve to the same user.
  A Google login is **never linked to an existing password account by email alone**; that user is told to log in with their password.
  Linking an existing password account to Google is not implemented (it would need an explicit, authenticated link flow).
- **Not available**: password reset and email verification need a mail service that this project does not have.
  The old Firebase reset/verification calls only existed when Firebase was configured and were never enforced.
- Same-origin requirement: the UI calls `/api/auth/*` on its own origin. Vite proxies `/api` to the backend in `npm run dev` / `preview`; in
  production serve UI and API behind one origin (reverse proxy) and set `ASTRAL_FRONTEND_URL` to that https origin.
- Note: the repository/graph/AI API routes are not gated by this login (unchanged); private GitHub repositories keep their own owner checks.

### Google Cloud Console setup (manual)

1. Create a project -> *APIs & Services* -> *OAuth consent screen* (External; scopes `openid`, `email`, `profile` only).
2. *Credentials* -> *Create credentials* -> *OAuth client ID* -> **Web application**.
3. **Authorized redirect URI**: `http://localhost:5173/api/auth/google/callback` for local dev (or `<ASTRAL_FRONTEND_URL>/api/auth/google/callback`;
   it must match `GOOGLE_REDIRECT_URI` / the default character for character). Add your production https URI too.
4. Put the client ID and secret in `backend/.env` as `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` and restart the backend.


## Quick setup: "Sign in with Google" and "Connect GitHub" on your own computer

Both buttons stay disabled/unavailable until you create your own credentials and put them in `backend/.env`.
Credentials are per-developer and are never committed. Run everything locally with the defaults below
(backend `http://127.0.0.1:8000`, frontend `http://localhost:5173`).

### 0. Start from a working local install

```bash
# backend
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows  (Linux/macOS: source .venv/bin/activate)
pip install -r requirements.txt
copy .env.example .env          # Windows  (Linux/macOS: cp .env.example .env)

# frontend (second terminal)
cd frontend
npm install
```

Make sure `.env` contains `ASTRAL_FRONTEND_URL=http://localhost:5173` and `ASTRAL_PUBLIC_BACKEND_URL=http://127.0.0.1:8000`.

### 1. Sign in with Google

1. Open [Google Cloud Console](https://console.cloud.google.com/) and create (or pick) a project.
2. *APIs & Services* -> *OAuth consent screen*: choose **External**, fill in the app name and your email, and add the scopes
   `openid`, `email`, `profile`. While the app is in "Testing", add your own Google address under **Test users**.
3. *APIs & Services* -> *Credentials* -> *Create credentials* -> *OAuth client ID* -> type **Web application**.
4. Under **Authorized redirect URIs** add exactly: `http://localhost:5173/api/auth/google/callback`
   (it must match character for character, including `localhost` vs `127.0.0.1`).
5. Copy the Client ID and Client secret into `backend/.env`:
   ```env
   GOOGLE_CLIENT_ID=<your-client-id>.apps.googleusercontent.com
   GOOGLE_CLIENT_SECRET=<your-client-secret>
   ```
6. Restart the backend, open `http://localhost:5173` (not `127.0.0.1:5173`) and click **Continue with Google**.

Troubleshooting: `redirect_uri_mismatch` means the URI in step 4 differs from the one you are using; `access_blocked` means your
account is not listed as a test user.

### 2. Connect GitHub (private repositories)

1. GitHub -> *Settings* -> *Developer settings* -> *GitHub Apps* -> **New GitHub App**.
2. Set **Callback URL** and **Setup URL** to `http://127.0.0.1:8000/api/github/callback`, tick
   **Request user authorization (OAuth) during installation**, and untick **Webhook -> Active**.
3. Repository permissions (read-only): **Contents** and **Metadata**. Nothing else.
4. Create the app, then note the **App ID**, **Client ID** and **slug** (the name in `github.com/apps/<slug>`).
   Click **Generate a new client secret** and **Generate a private key** (downloads a `.pem` file; keep it outside the repo).
5. Fill `backend/.env`:
   ```env
   GITHUB_APP_ID=<app id>
   GITHUB_APP_SLUG=<slug>
   GITHUB_APP_CLIENT_ID=<client id>
   GITHUB_APP_CLIENT_SECRET=<client secret>
   GITHUB_APP_PRIVATE_KEY_PATH=C:/path/to/your-app.private-key.pem
   ```
6. Restart the backend, then on your GitHub App's page click **Install App** and choose the repositories it may read.
7. In the web app open the Dashboard -> **Connect GitHub**, authorize, pick a repository and click **Analyse**.

Public repositories never need GitHub credentials; only private-repo access does. See *Private repositories (GitHub App)* and
*Authentication* above for the security details.
