"""Symbol and import resolution engine for Astral Cartographer.

Resolves imports and call expressions to concrete local definitions
using conservative matching and explicit ambiguity tracking.
Supports Python, JavaScript, and TypeScript language semantics.
"""

from __future__ import annotations

import builtins
import json
import os
import re
from pathlib import Path
import sys
from typing import Any, Optional

from app.graph.models import (
    STATUS_AMBIGUOUS,
    STATUS_EXTERNAL,
    STATUS_RESOLVED,
    STATUS_UNRESOLVED,
    UnresolvedReference,
)

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
        "require",
        "module",
        "exports",
        "globalThis",
        "window",
        "document",
        "alert",
        "parseInt",
        "parseFloat",
        "isNaN",
        "isFinite",
        "encodeURI",
        "decodeURI",
        "encodeURIComponent",
        "decodeURIComponent",
    }
)

# Node.js core modules (with or without the ``node:`` prefix) are never repository files.
NODE_BUILTIN_MODULES: frozenset[str] = frozenset(
    {
        "assert", "async_hooks", "buffer", "child_process", "cluster", "console",
        "constants", "crypto", "dgram", "diagnostics_channel", "dns", "domain",
        "events", "fs", "http", "http2", "https", "inspector", "module", "net",
        "os", "path", "perf_hooks", "process", "punycode", "querystring",
        "readline", "repl", "stream", "string_decoder", "sys", "timers", "tls",
        "trace_events", "tty", "url", "util", "v8", "vm", "wasi", "worker_threads",
        "zlib", "test",
    }
)

_JSONC_COMMENT = re.compile(r'("(?:\\.|[^"\\])*")|//[^\n]*|/\*.*?\*/', re.DOTALL)
_JSONC_TRAILING_COMMA = re.compile(r",(\s*[}\]])")


def _parse_jsonc(text: str) -> dict[str, Any]:
    """Parse tsconfig-style JSON (comments and trailing commas allowed)."""
    stripped = _JSONC_COMMENT.sub(lambda m: m.group(1) or "", text)
    stripped = _JSONC_TRAILING_COMMA.sub(r"\1", stripped)
    data = json.loads(stripped)
    return data if isinstance(data, dict) else {}


JS_TS_EXTENSIONS: list[str] = [
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".mjs",
    ".cjs",
    ".mts",
    ".cts",
]


