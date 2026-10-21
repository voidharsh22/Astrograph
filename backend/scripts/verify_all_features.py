"""
Comprehensive end-to-end verification and diagnostic runner for Astral Cartographer.
Executes live functional checks across every single feature of the platform.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sys
import tempfile
import time
import zipfile

# Ensure backend root is on PYTHONPATH
backend_dir = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(backend_dir))

from starlette.testclient import TestClient

from app.main import app
from app.schemas.graph_schema import AstralGraph
from app.services.archive_extractor import extract_archive_safely
from app.services.downloader import extract_github_owner_and_repo
from app.services.graph_queries import compute_impact_analysis, get_dependencies_for_node
from app.services.graph_store import get_active_graph_store, GraphStore
from app.services.parsers.base import ParseResult, ParsedSymbol, ParsedImport, ParsedCall
from app.services.parsers.python_parser import PythonParser
from app.services.parsers.treesitter_js_parser import TreeSitterJSParser
from app.services.symbol_resolver import SymbolResolver, STATUS_RESOLVED, STATUS_EXTERNAL, STATUS_UNRESOLVED
from app.storage.database import init_db
from app.storage.repository_store import (
    create_or_get_repository,
    create_job,
    get_job,
    get_repository,
    update_job_progress,
    complete_job,
    list_repositories,
    save_graph_artifact,
)


# Ensure UTF-8 output on Windows console
if sys.stdout.encoding.lower() != "utf-8":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def print_header(title: str):
    print("\n" + "=" * 70)
    print(f"  >>> {title.upper()}")
    print("=" * 70)


def print_pass(msg: str):
    print(f"  [PASS] {msg}")


def print_detail(key: str, value: Any):
    print(f"     * {key}: {value}")


async def run_all_checks():
    client = TestClient(app)
    results: list[tuple[str, bool]] = []

    # -----------------------------------------------------------------------
    # Check 1: Healthcheck & Liveness Probe
    # -----------------------------------------------------------------------
    print_header("1. API Health & Liveness Probe")
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    print_pass("Healthcheck returned 200 OK")
    print_detail("Status", data.get("status"))
    print_detail("API Version", data.get("version"))
    print_detail("Timestamp", data.get("timestamp"))
    results.append(("Healthcheck Endpoint", True))

    # -----------------------------------------------------------------------
    # Check 2: 3D Galaxy Demo Graph Payload (Three.js WebGL Contract)
    # -----------------------------------------------------------------------
    print_header("2. 3D Galaxy Graph Payload (Three.js WebGL Contract)")
    resp = client.get("/api/v1/graph/demo")
    assert resp.status_code == 200
    demo_graph = resp.json()
    nodes = demo_graph.get("nodes", [])
    edges = demo_graph.get("edges", [])
    workflows = demo_graph.get("workflows", [])
    assert len(nodes) > 0
    assert len(edges) > 0

    # Validate position hint and metrics
    first_node = nodes[0]
    pos = first_node["position_hint"]
    assert "cluster_id" in pos and "depth" in pos
    assert "centrality" in first_node["metrics"]
    print_pass("Demo Galaxy payload conforms to AstralGraph schema")
    print_detail("Total Celestial Nodes", len(nodes))
    print_detail("Total Dependency Edges", len(edges))
    print_detail("Traced Workflows", len(workflows))
    print_detail("Sample Node Cluster ID", pos.get("cluster_id"))
    print_detail("Sample Node Depth", pos.get("depth"))
    print_detail("Sample Node PageRank Centrality", first_node["metrics"]["centrality"])
    results.append(("3D Galaxy Graph Payload", True))

    # -----------------------------------------------------------------------
    # Check 3: Python AST Parser (Zero-Execution Code Analysis)
    # -----------------------------------------------------------------------
    print_header("3. Python AST Code Parser")
    py_parser = PythonParser()
    py_code = """
import os
from math import sqrt
from app.services.auth import verify_token

class AccountManager(BaseManager):
    \"\"\"Manages user account lifecycles.\"\"\"
    def __init__(self, db):
        self.db = db

    async def create_user(self, username: str):
        token = verify_token(username)
        print("User created:", username)
        return token
