"""Repository querying, file inspection, symbol search, and graph services."""

from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import Any, Optional
import uuid

from app.config import settings
from app.graph.graph_queries import (
    find_node_by_id,
    get_incoming_neighbors,
    get_outgoing_neighbors,
    impact_analysis,
    traverse_outgoing,
)
from app.services.downloader import extract_github_owner_and_repo
from app.services.indexing_service import indexing_service
from app.storage.repository_store import (
    JobRecord,
    RepositoryRecord,
    create_job,
    create_repository,
    get_job,
    get_repository,
    delete_repository_records,
    get_repository_by_url_and_branch,
    get_repository_exact,
    list_repositories,
    update_repository_status,
)

logger = logging.getLogger(__name__)

BRANCH_PATTERN = re.compile(r"[A-Za-z0-9._/\-]{1,100}")

SENSITIVE_FILENAME_PATTERNS: tuple[str, ...] = (
    ".env",
    ".git",
    "id_rsa",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    ".pem",
    ".key",
    ".p12",
    ".pfx",
    "credentials",
    "secret",
)


def submit_repository_for_indexing(
    url: str,
    branch: str = "main",
    db_path: Optional[Path] = None,
) -> tuple[RepositoryRecord, JobRecord]:
    """Validate, register, and queue a repository for indexing."""
    owner, repo_name = extract_github_owner_and_repo(url)
    if not BRANCH_PATTERN.fullmatch(branch or "") or ".." in branch:
        raise ValueError("Invalid branch name")
    canonical_url = f"https://github.com/{owner}/{repo_name}"

    existing = get_repository_by_url_and_branch(canonical_url, branch, db_path=db_path)

    # If already queued or running, return existing records
    if existing and existing.status in ("queued", "running") and existing.current_job_id:
        existing_job = get_job(existing.current_job_id, db_path=db_path)
        if existing_job:
            return existing, existing_job

    job_id = f"job_{uuid.uuid4().hex[:12]}"

    if existing:
        repo_id = existing.id
        update_repository_status(
            repo_id,
            status="queued",
            current_job_id=job_id,
            error_message=None,
            db_path=db_path,
        )
        repo_record = get_repository(repo_id, db_path=db_path)
        if not repo_record:
            raise RuntimeError("Failed to retrieve updated repository record")
    else:
        repo_id = f"repo_{uuid.uuid4().hex[:12]}"
        workspace_dir = str(settings.get_repo_source_dir(repo_id))
        artifact_dir = str(settings.get_repo_artifact_dir(repo_id))

        repo_record = create_repository(
            repo_id=repo_id,
            url=canonical_url,
            owner=owner,
            name=repo_name,
            branch=branch,
            workspace_dir=workspace_dir,
            artifact_dir=artifact_dir,
            status="queued",
            current_job_id=job_id,
            db_path=db_path,
        )

    job_record = create_job(job_id=job_id, repo_id=repo_id, db_path=db_path)

    indexing_service.submit_job(
        repo_id=repo_id,
        job_id=job_id,
        url=canonical_url,
        branch=branch,
    )

    return repo_record, job_record


def get_repository_files(
    repo_id: str,
    language: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db_path: Optional[Path] = None,
) -> tuple[int, list[dict[str, Any]]]:
    """Retrieve indexed repository file records from the inventory artifact."""
    repo = get_repository(repo_id, db_path=db_path)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")

    inv_path = settings.get_repo_artifact_dir(repo_id) / "repository_inventory.json"
    if not inv_path.exists():
        return 0, []

    with open(inv_path, "r", encoding="utf-8") as f:
        inv_data = json.load(f)

    all_files = inv_data.get("files", [])
    if language:
        lang_lower = language.lower()
        all_files = [f for f in all_files if (f.get("language") or "").lower() == lang_lower]

    total = len(all_files)
    paginated = all_files[offset : offset + limit]
    return total, paginated


