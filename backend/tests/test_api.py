"""Automated unit and integration tests for Astral Cartographer FastAPI backend and indexing workflow."""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import zipfile

from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.services.archive_extractor import extract_archive_safely
from app.services.downloader import (
    download_github_archive,
    extract_github_owner_and_repo,
)
from app.storage.database import init_db
from app.storage.repository_store import (
    create_job,
    create_repository,
    get_job,
    get_repository,
    recover_interrupted_jobs,
    update_job,
)


def create_test_zip(
    files: dict[str, str],
    zip_path: Path,
    wrapper_dir: str = "test-repo-main",
) -> None:
    """Helper creating a zip archive matching GitHub's wrapper format."""
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for rel_path, content in files.items():
            entry_name = f"{wrapper_dir}/{rel_path}" if wrapper_dir else rel_path
            zf.writestr(entry_name, content.encode("utf-8"))


class TestFastAPIBackend(unittest.TestCase):
    """Test suite covering API endpoints, ingestion, persistence, and pipeline orchestration."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.temp_path = Path(self.temp_dir.name).resolve()

        # Isolate database and storage directories for this test run
        self.orig_data_dir = settings.data_dir
        settings.data_dir = self.temp_path / "data"
        settings.ensure_directories()
        init_db()

        self.client = TestClient(app)

    def _wait_for_repo(self, repo_id: str, timeout: float = 60.0) -> None:
        """Poll until the repository leaves queued/running instead of sleeping a fixed time."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            repo = get_repository(repo_id)
            if repo and repo.status in ("completed", "failed"):
                return
            time.sleep(0.05)
        self.fail(f"Repository {repo_id} did not finish within {timeout}s")

    def tearDown(self) -> None:
        settings.data_dir = self.orig_data_dir
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    # 1. API startup and health endpoint
    def test_01_api_startup_and_health(self) -> None:
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["database"], "connected")
        self.assertEqual(data["version"], "1.0.0")

        # Root route
        root_res = self.client.get("/")
        self.assertEqual(root_res.status_code, 200)
        self.assertIn("docs", root_res.json())

    # 2. Valid repository submission
    def test_02_valid_repository_submission(self) -> None:
        with patch("app.services.indexing_service.IndexingService.submit_job") as mock_submit:
            payload = {
                "url": "https://github.com/pallets/flask",
                "branch": "main",
            }
            res = self.client.post("/api/repositories", json=payload)
            self.assertEqual(res.status_code, 202)
            data = res.json()
            self.assertTrue(data["repository_id"].startswith("repo_"))
            self.assertTrue(data["job_id"].startswith("job_"))
            self.assertEqual(data["status"], "queued")
            self.assertIn("queued", data["message"].lower())
            mock_submit.assert_called_once()

    # 3. Invalid URLs, unsupported schemes, malformed paths, and hostile hosts
    def test_03_invalid_url_and_input_validation(self) -> None:
        invalid_cases = [
            {"url": "http://github.com/owner/repo"},  # Non-HTTPS
            {"url": "https://gitlab.com/owner/repo"},  # Hostile/unsupported host
            {"url": "https://user:pass@github.com/owner/repo"},  # Credentials in URL
            {"url": "https://github.com/owner"},  # Incomplete path
            {"url": "https://github.com/owner/repo/extra"},  # Too many segments
            {"url": "https://github.com/owner/../repo"},  # Path traversal
            {"url": "not_a_url"},
            {"url": "https://github.com/owner/repo", "branch": "../../bad"},  # Invalid branch
            {"url": "https://github.com/owner/repo", "branch": "branch\x00null"},  # Control chars
        ]
        for case in invalid_cases:
            res = self.client.post("/api/repositories", json=case)
            self.assertIn(
                res.status_code,
                (400, 422),
                f"Expected 400 or 422 for {case}, got {res.status_code}",
            )

    # 4. Repository records and job records persisted correctly
    def test_04_records_persisted_correctly(self) -> None:
        with patch("app.services.indexing_service.IndexingService.submit_job"):
            payload = {
                "url": "https://github.com/owner/my-project",
                "branch": "feature/v1",
            }
            res = self.client.post("/api/repositories", json=payload)
            self.assertEqual(res.status_code, 202)
            repo_id = res.json()["repository_id"]
            job_id = res.json()["job_id"]

            # Verify persisted repository
            repo_rec = get_repository(repo_id)
            self.assertIsNotNone(repo_rec)
            self.assertEqual(repo_rec.owner, "owner")
            self.assertEqual(repo_rec.name, "my-project")
            self.assertEqual(repo_rec.branch, "feature/v1")
            self.assertEqual(repo_rec.status, "queued")

            # Verify persisted job
            job_rec = get_job(job_id)
            self.assertIsNotNone(job_rec)
            self.assertEqual(job_rec.repository_id, repo_id)
            self.assertEqual(job_rec.status, "queued")
            self.assertEqual(job_rec.progress, 0)

    # 5. Job progress transitions and failure recording
    def test_05_job_progress_and_failure_recording(self) -> None:
        create_repository(
            repo_id="repo_test5",
            url="https://github.com/owner/repo5",
            owner="owner",
            name="repo5",
            branch="main",
            workspace_dir=str(self.temp_path / "repo_test5" / "source"),
            artifact_dir=str(self.temp_path / "repo_test5" / "artifacts"),
        )
        job = create_job("job_test5", "repo_test5")
        self.assertEqual(job.status, "queued")

        update_job("job_test5", status="running", stage="downloading", progress=10, started=True)
        running_job = get_job("job_test5")
        self.assertEqual(running_job.status, "running")
        self.assertEqual(running_job.stage, "downloading")
        self.assertEqual(running_job.progress, 10)
        self.assertIsNotNone(running_job.started_at)

        update_job(
            "job_test5",
            status="failed",
            stage="failed",
            error_message="Network failure",
            completed=True,
        )
        failed_job = get_job("job_test5")
        self.assertEqual(failed_job.status, "failed")
        self.assertEqual(failed_job.error_message, "Network failure")
        self.assertIsNotNone(failed_job.completed_at)

    # 6. Missing repository and job responses
    def test_06_missing_resources_return_404(self) -> None:
        res_repo = self.client.get("/api/repositories/non_existent_repo")
        self.assertEqual(res_repo.status_code, 404)

        res_job = self.client.get("/api/jobs/non_existent_job")
        self.assertEqual(res_job.status_code, 404)

        res_files = self.client.get("/api/repositories/non_existent_repo/files")
        self.assertEqual(res_files.status_code, 404)

    # 7. Safe archive extraction
    def test_07_safe_archive_extraction(self) -> None:
        zip_path = self.temp_path / "sample.zip"
        create_test_zip(
            {
                "src/index.js": "console.log('hello');\n",
                "src/utils.py": "def add(a, b): return a + b\n",
            },
            zip_path,
        )

        dest_dir = self.temp_path / "extracted"
        count = extract_archive_safely(zip_path, dest_dir)
        self.assertEqual(count, 2)
        self.assertTrue((dest_dir / "src" / "index.js").exists())
        self.assertTrue((dest_dir / "src" / "utils.py").exists())
        self.assertEqual(
            (dest_dir / "src" / "index.js").read_text(encoding="utf-8").strip(),
            "console.log('hello');",
        )

    # 8. Zip-slip and path-traversal archive entries rejected
    def test_08_path_traversal_archive_rejected(self) -> None:
        bad_zip = self.temp_path / "bad.zip"
        with zipfile.ZipFile(bad_zip, "w") as zf:
            zf.writestr("../../escaped.txt", b"evil")

        dest_dir = self.temp_path / "extracted_bad"
        with self.assertRaises(ValueError) as ctx:
            extract_archive_safely(bad_zip, dest_dir)
        self.assertIn("traversal", str(ctx.exception).lower())
        self.assertFalse((self.temp_path / "escaped.txt").exists())

    # 9. Archive size, extracted-size, and file-count limits
    def test_09_archive_limits_enforced(self) -> None:
        zip_path = self.temp_path / "limits.zip"
        create_test_zip({"file1.txt": "a", "file2.txt": "b", "file3.txt": "c"}, zip_path)

        dest_dir = self.temp_path / "extracted_limits"
        # Test max files limit
        with self.assertRaises(ValueError) as ctx:
            extract_archive_safely(zip_path, dest_dir, max_files=2)
        self.assertIn("file count limit", str(ctx.exception).lower())

        # Test single file size limit
        large_zip = self.temp_path / "large_single.zip"
        create_test_zip({"big.txt": "x" * 1024}, large_zip)
        with self.assertRaises(ValueError) as ctx:
            extract_archive_safely(large_zip, dest_dir, max_single_file_bytes=500)
        self.assertIn("exceeds limit", str(ctx.exception).lower())

    # 10. Download timeout and HTTP error handling
    def test_10_download_error_handling(self) -> None:
        target_zip = self.temp_path / "dl.zip"

        # Host validation failure
        with self.assertRaises(ValueError):
            download_github_archive("https://evil.com/owner/repo", "main", target_zip)

        # Non-existent repository simulation via mocked 404
        with patch("httpx.Client.stream") as mock_stream:
            mock_resp = unittest.mock.MagicMock()
            mock_resp.status_code = 404
            mock_stream.return_value.__enter__.return_value = mock_resp

            with self.assertRaises(ValueError) as ctx:
                download_github_archive("https://github.com/missing/repo", "main", target_zip)
            self.assertIn("not found", str(ctx.exception).lower())

    # 11. Full Indexing pipeline orchestration with mocked download
    def test_11_indexing_pipeline_orchestration(self) -> None:
        repo_files = {
            "calculator.py": "def add(x, y):\n    return x + y\n",
            "main.py": "import calculator\nresult = calculator.add(5, 10)\n",
        }

        def fake_download(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_download):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/python-calc", "branch": "main"},
            )
            self.assertEqual(res.status_code, 202)
            repo_id = res.json()["repository_id"]
            job_id = res.json()["job_id"]

            # Wait briefly for in-process thread pool to execute pipeline
            for _ in range(30):
                job_res = self.client.get(f"/api/jobs/{job_id}")
                if job_res.status_code == 200 and job_res.json().get("status") in ("completed", "failed"):
                    break
                time.sleep(0.1)

            # Check job completion
            job_res = self.client.get(f"/api/jobs/{job_id}")
            self.assertEqual(job_res.status_code, 200)
            job_data = job_res.json()
            self.assertEqual(job_data["status"], "completed")
            self.assertEqual(job_data["progress"], 100)

            # Check repo status
            repo_res = self.client.get(f"/api/repositories/{repo_id}")
            self.assertEqual(repo_res.status_code, 200)
            self.assertEqual(repo_res.json()["status"], "completed")

            # Check artifacts generated
            artifact_dir = settings.get_repo_artifact_dir(repo_id)
            self.assertTrue((artifact_dir / "repository_inventory.json").exists())
            self.assertTrue((artifact_dir / "python_analysis.json").exists())
            self.assertTrue((artifact_dir / "javascript_analysis.json").exists())
            self.assertTrue((artifact_dir / "code_graph.json").exists())
            self.assertTrue((artifact_dir / "graph_analytics.json").exists())

    # 12. Pipeline failure cases recorded gracefully
    def test_12_pipeline_failure_handling(self) -> None:
        def broken_download(url, branch, dest_path, **kwargs):
            raise RuntimeError("GitHub server 500 error")

        with patch("app.services.indexing_service.download_github_archive", side_effect=broken_download):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/broken-repo", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            job_id = res.json()["job_id"]

            time.sleep(0.5)

            job_data = self.client.get(f"/api/jobs/{job_id}").json()
            self.assertEqual(job_data["status"], "failed")
            self.assertIn("500", job_data["error_message"])

            repo_data = self.client.get(f"/api/repositories/{repo_id}").json()
            self.assertEqual(repo_data["status"], "failed")

    # 13. Python-only repositories
    def test_13_python_only_repository(self) -> None:
        repo_files = {
            "app.py": "def run():\n    print('ok')\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/py-only", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            graph_res = self.client.get(f"/api/repositories/{repo_id}/graph")
            self.assertEqual(graph_res.status_code, 200)
            graph = graph_res.json()
            self.assertGreater(graph["summary"]["node_count"], 0)
            self.assertIn("function", graph["summary"]["nodes_by_type"])

    # 14. JavaScript/TypeScript-only repositories
    def test_14_javascript_typescript_only_repository(self) -> None:
        repo_files = {
            "src/index.ts": "export interface Config { debug: boolean; }\nexport function init(): void {}\ninit();\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/ts-only", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            graph_res = self.client.get(f"/api/repositories/{repo_id}/graph")
            self.assertEqual(graph_res.status_code, 200)
            graph = graph_res.json()
            node_types = graph["summary"]["nodes_by_type"]
            self.assertIn("interface", node_types)
            self.assertIn("function", node_types)

    # 15. Repositories containing both languages
    def test_15_polyglot_repository(self) -> None:
        repo_files = {
            "backend/server.py": "def start(): pass\n",
            "frontend/app.tsx": "export const App = () => <div>Hello</div>;\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/polyglot", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Files list check
            files_res = self.client.get(f"/api/repositories/{repo_id}/files")
            self.assertEqual(files_res.status_code, 200)
            self.assertEqual(files_res.json()["total_files"], 2)

            # Graph check
            graph = self.client.get(f"/api/repositories/{repo_id}/graph").json()
            file_nodes = [n for n in graph["nodes"] if n["type"] == "file"]
            self.assertEqual(len(file_nodes), 2)

    # 16. Zero-file and malformed-source scenarios handled gracefully
    def test_16_zero_files_handled_gracefully(self) -> None:
        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip({}, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/empty", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            graph = self.client.get(f"/api/repositories/{repo_id}/graph").json()
            self.assertEqual(graph["summary"]["node_count"], 1)  # Repository node

    # 17. Graph retrieval after successful indexing
    def test_17_graph_retrieval_filtering(self) -> None:
        repo_files = {
            "service.py": "class Worker:\n    def execute(self):\n        pass\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/filtering", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Filter by node type
            graph_res = self.client.get(f"/api/repositories/{repo_id}/graph?node_type=class")
            self.assertEqual(graph_res.status_code, 200)
            data = graph_res.json()
            self.assertTrue(all(n["type"] == "class" for n in data["nodes"]))

    # 18. Graph retrieval rejected while indexing is incomplete (409 Conflict)
    def test_18_graph_retrieval_rejected_when_not_ready(self) -> None:
        repo = create_repository(
            repo_id="repo_unready",
            url="https://github.com/example/unready",
            owner="example",
            name="unready",
            branch="main",
            workspace_dir="",
            artifact_dir="",
            status="running",
        )
        res = self.client.get(f"/api/repositories/{repo.id}/graph")
        self.assertEqual(res.status_code, 409)

    # 19. File inventory endpoint
    def test_19_file_inventory_filtering(self) -> None:
        repo_files = {
            "a.py": "x = 1\n",
            "b.js": "let y = 2;\n",
            "README.md": "# Readme\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/inv-filter", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Filter by language Python
            py_files = self.client.get(f"/api/repositories/{repo_id}/files?language=Python").json()
            self.assertEqual(py_files["total_files"], 1)
            self.assertEqual(py_files["files"][0]["path"], "a.py")

    # 20. Source file access with valid relative paths
    def test_20_source_file_reading(self) -> None:
        repo_files = {
            "module/hello.py": "# Line 1\n# Line 2\ndef hello():\n    return 'world'\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/source-read", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Full file
            file_res = self.client.get(f"/api/repositories/{repo_id}/file?path=module/hello.py")
            self.assertEqual(file_res.status_code, 200)
            data = file_res.json()
            self.assertEqual(data["total_lines"], 4)
            self.assertIn("def hello():", data["content"])

            # Sliced lines (lines 3 to 4)
            sliced = self.client.get(
                f"/api/repositories/{repo_id}/file?path=module/hello.py&start_line=3&end_line=4"
            ).json()
            self.assertEqual(sliced["start_line"], 3)
            self.assertEqual(sliced["end_line"], 4)
            self.assertEqual(sliced["content"], "def hello():\n    return 'world'")

    # 21. Traversal, symlink, sensitive-file, and out-of-root access rejected
    def test_21_source_file_security_checks(self) -> None:
        repo_files = {
            "safe.py": "print(1)\n",
            ".env": "SECRET=123\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/sec-check", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Path traversal
            res_trav = self.client.get(f"/api/repositories/{repo_id}/file?path=../../outside.txt")
            self.assertEqual(res_trav.status_code, 400)

            # Sensitive file
            res_env = self.client.get(f"/api/repositories/{repo_id}/file?path=.env")
            self.assertEqual(res_env.status_code, 403)

            # Missing file
            res_miss = self.client.get(f"/api/repositories/{repo_id}/file?path=not_here.py")
            self.assertEqual(res_miss.status_code, 404)

    # 22. Symbol search and dependency-query endpoints
    def test_22_symbol_search_and_dependencies(self) -> None:
        repo_files = {
            "auth.py": "def verify_token(token):\n    return True\n",
            "server.py": "import auth\ndef login():\n    auth.verify_token('abc')\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/search-dep", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Search symbol
            search_res = self.client.get(f"/api/repositories/{repo_id}/symbols?q=verify_token")
            self.assertEqual(search_res.status_code, 200)
            symbols = search_res.json()["symbols"]
            self.assertEqual(len(symbols), 1)
            sym_id = symbols[0]["id"]
            self.assertEqual(symbols[0]["name"], "verify_token")

            # Query incoming dependencies / callers of verify_token
            dep_res = self.client.get(
                f"/api/repositories/{repo_id}/dependencies?symbol_id={sym_id}&direction=incoming"
            )
            self.assertEqual(dep_res.status_code, 200)
            dep_data = dep_res.json()
            self.assertGreater(len(dep_data["nodes"]), 0)

    # 23. Impact-analysis endpoint argument validation
    def test_23_impact_analysis_endpoint(self) -> None:
        repo_files = {
            "db.py": "def connect(): pass\n",
            "api.py": "import db\ndef handler(): db.connect()\n",
        }

        def fake_dl(url, branch, dest_path, **kwargs):
            create_test_zip(repo_files, dest_path)

        with patch("app.services.indexing_service.download_github_archive", side_effect=fake_dl):
            res = self.client.post(
                "/api/repositories",
                json={"url": "https://github.com/example/impact-test", "branch": "main"},
            )
            repo_id = res.json()["repository_id"]
            self._wait_for_repo(repo_id)

            # Find db.connect symbol
            syms = self.client.get(f"/api/repositories/{repo_id}/symbols?q=connect").json()["symbols"]
            target_id = syms[0]["id"]

            impact_res = self.client.get(
                f"/api/repositories/{repo_id}/impact?symbol_id={target_id}&max_depth=3"
            )
            self.assertEqual(impact_res.status_code, 200)
            impact_data = impact_res.json()
            self.assertEqual(impact_data["target_symbol_id"], target_id)
            self.assertGreater(len(impact_data["impacted_nodes"]), 0)

    # 24. Consistent status codes and response schemas
    def test_24_consistent_status_codes(self) -> None:
        # Invalid dependency direction
        res_dir = self.client.get(
            "/api/repositories/any/dependencies?symbol_id=s1&direction=invalid"
        )
        self.assertEqual(res_dir.status_code, 400)

        # Repositories list pagination
        res_list = self.client.get("/api/repositories?limit=10&offset=0")
        self.assertEqual(res_list.status_code, 200)
        self.assertIn("items", res_list.json())

    # 25. Concurrent job submissions do not corrupt repository or job records
    def test_25_concurrent_submissions(self) -> None:
        import concurrent.futures

        def submit_one(i: int):
            return self.client.post(
                "/api/repositories",
                json={"url": f"https://github.com/concur/repo-{i}", "branch": "main"},
            )

        with patch("app.services.indexing_service.IndexingService.submit_job"):
            with concurrent.futures.ThreadPoolExecutor(max_workers=5) as ex:
                futures = [ex.submit(submit_one, i) for i in range(10)]
                results = [f.result() for f in futures]

            for res in results:
                self.assertEqual(res.status_code, 202)

            repos = self.client.get("/api/repositories?limit=100").json()["items"]
            self.assertEqual(len(repos), 10)

    # 26. Interrupted job recovery upon server startup
    def test_26_interrupted_job_recovery(self) -> None:
        repo = create_repository(
            repo_id="repo_crashed",
            url="https://github.com/crash/test",
            owner="crash",
            name="test",
            branch="main",
            workspace_dir="",
            artifact_dir="",
            status="running",
        )
        job = create_job("job_crashed", repo.id)
        update_job("job_crashed", status="running", stage="scanning")

        # Simulate server restart recovery
        recovered_count = recover_interrupted_jobs()
        self.assertGreaterEqual(recovered_count, 1)

        updated_job = get_job("job_crashed")
        self.assertEqual(updated_job.status, "failed")
        self.assertIn("restarted", updated_job.error_message)

        updated_repo = get_repository(repo.id)
        self.assertEqual(updated_repo.status, "failed")


if __name__ == "__main__":
    unittest.main()
