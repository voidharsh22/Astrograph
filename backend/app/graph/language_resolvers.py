"""Language-specific resolution for Java, Kotlin and Rust.

``SymbolResolver`` delegates to these classes by file extension, so the graph builder stays
language-neutral. Everything is conservative and syntax-based: receiver types come only from
declared types the parser recorded, overloads are separated by argument count (more than one
candidate is reported as *ambiguous*, never guessed), and anything involving reflection,
macros, generated code or dependencies outside the repository stays unresolved or external.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath
import re
from typing import TYPE_CHECKING, Any, Optional

from app.graph.models import STATUS_AMBIGUOUS, STATUS_EXTERNAL, STATUS_UNRESOLVED, UnresolvedReference
from app.parsers.rust_parser import STD_MACROS, rust_crate_root, rust_module_path

if TYPE_CHECKING:  # pragma: no cover
    from app.graph.symbol_resolver import SymbolResolver

Resolved = tuple[Optional[str], Optional[UnresolvedReference], Optional[str]]
TYPE_KINDS = ("class", "interface", "enum", "type_alias")
CALLABLE_KINDS = ("method", "function", "async_function")

JAVA_LANG = frozenset(
    "String Object Integer Long Double Float Boolean Character Byte Short Math System Thread Runnable Exception "
    "RuntimeException Error Throwable Iterable Comparable Class Enum Record Override Deprecated StringBuilder "
    "Number Void List Map Set Optional".split()
)
KOTLIN_STD = frozenset(
    "String Int Long Double Float Boolean Char Byte Short Any Unit Nothing Array List Map Set MutableList MutableMap "
    "MutableSet Pair Triple Sequence Iterable Collection Exception RuntimeException Throwable Result Comparable "
    "Number StringBuilder".split()
)
KOTLIN_STD_FUNCS = frozenset(
    "println print listOf mutableListOf mapOf mutableMapOf setOf mutableSetOf arrayOf emptyList emptyMap emptySet "
    "require check error lazy run let apply also with repeat to maxOf minOf TODO assert".split()
)


def _unres(kind: str, item: dict[str, Any], status: str, reason: str, candidates: Optional[list[str]] = None) -> UnresolvedReference:
    if kind == "call":
        return UnresolvedReference(
            kind="call", source_file=Path(item["file_path"]).as_posix(), caller_id=item.get("caller_symbol_id"),
            expression=item.get("callee", ""), target_name=item.get("callee_name"), lineno=item.get("lineno"),
            col_offset=item.get("col_offset"), status=status, reason=reason, candidates=candidates or [],
        )
    return UnresolvedReference(
        kind=kind, source_file=Path(item["file_path"]).as_posix(), caller_id=item.get("source_symbol_id"),
        expression=f"{item.get('kind', '')} {item.get('target', '')}".strip(), target_name=item.get("target"),
        lineno=item.get("lineno"), col_offset=item.get("col_offset"), status=status, reason=reason,
    )


class LanguageResolver:
    """Interface the SymbolResolver delegates to."""

    languages: tuple[str, ...] = ()

    def __init__(self, base: "SymbolResolver") -> None:
        self.base = base
        self.prepared = False

    def prepare(self, imports: list[dict[str, Any]]) -> None:  # pragma: no cover - interface
        raise NotImplementedError

    def resolve_import(self, imp: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference]]:  # pragma: no cover
        raise NotImplementedError

    def resolve_call(self, call: dict[str, Any]) -> Resolved:  # pragma: no cover
        raise NotImplementedError

    def resolve_relation(self, rel: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference], str]:  # pragma: no cover
        raise NotImplementedError


# ============================================================================== JVM (Java + Kotlin)
class JvmResolver(LanguageResolver):
    """Shared package/type machinery for Java and Kotlin."""

    lang = ""
    builtin_types: frozenset[str] = frozenset()

    def prepare(self, imports: list[dict[str, Any]]) -> None:
        b = self.base
        self.types_by_fqn: dict[str, dict[str, Any]] = {}
        self.members: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        self.top_funcs: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
        self.extensions: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.ns_files: dict[str, set[str]] = defaultdict(set)
        self.fqn_file: dict[str, str] = {}
        syms = [s for s in b.symbols_by_id.values() if s.get("language") == self.lang]
        for s in syms:
            ns = s.get("namespace") or ""
            fqn = f"{ns}.{s['qualified_name']}" if ns else s["qualified_name"]
            self.ns_files[ns].add(s["file_path"])
            if s["kind"] in TYPE_KINDS:
                self.types_by_fqn.setdefault(fqn, s)
                self.fqn_file[fqn] = s["file_path"]
        for s in syms:
            if s["kind"] in CALLABLE_KINDS:
                owner = self._owner(s)
                if owner is not None:
                    self.members[owner["id"]][s["name"]].append(s)
                else:
                    self.top_funcs[(s.get("namespace") or "", s["name"])].append(s)
                    if s.get("receiver_type"):
                        self.extensions[s["receiver_type"].rsplit(".", 1)[-1]].append(s)
        self.simple_imports: dict[str, dict[str, str]] = defaultdict(dict)
        self.wildcards: dict[str, list[str]] = defaultdict(list)
        self.static_imports: dict[str, list[tuple[str, str]]] = defaultdict(list)
        for imp in imports:
            if imp.get("language") != self.lang:
                continue
            f = Path(imp["file_path"]).as_posix()
            module, name, form = imp.get("module") or "", imp.get("name") or "", imp.get("import_form")
            if form == "namespace":
                self.wildcards[f].append(module)
            elif form in ("static", "static_wildcard"):
                self.static_imports[f].append((module, name))
            elif name:
                self.simple_imports[f][imp.get("alias") or name] = f"{module}.{name}" if module else name
        self._supers: dict[str, list[str]] = {}
        self.relations_by_source: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self.prepared = True

    def set_relations(self, relations: list[dict[str, Any]]) -> None:
        for r in relations:
            if r.get("language") == self.lang and r.get("source_symbol_id"):
                self.relations_by_source[r["source_symbol_id"]].append(r)

    def _owner(self, sym: dict[str, Any]) -> Optional[dict[str, Any]]:
        parent = sym.get("parent_scope")
        if not parent:
            return None
        owner = self.base.symbols_by_file_and_qname.get((sym["file_path"], parent))
        return owner if owner is not None and owner["kind"] in TYPE_KINDS else None

    # -------------------------------------------------------------- types
    def resolve_type(self, file_path: str, name: str, scope_qname: Optional[str]) -> tuple[Optional[dict[str, Any]], str]:
        """Return (symbol, status) with status 'resolved' | 'external' | 'unresolved'."""
        if not name:
            return None, "unresolved"
        ns = self._file_ns(file_path)
        if "." in name:
            sym = self.types_by_fqn.get(name)
            if sym:
                return sym, "resolved"
            head, _, rest = name.partition(".")
            outer, status = self.resolve_type(file_path, head, scope_qname)
            if outer is not None:
                onv = outer.get("namespace") or ""
                nested = self.types_by_fqn.get(f"{onv}.{outer['qualified_name']}.{rest}" if onv else f"{outer['qualified_name']}.{rest}")
                return (nested, "resolved") if nested else (None, "unresolved")
            return (None, "external") if status == "external" or not self._known_namespace(head) else (None, "unresolved")
        # enclosing classes, innermost first
        parts = (scope_qname or "").split(".") if scope_qname else []
        while parts:
            cand = ".".join(parts + [name])
            sym = self.types_by_fqn.get(f"{ns}.{cand}" if ns else cand)
            if sym:
                return sym, "resolved"
            parts.pop()
        sym = self.types_by_fqn.get(f"{ns}.{name}" if ns else name)
        if sym:
            return sym, "resolved"
        fqn = self.simple_imports.get(file_path, {}).get(name)
        if fqn:
            sym = self.types_by_fqn.get(fqn)
            return (sym, "resolved") if sym else (None, "external")
        for pkg in self.wildcards.get(file_path, []):
            sym = self.types_by_fqn.get(f"{pkg}.{name}")
            if sym:
                return sym, "resolved"
        if name in self.builtin_types:
            return None, "external"
        if self.wildcards.get(file_path) and not any(p in self.ns_files for p in self.wildcards[file_path]):
            return None, "external"  # wildcard of a package outside the repository
        return None, "unresolved"

    def _known_namespace(self, head: str) -> bool:
        return any(ns == head or ns.startswith(head + ".") for ns in self.ns_files)

    def _file_ns(self, file_path: str) -> str:
        for s in self.base.symbols_by_file.get(file_path, []):
            if s.get("namespace") is not None:
                return s["namespace"]
        return ""

    # -------------------------------------------------------------- imports
    def resolve_import(self, imp: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference]]:
        file_path = Path(imp["file_path"]).as_posix()
        module, name, form = imp.get("module") or "", imp.get("name") or "", imp.get("import_form")
        expr = f"import {module}.{name}" if module else f"import {name}"
        # import a.b.C / import a.b.C.member / import a.b.*
        if form in ("namespace",):
            if module in self.ns_files or self.types_by_fqn.get(module):
                return None, None  # wildcard: edges come from the references that actually use it
            return None, _unres_import(file_path, imp, expr, STATUS_EXTERNAL, f"Package '{module}' is outside the repository")
        full = f"{module}.{name}" if module else name
        candidates = [full]
        if form in ("static", "static_wildcard"):
            candidates = [module, full]
        for cand in candidates:
            sym = self.types_by_fqn.get(cand)
            if sym:
                return sym["file_path"], None
        # Kotlin: import pkg.topLevelFun / pkg.property
        funcs = self.top_funcs.get((module, name))
        if funcs:
            return funcs[0]["file_path"], None
        return None, _unres_import(file_path, imp, expr, STATUS_EXTERNAL, f"'{full}' is not defined in the repository (external dependency)")

    # -------------------------------------------------------------- inheritance
    def supertypes(self, type_sym: dict[str, Any], seen: Optional[set[str]] = None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for rel in self.relations_by_source.get(type_sym["id"], []):
            sup, _ = self.resolve_type(type_sym["file_path"], rel["target"], type_sym.get("parent_scope"))
            if sup is not None:
                out.append(sup)
        return out

    def find_methods(self, type_sym: dict[str, Any], name: str, argc: Optional[int]) -> tuple[list[dict[str, Any]], str]:
        """Search the type, its companion/nested companion, then supertypes (breadth-first, cycle-safe)."""
        queue, seen = [type_sym], set()
        while queue:
            cur = queue.pop(0)
            if cur["id"] in seen:
                continue
            seen.add(cur["id"])
            cands = list(self.members.get(cur["id"], {}).get(name, []))
            comp = self.types_by_fqn.get(f"{cur.get('namespace') or ''}.{cur['qualified_name']}.Companion".lstrip("."))
            if comp is not None:
                cands += self.members.get(comp["id"], {}).get(name, [])
            if cands:
                return self._by_arity(cands, argc)
            queue.extend(self.supertypes(cur))
        return [], "none"

    def _by_arity(self, cands: list[dict[str, Any]], argc: Optional[int]) -> tuple[list[dict[str, Any]], str]:
        if argc is None:
            return cands, "name"
        exact = [c for c in cands if self._arity_ok(c, argc)]
        if exact:
            return exact, "arity"
        return (cands, "name_only") if len(cands) == 1 else ([], "none")

    @staticmethod
    def _arity_ok(sym: dict[str, Any], argc: int) -> bool:
        params = sym.get("parameters") or []
        sig = sym.get("signature") or ""
        if "..." in sig:  # Java varargs
            return argc >= len(params) - 1
        return len(params) == argc

    def _target(self, cands: list[dict[str, Any]], call: dict[str, Any], strategy: str) -> Resolved:
        if len(cands) == 1:
            return f"symbol:{cands[0]['id']}", None, strategy
        ids = [f"symbol:{c['id']}" for c in cands]
        return None, _unres("call", call, STATUS_AMBIGUOUS, f"{len(cands)} overloads match '{call.get('callee_name')}' with {call.get('arg_count')} argument(s)", ids), None

    # -------------------------------------------------------------- calls
    def resolve_call(self, call: dict[str, Any]) -> Resolved:
        f = Path(call["file_path"]).as_posix()
        name, callee, kind = call.get("callee_name") or "", call.get("callee") or "", call.get("call_kind")
        argc = call.get("arg_count")
        caller = self.base.symbols_by_id.get(call.get("caller_symbol_id") or "")
        scope = (caller or {}).get("parent_scope") if caller else None
        if caller and caller["kind"] in TYPE_KINDS:
            scope = caller["qualified_name"]

        if kind == "constructor_call" or (self.lang == "kotlin" and kind == "function_call" and name[:1].isupper() and "." not in callee):
            tname = call.get("receiver_type") or name
            sym, status = self.resolve_type(f, tname, scope)
            if sym is not None and sym["kind"] in ("class", "enum"):
                return f"symbol:{sym['id']}", None, "constructor_call"
            if status == "external":
                return None, _unres("call", call, STATUS_EXTERNAL, f"Constructor of external type '{tname}'"), None
            if kind == "constructor_call":
                return None, _unres("call", call, STATUS_UNRESOLVED, f"Type '{tname}' not found in the repository"), None

        recv = call.get("receiver_type")
        if kind == "method_call" or "." in callee:
            qualifier = callee.rsplit(".", 1)[0] if "." in callee else ""
            type_sym: Optional[dict[str, Any]] = None
            status = "unresolved"
            if recv in ("this", "super"):
                owner = self._context_type(caller, scope, f, super_=recv == "super")
                type_sym, status = owner, "resolved" if owner else "unresolved"
                if recv == "super" and owner is not None:
                    sups = self.supertypes(owner)
                    for sup in sups:
                        cands, how = self.find_methods(sup, name, argc)
                        if cands:
                            return self._target(cands, call, "super_method")
                    return None, _unres("call", call, STATUS_UNRESOLVED, f"'{name}' not found in supertypes"), None
                if caller and caller.get("receiver_type") and recv == "this":
                    type_sym, status = self.resolve_type(f, caller["receiver_type"], scope)
            elif recv:
                type_sym, status = self.resolve_type(f, recv, scope)
            elif qualifier and re.fullmatch(r"[\w.]+", qualifier):
                type_sym, status = self.resolve_type(f, qualifier, scope)  # static / object / companion call
            if type_sym is not None:
                cands, how = self.find_methods(type_sym, name, argc)
                if cands:
                    return self._target(cands, call, "typed_receiver" if recv else "static_call")
                ext = self._extension(f, type_sym["name"], name, argc)
                if ext:
                    return self._target(ext, call, "extension_function")
                return None, _unres("call", call, STATUS_UNRESOLVED, f"No member '{name}' found on '{type_sym['qualified_name']}' or its supertypes"), None
            if status == "external" or (recv and (recv.rsplit(".", 1)[-1] in self.builtin_types)):
                ext = self._extension(f, (recv or "").rsplit(".", 1)[-1], name, argc)
                if ext:
                    return self._target(ext, call, "extension_function")
                return None, _unres("call", call, STATUS_EXTERNAL, f"Receiver type '{recv or qualifier}' is outside the repository"), None
            if recv:
                ext = self._extension(f, recv.rsplit(".", 1)[-1], name, argc)
                if ext:
                    return self._target(ext, call, "extension_function")
            return None, _unres("call", call, STATUS_UNRESOLVED, f"Receiver type of '{callee}' could not be determined statically"), None

        # unqualified call: members of the enclosing type chain, then top-level / imported functions
        ctx = self._context_type(caller, scope, f)
        while ctx is not None:
            cands, how = self.find_methods(ctx, name, argc)
            if cands:
                return self._target(cands, call, "same_class")
            parent = ctx.get("parent_scope")
            ctx = self.base.symbols_by_file_and_qname.get((f, parent)) if parent else None
        ns = self._file_ns(f)
        top = self.top_funcs.get((ns, name), [])
        if top:
            c, _ = self._by_arity(top, argc)
            if c:
                return self._target(c, call, "same_package")
        fqn = self.simple_imports.get(f, {}).get(name)
        if fqn:
            mod, _, orig = fqn.rpartition(".")
            imp_top = self.top_funcs.get((mod, orig), [])
            if imp_top:
                c, _ = self._by_arity(imp_top, argc)
                if c:
                    return self._target(c, call, "imported_function")
            return None, _unres("call", call, STATUS_EXTERNAL, f"Imported from outside the repository: {fqn}"), None
        for cls, member in self.static_imports.get(f, []):
            if member in ("*", name):
                tsym = self.types_by_fqn.get(cls)
                if tsym:
                    c, _ = self.find_methods(tsym, name, argc)
                    if c:
                        return self._target(c, call, "static_import")
                elif member == name:
                    return None, _unres("call", call, STATUS_EXTERNAL, f"Static import from outside the repository: {cls}.{name}"), None
        for pkg in self.wildcards.get(f, []):
            wild = self.top_funcs.get((pkg, name), [])
            if wild:
                c, _ = self._by_arity(wild, argc)
                if c:
                    return self._target(c, call, "wildcard_import")
        if self.lang == "kotlin" and name in KOTLIN_STD_FUNCS:
            return None, _unres("call", call, STATUS_EXTERNAL, f"Kotlin standard library function '{name}'"), None
        return None, _unres("call", call, STATUS_UNRESOLVED, f"'{name}' could not be resolved to a definition"), None

    def _extension(self, file_path: str, recv_simple: str, name: str, argc: Optional[int]) -> list[dict[str, Any]]:
        if self.lang != "kotlin" or not recv_simple:
            return []
        cands = [e for e in self.extensions.get(recv_simple, []) if e["name"] == name]
        return self._by_arity(cands, argc)[0] if cands else []

    def _context_type(self, caller: Optional[dict[str, Any]], scope: Optional[str], f: str, super_: bool = False) -> Optional[dict[str, Any]]:
        if not scope:
            return None
        return self.base.symbols_by_file_and_qname.get((f, scope))

    # -------------------------------------------------------------- relations
    def resolve_relation(self, rel: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference], str]:
        f = Path(rel["file_path"]).as_posix()
        src = self.base.symbols_by_id.get(rel.get("source_symbol_id") or "")
        sym, status = self.resolve_type(f, rel["target"], (src or {}).get("parent_scope"))
        kind = rel["kind"]
        if sym is not None:
            if self.lang == "kotlin" and kind in ("extends", "implements"):
                # Kotlin writes both as supertypes: classify by what the target actually is.
                kind = "implements" if sym["kind"] == "interface" else "extends"
            return f"symbol:{sym['id']}", None, kind.upper()
        reason = "Supertype is outside the repository" if status == "external" else f"Type '{rel['target']}' not found in the repository"
        return None, _unres("relation", rel, STATUS_EXTERNAL if status == "external" else STATUS_UNRESOLVED, reason), kind.upper()


def _unres_import(file_path: str, imp: dict[str, Any], expr: str, status: str, reason: str) -> UnresolvedReference:
    return UnresolvedReference(kind="import", source_file=file_path, expression=expr, target_name=imp.get("module") or imp.get("name"),
                               lineno=imp.get("lineno"), status=status, reason=reason)


class JavaResolver(JvmResolver):
    languages = ("java",)
    lang = "java"
    builtin_types = JAVA_LANG


class KotlinResolver(JvmResolver):
    languages = ("kotlin",)
    lang = "kotlin"
    builtin_types = KOTLIN_STD


# ============================================================================== Rust
class RustResolver(LanguageResolver):
    languages = ("rust",)

    def prepare(self, imports: list[dict[str, Any]]) -> None:
        b = self.base
        self.items: dict[tuple[str, str], dict[str, Any]] = {}
        self.modules: dict[tuple[str, str], str] = {}
        self.members: dict[str, dict[str, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
        self.use_map: dict[str, dict[str, list[str]]] = defaultdict(dict)
        self.use_wild: dict[str, list[list[str]]] = defaultdict(list)
        self.crates: dict[str, str] = {}  # crate name -> crate root dir
        self.reexports: dict[tuple[str, str], list[str]] = {}
        self._load_crates()
        for path in b.all_files:
            if path.endswith(".rs"):
                self.modules[(rust_crate_root(path), rust_module_path(path))] = path
        self.prefixes: set[tuple[str, str]] = set()  # every module/item path prefix, for O(1) relative-path checks
        for (croot, full) in [*self.modules.keys()]:
            parts = full.split("::")
            self.prefixes.update((croot, "::".join(parts[:i])) for i in range(1, len(parts) + 1))
        syms = [s for s in b.symbols_by_id.values() if s.get("language") == "rust"]
        for s in syms:
            if s["kind"] in TYPE_KINDS or (s["kind"] in CALLABLE_KINDS and not s.get("parent_scope")):
                root = rust_crate_root(s["file_path"])
                key = (root, f"{s['namespace']}::{s['qualified_name']}")
                self.items.setdefault(key, s)
                parts = key[1].split("::")
                self.prefixes.update((root, "::".join(parts[:i])) for i in range(1, len(parts) + 1))
        for s in syms:
            if s["kind"] in CALLABLE_KINDS and s.get("parent_scope"):
                tsym = self._type_of_impl(s)
                if tsym is not None:
                    self.members[tsym["id"]][s["name"]].append(s)
        for imp in imports:
            if imp.get("language") != "rust" or imp.get("import_form") == "mod":
                continue
            f = Path(imp["file_path"]).as_posix()
            module, name = imp.get("module") or "", imp.get("name") or ""
            segs = [x for x in (module.split("::") if module else []) if x]
            if name == "*":
                self.use_wild[f].append(self.abs_path(f, segs) or [])
            else:
                full = self.abs_path(f, segs + [name], resolve_use=False)
                if full is not None:
                    self.use_map[f][imp.get("alias") or name] = full
                else:
                    self.use_map[f][imp.get("alias") or name] = ["<extern>", *segs, name]
        # `pub use a::B;` makes B reachable from this module's path.
        for path, exps in b.exports_by_file.items():
            if not path.endswith(".rs"):
                continue
            for exp in exps:
                if exp.get("language") != "rust" or not exp.get("is_reexport"):
                    continue
                segs = [x for x in (exp.get("source_module") or "").split("::") if x] + [exp.get("alias") or exp["name"]]
                target = self.abs_path(path, segs, resolve_use=False)
                if target is not None:
                    self.reexports[(rust_crate_root(path), f"{rust_module_path(path)}::{exp['name']}")] = target
        self.prepared = True

    def _load_crates(self) -> None:
        try:
            import tomllib  # Python 3.11+
        except ImportError:  # pragma: no cover
            tomllib = None
        for path in self.base.all_files:
            if PurePosixPath(path).name != "Cargo.toml":
                continue
            try:
                text = (self.base.repo_root / path).read_text(encoding="utf-8", errors="replace")
                name = (tomllib.loads(text).get("package", {}) or {}).get("name") if tomllib else None
                if name is None:
                    m = re.search(r'^\s*name\s*=\s*"([^"]+)"', text, re.M)
                    name = m.group(1) if m else None
            except Exception:  # noqa: BLE001 - malformed manifests must not break analysis
                continue
            if name:
                parent = str(PurePosixPath(path).parent)
                self.crates[name.replace("-", "_")] = f"{'' if parent == '.' else parent + '/'}src"

    def _type_of_impl(self, method: dict[str, Any]) -> Optional[dict[str, Any]]:
        name = method.get("receiver_type") or method.get("parent_scope")
        return self.resolve_type(method["file_path"], name or "", None)[0]

    # -------------------------------------------------------------- paths
    def abs_path(self, file_path: str, segs: list[str], resolve_use: bool = True) -> Optional[list[str]]:
        """Absolute ``[crate_root, 'crate', 'a', 'B']`` path, or None when it points outside the repository."""
        if not segs:
            return None
        root = rust_crate_root(file_path)
        mod = rust_module_path(file_path).split("::")
        head, rest = segs[0], segs[1:]
        if head == "crate":
            return [root, "crate", *rest]
        if head == "self":
            return [root, *mod, *rest]
        if head == "super":
            base = mod[:-1] or ["crate"]
            while rest and rest[0] == "super":
                base, rest = (base[:-1] or ["crate"]), rest[1:]
            return [root, *base, *rest]
        if head in self.crates:
            return [self.crates[head], "crate", *rest]
        if resolve_use and head in self.use_map.get(file_path, {}):
            target = self.use_map[file_path][head]
            return None if target and target[0] == "<extern>" else [*target, *rest]
        # a child module / item declared in this module (2018 relative path)
        local = (root, f"{'::'.join(mod)}::{head}")
        if local in self.items or local in self.modules or local in self.prefixes:
            return [root, *mod, head, *rest]
        return None

    def _item_keys(self) -> Any:
        return self.items.keys()

    def lookup(self, absolute: Optional[list[str]], depth: int = 0) -> tuple[str, Any]:
        """Resolve an absolute path to ('item', symbol) | ('member', symbol list) | ('module', file) | ('none', None)."""
        if not absolute or len(absolute) < 2 or depth > 6:
            return "none", None
        root, segs = absolute[0], absolute[1:]
        for k in range(len(segs), 0, -1):
            prefix = "::".join(segs[:k])
            rest = segs[k:]
            item = self.items.get((root, prefix))
            if item is not None:
                if not rest:
                    return "item", item
                if len(rest) == 1 and item["kind"] in TYPE_KINDS:
                    ms = self.members.get(item["id"], {}).get(rest[0])
                    if ms:
                        return "member", ms
                    if item["kind"] == "enum":
                        return "item", item  # enum variant -> the enum
                return "none", None
            re_target = self.reexports.get((root, prefix))
            if re_target is not None:
                return self.lookup([*re_target, *rest], depth + 1)
            mod_file = self.modules.get((root, prefix))
            if mod_file is not None:
                if not rest:
                    return "module", mod_file
                continue
        return "none", None

    def resolve_type(self, file_path: str, name: str, scope: Optional[str]) -> tuple[Optional[dict[str, Any]], str]:
        if not name:
            return None, "unresolved"
        segs = name.split("::")
        absolute = self.abs_path(file_path, segs)
        if absolute is None and len(segs) == 1:
            root = rust_crate_root(file_path)
            absolute = [root, *rust_module_path(file_path).split("::"), segs[0]]
        kind, val = self.lookup(absolute)
        if kind == "item":
            return val, "resolved"
        for wild in self.use_wild.get(file_path, []):
            kind, val = self.lookup([*wild, *segs]) if wild else ("none", None)
            if kind == "item":
                return val, "resolved"
        head = segs[0]
        if head in self.use_map.get(file_path, {}) and self.use_map[file_path][head][:1] == ["<extern>"]:
            return None, "external"
        if head in ("std", "core", "alloc") or head[:1].isupper() and head in {"String", "Vec", "Option", "Result", "Box", "Rc", "Arc", "HashMap", "Self"}:
            return None, "external"
        return None, "unresolved"

    # -------------------------------------------------------------- imports
    def resolve_import(self, imp: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference]]:
        f = Path(imp["file_path"]).as_posix()
        module, name = imp.get("module") or "", imp.get("name") or ""
        segs = [x for x in module.split("::") if x] + ([name] if name != "*" else [])
        expr = f"use {module}::{name}" if module else f"use {name}"
        if imp.get("import_form") == "mod":
            absolute = self.abs_path(f, ["self", name])
            kind, val = self.lookup(absolute)
            if kind == "module":
                return val, None
            return None, _unres_import(f, imp, expr.replace("use", "mod"), STATUS_UNRESOLVED, f"Module file for '{name}' not found (expected {name}.rs or {name}/mod.rs)")
        absolute = self.abs_path(f, segs, resolve_use=False)
        if absolute is None:
            return None, _unres_import(f, imp, expr, STATUS_EXTERNAL, f"'{segs[0] if segs else name}' is an external crate")
        kind, val = self.lookup(absolute)
        if kind == "item":
            return val["file_path"], None
        if kind == "member":
            return val[0]["file_path"], None
        if kind == "module":
            return val, None
        if segs and segs[0] in ("std", "core", "alloc"):
            return None, _unres_import(f, imp, expr, STATUS_EXTERNAL, "Rust standard library")
        return None, _unres_import(f, imp, expr, STATUS_UNRESOLVED, f"'{'::'.join(segs)}' could not be located in the repository")

    # -------------------------------------------------------------- calls
    def resolve_call(self, call: dict[str, Any]) -> Resolved:
        f = Path(call["file_path"]).as_posix()
        callee, name, kind = call.get("callee") or "", call.get("callee_name") or "", call.get("call_kind")
        if kind == "macro_call":
            base = name
            if base in STD_MACROS:
                return None, _unres("call", call, STATUS_EXTERNAL, f"Standard library macro '{base}!'"), None
            return None, _unres("call", call, STATUS_UNRESOLVED, f"Macro '{base}!' is not expanded; generated code is not analysed"), None
        caller = self.base.symbols_by_id.get(call.get("caller_symbol_id") or "")
        if kind == "method_call":
            recv = call.get("receiver_type")
            if recv == "Self" and caller is not None:
                recv = caller.get("receiver_type") or caller.get("parent_scope")
            if recv:
                tsym, status = self.resolve_type(f, recv, None)
                if tsym is not None:
                    ms = self.members.get(tsym["id"], {}).get(name)
                    if ms:
                        return self._pick(ms, call, "typed_receiver")
                    return None, _unres("call", call, STATUS_UNRESOLVED, f"No method '{name}' found on '{tsym['qualified_name']}' (trait-provided or derived methods are not modelled)"), None
                if status == "external":
                    return None, _unres("call", call, STATUS_EXTERNAL, f"Receiver type '{recv}' is outside the repository"), None
            return None, _unres("call", call, STATUS_UNRESOLVED, f"Receiver type of '{callee}' could not be determined statically"), None
        segs = callee.split("::")
        if len(segs) == 1:  # plain function in this module, or imported by `use`
            absolute = self.abs_path(f, segs)
            if absolute is None:
                root = rust_crate_root(f)
                prefix = ""
                if caller is not None and "::" in caller["qualified_name"] and not caller.get("parent_scope"):
                    prefix = caller["qualified_name"].rsplit("::", 1)[0] + "::"  # sibling in the same inline module
                absolute = [root, *rust_module_path(f).split("::"), prefix + segs[0]] if not prefix else [root, *rust_module_path(f).split("::"), *prefix.rstrip(":").split("::"), segs[0]]
        else:
            absolute = self.abs_path(f, segs)
            if absolute is None and segs[0] == "Self" and caller is not None:
                owner = caller.get("receiver_type") or caller.get("parent_scope")
                tsym, _ = self.resolve_type(f, owner or "", None)
                if tsym is not None:
                    ms = self.members.get(tsym["id"], {}).get(segs[-1])
                    if ms:
                        return self._pick(ms, call, "self_path")
        k, val = self.lookup(absolute)
        if k == "item" and val["kind"] in CALLABLE_KINDS:
            return f"symbol:{val['id']}", None, "path_call"
        if k == "item" and val["kind"] in TYPE_KINDS:
            return f"symbol:{val['id']}", None, "constructor_call"
        if k == "member":
            return self._pick(val, call, "associated_function")
        if absolute is None and (segs[0] in ("std", "core", "alloc") or segs[0][:1].isupper() and len(segs) > 1):
            return None, _unres("call", call, STATUS_EXTERNAL, f"'{callee}' refers to the standard library or an external crate"), None
        if absolute is None and len(segs) > 1:
            return None, _unres("call", call, STATUS_EXTERNAL, f"'{segs[0]}' is an external crate or unknown path root"), None
        return None, _unres("call", call, STATUS_UNRESOLVED, f"'{callee}' could not be resolved to a definition"), None

    def _pick(self, ms: list[dict[str, Any]], call: dict[str, Any], strategy: str) -> Resolved:
        if len(ms) == 1:
            return f"symbol:{ms[0]['id']}", None, strategy
        ids = [f"symbol:{m['id']}" for m in ms]
        return None, _unres("call", call, STATUS_AMBIGUOUS, f"{len(ms)} definitions of '{call.get('callee_name')}' (trait implementations)", ids), None

    # -------------------------------------------------------------- relations
    def resolve_relation(self, rel: dict[str, Any]) -> tuple[Optional[str], Optional[UnresolvedReference], str]:
        f = Path(rel["file_path"]).as_posix()
        sym, status = self.resolve_type(f, rel["target"], None)
        kind = rel["kind"].upper()
        if sym is not None:
            return f"symbol:{sym['id']}", None, kind
        reason = "Trait is outside the repository" if status == "external" else f"Trait '{rel['target']}' not found in the repository"
        return None, _unres("relation", rel, STATUS_EXTERNAL if status == "external" else STATUS_UNRESOLVED, reason), kind

    def relation_source(self, rel: dict[str, Any]) -> Optional[str]:
        """Source type node for `impl Trait for Type` (the parser only knows the type name)."""
        if rel.get("source_symbol_id"):
            return f"symbol:{rel['source_symbol_id']}"
        sym, _ = self.resolve_type(Path(rel["file_path"]).as_posix(), rel.get("source_name") or "", None)
        return f"symbol:{sym['id']}" if sym else None