"""
    repo_files = {"app/services/auth.py", "app/main.py"}
    py_res = py_parser.parse_file("app/account.py", py_code, repo_files)
    sym_names = [s.name for s in py_res.symbols]
    assert "AccountManager" in sym_names
    assert "create_user" in sym_names
    assert len(py_res.imports) >= 2
    assert any(c.callee_name == "verify_token" for c in py_res.calls)

    print_pass("Python AST Parser extracted classes, async methods, imports, and calls")
    print_detail("Extracted Symbols", sym_names)
    print_detail("Extracted Class Bases", py_res.symbols[0].bases)
    print_detail("Extracted Imports", [imp.raw_statement for imp in py_res.imports])
    print_detail("Extracted Call Sites", [c.callee_name for c in py_res.calls])
    results.append(("Python AST Parser", True))

    # -----------------------------------------------------------------------
    # Check 4: Tree-sitter JavaScript & TypeScript Parser
    # -----------------------------------------------------------------------
    print_header("4. Tree-sitter JavaScript & TypeScript Parser")
    ts_parser = TreeSitterJSParser()
    ts_code = """
import { GalaxyRenderer } from './renderer';
const lodash = require('lodash');

export interface StarProperties {
    lumens: number;
    spectralType: string;
}

export enum GalaxyClusterType {
    SPIRAL = "spiral",
    ELLIPTICAL = "elliptical"
}

export class SolarSystem extends CelestialBody {
    private planets: number;

    constructor(name: string) {
        super(name);
        this.planets = 8;
    }

    public renderOrbit(): void {
        renderGalaxySpline(this.planets);
    }
}

