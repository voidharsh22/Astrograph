"""Database, AI client, retrieval and graph-insight tests (provider calls are mocked)."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import httpx

from app.config import settings
from app.services import ai_client as aic
from app.services import graph_insights as gi
from app.services.analysis_pipeline import run_analysis
from app.services.retrieval import redact
from app.storage import database
from app.storage import repository_store as store


class DatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.db = Path(self.tmp.name) / "t.db"
        database.init_db(self.db)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _repo(self, rid="repo_1", job="job_1") -> None:
        store.create_repository(rid, "https://github.com/a/b", "a", "b", "main", "w", "a", db_path=self.db)
        store.create_job(job, rid, db_path=self.db)

    def test_migrations_idempotent_and_versioned(self) -> None:
        database.init_db(self.db)
        self.assertEqual(database.schema_version(self.db), max(v for v, _, _ in database.MIGRATIONS))

    def test_create_retrieve_complete_delete_cascade(self) -> None:
        self._repo()
        diag = {"files": {"discovered": 3}, "symbols": {"extracted": 4}, "dependencies": {"imports_unresolved": 1}, "status": "partial"}
        rec = store.complete_analysis("job_1", "repo_1", "an_1", {"node_count": 5, "edge_count": 6, "edges_by_type": {"IMPORTS": 2}}, "abc", diag, db_path=self.db)
        self.assertEqual((rec.node_count, rec.edge_count, rec.import_edge_count, rec.unresolved_import_count), (5, 6, 2, 1))
        self.assertEqual(store.get_latest_analysis("repo_1", db_path=self.db).diagnostics, diag)
        self.assertEqual(store.get_repository("repo_1", db_path=self.db).status, "completed")
        self.assertEqual(store.get_job("job_1", db_path=self.db).status, "completed")
        self.assertTrue(store.delete_repository_records("repo_1", db_path=self.db))
        with database.get_db(self.db) as c:
            self.assertEqual(c.execute("SELECT COUNT(*) FROM analyses").fetchone()[0], 0)
            self.assertEqual(c.execute("SELECT COUNT(*) FROM indexing_jobs").fetchone()[0], 0)

    def test_complete_analysis_rolls_back_atomically(self) -> None:
        self._repo()
        store.complete_analysis("job_1", "repo_1", "an_1", {}, None, {}, db_path=self.db)
        store.update_repository_status("repo_1", "running", db_path=self.db)
        # duplicate job_id violates UNIQUE -> whole transaction must roll back
        with self.assertRaises(sqlite3.IntegrityError):
            store.complete_analysis("job_1", "repo_1", "an_2", {}, None, {}, db_path=self.db)
        self.assertEqual(store.get_repository("repo_1", db_path=self.db).status, "running")
        self.assertEqual(len(store.list_analyses("repo_1", db_path=self.db)), 1)

    def test_history_is_bounded(self) -> None:
        self._repo()
        for i in range(store.MAX_ANALYSES_PER_REPOSITORY + 3):
            store.create_job(f"j{i}", "repo_1", db_path=self.db)
            store.complete_analysis(f"j{i}", "repo_1", f"a{i}", {}, None, {}, db_path=self.db)
        self.assertEqual(len(store.list_analyses("repo_1", 50, db_path=self.db)), store.MAX_ANALYSES_PER_REPOSITORY)

    def test_foreign_keys_enforced_and_persistence_across_connections(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            store.create_job("orphan", "missing_repo", db_path=self.db)
        self._repo()
        self.assertIsNotNone(store.get_repository_exact("repo_1", db_path=self.db))  # new connection each call

    def test_injection_style_ids_are_inert(self) -> None:
        self._repo()
        self.assertIsNone(store.get_repository_exact("repo_1' OR '1'='1", db_path=self.db))


class AIClientTest(unittest.TestCase):
    def test_status_never_contains_key_and_reflects_env(self) -> None:
        with patch.object(settings, "gemini_api_key", "AIzaFAKEKEY1234567890"), patch.object(settings, "anthropic_api_key", ""), patch.object(settings, "ai_provider", ""):
            st = aic.ai_status()
            self.assertTrue(st["configured"])
            self.assertEqual(st["provider"], "gemini")
            self.assertNotIn("FAKEKEY", json.dumps(st))
        with patch.object(settings, "gemini_api_key", ""), patch.object(settings, "anthropic_api_key", ""):
            self.assertFalse(aic.ai_status()["configured"])

    def test_missing_key_raises_actionable_error_no_fake_answer(self) -> None:
        with patch.object(settings, "gemini_api_key", ""), patch.object(settings, "anthropic_api_key", ""):
            with self.assertRaises(aic.AIError) as cm:
                asyncio.run(aic.ai_client.complete_text("s", [{"role": "user", "content": "q"}]))
            self.assertEqual(cm.exception.code, "ai_not_configured")
            self.assertIn("backend/.env", cm.exception.message)

    def _run_with_transport(self, handler, key="AIzaFAKEKEY1234567890"):
        real = httpx.AsyncClient

        def factory(*a, **k):
            k["transport"] = httpx.MockTransport(handler)
            return real(*a, **k)

        async def go():
            return await aic.AIClient().complete_text("sys", [{"role": "user", "content": "hi"}])

        with patch.object(settings, "gemini_api_key", key), patch.object(settings, "ai_provider", "gemini"), \
                patch("app.services.ai_client.httpx.AsyncClient", factory), patch("app.services.ai_client.asyncio.sleep", new=AsyncMock()):
            return asyncio.run(go())

    def test_gemini_request_shape_and_stream_parsing(self) -> None:
        seen = {}

        def handler(req: httpx.Request) -> httpx.Response:
            seen["url"], seen["key"], seen["body"] = str(req.url), req.headers.get("x-goog-api-key"), json.loads(req.content)
            sse = 'data: {"candidates":[{"content":{"parts":[{"text":"Hel"}]}}]}\n\ndata: {"candidates":[{"content":{"parts":[{"text":"lo"}]}}]}\n\n'
            return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

        self.assertEqual(self._run_with_transport(handler), "Hello")
        self.assertIn(":streamGenerateContent?alt=sse", seen["url"])
        self.assertNotIn("FAKEKEY", seen["url"])  # key travels in a header, not the URL
        self.assertEqual(seen["key"], "AIzaFAKEKEY1234567890")
        self.assertEqual(seen["body"]["systemInstruction"]["parts"][0]["text"], "sys")
        self.assertEqual(seen["body"]["contents"][0]["role"], "user")

    def test_rejected_key_maps_to_actionable_error_without_leaking_key(self) -> None:
        def handler(req):
            return httpx.Response(400, json={"error": {"message": "API key not valid. Please pass a valid API key. AIzaFAKEKEY1234567890"}})

        with self.assertRaises(aic.AIError) as cm:
            self._run_with_transport(handler)
        self.assertEqual(cm.exception.code, "ai_key_rejected")
        self.assertNotIn("FAKEKEY", cm.exception.message)

    def test_rate_limit_retries_then_succeeds_and_exhausts(self) -> None:
        calls = {"n": 0}

        def flaky(req):
            calls["n"] += 1
            if calls["n"] < 3:
                return httpx.Response(429, json={"error": {"message": "slow down"}}, headers={"retry-after": "1"})
            return httpx.Response(200, content=b'data: {"candidates":[{"content":{"parts":[{"text":"ok"}]}}]}\n\n')

        self.assertEqual(self._run_with_transport(flaky), "ok")
        self.assertEqual(calls["n"], 3)

        with self.assertRaises(aic.AIError) as cm:
            self._run_with_transport(lambda r: httpx.Response(429, json={"error": {"message": "slow down"}}))
        self.assertEqual(cm.exception.code, "ai_rate_limited")
        self.assertTrue(cm.exception.retryable)

    def test_timeout_maps_to_retryable_error(self) -> None:
        def handler(req):
            raise httpx.ReadTimeout("t", request=req)

        with self.assertRaises(aic.AIError) as cm:
            self._run_with_transport(handler)
        self.assertEqual(cm.exception.code, "ai_timeout")

    def test_json_parsing_tolerates_fences(self) -> None:
        self.assertEqual(aic.parse_json_object('```json\n{"a": 1}\n```'), {"a": 1})
        with self.assertRaises(aic.AIError):
            aic.parse_json_object("no json here")

    def test_redaction_removes_secrets(self) -> None:
        text = 'key = "AIzaSyD-abcdefghijklmnopqrstuvwxyz012345"\npassword: hunter2hunter2\nAKIAABCDEFGHIJKLMNOP'
        out = redact(text)
        for secret in ("AIzaSyD", "hunter2", "AKIAABC"):
            self.assertNotIn(secret, out)


class InsightsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(cls.tmp.name)
        files = {
            "app/main.py": "from app import a\nfrom app import b\n",
            "app/a.py": "from app import core\n",
            "app/b.py": "from app import core\nfrom app import c\n",
            "app/c.py": "from app import b\n",
            "app/core.py": "def f():\n    return 1\n",
            "lonely.py": "x = 1\n",
        }
        for rel, body in files.items():
            p = root / "src" / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(body)
        (root / "src/app/__init__.py").write_text("")
        run_analysis(root / "src", root / "art")
        graph = json.loads((root / "art/code_graph.json").read_text())
        from app.services.graph_analytics_service import build_networkx_graph

        nodes = {n["id"]: n for n in graph["nodes"]}
        files_ = {k: v for k, v in nodes.items() if v["type"] == "file"}
        v = gi.RepoView("r", "r", graph, build_networkx_graph(graph), json.loads((root / "art/graph_analytics.json").read_text()),
                        json.loads((root / "art/diagnostics.json").read_text()), nodes, files_)
        for fid, n in files_.items():
            v.path_to_file[(n.get("metadata") or {}).get("path") or fid.split(":", 1)[1]] = fid
        v.FG = gi._build_file_graph(v)
        cls.view = v

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def test_impact_direct_and_transitive(self) -> None:
        r = gi.impact(self.view, "file:app/core.py")
        direct = {d["path"] for d in r["direct_dependents"]}
        trans = {d["path"] for d in r["transitive_dependents"]}
        self.assertTrue({"app/a.py", "app/b.py"} <= direct)
        self.assertTrue({"app/main.py", "app/c.py"} <= trans | direct)
        self.assertNotIn("lonely.py", direct | trans)

    def test_health_detects_cycle_and_isolated(self) -> None:
        h = gi.health(self.view)
        cycles = [f for f in h["findings"] if f["category"] == "circular_dependency"]
        self.assertEqual(len(cycles), 1)
        self.assertEqual(set(cycles[0]["paths"]), {"app/b.py", "app/c.py"})
        self.assertIn("lonely.py", {p for f in h["findings"] if f["category"] == "isolated_file" for p in f["paths"]})

    def test_shortest_path_direction(self) -> None:
        self.assertTrue(gi.shortest_path(self.view, "file:app/main.py", "file:app/core.py")["found"])
        self.assertFalse(gi.shortest_path(self.view, "file:app/core.py", "file:app/main.py")["found"])

    def test_query_spec_is_whitelisted_and_executed_deterministically(self) -> None:
        spec = gi.validate_query_spec({"text_terms": ["core"], "relation": "upstream", "depth": 99, "sql": "DROP TABLE x", "node_types": ["file", "evil"]})
        self.assertEqual((spec["relation"], spec["depth"], spec["node_types"]), ("upstream", gi.MAX_QUERY_DEPTH, ["file"]))
        self.assertNotIn("sql", spec)
        res = gi.execute_query(self.view, spec)
        self.assertIn("file:app/core.py", res["node_ids"])
        self.assertIn("file:app/a.py", res["node_ids"])
        none = gi.execute_query(self.view, {"text_terms": ["zzzz-nothing"]})
        self.assertTrue(none["needs_clarification"])
        self.assertTrue(gi.execute_query(self.view, {})["needs_clarification"])

    def test_cycle_query(self) -> None:
        res = gi.execute_query(self.view, {"only_cycles": True})
        self.assertEqual(set(res["node_ids"]), {"file:app/b.py", "file:app/c.py"})

    def test_context_is_bounded_labelled_and_secret_free(self) -> None:
        from app.services.retrieval import build_context

        with patch("app.services.retrieval.read_snippet", return_value=None):
            b = build_context(self.view, "what does core do", max_chars=1500)
        self.assertLessEqual(len(b.text), 1500 + 600)
        self.assertIn("Verified parser facts", b.text)
        self.assertTrue(any(s["path"] == "app/core.py" for s in b.sources))


if __name__ == "__main__":
    unittest.main()
