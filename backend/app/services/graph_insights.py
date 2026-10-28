"""Deterministic graph intelligence over a persisted analysis.

Everything here is computed from parser-generated nodes and edges. Nothing in this
module calls an AI model; AI features layer explanations on top of these facts and
must keep them visibly separate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
import logging
from pathlib import PurePosixPath
from typing import Any, Optional

import networkx as nx

from app.config import settings
from app.services.analysis_pipeline import DIAGNOSTICS_FILENAME
from app.services.graph_analytics_service import build_networkx_graph, graph_analytics_service
from app.services.repository_graph_cache import repository_graph_cache
from app.storage.repository_store import get_repository

logger = logging.getLogger(__name__)

# Measurable thresholds used by the health findings (returned with the results).
THRESHOLDS = {
    "high_fan_in": 8,
    "high_fan_out": 10,
    "oversized_loc": 500,
    "oversized_symbols": 30,
    "hotspot_min_fan_in": 3,
    "hotspot_min_dependent_ratio": 0.25,
}
DEPENDENCY_EDGE_TYPES = ("IMPORTS", "CALLS", "EXTENDS", "IMPLEMENTS", "RENDERS")
ENTRY_NAME_HINTS = (
    "main", "__main__", "app", "server", "index", "cli", "manage", "wsgi", "asgi", "run",
)
MAX_LIST = 25
MAX_QUERY_TERMS = 8
MAX_QUERY_DEPTH = 4


@dataclass
class RepoView:
    repo_id: str
    repo_name: str
    graph: dict[str, Any]
    G: nx.DiGraph
    analytics: dict[str, Any]
    diagnostics: dict[str, Any]
    nodes: dict[str, dict[str, Any]]
    files: dict[str, dict[str, Any]]  # file node id -> node
    path_to_file: dict[str, str] = field(default_factory=dict)
    FG: nx.DiGraph = field(default_factory=nx.DiGraph)  # file-level dependency graph

    def node_path(self, node_id: str) -> str:
        n = self.nodes.get(node_id) or {}
        meta = n.get("metadata", {}) or {}
        return meta.get("path") or meta.get("file_path") or ""

    def owning_file(self, node_id: str) -> Optional[str]:
        n = self.nodes.get(node_id)
        if not n:
            return None
        if n.get("type") == "file":
            return node_id
        return self.path_to_file.get(self.node_path(node_id))


def _build_file_graph(view: RepoView) -> nx.DiGraph:
    """File-level dependency graph: IMPORTS between files, CALLS lifted to owning files."""
    FG = nx.DiGraph()
    for fid in view.files:
        FG.add_node(fid)
    for edge in view.graph.get("edges", []):
        etype = edge.get("type")
        if etype not in DEPENDENCY_EDGE_TYPES:
            continue
        src = view.owning_file(edge.get("source", ""))
        tgt = view.owning_file(edge.get("target", ""))
        if not src or not tgt or src == tgt:
            continue
        meta = edge.get("metadata", {}) or {}
        lines = list(meta.get("lines") or ([meta["line"]] if meta.get("line") else []))
        if FG.has_edge(src, tgt):
            data = FG[src][tgt]
            data["kinds"].add(etype)
            data["lines"].extend(l for l in lines if l not in data["lines"])
            data["edge_ids"].append(edge.get("id"))
        else:
            FG.add_edge(src, tgt, kinds={etype}, lines=lines, edge_ids=[edge.get("id")])
    return FG


def load_repo_view(repo_id: str) -> RepoView:
    """Load the persisted analysis for a completed repository (raises FileNotFoundError/ValueError)."""
    repo = get_repository(repo_id)
    if not repo:
        raise FileNotFoundError(f"Repository '{repo_id}' not found")
    if repo.status != "completed":
        raise ValueError(f"Repository indexing is in '{repo.status}' state; analysis is not ready")

    cached = repository_graph_cache.get(repo.id)
    if cached:
        graph, G = cached
    else:
        graph_file = settings.get_repo_artifact_dir(repo.id) / "code_graph.json"
        if not graph_file.exists():
            raise FileNotFoundError(f"Code graph artifact not found for repository '{repo_id}'")
        graph = json.loads(graph_file.read_text(encoding="utf-8"))
        G = build_networkx_graph(graph)
        repository_graph_cache.put(repo.id, graph, G)

    analytics = graph_analytics_service.get_repository_analytics(repo.id)
    diag_file = settings.get_repo_artifact_dir(repo.id) / DIAGNOSTICS_FILENAME
    diagnostics = json.loads(diag_file.read_text(encoding="utf-8")) if diag_file.exists() else {}

    nodes = {n["id"]: n for n in graph.get("nodes", [])}
    files = {nid: n for nid, n in nodes.items() if n.get("type") == "file"}
    view = RepoView(repo.id, repo.name, graph, G, analytics, diagnostics, nodes, files)
    for fid, n in files.items():
        meta = n.get("metadata", {}) or {}
        path = meta.get("path") or fid.split(":", 1)[-1]
        view.path_to_file[path] = fid
    view.FG = _build_file_graph(view)
    return view


def file_path(view: RepoView, node_id: str) -> str:
    return view.node_path(node_id) or node_id.split(":", 1)[-1]


def describe_node(view: RepoView, node_id: str) -> dict[str, Any]:
    n = view.nodes.get(node_id, {})
    meta = n.get("metadata", {}) or {}
    return {
        "id": node_id,
        "type": n.get("type"),
        "name": n.get("name"),
        "path": file_path(view, node_id),
        "line": meta.get("lineno"),
        "end_line": meta.get("end_lineno"),
    }


def _pagerank(view: RepoView) -> dict[str, float]:
    return {
        n["id"]: (n.get("metrics", {}) or {}).get("pagerank", 0.0)
        for n in view.analytics.get("nodes", [])
    }


# --------------------------------------------------------------------------- impact
def impact(view: RepoView, node_id: str, max_depth: int = 6) -> dict[str, Any]:
    """Confirmed reverse-dependency closure of a file or symbol.

    Files: reverse traversal of IMPORTS/CALLS lifted to files. Symbols: callers via
    CALLS edges, plus importers of the defining file reported separately because an
    import does not prove the symbol is used.
    """
    if node_id not in view.nodes:
        raise FileNotFoundError(f"Node '{node_id}' was not found in the code graph")
    node = view.nodes[node_id]
    ntype = node.get("type")
    affected_nodes: set[str] = {node_id}
    affected_edges: list[str] = []
    levels: dict[str, int] = {}
    via: dict[str, dict[str, Any]] = {}

    if ntype in ("directory", "repository"):
        raise ValueError("Impact analysis supports files and symbols, not directories")

    if ntype == "file":
        graph, start = view.FG, node_id
    else:
        # symbol-level callers
        sym_graph = nx.DiGraph()
        for e in view.graph.get("edges", []):
            if e.get("type") == "CALLS":
                sym_graph.add_edge(e["source"], e["target"], edge_ids=[e.get("id")], kinds={"CALLS"},
                                   lines=(e.get("metadata", {}) or {}).get("lines", []))
        graph, start = sym_graph, node_id
        if start not in graph:
            graph.add_node(start)

    frontier = [start]
    depth = 0
    seen = {start}
    while frontier and depth < max_depth:
        depth += 1
        nxt = []
        for cur in frontier:
            for pred in graph.predecessors(cur):
                if pred in seen:
                    continue
                seen.add(pred)
                data = graph[pred][cur]
                levels[pred] = depth
                via[pred] = {"to": cur, "kinds": sorted(data.get("kinds", [])), "lines": data.get("lines", [])[:10]}
                affected_edges.extend(i for i in data.get("edge_ids", []) if i)
                nxt.append(pred)
        frontier = nxt

    def row(nid: str) -> dict[str, Any]:
        return {**describe_node(view, nid), "depth": levels[nid], **via[nid]}

    direct = [row(n) for n, d in levels.items() if d == 1]
    transitive = [row(n) for n, d in levels.items() if d > 1]
    importers_of_file: list[dict[str, Any]] = []
    if ntype != "file":
        owner = view.owning_file(node_id)
        if owner:
            for pred in view.FG.predecessors(owner):
                data = view.FG[pred][owner]
                importers_of_file.append({**describe_node(view, pred), "kinds": sorted(data["kinds"]), "lines": data["lines"][:10]})
    affected_nodes.update(levels)
    return {
        "target": describe_node(view, node_id),
        "direct_dependents": sorted(direct, key=lambda r: r["path"])[: MAX_LIST * 4],
        "transitive_dependents": sorted(transitive, key=lambda r: (r["depth"], r["path"]))[: MAX_LIST * 4],
        "counts": {"direct": len(direct), "transitive": len(transitive), "max_depth": max_depth,
                   "depth_reached": max(levels.values()) if levels else 0},
        "importers_of_defining_file": importers_of_file[:MAX_LIST],
        "affected_node_ids": sorted(affected_nodes),
        "affected_edge_ids": sorted(set(affected_edges)),
        "basis": "Confirmed parser edges only (IMPORTS and resolved CALLS). Dynamic dispatch, reflection and unresolved references are not included.",
    }


# --------------------------------------------------------------------------- health
def _loc(view: RepoView, fid: str) -> int:
    meta = view.files[fid].get("metadata", {}) or {}
    if meta.get("loc"):
        return int(meta["loc"])
    path = file_path(view, fid)
    ends = [
        (view.nodes[s].get("metadata", {}) or {}).get("end_lineno") or 0
        for s in view.G.successors(fid)
        if view.nodes.get(s, {}).get("type") not in ("file", "directory")
    ]
    return max(ends) if ends else 0


def _symbol_count(view: RepoView, fid: str) -> int:
    return sum(1 for s in view.G.successors(fid) if view.nodes.get(s, {}).get("type") not in ("file", "directory"))


def health(view: RepoView) -> dict[str, Any]:
    """Evidence-based architecture findings with explicit rules. These are metrics, not vulnerabilities."""
    t = THRESHOLDS
    findings: list[dict[str, Any]] = []
    FG = view.FG
    n_files = max(1, len(view.files))

    def add(category: str, severity: str, title: str, rule: str, evidence: dict[str, Any], node_ids: list[str]) -> None:
        findings.append({
            "id": f"{category}-{len(findings) + 1}", "category": category, "severity": severity, "title": title,
            "rule": rule, "evidence": evidence, "node_ids": node_ids,
            "paths": [file_path(view, n) for n in node_ids][:MAX_LIST],
        })

    # cycles: strongly connected components over file IMPORTS only
    imp = nx.DiGraph((u, v) for u, v, d in FG.edges(data=True) if "IMPORTS" in d["kinds"])
    for comp in sorted((c for c in nx.strongly_connected_components(imp) if len(c) > 1), key=len, reverse=True)[:MAX_LIST]:
        sub = imp.subgraph(comp)
        try:
            cyc = [u for u, _ in nx.find_cycle(sub)]
        except nx.NetworkXNoCycle:
            cyc = sorted(comp)
        add("circular_dependency", "warning", f"Import cycle across {len(comp)} files",
            "Strongly connected component of size > 1 in the file IMPORTS graph",
            {"files": [file_path(view, n) for n in sorted(comp)][:MAX_LIST],
             "example_cycle": [file_path(view, n) for n in cyc]}, sorted(comp))

    fan_in = {f: FG.in_degree(f) for f in FG}
    fan_out = {f: FG.out_degree(f) for f in FG}
    for f, v in sorted(fan_in.items(), key=lambda kv: -kv[1]):
        if v >= t["high_fan_in"]:
            add("high_fan_in", "info", f"{file_path(view, f)} is depended on by {v} files",
                f"fan-in >= {t['high_fan_in']}", {"fan_in": v, "dependents": [file_path(view, p) for p in FG.predecessors(f)][:MAX_LIST]}, [f])
    for f, v in sorted(fan_out.items(), key=lambda kv: -kv[1]):
        if v >= t["high_fan_out"]:
            add("high_fan_out", "info", f"{file_path(view, f)} depends on {v} files",
                f"fan-out >= {t['high_fan_out']}", {"fan_out": v, "dependencies": [file_path(view, s) for s in FG.successors(f)][:MAX_LIST]}, [f])

    for f in view.files:
        loc, syms = _loc(view, f), _symbol_count(view, f)
        if loc >= t["oversized_loc"] or syms >= t["oversized_symbols"]:
            add("oversized_module", "info", f"{file_path(view, f)} is large ({loc} lines, {syms} symbols)",
                f"lines >= {t['oversized_loc']} or symbols >= {t['oversized_symbols']}", {"lines": loc, "symbols": syms}, [f])

    unresolved = [u for u in view.graph.get("unresolved_references", []) if u.get("kind") == "import" and u.get("status") == "unresolved"]
    for u in unresolved[:MAX_LIST]:
        fid = view.path_to_file.get(u.get("source_file", ""))
        add("unresolved_internal_import", "warning", f"Unresolved relative import '{u.get('target_name')}' in {u.get('source_file')}",
            "Relative import with no matching repository file", {"line": u.get("lineno"), "reason": u.get("reason")}, [fid] if fid else [])

    ENTRYISH = ("__init__", "conftest", "setup")
    for f in view.files:
        lang = ((view.files[f].get("metadata", {}) or {}).get("language") or "").lower()
        stem = PurePosixPath(file_path(view, f)).stem
        if FG.degree(f) == 0 and lang in ("python", "javascript", "typescript") and stem not in ENTRYISH:
            add("isolated_file", "info", f"{file_path(view, f)} has no resolved dependencies in either direction",
                "No IMPORTS/CALLS edges to or from other repository files", {}, [f])

    for f in view.files:
        if fan_in[f] < t["hotspot_min_fan_in"]:
            continue
        dependents = nx.ancestors(FG, f)
        if len(dependents) / n_files >= t["hotspot_min_dependent_ratio"]:
            add("change_hotspot", "warning", f"A change to {file_path(view, f)} can reach {len(dependents)} files",
                f"fan-in >= {t['hotspot_min_fan_in']} and transitive dependents >= {int(t['hotspot_min_dependent_ratio'] * 100)}% of files",
                {"fan_in": fan_in[f], "transitive_dependents": len(dependents), "share_of_files": round(len(dependents) / n_files, 3)}, [f])

    counts: dict[str, int] = {}
    for f in findings:
        counts[f["category"]] = counts.get(f["category"], 0) + 1
    return {"thresholds": t, "counts": counts, "findings": findings[:200],
            "disclaimer": "These are structural metrics derived from parsed imports and calls. They are not security findings."}


# ------------------------------------------------------------------- paths / entry
def shortest_path(view: RepoView, source: str, target: str) -> dict[str, Any]:
    a, b = view.owning_file(source), view.owning_file(target)
    if not a or not b:
        raise FileNotFoundError("Both nodes must exist in the graph")
    try:
        path = nx.shortest_path(view.FG, a, b)
    except nx.NetworkXNoPath:
        return {"found": False, "node_ids": [], "edge_ids": [], "steps": []}
    edge_ids: list[str] = []
    steps = []
    for u, v in zip(path, path[1:]):
        d = view.FG[u][v]
        edge_ids.extend(i for i in d["edge_ids"] if i)
        steps.append({"from": file_path(view, u), "to": file_path(view, v), "kinds": sorted(d["kinds"]), "lines": d["lines"][:5]})
    return {"found": True, "node_ids": path, "edge_ids": edge_ids, "steps": steps}


def entry_points(view: RepoView) -> list[dict[str, Any]]:
    pr = _pagerank(view)
    rows = []
    for f in view.files:
        path = file_path(view, f)
        stem = PurePosixPath(path).stem.lower()
        is_test = any(p in path.lower() for p in ("test", "spec", "__tests__", "example"))
        no_importers = view.FG.in_degree(f) == 0 and view.FG.out_degree(f) > 0
        hinted = stem in ENTRY_NAME_HINTS
        if (no_importers or hinted) and not is_test:
            reasons = []
            if hinted:
                reasons.append(f"conventional entry file name '{stem}'")
            if no_importers:
                reasons.append(f"not imported by any file; imports {view.FG.out_degree(f)}")
            rows.append({"node_id": f, "path": path, "reasons": reasons,
                         "score": (2 if hinted else 0) + (1 if no_importers else 0) + view.FG.out_degree(f) * 0.05 + pr.get(f, 0)})
    return sorted(rows, key=lambda r: -r["score"])[:MAX_LIST]


def onboarding_skeleton(view: RepoView, limit: int = 8) -> list[dict[str, Any]]:
    """Grounded reading order: entry points, then the most depended-on modules, then direct imports."""
    pr = _pagerank(view)
    order: list[str] = []
    reason: dict[str, str] = {}
    for ep in entry_points(view)[:2]:
        order.append(ep["node_id"]); reason[ep["node_id"]] = "Entry point: " + "; ".join(ep["reasons"])
    def is_support(f: str) -> bool:
        low = file_path(view, f).lower()
        return any(p in low for p in ("test", "spec", "__tests__", "example", "fixture"))

    hubs = sorted((f for f in view.files if not is_support(f)), key=lambda f: (-view.FG.in_degree(f), -pr.get(f, 0)))
    for f in hubs[:4]:
        if view.FG.in_degree(f) > 0 and f not in reason:
            order.append(f); reason[f] = f"Imported/used by {view.FG.in_degree(f)} files"
    for ep in list(order[:2]):
        for dep in sorted(view.FG.successors(ep), key=lambda f: -pr.get(f, 0)):
            if dep not in reason:
                order.append(dep); reason[dep] = f"Directly imported by {file_path(view, ep)}"
    steps = []
    for i, f in enumerate(order[:limit], 1):
        steps.append({
            "step": i, "node_id": f, "path": file_path(view, f), "evidence": reason[f],
            "prerequisites": [file_path(view, d) for d in view.FG.successors(f)][:6],
            "used_by": [file_path(view, p) for p in view.FG.predecessors(f)][:6],
        })
    return steps


# --------------------------------------------------------------------- graph query
ALLOWED_RELATIONS = ("none", "connected", "downstream", "upstream")
ALLOWED_NODE_TYPES = ("file", "class", "function", "async_function", "method", "interface", "type_alias", "enum")


def validate_query_spec(raw: dict[str, Any]) -> dict[str, Any]:
    """Whitelist-validate a model-produced query spec. Unknown keys are dropped."""
    def strs(key: str, limit: int, maxlen: int = 60) -> list[str]:
        val = raw.get(key) or []
        if not isinstance(val, list):
            return []
        return [str(v).strip().lower()[:maxlen] for v in val if isinstance(v, (str, int)) and str(v).strip()][:limit]

    relation = raw.get("relation", "none")
    try:
        depth = int(raw.get("depth", 1))
    except (TypeError, ValueError):
        depth = 1
    prefix = raw.get("path_prefix")
    return {
        "text_terms": strs("text_terms", MAX_QUERY_TERMS),
        "path_prefix": str(prefix).strip().lstrip("/")[:120] if isinstance(prefix, str) and prefix.strip() else None,
        "languages": strs("languages", 5, 20),
        "node_types": [t for t in strs("node_types", 8, 30) if t in ALLOWED_NODE_TYPES],
        "relation": relation if relation in ALLOWED_RELATIONS else "none",
        "depth": max(1, min(depth, MAX_QUERY_DEPTH)),
        "only_unresolved_imports": bool(raw.get("only_unresolved_imports", False)),
        "only_entry_points": bool(raw.get("only_entry_points", False)),
        "only_cycles": bool(raw.get("only_cycles", False)),
        "clarification": str(raw["clarification"])[:300] if isinstance(raw.get("clarification"), str) and raw["clarification"].strip() else None,
    }


def execute_query(view: RepoView, spec: dict[str, Any]) -> dict[str, Any]:
    """Run a validated spec against the graph. No model-generated code or SQL is executed."""
    spec = validate_query_spec(spec)
    if spec["clarification"]:
        return {"spec": spec, "node_ids": [], "edge_ids": [], "matched": 0, "needs_clarification": spec["clarification"], "explanation": ""}

    matches: set[str] = set()
    explain: list[str] = []
    if spec["only_unresolved_imports"]:
        for u in view.graph.get("unresolved_references", []):
            if u.get("kind") == "import" and u.get("status") == "unresolved":
                fid = view.path_to_file.get(u.get("source_file", ""))
                if fid:
                    matches.add(fid)
        explain.append("files with unresolved relative imports")
    elif spec["only_cycles"]:
        imp = nx.DiGraph((u, v) for u, v, d in view.FG.edges(data=True) if "IMPORTS" in d["kinds"])
        for comp in nx.strongly_connected_components(imp):
            if len(comp) > 1:
                matches |= comp
        explain.append("files in import cycles")
    elif spec["only_entry_points"]:
        matches |= {e["node_id"] for e in entry_points(view)}
        explain.append("entry-point files")
    else:
        terms, prefix, langs, types = spec["text_terms"], spec["path_prefix"], spec["languages"], spec["node_types"]
        if not (terms or prefix or langs or types):
            return {"spec": spec, "node_ids": [], "edge_ids": [], "matched": 0,
                    "needs_clarification": "I could not tell which files you mean. Name a feature, file, folder or symbol.", "explanation": ""}
        for nid, n in view.nodes.items():
            if n.get("type") in ("directory", "repository"):
                continue
            if types and n.get("type") not in types:
                continue
            path = file_path(view, nid).lower()
            meta = n.get("metadata", {}) or {}
            if langs and (meta.get("language") or "").lower() not in langs:
                continue
            if prefix and not path.startswith(prefix.lower()):
                continue
            hay = f"{path} {str(n.get('name', '')).lower()}"
            if terms and not any(t in hay for t in terms):
                continue
            matches.add(nid)
        explain.append("nodes whose path or name contains " + ", ".join(repr(t) for t in terms) if terms else "nodes matching the filters")

    node_ids = set(matches)
    rel = spec["relation"]
    if rel != "none" and matches:
        files = {view.owning_file(m) for m in matches} - {None}
        for f in files:
            if rel in ("downstream", "connected"):
                node_ids |= set(nx.single_source_shortest_path_length(view.FG, f, cutoff=spec["depth"]))
            if rel in ("upstream", "connected"):
                node_ids |= set(nx.single_source_shortest_path_length(view.FG.reverse(copy=False), f, cutoff=spec["depth"]))
        explain.append(f"expanded {rel} to depth {spec['depth']} over IMPORTS/CALLS")
    node_ids = set(list(node_ids)[:2000])
    edge_ids = [i for u, v, d in view.FG.edges(data=True) if u in node_ids and v in node_ids for i in d["edge_ids"] if i]
    return {"spec": spec, "node_ids": sorted(node_ids), "edge_ids": edge_ids[:4000], "matched": len(matches),
            "needs_clarification": None if matches else "Nothing in the analysed graph matched. Try a different term, or check the unresolved/unsupported files in diagnostics.",
            "explanation": "Highlighted " + "; ".join(explain)}
