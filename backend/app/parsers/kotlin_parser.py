"""Kotlin adapter (tree-sitter-kotlin, tree-sitter-grammars).

Kotlin specifics kept separate from Java: top-level functions are never given a class owner,
extension functions record their receiver type, ``object``/``companion object`` are classes
with a decorator, and supertypes written as ``Base()`` (constructor invocation) are treated as
``extends`` while bare supertypes are reported as ``implements`` and reclassified by the
resolver once the target kind is known.

Known grammar limitation: members written on the same line as the class's opening brace
(``class A { fun f() {} }``) make tree-sitter-kotlin 1.1.0 report a syntax error. Normal
multi-line code parses cleanly. Such files are reported as having syntax errors.
"""

from __future__ import annotations

from typing import Optional

import tree_sitter as ts
import tree_sitter_kotlin as tsk

from app.parsers.common import AdapterSpec, TreeCursorHelper, collect_syntax_errors, run_adapter, symbol_id, unique
from app.parsers.models import Call, FileParseResult, Import, Relation, Symbol

LANGUAGE = ts.Language(tsk.language())
_PARSER = ts.Parser(LANGUAGE)

CLASS_MODS = {"data", "sealed", "open", "abstract", "inner", "annotation", "value", "enum"}


class _Scope:
    __slots__ = ("qname", "symbol", "kind", "fields", "locals")

    def __init__(self, qname: str, symbol: Optional[Symbol], kind: str) -> None:
        self.qname, self.symbol, self.kind = qname, symbol, kind  # kind: "type" | "func" | "file"
        self.fields: dict[str, str] = {}
        self.locals: dict[str, str] = {}


