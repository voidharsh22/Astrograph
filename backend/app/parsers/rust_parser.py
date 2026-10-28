"""Rust adapter (tree-sitter-rust).

Module identity is crate-relative: ``src/a/b.rs`` is ``crate::a::b`` and the file's module
path is stored in ``Symbol.namespace``; inline ``mod x { }`` blocks prefix the symbol's
qualified name (``x::Foo``). Structs become ``class`` nodes (decorator ``struct``), traits
``interface`` nodes (decorator ``trait``), and ``impl`` blocks contribute methods to the
implemented type. Methods take ``self``; associated functions do not and carry the decorator
``associated``. Macro invocations are recorded as ``macro_call`` calls and are never claimed
to be resolved (no macro expansion is performed). No Cargo build is needed.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import Optional

import tree_sitter as ts
import tree_sitter_rust as tsr

from app.parsers.common import AdapterSpec, TreeCursorHelper, collect_syntax_errors, run_adapter, symbol_id
from app.parsers.models import Call, Export, FileParseResult, Import, Relation, Symbol

LANGUAGE = ts.Language(tsr.language())
_PARSER = ts.Parser(LANGUAGE)

# Macros from the standard library: reported as external rather than unresolved.
STD_MACROS = frozenset(
    "println print eprintln eprint format vec assert assert_eq assert_ne debug_assert debug_assert_eq debug_assert_ne "
    "panic todo unimplemented unreachable write writeln matches dbg include_str env concat stringify line file "
    "column cfg thread_local".split()
)


def rust_crate_root(file_path: str) -> str:
    """Directory (posix, may be empty) containing the crate's root module for a source file."""
    parts = PurePosixPath(file_path).parts
    if "src" in parts[:-1]:
        idx = len(parts) - 2 - list(reversed(parts[:-1])).index("src")
        return "/".join(parts[: idx + 1])
    return "/".join(parts[:-1])


def rust_module_path(file_path: str) -> str:
    """``crate::a::b`` module path for a file, from its position relative to the crate root."""
    p = PurePosixPath(file_path)
    root = rust_crate_root(file_path)
    rel = p.relative_to(root) if root else p
    segs = list(rel.with_suffix("").parts)
    if segs and segs[-1] in ("lib", "main", "mod") and (len(segs) == 1 or segs[-1] == "mod"):
        segs = segs[:-1]
    elif "src" not in p.parts[:-1]:
        segs = []  # tests/, examples/, build.rs: each file is its own crate root
    return "::".join(["crate", *segs])


class _Impl:
    __slots__ = ("qname", "type_name", "trait")

    def __init__(self, qname: str, type_name: str, trait: Optional[str]) -> None:
        self.qname, self.type_name, self.trait = qname, type_name, trait


