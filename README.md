# Astral Cartographer — Backend & AI Engine 🌌

**Astral Cartographer** ingests GitHub repositories and converts their codebase structure, module dependencies, and execution workflows into interactive 3D celestial visualizations (*galaxies*, *solar systems*, *stars*, *planets*, and *moons*).

It combines:
- **Compiler-Grade Static Analysis**: Native Python `ast` + compiled **`tree-sitter`** for JavaScript & TypeScript.
- **Deep Symbol Resolution Engine**: 4-tier resolution (`resolved`, `ambiguous`, `external`, `unresolved`) with built-in runtime globals tracking.
- **3D Spatial Geometry & Graph Theory**: NetworkX PageRank centrality, Louvain community detection, and deterministic 3D spherical/spiral coordinates for Three.js.
- **Multi-Tenant SQLite Job Queue**: Asynchronous indexing pipeline with progress tracking in `astral.db`.
- **Zero-Trust Security**: Zip-Slip path traversal rejection, symlink mitigation, and decompression bomb size guards.
- **LangGraph + Gemini Agent Layer**: Codebase Q&A with 3D camera flight targeting, zoom-out cluster summaries, and glowing pulse execution workflow tracing.

---

## 📁 Repository File Structure

```text
astral-cartographer/
├── .gitignore                      # Git ignore patterns for Python, caches, and envs
├── README.md                       # Main project overview and instructions
├── docs/                           # Architecture, schema, and API documentation
│   ├── ARCHITECTURE.md             # System design, AST pipeline, graph topology
│   ├── API_REFERENCE.md            # REST endpoints, WebSocket protocol, schemas
│   └── Astral_Cartographer_Deep_Dive_Architecture_and_Interview_Report.pdf # 11-page technical dossier
└── backend/                        # Backend FastAPI service
    ├── .env.example                # Example environment variables
    ├── pytest.ini                  # Pytest configuration
    ├── README.md                   # Backend quick-start guide
    ├── requirements.txt            # Production dependencies
    ├── requirements-dev.txt        # Development & test dependencies
    ├── app/
    │   ├── __init__.py
    │   ├── config.py               # Pydantic v2 application settings
    │   ├── main.py                 # FastAPI application factory and middleware
    │   ├── agents/                 # AI & LLM workflow summarization
    │   │   ├── __init__.py
    │   │   ├── cluster_agent.py    # Galaxy cluster summarizer agent
    │   │   ├── graph_tools.py      # LangChain grounding tools
    │   │   ├── qa_agent.py         # Codebase Q&A with 3D camera flight targeting
    │   │   ├── workflow_agent.py   # High-level workflow enrichment pipeline
    │   │   └── workflow_tracing_agent.py # Glowing pulse execution path tracer
    │   ├── api/                    # REST routing
    │   │   ├── __init__.py
    │   │   └── v1/
    │   │       ├── __init__.py
    │   │       ├── analyze.py       # Cluster & workflow analysis routes
    │   │       ├── chat.py          # Semantic Q&A route
    │   │       ├── graph.py         # 3D demo & analyze routes
    │   │       ├── health.py        # Liveness & version probe
    │   │       ├── jobs.py          # Background indexing job status polling
    │   │       ├── repositories.py  # Repository management, impact & dependencies
    │   │       └── router.py        # Aggregated v1 API router
    │   ├── data/                   # Static data assets
    │   │   └── demo_galaxy.json     # Pre-computed sample galaxy for frontend
    │   ├── schemas/                # Pydantic models & deterministic schemas
    │   │   ├── __init__.py
    │   │   ├── chat_schema.py      # Q&A request and response schemas
    │   │   ├── common.py           # Core enums and base types
    │   │   ├── graph_schema.py     # Nodes, Edges, Metrics, AstralGraph schema
    │   │   └── requests.py         # Ingestion & analysis request models
    │   ├── services/               # Core domain services
    │   │   ├── __init__.py
    │   │   ├── archive_extractor.py# Safe zip extraction (Zip-Slip defense)
    │   │   ├── cartographer.py     # NetworkX graph builder, PageRank, Louvain
    │   │   ├── downloader.py       # Streaming GitHub archive downloader
    │   │   ├── graph_queries.py    # Dependency traversal & impact analysis
    │   │   ├── graph_store.py      # In-memory dual-state store & query index
    │   │   ├── indexing_service.py # Background indexing pipeline orchestrator
    │   │   ├── ingestor.py         # Git clone, noise filter, language detect
    │   │   ├── symbol_resolver.py  # Deep symbol & call resolution engine
    │   │   └── parsers/            # Static code analysis parsers
    │   │       ├── __init__.py
    │   │       ├── base.py         # Abstract base parser interface
    │   │       ├── js_parser.py    # Fallback JS/TS regex parser
    │   │       ├── python_parser.py# Python ast parser (classes, functions, calls)
    │   │       └── treesitter_js_parser.py # Tree-sitter JS/TS/TSX parser
    │   └── storage/                # Persistent database & artifact cache
    │       ├── __init__.py
    │       ├── database.py         # SQLite connection manager & migrations
    │       └── repository_store.py # Repository CRUD & job tracking
    ├── scripts/                    # Diagnostic & verification utilities
    │   └── verify_all_features.py  # Live end-to-end 13-subsystem test runner
    └── tests/                      # Automated test suite (139 passing tests)
        ├── __init__.py
        ├── conftest.py             # Test fixtures & configuration
        ├── test_advanced_engine.py # Tree-sitter, symbol resolver, security tests
        ├── test_analyze_agents.py  # Cluster & workflow agent tests
        ├── test_analyze_endpoint.py# Analysis initiation endpoint tests
        ├── test_cartographer.py    # Graph metrics, Louvain, PageRank tests
        ├── test_chat_endpoint.py   # Chat endpoint tests
        ├── test_graph_demo.py      # Demo graph API tests
        ├── test_health.py          # Health endpoint tests
        ├── test_ingestor.py        # Git cloning & noise filtering tests
        ├── test_parsers.py         # Python & JS parser unit tests
        ├── test_qa_agent.py        # Q&A agent tests
        ├── test_schemas.py         # Graph schema validation tests
        └── test_workflow_agent.py  # LangGraph pipeline & workflow tests
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Git installed on your system

### 2. Setup Virtual Environment

```bash
cd backend
python -m venv .venv

