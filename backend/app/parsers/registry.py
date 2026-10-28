"""Parser registry: the single place that maps languages to analysis runners.

Adding a language means writing an adapter (see ``common.AdapterSpec``) and appending one
``ParserSpec`` here; the pipeline, indexing job, symbol search and diagnostics iterate this list.
Each runner reads the scanner inventory and writes ``<key>_analysis.json`` in the shared layout
(``symbols``, ``imports``, ``exports``, ``calls``, ``relations``, ``parse_errors``, ``summary``).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

Runner = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ParserSpec:
    key: str  # stage/summary key and analysis file prefix
    stage: str  # progress stage name reported to the job
    languages: tuple[str, ...]  # scanner language names handled
    run: Runner  # (inventory_path=, repo_root=, output_path=) -> analysis dict

    @property
    def filename(self) -> str:
        return f"{self.key}_analysis.json"


def _python() -> Runner:
    from app.parsers.python_parser import parse_repository_inventory

    return parse_repository_inventory


def _javascript() -> Runner:
    from app.parsers.javascript_parser import parse_js_repository_inventory

    return parse_js_repository_inventory


def _java() -> Runner:
    from app.parsers.java_parser import parse_java_repository_inventory

    return parse_java_repository_inventory


def _kotlin() -> Runner:
    from app.parsers.kotlin_parser import parse_kotlin_repository_inventory

    return parse_kotlin_repository_inventory


def _rust() -> Runner:
    from app.parsers.rust_parser import parse_rust_repository_inventory

    return parse_rust_repository_inventory


class _Lazy:
    """Defer importing a grammar until its runner is actually used."""

    def __init__(self, factory: Callable[[], Runner]) -> None:
        self._factory = factory

    def __call__(self, **kwargs: Any) -> dict[str, Any]:
        return self._factory()(**kwargs)


# JSX is handled by the JavaScript grammar and TSX by tree-sitter-typescript's TSX grammar
# (selected by file extension inside javascript_parser.get_language_and_parser).
PARSER_SPECS: tuple[ParserSpec, ...] = (
    ParserSpec("python", "parsing_python", ("Python",), _Lazy(_python)),
    ParserSpec("javascript", "parsing_javascript", ("JavaScript", "TypeScript"), _Lazy(_javascript)),
    ParserSpec("java", "parsing_java", ("Java",), _Lazy(_java)),
    ParserSpec("kotlin", "parsing_kotlin", ("Kotlin",), _Lazy(_kotlin)),
    ParserSpec("rust", "parsing_rust", ("Rust",), _Lazy(_rust)),
)

PARSER_BY_LANGUAGE: dict[str, ParserSpec] = {lang: spec for spec in PARSER_SPECS for lang in spec.languages}
ANALYSIS_FILENAMES: tuple[str, ...] = tuple(spec.filename for spec in PARSER_SPECS)


def spec_for_language(language: Optional[str]) -> Optional[ParserSpec]:
    """Return the parser handling a scanner language name (each language maps to exactly one parser)."""
    return PARSER_BY_LANGUAGE.get(language or "")


def analysis_paths(artifact_dir: Path) -> list[Path]:
    return [artifact_dir / name for name in ANALYSIS_FILENAMES]