class KotlinVisitor:
    def __init__(self, file_path: str, source: bytes) -> None:
        self.file_path = file_path
        self.h = TreeCursorHelper(source)
        self.package: Optional[str] = None
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.calls: list[Call] = []
        self.relations: list[Relation] = []
        self.scopes: list[_Scope] = [_Scope("", None, "file")]

    # -------------------------------------------------------------- helpers
    def ktype(self, node: Optional[ts.Node]) -> str:
        if node is None:
            return ""
        if node.type == "user_type":
            return ".".join(self.h.text(c) for c in node.children if c.type == "identifier")
        if node.type in ("nullable_type", "parenthesized_type"):
            inner = next((c for c in node.children if c.is_named), None)
            return self.ktype(inner)
        return ""

    def _owner(self) -> Optional[_Scope]:
        return next((s for s in reversed(self.scopes) if s.kind == "type"), None)

    def _caller(self) -> Optional[Symbol]:
        return next((s.symbol for s in reversed(self.scopes) if s.kind == "func" and s.symbol), None)

    def _lookup(self, name: str) -> Optional[str]:
        for s in reversed(self.scopes):
            if name in s.locals:
                return s.locals[name]
            if s.kind in ("type", "file") and name in s.fields:
                return s.fields[name]
        return None

    def _mods(self, node: ts.Node) -> list[str]:
        m = next((c for c in node.children if c.type == "modifiers"), None)
        out: list[str] = []
        if m:
            for c in m.children:
                for leaf in ([c] if not c.children else c.children):
                    if not leaf.children:
                        out.append(self.h.text(leaf))
        return out

    def _sym(self, node: ts.Node, name: str, qname: str, kind: str, parent: Optional[str], params: list[str],
             sig: str, mods: list[str], bases: Optional[list[str]] = None, deco: Optional[list[str]] = None,
             receiver: Optional[str] = None, is_async: bool = False) -> Symbol:
        sym = Symbol(
            id=symbol_id(self.file_path, qname, kind, self.h.line(node)), name=name, qualified_name=qname,
            kind=kind, file_path=self.file_path, lineno=self.h.line(node), end_lineno=self.h.end_line(node),
            col_offset=self.h.col(node), end_col_offset=self.h.end_col(node), parent_scope=parent, parameters=params,
            signature=sig, decorators=deco or [], bases=bases, is_async=is_async, language="kotlin",
            is_exported="private" not in mods and "internal" not in mods, namespace=self.package, receiver_type=receiver,
        )
        self.symbols.append(sym)
        return sym

    # -------------------------------------------------------------- top level
    def visit(self, root: ts.Node) -> None:
        for c in root.children:
            if c.type == "package_header":
                self.package = ".".join(self.h.text(i) for i in c.children if i.type == "identifier") or None
                q = next((i for i in c.children if i.type == "qualified_identifier"), None)
                self.package = ".".join(self.h.text(i) for i in q.children if i.type == "identifier") if q else self.package
            elif c.type == "import":
                self._import(c)
            else:
                self._decl(c)

    def _import(self, node: ts.Node) -> None:
        q = next((c for c in node.children if c.type == "qualified_identifier"), None)
        parts = [self.h.text(i) for i in q.children if i.type == "identifier"] if q else []
        wildcard = any(c.type == "*" for c in node.children)
        alias = None
        for i, c in enumerate(node.children):
            if c.type == "as" and i + 1 < len(node.children):
                alias = self.h.text(node.children[i + 1])
        if not parts:
            return
        if wildcard:
            module, name, form = ".".join(parts), "*", "namespace"
        else:
            module, name, form = ".".join(parts[:-1]), parts[-1], "named"
        self.imports.append(Import(module=module or None, name=name, alias=alias, file_path=self.file_path,
                                   lineno=self.h.line(node), col_offset=self.h.col(node), level=0,
                                   import_form=form, language="kotlin"))

    def _decl(self, node: ts.Node) -> None:
        t = node.type
        if t == "class_declaration":
            self._class(node)
        elif t == "object_declaration":
            self._class(node, as_object=True)
        elif t == "companion_object":
            self._class(node, companion=True)
        elif t == "function_declaration":
            self._function(node)
        elif t == "secondary_constructor":
            self._secondary_ctor(node)
        elif t == "property_declaration":
            self._property(node)
        elif t == "type_alias":
            name = self.h.text(node.child_by_field_name("type"))
            owner = self._owner()
            qname = f"{owner.qname}.{name}" if owner else name
            self._sym(node, name, qname, "type_alias", owner.qname if owner else None, [], f"typealias {name}", self._mods(node))
        elif t in ("anonymous_initializer", "enum_entry"):
            self._walk(node)

    # -------------------------------------------------------------- classes
    def _class(self, node: ts.Node, as_object: bool = False, companion: bool = False) -> None:
        mods = self._mods(node)
        name_node = node.child_by_field_name("name") or next((c for c in node.children if c.type == "identifier"), None)
        name = self.h.text(name_node) if name_node else ("Companion" if companion else "<anonymous>")
        is_interface = any(c.type == "interface" for c in node.children)
        kind = "interface" if is_interface else ("enum" if "enum" in mods else "class")
        deco = [m for m in mods if m in CLASS_MODS]
        if as_object:
            deco.append("object")
        if companion:
            deco.append("companion")
        owner = self._owner()
        qname = f"{owner.qname}.{name}" if owner else name
        rels: list[tuple[str, str, ts.Node]] = []
        for ds in node.children:
            if ds.type != "delegation_specifiers":
                continue
            for spec in ds.children:
                if spec.type != "delegation_specifier":
                    continue
                ctor = next((c for c in spec.children if c.type == "constructor_invocation"), None)
                ut = next((c for c in (ctor.children if ctor else spec.children) if c.type in ("user_type", "nullable_type")), None)
                if ut is None:
                    continue
                if ctor is not None:
                    rels.append(("extends", self.ktype(ut), ut))
                else:
                    rels.append(("extends" if is_interface else "implements", self.ktype(ut), ut))
        kw = "interface" if is_interface else ("object" if as_object or companion else "class")
        sym = self._sym(node, name, qname, kind, owner.qname if owner else None, [], f"{' '.join(deco + [kw])} {name}".strip(),
                        mods, unique(r[1] for r in rels) or None, deco)
        for k, target, tn in rels:
            self.relations.append(Relation(k, target, self.file_path, self.h.line(tn), self.h.col(tn), sym.id, "kotlin"))
        scope = _Scope(qname, sym, "type")
        self.scopes.append(scope)
        pc = next((c for c in node.children if c.type == "primary_constructor"), None)
        if pc is not None:
            ptypes: list[str] = []
            pnames: list[str] = []
            for cp in (pc.children[0].children if pc.children and pc.children[0].type == "class_parameters" else []):
                if cp.type == "class_parameter":
                    idn = next((c for c in cp.children if c.type == "identifier"), None)
                    ty = self.ktype(next((c for c in cp.children if c.type in ("user_type", "nullable_type")), None))
                    ptypes.append(ty or "?")
                    pnames.append(self.h.text(idn))
                    if any(c.type in ("val", "var") for c in cp.children):
                        scope.fields[self.h.text(idn)] = ty
            ctor_q = f"{qname}.<init>({','.join(ptypes)})"
            cs = self._sym(pc, name, ctor_q, "method", qname, pnames,
                           f"{name}({', '.join(f'{n}: {t}' for n, t in zip(pnames, ptypes))})", [], deco=["constructor"])
            ctor_scope = _Scope(ctor_q, cs, "func")
            ctor_scope.locals.update({n: t for n, t in zip(pnames, ptypes) if t})
            # no body to walk for primary constructors
        for c in node.children:
            if c.type in ("class_body", "enum_class_body"):
                for member in c.children:
                    self._decl(member)
        self.scopes.pop()

    # -------------------------------------------------------------- functions & properties
    def _params(self, fvp: Optional[ts.Node]) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        if fvp is None:
            return out
        for p in fvp.children:
            if p.type == "parameter":
                idn = next((c for c in p.children if c.type == "identifier"), None)
                ty = self.ktype(next((c for c in p.children if c.type in ("user_type", "nullable_type")), None))
                out.append((self.h.text(idn), ty))
        return out

    def _function(self, node: ts.Node) -> None:
        mods = self._mods(node)
        name_node = node.child_by_field_name("name")
        name = self.h.text(name_node)
        # Extension receiver: the type written before the function name.
        receiver = None
        for c in node.children:
            if c is name_node or (name_node is not None and c.start_byte >= name_node.start_byte):
                break
            if c.type in ("user_type", "nullable_type"):
                receiver = self.ktype(c)
        owner = self._owner()
        params = self._params(next((c for c in node.children if c.type == "function_value_parameters"), None))
        types = [t or "?" for _, t in params]
        prefix = f"{owner.qname}." if owner else ""
        qname = f"{prefix}{(receiver + '.') if receiver else ''}{name}({','.join(types)})"
        is_suspend = "suspend" in mods
        kind = "method" if owner else ("async_function" if is_suspend else "function")
        deco = (["extension"] if receiver else []) + (["suspend"] if is_suspend else [])
        ret = self.ktype(next((c for c in node.children if c.type in ("user_type", "nullable_type") and name_node is not None
                               and c.start_byte > name_node.start_byte), None))
        sig = f"{'suspend ' if is_suspend else ''}fun {(receiver + '.') if receiver else ''}{name}({', '.join(f'{n}: {t}' for n, t in params)})" + (f": {ret}" if ret else "")
        sym = self._sym(node, name, qname, kind, owner.qname if owner else None, [n for n, _ in params], sig, mods,
                        deco=deco, receiver=receiver, is_async=is_suspend)
        scope = _Scope(qname, sym, "func")
        scope.locals.update({n: t for n, t in params if t})
        if receiver:
            scope.locals["this"] = receiver
        self.scopes.append(scope)
        for c in node.children:
            if c.type == "function_body":
                self._walk(c)
        self.scopes.pop()

    def _secondary_ctor(self, node: ts.Node) -> None:
        owner = self._owner()
        if owner is None:
            return
        params = self._params(next((c for c in node.children if c.type == "function_value_parameters"), None))
        qname = f"{owner.qname}.<init>({','.join(t or '?' for _, t in params)})"
        name = owner.qname.rsplit(".", 1)[-1]
        sym = self._sym(node, name, qname, "method", owner.qname, [n for n, _ in params],
                        f"constructor({', '.join(f'{n}: {t}' for n, t in params)})", [], deco=["constructor"])
        scope = _Scope(qname, sym, "func")
        scope.locals.update({n: t for n, t in params if t})
        self.scopes.append(scope)
        self._walk(node)
        self.scopes.pop()

    def _property(self, node: ts.Node) -> None:
        vd = next((c for c in node.children if c.type == "variable_declaration"), None)
        if vd is None:
            for c in node.children:
                self._walk(c)
            return
        name = self.h.text(next((c for c in vd.children if c.type == "identifier"), None))
        ty = self.ktype(next((c for c in vd.children if c.type in ("user_type", "nullable_type")), None))
        if not ty:
            ty = self._infer(next((c for c in node.children if c.type not in ("variable_declaration", "modifiers", "val", "var", "=") and c.is_named), None))
        target = self.scopes[-1]
        if ty:
            (target.locals if target.kind == "func" else target.fields)[name] = ty
        for c in node.children:  # initializer expressions may contain calls
            self._walk(c)

    def _infer(self, expr: Optional[ts.Node]) -> str:
        """Type of a constructor-looking call such as ``Foo()``; empty when unknown."""
        if expr is not None and expr.type == "call_expression":
            callee = next((c for c in expr.children if c.is_named), None)
            if callee is not None and callee.type == "identifier":
                n = self.h.text(callee)
                if n[:1].isupper():
                    return n
        return ""

    # -------------------------------------------------------------- bodies
    def _walk(self, node: ts.Node) -> None:
        t = node.type
        if t == "property_declaration":
            self._property(node)
            return
        if t == "call_expression":
            self._call(node)
        elif t in ("class_declaration", "object_declaration"):
            self._decl(node)
            return
        elif t == "function_declaration":
            self._function(node)
            return
        for c in node.children:
            self._walk(c)

    def _arg_count(self, node: ts.Node) -> int:
        n = 0
        for c in node.children:
            if c.type == "value_arguments":
                n += sum(1 for a in c.children if a.type == "value_argument")
            elif c.type in ("annotated_lambda", "lambda_literal"):
                n += 1
        return n

    def _receiver_type(self, recv: ts.Node) -> Optional[str]:
        if recv.type == "this_expression":
            return "this"
        if recv.type == "super_expression":
            return "super"
        if recv.type == "identifier":
            return self._lookup(self.h.text(recv))
        if recv.type == "call_expression":
            return self._infer(recv) or None
        return None

    def _call(self, node: ts.Node) -> None:
        callee_node = next((c for c in node.children if c.is_named and c.type not in ("type_arguments", "value_arguments", "annotated_lambda")), None)
        if callee_node is None:
            return
        caller = self._caller()
        receiver = None
        if callee_node.type == "identifier":
            callee = name = self.h.text(callee_node)
            kind = "function_call"
        elif callee_node.type == "navigation_expression":
            kids = [c for c in callee_node.children if c.is_named]
            name = self.h.text(kids[-1]) if kids else ""
            callee = self.h.text(callee_node)
            callee = callee if "\n" not in callee and len(callee) < 200 else f"<expr>.{name}"
            receiver = self._receiver_type(kids[0]) if len(kids) >= 2 else None
            kind = "method_call"
        else:
            return
        self.calls.append(Call(
            callee=callee, callee_name=name, file_path=self.file_path, lineno=self.h.line(node), col_offset=self.h.col(node),
            caller=caller.qualified_name if caller else None, caller_symbol_id=caller.id if caller else None,
            is_module_level=caller is None, call_kind=kind, language="kotlin", receiver_type=receiver,
            arg_count=self._arg_count(node),
        ))


def parse_kotlin_source(file_path: str, source: bytes) -> FileParseResult:
    root = _PARSER.parse(source).root_node
    v = KotlinVisitor(file_path, source)
    v.visit(root)
    return FileParseResult(file_path=file_path, symbols=v.symbols, imports=v.imports, calls=v.calls, relations=v.relations,
                           errors=collect_syntax_errors(root, file_path, TreeCursorHelper(source)))


KOTLIN_SPEC = AdapterSpec(key="kotlin", languages=("Kotlin",), parse_source=parse_kotlin_source)


def parse_kotlin_repository_inventory(inventory_path, repo_root, output_path=None):
    return run_adapter(KOTLIN_SPEC, inventory_path, repo_root, output_path)
