"""Data models representing extracted AST structures for Astral Cartographer."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Symbol:
    """Represents a code symbol (function, method, class, interface, enum, etc.) extracted from AST."""

    id: str
    name: str
    qualified_name: str
    kind: str  # "function", "async_function", "method", "class", "interface", "type_alias", "enum", "constructor"
    file_path: str
    lineno: int
    end_lineno: int
    col_offset: int
    parent_scope: Optional[str] = None
    parameters: Optional[list[str]] = None
    signature: Optional[str] = None
    decorators: list[str] = field(default_factory=list)
    bases: Optional[list[str]] = None
    is_async: bool = False
    language: str = "python"
    is_exported: bool = False
    local_variables: list[str] = field(default_factory=list)
    # Package / module path (Java/Kotlin package, Rust module path). None for languages without one.
    namespace: Optional[str] = None
    # Kotlin extension receiver type or Rust impl target, when different from the lexical parent.
    receiver_type: Optional[str] = None
    end_col_offset: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert symbol to dictionary suitable for JSON serialization."""
        data = {
            "id": self.id,
            "name": self.name,
            "qualified_name": self.qualified_name,
            "kind": self.kind,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "end_lineno": self.end_lineno,
            "col_offset": self.col_offset,
            "parent_scope": self.parent_scope,
            "parameters": self.parameters,
            "signature": self.signature,
            "decorators": self.decorators,
            "bases": self.bases,
            "is_async": self.is_async,
            "language": self.language,
            "is_exported": self.is_exported,
            "local_variables": self.local_variables,
        }
        # Optional fields are only emitted when set so Python/JS/TS output is unchanged.
        for key in ("namespace", "receiver_type", "end_col_offset"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        return data


@dataclass
class Import:
    """Represents an imported module or symbol."""

    module: Optional[str]
    name: str
    alias: Optional[str]
    file_path: str
    lineno: int
    col_offset: int
    level: int = 0
    import_form: str = "named"  # "default", "named", "namespace", "side_effect", "type_only"
    is_type_only: bool = False
    language: str = "python"

    def to_dict(self) -> dict[str, Any]:
        """Convert import statement to dictionary suitable for JSON serialization."""
        return {
            "module": self.module,
            "name": self.name,
            "alias": self.alias,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "level": self.level,
            "import_form": self.import_form,
            "is_type_only": self.is_type_only,
            "language": self.language,
        }


@dataclass
class Export:
    """Represents an exported symbol, declaration, or re-export."""

    name: str
    file_path: str
    lineno: int
    col_offset: int
    alias: Optional[str] = None
    is_default: bool = False
    is_reexport: bool = False
    source_module: Optional[str] = None
    is_type_only: bool = False
    language: str = "javascript"

    def to_dict(self) -> dict[str, Any]:
        """Convert export statement to dictionary suitable for JSON serialization."""
        return {
            "name": self.name,
            "alias": self.alias,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "is_default": self.is_default,
            "is_reexport": self.is_reexport,
            "source_module": self.source_module,
            "is_type_only": self.is_type_only,
            "language": self.language,
        }


@dataclass
class Call:
    """Represents a function or method call expression."""

    callee: str
    callee_name: Optional[str]
    file_path: str
    lineno: int
    col_offset: int
    caller: Optional[str] = None
    caller_symbol_id: Optional[str] = None
    is_module_level: bool = True
    call_kind: str = "function_call"  # "function_call", "method_call", "constructor_call", "macro_call"
    language: str = "python"
    # Statically inferred receiver type name (simple or qualified as written) and argument count,
    # used for method/overload resolution in Java, Kotlin and Rust.
    receiver_type: Optional[str] = None
    arg_count: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        """Convert call expression to dictionary suitable for JSON serialization."""
        data = {
            "callee": self.callee,
            "callee_name": self.callee_name,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "caller": self.caller,
            "caller_symbol_id": self.caller_symbol_id,
            "is_module_level": self.is_module_level,
            "call_kind": self.call_kind,
            "language": self.language,
        }
        for key in ("receiver_type", "arg_count"):
            if getattr(self, key) is not None:
                data[key] = getattr(self, key)
        return data


@dataclass
class Relation:
    """A type-level relationship found in source: inheritance or JSX component usage.

    kind: "extends", "implements" or "renders". The source is a symbol (``source_symbol_id``)
    or, for module-level usage, the file. ``target`` is the name as written in the source.
    """

    kind: str
    target: str
    file_path: str
    lineno: int
    col_offset: int
    source_symbol_id: Optional[str] = None
    language: str = "python"
    # Type name as written when the source symbol is not known to the parser (Rust `impl Trait for Type`).
    source_name: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_name": self.source_name,
            "kind": self.kind,
            "target": self.target,
            "file_path": self.file_path,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "source_symbol_id": self.source_symbol_id,
            "language": self.language,
        }


@dataclass
class ParseError:
    """Represents a syntax, decoding, or filesystem error encountered during parsing."""

    file_path: str
    lineno: Optional[int]
    col_offset: Optional[int]
    error_message: str

    def to_dict(self) -> dict[str, Any]:
        """Convert parse error to dictionary suitable for JSON serialization."""
        return {
            "file_path": self.file_path,
            "lineno": self.lineno,
            "col_offset": self.col_offset,
            "error_message": self.error_message,
        }


@dataclass
class ParseSummary:
    """Aggregated statistics for a Python parsing run across files."""

    python_files_discovered: int = 0
    python_files_parsed: int = 0
    python_files_with_errors: int = 0
    symbols_found: int = 0
    imports_found: int = 0
    calls_found: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert summary metrics to dictionary."""
        return {
            "python_files_discovered": self.python_files_discovered,
            "python_files_parsed": self.python_files_parsed,
            "python_files_with_errors": self.python_files_with_errors,
            "symbols_found": self.symbols_found,
            "imports_found": self.imports_found,
            "calls_found": self.calls_found,
        }


@dataclass
class JSParseSummary:
    """Aggregated statistics for a JavaScript/TypeScript parsing run."""

    javascript_files_discovered: int = 0
    javascript_files_parsed: int = 0
    typescript_files_discovered: int = 0
    typescript_files_parsed: int = 0
    files_with_errors: int = 0
    symbols_found: int = 0
    imports_found: int = 0
    exports_found: int = 0
    calls_found: int = 0

    def to_dict(self) -> dict[str, int]:
        """Convert summary metrics to dictionary."""
        return {
            "javascript_files_discovered": self.javascript_files_discovered,
            "javascript_files_parsed": self.javascript_files_parsed,
            "typescript_files_discovered": self.typescript_files_discovered,
            "typescript_files_parsed": self.typescript_files_parsed,
            "files_with_errors": self.files_with_errors,
            "symbols_found": self.symbols_found,
            "imports_found": self.imports_found,
            "exports_found": self.exports_found,
            "calls_found": self.calls_found,
        }


@dataclass
class FileParseResult:
    """Analysis results for an individual source file."""

    file_path: str
    symbols: list[Symbol] = field(default_factory=list)
    imports: list[Import] = field(default_factory=list)
    calls: list[Call] = field(default_factory=list)
    exports: list[Export] = field(default_factory=list)
    relations: list[Relation] = field(default_factory=list)
    errors: list[ParseError] = field(default_factory=list)
