"""Astral Cartographer - JavaScript/TypeScript Structural Parser.

Extracts symbols (functions, arrow functions, classes, methods, constructors,
interfaces, type aliases, enums), imports, exports, and call expressions
from JavaScript and TypeScript source files using Tree-sitter without executing code.
Integrates with the Step 1 repository scanner inventory.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Any, Optional

import tree_sitter as ts
import tree_sitter_javascript as tsjs
import tree_sitter_typescript as tsts

from app.parsers.models import (
    Call,
    Export,
    FileParseResult,
    Import,
    JSParseSummary,
    ParseError,
    Symbol,
)

SCHEMA_VERSION: int = 1
DEFAULT_OUTPUT_FILENAME: str = "output/javascript_analysis.json"

# Supported language extensions
JS_EXTENSIONS: frozenset[str] = frozenset({".js", ".jsx", ".mjs", ".cjs"})
TS_EXTENSIONS: frozenset[str] = frozenset({".ts", ".mts", ".cts"})
TSX_EXTENSIONS: frozenset[str] = frozenset({".tsx"})
ALL_SUPPORTED_EXTENSIONS: frozenset[str] = (
    JS_EXTENSIONS | TS_EXTENSIONS | TSX_EXTENSIONS
)

# Tree-sitter Language instances
JS_LANGUAGE: ts.Language = ts.Language(tsjs.language())
TS_LANGUAGE: ts.Language = ts.Language(tsts.language_typescript())
TSX_LANGUAGE: ts.Language = ts.Language(tsts.language_tsx())


def get_language_and_parser(file_path: str) -> tuple[str, ts.Parser]:
    """Return language name ('javascript' or 'typescript') and configured Tree-sitter Parser."""
    ext = Path(file_path).suffix.lower()
    if ext in TSX_EXTENSIONS:
        return "typescript", ts.Parser(TSX_LANGUAGE)
    if ext in TS_EXTENSIONS:
        return "typescript", ts.Parser(TS_LANGUAGE)
    return "javascript", ts.Parser(JS_LANGUAGE)


class JavaScriptTreeSitterVisitor:
    """Extracts symbols, imports, exports, and calls from a JS/TS syntax tree."""

    def __init__(
        self,
        file_path: str,
        source_bytes: bytes,
        language: str,
    ) -> None:
        self.file_path: str = file_path
        self.source_bytes: bytes = source_bytes
        self.language: str = language

        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.exports: list[Export] = []
        self.calls: list[Call] = []
        self.errors: list[ParseError] = []

        # Scope stack: list of (qualified_name, scope_type) e.g. ("PaymentService", "class")
        self._scope_stack: list[tuple[str, str]] = []
        # Function stack: list of Symbol instances representing current active function/method
        self._func_stack: list[Symbol] = []
        # start_byte of require() calls already recorded by a declaration handler
        self._consumed_requires: set[int] = set()

    def _text(self, node: Optional[ts.Node]) -> str:
        if node is None:
            return ""
        return self.source_bytes[node.start_byte : node.end_byte].decode(
            "utf-8", errors="replace"
        )

    def _lineno(self, node: ts.Node) -> int:
        return node.start_point.row + 1

    def _end_lineno(self, node: ts.Node) -> int:
        return node.end_point.row + 1

    def _col_offset(self, node: ts.Node) -> int:
        return node.start_point.column

    def _current_scope_name(self) -> Optional[str]:
        if not self._scope_stack:
            return None
        return self._scope_stack[-1][0]

    def _clean_str(self, text: str) -> str:
        return text.strip("'\"`")

    def _extract_param_name(self, node: ts.Node) -> str:
        """Extract clean parameter name string from various Tree-sitter parameter patterns."""
        if node.type == "identifier":
            return self._text(node)
        if node.type in ("required_parameter", "optional_parameter"):
            pat = node.child_by_field_name("pattern")
            if pat:
                return self._extract_param_name(pat)
        if node.type == "rest_pattern":
            for c in node.children:
                if c.type == "identifier":
                    return f"...{self._text(c)}"
            return f"...{self._text(node)}"
        if node.type == "assignment_pattern":
            left = node.child_by_field_name("left")
            if left:
                return self._extract_param_name(left)
        for c in node.children:
            if c.type == "identifier":
                return self._text(c)
        return self._text(node)

    def _extract_parameters(self, func_node: ts.Node) -> list[str]:
        """Extract list of parameter names for a function, method, or arrow function."""
        params_node = func_node.child_by_field_name("parameters")
        if params_node:
            result = []
            for c in params_node.children:
                if c.is_named and c.type not in ("{", "}", "(", ")", ","):
                    result.append(self._extract_param_name(c))
            return result

        single_param = func_node.child_by_field_name("parameter")
        if single_param:
            return [self._extract_param_name(single_param)]

        return []

    def _extract_js_local_variables(self, body_node: Optional[ts.Node]) -> list[str]:
        """Extract names of local variables declared in a function body without recursing into nested functions."""
        if not body_node:
            return []

        local_names: set[str] = set()

        def extract_identifiers_from_pattern(pat_node: ts.Node) -> None:
            if pat_node.type == "identifier":
                local_names.add(self._text(pat_node))
            else:
                for c in pat_node.children:
                    if c.type == "identifier":
                        local_names.add(self._text(c))
                    elif c.type in (
                        "object_pattern",
                        "array_pattern",
                        "shorthand_property_identifier_pattern",
                        "pair_pattern",
                        "rest_pattern",
                    ):
                        extract_identifiers_from_pattern(c)

        queue = list(body_node.children)
        while queue:
            curr = queue.pop(0)
            if curr.type in (
                "function_declaration",
                "generator_function_declaration",
                "arrow_function",
                "function_expression",
                "class_declaration",
                "class",
            ):
                continue

            if curr.type in ("lexical_declaration", "variable_declaration"):
                for c in curr.children:
                    if c.type == "variable_declarator":
                        name_node = c.child_by_field_name("name")
                        if name_node:
                            extract_identifiers_from_pattern(name_node)
            elif curr.type == "catch_clause":
                param_node = curr.child_by_field_name("parameter")
                if param_node:
                    extract_identifiers_from_pattern(param_node)
            elif curr.type in ("for_in_statement", "for_of_statement", "for_statement"):
                left_node = curr.child_by_field_name("left") or curr.child_by_field_name("initializer")
                if left_node:
                    for c in left_node.children:
                        if c.type == "variable_declarator":
                            n_node = c.child_by_field_name("name")
                            if n_node:
                                extract_identifiers_from_pattern(n_node)
                        elif c.type == "identifier":
                            local_names.add(self._text(c))

            for child in curr.children:
                if child.type not in (
                    "function_declaration",
                    "generator_function_declaration",
                    "arrow_function",
                    "function_expression",
                    "class_declaration",
                    "class",
                ):
                    queue.append(child)

        return sorted(local_names)

    def scan_for_syntax_errors(self, root_node: ts.Node) -> None:
        """Walk syntax tree and record ERROR and MISSING nodes as ParseError instances."""
        to_visit = [root_node]
        seen_points: set[tuple[int, int]] = set()

        while to_visit:
            curr = to_visit.pop()
            if curr.type == "ERROR" or curr.is_missing:
                pt = (self._lineno(curr), self._col_offset(curr))
                if pt not in seen_points:
                    seen_points.add(pt)
                    snippet = self._text(curr)[:40].replace("\n", " ")
                    msg = (
                        f"Missing syntax node '{curr.type}'"
                        if curr.is_missing
                        else f"Syntax error near '{snippet}'"
                    )
                    self.errors.append(
                        ParseError(
                            file_path=self.file_path,
                            lineno=pt[0],
                            col_offset=pt[1],
                            error_message=msg,
                        )
                    )
            to_visit.extend(curr.children)

    def walk(self, node: ts.Node) -> None:
        """Dispatch node to appropriate handler."""
        ntype = node.type

        if ntype == "import_statement":
            self._visit_import(node)
            return

        if ntype == "export_statement":
            self._visit_export(node)
            return

        if ntype in ("function_declaration", "generator_function_declaration"):
            self._visit_function_declaration(node)
            return

        if ntype in ("lexical_declaration", "variable_declaration"):
            self._visit_variable_declaration(node)
            return

        if ntype in ("class_declaration", "class"):
            self._visit_class_declaration(node)
            return

        if ntype == "interface_declaration":
            self._visit_interface_declaration(node)
            return

        if ntype == "type_alias_declaration":
            self._visit_type_alias_declaration(node)
            return

        if ntype == "enum_declaration":
            self._visit_enum_declaration(node)
            return

        if ntype == "assignment_expression":
            if self._visit_assignment_expression(node):
                return

        if ntype == "call_expression":
            self._visit_call_expression(node)
            return

        if ntype == "new_expression":
            self._visit_new_expression(node)
            return

        # Recurse children
        for child in node.children:
            self.walk(child)

    def _visit_import(self, node: ts.Node) -> None:
        """Extract import statement information."""
        is_type_only = any(c.type == "type" for c in node.children)
        source_node = node.child_by_field_name("source")
        source_val = self._clean_str(self._text(source_node)) if source_node else ""

        lineno = self._lineno(node)
        col = self._col_offset(node)

        clause = None
        for c in node.children:
            if c.type == "import_clause":
                clause = c
                break

        # Side-effect import: import './styles.css';
        if not clause:
            self.imports.append(
                Import(
                    module=source_val,
                    name="",
                    alias=None,
                    file_path=self.file_path,
                    lineno=lineno,
                    col_offset=col,
                    level=0,
                    import_form="side_effect",
                    is_type_only=is_type_only,
                    language=self.language,
                )
            )
            return

        for child in clause.children:
            # Default import: import React from 'react';
            if child.type == "identifier":
                local_name = self._text(child)
                self.imports.append(
                    Import(
                        module=source_val,
                        name="default",
                        alias=local_name,
                        file_path=self.file_path,
                        lineno=self._lineno(child),
                        col_offset=self._col_offset(child),
                        level=0,
                        import_form="type_only" if is_type_only else "default",
                        is_type_only=is_type_only,
                        language=self.language,
                    )
                )
            # Namespace import: import * as utils from './utils';
            elif child.type == "namespace_import":
                ns_id_node = child.child_by_field_name("name") or next(
                    (x for x in child.children if x.type == "identifier"), None
                )
                ns_name = self._text(ns_id_node) if ns_id_node else "*"
                self.imports.append(
                    Import(
                        module=source_val,
                        name="*",
                        alias=ns_name,
                        file_path=self.file_path,
                        lineno=self._lineno(child),
                        col_offset=self._col_offset(child),
                        level=0,
                        import_form="namespace",
                        is_type_only=is_type_only,
                        language=self.language,
                    )
                )
            # Named imports: import { useState, useEffect as useEff } from 'react';
            elif child.type == "named_imports":
                for spec in child.children:
                    if spec.type == "import_specifier":
                        spec_type = is_type_only or any(
                            x.type == "type" for x in spec.children
                        )
                        name_node = spec.child_by_field_name("name")
                        alias_node = spec.child_by_field_name("alias")
                        orig_name = self._text(name_node)
                        alias_name = self._text(alias_node) if alias_node else None

                        self.imports.append(
                            Import(
                                module=source_val,
                                name=orig_name,
                                alias=alias_name,
                                file_path=self.file_path,
                                lineno=self._lineno(spec),
                                col_offset=self._col_offset(spec),
                                level=0,
                                import_form="type_only" if spec_type else "named",
                                is_type_only=spec_type,
                                language=self.language,
                            )
                        )

    def _visit_export(self, node: ts.Node) -> None:
        """Extract export statements, declarations, and re-exports."""
        is_type_only = any(c.type == "type" for c in node.children)
        is_default = any(c.type == "default" for c in node.children)
        source_node = node.child_by_field_name("source")
        source_val = self._clean_str(self._text(source_node)) if source_node else None
        lineno = self._lineno(node)
        col = self._col_offset(node)

        # 1. Re-export all: export * from './all';
        if any(c.type == "*" for c in node.children) and not any(
            c.type == "namespace_export" for c in node.children
        ):
            self.exports.append(
                Export(
                    name="*",
                    file_path=self.file_path,
                    lineno=lineno,
                    col_offset=col,
                    alias=None,
                    is_default=False,
                    is_reexport=True,
                    source_module=source_val,
                    is_type_only=is_type_only,
                    language=self.language,
                )
            )
            return

        # 2. Re-export namespace: export * as ns from './all';
        ns_export = next(
            (c for c in node.children if c.type == "namespace_export"), None
        )
        if ns_export:
            ns_id_node = ns_export.child_by_field_name("name") or next(
                (x for x in ns_export.children if x.type == "identifier"), None
            )
            ns_name = self._text(ns_id_node)
            self.exports.append(
                Export(
                    name=ns_name,
                    file_path=self.file_path,
                    lineno=lineno,
                    col_offset=col,
                    alias="*",
                    is_default=False,
                    is_reexport=True,
                    source_module=source_val,
                    is_type_only=is_type_only,
                    language=self.language,
                )
            )
            return

        # 3. Export clause: export { a, b as c }; or export { ext } from './mod';
        clause = next((c for c in node.children if c.type == "export_clause"), None)
        if clause:
            for spec in clause.children:
                if spec.type == "export_specifier":
                    name_n = spec.child_by_field_name("name")
                    alias_n = spec.child_by_field_name("alias")
                    spec_type = is_type_only or any(
                        x.type == "type" for x in spec.children
                    )
                    # In Tree-sitter: export { a as b }: name='a', alias='b'
                    exp_name = self._text(alias_n) if alias_n else self._text(name_n)
                    local_name = self._text(name_n) if alias_n else None

                    self.exports.append(
                        Export(
                            name=exp_name,
                            file_path=self.file_path,
                            lineno=self._lineno(spec),
                            col_offset=self._col_offset(spec),
                            alias=local_name,
                            is_default=False,
                            is_reexport=bool(source_val),
                            source_module=source_val,
                            is_type_only=spec_type,
                            language=self.language,
                        )
                    )
            return

        # 4. Default export: export default foo; / export default class Bar {}
        if is_default:
            decl = node.child_by_field_name("value") or next(
                (c for c in node.children if c.type not in ("export", "default", ";")),
                None,
            )
            name_val = "default"
            if decl:
                if decl.type in (
                    "function_declaration",
                    "generator_function_declaration",
                ):
                    self._visit_function_declaration(decl, is_exported=True)
                    fn_name_node = decl.child_by_field_name("name")
                    name_val = self._text(fn_name_node) or "default"
                elif decl.type in ("class_declaration", "class"):
                    self._visit_class_declaration(decl, is_exported=True)
                    cls_name_node = decl.child_by_field_name("name")
                    name_val = self._text(cls_name_node) or "default"
                elif decl.type == "identifier":
                    name_val = self._text(decl)
                else:
                    self.walk(decl)

            self.exports.append(
                Export(
                    name="default",
                    file_path=self.file_path,
                    lineno=lineno,
                    col_offset=col,
                    alias=name_val if name_val != "default" else None,
                    is_default=True,
                    is_reexport=False,
                    source_module=None,
                    is_type_only=is_type_only,
                    language=self.language,
                )
            )
            return

        # 5. Exported declaration: export const x = 1; / export function f() {} / export class C {}
        decl = node.child_by_field_name("declaration")
        if decl:
            start_sym_count = len(self.symbols)
            if decl.type in (
                "function_declaration",
                "generator_function_declaration",
            ):
                self._visit_function_declaration(decl, is_exported=True)
            elif decl.type in ("lexical_declaration", "variable_declaration"):
                self._visit_variable_declaration(decl, is_exported=True)
            elif decl.type in ("class_declaration", "class"):
                self._visit_class_declaration(decl, is_exported=True)
            elif decl.type == "interface_declaration":
                self._visit_interface_declaration(decl, is_exported=True)
            elif decl.type == "type_alias_declaration":
                self._visit_type_alias_declaration(decl, is_exported=True)
            elif decl.type == "enum_declaration":
                self._visit_enum_declaration(decl, is_exported=True)
            else:
                self.walk(decl)

            # Record export for newly created top-level symbols
            for sym in self.symbols[start_sym_count:]:
                if sym.parent_scope is None:
                    self.exports.append(
                        Export(
                            name=sym.name,
                            file_path=self.file_path,
                            lineno=sym.lineno,
                            col_offset=sym.col_offset,
                            alias=None,
                            is_default=False,
                            is_reexport=False,
                            source_module=None,
                            is_type_only=sym.kind in ("interface", "type_alias"),
                            language=self.language,
                        )
                    )

    def _visit_function_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract function or async function declaration."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<anonymous>"

        is_async = any(c.type == "async" for c in node.children)
        kind = "async_function" if is_async else "function"

        parent_scope = self._current_scope_name()
        qualified_name = f"{parent_scope}.{name}" if parent_scope else name
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:{kind}:{lineno}"

        params = self._extract_parameters(node)
        async_prefix = "async " if is_async else ""
        signature = f"{async_prefix}function {name}({', '.join(params)})"

        body_node = node.child_by_field_name("body")
        local_vars = self._extract_js_local_variables(body_node)

        sym = Symbol(
            id=symbol_id,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            lineno=lineno,
            end_lineno=end_lineno,
            col_offset=col,
            parent_scope=parent_scope,
            parameters=params,
            signature=signature,
            decorators=[],
            bases=None,
            is_async=is_async,
            language=self.language,
            is_exported=is_exported,
            local_variables=local_vars,
        )
        self.symbols.append(sym)

        # Enter function scope and walk body
        self._scope_stack.append((qualified_name, "function"))
        self._func_stack.append(sym)

        if body_node:
            for c in body_node.children:
                self.walk(c)

        self._func_stack.pop()
        self._scope_stack.pop()

    def _visit_variable_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract arrow functions or function expressions assigned to variables."""
        for child in node.children:
            if child.type != "variable_declarator":
                continue

            name_node = child.child_by_field_name("name")
            value_node = child.child_by_field_name("value")

            if not name_node or not value_node:
                continue

            if self._visit_require_declarator(name_node, value_node):
                continue

            var_name = self._text(name_node)

            if value_node.type in (
                "arrow_function",
                "function_expression",
                "generator_function",
            ):
                is_async = any(c.type == "async" for c in value_node.children)
                kind = "async_function" if is_async else "function"

                parent_scope = self._current_scope_name()
                qualified_name = (
                    f"{parent_scope}.{var_name}" if parent_scope else var_name
                )
                lineno = self._lineno(child)
                end_lineno = self._end_lineno(child)
                col = self._col_offset(child)
                symbol_id = f"{self.file_path}::{qualified_name}:{kind}:{lineno}"

                params = self._extract_parameters(value_node)
                async_prefix = "async " if is_async else ""
                if value_node.type == "arrow_function":
                    sig = f"const {var_name} = {async_prefix}({', '.join(params)}) => ..."
                else:
                    sig = f"const {var_name} = {async_prefix}function({', '.join(params)})"

                body_node = value_node.child_by_field_name("body")
                local_vars = self._extract_js_local_variables(body_node)

                sym = Symbol(
                    id=symbol_id,
                    name=var_name,
                    qualified_name=qualified_name,
                    kind=kind,
                    file_path=self.file_path,
                    lineno=lineno,
                    end_lineno=end_lineno,
                    col_offset=col,
                    parent_scope=parent_scope,
                    parameters=params,
                    signature=sig,
                    decorators=[],
                    bases=None,
                    is_async=is_async,
                    language=self.language,
                    is_exported=is_exported,
                    local_variables=local_vars,
                )
                self.symbols.append(sym)

                # Enter function scope and walk body
                self._scope_stack.append((qualified_name, "function"))
                self._func_stack.append(sym)

                if body_node:
                    self.walk(body_node)

                self._func_stack.pop()
                self._scope_stack.pop()
            else:
                # Walk non-function variable initialization for calls
                self.walk(value_node)

    # ------------------------------------------------------------------
    # CommonJS / dynamic-import support
    # ------------------------------------------------------------------
    def _string_literal_value(self, node: Optional[ts.Node]) -> Optional[str]:
        """Return the value of a plain string literal (no template substitutions)."""
        if node is None:
            return None
        if node.type == "string":
            return self._clean_str(self._text(node))
        if node.type == "template_string" and not any(
            c.type == "template_substitution" for c in node.children
        ):
            return self._clean_str(self._text(node))
        return None

    def _require_module(self, node: Optional[ts.Node]) -> Optional[str]:
        """Return the module specifier when node is `require('literal')`."""
        if node is None or node.type != "call_expression":
            return None
        fn = node.child_by_field_name("function")
        if fn is None or fn.type != "identifier" or self._text(fn) != "require":
            return None
        args = node.child_by_field_name("arguments")
        if args is None:
            return None
        named = [c for c in args.children if c.is_named and c.type != "comment"]
        if len(named) != 1:
            return None
        return self._string_literal_value(named[0])

    def _add_cjs_import(
        self, node: ts.Node, module: str, name: str, alias: Optional[str], form: str
    ) -> None:
        self.imports.append(
            Import(
                module=module,
                name=name,
                alias=alias,
                file_path=self.file_path,
                lineno=self._lineno(node),
                col_offset=self._col_offset(node),
                level=0,
                import_form=form,
                is_type_only=False,
                language=self.language,
            )
        )

    def _visit_module_loader_call(
        self, node: ts.Node, fn_node: Optional[ts.Node]
    ) -> bool:
        """Record `require('x')` and `import('x')` calls as file dependencies."""
        if fn_node is None:
            return False
        module: Optional[str] = None
        if fn_node.type == "import":
            args = node.child_by_field_name("arguments")
            first = next((c for c in (args.children if args else []) if c.is_named), None)
            module = self._string_literal_value(first)
        else:
            module = self._require_module(node)
        if module is None:
            return False
        if node.start_byte not in self._consumed_requires:
            self._add_cjs_import(node, module, "", None, "side_effect")
        return True

    def _visit_require_declarator(
        self, name_node: ts.Node, value_node: ts.Node
    ) -> bool:
        """Handle `const x = require('m')`, `const {a, b: c} = require('m')`, `require('m').p`."""
        member: Optional[str] = None
        call = value_node
        if value_node.type == "member_expression":
            call = value_node.child_by_field_name("object")
            prop = value_node.child_by_field_name("property")
            member = self._text(prop) if prop else None
            if call is None or member is None:
                return False
        module = self._require_module(call)
        if module is None:
            return False
        self._consumed_requires.add(call.start_byte)

        if name_node.type == "identifier":
            local = self._text(name_node)
            if member:
                self._add_cjs_import(name_node, module, member, local, "named")
            else:
                self._add_cjs_import(name_node, module, "*", local, "namespace")
        elif name_node.type == "object_pattern" and not member:
            added = False
            for prop in name_node.children:
                if prop.type == "shorthand_property_identifier_pattern":
                    self._add_cjs_import(prop, module, self._text(prop), None, "named")
                    added = True
                elif prop.type == "pair_pattern":
                    key = prop.child_by_field_name("key")
                    val = prop.child_by_field_name("value")
                    if key is not None and val is not None and val.type == "identifier":
                        self._add_cjs_import(
                            prop, module, self._text(key), self._text(val), "named"
                        )
                        added = True
            if not added:
                self._add_cjs_import(name_node, module, "", None, "side_effect")
        else:
            self._add_cjs_import(name_node, module, "", None, "side_effect")
        return True

    def _emit_function_symbol(
        self,
        fn_node: ts.Node,
        name: str,
        qualified_name: str,
        kind: str,
        is_exported: bool,
    ) -> Symbol:
        """Create a symbol for a function expression and walk its body."""
        is_async = any(c.type == "async" for c in fn_node.children)
        if is_async and kind == "function":
            kind = "async_function"
        lineno = self._lineno(fn_node)
        params = self._extract_parameters(fn_node)
        body_node = fn_node.child_by_field_name("body")
        sym = Symbol(
            id=f"{self.file_path}::{qualified_name}:{kind}:{lineno}",
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            lineno=lineno,
            end_lineno=self._end_lineno(fn_node),
            col_offset=self._col_offset(fn_node),
            parent_scope=self._current_scope_name(),
            parameters=params,
            signature=f"{qualified_name}({', '.join(params)})",
            decorators=[],
            bases=None,
            is_async=is_async,
            language=self.language,
            is_exported=is_exported,
            local_variables=self._extract_js_local_variables(body_node),
        )
        self.symbols.append(sym)
        self._scope_stack.append((qualified_name, "function"))
        self._func_stack.append(sym)
        if body_node:
            self.walk(body_node)
        self._func_stack.pop()
        self._scope_stack.pop()
        return sym

    def _add_cjs_export(
        self, node: ts.Node, name: str, alias: Optional[str], is_default: bool = False
    ) -> None:
        self.exports.append(
            Export(
                name=name,
                file_path=self.file_path,
                lineno=self._lineno(node),
                col_offset=self._col_offset(node),
                alias=alias,
                is_default=is_default,
                language=self.language,
            )
        )

    def _visit_assignment_expression(self, node: ts.Node) -> bool:
        """Handle CommonJS exports and `obj.method = function () {}` assignments.

        Returns True when the assignment was fully handled (children walked).
        """
        left = node.child_by_field_name("left")
        right = node.child_by_field_name("right")
        if left is None or right is None or left.type not in ("member_expression", "identifier"):
            return False
        left_text = self._text(left)
        fn_types = ("function_expression", "arrow_function", "generator_function")
        is_fn = right.type in fn_types
        file_stem = Path(self.file_path).stem

        # module.exports = ... / exports = ...
        if left_text in ("module.exports", "exports"):
            if right.type == "assignment_expression":
                return False  # chained; the inner assignment is handled when walked
            if right.type == "object":
                for member in right.children:
                    if member.type == "shorthand_property_identifier":
                        self._add_cjs_export(member, self._text(member), None)
                    elif member.type == "pair":
                        key = member.child_by_field_name("key")
                        val = member.child_by_field_name("value")
                        if key is None or val is None:
                            continue
                        key_name = self._clean_str(self._text(key))
                        if val.type == "identifier":
                            ident = self._text(val)
                            self._add_cjs_export(
                                member, key_name, ident if ident != key_name else None
                            )
                        elif val.type in fn_types:
                            self._emit_function_symbol(val, key_name, key_name, "function", True)
                            self._add_cjs_export(member, key_name, None)
                        else:
                            self.walk(val)
                    elif member.type == "method_definition":
                        mname = member.child_by_field_name("name")
                        if mname is not None:
                            n = self._text(mname)
                            self._emit_function_symbol(member, n, n, "function", True)
                            self._add_cjs_export(member, n, None)
                return True
            if right.type == "identifier":
                self._add_cjs_export(node, "default", self._text(right), is_default=True)
                return True
            if is_fn:
                fn_name_node = right.child_by_field_name("name")
                fn_name = self._text(fn_name_node) if fn_name_node else file_stem
                self._emit_function_symbol(right, fn_name, fn_name, "function", True)
                self._add_cjs_export(node, "default", fn_name, is_default=True)
                return True
            if right.type == "class":
                return False
            self._add_cjs_export(node, "default", None, is_default=True)
            self.walk(right)
            return True

        # exports.name = ... / module.exports.name = ...
        for prefix in ("module.exports.", "exports."):
            if left_text.startswith(prefix) and "." not in left_text[len(prefix):]:
                name = left_text[len(prefix):]
                if is_fn:
                    self._emit_function_symbol(right, name, name, "function", True)
                    self._add_cjs_export(node, name, None)
                    return True
                if right.type == "identifier":
                    ident = self._text(right)
                    self._add_cjs_export(node, name, ident if ident != name else None)
                    return True
                self._add_cjs_export(node, name, None)
                self.walk(right)
                return True

        # Obj.method = function () {} / Obj.prototype.method = function () {}
        if is_fn and left.type == "member_expression":
            obj = left.child_by_field_name("object")
            prop = left.child_by_field_name("property")
            if obj is not None and prop is not None and prop.type == "property_identifier":
                obj_text = self._text(obj)
                if obj_text.endswith(".prototype"):
                    obj_text = obj_text[: -len(".prototype")]
                root = obj_text.split(".")[0]
                if (
                    obj_text
                    and root not in ("this", "window", "global", "globalThis", "self", "module", "exports")
                    and root.isidentifier()
                ):
                    name = self._text(prop)
                    self._emit_function_symbol(right, name, f"{obj_text}.{name}", "method", False)
                    return True
        return False


    def _visit_class_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract class definition and its member methods and constructors."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<anonymous_class>"

        parent_scope = self._current_scope_name()
        qualified_name = f"{parent_scope}.{name}" if parent_scope else name
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:class:{lineno}"

        # Extract base classes / heritage
        bases: list[str] = []
        heritage_node = node.child_by_field_name("heritage")
        if not heritage_node:
            for c in node.children:
                if c.type == "class_heritage":
                    heritage_node = c
                    break

        if heritage_node:
            for c in heritage_node.children:
                if c.type in ("extends_clause", "implements_clause"):
                    for sub in c.children:
                        if sub.type in ("identifier", "type_identifier"):
                            bases.append(self._text(sub))
                elif c.type in ("identifier", "type_identifier"):
                    bases.append(self._text(c))

        base_str = f" extends {', '.join(bases)}" if bases else ""
        signature = f"class {name}{base_str}"

        class_sym = Symbol(
            id=symbol_id,
            name=name,
            qualified_name=qualified_name,
            kind="class",
            file_path=self.file_path,
            lineno=lineno,
            end_lineno=end_lineno,
            col_offset=col,
            parent_scope=parent_scope,
            parameters=None,
            signature=signature,
            decorators=[],
            bases=bases if bases else None,
            is_async=False,
            language=self.language,
            is_exported=is_exported,
        )
        self.symbols.append(class_sym)

        # Enter class scope
        self._scope_stack.append((qualified_name, "class"))

        body_node = node.child_by_field_name("body")
        if body_node:
            for c in body_node.children:
                if c.type == "method_definition":
                    self._visit_method_definition(c, class_qname=qualified_name)
                else:
                    self.walk(c)

        self._scope_stack.pop()

    def _visit_method_definition(
        self, node: ts.Node, class_qname: str
    ) -> None:
        """Extract class method or constructor."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<method>"

        is_async = any(c.type == "async" for c in node.children)
        is_constructor = name == "constructor"
        kind = "method"

        qualified_name = f"{class_qname}.{name}"
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:{kind}:{lineno}"

        params = self._extract_parameters(node)
        async_prefix = "async " if is_async else ""
        sig = f"{async_prefix}{name}({', '.join(params)})"

        body_node = node.child_by_field_name("body")
        local_vars = self._extract_js_local_variables(body_node)

        method_sym = Symbol(
            id=symbol_id,
            name=name,
            qualified_name=qualified_name,
            kind=kind,
            file_path=self.file_path,
            lineno=lineno,
            end_lineno=end_lineno,
            col_offset=col,
            parent_scope=class_qname,
            parameters=params,
            signature=sig,
            decorators=[],
            bases=None,
            is_async=is_async,
            language=self.language,
            is_exported=False,
            local_variables=local_vars,
        )
        self.symbols.append(method_sym)

        # Enter method scope and walk body
        self._scope_stack.append((qualified_name, "function"))
        self._func_stack.append(method_sym)

        if body_node:
            for c in body_node.children:
                self.walk(c)

        self._func_stack.pop()
        self._scope_stack.pop()

    def _visit_interface_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract TypeScript interface declaration."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<interface>"

        parent_scope = self._current_scope_name()
        qualified_name = f"{parent_scope}.{name}" if parent_scope else name
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:interface:{lineno}"

        bases: list[str] = []
        for c in node.children:
            if c.type == "extends_type_clause":
                for sub in c.children:
                    if sub.type in ("identifier", "type_identifier"):
                        bases.append(self._text(sub))

        base_str = f" extends {', '.join(bases)}" if bases else ""
        signature = f"interface {name}{base_str}"

        self.symbols.append(
            Symbol(
                id=symbol_id,
                name=name,
                qualified_name=qualified_name,
                kind="interface",
                file_path=self.file_path,
                lineno=lineno,
                end_lineno=end_lineno,
                col_offset=col,
                parent_scope=parent_scope,
                parameters=None,
                signature=signature,
                decorators=[],
                bases=bases if bases else None,
                is_async=False,
                language="typescript",
                is_exported=is_exported,
            )
        )

    def _visit_type_alias_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract TypeScript type alias declaration."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<type_alias>"

        parent_scope = self._current_scope_name()
        qualified_name = f"{parent_scope}.{name}" if parent_scope else name
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:type_alias:{lineno}"

        type_text = self._text(node).strip()
        signature = type_text.split(";")[0] if ";" in type_text else type_text

        self.symbols.append(
            Symbol(
                id=symbol_id,
                name=name,
                qualified_name=qualified_name,
                kind="type_alias",
                file_path=self.file_path,
                lineno=lineno,
                end_lineno=end_lineno,
                col_offset=col,
                parent_scope=parent_scope,
                parameters=None,
                signature=signature,
                decorators=[],
                bases=None,
                is_async=False,
                language="typescript",
                is_exported=is_exported,
            )
        )

    def _visit_enum_declaration(
        self, node: ts.Node, is_exported: bool = False
    ) -> None:
        """Extract TypeScript enum declaration."""
        name_node = node.child_by_field_name("name")
        name = self._text(name_node)
        if not name:
            name = "<enum>"

        parent_scope = self._current_scope_name()
        qualified_name = f"{parent_scope}.{name}" if parent_scope else name
        lineno = self._lineno(node)
        end_lineno = self._end_lineno(node)
        col = self._col_offset(node)
        symbol_id = f"{self.file_path}::{qualified_name}:enum:{lineno}"

        signature = f"enum {name}"

        self.symbols.append(
            Symbol(
                id=symbol_id,
                name=name,
                qualified_name=qualified_name,
                kind="enum",
                file_path=self.file_path,
                lineno=lineno,
                end_lineno=end_lineno,
                col_offset=col,
                parent_scope=parent_scope,
                parameters=None,
                signature=signature,
                decorators=[],
                bases=None,
                is_async=False,
                language="typescript",
                is_exported=is_exported,
            )
        )

    def _visit_call_expression(self, node: ts.Node) -> None:
        """Extract function or method call expression."""
        fn_node = node.child_by_field_name("function")
        if self._visit_module_loader_call(node, fn_node):
            return
        callee_expr = self._text(fn_node)
        lineno = self._lineno(node)
        col = self._col_offset(node)

        is_member = fn_node and fn_node.type == "member_expression"
        call_kind = "method_call" if is_member else "function_call"

        # Determine simple callee name
        if is_member:
            prop_node = fn_node.child_by_field_name("property")
            callee_name = self._text(prop_node) or callee_expr.split(".")[-1]
        else:
            callee_name = callee_expr

        caller_sym = self._func_stack[-1] if self._func_stack else None
        caller_id = caller_sym.id if caller_sym else None
        caller_name = caller_sym.qualified_name if caller_sym else None
        is_module_level = caller_sym is None

        self.calls.append(
            Call(
                callee=callee_expr,
                callee_name=callee_name,
                file_path=self.file_path,
                lineno=lineno,
                col_offset=col,
                caller=caller_name,
                caller_symbol_id=caller_id,
                is_module_level=is_module_level,
                call_kind=call_kind,
                language=self.language,
            )
        )

        # Walk arguments or callee expression for nested calls
        args_node = node.child_by_field_name("arguments")
        if args_node:
            for c in args_node.children:
                self.walk(c)
        if fn_node and is_member:
            obj_node = fn_node.child_by_field_name("object")
            if obj_node:
                self.walk(obj_node)

    def _visit_new_expression(self, node: ts.Node) -> None:
        """Extract constructor invocation (new ClassName())."""
        ctor_node = node.child_by_field_name("constructor")
        ctor_expr = self._text(ctor_node)
        lineno = self._lineno(node)
        col = self._col_offset(node)

        callee_expr = f"new {ctor_expr}"
        callee_name = ctor_expr.split(".")[-1]

        caller_sym = self._func_stack[-1] if self._func_stack else None
        caller_id = caller_sym.id if caller_sym else None
        caller_name = caller_sym.qualified_name if caller_sym else None
        is_module_level = caller_sym is None

        self.calls.append(
            Call(
                callee=callee_expr,
                callee_name=callee_name,
                file_path=self.file_path,
                lineno=lineno,
                col_offset=col,
                caller=caller_name,
                caller_symbol_id=caller_id,
                is_module_level=is_module_level,
                call_kind="constructor_call",
                language=self.language,
            )
        )

        args_node = node.child_by_field_name("arguments")
        if args_node:
            for c in args_node.children:
                self.walk(c)


def parse_js_source_code(
    source_code: str | bytes,
    file_path: str,
    language: Optional[str] = None,
) -> FileParseResult:
    """Parse JavaScript or TypeScript source code string or bytes into structural records."""
    if isinstance(source_code, str):
        source_bytes = source_code.encode("utf-8")
    else:
        source_bytes = source_code

    detected_lang, parser = get_language_and_parser(file_path)
    final_lang = language or detected_lang

    try:
        tree = parser.parse(source_bytes)
    except Exception as err:
        return FileParseResult(
            file_path=file_path,
            errors=[
                ParseError(
                    file_path=file_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"Tree-sitter parser exception: {err}",
                )
            ],
        )

    visitor = JavaScriptTreeSitterVisitor(
        file_path=file_path,
        source_bytes=source_bytes,
        language=final_lang,
    )

    # Scan for syntax errors
    if tree.root_node.has_error:
        visitor.scan_for_syntax_errors(tree.root_node)

    # Walk AST
    visitor.walk(tree.root_node)

    return FileParseResult(
        file_path=file_path,
        symbols=visitor.symbols,
        imports=visitor.imports,
        calls=visitor.calls,
        exports=visitor.exports,
        errors=visitor.errors,
    )


def parse_js_file_path(
    file_path: Path | str,
    repo_root: Path | str,
) -> FileParseResult:
    """Parse a single JavaScript or TypeScript file securely validating path constraints."""
    resolved_root = Path(repo_root).resolve()
    target_path = Path(file_path)

    if not target_path.is_absolute():
        target_path = (resolved_root / target_path).resolve()
    else:
        target_path = target_path.resolve()

    try:
        rel_path = target_path.relative_to(resolved_root).as_posix()
    except ValueError:
        return FileParseResult(
            file_path=str(file_path),
            errors=[
                ParseError(
                    file_path=str(file_path),
                    lineno=None,
                    col_offset=None,
                    error_message=f"File path '{file_path}' resolves outside repository root '{resolved_root}'",
                )
            ],
        )

    if target_path.is_symlink():
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"Symbolic link '{rel_path}' skipped for security",
                )
            ],
        )

    if not target_path.exists():
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"File not found: {rel_path}",
                )
            ],
        )

    try:
        source_bytes = target_path.read_bytes()
    except Exception as err:
        return FileParseResult(
            file_path=rel_path,
            errors=[
                ParseError(
                    file_path=rel_path,
                    lineno=None,
                    col_offset=None,
                    error_message=f"Could not read file: {err}",
                )
            ],
        )

    return parse_js_source_code(source_code=source_bytes, file_path=rel_path)


def parse_js_repository_inventory(
    inventory_path: Path | str,
    repo_root: Path | str,
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Parse JavaScript and TypeScript files discovered in scanner inventory report."""
    resolved_root = Path(repo_root).resolve()
    inv_file = Path(inventory_path).resolve()

    if not inv_file.exists():
        raise FileNotFoundError(f"Inventory file does not exist: {inv_file}")

    with open(inv_file, "r", encoding="utf-8") as f:
        inventory_data = json.load(f)

    repo_name = inventory_data.get("repository_name", resolved_root.name)
    all_inv_files = inventory_data.get("files", [])

    js_files = []
    ts_files = []
    for f in all_inv_files:
        lang = f.get("language")
        ext = f.get("extension", "").lower()
        if lang == "JavaScript" or ext in JS_EXTENSIONS:
            js_files.append(f)
        elif lang == "TypeScript" or ext in TS_EXTENSIONS or ext in TSX_EXTENSIONS:
            ts_files.append(f)

    all_symbols: list[Symbol] = []
    all_imports: list[Import] = []
    all_exports: list[Export] = []
    all_calls: list[Call] = []
    all_errors: list[ParseError] = []

    files_with_errors = 0
    js_parsed = 0
    ts_parsed = 0

    target_files = [(f, "javascript") for f in js_files] + [
        (f, "typescript") for f in ts_files
    ]

    for file_info, file_lang in target_files:
        rel_path = file_info["path"]
        result = parse_js_file_path(file_path=rel_path, repo_root=resolved_root)

        if result.errors:
            files_with_errors += 1
            all_errors.extend(result.errors)
        else:
            if file_lang == "javascript":
                js_parsed += 1
            else:
                ts_parsed += 1

        all_symbols.extend(result.symbols)
        all_imports.extend(result.imports)
        all_exports.extend(result.exports)
        all_calls.extend(result.calls)

    # Sort deterministically
    all_symbols.sort(key=lambda s: (s.file_path, s.lineno, s.col_offset, s.id))
    all_imports.sort(
        key=lambda i: (i.file_path, i.lineno, i.col_offset, i.module or "", i.name)
    )
    all_exports.sort(
        key=lambda e: (e.file_path, e.lineno, e.col_offset, e.name, e.alias or "")
    )
    all_calls.sort(key=lambda c: (c.file_path, c.lineno, c.col_offset, c.callee))
    all_errors.sort(key=lambda e: (e.file_path, e.lineno or 0, e.col_offset or 0))

    summary = JSParseSummary(
        javascript_files_discovered=len(js_files),
        javascript_files_parsed=js_parsed,
        typescript_files_discovered=len(ts_files),
        typescript_files_parsed=ts_parsed,
        files_with_errors=files_with_errors,
        symbols_found=len(all_symbols),
        imports_found=len(all_imports),
        exports_found=len(all_exports),
        calls_found=len(all_calls),
    )

    analysis_result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": repo_name,
        "summary": summary.to_dict(),
        "symbols": [s.to_dict() for s in all_symbols],
        "imports": [i.to_dict() for i in all_imports],
        "exports": [e.to_dict() for e in all_exports],
        "calls": [c.to_dict() for c in all_calls],
        "parse_errors": [e.to_dict() for e in all_errors],
    }

    if output_path is not None:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return analysis_result


