"""End-to-end analysis pipeline: scan -> parse -> resolve -> graph -> analytics -> diagnostics.

The pipeline is the single place that turns an extracted source tree into the
persisted analysis artifacts, so the API, the indexing job and the tests all
exercise the same code path.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import tempfile
import time
from typing import Any, Callable, Optional

from app.graph.graph_builder import build_graph
from app.ingestion.scanner import scan_repository
from app.parsers.javascript_parser import (
    ALL_SUPPORTED_EXTENSIONS as JS_TS_EXTENSIONS,
    parse_js_repository_inventory,
)
from app.parsers.python_parser import parse_repository_inventory as parse_py_inventory

DIAGNOSTICS_FILENAME = "diagnostics.json"
DIAGNOSTICS_SCHEMA_VERSION = 1
PARSEABLE_LANGUAGES = {"Python", "JavaScript", "TypeScript"}
MAX_DETAIL_ITEMS = 200

ProgressCallback = Callable[[str, int], None]


def write_json_atomic(path: Path, data: Any) -> None:
    """Write JSON via a temp file + rename so readers never observe a partial artifact."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def _read_json(path: Path) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def build_diagnostics(
    inventory: dict[str, Any],
    py_analysis: dict[str, Any],
    js_analysis: dict[str, Any],
    graph: dict[str, Any],
    stage_durations_ms: dict[str, int],
    total_duration_ms: int,
) -> dict[str, Any]:
    """Summarise what the parsers and resolver actually did, derived only from real artifacts."""
    files = inventory.get("files", [])
    inv_summary = inventory.get("summary", {})
    lang_counts = Counter(f.get("language") or "Unknown" for f in files)

    parse_errors = list(py_analysis.get("parse_errors", [])) + list(
        js_analysis.get("parse_errors", [])
    )
    files_with_errors: dict[str, list[dict[str, Any]]] = {}
    for err in parse_errors:
        files_with_errors.setdefault(err.get("file_path", "?"), []).append(
            {
                "line": err.get("lineno"),
                "column": err.get("col_offset"),
                "message": err.get("error_message"),
            }
        )

    py_sum = py_analysis.get("summary", {})
    js_sum = js_analysis.get("summary", {})
    parsed_files = (
        py_sum.get("python_files_parsed", 0)
        + js_sum.get("javascript_files_parsed", 0)
        + js_sum.get("typescript_files_parsed", 0)
    )
    parseable_discovered = (
        py_sum.get("python_files_discovered", 0)
        + js_sum.get("javascript_files_discovered", 0)
        + js_sum.get("typescript_files_discovered", 0)
    )

    unsupported = Counter()
    for f in files:
        if (f.get("language") or "Unknown") not in PARSEABLE_LANGUAGES:
            unsupported[(f.get("extension") or "(none)").lower()] += 1

    unresolved = graph.get("unresolved_references", [])
    imports_by_status = Counter(
        u.get("status") for u in unresolved if u.get("kind") == "import"
    )
    calls_by_status = Counter(
        u.get("status") for u in unresolved if u.get("kind") == "call"
    )
    graph_summary = graph.get("summary", {})
    unresolved_internal = [
        {
            "source_file": u.get("source_file"),
            "target": u.get("target_name"),
            "line": u.get("lineno"),
            "reason": u.get("reason"),
        }
        for u in unresolved
        if u.get("kind") == "import" and u.get("status") == "unresolved"
    ]

    skipped = inv_summary.get("skipped", {}) or {}
    skipped_total = sum(v for v in skipped.values() if isinstance(v, int))

    warnings: list[str] = []
    if files_with_errors:
        warnings.append(
            f"{len(files_with_errors)} file(s) contain syntax errors; their symbols may be incomplete."
        )
    if unresolved_internal:
        warnings.append(
            f"{len(unresolved_internal)} relative import(s) could not be located in the repository."
        )
    if parseable_discovered == 0:
        warnings.append(
            "No Python, JavaScript or TypeScript files were found; the graph only contains the file tree."
        )
    if skipped.get("sensitive_files"):
        warnings.append(
            f"{skipped['sensitive_files']} sensitive file(s) (keys, credentials, .env) were skipped and not analysed."
        )

    complete = not files_with_errors and not unresolved_internal and parseable_discovered > 0
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "complete" if complete else "partial",
        "files": {
            "discovered": len(files),
            "by_language": dict(lang_counts),
            "parseable_discovered": parseable_discovered,
            "parsed_successfully": max(0, parsed_files - len(files_with_errors)),
            "with_syntax_errors": len(files_with_errors),
            "unsupported": sum(unsupported.values()),
            "unsupported_by_extension": dict(unsupported.most_common(25)),
            "skipped": {**skipped, "total": skipped_total},
        },
        "syntax_errors": [
            {"file_path": fp, "errors": errs[:5]}
            for fp, errs in list(files_with_errors.items())[:MAX_DETAIL_ITEMS]
        ],
        "symbols": {
            "extracted": py_sum.get("symbols_found", 0) + js_sum.get("symbols_found", 0),
            "imports_found": py_sum.get("imports_found", 0) + js_sum.get("imports_found", 0),
            "exports_found": js_sum.get("exports_found", 0),
            "calls_found": py_sum.get("calls_found", 0) + js_sum.get("calls_found", 0),
        },
        "dependencies": {
            "imports_resolved": graph_summary.get("resolved_imports", 0),
            "imports_external": imports_by_status.get("external", 0),
            "imports_unresolved": imports_by_status.get("unresolved", 0),
            "calls_resolved": graph_summary.get("resolved_calls", 0),
            "calls_ambiguous": calls_by_status.get("ambiguous", 0),
            "calls_unresolved": calls_by_status.get("unresolved", 0),
            "calls_external": calls_by_status.get("external", 0),
        },
        "unresolved_internal_imports": unresolved_internal[:MAX_DETAIL_ITEMS],
        "warnings": warnings,
        "timings_ms": {**stage_durations_ms, "total": total_duration_ms},
    }


