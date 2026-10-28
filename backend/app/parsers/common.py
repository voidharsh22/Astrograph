"""Shared helpers for tree-sitter language adapters (Java, Kotlin, Rust).

A language adapter is a function ``parse_source(file_path, source_bytes) -> FileParseResult``.
``run_adapter`` turns that into the repository-level analysis artifact consumed by the graph
builder, using the same JSON layout as the Python and JavaScript parsers.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

import tree_sitter as ts

from app.parsers.models import FileParseResult, ParseError

logger = logging.getLogger(__name__)

SCHEMA_VERSION = 1
MAX_FILE_BYTES = 5 * 1024 * 1024

Adapter = Callable[[str, bytes], FileParseResult]


@dataclass(frozen=True)
class AdapterSpec:
    """Describes one tree-sitter language adapter for the generic runner."""

    key: str  # summary key prefix, e.g. "java" -> java_files_discovered
    languages: tuple[str, ...]  # scanner language names handled by this adapter
    parse_source: Adapter


class TreeCursorHelper:
    """Small helpers shared by adapters for reading node text and positions."""

    def __init__(self, source: bytes) -> None:
        self.source = source

    def text(self, node: Optional[ts.Node]) -> str:
        if node is None:
            return ""
        return self.source[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

    @staticmethod
    def line(node: ts.Node) -> int:
        return node.start_point.row + 1

    @staticmethod
    def end_line(node: ts.Node) -> int:
        return node.end_point.row + 1

    @staticmethod
    def col(node: ts.Node) -> int:
        return node.start_point.column

    @staticmethod
    def end_col(node: ts.Node) -> int:
        return node.end_point.column


def collect_syntax_errors(root: ts.Node, file_path: str, helper: TreeCursorHelper, limit: int = 20) -> list[ParseError]:
    """Report ERROR / MISSING nodes (bounded) without dumping source text."""
    errors: list[ParseError] = []
    if not root.has_error:
        return errors
    stack = [root]
    seen: set[tuple[int, int]] = set()
    while stack and len(errors) < limit:
        node = stack.pop()
        if node.is_error or node.is_missing:
            point = (node.start_point.row, node.start_point.column)
            if point not in seen:
                seen.add(point)
                message = (
                    f"Missing syntax node '{node.type}'"
                    if node.is_missing
                    else f"Syntax error near '{helper.text(node)[:40]!s}'".replace("\n", " ")
                )
                errors.append(ParseError(file_path, point[0] + 1, point[1], message))
            continue
        if node.has_error:
            stack.extend(reversed(node.children))
    errors.sort(key=lambda e: (e.lineno or 0, e.col_offset or 0))
    return errors


def parse_with(parser: ts.Parser, source: bytes) -> ts.Node:
    return parser.parse(source).root_node


def run_adapter(
    spec: AdapterSpec,
    inventory_path: Path | str,
    repo_root: Path | str,
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Parse every inventory file for ``spec`` and return/write the analysis artifact.

    One failing file never aborts the run: decoding, IO and parser exceptions are recorded
    as file-level parse errors and the remaining files are still analysed.
    """
    root = Path(repo_root).resolve()
    inventory = json.loads(Path(inventory_path).read_text(encoding="utf-8"))
    files = [f for f in inventory.get("files", []) if f.get("language") in spec.languages]

    symbols, imports, exports, calls, relations, errors = [], [], [], [], [], []
    parsed = 0
    files_with_errors = 0
    for info in sorted(files, key=lambda f: f["path"]):
        rel = info["path"]
        try:
            target = (root / rel).resolve()
            if not target.is_relative_to(root) or target.is_symlink():
                raise ValueError("path escapes repository or is a symlink")
            if target.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("file exceeds parser size limit")
            result = spec.parse_source(rel, target.read_bytes())
        except Exception as exc:  # noqa: BLE001 - isolate every file-level failure
            logger.warning("%s parser failed on %s: %s", spec.key, rel, type(exc).__name__)
            result = FileParseResult(file_path=rel, errors=[ParseError(rel, None, None, f"Parser failure: {type(exc).__name__}: {exc}"[:300])])
        if result.errors:
            files_with_errors += 1
            errors.extend(result.errors)
        else:
            parsed += 1
        symbols.extend(result.symbols)
        imports.extend(result.imports)
        exports.extend(result.exports)
        calls.extend(result.calls)
        relations.extend(result.relations)

    symbols.sort(key=lambda s: (s.file_path, s.lineno, s.col_offset, s.id))
    imports.sort(key=lambda i: (i.file_path, i.lineno, i.col_offset, i.module or "", i.name))
    calls.sort(key=lambda c: (c.file_path, c.lineno, c.col_offset, c.callee))
    relations.sort(key=lambda r: (r.file_path, r.lineno, r.col_offset, r.kind, r.target))
    errors.sort(key=lambda e: (e.file_path, e.lineno or 0, e.col_offset or 0))

    analysis = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": inventory.get("repository_name", root.name),
        "summary": {
            f"{spec.key}_files_discovered": len(files),
            f"{spec.key}_files_parsed": parsed,
            "files_with_errors": files_with_errors,
            "symbols_found": len(symbols),
            "imports_found": len(imports),
            "exports_found": len(exports),
            "calls_found": len(calls),
            "relations_found": len(relations),
        },
        "symbols": [s.to_dict() for s in symbols],
        "imports": [i.to_dict() for i in imports],
        "exports": [e.to_dict() for e in exports],
        "calls": [c.to_dict() for c in calls],
        "relations": [r.to_dict() for r in relations],
        "parse_errors": [e.to_dict() for e in errors],
    }
    if output_path is not None:
        out = Path(output_path).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(analysis, indent=2), encoding="utf-8")
    return analysis


def join_qualified(*parts: Optional[str], sep: str = ".") -> str:
    return sep.join(p for p in parts if p)


def symbol_id(file_path: str, qualified_name: str, kind: str, line: int) -> str:
    """Deterministic ID in the same format as the existing parsers."""
    return f"{file_path}::{qualified_name}:{kind}:{line}"


def unique(items: Iterable[str]) -> list[str]:
    seen: dict[str, None] = {}
    for i in items:
        seen.setdefault(i, None)
    return list(seen)