class RustVisitor:
    def __init__(self, file_path: str, source: bytes) -> None:
        self.file_path = file_path
        self.h = TreeCursorHelper(source)
        self.module = rust_module_path(file_path)
        self.symbols: list[Symbol] = []
        self.imports: list[Import] = []
        self.exports: list[Export] = []
        self.calls: list[Call] = []
        self.relations: list[Relation] = []
        self.inline: list[str] = []  # inline `mod x {}` nesting
        self.struct_fields: dict[str, dict[str, str]] = {}
        self.func_stack: list[Symbol] = []
        self.locals: list[dict[str, str]] = []
        self.impl: Optional[_Impl] = None

    # ------------------------------------------------------------------ helpers
    def rtype(self, node: Optional[ts.Node]) -> str:
        """Erased type: references/generics stripped, path kept (``a::B``)."""
        if node is None:
            return ""
        t = node.type
        if t in ("reference_type", "pointer_type"):
            return self.rtype(node.child_by_field_name("type"))
        if t == "generic_type":
            return self.rtype(node.child_by_field_name("type"))
        if t == "scoped_type_identifier":
            path = node.child_by_field_name("path")
            name = node.child_by_field_name("name")
            return f"{self.rtype(path)}::{self.h.text(name)}" if path is not None else self.h.text(name)
        if t in ("type_identifier", "identifier", "primitive_type", "crate", "super", "self", "scoped_identifier"):
            return self.h.text(node).replace(" ", "")
        return ""

    def _prefix(self, name: str) -> str:
        return "::".join([*self.inline, name]) if self.inline else name

    def _sym(self, node: ts.Node, name: str, qname: str, kind: str, parent: Optional[str], params: list[str],
             sig: str, pub: bool, deco: list[str], bases: Optional[list[str]] = None, receiver: Optional[str] = None) -> Symbol:
        sym = Symbol(
            id=symbol_id(self.file_path, qname, kind, self.h.line(node)), name=name, qualified_name=qname, kind=kind,
            file_path=self.file_path, lineno=self.h.line(node), end_lineno=self.h.end_line(node), col_offset=self.h.col(node),
            end_col_offset=self.h.end_col(node), parent_scope=parent, parameters=params, signature=sig, decorators=deco,
            bases=bases, language="rust", is_exported=pub, namespace=self.module, receiver_type=receiver,
        )
        self.symbols.append(sym)
        return sym

    @staticmethod
    def _is_pub(node: ts.Node) -> bool:
        return any(c.type == "visibility_modifier" for c in node.children)

    # ------------------------------------------------------------------ items
    def visit(self, root: ts.Node) -> None:
        self._collect_struct_fields(root)
        for c in root.children:
            self._item(c)

    def _collect_struct_fields(self, node: ts.Node) -> None:
        for c in node.children:
            if c.type == "struct_item":
                name = self.h.text(c.child_by_field_name("name"))
                body = c.child_by_field_name("body")
                fields: dict[str, str] = {}
                for f in (body.children if body is not None else []):
                    if f.type == "field_declaration":
                        fields[self.h.text(f.child_by_field_name("name"))] = self.rtype(f.child_by_field_name("type"))
                self.struct_fields[name] = fields
            elif c.type == "mod_item":
                body = c.child_by_field_name("body")
                if body is not None:
                    self._collect_struct_fields(body)

    def _item(self, node: ts.Node) -> None:
        t = node.type
        if t == "use_declaration":
            self._use(node)
        elif t == "mod_item":
            self._mod(node)
        elif t == "struct_item":
            name = self.h.text(node.child_by_field_name("name"))
            self._sym(node, name, self._prefix(name), "class", None, [], f"struct {name}", self._is_pub(node), ["struct"])
        elif t == "enum_item":
            name = self.h.text(node.child_by_field_name("name"))
            self._sym(node, name, self._prefix(name), "enum", None, [], f"enum {name}", self._is_pub(node), [])
        elif t == "type_item":
            name = self.h.text(node.child_by_field_name("name"))
            self._sym(node, name, self._prefix(name), "type_alias", None, [], f"type {name}", self._is_pub(node), [])
        elif t == "trait_item":
            self._trait(node)
        elif t == "impl_item":
            self._impl(node)
        elif t == "function_item":
            self._function(node, owner=None)

    def _mod(self, node: ts.Node) -> None:
        name = self.h.text(node.child_by_field_name("name"))
        body = node.child_by_field_name("body")
        if body is None:  # `mod foo;` declares a file module
            self.imports.append(Import(module=self.module, name=name, alias=None, file_path=self.file_path,
                                       lineno=self.h.line(node), col_offset=self.h.col(node), level=0,
                                       import_form="mod", language="rust"))
            return
        self.inline.append(name)
        for c in body.children:
            self._item(c)
        self.inline.pop()

    def _trait(self, node: ts.Node) -> None:
        name = self.h.text(node.child_by_field_name("name"))
        qname = self._prefix(name)
        bounds = node.child_by_field_name("bounds")
        supers = [self.rtype(b) for b in (bounds.children if bounds is not None else []) if b.is_named and self.rtype(b)]
        sym = self._sym(node, name, qname, "interface", None, [], f"trait {name}", self._is_pub(node), ["trait"], supers or None)
        for b in (bounds.children if bounds is not None else []):
            if b.is_named and self.rtype(b):
                self.relations.append(Relation("extends", self.rtype(b), self.file_path, self.h.line(b), self.h.col(b), sym.id, "rust"))
        prev = self.impl
        self.impl = _Impl(qname, name, None)
        body = node.child_by_field_name("body")
        for m in (body.children if body is not None else []):
            if m.type in ("function_item", "function_signature_item"):
                self._function(m, owner=self.impl, trait_method=True)
        self.impl = prev

    def _impl(self, node: ts.Node) -> None:
        ty = node.child_by_field_name("type")
        trait = node.child_by_field_name("trait")
        type_name = self.rtype(ty)
        if not type_name:
            return
        qname = self._prefix(type_name.rsplit("::", 1)[-1]) if "::" not in type_name else type_name
        trait_name = self.rtype(trait) if trait is not None else None
        if trait_name:
            self.relations.append(Relation("implements", trait_name, self.file_path, self.h.line(node), self.h.col(node),
                                           None, "rust", source_name=type_name))
        prev = self.impl
        self.impl = _Impl(qname, type_name, trait_name)
        body = node.child_by_field_name("body")
        for m in (body.children if body is not None else []):
            if m.type == "function_item":
                self._function(m, owner=self.impl)
        self.impl = prev

    def _function(self, node: ts.Node, owner: Optional[_Impl], trait_method: bool = False) -> None:
        name = self.h.text(node.child_by_field_name("name"))
        params_node = node.child_by_field_name("parameters")
        has_self = False
        names: list[str] = []
        local: dict[str, str] = {}
        for p in (params_node.children if params_node is not None else []):
            if p.type == "self_parameter":
                has_self = True
                if owner:
                    local["self"] = owner.type_name
            elif p.type == "parameter":
                pat = p.child_by_field_name("pattern")
                pn = self.h.text(pat)
                names.append(pn)
                ty = self.rtype(p.child_by_field_name("type"))
                if ty and pat is not None and pat.type == "identifier":
                    local[pn] = owner.type_name if ty == "Self" and owner else ty
        qname = f"{owner.qname}::{name}" if owner else self._prefix(name)
        kind = "method" if (owner and has_self) else "function"
        deco: list[str] = []
        if owner and not has_self:
            deco.append("associated")
        if owner and owner.trait and not trait_method:
            deco.append(f"impl:{owner.trait}")
        if trait_method:
            deco.append("trait_method")
        body = node.child_by_field_name("body")
        sig_end = body.start_byte if body is not None else node.end_byte
        sig = " ".join(self.h.source[node.start_byte:sig_end].decode("utf-8", "replace").split())[:300]
        sym = self._sym(node, name, qname, kind, owner.qname if owner else None, names, sig, self._is_pub(node) or trait_method,
                        deco, receiver=owner.type_name if owner else None)
        sym.is_async = any(c.type == "function_modifiers" and "async" in self.h.text(c) for c in node.children)
        if body is None:
            return
        self.func_stack.append(sym)
        self.locals.append(local)
        self._walk(body)
        self.locals.pop()
        self.func_stack.pop()

    # ------------------------------------------------------------------ use
    def _use(self, node: ts.Node) -> None:
        arg = node.child_by_field_name("argument")
        pub = self._is_pub(node)
        for module, name, alias in self._flatten(arg, ""):
            form = "namespace" if name == "*" else "named"
            self.imports.append(Import(module=module or None, name=name, alias=alias, file_path=self.file_path,
                                       lineno=self.h.line(node), col_offset=self.h.col(node), level=0,
                                       import_form=form, language="rust"))
            if pub and name != "*":
                self.exports.append(Export(name=alias or name, file_path=self.file_path, lineno=self.h.line(node),
                                           col_offset=self.h.col(node), alias=name if alias else None, is_reexport=True,
                                           source_module=module or None, language="rust"))

    def _flatten(self, node: Optional[ts.Node], prefix: str) -> list[tuple[str, str, Optional[str]]]:
        if node is None:
            return []
        t = node.type
        join = lambda a, b: f"{a}::{b}" if a else b  # noqa: E731
        if t in ("identifier", "self", "crate", "super"):
            text = self.h.text(node)
            if text == "self" and prefix:
                head, _, last = prefix.rpartition("::")
                return [(head, last, None)]
            return [(prefix, text, None)]
        if t == "scoped_identifier":
            full = join(prefix, self.h.text(node).replace(" ", ""))
            head, _, last = full.rpartition("::")
            return [(head, last, None)]
        if t == "use_as_clause":
            inner = node.child_by_field_name("path")
            alias = self.h.text(node.child_by_field_name("alias"))
            return [(m, n, alias) for m, n, _ in self._flatten(inner, prefix)]
        if t == "use_wildcard":
            inner = next((c for c in node.children if c.is_named), None)
            return [(join(prefix, self.h.text(inner).replace(" ", "")) if inner is not None else prefix, "*", None)]
        if t == "scoped_use_list":
            path = node.child_by_field_name("path")
            new_prefix = join(prefix, self.h.text(path).replace(" ", "")) if path is not None else prefix
            out: list[tuple[str, str, Optional[str]]] = []
            for item in (node.child_by_field_name("list").children if node.child_by_field_name("list") is not None else []):
                if item.is_named:
                    out.extend(self._flatten(item, new_prefix))
            return out
        if t == "use_list":
            out = []
            for item in node.children:
                if item.is_named:
                    out.extend(self._flatten(item, prefix))
            return out
        return []

    # ------------------------------------------------------------------ bodies
    def _lookup(self, name: str) -> Optional[str]:
        for scope in reversed(self.locals):
            if name in scope:
                return scope[name]
        return None

    def _walk(self, node: ts.Node) -> None:
        t = node.type
        if t == "let_declaration" and self.locals:
            pat = node.child_by_field_name("pattern")
            ty = self.rtype(node.child_by_field_name("type"))
            if not ty:
                ty = self._infer(node.child_by_field_name("value"))
            if pat is not None and pat.type == "identifier" and ty:
                self.locals[-1][self.h.text(pat)] = self.impl.type_name if ty == "Self" and self.impl else ty
        elif t == "call_expression":
            self._call(node)
        elif t == "macro_invocation":
            self._macro(node)
        elif t == "function_item":
            self._function(node, owner=None)
            return
        for c in node.children:
            self._walk(c)

    def _infer(self, value: Optional[ts.Node]) -> str:
        """``Foo::new()`` / ``Foo::default()`` -> ``Foo``; struct literals -> their name."""
        if value is None:
            return ""
        if value.type == "struct_expression":
            return self.rtype(value.child_by_field_name("name"))
        if value.type == "call_expression":
            fn = value.child_by_field_name("function")
            if fn is not None and fn.type == "scoped_identifier":
                path = fn.child_by_field_name("path")
                head = self.h.text(path).replace(" ", "") if path is not None else ""
                last = head.rsplit("::", 1)[-1]
                if last[:1].isupper():
                    return head
        return ""

    def _recv_type(self, value: Optional[ts.Node]) -> Optional[str]:
        if value is None:
            return None
        if value.type == "self":
            return "Self"
        if value.type == "identifier":
            return self._lookup(self.h.text(value))
        if value.type == "field_expression":
            base = value.child_by_field_name("value")
            field = self.h.text(value.child_by_field_name("field"))
            if base is not None and base.type == "self" and self.impl:
                return self.struct_fields.get(self.impl.type_name.rsplit("::", 1)[-1], {}).get(field) or None
        return None

    def _call(self, node: ts.Node) -> None:
        fn = node.child_by_field_name("function")
        if fn is not None and fn.type == "generic_function":
            fn = fn.child_by_field_name("function")
        if fn is None:
            return
        args = node.child_by_field_name("arguments")
        argc = sum(1 for a in (args.children if args else []) if a.is_named and a.type not in ("line_comment", "block_comment"))
        caller = self.func_stack[-1] if self.func_stack else None
        receiver: Optional[str] = None
        if fn.type == "identifier":
            callee, name, kind = self.h.text(fn), self.h.text(fn), "function_call"
        elif fn.type == "scoped_identifier":
            callee = self.h.text(fn).replace(" ", "")
            name = callee.rsplit("::", 1)[-1]
            kind = "function_call"
        elif fn.type == "field_expression":
            value = fn.child_by_field_name("value")
            name = self.h.text(fn.child_by_field_name("field"))
            simple = value is not None and value.type in ("self", "identifier", "field_expression")
            callee = f"{self.h.text(value)}.{name}" if simple else f"<expr>.{name}"
            receiver = self._recv_type(value)
            kind = "method_call"
        else:
            return
        self.calls.append(Call(callee=callee, callee_name=name, file_path=self.file_path, lineno=self.h.line(node),
                               col_offset=self.h.col(node), caller=caller.qualified_name if caller else None,
                               caller_symbol_id=caller.id if caller else None, is_module_level=caller is None,
                               call_kind=kind, language="rust", receiver_type=receiver, arg_count=argc))

    def _macro(self, node: ts.Node) -> None:
        macro = node.child_by_field_name("macro")
        name = self.h.text(macro).replace(" ", "")
        caller = self.func_stack[-1] if self.func_stack else None
        self.calls.append(Call(callee=f"{name}!", callee_name=name.rsplit("::", 1)[-1], file_path=self.file_path,
                               lineno=self.h.line(node), col_offset=self.h.col(node),
                               caller=caller.qualified_name if caller else None,
                               caller_symbol_id=caller.id if caller else None, is_module_level=caller is None,
                               call_kind="macro_call", language="rust"))


def parse_rust_source(file_path: str, source: bytes) -> FileParseResult:
    root = _PARSER.parse(source).root_node
    v = RustVisitor(file_path, source)
    v.visit(root)
    return FileParseResult(file_path=file_path, symbols=v.symbols, imports=v.imports, calls=v.calls, exports=v.exports,
                           relations=v.relations, errors=collect_syntax_errors(root, file_path, TreeCursorHelper(source)))


RUST_SPEC = AdapterSpec(key="rust", languages=("Rust",), parse_source=parse_rust_source)


def parse_rust_repository_inventory(inventory_path, repo_root, output_path=None):
    return run_adapter(RUST_SPEC, inventory_path, repo_root, output_path)
