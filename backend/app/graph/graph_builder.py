"""Code graph builder for Astral Cartographer.

Assembles language-neutral code graph nodes and edges from repository inventory
and AST structural analysis reports, enforcing endpoint integrity and deduplication.
Supports multi-language analysis merging across Python, JavaScript, and TypeScript.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional

from app.graph.models import (
    EDGE_TYPE_CALLS,
    EDGE_TYPE_CONTAINS,
    EDGE_TYPE_DEFINES,
    EDGE_TYPE_IMPORTS,
    NODE_TYPE_CLASS,
    NODE_TYPE_DIRECTORY,
    NODE_TYPE_FILE,
    NODE_TYPE_REPOSITORY,
    VALID_NODE_TYPES,
    CodeGraph,
    GraphEdge,
    GraphNode,
    GraphSummary,
    UnresolvedReference,
)
from app.graph.symbol_resolver import SymbolResolver

GRAPH_SCHEMA_VERSION: int = 1
DEFAULT_OUTPUT_FILENAME: str = "output/code_graph.json"


class AnalysisAction(argparse.Action):
    """Custom argparse action accepting both repeated flags and multiple arguments."""

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: Any,
        option_string: Optional[str] = None,
    ) -> None:
        current = getattr(namespace, self.dest, None) or []
        if isinstance(values, list):
            current.extend(values)
        else:
            current.append(values)
        setattr(namespace, self.dest, current)


class GraphBuilder:
    """Builds a complete, connected code graph from inventory and analysis artifacts."""

    def __init__(
        self,
        repo_root: Path | str,
        inventory_data: dict[str, Any],
        analysis_data: dict[str, Any] | list[dict[str, Any]],
    ) -> None:
        self.repo_root: Path = Path(repo_root).resolve()
        self.inventory_data: dict[str, Any] = inventory_data

        if isinstance(analysis_data, dict):
            self.analysis_list: list[dict[str, Any]] = [analysis_data]
        else:
            self.analysis_list = list(analysis_data)

        self.analysis_data: dict[str, Any] = (
            self.analysis_list[0] if self.analysis_list else {}
        )

        self.nodes: dict[str, GraphNode] = {}
        self.edges: dict[tuple[str, str, str], GraphEdge] = {}
        self.unresolved_references: list[UnresolvedReference] = []

        self.resolved_calls_count: int = 0
        self.ambiguous_calls_count: int = 0
        self.unresolved_calls_count: int = 0
        self.resolved_imports_count: int = 0
        self.unresolved_imports_count: int = 0

        self.resolver = SymbolResolver(self.repo_root)

    def build(self) -> CodeGraph:
        """Execute the full graph construction pipeline."""
        repo_name = self.inventory_data.get("repository_name") or self.repo_root.name

        inventory_files = self.inventory_data.get("files", [])

        # Merge symbols, imports, exports, and calls across all analyses
        symbols: list[dict[str, Any]] = []
        imports: list[dict[str, Any]] = []
        exports: list[dict[str, Any]] = []
        calls: list[dict[str, Any]] = []
        relations: list[dict[str, Any]] = []
        analyzed_languages: set[str] = set()
        seen_symbol_ids: set[str] = set()

        python_parser_ran = False
        js_ts_parser_ran = False

        for ana in self.analysis_list:
            summary = ana.get("summary", {})
            if "python_files_discovered" in summary:
                python_parser_ran = True
            if (
                "javascript_files_discovered" in summary
                or "typescript_files_discovered" in summary
            ):
                js_ts_parser_ran = True

            for sym in ana.get("symbols", []):
                sym_id = sym.get("id")
                if sym_id not in seen_symbol_ids:
                    seen_symbol_ids.add(sym_id)
                    symbols.append(sym)
                if sym.get("language") == "python":
                    python_parser_ran = True
                elif sym.get("language") in ("javascript", "typescript"):
                    js_ts_parser_ran = True

            imports.extend(ana.get("imports", []))
            exports.extend(ana.get("exports", []))
            calls.extend(ana.get("calls", []))
            relations.extend(ana.get("relations", []))
            for key in summary:
                if key.endswith("_files_discovered"):
                    analyzed_languages.add(key[: -len("_files_discovered")])

        # Fallback detection if summary was minimal
        if not python_parser_ran and not js_ts_parser_ran:
            python_parser_ran = True

        # Step 1: Index inventory, symbols, and exports in the resolver
        self.resolver.index_inventory(inventory_files)
        self.resolver.index_exports(exports)
        self.resolver.index_symbols(symbols)
        self.resolver.index_relations(relations)
        self.resolver.build_file_import_scopes(imports)

        # Step 2: Build structural nodes (Repository, Directories, Files, Symbols)
        self._build_repository_node(repo_name)
        self._build_filesystem_nodes(
            inventory_files,
            python_parser_ran=python_parser_ran,
            js_ts_parser_ran=js_ts_parser_ran,
            analyzed_languages=analyzed_languages,
        )
        self._build_symbol_nodes(symbols)

        # Step 3: Build containment and definition edges
        self._build_containment_edges(inventory_files)
        self._build_symbol_definition_and_class_edges(symbols)

        # Step 4: Resolve and build IMPORTS edges
        self._build_import_edges(imports, exports)

        # Step 5: Resolve and build CALLS edges
        self._build_call_edges(calls)

        # Step 5b: Inheritance (EXTENDS/IMPLEMENTS) and JSX usage (RENDERS) edges
        self._build_relation_edges(relations)

        # Step 6: Validate edge endpoints
        self._validate_edge_endpoints()

        # Step 7: Calculate summary statistics
        summary_stats = self._calculate_summary()

        # Step 8: Deterministic sorting
        sorted_nodes = sorted(self.nodes.values(), key=lambda n: (n.type, n.id))
        sorted_edges = sorted(
            self.edges.values(), key=lambda e: (e.type, e.source, e.target, e.id)
        )
        sorted_unresolved = sorted(
            self.unresolved_references,
            key=lambda u: (u.kind, u.source_file, u.lineno or 0, u.expression),
        )

        return CodeGraph(
            schema_version=GRAPH_SCHEMA_VERSION,
            repository={"id": f"repository:{repo_name}", "name": repo_name},
            summary=summary_stats,
            nodes=sorted_nodes,
            edges=sorted_edges,
            unresolved_references=sorted_unresolved,
        )

    def _build_repository_node(self, repo_name: str) -> None:
        """Create the top-level repository vertex."""
        repo_id = f"repository:{repo_name}"
        self.nodes[repo_id] = GraphNode(
            id=repo_id,
            type=NODE_TYPE_REPOSITORY,
            name=repo_name,
            label=f"Repository: {repo_name}",
            metadata={"name": repo_name},
        )

    def _build_filesystem_nodes(
        self,
        inventory_files: list[dict[str, Any]],
        python_parser_ran: bool = True,
        js_ts_parser_ran: bool = False,
        analyzed_languages: Optional[set[str]] = None,
    ) -> None:
        """Create directory and file nodes from the inventory report."""
        extra_langs = {"java": "Java", "kotlin": "Kotlin", "rust": "Rust"}
        analyzed_extra = {extra_langs[k] for k in (analyzed_languages or set()) if k in extra_langs}
        seen_dirs: set[str] = set()

        for f in inventory_files:
            file_path = Path(f["path"]).as_posix()
            file_node_id = f"file:{file_path}"
            file_name = Path(file_path).name

            lang = f.get("language")
            is_analyzed = False
            if lang == "Python" and python_parser_ran:
                is_analyzed = True
            elif lang in ("JavaScript", "TypeScript") and js_ts_parser_ran:
                is_analyzed = True
            elif lang in analyzed_extra:
                is_analyzed = True

            self.nodes[file_node_id] = GraphNode(
                id=file_node_id,
                type=NODE_TYPE_FILE,
                name=file_name,
                label=f"File: {file_path}",
                metadata={
                    "path": file_path,
                    "language": f.get("language", "Unknown"),
                    "size_bytes": f.get("size_bytes", 0),
                    "sha256": f.get("sha256"),
                    "analyzed": is_analyzed,
                },
            )

            # Extract all ancestor directories
            parent = Path(file_path).parent
            while parent and str(parent) != ".":
                d_posix = parent.as_posix()
                if d_posix not in seen_dirs:
                    seen_dirs.add(d_posix)
                    d_node_id = f"directory:{d_posix}"
                    d_name = parent.name
                    self.nodes[d_node_id] = GraphNode(
                        id=d_node_id,
                        type=NODE_TYPE_DIRECTORY,
                        name=d_name,
                        label=f"Directory: {d_posix}",
                        metadata={"path": d_posix},
                    )
                parent = parent.parent

    def _build_symbol_nodes(self, symbols: list[dict[str, Any]]) -> None:
        """Create symbol nodes from parser analysis."""
        for sym in symbols:
            raw_id = sym.get("id")
            if not raw_id:
                continue
            node_id = f"symbol:{raw_id}"
            kind = sym.get("kind", "function")
            name = sym.get("name", "")
            qname = sym.get("qualified_name") or name
            file_path = sym.get("file_path", "")

            node_type = kind
            if node_type not in VALID_NODE_TYPES:
                if node_type == "constructor":
                    node_type = "method"
                else:
                    node_type = "function"

            self.nodes[node_id] = GraphNode(
                id=node_id,
                type=node_type,
                name=name,
                label=f"{node_type.capitalize()}: {qname}",
                metadata={
                    "symbol_id": raw_id,
                    "file_path": file_path,
                    "qualified_name": qname,
                    "kind": kind,
                    "language": sym.get("language", "python"),
                    "lineno": sym.get("lineno"),
                    "end_lineno": sym.get("end_lineno"),
                    "col_offset": sym.get("col_offset"),
                    "parent_scope": sym.get("parent_scope"),
                    "parameters": sym.get("parameters"),
                    "signature": sym.get("signature"),
                    "decorators": sym.get("decorators", []),
                    "bases": sym.get("bases"),
                    "is_async": sym.get("is_async", False),
                    "is_exported": sym.get("is_exported", False),
                    # Optional language-specific fields (Java/Kotlin/Rust); absent for Python/JS/TS.
                    **{
                        k: sym[k]
                        for k in ("namespace", "receiver_type", "end_col_offset")
                        if sym.get(k) is not None
                    },
                },
            )

    def _build_containment_edges(self, inventory_files: list[dict[str, Any]]) -> None:
        """Connect repository -> root directories/files and directory -> child directory/file."""
        repo_id = next(
            nid for nid, n in self.nodes.items() if n.type == NODE_TYPE_REPOSITORY
        )
        all_dirs = {
            nid: n.metadata["path"]
            for nid, n in self.nodes.items()
            if n.type == NODE_TYPE_DIRECTORY
        }

        # 1. Connect directories to child directories and repository to root directories
        for d_node_id, d_path in all_dirs.items():
            parent_dir = Path(d_path).parent
            if parent_dir and str(parent_dir) != ".":
                parent_node_id = f"directory:{parent_dir.as_posix()}"
                self._add_edge(
                    source=parent_node_id,
                    target=d_node_id,
                    edge_type=EDGE_TYPE_CONTAINS,
                    metadata={"relationship": "directory_to_directory"},
                )
            else:
                self._add_edge(
                    source=repo_id,
                    target=d_node_id,
                    edge_type=EDGE_TYPE_CONTAINS,
                    metadata={"relationship": "repository_to_directory"},
                )

        # 2. Connect files to containing directory or repository
        for f in inventory_files:
            file_path = Path(f["path"]).as_posix()
            file_node_id = f"file:{file_path}"
            parent_dir = Path(file_path).parent

            if parent_dir and str(parent_dir) != ".":
                dir_node_id = f"directory:{parent_dir.as_posix()}"
                self._add_edge(
                    source=dir_node_id,
                    target=file_node_id,
                    edge_type=EDGE_TYPE_CONTAINS,
                    metadata={"relationship": "directory_to_file"},
                )
            else:
                self._add_edge(
                    source=repo_id,
                    target=file_node_id,
                    edge_type=EDGE_TYPE_CONTAINS,
                    metadata={"relationship": "repository_to_file"},
                )

    def _build_symbol_definition_and_class_edges(
        self, symbols: list[dict[str, Any]]
    ) -> None:
        """Create DEFINES edges from files to symbols and CONTAINS edges from classes to methods."""
        for sym in symbols:
            raw_id = sym.get("id")
            if not raw_id:
                continue
            sym_node_id = f"symbol:{raw_id}"
            file_path = Path(sym.get("file_path", "")).as_posix()
            file_node_id = f"file:{file_path}"
            parent_scope = sym.get("parent_scope")

            # Top-level symbols are DEFINED by the file
            if not parent_scope:
                self._add_edge(
                    source=file_node_id,
                    target=sym_node_id,
                    edge_type=EDGE_TYPE_DEFINES,
                    metadata={
                        "symbol_name": sym.get("name", ""),
                        "kind": sym.get("kind", "function"),
                        "lineno": sym.get("lineno"),
                    },
                )
            else:
                # Nested member or class method: connect parent class -> method
                parent_sym = self.resolver.symbols_by_file_and_qname.get(
                    (file_path, parent_scope)
                )
                if parent_sym:
                    parent_node_id = f"symbol:{parent_sym['id']}"
                    self._add_edge(
                        source=parent_node_id,
                        target=sym_node_id,
                        edge_type=EDGE_TYPE_CONTAINS,
                        metadata={
                            "relationship": "class_to_member"
                            if parent_sym["kind"] == NODE_TYPE_CLASS
                            else "scope_to_nested",
                            "lineno": sym.get("lineno"),
                        },
                    )
                else:
                    self._add_edge(
                        source=file_node_id,
                        target=sym_node_id,
                        edge_type=EDGE_TYPE_DEFINES,
                        metadata={"lineno": sym.get("lineno")},
                    )

    def _build_import_edges(
        self,
        imports: list[dict[str, Any]],
        exports: Optional[list[dict[str, Any]]] = None,
    ) -> None:
        """Resolve import references and create IMPORTS edges between files."""
        for imp in imports:
            source_file = Path(imp["file_path"]).as_posix()
            source_node_id = f"file:{source_file}"

            target_file, unresolved_ref = self.resolver.resolve_import(imp)

            if target_file:
                target_node_id = f"file:{target_file}"
                edge_added = self._add_edge(
                    source=source_node_id,
                    target=target_node_id,
                    edge_type=EDGE_TYPE_IMPORTS,
                    metadata={
                        "source_file": source_file,
                        "target_file": target_file,
                        "module": imp.get("module"),
                        "imported_name": imp.get("name"),
                        "alias": imp.get("alias"),
                        "line": imp.get("lineno"),
                        "level": imp.get("level", 0),
                        "resolution_status": "resolved",
                    },
                )
                if edge_added:
                    self.resolved_imports_count += 1
            else:
                if unresolved_ref:
                    self.unresolved_references.append(unresolved_ref)
                self.unresolved_imports_count += 1

        if exports:
            for exp in exports:
                if exp.get("is_reexport") and exp.get("source_module"):
                    source_file = Path(exp["file_path"]).as_posix()
                    source_node_id = f"file:{source_file}"
                    fake_imp = {
                        "file_path": source_file,
                        "module": exp.get("source_module"),
                        "name": exp.get("name"),
                        "alias": exp.get("alias"),
                        "lineno": exp.get("lineno"),
                        "language": exp.get("language", "javascript"),
                    }
                    target_file, unresolved_ref = self.resolver.resolve_import(fake_imp)
                    if target_file:
                        target_node_id = f"file:{target_file}"
                        edge_added = self._add_edge(
                            source=source_node_id,
                            target=target_node_id,
                            edge_type=EDGE_TYPE_IMPORTS,
                            metadata={
                                "source_file": source_file,
                                "target_file": target_file,
                                "module": exp.get("source_module"),
                                "imported_name": exp.get("name"),
                                "alias": exp.get("alias"),
                                "line": exp.get("lineno"),
                                "is_reexport": True,
                                "resolution_status": "resolved",
                            },
                        )
                        if edge_added:
                            self.resolved_imports_count += 1
                    else:
                        if unresolved_ref:
                            self.unresolved_references.append(unresolved_ref)
                        self.unresolved_imports_count += 1

    def _build_call_edges(self, calls: list[dict[str, Any]]) -> None:
        """Resolve call expressions and create CALLS edges between callers and callees."""
        for call in calls:
            source_file = Path(call["file_path"]).as_posix()
            caller_id = call.get("caller_symbol_id")
            is_module_level = call.get("is_module_level", False)

            target_node_id, unresolved_ref, strategy = self.resolver.resolve_call(call)

            if target_node_id:
                if is_module_level or not caller_id:
                    source_node_id = f"file:{source_file}"
                else:
                    source_node_id = f"symbol:{caller_id}"

                edge_added = self._add_edge(
                    source=source_node_id,
                    target=target_node_id,
                    edge_type=EDGE_TYPE_CALLS,
                    metadata={
                        "source_file": source_file,
                        "callee": call.get("callee"),
                        "callee_name": call.get("callee_name"),
                        "line": call.get("lineno"),
                        "col_offset": call.get("col_offset"),
                        "is_module_level": is_module_level,
                        "strategy": strategy,
                        "resolution_status": "resolved",
                    },
                )
                if edge_added:
                    self.resolved_calls_count += 1
            else:
                if unresolved_ref:
                    self.unresolved_references.append(unresolved_ref)
                    if unresolved_ref.status == "ambiguous":
                        self.ambiguous_calls_count += 1
                    else:
                        self.unresolved_calls_count += 1
                else:
                    self.unresolved_calls_count += 1

    def _build_relation_edges(self, relations: list[dict[str, Any]]) -> None:
        """Create EXTENDS / IMPLEMENTS / RENDERS edges; unresolved targets are recorded, never faked."""
        for rel in relations:
            source, target, unresolved, edge_type = self.resolver.resolve_relation(rel)
            file_path = Path(rel["file_path"]).as_posix()
            if source is None or source not in self.nodes:
                source = f"file:{file_path}" if f"file:{file_path}" in self.nodes else None
            if source is None:
                continue
            if target and target in self.nodes:
                self._add_edge(
                    source=source,
                    target=target,
                    edge_type=edge_type,
                    metadata={
                        "source_file": file_path,
                        "target_name": rel.get("target"),
                        "line": rel.get("lineno"),
                        "col_offset": rel.get("col_offset"),
                        "resolution_status": "resolved",
                        "file_level": target.startswith("file:"),
                    },
                )
            elif unresolved is not None:
                self.unresolved_references.append(unresolved)

    def _add_edge(
        self,
        source: str,
        target: str,
        edge_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> bool:
        """Add a directed edge between source and target with deduplication."""
        if source not in self.nodes or target not in self.nodes:
            return False

        key = (source, target, edge_type)
        if key in self.edges:
            existing_meta = self.edges[key].metadata
            if metadata and "line" in metadata:
                lines = existing_meta.setdefault("lines", [])
                new_line = metadata["line"]
                if new_line and new_line not in lines:
                    lines.append(new_line)
            return False

        meta = dict(metadata or {})
        if "line" in meta and "lines" not in meta:
            meta["lines"] = [meta["line"]]

        edge_id = f"edge:{edge_type.lower()}:{source}->{target}"
        self.edges[key] = GraphEdge(
            id=edge_id,
            source=source,
            target=target,
            type=edge_type,
            metadata=meta,
        )
        return True

    def _validate_edge_endpoints(self) -> None:
        """Remove any edges whose source or target vertices are missing from nodes."""
        invalid_keys: list[tuple[str, str, str]] = []
        for key, edge in self.edges.items():
            if edge.source not in self.nodes or edge.target not in self.nodes:
                invalid_keys.append(key)
        for k in invalid_keys:
            del self.edges[k]

    def _calculate_summary(self) -> GraphSummary:
        """Compute aggregate statistics over all graph nodes and edges."""
        nodes_by_type: dict[str, int] = {}
        for n in self.nodes.values():
            nodes_by_type[n.type] = nodes_by_type.get(n.type, 0) + 1

        edges_by_type: dict[str, int] = {}
        for e in self.edges.values():
            edges_by_type[e.type] = edges_by_type.get(e.type, 0) + 1

        return GraphSummary(
            node_count=len(self.nodes),
            edge_count=len(self.edges),
            nodes_by_type=dict(sorted(nodes_by_type.items())),
            edges_by_type=dict(sorted(edges_by_type.items())),
            resolved_calls=self.resolved_calls_count,
            ambiguous_calls=self.ambiguous_calls_count,
            unresolved_calls=self.unresolved_calls_count,
            resolved_imports=self.resolved_imports_count,
            unresolved_imports=self.unresolved_imports_count,
        )


def build_graph(
    repo_root: Path | str,
    inventory_path: Path | str,
    analysis_path: Path | str | list[Path | str],
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Build and serialize code graph from inventory and one or more analysis files."""
    root_path = Path(repo_root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(f"Repository root does not exist: {root_path}")
    if not root_path.is_dir():
        raise NotADirectoryError(f"Repository root is not a directory: {root_path}")

    inv_path = Path(inventory_path).resolve()
    if not inv_path.exists():
        raise FileNotFoundError(f"Inventory file does not exist: {inv_path}")

    with open(inv_path, "r", encoding="utf-8") as f:
        inv_data = json.load(f)

    if isinstance(analysis_path, (list, tuple)):
        analysis_paths = [Path(p).resolve() for p in analysis_path]
    else:
        analysis_paths = [Path(analysis_path).resolve()]

    analysis_data_list = []
    for ana_p in analysis_paths:
        if not ana_p.exists():
            raise FileNotFoundError(f"Analysis file does not exist: {ana_p}")
        with open(ana_p, "r", encoding="utf-8") as f:
            analysis_data_list.append(json.load(f))

    builder = GraphBuilder(
        repo_root=root_path,
        inventory_data=inv_data,
        analysis_data=analysis_data_list,
    )
    graph = builder.build()
    graph_dict = graph.to_dict()

    if output_path is not None:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(graph_dict, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return graph_dict


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for graph builder."""
    parser = argparse.ArgumentParser(
        prog="python -m app.graph.graph_builder",
        description="Astral Cartographer - Code Graph Builder",
    )
    parser.add_argument(
        "-r",
        "--root",
        type=str,
        default=".",
        help="Path to repository root directory (default: .)",
    )
    parser.add_argument(
        "-i",
        "--inventory",
        type=str,
        default="output/repository_inventory.json",
        help="Path to repository_inventory.json (default: output/repository_inventory.json)",
    )
    parser.add_argument(
        "-a",
        "--analysis",
        nargs="+",
        action=AnalysisAction,
        default=None,
        help="Path to analysis JSON report(s). Can be specified multiple times.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Path to output code_graph.json (default: {DEFAULT_OUTPUT_FILENAME})",
    )
    return parser.parse_args(args)


def print_cli_summary(graph_dict: dict[str, Any], output_path: Optional[Path]) -> None:
    """Display terminal report of graph construction results."""
    summary = graph_dict["summary"]
    repo = graph_dict.get("repository", {})

    sep = "=" * 60
    print(sep)
    print(" Astral Cartographer - Code Graph Builder Summary")
    print(sep)
    print(f"Repository:              {repo.get('name', 'Unknown')}")
    if output_path:
        print(f"Output File:             {output_path}")
    print(f"Schema Version:          {graph_dict.get('schema_version', 1)}")
    print("-" * 60)
    print("Graph Entities:")
    print(f"  Total Nodes:           {summary['node_count']}")
    for ntype, count in summary.get("nodes_by_type", {}).items():
        print(f"    - {ntype:<18} {count}")
    print(f"  Total Edges:           {summary['edge_count']}")
    for etype, count in summary.get("edges_by_type", {}).items():
        print(f"    - {etype:<18} {count}")
    print("-" * 60)
    print("Resolution Metrics:")
    print(f"  Resolved Calls:        {summary['resolved_calls']}")
    print(f"  Ambiguous Calls:       {summary['ambiguous_calls']}")
    print(f"  Unresolved Calls:      {summary['unresolved_calls']}")
    print(f"  Resolved Imports:      {summary['resolved_imports']}")
    print(f"  Unresolved Imports:    {summary['unresolved_imports']}")
    print(sep)
    print("Code graph construction completed successfully.")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI execution entrypoint."""
    args = parse_args(argv)

    try:
        repo_root = Path(args.root).resolve()
        inventory_path = Path(args.inventory).resolve()
        output_path = Path(args.output).resolve() if args.output else None

        if args.analysis:
            analysis_paths = [Path(p).resolve() for p in args.analysis]
        else:
            default_py = Path("output/python_analysis.json").resolve()
            default_js = Path("output/javascript_analysis.json").resolve()
            analysis_paths = []
            if default_py.exists():
                analysis_paths.append(default_py)
            if default_js.exists():
                analysis_paths.append(default_js)
            if not analysis_paths:
                analysis_paths.append(default_py)

        graph_dict = build_graph(
            repo_root=repo_root,
            inventory_path=inventory_path,
            analysis_path=analysis_paths,
            output_path=output_path,
        )

        print_cli_summary(graph_dict, output_path)
        return 0

    except (FileNotFoundError, NotADirectoryError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as err:
        print(f"JSON Decode Error in input artifact: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error during graph construction: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
