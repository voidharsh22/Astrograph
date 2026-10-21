"""
AST & Dependency Graph Engine (Cartographer).

Takes ingested RepoData, parses source files, builds a NetworkX directed graph
with structural and dependency edges, computes centrality/community metrics,
and serializes everything into the AstralGraph Pydantic schema.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import community as community_louvain  # python-louvain
import networkx as nx

from app.schemas.graph_schema import (
    AstralGraph,
    EdgeRelation,
    GraphEdge,
    GraphMetadata,
    GraphNode,
    NodeMetrics,
    NodeType,
    PositionHint,
    Workflow,
)
from app.agents.workflow_agent import enrich_graph
from app.services.ingestor import FileInfo, RepoData
from app.services.parsers import JSParser, ParseResult, PythonParser, TreeSitterJSParser
from app.services.parsers.base import BaseParser
from app.services.symbol_resolver import SymbolResolver

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Parser registry
# ---------------------------------------------------------------------------

_PARSERS: list[BaseParser] = [PythonParser(), TreeSitterJSParser(), JSParser()]

_EXTENSION_TO_PARSER: dict[str, BaseParser] = {}
for _p in _PARSERS:
    for _ext in _p.supported_extensions:
        if _ext not in _EXTENSION_TO_PARSER:
            _EXTENSION_TO_PARSER[_ext] = _p


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def build_graph(
    repo_data: RepoData,
    *,
    include_ai: bool = True,
) -> AstralGraph:
    """
    Full pipeline: parse → build graph → compute metrics → serialize → AI enrich.

    Args:
        repo_data: Output from the ingestor service.
        include_ai: When True, run the AI agent for summaries and workflow detection.

    Returns:
        A fully populated AstralGraph ready for the 3D frontend.
    """
    start_time = time.perf_counter()

    # Step 1: Parse all source files
    repo_file_paths = {f.path for f in repo_data.files}
    parse_results = _parse_all_files(repo_data.clone_path, repo_data.files, repo_file_paths)

    # Step 2: Build the NetworkX graph
    G = _build_networkx_graph(repo_data.files, parse_results)

    # Step 3: Compute metrics (PageRank, centrality)
    pagerank = _compute_pagerank(G)
    degree_cent = nx.degree_centrality(G)

    # Step 4: Community detection (Louvain on undirected projection)
    clusters = _compute_communities(G)

    # Step 5: Serialize to AstralGraph
    elapsed_ms = (time.perf_counter() - start_time) * 1000
    graph = _serialize_graph(
        repo_data=repo_data,
        G=G,
        parse_results=parse_results,
        pagerank=pagerank,
        degree_centrality=degree_cent,
        clusters=clusters,
        elapsed_ms=elapsed_ms,
    )

    # Step 6: AI enrichment — summaries + workflow detection
    if include_ai:
        source_snippets = _collect_source_snippets(
            repo_data.clone_path, graph, parse_results
        )
        await enrich_graph(graph, source_snippets)
        # Update the duration to include AI time
        total_ms = (time.perf_counter() - start_time) * 1000
        graph.metadata.analysis_duration_ms = round(total_ms, 2)
        logger.info(
            "AI enrichment completed: %d summaries, %d workflows (%.1fms total)",
            sum(1 for n in graph.nodes if n.ai_summary),
            len(graph.workflows),
            total_ms,
        )

    return graph


# ---------------------------------------------------------------------------
# Step 1: Parse all files
# ---------------------------------------------------------------------------

def _parse_all_files(
    clone_path: Path,
    files: list[FileInfo],
    repo_file_paths: set[str],
) -> dict[str, ParseResult]:
    """Parse every source file that has a registered parser."""
    results: dict[str, ParseResult] = {}

    for file_info in files:
        ext = Path(file_info.path).suffix
        parser = _EXTENSION_TO_PARSER.get(ext)
        if parser is None:
            continue

        file_path = clone_path / file_info.path.replace("/", "\\")
        try:
            source = file_path.read_text(encoding="utf-8", errors="replace")
        except Exception:
            continue

        result = parser.parse_file(file_info.path, source, repo_file_paths)
        results[file_info.path] = result

    return results


def _collect_source_snippets(
    clone_path: Path,
    graph: AstralGraph,
    parse_results: dict[str, ParseResult],
) -> dict[str, str]:
    """
    Build a mapping of node_id → source code snippet.

    For file-level nodes, reads the full file source.
    For function/class nodes, extracts the relevant line range.
    """
    snippets: dict[str, str] = {}

    # Cache file contents so we don't re-read the same file for each symbol
    _file_cache: dict[str, str] = {}

    for node in graph.nodes:
        try:
            if node.type.value == "file":
                file_rel = node.path
                if file_rel not in _file_cache:
                    abs_path = clone_path / file_rel.replace("/", "\\")
                    _file_cache[file_rel] = abs_path.read_text(
                        encoding="utf-8", errors="replace"
                    )
                snippets[node.id] = _file_cache[file_rel]

            elif node.type.value in ("function", "class"):
                # node.id is like  "func::path/file.py::name"  or  "class::..."
                parts = node.id.split("::")
                if len(parts) >= 3:
                    file_rel = parts[1]
                    sym_name = parts[2]
                    if file_rel not in _file_cache:
                        abs_path = clone_path / file_rel.replace("/", "\\")
                        _file_cache[file_rel] = abs_path.read_text(
                            encoding="utf-8", errors="replace"
                        )
                    # Find the symbol in parse results to get line range
                    if file_rel in parse_results:
                        for sym in parse_results[file_rel].symbols:
                            if sym.name == sym_name:
                                lines = _file_cache[file_rel].splitlines()
                                start = max(sym.line_start - 1, 0)
                                end = min(sym.line_end, len(lines))
                                snippets[node.id] = "\n".join(lines[start:end])
                                break
        except Exception:
            # Non-fatal: just skip this node's snippet
            continue

    return snippets


# ---------------------------------------------------------------------------
# Step 2: Build NetworkX graph
# ---------------------------------------------------------------------------

def _build_networkx_graph(
    files: list[FileInfo],
    parse_results: dict[str, ParseResult],
) -> nx.DiGraph:
    """Construct a directed graph with structural and dependency edges."""
    G = nx.DiGraph()

    # Collect all unique directory paths
    all_dirs: set[str] = set()
    for f in files:
        parts = f.path.split("/")
        for i in range(len(parts) - 1):
            all_dirs.add("/".join(parts[: i + 1]))

    # Add directory nodes
    for dir_path in sorted(all_dirs):
        depth = dir_path.count("/")
        node_id = f"dir::{dir_path}"
        G.add_node(
            node_id,
            label=dir_path.split("/")[-1],
            type="directory",
            language=None,
            path=dir_path,
            loc=0,
            depth=depth,
        )

    # Add containment edges between directories
    for dir_path in sorted(all_dirs):
        parts = dir_path.split("/")
        if len(parts) > 1:
            parent_path = "/".join(parts[:-1])
            parent_id = f"dir::{parent_path}"
            child_id = f"dir::{dir_path}"
            if G.has_node(parent_id):
                G.add_edge(parent_id, child_id, relation="contains", weight=1.0)

    # Add file nodes + containment edges (dir → file)
    for f in files:
        file_id = f"file::{f.path}"
        parts = f.path.split("/")
        depth = len(parts) - 1

        G.add_node(
            file_id,
            label=parts[-1],
            type="file",
            language=f.language,
            path=f.path,
            loc=f.loc,
            depth=depth,
        )

        # Connect to parent directory
        if len(parts) > 1:
            parent_dir = "/".join(parts[:-1])
            parent_id = f"dir::{parent_dir}"
            if G.has_node(parent_id):
                G.add_edge(parent_id, file_id, relation="contains", weight=1.0)

    # Add function/class nodes from parse results + import/inheritance edges
    for file_path, result in parse_results.items():
        file_id = f"file::{file_path}"

        # Symbols (functions, classes)
        for sym in result.symbols:
            if sym.kind == "function":
                sym_id = f"func::{file_path}::{sym.name}"
                node_type = "function"
            else:
                sym_id = f"class::{file_path}::{sym.name}"
                node_type = "class"

            file_depth = file_path.count("/")
            G.add_node(
                sym_id,
                label=f"{sym.name}()" if sym.kind == "function" else sym.name,
                type=node_type,
                language=result.language,
                path=file_path,
                loc=sym.line_end - sym.line_start + 1,
                depth=file_depth + 1,
            )

            # file --contains--> symbol
            G.add_edge(file_id, sym_id, relation="contains", weight=1.0)

            # Inheritance edges (class --inherits--> base class)
            if sym.kind == "class" and sym.bases:
                for base_name in sym.bases:
                    # Try to find the base class in the same file or other files
                    base_id = _find_class_node(base_name, file_path, parse_results)
                    if base_id and G.has_node(base_id):
                        G.add_edge(sym_id, base_id, relation="inherits", weight=0.8)

        # Import edges (file --imports--> file)
        for imp in result.imports:
            if imp.resolved_path:
                target_id = f"file::{imp.resolved_path}"
                if G.has_node(target_id) and file_id != target_id:
                    # Use existing edge weight or add new
                    if G.has_edge(file_id, target_id):
                        G[file_id][target_id]["weight"] += 0.1
                    else:
                        G.add_edge(
                            file_id, target_id, relation="imports", weight=0.7
                        )

        # Resolve calls using SymbolResolver and add calls edges
        resolver = SymbolResolver(parse_results)
        resolved_calls = resolver.resolve_calls()
        for rc in resolved_calls:
            if rc.status in ("resolved", "ambiguous") and rc.target_id:
                if G.has_node(rc.caller_id) and G.has_node(rc.target_id) and rc.caller_id != rc.target_id:
                    if not G.has_edge(rc.caller_id, rc.target_id):
                        G.add_edge(rc.caller_id, rc.target_id, relation="calls", weight=0.6)

    return G


def _find_class_node(
    class_name: str,
    current_file: str,
    parse_results: dict[str, ParseResult],
) -> str | None:
    """Try to find a class node ID by name, searching current file first."""
    # Check current file first
    if current_file in parse_results:
        for sym in parse_results[current_file].symbols:
            if sym.kind == "class" and sym.name == class_name:
                return f"class::{current_file}::{class_name}"

    # Check all other files
    for fpath, result in parse_results.items():
        if fpath == current_file:
            continue
        for sym in result.symbols:
            if sym.kind == "class" and sym.name == class_name:
                return f"class::{fpath}::{class_name}"

    return None


# ---------------------------------------------------------------------------
# Step 3-4: Metrics & community detection
# ---------------------------------------------------------------------------

def _compute_pagerank(G: nx.DiGraph) -> dict[str, float]:
    """Compute PageRank on the graph, handling edge cases."""
    if len(G) == 0:
        return {}
    try:
        return nx.pagerank(G, alpha=0.85)
    except nx.PowerIterationFailedConvergence:
        # Fallback to degree centrality
        return nx.degree_centrality(G)


def _compute_communities(G: nx.DiGraph) -> dict[str, int]:
    """Run Louvain community detection on the undirected projection."""
    if len(G) == 0:
        return {}

    # Convert to undirected for community detection
    undirected = G.to_undirected()

    # Remove isolated nodes for better clustering
    connected_nodes = [n for n in undirected.nodes() if undirected.degree(n) > 0]
    if not connected_nodes:
        return {n: 0 for n in G.nodes()}

    subgraph = undirected.subgraph(connected_nodes)

    try:
        partition = community_louvain.best_partition(subgraph, random_state=42)
    except Exception:
        partition = {n: 0 for n in connected_nodes}

    # Assign cluster 0 to isolated nodes
    result = {n: 0 for n in G.nodes()}
    result.update(partition)
    return result


# ---------------------------------------------------------------------------
# Step 5: Serialize to AstralGraph
# ---------------------------------------------------------------------------

def _serialize_graph(
    repo_data: RepoData,
    G: nx.DiGraph,
    parse_results: dict[str, ParseResult],
    pagerank: dict[str, float],
    degree_centrality: dict[str, float],
    clusters: dict[str, int],
    elapsed_ms: float,
) -> AstralGraph:
    """Convert the NetworkX graph into the AstralGraph Pydantic model."""

    # Normalize PageRank to [0, 1]
    max_pr = max(pagerank.values()) if pagerank else 1.0
    if max_pr == 0:
        max_pr = 1.0

    # Build nodes
    nodes: list[GraphNode] = []
    for node_id, data in G.nodes(data=True):
        pr = pagerank.get(node_id, 0.0)
        centrality = min(pr / max_pr, 1.0)  # Normalize to [0, 1]

        nodes.append(
            GraphNode(
                id=node_id,
                label=data.get("label", node_id),
                type=NodeType(data["type"]),
                language=data.get("language"),
                path=data.get("path", ""),
                metrics=NodeMetrics(
                    loc=data.get("loc", 0),
                    centrality=round(centrality, 4),
                    complexity=0.0,  # Phase 3: compute cyclomatic complexity
                ),
                position_hint=PositionHint(
                    cluster_id=clusters.get(node_id, 0),
                    depth=data.get("depth", 0),
                ),
                ai_summary=None,  # Phase 3: filled by the AI agent
            )
        )

    # Build edges
    edges: list[GraphEdge] = []
    for i, (src, tgt, data) in enumerate(G.edges(data=True)):
        relation_str = data.get("relation", "contains")
        edge_id = f"e-{i:04d}"
        edges.append(
            GraphEdge(
                id=edge_id,
                source=src,
                target=tgt,
                relation=EdgeRelation(relation_str),
                weight=round(data.get("weight", 1.0), 3),
            )
        )

    # Collect metadata
    languages = sorted(
        {f.language for f in repo_data.files if f.language not in ("unknown", "text")}
    )
    total_functions = sum(
        1
        for _, d in G.nodes(data=True)
        if d.get("type") == "function"
    )
    total_classes = sum(
        1
        for _, d in G.nodes(data=True)
        if d.get("type") == "class"
    )

    return AstralGraph(
        repo_url=repo_data.repo_url,
        repo_name=repo_data.repo_name,
        branch=repo_data.branch,
        commit_sha=repo_data.commit_sha,
        nodes=nodes,
        edges=edges,
        workflows=[],  # Phase 3: populated by AI workflow agent
        metadata=GraphMetadata(
            total_files=len(repo_data.files),
            total_functions=total_functions,
            total_classes=total_classes,
            languages=languages,
            analysis_duration_ms=round(elapsed_ms, 2),
        ),
    )
