"""
Integration test suite for advanced compiler, Tree-sitter, symbol resolution,
archive security, and persistent repository storage features.
"""

from __future__ import annotations

import io
from pathlib import Path
import tempfile
import zipfile

import pytest
from starlette.testclient import TestClient

from app.main import app
from app.services.archive_extractor import extract_archive_safely, is_symlink_zip_entry
from app.services.downloader import extract_github_owner_and_repo
from app.services.parsers.base import ParseResult, ParsedSymbol, ParsedImport, ParsedCall
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
)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Tree-sitter Parser Tests
# ---------------------------------------------------------------------------

def test_treesitter_js_and_ts_parsing() -> None:
    parser = TreeSitterJSParser()
    assert ".ts" in parser.supported_extensions
    assert ".tsx" in parser.supported_extensions
    assert ".js" in parser.supported_extensions

    ts_code = """
    import { PaymentGateway } from './gateway';
    const helper = require('./utils');

    export interface UserProfile {
        id: string;
        username: string;
    }

    export class AuthService extends BaseAuth {
        constructor() {
            super();
        }

        async login(user: string): Promise<boolean> {
            this.validate();
            return true;
        }
    }

    export const processPayment = async (amount: number) => {
        executeTransaction(amount);
    };
    """
    repo_files = {"src/gateway.ts", "src/utils.js"}
    res = parser.parse_file("src/auth.ts", ts_code, repo_files)

    assert res.language == "typescript"
    sym_names = [s.name for s in res.symbols]
    assert "AuthService" in sym_names
    assert "UserProfile" in sym_names
    assert "processPayment" in sym_names

    # Check class inheritance
    auth_class = next(s for s in res.symbols if s.name == "AuthService")
    assert "BaseAuth" in auth_class.bases

    # Check imports
    resolved_imports = [imp.resolved_path for imp in res.imports if imp.resolved_path]
    assert "src/gateway.ts" in resolved_imports or "src/utils.js" in resolved_imports

    # Check calls
    callees = [c.callee_name for c in res.calls]
    assert "executeTransaction" in callees or "validate" in callees


# ---------------------------------------------------------------------------
# 2. Symbol Resolver Tests
# ---------------------------------------------------------------------------

def test_symbol_resolver_engine() -> None:
    file_a = ParseResult(
        file_path="app/main.py",
        language="python",
        symbols=[ParsedSymbol(name="start_app", kind="function", line_start=1, line_end=5)],
        imports=[ParsedImport(raw_statement="from app.auth import login", resolved_path="app/auth.py", imported_names=["login"])],
        calls=[
            ParsedCall(callee_name="login", line=3),
            ParsedCall(callee_name="print", line=4),
            ParsedCall(callee_name="nonexistent_func", line=5),
        ],
    )
    file_b = ParseResult(
        file_path="app/auth.py",
        language="python",
        symbols=[ParsedSymbol(name="login", kind="function", line_start=1, line_end=10)],
        imports=[],
        calls=[],
    )

    resolver = SymbolResolver({"app/main.py": file_a, "app/auth.py": file_b})
    resolved = resolver.resolve_calls()

    login_call = next(r for r in resolved if r.callee_name == "login")
    assert login_call.status == STATUS_RESOLVED
    assert login_call.target_id == "func::app/auth.py::login"

    print_call = next(r for r in resolved if r.callee_name == "print")
    assert print_call.status == STATUS_EXTERNAL

    missing_call = next(r for r in resolved if r.callee_name == "nonexistent_func")
    assert missing_call.status == STATUS_UNRESOLVED


# ---------------------------------------------------------------------------
# 3. Archive Extractor & Security Tests
# ---------------------------------------------------------------------------

def test_archive_extractor_path_traversal_prevention(tmp_path: Path) -> None:
    zip_path = tmp_path / "malicious.zip"
    extract_target = tmp_path / "extracted"

    # Create zip with malicious path traversal entry
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../evil.txt", "pwned")

    with pytest.raises(ValueError, match="Path traversal sequence detected"):
        extract_archive_safely(zip_path, extract_target)


def test_archive_extractor_safe_extraction(tmp_path: Path) -> None:
    zip_path = tmp_path / "valid.zip"
    extract_target = tmp_path / "extracted"

    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("repo-main/src/app.py", "print('hello')")
        zf.writestr("repo-main/README.md", "# Hello")

    count = extract_archive_safely(zip_path, extract_target)
    assert count == 2
    assert (extract_target / "src/app.py").exists()
    assert (extract_target / "README.md").exists()


def test_github_url_validator() -> None:
    owner, repo = extract_github_owner_and_repo("https://github.com/fastapi/fastapi.git")
    assert owner == "fastapi"
    assert repo == "fastapi"

    with pytest.raises(ValueError):
        extract_github_owner_and_repo("http://insecure.com/evil/repo")


# ---------------------------------------------------------------------------
# 4. Storage & Persistence Tests
# ---------------------------------------------------------------------------

def test_sqlite_repository_and_job_lifecycle(tmp_path: Path) -> None:
    db_file = tmp_path / "test_astral.db"
    init_db(db_file)

    repo = create_or_get_repository(
        url="https://github.com/test/repo",
        owner="test",
        name="repo",
        branch="main",
        db_path=db_file,
    )
    assert repo["id"].startswith("repo_")

    job = create_job(repo["id"], db_path=db_file)
    assert job["id"].startswith("job_")
    assert job["status"] == "queued"

    update_job_progress(job["id"], stage="building_graph", progress=60, db_path=db_file)
    fetched_job = get_job(job["id"], db_path=db_file)
    assert fetched_job["stage"] == "building_graph"
    assert fetched_job["progress"] == 60

    complete_job(job["id"], repo["id"], db_path=db_file)
    completed_job = get_job(job["id"], db_path=db_file)
    assert completed_job["status"] == "completed"

    repos = list_repositories(db_path=db_file)
    assert len(repos) == 1
    assert repos[0]["status"] == "ready"


# ---------------------------------------------------------------------------
# 5. Repositories & Jobs API Endpoints Tests
# ---------------------------------------------------------------------------

def test_repositories_and_jobs_api(client: TestClient) -> None:
    # 1. Submit repository
    payload = {"repo_url": "https://github.com/encode/uvicorn", "branch": "master"}
    resp = client.post("/api/v1/repositories", json=payload)
    assert resp.status_code == 202
    data = resp.json()
    assert "repository_id" in data
    assert "job_id" in data

    job_id = data["job_id"]
    repo_id = data["repository_id"]

    # 2. Check job status
    job_resp = client.get(f"/api/v1/jobs/{job_id}")
    assert job_resp.status_code == 200
    assert job_resp.json()["id"] == job_id

    # 3. List repositories
    list_resp = client.get("/api/v1/repositories")
    assert list_resp.status_code == 200
    assert isinstance(list_resp.json(), list)

    # 4. Get repository details
    detail_resp = client.get(f"/api/v1/repositories/{repo_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["id"] == repo_id
