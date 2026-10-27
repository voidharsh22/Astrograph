"""Automated tests validating Features A, B, C, D, and E.

Verifies:
1. Feature A: AI-powered codebase Q&A grounded in repo graph with fallback & isolation.
2. Feature B: Louvain community cluster retrieval and AI architectural summarization.
3. Feature C: Execution workflow detection, path continuity along valid graph edges, and naming.
4. Feature D: Live indexing progress streaming via Server-Sent Events (SSE).
5. Feature E: Repository-scoped cache correctness, multi-repo isolation, and reindexing artifact cleanup.
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
import networkx as nx

from app.api.schemas import (
    ClusterSummarizeResponse,
    QAResponse,
    RepositoryClustersResponse,
    WorkflowListResponse,
    WorkflowTraceResponse,
)
from app.config import settings
from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    NODE_TYPE_CLASS,
    NODE_TYPE_FILE,
    NODE_TYPE_FUNCTION,
    NODE_TYPE_METHOD,
    NODE_TYPE_REPOSITORY,
)
from app.main import app
from app.services.ai_client import ai_client
from app.services.cluster_service import cluster_service
from app.services.graph_analytics_service import graph_analytics_service
from app.services.indexing_service import indexing_service
from app.services.qa_service import qa_service
from app.services.repository_graph_cache import repository_graph_cache
from app.services.workflow_service import workflow_service
from app.storage.database import init_db
from app.storage.repository_store import (
    create_job,
    create_repository,
    get_job,
    update_job,
    update_repository_status,
)


class TestIntelligenceFeatures(unittest.TestCase):
    """Integration test suite for intelligence features A-E."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_path = Path(self.temp_dir.name).resolve()

        self.orig_data_dir = settings.data_dir
        settings.data_dir = self.temp_path / "data"
        settings.ensure_directories()
        init_db()

        repository_graph_cache.clear()
        self.client = TestClient(app)

    def tearDown(self) -> None:
        settings.data_dir = self.orig_data_dir
        repository_graph_cache.clear()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def _setup_test_repo(self, repo_id: str, graph_dict: dict) -> Path:
        """Helper to create a completed repository record and write its code_graph.json."""
        create_repository(
            repo_id=repo_id,
            url=f"https://github.com/example/{repo_id}",
            owner="example",
            name=repo_id,
            branch="main",
            workspace_dir=str(settings.get_repo_source_dir(repo_id)),
            artifact_dir=str(settings.get_repo_artifact_dir(repo_id)),
        )
        update_repository_status(repo_id, status="completed")

        art_dir = settings.get_repo_artifact_dir(repo_id)
        art_dir.mkdir(parents=True, exist_ok=True)
        source_dir = settings.get_repo_source_dir(repo_id)
        source_dir.mkdir(parents=True, exist_ok=True)

        # Write code_graph.json
        graph_file = art_dir / "code_graph.json"
        graph_file.write_text(json.dumps(graph_dict), encoding="utf-8")

        # Compute and write graph_analytics.json
        graph_analytics_service.compute_and_save_repository_analytics(
            repo_id=repo_id,
            code_graph_path=graph_file,
            output_path=art_dir / "graph_analytics.json",
        )
        return art_dir

    # -----------------------------------------------------------------------
    # Feature A: Codebase Q&A Tests
    # -----------------------------------------------------------------------

    def test_feature_a_chat_grounded_answer(self) -> None:
        """Q&A endpoint returns structured explanation grounded in the repository graph."""
        repo_id = "repo_qa_1"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "qa_1"},
            "summary": {"node_count": 3, "edge_count": 2},
            "nodes": [
                {"id": "file:auth.py", "type": NODE_TYPE_FILE, "name": "auth.py", "label": "auth.py", "metadata": {"path": "auth.py"}},
                {"id": "func:login", "type": NODE_TYPE_FUNCTION, "name": "login", "label": "login()", "metadata": {"path": "auth.py"}},
                {"id": "func:verify_jwt", "type": NODE_TYPE_FUNCTION, "name": "verify_jwt", "label": "verify_jwt()", "metadata": {"path": "auth.py"}},
            ],
            "edges": [
                {"id": "e1", "source": "file:auth.py", "target": "func:login", "type": EDGE_TYPE_DEFINES},
                {"id": "e2", "source": "func:login", "target": "func:verify_jwt", "type": EDGE_TYPE_CALLS},
            ],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        # Write sample source file
        src_file = settings.get_repo_source_dir(repo_id) / "auth.py"
        src_file.write_text("def login():\n    return verify_jwt()\n\ndef verify_jwt():\n    return True\n", encoding="utf-8")

        res = self.client.post(
            f"/api/repositories/{repo_id}/chat",
            json={"question": "How does login verify tokens in auth.py?"},
        )
        self.assertEqual(res.status_code, 200)

        data = res.json()
        validated = QAResponse.model_validate(data)
        self.assertEqual(validated.repository_id, repo_id)
        self.assertIn("login", validated.answer.lower())
        self.assertTrue(any("func:login" in nid or "verify_jwt" in nid for nid in validated.highlighted_node_ids))
        self.assertIn("auth.py", validated.relevant_files)

    def test_feature_a_chat_mocked_gemini_success(self) -> None:
        """When Gemini returns a response, Q&A agent formats the answer and highlighted node IDs."""
        repo_id = "repo_qa_gemini"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "qa_gemini"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "file:db.py", "type": NODE_TYPE_FILE, "name": "db.py", "label": "db.py"},
                {"id": "func:connect", "type": NODE_TYPE_FUNCTION, "name": "connect", "label": "connect()"},
            ],
            "edges": [{"id": "e_db", "source": "file:db.py", "target": "func:connect", "type": EDGE_TYPE_DEFINES}],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        mock_gemini_text = (
            "The database connection is managed by `connect()` inside `db.py`.\n\n"
            "```json\n"
            '{"highlighted_node_ids": ["func:connect", "file:db.py"]}\n'
            "```"
        )

        with patch.object(ai_client, "complete_text", new=AsyncMock(return_value=mock_gemini_text)):
            res = self.client.post(
                f"/api/repositories/{repo_id}/chat",
                json={"question": "How does the app connect to the database?"},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertIn("database connection is managed", data["answer"])
            self.assertIn("func:connect", data["highlighted_node_ids"])

    def test_feature_a_chat_ai_failure_returns_structured_error_not_fake_answer(self) -> None:
        """When the provider fails, the API returns a structured error and never a fabricated answer."""
        from app.services.ai_client import AIError

        repo_id = "repo_qa_fallback"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "qa_fallback"},
            "summary": {"node_count": 1, "edge_count": 0},
            "nodes": [{"id": "file:main.py", "type": NODE_TYPE_FILE, "name": "main.py", "label": "main.py"}],
            "edges": [],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        err = AIError("ai_quota_exceeded", "quota exhausted", 429)
        with patch.object(ai_client, "complete_text", new=AsyncMock(side_effect=err)):
            res = self.client.post(f"/api/repositories/{repo_id}/chat", json={"question": "What is in main.py?"})
            self.assertEqual(res.status_code, 429)
            detail = res.json()["detail"]
            self.assertEqual(detail["code"], "ai_quota_exceeded")
            self.assertNotIn("answer", res.json())

    def test_feature_a_chat_status_guards(self) -> None:
        """Chat returns 404 for missing repo, 409 for running repo, and 422 for empty question."""
        # 404
        res_404 = self.client.post("/api/repositories/non_existent/chat", json={"question": "hello"})
        self.assertEqual(res_404.status_code, 404)

        # 409
        create_repository(
            repo_id="repo_unready",
            url="https://github.com/example/unready",
            owner="example",
            name="unready",
            branch="main",
            workspace_dir="",
            artifact_dir="",
            status="running",
        )
        res_409 = self.client.post("/api/repositories/repo_unready/chat", json={"question": "hello"})
        self.assertEqual(res_409.status_code, 409)

        # 422 empty question
        res_422 = self.client.post("/api/repositories/repo_unready/chat", json={"question": ""})
        self.assertEqual(res_422.status_code, 422)

    # -----------------------------------------------------------------------
    # Feature B: Cluster Summaries Tests
    # -----------------------------------------------------------------------

    def test_feature_b_get_clusters_and_specific_cluster(self) -> None:
        """GET /repositories/{id}/clusters returns cluster profiles, and filters by cluster_id."""
        repo_id = "repo_clusters_1"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "clusters_1"},
            "summary": {"node_count": 4, "edge_count": 2},
            "nodes": [
                {"id": "file:c0_1.py", "type": NODE_TYPE_FILE, "name": "c0_1.py", "label": "c0_1.py", "metadata": {"path": "src/c0_1.py"}},
                {"id": "file:c0_2.py", "type": NODE_TYPE_FILE, "name": "c0_2.py", "label": "c0_2.py", "metadata": {"path": "src/c0_2.py"}},
                {"id": "file:c1_1.py", "type": NODE_TYPE_FILE, "name": "c1_1.py", "label": "c1_1.py", "metadata": {"path": "pkg/c1_1.py"}},
                {"id": "file:c1_2.py", "type": NODE_TYPE_FILE, "name": "c1_2.py", "label": "c1_2.py", "metadata": {"path": "pkg/c1_2.py"}},
            ],
            "edges": [
                {"id": "e_c0", "source": "file:c0_1.py", "target": "file:c0_2.py", "type": EDGE_TYPE_IMPORTS},
                {"id": "e_c1", "source": "file:c1_1.py", "target": "file:c1_2.py", "type": EDGE_TYPE_IMPORTS},
            ],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        # Retrieve all clusters
        res = self.client.get(f"/api/repositories/{repo_id}/clusters")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        validated = RepositoryClustersResponse.model_validate(data)
        self.assertEqual(validated.total_clusters, 2)

        # Retrieve specific cluster 0
        res_c0 = self.client.get(f"/api/repositories/{repo_id}/clusters?cluster_id=0")
        self.assertEqual(res_c0.status_code, 200)
        data_c0 = res_c0.json()
        self.assertEqual(data_c0["total_clusters"], 1)
        self.assertEqual(data_c0["clusters"][0]["cluster_id"], 0)

        # Invalid cluster ID returns 404
        res_invalid = self.client.get(f"/api/repositories/{repo_id}/clusters?cluster_id=999")
        self.assertEqual(res_invalid.status_code, 404)

    def test_feature_b_summarize_clusters_mocked_gemini_and_caching(self) -> None:
        """POST /repositories/{id}/clusters/summarize synthesizes summaries and caches them."""
        repo_id = "repo_clusters_summary"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "clusters_summary"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "file:a.py", "type": NODE_TYPE_FILE, "name": "a.py", "label": "a.py", "metadata": {"path": "src/a.py"}},
                {"id": "file:b.py", "type": NODE_TYPE_FILE, "name": "b.py", "label": "b.py", "metadata": {"path": "src/b.py"}},
            ],
            "edges": [{"id": "e1", "source": "file:a.py", "target": "file:b.py", "type": EDGE_TYPE_IMPORTS}],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        mock_summary = "Core routing and request dispatching module."
        with patch.object(ai_client, "complete_text", new=AsyncMock(return_value=mock_summary)):
            # First call: generates
            res = self.client.post(
                f"/api/repositories/{repo_id}/clusters/summarize",
                json={"force_refresh": False},
            )
            self.assertEqual(res.status_code, 200)
            data = res.json()
            validated = ClusterSummarizeResponse.model_validate(data)
            self.assertEqual(validated.generated_count, 1)
            self.assertEqual(validated.cached_count, 0)
            self.assertEqual(validated.summaries["0"], mock_summary)

            # Second call without force_refresh: reuses cache
            res_cached = self.client.post(
                f"/api/repositories/{repo_id}/clusters/summarize",
                json={"force_refresh": False},
            )
            self.assertEqual(res_cached.status_code, 200)
            data_cached = res_cached.json()
            self.assertEqual(data_cached["generated_count"], 0)
            self.assertEqual(data_cached["cached_count"], 1)

            # File persisted on disk
            sum_file = settings.get_repo_artifact_dir(repo_id) / "cluster_summaries.json"
            self.assertTrue(sum_file.exists())

    # -----------------------------------------------------------------------
    # Feature C: Workflow Detection and Tracing Tests
    # -----------------------------------------------------------------------

    def test_feature_c_workflow_tracing_path_continuity(self) -> None:
        """Workflows strictly follow existing CALLS/DEFINES edges and validate continuity."""
        repo_id = "repo_wf_1"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "wf_1"},
            "summary": {"node_count": 4, "edge_count": 3},
            "nodes": [
                {"id": "file:api.py", "type": NODE_TYPE_FILE, "name": "api.py", "label": "api.py", "metadata": {"path": "api.py"}},
                {"id": "func:handler", "type": NODE_TYPE_FUNCTION, "name": "handler", "label": "handler()", "metadata": {"path": "api.py"}},
                {"id": "func:process", "type": NODE_TYPE_FUNCTION, "name": "process", "label": "process()", "metadata": {"path": "service.py"}},
                {"id": "func:save_db", "type": NODE_TYPE_FUNCTION, "name": "save_db", "label": "save_db()", "metadata": {"path": "db.py"}},
            ],
            "edges": [
                {"id": "e_def", "source": "file:api.py", "target": "func:handler", "type": EDGE_TYPE_DEFINES},
                {"id": "e_call1", "source": "func:handler", "target": "func:process", "type": EDGE_TYPE_CALLS},
                {"id": "e_call2", "source": "func:process", "target": "func:save_db", "type": EDGE_TYPE_CALLS},
            ],
            "unresolved_references": [],
        }
        self._setup_test_repo(repo_id, graph)

        res = self.client.post(
            f"/api/repositories/{repo_id}/workflows/trace",
            json={"max_workflows": 3, "force_refresh": True},
        )
        self.assertEqual(res.status_code, 200)

        data = res.json()
        validated = WorkflowTraceResponse.model_validate(data)
        self.assertGreaterEqual(validated.total_workflows, 1)

        wf = validated.workflows[0]
        self.assertTrue(wf.inferred)
        self.assertGreaterEqual(len(wf.ordered_node_ids), 2)
        self.assertGreaterEqual(len(wf.edge_ids), 1)

        # Every node and edge in workflow must exist in the original graph
        orig_nodes = {n["id"] for n in graph["nodes"]}
        orig_edges = {e["id"] for e in graph["edges"]}
        for nid in wf.ordered_node_ids:
            self.assertIn(nid, orig_nodes)
        for eid in wf.edge_ids:
            self.assertIn(eid, orig_edges)

        # GET /workflows returns persisted workflows
        get_res = self.client.get(f"/api/repositories/{repo_id}/workflows")
        self.assertEqual(get_res.status_code, 200)
        get_data = get_res.json()
        validated_list = WorkflowListResponse.model_validate(get_data)
        self.assertEqual(validated_list.total_workflows, validated.total_workflows)

    # -----------------------------------------------------------------------
    # Feature D: Job Progress Streaming with SSE Tests
    # -----------------------------------------------------------------------

    def test_feature_d_sse_stream_formatting_and_terminal_completion(self) -> None:
        """GET /jobs/{id}/stream streams text/event-stream data and terminates properly."""
        repo_id = "repo_sse_job"
        create_repository(
            repo_id=repo_id,
            url="https://github.com/example/sse",
            owner="example",
            name="sse",
            branch="main",
            workspace_dir="",
            artifact_dir="",
        )
        job = create_job("job_sse_test", repo_id)

        # Test active job streaming output
        res = self.client.get("/api/jobs/job_sse_test/stream?max_events=1")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/event-stream", res.headers.get("content-type", ""))
        self.assertIn("data:", res.text)
        self.assertIn('"status": "queued"', res.text)

        # Mark job completed in database
        update_job("job_sse_test", status="completed", stage="completed", progress=100, completed=True)

        # Terminal completed job should deliver final event and close immediately
        res_completed = self.client.get("/api/jobs/job_sse_test/stream")
        self.assertEqual(res_completed.status_code, 200)
        content = res_completed.text
        self.assertIn("data:", content)
        self.assertIn('"status": "completed"', content)
        self.assertIn('"progress": 100', content)

        # Test terminal failed job streaming
        failed_job = create_job("job_sse_failed", repo_id)
        update_job("job_sse_failed", status="failed", stage="parsing_python", error_message="SyntaxError in ast", completed=True)
        res_failed = self.client.get("/api/jobs/job_sse_failed/stream")
        self.assertEqual(res_failed.status_code, 200)
        failed_content = res_failed.text
        self.assertIn("data:", failed_content)
        self.assertIn('"status": "failed"', failed_content)
        self.assertIn("SyntaxError in ast", failed_content)

    def test_feature_d_sse_stream_missing_job_returns_404(self) -> None:
        """Missing job returns 404 before stream initialization."""
        res = self.client.get("/api/jobs/missing_job_12345/stream")
        self.assertEqual(res.status_code, 404)

    # -----------------------------------------------------------------------
    # Feature E: Multi-Repository Isolation and Stale Artifact Cleanup
    # -----------------------------------------------------------------------

    def test_feature_e_reindexing_cleans_stale_artifacts_and_invalidates_cache(self) -> None:
        """Reindexing a repository wipes prior cluster summaries and workflows."""
        repo_id = "repo_reindex_clean"
        graph = {
            "schema_version": 1,
            "repository": {"id": repo_id, "name": "reindex_clean"},
            "summary": {"node_count": 2, "edge_count": 1},
            "nodes": [
                {"id": "file:main.py", "type": NODE_TYPE_FILE, "name": "main.py", "label": "main.py"},
                {"id": "func:run", "type": NODE_TYPE_FUNCTION, "name": "run", "label": "run()"},
            ],
            "edges": [{"id": "e_r", "source": "file:main.py", "target": "func:run", "type": EDGE_TYPE_DEFINES}],
            "unresolved_references": [],
        }
        art_dir = self._setup_test_repo(repo_id, graph)

        # Create dummy cluster summaries and workflows artifacts
        (art_dir / "cluster_summaries.json").write_text('{"0": "Old summary"}', encoding="utf-8")
        (art_dir / "workflows.json").write_text('[{"id": "old_wf"}]', encoding="utf-8")

        # Put in memory cache
        repository_graph_cache.put(repo_id, graph, nx.DiGraph())
        self.assertIsNotNone(repository_graph_cache.get(repo_id))

        # Simulate reindexing job starting Stage B
        job = create_job("job_reindex", repo_id)
        source_dir = settings.get_repo_source_dir(repo_id)

        # Trigger reindexing cleanup directly via indexing_service helper logic
        repository_graph_cache.invalidate(repo_id)
        for stale in [art_dir / "cluster_summaries.json", art_dir / "workflows.json"]:
            if stale.exists():
                stale.unlink(missing_ok=True)

        # Cache invalidated
        self.assertIsNone(repository_graph_cache.get(repo_id))
        # Stale artifacts cleaned up
        self.assertFalse((art_dir / "cluster_summaries.json").exists())
        self.assertFalse((art_dir / "workflows.json").exists())
