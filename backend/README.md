# Astral Cartographer — Backend & AI Engine 🌌

**Astral Cartographer** ingests GitHub repositories and converts their codebase structure, module dependencies, and execution pathways into interactive 3D celestial visualizations (*galaxies*, *solar systems*, *stars*, *planets*, and *moons*).

It combines:
- **Compiler-Grade Static Analysis**: Native Python `ast` + compiled **`tree-sitter`** for JavaScript & TypeScript.
- **Deep Symbol Resolution Engine**: 4-tier resolution (`resolved`, `ambiguous`, `external`, `unresolved`) with built-in runtime globals tracking.
- **3D Spatial Geometry & Graph Theory**: NetworkX PageRank centrality, Louvain community detection, and deterministic 3D spherical/spiral coordinates for Three.js.
- **Multi-Tenant SQLite Job Queue**: Asynchronous indexing pipeline with progress tracking in `astral.db`.
- **Zero-Trust Security**: Zip-Slip path traversal rejection, symlink mitigation, and decompression bomb size guards.
- **LangGraph + Gemini Agent Layer**: Codebase Q&A with 3D camera flight targeting, zoom-out cluster summaries, and glowing pulse execution workflow tracing.

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.11+
- Git installed on your system

### 2. Setup Virtual Environment

```bash
# In the backend directory
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
*(Optional)* Add your `GEMINI_API_KEY` to enable live LLM synthesis.

### 5. Start the API Server

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```
- **Interactive Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc Documentation**: [http://localhost:8000/redoc](http://localhost:8000/redoc)

---

## 🌐 Complete REST API Reference

All routes are mounted under the `/api/v1` prefix:

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/api/v1/health` | Liveness probe and version check |
| `GET` | `/api/v1/graph/demo` | Serves pre-computed 3D galaxy graph JSON for Three.js frontend testing |
| `POST` | `/api/v1/graph/analyze` | Ingests a public repo, runs AST extraction, calculates PageRank & 3D coordinates |
| `POST` | `/api/v1/repositories` | Asynchronously queues a repository for background indexing (`202 Accepted`) |
| `GET` | `/api/v1/jobs/{job_id}` | Polls background indexing progress percentage and current stage |
| `GET` | `/api/v1/repositories` | Lists all indexed repositories with pagination |
| `GET` | `/api/v1/repositories/{id}` | Retrieves metadata and status for a specific repository |
| `GET` | `/api/v1/repositories/{id}/graph` | Retrieves the full 3D `AstralGraph` JSON for an indexed repository |
| `GET` | `/api/v1/repositories/{id}/dependencies` | Queries incoming/outgoing dependencies for a node up to depth $N$ |
| `GET` | `/api/v1/repositories/{id}/impact` | Computes architectural blast radius analysis for a modified node |
| `POST` | `/api/v1/chat` | Semantic Q&A with 3D camera flight targeting coordinates |
| `POST` | `/api/v1/analyze/clusters` | Batch synthesizes AI module summaries for 3D zoom-out views |
| `POST` | `/api/v1/analyze/workflows` | Traces execution pathways for animated 3D glowing pulses |

---

## 🧪 Running Automated Tests

Run the full automated test suite (139 passing tests):

```bash
pytest -v
```

Run the live end-to-end diagnostic verification across all 13 core features:

```bash
python scripts/verify_all_features.py
```

---

## 🌌 Frontend 3D Integration

Point your Three.js / React Three Fiber data loader at:
```text
http://localhost:8000/api/v1/graph/demo
```
or fetch an analyzed repository directly via:
```text
http://localhost:8000/api/v1/repositories/{repo_id}/graph
```
Each node in `AstralGraph.nodes` provides:
* `position_hint`: Louvain `cluster_id`, tree `depth`
* `metrics`: PageRank `centrality` ($0.0 \le \text{centrality} \le 1.0$), Lines of Code (`loc`), `complexity`
* `ai_summary`: Synthesized plain-English architectural description
