"""
Python AST-based source code parser.

Uses the built-in `ast` module for full-fidelity extraction of:
- Import statements (import X, from X import Y, relative imports)
- Function and async function definitions
- Class definitions with inheritance bases
"""

from __future__ import annotations

import ast
from pathlib import PurePosixPath

from app.services.parsers.base import (
    BaseParser,
    ParsedCall,
    ParsedImport,
    ParsedSymbol,
    ParseResult,
)


class PythonParser(BaseParser):
    """Parses Python source files using the `ast` module."""

    @property
    def supported_extensions(self) -> set[str]:
        return {".py"}

    def parse_file(
        self, file_path: str, source_code: str, repo_files: set[str]
    ) -> ParseResult:
        loc = len([line for line in source_code.splitlines() if line.strip()])
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        calls: list[ParsedCall] = []

        try:
            tree = ast.parse(source_code, filename=file_path)
        except SyntaxError:
            # Gracefully skip files that can't be parsed
            return ParseResult(file_path=file_path, language="python", loc=loc)

        for node in ast.walk(tree):
            # --- Functions ---
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        kind="function",
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                    )
                )

            # --- Classes ---
            elif isinstance(node, ast.ClassDef):
                bases = []
                for base in node.bases:
                    if isinstance(base, ast.Name):
                        bases.append(base.id)
                    elif isinstance(base, ast.Attribute):
                        bases.append(ast.unparse(base))
                symbols.append(
                    ParsedSymbol(
                        name=node.name,
                        kind="class",
                        line_start=node.lineno,
                        line_end=node.end_lineno or node.lineno,
                        bases=bases,
                    )
                )

            # --- import X / import X as Y ---
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    resolved = self._resolve_import(alias.name, file_path, repo_files)
                    imports.append(
                        ParsedImport(
                            raw_statement=f"import {alias.name}",
                            resolved_path=resolved,
                            imported_names=[alias.asname or alias.name],
                        )
                    )

            # --- from X import Y ---
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                level = node.level or 0
                names = [alias.name for alias in node.names]

                if level > 0:
                    # Relative import — resolve from current file's directory
                    resolved = self._resolve_relative_import(
                        module, level, file_path, repo_files
                    )
                else:
                    resolved = self._resolve_import(module, file_path, repo_files)

                raw = f"from {'.' * level}{module} import {', '.join(names)}"
                imports.append(
                    ParsedImport(
                        raw_statement=raw,
                        resolved_path=resolved,
                        imported_names=names,
                    )
                )

            # --- Function / Method Calls ---
            elif isinstance(node, ast.Call):
                callee: str | None = None
                if isinstance(node.func, ast.Name):
                    callee = node.func.id
                elif isinstance(node.func, ast.Attribute):
                    callee = node.func.attr
                if callee:
                    calls.append(ParsedCall(callee_name=callee, line=node.lineno))

        return ParseResult(
            file_path=file_path,
            language="python",
            symbols=symbols,
            imports=imports,
            calls=calls,
            loc=loc,
        )

    def _resolve_import(
        self, module_name: str, current_file: str, repo_files: set[str]
    ) -> str | None:
        """Try to resolve a dotted module name to a file path within the repo."""
        # Convert dotted path to file path: "app.services.weather" -> "app/services/weather"
        parts = module_name.replace(".", "/")

        # Try as a direct .py file
        candidate = f"{parts}.py"
        if candidate in repo_files:
            return candidate

        # Try as a package __init__.py
        candidate = f"{parts}/__init__.py"
        if candidate in repo_files:
            return candidate

        # External dependency — return None
        return None

    def _resolve_relative_import(
        self,
        module_name: str,
        level: int,
        current_file: str,
        repo_files: set[str],
    ) -> str | None:
        """Resolve a relative import (from .X import Y) to a repo file path."""
        current_dir = PurePosixPath(current_file.replace("\\", "/")).parent

        # Walk up `level - 1` directories (level=1 means current package)
        base = current_dir
        for _ in range(level - 1):
            base = base.parent

        if module_name:
            relative = str(base / module_name.replace(".", "/"))
        else:
            relative = str(base)

        # Try as .py file
        candidate = f"{relative}.py"
        if candidate in repo_files:
            return candidate

        # Try as package
        candidate = f"{relative}/__init__.py"
        if candidate in repo_files:
            return candidate

        return None