class SymbolResolver:
    """Indexes symbols and resolves import and call references."""

    def __init__(self, repo_root: Path | str) -> None:
        self.repo_root: Path = Path(repo_root).resolve()

        # Files and directories from inventory
        self.all_files: set[str] = set()
        self.python_files: set[str] = set()
        self.file_records: dict[str, dict[str, Any]] = {}

        # Symbol indexes
        self.symbols_by_id: dict[str, dict[str, Any]] = {}
        self.symbols_by_node_id: dict[str, dict[str, Any]] = {}
        self.symbols_by_file: dict[str, list[dict[str, Any]]] = {}
        self.symbols_by_file_and_qname: dict[tuple[str, str], dict[str, Any]] = {}
        self.symbols_by_file_and_name: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self.symbols_by_qname: dict[str, list[dict[str, Any]]] = {}
        self.symbols_by_name: dict[str, list[dict[str, Any]]] = {}
        self.classes_by_file: dict[str, dict[str, dict[str, Any]]] = {}

        # Export indexes: file_path -> list of exports, (file_path, exported_name) -> export
        self.exports_by_file: dict[str, list[dict[str, Any]]] = {}
        self.exports_by_file_and_name: dict[tuple[str, str], dict[str, Any]] = {}

        # Scope import mapping per file:
        # file_path -> { local_name: { "type": "symbol"|"module"|"namespace", ... } }
        self.file_import_scopes: dict[str, dict[str, Any]] = {}

        # tsconfig/jsconfig path aliases: (config_dir, base_dir, [(pattern, [targets])])
        self.js_alias_configs: list[tuple[str, str, list[tuple[str, list[str]]]]] = []
        self.config_warnings: list[str] = []

    def index_inventory(self, files: list[dict[str, Any]]) -> None:
        """Index repository files from scanner inventory."""
        for f in files:
            norm_path = Path(f["path"]).as_posix()
            self.all_files.add(norm_path)
            self.file_records[norm_path] = f
            if f.get("language") == "Python":
                self.python_files.add(norm_path)
        self._load_js_alias_configs()

    def _load_js_alias_configs(self) -> None:
        """Read tsconfig.json / jsconfig.json ``baseUrl`` and ``paths`` for alias resolution."""
        self.js_alias_configs = []
        for rel in sorted(self.all_files):
            if Path(rel).name not in ("tsconfig.json", "jsconfig.json"):
                continue
            try:
                raw = (self.repo_root / rel).read_text(encoding="utf-8", errors="replace")
                opts = (_parse_jsonc(raw).get("compilerOptions") or {})
            except (OSError, ValueError) as exc:
                self.config_warnings.append(f"Could not read {rel}: {exc}")
                continue
            base_url = opts.get("baseUrl")
            paths = opts.get("paths") or {}
            if base_url is None and not paths:
                continue
            config_dir = Path(rel).parent.as_posix()
            config_dir = "" if config_dir == "." else config_dir
            base_dir = (Path(config_dir) / (base_url or ".")).as_posix()
            base_dir = "" if base_dir == "." else os.path.normpath(base_dir).replace("\\", "/")
            base_dir = "" if base_dir == "." else base_dir
            patterns = [
                (pat, [t for t in targets if isinstance(t, str)])
                for pat, targets in paths.items()
                if isinstance(targets, list)
            ]
            self.js_alias_configs.append((config_dir, base_dir, patterns))
            if base_url is not None:
                patterns.append(("*", ["*"]))

    def _resolve_js_alias(self, importing_file: str, specifier: str) -> Optional[str]:
        """Resolve a bare specifier through tsconfig/jsconfig ``paths``/``baseUrl``."""
        importing_dir = Path(importing_file).parent.as_posix()
        for config_dir, base_dir, patterns in self.js_alias_configs:
            if config_dir and not (
                importing_dir == config_dir or importing_dir.startswith(config_dir + "/")
            ):
                continue
            for pattern, targets in patterns:
                if "*" in pattern:
                    prefix, _, suffix = pattern.partition("*")
                    if not (specifier.startswith(prefix) and specifier.endswith(suffix)):
                        continue
                    star = specifier[len(prefix): len(specifier) - len(suffix) if suffix else None]
                elif specifier == pattern:
                    star = ""
                else:
                    continue
                for target in targets:
                    candidate = target.replace("*", star)
                    joined = os.path.normpath(os.path.join(base_dir, candidate)).replace("\\", "/")
                    joined = "" if joined == "." else joined
                    resolved = self._resolve_js_relative_specifier(
                        importing_file, "/" + joined if joined else "/"
                    )
                    if resolved:
                        return resolved
        return None

    def index_symbols(self, symbols: list[dict[str, Any]]) -> None:
        """Index symbols extracted by AST parser."""
        for sym in symbols:
            raw_id = sym.get("id")
            if not raw_id:
                continue
            node_id = f"symbol:{raw_id}"
            file_path = Path(sym.get("file_path", "")).as_posix()
            name = sym.get("name", "")
            qname = sym.get("qualified_name") or name
            kind = sym.get("kind", "function")

            self.symbols_by_id[raw_id] = sym
            self.symbols_by_node_id[node_id] = sym

            self.symbols_by_file.setdefault(file_path, []).append(sym)
            self.symbols_by_file_and_qname[(file_path, qname)] = sym
            self.symbols_by_file_and_name.setdefault((file_path, name), []).append(sym)

            self.symbols_by_qname.setdefault(qname, []).append(sym)
            self.symbols_by_name.setdefault(name, []).append(sym)

            if kind == "class":
                self.classes_by_file.setdefault(file_path, {})[name] = sym

    def index_exports(self, exports: list[dict[str, Any]]) -> None:
        """Index exports extracted by JavaScript/TypeScript parser."""
        for exp in exports:
            if not exp.get("file_path") or not exp.get("name"):
                continue
            file_path = Path(exp["file_path"]).as_posix()
            exp_name = exp["name"]
            self.exports_by_file.setdefault(file_path, []).append(exp)
            self.exports_by_file_and_name[(file_path, exp_name)] = exp

    def find_exported_symbol(
        self,
        file_path: str,
        name: str,
        visited: Optional[set[str]] = None,
    ) -> Optional[dict[str, Any]]:
        """Look up an exported symbol in file_path, following re-exports recursively."""
        if visited is None:
            visited = set()
        if file_path in visited:
            return None
        visited.add(file_path)

        # 1. Check direct export record
        if (file_path, name) in self.exports_by_file_and_name:
            exp = self.exports_by_file_and_name[(file_path, name)]
            if exp.get("is_reexport") and exp.get("source_module"):
                target_f = self._resolve_js_relative_specifier(
                    file_path, exp["source_module"]
                )
                if target_f:
                    target_name = exp.get("alias") or name
                    if target_name == "*":
                        return None
                    return self.find_exported_symbol(target_f, target_name, visited)
            else:
                local_name = exp.get("alias") or name
                syms = self.symbols_by_file_and_name.get((file_path, local_name), [])
                if syms:
                    return syms[0]

        # 2. Check wildcard re-exports: export * from './other'
        for exp in self.exports_by_file.get(file_path, []):
            if exp.get("is_reexport") and exp.get("name") == "*":
                source_mod = exp.get("source_module")
                if source_mod:
                    target_f = self._resolve_js_relative_specifier(
                        file_path, source_mod
                    )
                    if target_f:
                        res = self.find_exported_symbol(target_f, name, visited)
                        if res:
                            return res

        # 3. Check if local symbol is explicitly marked exported
        local_syms = self.symbols_by_file_and_name.get((file_path, name), [])
        exported_syms = [s for s in local_syms if s.get("is_exported")]
        if exported_syms:
            return exported_syms[0]

        # 4. If name is 'default', check for default export
        if name == "default":
            for exp in self.exports_by_file.get(file_path, []):
                if exp.get("is_default"):
                    alias = exp.get("alias")
                    if alias and alias != "default":
                        syms = self.symbols_by_file_and_name.get((file_path, alias), [])
                        if syms:
                            return syms[0]
            # Look for top-level class or function explicitly marked exported
            file_syms = self.symbols_by_file.get(file_path, [])
            top_exported = [
                s
                for s in file_syms
                if s.get("parent_scope") is None
                and s.get("is_exported")
                and s["kind"] in ("class", "function", "async_function")
            ]
            if len(top_exported) == 1:
                return top_exported[0]

        return None

    def resolve_import(
        self,
        imp: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference]]:
        """Resolve an import statement to a local repository file."""
        if not imp.get("module") and not imp.get("name"):
            return None, None

        file_path = Path(imp.get("file_path", "")).as_posix()
        is_python = (
            imp.get("language") == "python"
            or file_path.endswith((".py", ".pyw", ".pyi"))
        )

        if is_python:
            return self._resolve_python_import(imp)
        else:
            return self._resolve_js_import(imp)

    def _resolve_python_import(
        self,
        imp: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference]]:
        """Python-specific import resolution."""
        importing_file = Path(imp["file_path"]).as_posix()
        module = imp.get("module")
        name = imp.get("name", "")
        lineno = imp.get("lineno")
        level = imp.get("level", 0)

        # 1. Relative import resolution (level > 0)
        if level > 0:
            target_path = self._resolve_relative_import_path(
                importing_file=importing_file,
                module=module,
                name=name,
                level=level,
            )
            if target_path and target_path in self.all_files:
                return (target_path, None)

            expr = f"from {'.' * level}{module or ''} import {name}"
            return (
                None,
                UnresolvedReference(
                    kind="import",
                    source_file=importing_file,
                    expression=expr,
                    target_name=name,
                    lineno=lineno,
                    status=STATUS_UNRESOLVED,
                    reason=f"Relative import target '{module or name}' could not be located in repository",
                ),
            )

        # 2. Absolute import resolution (level == 0)
        target_path = self._resolve_absolute_import_path(
            importing_file=importing_file,
            module=module,
            name=name,
        )
        if target_path and target_path in self.all_files:
            return (target_path, None)

        # Check if external or standard library
        root_mod = (module.split(".")[0] if module else name).split(".")[0]
        if root_mod in STDLIB_MODULE_NAMES:
            status = STATUS_EXTERNAL
            reason = f"Module '{root_mod}' is part of Python standard library"
        else:
            status = STATUS_EXTERNAL
            reason = f"Module '{root_mod}' is an external or third-party dependency"

        expr = (
            f"import {module}"
            if not name or module == name
            else f"from {module} import {name}"
        )
        return (
            None,
            UnresolvedReference(
                kind="import",
                source_file=importing_file,
                expression=expr,
                target_name=name,
                lineno=lineno,
                status=status,
                reason=reason,
            ),
        )

    def _resolve_relative_import_path(
        self,
        importing_file: str,
        module: Optional[str],
        name: str,
        level: int,
    ) -> Optional[str]:
        """Resolve a Python relative import to candidate file path."""
        file_path_obj = Path(importing_file)
        base_dir = file_path_obj.parent
        for _ in range(level - 1):
            base_dir = base_dir.parent

        base_posix = base_dir.as_posix()
        prefix = f"{base_posix}/" if base_posix and base_posix != "." else ""

        candidates: list[str] = []
        if module:
            mod_path = module.replace(".", "/")
            candidates.append(f"{prefix}{mod_path}.py")
            if name:
                candidates.append(f"{prefix}{mod_path}/{name}.py")
                candidates.append(f"{prefix}{mod_path}/{name}/__init__.py")
            candidates.append(f"{prefix}{mod_path}/__init__.py")
        elif name:
            candidates.append(f"{prefix}{name}.py")
            candidates.append(f"{prefix}{name}/__init__.py")

        for c in candidates:
            clean_c = Path(c).as_posix()
            if clean_c in self.all_files:
                return clean_c
        return None

    def _resolve_absolute_import_path(
        self,
        importing_file: str,
        module: Optional[str],
        name: str,
    ) -> Optional[str]:
        """Resolve a Python absolute import against repository roots and subroots."""
        if not module and not name:
            return None

        mod_variants: list[str] = []
        if module:
            mod_rel = module.replace(".", "/")
            mod_variants.append(f"{mod_rel}.py")
            if name:
                mod_variants.append(f"{mod_rel}/{name}.py")
                mod_variants.append(f"{mod_rel}/{name}/__init__.py")
            mod_variants.append(f"{mod_rel}/__init__.py")
        elif name:
            name_rel = name.replace(".", "/")
            mod_variants.append(f"{name_rel}.py")
            mod_variants.append(f"{name_rel}/__init__.py")

        importing_dir = Path(importing_file).parent
        search_roots: list[str] = [""]

        if str(importing_dir) != ".":
            search_roots.append(importing_dir.as_posix())

        for ancestor in [importing_dir] + list(importing_dir.parents):
            p = ancestor.as_posix()
            if p and p != "." and p not in search_roots:
                search_roots.append(p)

        for common_root in ["backend", "src", "app", "backend/app"]:
            if common_root in self.all_files or any(
                f.startswith(f"{common_root}/") for f in self.all_files
            ):
                if common_root not in search_roots:
                    search_roots.append(common_root)

        for base in search_roots:
            prefix = f"{base}/" if base else ""
            for variant in mod_variants:
                candidate = Path(f"{prefix}{variant}").as_posix()
                if candidate in self.all_files:
                    return candidate

        return None

    def _resolve_js_relative_specifier(
        self,
        importing_file: str,
        specifier: str,
    ) -> Optional[str]:
        """Resolve a relative or rooted JS/TS module specifier to a concrete repository file."""
        importing_dir = Path(importing_file).parent
        is_rel = specifier.startswith("./") or specifier.startswith("../")

        if is_rel:
            combined = (importing_dir / specifier).as_posix()
            # Normalize path without leading dots or escaping repository
            parts: list[str] = []
            for p in combined.split("/"):
                if p == "" or p == ".":
                    continue
                if p == "..":
                    if parts:
                        parts.pop()
                    else:
                        # Escaped repo root
                        return None
                else:
                    parts.append(p)
            base_target = "/".join(parts)
        else:
            # Rooted specifier (used for alias targets): relative to repository root
            base_target = specifier.strip("/")

        # 1. Exact match
        if base_target in self.all_files:
            return base_target

        # 2. Check TS corresponding file if specifier used JS extension (.js -> .ts/.tsx)
        for js_ext in (".js", ".jsx", ".mjs", ".cjs"):
            if base_target.endswith(js_ext):
                stem = base_target[: -len(js_ext)]
                for ts_ext in (".ts", ".tsx", ".mts", ".cts"):
                    candidate = f"{stem}{ts_ext}"
                    if candidate in self.all_files:
                        return candidate

        # 3. Extensionless file match
        for ext in JS_TS_EXTENSIONS:
            candidate = f"{base_target}{ext}"
            if candidate in self.all_files:
                return candidate

        # 4. Directory index match: ./dir -> dir/index.ts, dir/index.js, etc.
        for ext in JS_TS_EXTENSIONS:
            candidate = f"{base_target}/index{ext}" if base_target else f"index{ext}"
            if candidate in self.all_files:
                return candidate

        return None

    def _resolve_js_import(
        self,
        imp: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference]]:
        """JavaScript and TypeScript module resolution."""
        importing_file = Path(imp["file_path"]).as_posix()
        module = imp.get("module") or ""
        name = imp.get("name", "")
        alias = imp.get("alias")
        lineno = imp.get("lineno")
        import_form = imp.get("import_form", "named")

        expr = f"import {name} from '{module}'"
        if import_form == "namespace":
            expr = f"import * as {alias} from '{module}'"
        elif import_form == "side_effect":
            expr = f"import '{module}'"

        # Check if external package (not starting with . or /)
        is_relative = module.startswith("./") or module.startswith("../")
        if not is_relative:
            # Only tsconfig/jsconfig aliases may map a bare specifier onto repository
            # files; a bare name is never guessed from the repository root.
            target = self._resolve_js_alias(importing_file, module)
            if target:
                return (target, None)
            if module.startswith("node:") or module.split("/")[0] in NODE_BUILTIN_MODULES:
                return (
                    None,
                    UnresolvedReference(
                        kind="import",
                        source_file=importing_file,
                        expression=expr,
                        target_name=module,
                        lineno=lineno,
                        status=STATUS_EXTERNAL,
                        reason=f"Module '{module}' is a Node.js built-in",
                    ),
                )

            # Not found locally: treat as external dependency
            return (
                None,
                UnresolvedReference(
                    kind="import",
                    source_file=importing_file,
                    expression=expr,
                    target_name=module,
                    lineno=lineno,
                    status=STATUS_EXTERNAL,
                    reason=f"Module '{module}' is an external package or dependency",
                ),
            )

        # Relative import
        target_file = self._resolve_js_relative_specifier(importing_file, module)
        if target_file and target_file in self.all_files:
            return (target_file, None)

        return (
            None,
            UnresolvedReference(
                kind="import",
                source_file=importing_file,
                expression=expr,
                target_name=module,
                lineno=lineno,
                status=STATUS_UNRESOLVED,
                reason=f"Relative module '{module}' could not be located in repository",
            ),
        )

    def build_file_import_scopes(self, imports: list[dict[str, Any]]) -> None:
        """Build a lookup table of imported names and modules available in each file."""
        for imp in imports:
            file_path = Path(imp["file_path"]).as_posix()
            scope = self.file_import_scopes.setdefault(file_path, {})

            target_file, _ = self.resolve_import(imp)
            name = imp.get("name", "")
            alias = imp.get("alias")
            module = imp.get("module")
            import_form = imp.get("import_form", "named")
            is_py = (
                imp.get("language") == "python"
                or file_path.endswith((".py", ".pyw", ".pyi"))
            )

            if target_file is None:
                # Track external imports for diagnostics
                if is_py:
                    root_mod = (module.split(".")[0] if module else name).split(".")[0]
                    is_stdlib = root_mod in STDLIB_MODULE_NAMES
                    if module and name and name != module:
                        local_name = alias if alias else name
                        scope[local_name] = {
                            "type": "external_symbol",
                            "module": module,
                            "name": name,
                            "is_stdlib": is_stdlib,
                        }
                    else:
                        scope_key = (
                            alias if alias else (module.split(".")[0] if module else name)
                        )
                        scope[scope_key] = {
                            "type": "external_module",
                            "module": root_mod,
                            "is_stdlib": is_stdlib,
                        }
                else:
                    mod_name = module or name
                    if import_form == "namespace" or name == "*":
                        local_key = alias or name
                        scope[local_key] = {
                            "type": "external_module",
                            "module": mod_name,
                        }
                    elif import_form == "default" or name == "default":
                        local_key = alias or "default"
                        scope[local_key] = {
                            "type": "external_symbol",
                            "module": mod_name,
                            "name": "default",
                        }
                    else:
                        local_key = alias if alias else name
                        scope[local_key] = {
                            "type": "external_symbol",
                            "module": mod_name,
                            "name": name,
                        }
                continue

            if is_py:
                local_name = alias if alias else name
                if module and name and name != module:
                    matching_syms = self.symbols_by_file_and_name.get(
                        (target_file, name), []
                    )
                    if matching_syms:
                        scope[local_name] = {
                            "type": "symbol",
                            "symbol": matching_syms[0],
                            "target_file": target_file,
                        }
                    else:
                        # Check if target_file (e.g. __init__.py) re-exported this symbol
                        reexp_scope = self.file_import_scopes.get(target_file, {})
                        if (
                            name in reexp_scope
                            and reexp_scope[name].get("type") == "symbol"
                        ):
                            scope[local_name] = reexp_scope[name]
                        else:
                            scope[local_name] = {
                                "type": "module_or_attr",
                                "target_file": target_file,
                                "name": name,
                            }
                else:
                    scope_key = (
                        alias if alias else (module.split(".")[0] if module else name)
                    )
                    scope[scope_key] = {
                        "type": "module",
                        "target_file": target_file,
                    }
                    if not alias and module and module != scope_key:
                        scope[module] = {
                            "type": "module",
                            "target_file": target_file,
                        }
            else:
                # JavaScript / TypeScript import handling
                if import_form == "namespace" or name == "*":
                    local_key = alias or name
                    scope[local_key] = {
                        "type": "namespace",
                        "target_file": target_file,
                    }
                elif import_form == "default" or name == "default":
                    local_key = alias or "default"
                    exp_sym = self.find_exported_symbol(
                        target_file, "default"
                    ) or self.find_exported_symbol(target_file, local_key)
                    if exp_sym:
                        scope[local_key] = {
                            "type": "symbol",
                            "symbol": exp_sym,
                            "target_file": target_file,
                        }
                    else:
                        scope[local_key] = {
                            "type": "module_or_attr",
                            "target_file": target_file,
                            "name": local_key,
                        }
                else:
                    # Named import
                    local_key = alias if alias else name
                    exp_sym = self.find_exported_symbol(target_file, name)
                    if exp_sym:
                        scope[local_key] = {
                            "type": "symbol",
                            "symbol": exp_sym,
                            "target_file": target_file,
                        }
                    else:
                        scope[local_key] = {
                            "type": "module_or_attr",
                            "target_file": target_file,
                            "name": name,
                        }

    def _find_method_in_class(
        self,
        file_path: str,
        class_name: str,
        method_name: str,
        visited: Optional[set[tuple[str, str]]] = None,
    ) -> Optional[dict[str, Any]]:
        """Look up a method in a class or its inheritance hierarchy."""
        if visited is None:
            visited = set()
        key = (file_path, class_name)
        if key in visited:
            return None
        visited.add(key)

        # 1. Direct method in class
        member_qname = f"{class_name}.{method_name}"
        if (file_path, member_qname) in self.symbols_by_file_and_qname:
            m = self.symbols_by_file_and_qname[(file_path, member_qname)]
            if m["kind"] in ("method", "function", "async_function"):
                return m

        # 2. Check base classes
        cls_sym = self.symbols_by_file_and_qname.get((file_path, class_name))
        if not cls_sym or cls_sym.get("kind") != "class":
            cls_sym = self.classes_by_file.get(file_path, {}).get(class_name)

        if cls_sym and cls_sym.get("bases"):
            file_scope = self.file_import_scopes.get(file_path, {})
            for base_name in cls_sym["bases"]:
                clean_base = base_name.split("(")[0].split("[")[0].strip()
                # Check same file
                found = self._find_method_in_class(
                    file_path, clean_base, method_name, visited
                )
                if found:
                    return found
                # Check imported class
                if (
                    clean_base in file_scope
                    and file_scope[clean_base].get("type") == "symbol"
                ):
                    imp_sym = file_scope[clean_base]["symbol"]
                    if imp_sym.get("kind") == "class":
                        found = self._find_method_in_class(
                            imp_sym["file_path"], imp_sym["name"], method_name, visited
                        )
                        if found:
                            return found
        return None

    def _is_name_shadowed_in_caller(
        self,
        source_file: str,
        caller_id: Optional[str],
        name: str,
    ) -> tuple[bool, Optional[dict[str, Any]]]:
        """Check if name is defined in caller's local scope (parameters or local vars).

        Returns:
            (is_shadowed, nested_function_symbol_if_any)
        """
        if not caller_id:
            return False, None

        curr_sym = self.symbols_by_id.get(caller_id)
        while curr_sym:
            # 1. Check if name is a nested function defined inside curr_sym
            nested_qname = f"{curr_sym['qualified_name']}.{name}"
            if (source_file, nested_qname) in self.symbols_by_file_and_qname:
                nested_sym = self.symbols_by_file_and_qname[(source_file, nested_qname)]
                if nested_sym["kind"] in ("function", "async_function"):
                    return False, nested_sym

            # 2. Check parameters
            params = curr_sym.get("parameters") or []
            clean_params = {p.lstrip("*") for p in params}
            if name in clean_params:
                return True, None

            # 3. Check local variables
            local_vars = set(curr_sym.get("local_variables") or [])
            if name in local_vars:
                return True, None

            # Traverse up enclosing function if nested
            parent_scope = curr_sym.get("parent_scope")
            if (
                parent_scope
                and (source_file, parent_scope) in self.symbols_by_file_and_qname
            ):
                parent_sym = self.symbols_by_file_and_qname[(source_file, parent_scope)]
                if parent_sym["kind"] in ("function", "async_function"):
                    curr_sym = parent_sym
                else:
                    break
            else:
                break

        return False, None

    def resolve_call(
        self,
        call: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference], Optional[str]]:
        """Resolve a call expression to a target node ID."""
        if not call.get("callee") and not call.get("callee_name"):
            return None, None, "empty_callee"

        file_path = Path(call.get("file_path", "")).as_posix()
        is_python = (
            call.get("language") == "python"
            or file_path.endswith((".py", ".pyw", ".pyi"))
        )

        if is_python:
            return self._resolve_python_call(call)
        else:
            return self._resolve_js_call(call)

    def _resolve_python_call(
        self,
        call: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference], Optional[str]]:
        """Python-specific call resolution logic."""
        source_file = Path(call["file_path"]).as_posix()
        caller_id = call.get("caller_symbol_id")
        callee = call.get("callee", "")
        callee_name = call.get("callee_name") or callee.split(".")[-1]
        lineno = call.get("lineno")
        col_offset = call.get("col_offset")
        file_scope = self.file_import_scopes.get(source_file, {})

        # Scope and shadowing check for unqualified calls
        if "." not in callee:
            is_shadowed, nested_fn = self._is_name_shadowed_in_caller(
                source_file, caller_id, callee_name
            )
            if nested_fn:
                return (f"symbol:{nested_fn['id']}", None, "nested_function")
            if is_shadowed:
                return (
                    None,
                    UnresolvedReference(
                        kind="call",
                        source_file=source_file,
                        caller_id=caller_id,
                        expression=callee,
                        target_name=callee_name,
                        lineno=lineno,
                        col_offset=col_offset,
                        status=STATUS_UNRESOLVED,
                        reason=f"Local variable or parameter '{callee_name}' shadows symbol in scope",
                    ),
                    None,
                )

        # Strategy 1: Direct function or class in the same module / enclosing scope
        if "." not in callee:
            caller_sym = self.symbols_by_id.get(caller_id or "")
            # Sibling in same parent scope
            if caller_sym and caller_sym.get("parent_scope"):
                sibling_qname = f"{caller_sym['parent_scope']}.{callee_name}"
                if (source_file, sibling_qname) in self.symbols_by_file_and_qname:
                    sib = self.symbols_by_file_and_qname[(source_file, sibling_qname)]
                    if sib["kind"] in ("function", "async_function", "class"):
                        return (f"symbol:{sib['id']}", None, "same_module")

            # Module-level definition (parent_scope is None)
            if (source_file, callee_name) in self.symbols_by_file_and_qname:
                mod_sym = self.symbols_by_file_and_qname[(source_file, callee_name)]
                if mod_sym.get("parent_scope") is None and mod_sym["kind"] in (
                    "function",
                    "async_function",
                    "class",
                ):
                    return (f"symbol:{mod_sym['id']}", None, "same_module")

        # Strategy 2: Call through an imported symbol or alias
        if "." not in callee:
            if callee in file_scope:
                entry = file_scope[callee]
                if entry["type"] == "symbol":
                    target_node_id = f"symbol:{entry['symbol']['id']}"
                    strategy = (
                        "imported_alias"
                        if call.get("callee") != entry["symbol"]["name"]
                        else "imported_symbol"
                    )
                    return (target_node_id, None, strategy)
                elif entry["type"] == "external_symbol":
                    status = STATUS_EXTERNAL
                    reason = (
                        f"Call to imported standard library symbol '{entry['module']}.{entry['name']}'"
                        if entry.get("is_stdlib")
                        else f"Call to external dependency '{entry['module']}.{entry['name']}'"
                    )
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=callee_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=status,
                            reason=reason,
                        ),
                        None,
                    )

        # Strategy 3: Method call on self.method() or cls.method()
        if callee.startswith("self.") or callee.startswith("cls."):
            is_cls = callee.startswith("cls.")
            method_name = callee.split(".", 1)[1]
            caller_sym = self.symbols_by_id.get(caller_id or "")
            if caller_sym and caller_sym.get("parent_scope"):
                parent_class_name = caller_sym["parent_scope"].split(".")[-1]
                target_method = self._find_method_in_class(
                    source_file, parent_class_name, method_name
                )
                if target_method:
                    strategy = "cls_method" if is_cls else "self_method"
                    return (f"symbol:{target_method['id']}", None, strategy)
                else:
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=method_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=STATUS_UNRESOLVED,
                            reason=f"Method '{method_name}' not defined on class '{parent_class_name}' (or inherited from external/unknown base)",
                        ),
                        None,
                    )

        # Strategy 4: Class-qualified call: ClassName.method()
        if "." in callee and callee.count(".") == 1:
            qualifier, member = callee.split(".", 1)

            # 4a. Same file class
            target_method = self._find_method_in_class(source_file, qualifier, member)
            if target_method:
                return (f"symbol:{target_method['id']}", None, "class_method")

            # 4b. Imported class
            if qualifier in file_scope and file_scope[qualifier]["type"] == "symbol":
                imp_sym = file_scope[qualifier]["symbol"]
                if imp_sym.get("kind") == "class":
                    target_method = self._find_method_in_class(
                        imp_sym["file_path"], imp_sym["name"], member
                    )
                    if target_method:
                        return (f"symbol:{target_method['id']}", None, "class_method")

        # Strategy 5: Module-qualified call: module.func() / alias.func()
        if "." in callee and callee.count(".") == 1:
            mod_prefix, member = callee.split(".", 1)
            if mod_prefix in file_scope:
                entry = file_scope[mod_prefix]
                if entry["type"] == "module":
                    target_file = entry.get("target_file")
                    if target_file:
                        target_matches = self.symbols_by_file_and_name.get(
                            (target_file, member), []
                        )
                        callable_targets = [
                            s
                            for s in target_matches
                            if s["kind"] in ("function", "async_function", "class")
                        ]
                        if len(callable_targets) == 1:
                            target_node_id = f"symbol:{callable_targets[0]['id']}"
                            strategy = "imported_module_alias"
                            return (target_node_id, None, strategy)
                elif entry["type"] == "external_module":
                    status = STATUS_EXTERNAL
                    reason = (
                        f"Call to standard library module '{entry['module']}'"
                        if entry.get("is_stdlib")
                        else f"Call to external dependency '{entry['module']}'"
                    )
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=callee_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=status,
                            reason=reason,
                        ),
                        None,
                    )

        # Strategy 6: Check Python built-ins
        if "." not in callee and callee_name in PYTHON_BUILTINS:
            return (
                None,
                UnresolvedReference(
                    kind="call",
                    source_file=source_file,
                    caller_id=caller_id,
                    expression=callee,
                    target_name=callee_name,
                    lineno=lineno,
                    col_offset=col_offset,
                    status=STATUS_EXTERNAL,
                    reason=f"Call to Python built-in '{callee_name}'",
                ),
                None,
            )

        # Strategy 7: Check external / standard library calls
        root_ident = callee.split(".")[0]
        if root_ident in STDLIB_MODULE_NAMES:
            return (
                None,
                UnresolvedReference(
                    kind="call",
                    source_file=source_file,
                    caller_id=caller_id,
                    expression=callee,
                    target_name=callee_name,
                    lineno=lineno,
                    col_offset=col_offset,
                    status=STATUS_EXTERNAL,
                    reason=f"Call to standard library module '{root_ident}'",
                ),
                None,
            )

        # Strategy 8: Method calls on unknown receiver
        if "." in callee:
            return (
                None,
                UnresolvedReference(
                    kind="call",
                    source_file=source_file,
                    caller_id=caller_id,
                    expression=callee,
                    target_name=callee_name,
                    lineno=lineno,
                    col_offset=col_offset,
                    status=STATUS_UNRESOLVED,
                    reason=f"Unknown receiver type for method call '{callee}'",
                ),
                None,
            )

        # Strategy 9: Ambiguity check across repository
        if "." not in callee:
            repo_matches = self.symbols_by_name.get(callee_name, [])
            callable_matches = [
                s
                for s in repo_matches
                if s["kind"] in ("function", "async_function", "class")
            ]
            if len(callable_matches) > 1:
                candidate_ids = [f"symbol:{s['id']}" for s in callable_matches]
                return (
                    None,
                    UnresolvedReference(
                        kind="call",
                        source_file=source_file,
                        caller_id=caller_id,
                        expression=callee,
                        target_name=callee_name,
                        lineno=lineno,
                        col_offset=col_offset,
                        status=STATUS_AMBIGUOUS,
                        candidates=candidate_ids,
                        reason=f"Multiple candidate definitions found ({len(candidate_ids)}) without import or scope evidence",
                    ),
                    None,
                )

        return (
            None,
            UnresolvedReference(
                kind="call",
                source_file=source_file,
                caller_id=caller_id,
                expression=callee,
                target_name=callee_name,
                lineno=lineno,
                col_offset=col_offset,
                status=STATUS_UNRESOLVED,
                reason=f"Call reference '{callee}' could not be uniquely resolved to a local definition",
            ),
            None,
        )

    def _resolve_js_call(
        self,
        call: dict[str, Any],
    ) -> tuple[Optional[str], Optional[UnresolvedReference], Optional[str]]:
        """JavaScript/TypeScript call resolution logic."""
        source_file = Path(call["file_path"]).as_posix()
        caller_id = call.get("caller_symbol_id")
        callee = call.get("callee", "")
        callee_name = call.get("callee_name") or callee.split(".")[-1]
        call_kind = call.get("call_kind", "function_call")
        lineno = call.get("lineno")
        col_offset = call.get("col_offset")
        file_scope = self.file_import_scopes.get(source_file, {})

        # Scope and shadowing check for unqualified calls
        if "." not in callee and not callee.startswith("new "):
            is_shadowed, nested_fn = self._is_name_shadowed_in_caller(
                source_file, caller_id, callee_name
            )
            if nested_fn:
                return (f"symbol:{nested_fn['id']}", None, "nested_function")
            if is_shadowed:
                return (
                    None,
                    UnresolvedReference(
                        kind="call",
                        source_file=source_file,
                        caller_id=caller_id,
                        expression=callee,
                        target_name=callee_name,
                        lineno=lineno,
                        col_offset=col_offset,
                        status=STATUS_UNRESOLVED,
                        reason=f"Local variable or parameter '{callee_name}' shadows symbol in scope",
                    ),
                    None,
                )

        # Strategy 1: JS built-ins (console.log, Math.max, fetch, setTimeout, etc.)
        root_ident = callee.replace("new ", "").split(".")[0].strip()
        if root_ident in JS_BUILTINS:
            return (
                None,
                UnresolvedReference(
                    kind="call",
                    source_file=source_file,
                    caller_id=caller_id,
                    expression=callee,
                    target_name=callee_name,
                    lineno=lineno,
                    col_offset=col_offset,
                    status=STATUS_EXTERNAL,
                    reason=f"Call to JavaScript built-in '{root_ident}'",
                ),
                None,
            )

        # Strategy 2: Constructor call (new PaymentService())
        if call_kind == "constructor_call" or callee.startswith("new "):
            target_class_name = callee_name
            # 2a. Same file class
            local_matches = self.symbols_by_file_and_name.get(
                (source_file, target_class_name), []
            )
            classes = [s for s in local_matches if s["kind"] == "class"]
            if len(classes) == 1:
                return (f"symbol:{classes[0]['id']}", None, "constructor_call")

            # 2b. Imported class
            if target_class_name in file_scope:
                entry = file_scope[target_class_name]
                if entry["type"] == "symbol" and entry["symbol"]["kind"] == "class":
                    return (
                        f"symbol:{entry['symbol']['id']}",
                        None,
                        "constructor_call",
                    )
                elif entry["type"] in ("external_symbol", "external_module"):
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=callee_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=STATUS_EXTERNAL,
                            reason=f"Constructor call to external dependency '{entry['module']}'",
                        ),
                        None,
                    )

        # Strategy 3: this.method() call
        if callee.startswith("this."):
            method_name = callee.split(".", 1)[1]
            caller_sym = self.symbols_by_id.get(caller_id or "")
            if caller_sym and caller_sym.get("parent_scope"):
                parent_class_name = caller_sym["parent_scope"].split(".")[-1]
                target_method = self._find_method_in_class(
                    source_file, parent_class_name, method_name
                )
                if target_method:
                    return (f"symbol:{target_method['id']}", None, "this_method")
                else:
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=method_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=STATUS_UNRESOLVED,
                            reason=f"Method '{method_name}' not defined on class '{parent_class_name}'",
                        ),
                        None,
                    )

        # Strategy 4: Uniquely defined function in the same file
        if "." not in callee and not callee.startswith("new "):
            caller_sym = self.symbols_by_id.get(caller_id or "")
            if caller_sym and caller_sym.get("parent_scope"):
                sibling_qname = f"{caller_sym['parent_scope']}.{callee_name}"
                if (source_file, sibling_qname) in self.symbols_by_file_and_qname:
                    sib = self.symbols_by_file_and_qname[(source_file, sibling_qname)]
                    if sib["kind"] in ("function", "async_function", "class"):
                        return (f"symbol:{sib['id']}", None, "same_module")

            if (source_file, callee_name) in self.symbols_by_file_and_qname:
                mod_sym = self.symbols_by_file_and_qname[(source_file, callee_name)]
                if mod_sym.get("parent_scope") is None and mod_sym["kind"] in (
                    "function",
                    "async_function",
                    "class",
                ):
                    return (f"symbol:{mod_sym['id']}", None, "same_module")

        # Strategy 5: Function imported by original name or alias
        if "." not in callee and not callee.startswith("new "):
            if callee in file_scope:
                entry = file_scope[callee]
                if entry["type"] == "symbol":
                    if entry["symbol"]["kind"] in (
                        "function",
                        "async_function",
                        "class",
                        "method",
                    ):
                        orig_name = entry["symbol"]["name"]
                        strategy = (
                            "imported_alias"
                            if callee != orig_name
                            else "imported_symbol"
                        )
                        return (f"symbol:{entry['symbol']['id']}", None, strategy)
                elif entry["type"] == "external_symbol":
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=callee_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=STATUS_EXTERNAL,
                            reason=f"Call to external package '{entry['module']}'",
                        ),
                        None,
                    )

        # Strategy 6: Namespace call (utilities.calculateTotal())
        if "." in callee and callee.count(".") == 1 and not callee.startswith("new "):
            ns_prefix, member = callee.split(".", 1)
            if ns_prefix in file_scope:
                entry = file_scope[ns_prefix]
                if entry["type"] == "namespace":
                    target_file = entry["target_file"]
                    exp_sym = self.find_exported_symbol(target_file, member)
                    if exp_sym and exp_sym["kind"] in (
                        "function",
                        "async_function",
                        "class",
                        "method",
                    ):
                        return (f"symbol:{exp_sym['id']}", None, "namespace_call")
                elif entry["type"] == "external_module":
                    return (
                        None,
                        UnresolvedReference(
                            kind="call",
                            source_file=source_file,
                            caller_id=caller_id,
                            expression=callee,
                            target_name=callee_name,
                            lineno=lineno,
                            col_offset=col_offset,
                            status=STATUS_EXTERNAL,
                            reason=f"Call to external package '{entry['module']}'",
                        ),
                        None,
                    )

        # Strategy 7: Member call on imported class/object (Service.method())
        if "." in callee and callee.count(".") == 1 and not callee.startswith("new "):
            qualifier, member = callee.split(".", 1)
            # 7a. Local class
            target_method = self._find_method_in_class(source_file, qualifier, member)
            if target_method:
                return (f"symbol:{target_method['id']}", None, "class_method")

            # 7b. Imported class
            if qualifier in file_scope and file_scope[qualifier]["type"] == "symbol":
                sym_entry = file_scope[qualifier]["symbol"]
                if sym_entry.get("kind") == "class":
                    target_method = self._find_method_in_class(
                        sym_entry["file_path"], sym_entry["name"], member
                    )
                    if target_method:
                        return (f"symbol:{target_method['id']}", None, "class_method")

        # Strategy 8: Dynamic member calls and computed property access
        if "." in callee or "[" in callee:
            return (
                None,
                UnresolvedReference(
                    kind="call",
                    source_file=source_file,
                    caller_id=caller_id,
                    expression=callee,
                    target_name=callee_name,
                    lineno=lineno,
                    col_offset=col_offset,
                    status=STATUS_UNRESOLVED,
                    reason=f"Unknown receiver type or dynamic call expression '{callee}'",
                ),
                None,
            )

        # Strategy 9: Ambiguity check across repository
        if "." not in callee and not callee.startswith("new "):
            repo_matches = self.symbols_by_name.get(callee_name, [])
            callable_matches = [
                s
                for s in repo_matches
                if s["kind"] in ("function", "async_function", "class")
            ]
            if len(callable_matches) > 1:
                candidate_ids = [f"symbol:{s['id']}" for s in callable_matches]
                return (
                    None,
                    UnresolvedReference(
                        kind="call",
                        source_file=source_file,
                        caller_id=caller_id,
                        expression=callee,
                        target_name=callee_name,
                        lineno=lineno,
                        col_offset=col_offset,
                        status=STATUS_AMBIGUOUS,
                        candidates=candidate_ids,
                        reason=f"Multiple candidate definitions found ({len(candidate_ids)}) without import or scope evidence",
                    ),
                    None,
                )

        return (
            None,
            UnresolvedReference(
                kind="call",
                source_file=source_file,
                caller_id=caller_id,
                expression=callee,
                target_name=callee_name,
                lineno=lineno,
                col_offset=col_offset,
                status=STATUS_UNRESOLVED,
                reason=f"Call reference '{callee}' could not be uniquely resolved to a local definition",
            ),
            None,
        )
