"""
Symbol and import resolution engine for Astral Cartographer.

Resolves imports and call expressions to concrete local definitions
using conservative matching and explicit ambiguity tracking.
Supports Python, JavaScript, and TypeScript language semantics.
"""

from __future__ import annotations

import builtins
from dataclasses import dataclass, field
import logging
import sys
from typing import Any, Optional

from app.services.parsers.base import ParseResult

logger = logging.getLogger(__name__)

# Standard Python built-in function and exception names
PYTHON_BUILTINS: frozenset[str] = frozenset(dir(builtins))

# Standard library module names (Python 3.10+)
STDLIB_MODULE_NAMES: frozenset[str] = getattr(
    sys, "stdlib_module_names", frozenset()
)

# Standard JavaScript / TypeScript built-ins and runtime globals
JS_BUILTINS: frozenset[str] = frozenset(
    {
        "console",
        "Math",
        "JSON",
        "Object",
        "Array",
        "String",
        "Number",
        "Boolean",
        "Date",
        "RegExp",
        "Error",
        "Map",
        "Set",
        "WeakMap",
        "WeakSet",
        "Promise",
        "Symbol",
        "Proxy",
        "Reflect",
        "Intl",
        "setTimeout",
        "clearTimeout",
        "setInterval",
        "clearInterval",
        "fetch",
        "process",
        "document",
        "window",
        "require",
        "module",
        "exports",
    }
)

STATUS_RESOLVED: str = "resolved"
STATUS_AMBIGUOUS: str = "ambiguous"
STATUS_UNRESOLVED: str = "unresolved"
STATUS_EXTERNAL: str = "external"


@dataclass
class ResolvedCall:
    """A resolved invocation link between caller and target."""

    caller_id: str
    callee_name: str
    target_id: Optional[str]
    status: str  # resolved | ambiguous | unresolved | external
    file_path: str
    line: int


class SymbolResolver:
    """Indexes codebase symbols and imports to resolve cross-file dependencies and calls."""

    def __init__(self, parse_results: dict[str, ParseResult]) -> None:
        self.parse_results = parse_results

        # Indices
        self.symbols_by_id: dict[str, Any] = {}
        self.symbols_by_name: dict[str, list[dict[str, Any]]] = {}
        self.symbols_by_file: dict[str, list[dict[str, Any]]] = {}
        self.imports_by_file: dict[str, dict[str, str]] = {}  # file -> { imported_name/alias: target_file }

        self._build_indices()

    def _build_indices(self) -> None:
        for file_path, result in self.parse_results.items():
            self.symbols_by_file[file_path] = []
            self.imports_by_file[file_path] = {}

            # Index symbols
            for sym in result.symbols:
                prefix = "func" if sym.kind == "function" else "class"
                sym_id = f"{prefix}::{file_path}::{sym.name}"
                sym_data = {
                    "id": sym_id,
                    "name": sym.name,
                    "kind": sym.kind,
                    "file_path": file_path,
                    "line_start": sym.line_start,
                    "line_end": sym.line_end,
                    "bases": sym.bases,
                }
                self.symbols_by_id[sym_id] = sym_data
                self.symbols_by_name.setdefault(sym.name, []).append(sym_data)
                self.symbols_by_file[file_path].append(sym_data)

            # Index imports
            for imp in result.imports:
                if imp.resolved_path:
                    for name in imp.imported_names:
                        clean_name = name.split(" as ")[-1].strip()
                        self.imports_by_file[file_path][clean_name] = imp.resolved_path

    def resolve_calls(self) -> list[ResolvedCall]:
        """Resolve all call sites across all parsed files."""
        resolved: list[ResolvedCall] = []

        for file_path, result in self.parse_results.items():
            lang = result.language
            file_node_id = f"file::{file_path}"

            for call in getattr(result, "calls", []):
                callee = call.callee_name
                line = call.line
                caller_id = f"func::{file_path}::{call.caller_name}" if call.caller_name else file_node_id

                # 1. Check built-ins
                if (lang == "python" and callee in PYTHON_BUILTINS) or (
                    lang in ("javascript", "typescript") and callee in JS_BUILTINS
                ):
                    resolved.append(
                        ResolvedCall(
                            caller_id=caller_id,
                            callee_name=callee,
                            target_id=None,
                            status=STATUS_EXTERNAL,
                            file_path=file_path,
                            line=line,
                        )
                    )
                    continue

                # 2. Check local file symbols
                local_candidates = [
                    s for s in self.symbols_by_file.get(file_path, []) if s["name"] == callee
                ]
                if local_candidates:
                    target_id = local_candidates[0]["id"]
                    resolved.append(
                        ResolvedCall(
                            caller_id=caller_id,
                            callee_name=callee,
                            target_id=target_id,
                            status=STATUS_RESOLVED,
                            file_path=file_path,
                            line=line,
                        )
                    )
                    continue

                # 3. Check explicitly imported symbols
                file_imports = self.imports_by_file.get(file_path, {})
                if callee in file_imports:
                    target_file = file_imports[callee]
                    target_candidates = [
                        s for s in self.symbols_by_file.get(target_file, []) if s["name"] == callee
                    ]
                    if target_candidates:
                        target_id = target_candidates[0]["id"]
                        resolved.append(
                            ResolvedCall(
                                caller_id=caller_id,
                                callee_name=callee,
                                target_id=target_id,
                                status=STATUS_RESOLVED,
                                file_path=file_path,
                                line=line,
                            )
                        )
                        continue

                # 4. Check global symbol matches
                global_candidates = self.symbols_by_name.get(callee, [])
                if len(global_candidates) == 1:
                    resolved.append(
                        ResolvedCall(
                            caller_id=caller_id,
                            callee_name=callee,
                            target_id=global_candidates[0]["id"],
                            status=STATUS_RESOLVED,
                            file_path=file_path,
                            line=line,
                        )
                    )
                elif len(global_candidates) > 1:
                    resolved.append(
                        ResolvedCall(
                            caller_id=caller_id,
                            callee_name=callee,
                            target_id=global_candidates[0]["id"],
                            status=STATUS_AMBIGUOUS,
                            file_path=file_path,
                            line=line,
                        )
                    )
                else:
                    resolved.append(
                        ResolvedCall(
                            caller_id=caller_id,
                            callee_name=callee,
                            target_id=None,
                            status=STATUS_UNRESOLVED,
                            file_path=file_path,
                            line=line,
                        )
                    )

        return resolved