def parse_js_repository(
    repo_root: Path | str,
    output_path: Optional[Path | str] = None,
) -> dict[str, Any]:
    """Discover and parse all JS/TS files directly when inventory is absent."""
    from app.ingestion.scanner import scan_repository

    temp_inv = scan_repository(repository_path=repo_root, output_path=None)
    repo_name = temp_inv.get("repository_name", Path(repo_root).name)
    resolved_root = Path(repo_root).resolve()

    js_files = []
    ts_files = []
    for f in temp_inv.get("files", []):
        lang = f.get("language")
        ext = f.get("extension", "").lower()
        if lang == "JavaScript" or ext in JS_EXTENSIONS:
            js_files.append(f)
        elif lang == "TypeScript" or ext in TS_EXTENSIONS or ext in TSX_EXTENSIONS:
            ts_files.append(f)

    all_symbols: list[Symbol] = []
    all_imports: list[Import] = []
    all_exports: list[Export] = []
    all_calls: list[Call] = []
    all_errors: list[ParseError] = []

    files_with_errors = 0
    js_parsed = 0
    ts_parsed = 0

    target_files = [(f, "javascript") for f in js_files] + [
        (f, "typescript") for f in ts_files
    ]

    for file_info, file_lang in target_files:
        rel_path = file_info["path"]
        result = parse_js_file_path(file_path=rel_path, repo_root=resolved_root)

        if result.errors:
            files_with_errors += 1
            all_errors.extend(result.errors)
        else:
            if file_lang == "javascript":
                js_parsed += 1
            else:
                ts_parsed += 1

        all_symbols.extend(result.symbols)
        all_imports.extend(result.imports)
        all_exports.extend(result.exports)
        all_calls.extend(result.calls)

    all_symbols.sort(key=lambda s: (s.file_path, s.lineno, s.col_offset, s.id))
    all_imports.sort(
        key=lambda i: (i.file_path, i.lineno, i.col_offset, i.module or "", i.name)
    )
    all_exports.sort(
        key=lambda e: (e.file_path, e.lineno, e.col_offset, e.name, e.alias or "")
    )
    all_calls.sort(key=lambda c: (c.file_path, c.lineno, c.col_offset, c.callee))
    all_errors.sort(key=lambda e: (e.file_path, e.lineno or 0, e.col_offset or 0))

    summary = JSParseSummary(
        javascript_files_discovered=len(js_files),
        javascript_files_parsed=js_parsed,
        typescript_files_discovered=len(ts_files),
        typescript_files_parsed=ts_parsed,
        files_with_errors=files_with_errors,
        symbols_found=len(all_symbols),
        imports_found=len(all_imports),
        exports_found=len(all_exports),
        calls_found=len(all_calls),
    )

    analysis_result: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "repository_name": repo_name,
        "summary": summary.to_dict(),
        "symbols": [s.to_dict() for s in all_symbols],
        "imports": [i.to_dict() for i in all_imports],
        "exports": [e.to_dict() for e in all_exports],
        "calls": [c.to_dict() for c in all_calls],
        "parse_errors": [e.to_dict() for e in all_errors],
    }

    if output_path is not None:
        out_p = Path(output_path).resolve()
        out_p.parent.mkdir(parents=True, exist_ok=True)
        with open(out_p, "w", encoding="utf-8") as f:
            json.dump(analysis_result, f, indent=2, ensure_ascii=False)
            f.write("\n")

    return analysis_result


