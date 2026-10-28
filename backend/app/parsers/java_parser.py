"""Java adapter (tree-sitter-java).

Produces the shared Symbol/Import/Call/Relation records. Qualified names are relative to
the package (``Outer.Inner.method(int,String)``); the package itself is stored in
``Symbol.namespace`` so resolution can build fully-qualified names. Overloads keep distinct
qualified names because the erased parameter types are part of a method's qualified name.
Resolution is syntactic: receiver types come only from declared field/parameter/local types.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import tree_sitter as ts
import tree_sitter_java as tsj

from app.parsers.common import (
    AdapterSpec,
    TreeCursorHelper,
    collect_syntax_errors,
    run_adapter,
    symbol_id,
    unique,
)
from app.parsers.models import Call, FileParseResult, Import, Relation, Symbol

LANGUAGE = ts.Language(tsj.language())
_PARSER = ts.Parser(LANGUAGE)  # parsers are reusable across files within a process

TYPE_DECLS = {
    "class_declaration": "class",
    "interface_declaration": "interface",
    "enum_declaration": "enum",
    "record_declaration": "class",
    "annotation_type_declaration": "interface",
}


class _Scope:
    __slots__ = ("qname", "symbol", "fields", "locals", "kind")

    def __init__(self, qname: str, symbol: Optional[Symbol], kind: str) -> None:
        self.qname = qname
        self.symbol = symbol
        self.kind = kind  # "type" | "method"
        self.fields: dict[str, str] = {}
        self.locals: dict[str, str] = {}


class JavaVisitor:
    def __init__(self, file_path: str, source: bytes) -> None:
        self.file_path = file_path
        self.h = TreeCursorHelper(source)
        self.package: Optional[str] = None
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.relations: list[Relation] = []
        self.scopes: list[_Scope] = []

    # ------------------------------------------------------------------ helpers
    def erase(self, node: Optional[ts.Node]) -> str:
        """Erased type text: generics removed, arrays kept as ``T[]``."""
        if node is None:
            return ""
        t = node.type
        if t == "generic_type":
            first = next((c for c in node.children if c.is_named), None)
            return self.erase(first)
        if t == "array_type":
            elem = node.child_by_field_name("element")
            return self.erase(elem) + "[]"
        if t == "annotated_type":
            named = [c for c in node.children if c.is_named and c.type not in ("annotation", "marker_annotation")]
            return self.erase(named[-1]) if named else ""
        if t == "scoped_type_identifier":
            return "".join(self.h.text(c) for c in node.children if c.type != "type_arguments").replace(" ", "")
        return self.h.text(node)

    def _type_scope(self) -> Optional[_Scope]:
        return next((s for s in reversed(self.scopes) if s.kind == "type"), None)

    def _enclosing_symbol(self) -> Optional[Symbol]:
        for s in reversed(self.scopes):
            if s.symbol is not None and s.kind == "method":
                return s.symbol
        return None

    def _lookup_var_type(self, name: str) -> Optional[str]:
        for s in reversed(self.scopes):
            if name in s.locals:
                return s.locals[name]
            if s.kind == "type" and name in s.fields:
                return s.fields[name]
        return None

    def _qualify(self, name: str) -> str:
        parent = self._type_scope()
        return f"{parent.qname}.{name}" if parent else name

    def _mk_symbol(self, node: ts.Node, name: str, qname: str, kind: str, parent: Optional[str],
                   params: list[str], sig: str, mods: str, bases: Optional[list[str]] = None,
                   decorators: Optional[list[str]] = None) -> Symbol:
        sym = Symbol(
            id=symbol_id(self.file_path, qname, kind, self.h.line(node)),
            name=name, qualified_name=qname, kind=kind, file_path=self.file_path,
            lineno=self.h.line(node), end_lineno=self.h.end_line(node), col_offset=self.h.col(node),
            end_col_offset=self.h.end_col(node), parent_scope=parent, parameters=params,
            signature=sig, decorators=decorators or [], bases=bases, language="java",
            is_exported="public" in mods.split(), namespace=self.package,
        )
        self.symbols.append(sym)
        return sym

    def _mods(self, node: ts.Node) -> str:
        m = next((c for c in node.children if c.type == "modifiers"), None)
        return " ".join(self.h.text(c) for c in m.children if c.type not in ("annotation", "marker_annotation")) if m else ""

    # ------------------------------------------------------------------ top level
    def visit_program(self, root: ts.Node) -> None:
        for child in root.children:
            if child.type == "package_declaration":
                ident = next((c for c in child.children if c.type in ("scoped_identifier", "identifier")), None)
                self.package = self.h.text(ident)
            elif child.type == "import_declaration":
                self._import(child)
            elif child.type in TYPE_DECLS:
                self._type(child)

    def _import(self, node: ts.Node) -> None:
        is_static = any(c.type == "static" for c in node.children)
        ident = next((c for c in node.children if c.type in ("scoped_identifier", "identifier")), None)
        wildcard = any(c.type == "asterisk" for c in node.children)
        path = self.h.text(ident)
        if wildcard:
            module, name, form = path, "*", ("static_wildcard" if is_static else "namespace")
        else:
            module, _, name = path.rpartition(".")
            form = "static" if is_static else "named"
        self.imports.append(Import(module=module or None, name=name, alias=None, file_path=self.file_path,
                                   lineno=self.h.line(node), col_offset=self.h.col(node), level=0,
                                   import_form=form, language="java"))

    # ------------------------------------------------------------------ types
    def _type(self, node: ts.Node) -> None:
        kind = TYPE_DECLS[node.type]
        name = self.h.text(node.child_by_field_name("name"))
        qname = self._qualify(name)
        parent = self._type_scope()
        mods = self._mods(node)
        bases: list[str] = []
        rels: list[tuple[str, str, ts.Node]] = []
        for c in node.children:
            if c.type == "superclass":
                for t in c.children:
                    if t.is_named:
                        rels.append(("extends", self.erase(t), t))
            elif c.type == "extends_interfaces":
                for lst in c.children:
                    if lst.type == "type_list":
                        rels.extend(("extends", self.erase(t), t) for t in lst.children if t.is_named)
            elif c.type == "super_interfaces":
                for lst in c.children:
                    if lst.type == "type_list":
                        rels.extend(("implements", self.erase(t), t) for t in lst.children if t.is_named)
        bases = unique(r[1] for r in rels)
        decorators = ["record"] if node.type == "record_declaration" else []
        sym = self._mk_symbol(node, name, qname, kind, parent.qname if parent else None, [],
                              f"{kind if node.type != 'record_declaration' else 'record'} {name}", mods, bases or None, decorators)
        for rel_kind, target, tnode in rels:
            self.relations.append(Relation(rel_kind, target, self.file_path, self.h.line(tnode), self.h.col(tnode), sym.id, "java"))
        scope = _Scope(qname, sym, "type")
        self.scopes.append(scope)
        if node.type == "record_declaration":
            for p in self._params(node.child_by_field_name("parameters"))[1]:
                scope.fields[p[1]] = p[0]
        body = node.child_by_field_name("body")
        if body is not None:
            for member in body.children:
                self._member(member)
        self.scopes.pop()

    def _member(self, node: ts.Node) -> None:
        t = node.type
        if t in TYPE_DECLS:
            self._type(node)
        elif t == "enum_body_declarations":
            for m in node.children:
                self._member(m)
        elif t in ("method_declaration", "constructor_declaration", "compact_constructor_declaration"):
            self._method(node)
        elif t == "field_declaration":
            ftype = self.erase(node.child_by_field_name("type"))
            for d in node.children:
                if d.type == "variable_declarator":
                    self._type_scope().fields[self.h.text(d.child_by_field_name("name"))] = ftype
                    value = d.child_by_field_name("value")
                    if value is not None:
                        self._walk(value)
        elif t in ("static_initializer", "block", "constructor_body"):
            self._walk(node)
        elif t == "enum_constant":
            self._walk(node)

    def _params(self, params: Optional[ts.Node]) -> tuple[list[str], list[tuple[str, str]]]:
        """Returns (erased types, [(type, name)])."""
        pairs: list[tuple[str, str]] = []
        if params is None:
            return [], pairs
        for p in params.children:
            if p.type in ("formal_parameter", "spread_parameter"):
                tnode = p.child_by_field_name("type") or next((c for c in p.children if c.is_named and c.type not in ("modifiers", "variable_declarator")), None)
                nnode = p.child_by_field_name("name") or next((c.child_by_field_name("name") for c in p.children if c.type == "variable_declarator"), None)
                ty = self.erase(tnode) + ("..." if p.type == "spread_parameter" else "")
                pairs.append((ty, self.h.text(nnode)))
        return [t for t, _ in pairs], pairs

    def _method(self, node: ts.Node) -> None:
        owner = self._type_scope()
        is_ctor = node.type != "method_declaration"
        name = self.h.text(node.child_by_field_name("name"))
        params_node = node.child_by_field_name("parameters")
        types, pairs = self._params(params_node)
        if node.type == "compact_constructor_declaration" and owner:
            pairs = [(t, n) for n, t in owner.fields.items()]
            types = [t for t, _ in pairs]
        qname = f"{owner.qname}.{name}({','.join(types)})"
        mods = self._mods(node)
        ret = "" if is_ctor else self.erase(node.child_by_field_name("type"))
        sig = f"{(ret + ' ') if ret else ''}{name}({', '.join(f'{t} {n}' for t, n in pairs)})"
        sym = self._mk_symbol(node, name, qname, "method", owner.qname if owner else None,
                              [n for _, n in pairs], sig, mods, decorators=["constructor"] if is_ctor else (["static"] if "static" in mods.split() else []))
        scope = _Scope(qname, sym, "method")
        for ty, n in pairs:
            scope.locals[n] = ty
        self.scopes.append(scope)
        body = node.child_by_field_name("body")
        if body is not None:
            self._walk(body)
        self.scopes.pop()

    # ------------------------------------------------------------------ bodies
    def _walk(self, node: ts.Node) -> None:
        t = node.type
        if t == "local_variable_declaration":
            ty = self.erase(node.child_by_field_name("type"))
            for d in node.children:
                if d.type == "variable_declarator":
                    n = self.h.text(d.child_by_field_name("name"))
                    if ty and ty != "var" and self.scopes:
                        self.scopes[-1].locals[n] = ty
        elif t == "enhanced_for_statement":
            ty = self.erase(node.child_by_field_name("type"))
            n = self.h.text(node.child_by_field_name("name"))
            if ty and ty != "var" and n and self.scopes:
                self.scopes[-1].locals[n] = ty
        elif t == "method_invocation":
            self._invocation(node)
        elif t == "object_creation_expression":
            self._creation(node)
        elif t in TYPE_DECLS:
            self._type(node)
            return
        for c in node.children:
            self._walk(c)

    def _receiver_type(self, obj: Optional[ts.Node]) -> Optional[str]:
        if obj is None:
            return None
        if obj.type == "this":
            return "this"
        if obj.type == "super":
            return "super"
        if obj.type == "identifier":
            return self._lookup_var_type(self.h.text(obj))
        if obj.type == "object_creation_expression":  # new Foo().bar()
            return self.erase(obj.child_by_field_name("type")) or None
        if obj.type == "field_access":
            o, f = obj.child_by_field_name("object"), obj.child_by_field_name("field")
            if o is not None and o.type == "this":
                return self._lookup_var_type(self.h.text(f))
        return None

    def _arg_count(self, args: Optional[ts.Node]) -> int:
        return sum(1 for c in args.children if c.is_named and c.type not in ("line_comment", "block_comment")) if args else 0

    def _invocation(self, node: ts.Node) -> None:
        obj = node.child_by_field_name("object")
        name = self.h.text(node.child_by_field_name("name"))
        callee = f"{self.h.text(obj)}.{name}" if obj is not None else name
        caller = self._enclosing_symbol()
        self.calls.append(Call(
            callee=callee, callee_name=name, file_path=self.file_path, lineno=self.h.line(node),
            col_offset=self.h.col(node), caller=caller.qualified_name if caller else None,
            caller_symbol_id=caller.id if caller else None, is_module_level=caller is None,
            call_kind="method_call" if obj is not None else "function_call", language="java",
            receiver_type=self._receiver_type(obj), arg_count=self._arg_count(node.child_by_field_name("arguments")),
        ))

    def _creation(self, node: ts.Node) -> None:
        ty = self.erase(node.child_by_field_name("type"))
        caller = self._enclosing_symbol()
        self.calls.append(Call(
            callee=f"new {ty}", callee_name=ty.rsplit(".", 1)[-1], file_path=self.file_path,
            lineno=self.h.line(node), col_offset=self.h.col(node), caller=caller.qualified_name if caller else None,
            caller_symbol_id=caller.id if caller else None, is_module_level=caller is None,
            call_kind="constructor_call", language="java", receiver_type=ty,
            arg_count=self._arg_count(node.child_by_field_name("arguments")),
        ))


def parse_java_source(file_path: str, source: bytes) -> FileParseResult:
    root = _PARSER.parse(source).root_node
    helper = TreeCursorHelper(source)
    visitor = JavaVisitor(file_path, source)
    visitor.visit_program(root)
    return FileParseResult(file_path=file_path, symbols=visitor.symbols, imports=visitor.imports,
                           calls=visitor.calls, relations=visitor.relations,
                           errors=collect_syntax_errors(root, file_path, helper))


JAVA_SPEC = AdapterSpec(key="java", languages=("Java",), parse_source=parse_java_source)


def parse_java_repository_inventory(inventory_path, repo_root, output_path=None):
    return run_adapter(JAVA_SPEC, inventory_path, repo_root, output_path)
