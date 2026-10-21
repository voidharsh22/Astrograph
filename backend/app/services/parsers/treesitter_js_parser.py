"""
High-fidelity Tree-sitter JavaScript & TypeScript Parser for Astral Cartographer.

Extracts symbols (functions, arrow functions, classes, methods, constructors,
interfaces, type aliases, enums), imports (ESM & CommonJS), and call expressions
without executing user code.
"""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath
from typing import Any, Optional

import tree_sitter as ts
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts

from app.services.parsers.base import (
    BaseParser,
    ParsedCall,
    ParsedImport,
    ParsedSymbol,
    ParseResult,
)

logger = logging.getLogger(__name__)

JS_EXTENSIONS: frozenset[str] = frozenset({".js", ".jsx", ".mjs", ".cjs"})
TS_EXTENSIONS: frozenset[str] = frozenset({".ts", ".mts", ".cts"})
TSX_EXTENSIONS: frozenset[str] = frozenset({".tsx"})
ALL_SUPPORTED_EXTENSIONS: frozenset[str] = (
    JS_EXTENSIONS | TS_EXTENSIONS | TSX_EXTENSIONS
)

JS_LANGUAGE: ts.Language = ts.Language(tsjs.language())
TS_LANGUAGE: ts.Language = ts.Language(tsts.language_typescript())
TSX_LANGUAGE: ts.Language = ts.Language(tsts.language_tsx())


def _get_parser(file_path: str) -> tuple[str, ts.Parser]:
    ext = Path(file_path).suffix.lower()
    if ext in TSX_EXTENSIONS:
        return "typescript", ts.Parser(TSX_LANGUAGE)
    if ext in TS_EXTENSIONS:
        return "typescript", ts.Parser(TS_LANGUAGE)
    return "javascript", ts.Parser(JS_LANGUAGE)


class TreeSitterJSParser(BaseParser):
    """Parses JavaScript and TypeScript source files using Tree-sitter."""

    @property
    def supported_extensions(self) -> set[str]:
        return set(ALL_SUPPORTED_EXTENSIONS)

    def parse_file(
        self,
        file_path: str,
        source_code: str,
        repo_files: set[str],
    ) -> ParseResult:
        loc = len([line for line in source_code.splitlines() if line.strip()])
        symbols: list[ParsedSymbol] = []
        imports: list[ParsedImport] = []
        calls: list[ParsedCall] = []

        lang_name, parser = _get_parser(file_path)
        source_bytes = source_code.encode("utf-8", errors="replace")

        try:
            tree = parser.parse(source_bytes)
        except Exception as exc:
            logger.warning("Tree-sitter parse failed for %s: %s", file_path, exc)
            return ParseResult(file_path=file_path, language=lang_name, loc=loc)

        def _node_text(node: ts.Node) -> str:
            return source_bytes[node.start_byte : node.end_byte].decode("utf-8", errors="replace")

        def _resolve_js_import(import_path: str) -> str | None:
            # Skip bare external package specifiers (e.g. "react", "express")
            if not import_path.startswith("."):
                return None

            current_dir = PurePosixPath(file_path).parent
            candidate_base = current_dir / import_path
            norm = PurePosixPath(candidate_base.as_posix())

            # Try exact matches and common JS extensions
            variants = [
                str(norm),
                *[f"{norm}{ext}" for ext in [".js", ".ts", ".jsx", ".tsx", ".mjs", ".cjs"]],
                *[f"{norm}/index{ext}" for ext in [".js", ".ts", ".jsx", ".tsx"]],
            ]
            for v in variants:
                clean = str(PurePosixPath(v)).replace("\\", "/")
                if clean in repo_files:
                    return clean
            return None

        def _walk(node: ts.Node) -> None:
            node_type = node.type

            # --- Function Declarations ---
            if node_type in ("function_declaration", "generator_function_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        ParsedSymbol(
                            name=_node_text(name_node),
                            kind="function",
                            line_start=node.start_point.row + 1,
                            line_end=node.end_point.row + 1,
                        )
                    )

            # --- Class Declarations ---
            elif node_type == "class_declaration":
                name_node = node.child_by_field_name("name")
                if name_node:
                    bases: list[str] = []
                    # Check for class heritage / extends
                    for child in node.children:
                        if child.type in ("class_heritage", "extends_clause"):
                            base_text = _node_text(child).replace("extends", "").strip()
                            if base_text:
                                bases.append(base_text)
                    symbols.append(
                        ParsedSymbol(
                            name=_node_text(name_node),
                            kind="class",
                            line_start=node.start_point.row + 1,
                            line_end=node.end_point.row + 1,
                            bases=bases,
                        )
                    )

            # --- TypeScript Interface / Type Alias / Enum ---
            elif node_type in ("interface_declaration", "type_alias_declaration", "enum_declaration"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    symbols.append(
                        ParsedSymbol(
                            name=_node_text(name_node),
                            kind="class" if node_type == "interface_declaration" else "function",
                            line_start=node.start_point.row + 1,
                            line_end=node.end_point.row + 1,
                        )
                    )

            # --- Variable Declarations (Arrow Functions & require calls) ---
            elif node_type in ("variable_declarator", "lexical_declaration"):
                name_node = node.child_by_field_name("name")
                value_node = node.child_by_field_name("value")
                if name_node and value_node and value_node.type in ("arrow_function", "function_expression"):
                    symbols.append(
                        ParsedSymbol(
                            name=_node_text(name_node),
                            kind="function",
                            line_start=node.start_point.row + 1,
                            line_end=node.end_point.row + 1,
                        )
                    )

            # --- ESM Import Statement ---
            elif node_type == "import_statement":
                source_node = node.child_by_field_name("source")
                if source_node:
                    raw_path = _node_text(source_node).strip("'\"`")
                    resolved = _resolve_js_import(raw_path)
                    imported_names: list[str] = []
                    for child in node.children:
                        if child.type == "import_clause":
                            imported_names.append(_node_text(child))
                    imports.append(
                        ParsedImport(
                            raw_statement=_node_text(node),
                            resolved_path=resolved,
                            imported_names=imported_names,
                        )
                    )

            # --- Call Expression ---
            elif node_type in ("call_expression", "new_expression"):
                fn_node = node.child_by_field_name("function") or node.child_by_field_name("constructor")
                if fn_node:
                    fn_name = _node_text(fn_node).split(".")[-1].strip()
                    # Check for require('...')
                    if fn_name == "require":
                        args_node = node.child_by_field_name("arguments")
                        if args_node and args_node.named_child_count > 0:
                            first_arg = args_node.named_children[0]
                            raw_path = _node_text(first_arg).strip("'\"`")
                            resolved = _resolve_js_import(raw_path)
                            imports.append(
                                ParsedImport(
                                    raw_statement=_node_text(node),
                                    resolved_path=resolved,
                                    imported_names=[raw_path],
                                )
                            )
                    elif fn_name:
                        calls.append(ParsedCall(callee_name=fn_name, line=node.start_point.row + 1))

            for child in node.children:
                _walk(child)

        _walk(tree.root_node)

        return ParseResult(
            file_path=file_path,
            language=lang_name,
            symbols=symbols,
            imports=imports,
            calls=calls,
            loc=loc,
        )