def parse_args(args: Optional[list[str]] = None) -> argparse.Namespace:
    """Parse CLI arguments for the JavaScript/TypeScript parser."""
    parser = argparse.ArgumentParser(
        prog="python -m app.parsers.javascript_parser",
        description="Astral Cartographer - JavaScript/TypeScript Structural Parser",
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
        default=None,
        help="Path to repository_inventory.json from Step 1 scanner",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=DEFAULT_OUTPUT_FILENAME,
        help=f"Destination path for javascript_analysis.json (default: {DEFAULT_OUTPUT_FILENAME})",
    )
    return parser.parse_args(args)


def print_cli_summary(analysis: dict[str, Any], output_path: Optional[Path]) -> None:
    """Display a formatted summary in the terminal."""
    summary = analysis["summary"]
    errors = analysis.get("parse_errors", [])

    sep = "=" * 60
    print(sep)
    print(" Astral Cartographer - JavaScript/TypeScript Parser Summary")
    print(sep)
    print(f"Repository Name:         {analysis['repository_name']}")
    if output_path:
        print(f"Output File:             {output_path}")
    print(f"Schema Version:          {analysis['schema_version']}")
    print("-" * 60)
    print("Files Processed:")
    print(f"  Discovered (JS):       {summary['javascript_files_discovered']}")
    print(f"  Parsed Successfully:   {summary['javascript_files_parsed']}")
    print(f"  Discovered (TS):       {summary['typescript_files_discovered']}")
    print(f"  Parsed Successfully:   {summary['typescript_files_parsed']}")
    print(f"  Failed with Errors:    {summary['files_with_errors']}")
    print("-" * 60)
    print("Extractions:")
    print(f"  Symbols Extracted:     {summary['symbols_found']}")
    print(f"  Imports Extracted:     {summary['imports_found']}")
    print(f"  Exports Extracted:     {summary['exports_found']}")
    print(f"  Calls Extracted:       {summary['calls_found']}")
    print(f"  Parse Errors:          {len(errors)}")

    if errors:
        print("-" * 60)
        print("Encountered Errors (First 5):")
        for err in errors[:5]:
            loc = f":{err['lineno']}" if err.get("lineno") else ""
            print(f"  {err['file_path']}{loc} - {err['error_message']}")

    print(sep)
    print("JS/TS AST analysis completed successfully.")


def main(argv: Optional[list[str]] = None) -> int:
    """CLI execution entrypoint."""
    args = parse_args(argv)

    try:
        repo_root = Path(args.root).resolve()
        output_path = Path(args.output).resolve() if args.output else None

        if args.inventory:
            inv_path = Path(args.inventory).resolve()
            analysis = parse_js_repository_inventory(
                inventory_path=inv_path,
                repo_root=repo_root,
                output_path=output_path,
            )
        else:
            default_inv = Path("output/repository_inventory.json").resolve()
            if default_inv.exists():
                analysis = parse_js_repository_inventory(
                    inventory_path=default_inv,
                    repo_root=repo_root,
                    output_path=output_path,
                )
            else:
                analysis = parse_js_repository(
                    repo_root=repo_root,
                    output_path=output_path,
                )

        print_cli_summary(analysis, output_path)
        return 0

    except (FileNotFoundError, NotADirectoryError, ValueError) as err:
        print(f"Error: {err}", file=sys.stderr)
        return 1
    except PermissionError as err:
        print(f"Filesystem permission error: {err}", file=sys.stderr)
        return 1
    except Exception as err:
        print(f"Unexpected error during JS/TS analysis: {err}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
