"""
Abstract base class for language-specific source code parsers.

Each parser extracts structural elements (functions, classes) and
dependency edges (imports, inheritance) from source files.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ParsedSymbol:
    """A function, class, or other named symbol extracted from source code."""

    name: str
    kind: str  # "function" | "class"
    line_start: int
    line_end: int
    # For classes: list of base class names (for inheritance edges)
    bases: list[str] = field(default_factory=list)


@dataclass
class ParsedImport:
    """A resolved import statement."""

    raw_statement: str        # Original import text (e.g. "from .utils import foo")
    resolved_path: str | None  # Resolved relative file path, or None if external
    imported_names: list[str]  # Specific names imported (empty = whole module)


@dataclass
class ParsedCall:
    """A function/method invocation extracted from source code."""

    callee_name: str
    line: int
    caller_name: str | None = None


@dataclass
class ParseResult:
    """Complete parse output for a single source file."""

    file_path: str
    language: str
    symbols: list[ParsedSymbol] = field(default_factory=list)
    imports: list[ParsedImport] = field(default_factory=list)
    calls: list[ParsedCall] = field(default_factory=list)
    loc: int = 0


class BaseParser(ABC):
    """Interface that all language-specific parsers must implement."""

    @property
    @abstractmethod
    def supported_extensions(self) -> set[str]:
        """File extensions this parser handles (e.g. {'.py'})."""
        ...

    @abstractmethod
    def parse_file(self, file_path: str, source_code: str, repo_files: set[str]) -> ParseResult:
        """
        Parse a source file and extract symbols + imports.

        Args:
            file_path: Relative path from the repo root.
            source_code: The full file content as a string.
            repo_files: Set of all relative file paths in the repo
                        (used to resolve imports to internal files).

        Returns:
            A ParseResult containing extracted symbols and imports.
        """
        ...