def run_analysis(
    source_dir: Path,
    artifact_dir: Path,
    progress: Optional[ProgressCallback] = None,
    repository_id: str = "",
) -> dict[str, Any]:
    """Run every analysis stage and write artifacts; returns the diagnostics report."""
    from app.services.graph_analytics_service import graph_analytics_service

    notify = progress or (lambda stage, pct: None)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    inventory_file = artifact_dir / "repository_inventory.json"
    py_file = artifact_dir / "python_analysis.json"
    js_file = artifact_dir / "javascript_analysis.json"
    graph_file = artifact_dir / "code_graph.json"
    analytics_file = artifact_dir / "graph_analytics.json"
    diagnostics_file = artifact_dir / DIAGNOSTICS_FILENAME

    durations: dict[str, int] = {}
    started = time.perf_counter()

    def timed(stage: str, pct: int, fn: Callable[[], Any]) -> Any:
        notify(stage, pct)
        t0 = time.perf_counter()
        result = fn()
        durations[stage] = int((time.perf_counter() - t0) * 1000)
        return result

    timed("scanning", 40, lambda: scan_repository(repository_path=source_dir, output_path=inventory_file))
    timed(
        "parsing_python",
        60,
        lambda: parse_py_inventory(inventory_path=inventory_file, repo_root=source_dir, output_path=py_file),
    )
    timed(
        "parsing_javascript",
        75,
        lambda: parse_js_repository_inventory(
            inventory_path=inventory_file, repo_root=source_dir, output_path=js_file
        ),
    )
    graph_obj = timed(
        "building_graph",
        90,
        lambda: build_graph(
            repo_root=source_dir,
            inventory_path=inventory_file,
            analysis_path=[py_file, js_file],
            output_path=graph_file,
        ),
    )
    analytics = timed(
        "analyzing_graph",
        95,
        lambda: graph_analytics_service.compute_analytics(graph_obj, repository_id=repository_id),
    )
    write_json_atomic(analytics_file, analytics)

    notify("saving_results", 98)
    diagnostics = build_diagnostics(
        _read_json(inventory_file),
        _read_json(py_file),
        _read_json(js_file),
        _read_json(graph_file),
        durations,
        int((time.perf_counter() - started) * 1000),
    )
    write_json_atomic(diagnostics_file, diagnostics)
    return diagnostics
