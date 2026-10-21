"""
JavaScript / TypeScript regex-based source code parser.

Extracts:
- Import statements: import ... from '...', import('...'), require('...')
- Function declarations (function, arrow functions assigned to const/let/var)
- Class declarations with extends (inheritance)
- Export default function/class
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath

from app.services.parsers.base import BaseParser, ParsedImport, ParsedSymbol, ParseResult

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# import Foo from './bar'  |  import { Foo, Bar } from './bar'  |  import './bar'
_IMPORT_FROM_RE = re.compile(
    r"""import\s+(?:(?:[\w*{}\s,]+)\s+from\s+)?['"]([^'"]+)['"]""",
    re.MULTILINE,
)

# const foo = require('./bar')  |  require('./bar')
_REQUIRE_RE = re.compile(
    r"""require\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# Dynamic import: import('./bar')
_DYNAMIC_IMPORT_RE = re.compile(
    r"""import\s*\(\s*['"]([^'"]+)['"]\s*\)""",
    re.MULTILINE,
)

# function foo(...)  |  async function foo(...)
_FUNCTION_DECL_RE = re.compile(
    r"""(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s+(\w+)""",
    re.MULTILINE,
)

# const foo = (...) =>  |  const foo = function(  |  let foo = async (
_ARROW_FUNC_RE = re.compile(
    r"""(?:export\s+(?:default\s+)?)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\([^)]*\)|[\w]+)\s*=>""",
    re.MULTILINE,
)

# class Foo  |  class Foo extends Bar  |  export default class Foo
_CLASS_DECL_RE = re.compile(
    r"""(?:export\s+(?:default\s+)?)?class\s+(\w+)(?:\s+extends\s+(\w+))?""",
    re.MULTILINE,
)

# JS/TS file extension resolution order
_JS_EXTENSIONS = [".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"]


class JSParser(BaseParser):
    """Parses JavaScript and TypeScript source files using regex patterns."""

    @property
    def supported_extensions(self) -> set[str]:
        return {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

    def parse_file(
        self, file_path: str, source_code: str, repo_files: set[str]
    ) -> ParseResult:
        loc = len([line for line in source_code.splitlines() if line.strip()])
        lang = "typescript" if file_path.endswith((".ts", ".tsx")) else "javascript"

        symbols = self._extract_symbols(source_code)
        imports = self._extract_imports(source_code, file_path, repo_files)

        return ParseResult(
            file_path=file_path,
            language=lang,
            symbols=symbols,
            imports=imports,
            loc=loc,
        )

    def _extract_symbols(self, source: str) -> list[ParsedSymbol]:
        symbols: list[ParsedSymbol] = []
        seen_names: set[str] = set()

        # Functions (named declarations)
        for m in _FUNCTION_DECL_RE.finditer(source):
            name = m.group(1)
            if name not in seen_names:
                line = source[: m.start()].count("\n") + 1
                symbols.append(
                    ParsedSymbol(name=name, kind="function", line_start=line, line_end=line)
                )
                seen_names.add(name)

        # Arrow functions / function expressions assigned to variables
        for m in _ARROW_FUNC_RE.finditer(source):
            name = m.group(1)
            if name not in seen_names:
                line = source[: m.start()].count("\n") + 1
                symbols.append(
                    ParsedSymbol(name=name, kind="function", line_start=line, line_end=line)
                )
                seen_names.add(name)

        # Classes
        for m in _CLASS_DECL_RE.finditer(source):
            name = m.group(1)
            bases = [m.group(2)] if m.group(2) else []
            line = source[: m.start()].count("\n") + 1
            symbols.append(
                ParsedSymbol(
                    name=name, kind="class", line_start=line, line_end=line, bases=bases
                )
            )

        return symbols

    def _extract_imports(
        self, source: str, file_path: str, repo_files: set[str]
    ) -> list[ParsedImport]:
        imports: list[ParsedImport] = []
        seen_paths: set[str] = set()

        all_specifiers: list[str] = []
        all_specifiers.extend(m.group(1) for m in _IMPORT_FROM_RE.finditer(source))
        all_specifiers.extend(m.group(1) for m in _REQUIRE_RE.finditer(source))
        all_specifiers.extend(m.group(1) for m in _DYNAMIC_IMPORT_RE.finditer(source))

        for spec in all_specifiers:
            if spec in seen_paths:
                continue
            seen_paths.add(spec)

            resolved = self._resolve_js_import(spec, file_path, repo_files)
            imports.append(
                ParsedImport(
                    raw_statement=spec,
                    resolved_path=resolved,
                    imported_names=[],
                )
            )

        return imports

    def _resolve_js_import(
        self, specifier: str, current_file: str, repo_files: set[str]
    ) -> str | None:
        """Resolve a JS/TS import specifier to a file path within the repo."""
        # Only resolve relative imports (./  ../)
        if not specifier.startswith("."):
            return None

        current_dir = PurePosixPath(current_file.replace("\\", "/")).parent
        target = str((current_dir / specifier).as_posix())

        # Normalize (remove trailing segments like ..)
        # PurePosixPath doesn't resolve .., so we do it manually
        parts = target.split("/")
        resolved_parts: list[str] = []
        for p in parts:
            if p == "..":
                if resolved_parts:
                    resolved_parts.pop()
            elif p != ".":
                resolved_parts.append(p)
        target = "/".join(resolved_parts)

        # Try exact match first
        if target in repo_files:
            return target

        # Try with extensions
        for ext in _JS_EXTENSIONS:
            candidate = f"{target}{ext}"
            if candidate in repo_files:
                return candidate

        # Try as directory with index file
        for ext in _JS_EXTENSIONS:
            candidate = f"{target}/index{ext}"
            if candidate in repo_files:
                return candidate

        return None