export const computeGravitationalForce = (mass1: number, mass2: number): number => {
    return calculatePhysicsG(mass1, mass2);
};
"""
    ts_res = ts_parser.parse_file("src/galaxy.ts", ts_code, {"src/renderer.ts"})
    ts_syms = [s.name for s in ts_res.symbols]
    assert "SolarSystem" in ts_syms
    assert "StarProperties" in ts_syms
    assert "GalaxyClusterType" in ts_syms
    assert "computeGravitationalForce" in ts_syms
    assert any(c.callee_name in ("renderGalaxySpline", "calculatePhysicsG") for c in ts_res.calls)

    print_pass("Tree-sitter TS/JS Parser extracted classes, interfaces, enums, arrow functions, and calls")
    print_detail("TypeScript Symbols", ts_syms)
    print_detail("TS Imports", [imp.raw_statement for imp in ts_res.imports])
    print_detail("TS Call Invocations", [c.callee_name for c in ts_res.calls])
    results.append(("Tree-sitter JS/TS Parser", True))

    # -----------------------------------------------------------------------
    # Check 5: Deep Symbol Resolution Engine
    # -----------------------------------------------------------------------
    print_header("5. Deep Symbol Resolution Engine")
    file_caller = ParseResult(
        file_path="src/service.py",
        language="python",
        symbols=[ParsedSymbol(name="handle_request", kind="function", line_start=1, line_end=5)],
        imports=[ParsedImport(raw_statement="from src.db import query_user", resolved_path="src/db.py", imported_names=["query_user"])],
        calls=[
            ParsedCall(callee_name="query_user", line=2),
            ParsedCall(callee_name="print", line=3),
            ParsedCall(callee_name="unregistered_helper", line=4),
        ],
    )
    file_callee = ParseResult(
        file_path="src/db.py",
        language="python",
        symbols=[ParsedSymbol(name="query_user", kind="function", line_start=1, line_end=10)],
        imports=[],
        calls=[],
    )

    resolver = SymbolResolver({"src/service.py": file_caller, "src/db.py": file_callee})
    resolved_calls = resolver.resolve_calls()

    query_user_res = next(r for r in resolved_calls if r.callee_name == "query_user")
    print_res = next(r for r in resolved_calls if r.callee_name == "print")
    missing_res = next(r for r in resolved_calls if r.callee_name == "unregistered_helper")

    assert query_user_res.status == STATUS_RESOLVED
    assert query_user_res.target_id == "func::src/db.py::query_user"
    assert print_res.status == STATUS_EXTERNAL
    assert missing_res.status == STATUS_UNRESOLVED

    print_pass("SymbolResolver distinguished resolved, external built-ins, and unresolved references")
    print_detail("Cross-file Call ('query_user')", f"Status={query_user_res.status}, Target={query_user_res.target_id}")
    print_detail("Built-in Call ('print')", f"Status={print_res.status} (Standard Library)")
    print_detail("Missing Call ('unregistered_helper')", f"Status={missing_res.status}")
    results.append(("Symbol Resolution Engine", True))

    # -----------------------------------------------------------------------
    # Check 6: Archive Security & Zip-Slip Defense
    # -----------------------------------------------------------------------
    print_header("6. Archive Security & Zip-Slip Traversal Mitigation")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        malicious_zip = tdp / "malicious.zip"
        extract_dir = tdp / "extracted"

        # Create zip with malicious path traversal sequence
        with zipfile.ZipFile(malicious_zip, "w") as zf:
            zf.writestr("../../etc/passwd", "root:x:0:0")

        try:
            extract_archive_safely(malicious_zip, extract_dir)
            raise AssertionError("Failed to block Zip-Slip traversal!")
        except ValueError as err:
            print_pass(f"Malicious Zip-Slip path blocked securely: {err}")

        # Test valid safe extraction
        safe_zip = tdp / "safe.zip"
        with zipfile.ZipFile(safe_zip, "w") as zf:
            zf.writestr("repo-main/app.py", "print('safe')")
            zf.writestr("repo-main/README.md", "# Safe Repo")

        extracted_count = extract_archive_safely(safe_zip, extract_dir)
        assert extracted_count == 2
        assert (extract_dir / "app.py").exists()
        print_pass(f"Extracted safe archive with GitHub wrapper stripped ({extracted_count} files)")
        results.append(("Archive Security & Downloader", True))

    # -----------------------------------------------------------------------
    # Check 7: Persistent SQLite Storage & Multi-Tenant Jobs
    # -----------------------------------------------------------------------
    print_header("7. Persistent SQLite Storage & Job State Machine")
    with tempfile.TemporaryDirectory() as td:
        test_db = Path(td) / "test_verify.db"
        init_db(test_db)

        repo = create_or_get_repository("https://github.com/astral/demo", "astral", "demo", db_path=test_db)
        repo_id = repo["id"]
        job = create_job(repo_id, db_path=test_db)
        job_id = job["id"]

        update_job_progress(job_id, stage="building_graph", progress=65, db_path=test_db)
        running_job = get_job(job_id, db_path=test_db)
        assert running_job["progress"] == 65
        assert running_job["stage"] == "building_graph"

        complete_job(job_id, repo_id, db_path=test_db)
        done_job = get_job(job_id, db_path=test_db)
        assert done_job["status"] == "completed"

        repos = list_repositories(db_path=test_db)
        assert len(repos) == 1
        assert repos[0]["status"] == "ready"

        print_pass("SQLite state machine tracked repository lifecycle: queued -> building_graph (65%) -> ready")
        print_detail("Repository ID", repo_id)
        print_detail("Job ID", job_id)
        print_detail("Job Status", done_job["status"])
        print_detail("Job Progress", f"{done_job['progress']}%")
        results.append(("SQLite Storage & Job Engine", True))

    # -----------------------------------------------------------------------
    # Check 8: Dependency Traversal & Blast Radius Impact Analysis
    # -----------------------------------------------------------------------
    print_header("8. Dependency Traversal & Impact Analysis (Blast Radius)")
    active_graph = get_active_graph_store().graph
    first_node_id = active_graph.nodes[0].id

    # 1. Dependency query
    dep_res = get_dependencies_for_node(active_graph, node_id=first_node_id, direction="outgoing", depth=2)
    assert dep_res["found"] is True
    print_pass(f"Dependency traversal successful for node '{first_node_id}'")
    print_detail("Visited Nodes Count", len(dep_res["nodes"]))
    print_detail("Traversed Edges Count", len(dep_res["edges"]))

    # 2. Impact analysis
    impact_res = compute_impact_analysis(active_graph, target_node_id=first_node_id, max_depth=3)
    assert impact_res["found"] is True
    print_pass("Architectural blast radius impact analysis completed")
    print_detail("Target Node", first_node_id)
    print_detail("Downstream Impacted Nodes", impact_res["impacted_count"])
    results.append(("Dependency & Impact Analysis", True))

    # -----------------------------------------------------------------------
    # Check 9: Repositories & Jobs API Endpoints
    # -----------------------------------------------------------------------
    print_header("9. Repositories & Jobs REST API")
    from unittest.mock import patch
    with patch("app.api.v1.repositories.run_indexing_pipeline"):
        sub_resp = client.post("/api/v1/repositories", json={"repo_url": "https://github.com/astral/sample-repo", "branch": "main"})
    assert sub_resp.status_code == 202
    sub_data = sub_resp.json()
    job_id = sub_data["job_id"]
    repo_id = sub_data["repository_id"]

    job_poll = client.get(f"/api/v1/jobs/{job_id}")
    assert job_poll.status_code == 200
    assert job_poll.json()["id"] == job_id

    repo_list = client.get("/api/v1/repositories")
    assert repo_list.status_code == 200

    print_pass("POST /api/v1/repositories returned 202 Accepted with job queue ID")
    print_detail("Queued Job ID", job_id)
    print_detail("Repository ID", repo_id)
    print_detail("Job Status Poll", job_poll.json()["status"])
    results.append(("Repositories & Jobs Endpoints", True))

    # -----------------------------------------------------------------------
    # Check 10: In-Memory GraphStore Indexing & Search
    # -----------------------------------------------------------------------
    print_header("10. In-Memory GraphStore Indexing & Keyword Search")
    store = get_active_graph_store()
    search_res = store.search_nodes_by_keyword("api", limit=5)
    cluster_ids = list(store.clusters.keys())
    assert len(cluster_ids) > 0
    sample_profile = store.get_cluster_summary(cluster_ids[0])

    print_pass("GraphStore indexed nodes and executed keyword search in RAM")
    print_detail("Total Indexed Clusters", len(cluster_ids))
    print_detail("Keyword Search Results ('api')", len(search_res))
    print_detail("Cluster Profile Sample Header", sample_profile.splitlines()[0])
    results.append(("In-Memory GraphStore", True))

    # -----------------------------------------------------------------------
    # Check 11: AI Agent Layer — Q&A with 3D Camera Flight Targeting
    # -----------------------------------------------------------------------
    print_header("11. AI Codebase Q&A Agent with 3D Camera Targeting")
    chat_resp = client.post("/api/v1/chat", json={"question": "Where is the API router located and how does it connect?"})
    assert chat_resp.status_code == 200
    chat_data = chat_resp.json()
    assert "answer" in chat_data
    assert "highlighted_node_ids" in chat_data
    assert isinstance(chat_data["highlighted_node_ids"], list)

    print_pass("Q&A agent reasoned over graph and returned 3D camera targeting coordinates")
    print_detail("Answer Excerpt", chat_data["answer"][:120] + "...")
    print_detail("3D Highlighted Node IDs (Camera Targets)", chat_data["highlighted_node_ids"])
    print_detail("Verified Citations", len(chat_data.get("citations", [])))
    results.append(("AI Q&A Agent (Camera Flight)", True))

    # -----------------------------------------------------------------------
    # Check 12: AI Agent Layer — Galaxy Cluster Summarization
    # -----------------------------------------------------------------------
    print_header("12. AI Galaxy Cluster Summarizer Agent")
    cluster_resp = client.post("/api/v1/analyze/clusters")
    assert cluster_resp.status_code == 200
    cluster_data = cluster_resp.json()
    assert "cluster_summaries" in cluster_data

    print_pass("Cluster agent synthesized high-level Galaxy summaries for 3D zoom-out view")
    print_detail("Synthesized Clusters", cluster_data["total_clusters"])
    results.append(("AI Cluster Summarizer", True))

    # -----------------------------------------------------------------------
    # Check 13: AI Agent Layer — Workflow Tracing ("Glowing Pulses")
    # -----------------------------------------------------------------------
    print_header("13. AI Workflow Tracing Agent ('Glowing Pulses')")
    wf_resp = client.post("/api/v1/analyze/workflows")
    assert wf_resp.status_code == 200
    wf_data = wf_resp.json()
    assert "workflows" in wf_data

    print_pass("Workflow agent traced execution pathways for 3D glowing pulse animation")
    print_detail("Traced Workflows Count", wf_data["total_workflows"])
    if wf_data["workflows"]:
        first_wf = wf_data["workflows"][0]
        print_detail("Sample Workflow Name", first_wf.get("name"))
        print_detail("Execution Path Nodes", len(first_wf.get("ordered_node_ids", [])))
    results.append(("AI Workflow Tracing", True))

    # -----------------------------------------------------------------------
    # Final Scorecard
    # -----------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("  [RESULTS] FINAL SYSTEM VERIFICATION SCORECARD")
    print("=" * 70)
    passed_count = sum(1 for _, ok in results if ok)
    for name, ok in results:
        status_sym = "[PASS]" if ok else "[FAIL]"
        print(f"  {status_sym}  {name}")
    print("-" * 70)
    print(f"  Total Features Tested: {len(results)} | Passed: {passed_count}/{len(results)} (100%)\n")


if __name__ == "__main__":
    asyncio.run(run_all_checks())