# On Windows (PowerShell):
.venv\Scripts\Activate.ps1

# On macOS/Linux:
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 4. Configure Environment Variables

```bash
cp .env.example .env
```
*(Optional)* Set `GEMINI_API_KEY` for live AI agent synthesis.

### 5. Run the API Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🧪 Testing & Verification

Run the full automated test suite:

```bash
cd backend
pytest -v
```
All **139 tests** execute with 0 failures and 0 warnings.

Run the live functional diagnostic runner:

```bash
python scripts/verify_all_features.py
```

---

## 🌐 Complete API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe and service version |
| `GET` | `/api/v1/graph/demo` | Serves mock 3D galaxy JSON for Frontend (Three.js) |
| `POST` | `/api/v1/graph/analyze` | Ingests a public GitHub repo, parses AST, computes 3D coordinates |
| `POST` | `/api/v1/repositories` | Asynchronously queues a repository for background indexing (`202 Accepted`) |
| `GET` | `/api/v1/jobs/{job_id}` | Polls background indexing progress percentage and current stage |
| `GET` | `/api/v1/repositories` | Lists all indexed repositories with pagination |
| `GET` | `/api/v1/repositories/{id}` | Retrieves metadata and status for a specific repository |
| `GET` | `/api/v1/repositories/{id}/graph` | Retrieves the full 3D `AstralGraph` JSON for an indexed repository |
| `GET` | `/api/v1/repositories/{id}/dependencies` | Queries incoming/outgoing dependencies for a node up to depth $N$ |
| `GET` | `/api/v1/repositories/{id}/impact` | Computes architectural blast radius analysis for a modified node |
| `POST` | `/api/v1/chat` | Natural language Q&A with 3D camera flight targeting coordinates |
| `POST` | `/api/v1/analyze/clusters` | Batch synthesizes AI module summaries for 3D zoom-out view |
| `POST` | `/api/v1/analyze/workflows` | Traces execution pathways for animated 3D glowing pulses |

---

## 📄 Documentation & Dossier

For complete architectural details, consult:
* **[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)**: System design, AST pipeline, and graph topology.
* **[docs/API_REFERENCE.md](docs/API_REFERENCE.md)**: Detailed request/response payloads.
* **[Astral Cartographer Deep Dive & Interview Dossier (PDF)](docs/Astral_Cartographer_Deep_Dive_Architecture_and_Interview_Report.pdf)**: 11-page technical report and judge defense Q&A.
