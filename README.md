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