def read_repository_source_file(
    repo_id: str,
    rel_path: str,
    start_line: Optional[int] = None,
    end_line: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Safely read content and line range of a source file within a repository."""
    repo = get_repository(repo_id, db_path=db_path)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")

    cleaned_rel = rel_path.strip().replace("\\", "/").strip("/")
    if not cleaned_rel or cleaned_rel.startswith("/") or ":" in cleaned_rel:
        raise ValueError("Invalid source file path")

    if ".." in Path(cleaned_rel).parts:
        raise ValueError("Path traversal sequences are strictly prohibited")

    # Sensitive file rejection
    base_name = Path(cleaned_rel).name.lower()
    for sensitive_pattern in SENSITIVE_FILENAME_PATTERNS:
        if sensitive_pattern in base_name:
            raise PermissionError(f"Access to sensitive file '{cleaned_rel}' is forbidden")

    source_root = settings.get_repo_source_dir(repo_id).resolve()
    target_path = (source_root / cleaned_rel).resolve()

    if not target_path.is_relative_to(source_root):
        raise ValueError("File path escapes repository workspace")

    if not target_path.exists():
        raise FileNotFoundError(f"File '{cleaned_rel}' not found in repository")

    if target_path.is_symlink():
        raise PermissionError("Accessing symbolic links is strictly prohibited")

    if not target_path.is_file():
        raise ValueError(f"Path '{cleaned_rel}' is not a regular file")

    max_bytes = settings.max_source_response_mb * 1024 * 1024
    file_size = target_path.stat().st_size
    if file_size > max_bytes:
        raise ValueError(
            f"File size ({file_size} bytes) exceeds maximum response limit of {settings.max_source_response_mb} MB"
        )

    content = target_path.read_text(encoding="utf-8", errors="replace")
    lines = content.splitlines()
    total_lines = len(lines)

    s_line = max(1, start_line) if start_line is not None else 1
    e_line = min(total_lines, end_line) if end_line is not None else total_lines

    if s_line > e_line or s_line > total_lines:
        sliced_content = ""
    else:
        sliced_content = "\n".join(lines[s_line - 1 : e_line])

    return {
        "repository_id": repo_id,
        "path": cleaned_rel,
        "total_lines": total_lines,
        "start_line": s_line,
        "end_line": e_line,
        "content": sliced_content,
        "truncated": file_size > max_bytes,
    }


def get_repository_code_graph(
    repo_id: str,
    node_type: Optional[str] = None,
    edge_type: Optional[str] = None,
    limit: Optional[int] = None,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Load and optionally filter the generated code graph for a completed repository."""
    repo = get_repository(repo_id, db_path=db_path)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")

    if repo.status != "completed":
        raise ValueError(f"Repository indexing is in '{repo.status}' state; graph is not ready")

    graph_file = settings.get_repo_artifact_dir(repo_id) / "code_graph.json"
    if not graph_file.exists():
        raise FileNotFoundError(f"Code graph artifact not found for repository '{repo_id}'")

    with open(graph_file, "r", encoding="utf-8") as f:
        graph_data = json.load(f)

    nodes = graph_data.get("nodes", [])
    edges = graph_data.get("edges", [])

    # Filter nodes by type if specified
    if node_type:
        nodes = [n for n in nodes if n.get("type") == node_type]

    if limit is not None and limit > 0:
        nodes = nodes[:limit]

    node_ids = {n["id"] for n in nodes}

    # Filter edges so that endpoints ALWAYS exist in returned node set
    valid_edges = [
        e for e in edges if e.get("source") in node_ids and e.get("target") in node_ids
    ]

    # Filter edges by type if specified
    if edge_type:
        valid_edges = [e for e in valid_edges if e.get("type") == edge_type]

    # Attempt to attach analytics if artifact exists
    analytics_summary = None
    analytics_file = settings.get_repo_artifact_dir(repo_id) / "graph_analytics.json"
    if analytics_file.exists():
        try:
            with open(analytics_file, "r", encoding="utf-8") as af:
                analytics_data = json.load(af)
            analytics_summary = analytics_data.get("summary")
            node_metrics_map = {n["id"]: n for n in analytics_data.get("nodes", [])}
            for n in nodes:
                nid = n.get("id")
                if nid in node_metrics_map:
                    ninfo = node_metrics_map[nid]
                    meta = n.setdefault("metadata", {})
                    meta["cluster_id"] = ninfo.get("cluster_id", 0)
                    m = ninfo.get("metrics", {})
                    meta["centrality"] = m.get("normalized_centrality", 0.0)
                    meta["pagerank"] = m.get("pagerank", 0.0)
                    meta["in_degree"] = m.get("in_degree", 0)
                    meta["out_degree"] = m.get("out_degree", 0)
                    meta["degree_centrality"] = m.get("degree_centrality", 0.0)
        except Exception as exc:
            logger.warning("Could not attach analytics to code graph for %s: %s", repo_id, exc)

    result = {
        "repository_id": repo_id,
        "repo_name": repo.name,
        "repo_url": repo.url,
        "branch": repo.branch,
        "schema_version": graph_data.get("schema_version", 1),
        "summary": graph_data.get("summary", {}),
        "nodes": nodes,
        "edges": valid_edges,
        "unresolved_references": graph_data.get("unresolved_references", []),
    }
    if analytics_summary is not None:
        result["analytics"] = analytics_summary
    return result


def get_repository_analytics(
    repo_id: str,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Retrieve graph intelligence analytics report for an indexed repository."""
    from app.services.graph_analytics_service import graph_analytics_service

    return graph_analytics_service.get_repository_analytics(repo_id, db_path=db_path)


def search_repository_symbols(
    repo_id: str,
    query: str,
    kind: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 50,
    db_path: Optional[Path] = None,
) -> list[dict[str, Any]]:
    """Search code symbols from the analysis artifacts by name or qualified name."""
    repo = get_repository(repo_id, db_path=db_path)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")

    artifact_dir = settings.get_repo_artifact_dir(repo_id)
    all_symbols: list[dict[str, Any]] = []

    from app.parsers.registry import ANALYSIS_FILENAMES

    for ana_filename in ANALYSIS_FILENAMES:
        ana_path = artifact_dir / ana_filename
        if ana_path.exists():
            try:
                with open(ana_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    all_symbols.extend(data.get("symbols", []))
            except Exception:
                pass

    q_lower = query.lower().strip()
    kind_lower = kind.lower().strip() if kind else None
    lang_lower = language.lower().strip() if language else None

    matches = []
    for s in all_symbols:
        s_name = (s.get("name") or "").lower()
        s_qname = (s.get("qualified_name") or "").lower()
        s_kind = (s.get("kind") or "").lower()
        s_lang = (s.get("language") or "").lower()

        if q_lower and (q_lower not in s_name and q_lower not in s_qname):
            continue
        if kind_lower and s_kind != kind_lower:
            continue
        if lang_lower and s_lang != lang_lower:
            continue

        matches.append(s)
        if len(matches) >= limit:
            break

    return matches


def get_symbol_dependencies(
    repo_id: str,
    symbol_id: str,
    direction: str = "outgoing",
    depth: int = 1,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Retrieve outgoing or incoming dependency nodes using graph queries."""
    graph_dict = get_repository_code_graph(repo_id=repo_id, db_path=db_path)

    # Normalize symbol node ID (with or without 'symbol:' prefix)
    target_node_id = symbol_id if symbol_id.startswith("symbol:") else f"symbol:{symbol_id}"
    target_node = find_node_by_id(graph_dict, target_node_id)
    if not target_node:
        # Also check raw ID
        target_node = find_node_by_id(graph_dict, symbol_id)
        if target_node:
            target_node_id = symbol_id
        else:
            raise FileNotFoundError(f"Symbol '{symbol_id}' was not found in the code graph")

    if direction == "incoming":
        neighbors = get_incoming_neighbors(graph_dict, target_node_id)
        node_ids = {n["id"] for n in neighbors} | {target_node_id}
        edges = [
            e for e in graph_dict.get("edges", [])
            if e.get("target") == target_node_id and e.get("source") in node_ids
        ]
        return {
            "repository_id": repo_id,
            "symbol_id": symbol_id,
            "direction": direction,
            "depth": depth,
            "nodes": neighbors,
            "edges": edges,
        }
    else:
        results = traverse_outgoing(
            graph_dict,
            target_node_id,
            max_depth=depth,
        )
        nodes = [item["node"] for item in results]
        node_ids = {n["id"] for n in nodes} | {target_node_id}
        edges = [
            e for e in graph_dict.get("edges", [])
            if e.get("source") in node_ids and e.get("target") in node_ids
        ]
        return {
            "repository_id": repo_id,
            "symbol_id": symbol_id,
            "direction": direction,
            "depth": depth,
            "nodes": nodes,
            "edges": edges,
        }


def get_symbol_impact_analysis(
    repo_id: str,
    symbol_id: str,
    max_depth: int = 5,
    db_path: Optional[Path] = None,
) -> dict[str, Any]:
    """Perform change impact analysis by traversing upstream dependents."""
    graph_dict = get_repository_code_graph(repo_id=repo_id, db_path=db_path)

    target_node_id = symbol_id if symbol_id.startswith("symbol:") else f"symbol:{symbol_id}"
    target_node = find_node_by_id(graph_dict, target_node_id)
    if not target_node:
        target_node = find_node_by_id(graph_dict, symbol_id)
        if target_node:
            target_node_id = symbol_id
        else:
            raise FileNotFoundError(f"Symbol '{symbol_id}' was not found in the code graph")

    report = impact_analysis(
        graph=graph_dict,
        target_node_id=target_node_id,
        max_depth=max_depth,
    )

    return {
        "repository_id": repo_id,
        "target_symbol_id": symbol_id,
        "max_depth": max_depth,
        "depth_reached": report["depth_reached"],
        "target_node": report["target_node"],
        "impacted_nodes": report["impacted_nodes"],
        "impacted_edges": report["impacted_edges"],
    }


def submit_zip_for_indexing(
    file_bytes: bytes,
    filename: str = "upload.zip",
    branch: str = "main",
    repo_name: Optional[str] = None,
    db_path: Optional[Path] = None,
) -> tuple[RepositoryRecord, JobRecord]:
    """Validate, register, and queue a user-uploaded ZIP archive for indexing."""
    import tempfile
    import os

    if len(file_bytes) < 4 or not file_bytes.startswith(b"PK"):
        raise ValueError("Uploaded file is not a valid ZIP archive (missing ZIP magic header)")

    max_bytes = settings.max_archive_mb * 1024 * 1024
    if len(file_bytes) > max_bytes:
        raise ValueError(
            f"Uploaded archive exceeds maximum permitted size of {settings.max_archive_mb} MB"
        )

    clean_name = repo_name or Path(filename).stem or "uploaded_repository"
    clean_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", clean_name)
    canonical_url = f"upload://{clean_name}"
    existing = get_repository_by_url_and_branch(canonical_url, branch, db_path=db_path)
    if existing and existing.status in ("queued", "running"):
        raise ValueError("An upload with this name is already being indexed")
    repo_id = existing.id if existing else f"repo_{uuid.uuid4().hex[:12]}"
    job_id = f"job_{uuid.uuid4().hex[:12]}"

    workspace_dir = str(settings.get_repo_source_dir(repo_id))
    artifact_dir = str(settings.get_repo_artifact_dir(repo_id))
    canonical_url = f"upload://{clean_name}"

    temp_fd, temp_zip_str = tempfile.mkstemp(suffix=".zip", prefix="astral_upload_")
    with os.fdopen(temp_fd, "wb") as f:
        f.write(file_bytes)
    temp_zip_path = Path(temp_zip_str)

    if existing:
        update_repository_status(repo_id, status="queued", current_job_id=job_id, error_message=None, db_path=db_path)
        repo_record = get_repository_exact(repo_id, db_path=db_path)
    else:
        repo_record = create_repository(
            repo_id=repo_id,
            url=canonical_url,
            owner="user",
            name=clean_name,
            branch=branch,
            workspace_dir=workspace_dir,
            artifact_dir=artifact_dir,
            status="queued",
            current_job_id=job_id,
            db_path=db_path,
        )
    job_record = create_job(job_id=job_id, repo_id=repo_id, db_path=db_path)

    indexing_service.submit_job(
        repo_id=repo_id,
        job_id=job_id,
        url=canonical_url,
        branch=branch,
        archive_path=temp_zip_path,
    )

    return repo_record, job_record


def delete_repository(repo_id: str, db_path: Optional[Path] = None) -> None:
    """Delete DB records (jobs/analyses cascade) and on-disk workspace; refuses while indexing."""
    import shutil

    from app.services.repository_graph_cache import repository_graph_cache

    repo = get_repository_exact(repo_id, db_path=db_path)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")
    if repo.status in ("queued", "running"):
        raise ValueError("Repository is currently being indexed; wait for it to finish before deleting")
    delete_repository_records(repo.id, db_path=db_path)
    repository_graph_cache.invalidate(repo.id)
    shutil.rmtree(settings.get_repo_dir(repo.id), ignore_errors=True)
