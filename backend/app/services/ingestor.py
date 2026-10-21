"""
Repository Ingestion Service.

Handles:
- Validating GitHub repository URLs
- Shallow git clone (depth=1) into an isolated temp workspace
- Directory traversal with noise filtering
- File metadata extraction (LOC, language, file size)
"""

from __future__ import annotations

import re
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from git import Repo as GitRepo

from app.config import settings

# ---------------------------------------------------------------------------
# Language detection by file extension
# ---------------------------------------------------------------------------

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyw": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cxx": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".hxx": "cpp",
    ".cs": "csharp",
    ".java": "java",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".scala": "scala",
    ".r": "r",
    ".R": "r",
    ".lua": "lua",
    ".sh": "shell",
    ".bash": "shell",
    ".zsh": "shell",
    ".ps1": "powershell",
    ".sql": "sql",
    ".html": "html",
    ".htm": "html",
    ".css": "css",
    ".scss": "scss",
    ".sass": "sass",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".xml": "xml",
    ".toml": "toml",
    ".md": "markdown",
    ".rst": "restructuredtext",
    ".txt": "text",
}

# ---------------------------------------------------------------------------
# Noise filters
# ---------------------------------------------------------------------------

_SKIP_DIRS: set[str] = {
    ".git",
    "node_modules",
    "venv",
    ".venv",
    "env",
    ".env",
    "__pycache__",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dist",
    "build",
    ".next",
    ".nuxt",
    "coverage",
    ".coverage",
    ".idea",
    ".vscode",
    ".vs",
    "vendor",
    "bower_components",
    "target",  # Rust/Java build output
}

_SKIP_FILES: set[str] = {
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "composer.lock",
    "Gemfile.lock",
    ".DS_Store",
    "Thumbs.db",
}

_BINARY_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".avi", ".mov", ".wmv", ".flv", ".wav", ".ogg",
    ".zip", ".tar", ".gz", ".bz2", ".7z", ".rar", ".xz",
    ".exe", ".dll", ".so", ".dylib", ".bin", ".obj", ".o",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".pyc", ".pyo", ".class", ".jar",
    ".db", ".sqlite", ".sqlite3",
    ".map",  # Source maps
}

# GitHub URL validation
_GITHUB_URL_RE = re.compile(
    r"^https?://github\.com/[\w.\-]+/[\w.\-]+(?:\.git)?/?$"
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class FileInfo:
    """Metadata about a single source file in the repository."""

    path: str         # Relative to repo root (forward slashes)
    language: str
    loc: int
    size_bytes: int


@dataclass
class RepoData:
    """Complete ingestion result for a cloned repository."""

    clone_path: Path
    repo_name: str
    repo_url: str
    branch: str
    commit_sha: str
    files: list[FileInfo] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_github_url(url: str) -> bool:
    """Check if the given URL is a valid GitHub repository URL."""
    return bool(_GITHUB_URL_RE.match(url.strip()))


def extract_repo_name(url: str) -> str:
    """Extract the repository name from a GitHub URL."""
    # Remove trailing .git and /
    clean = url.rstrip("/")
    if clean.endswith(".git"):
        clean = clean[:-4]
    return clean.split("/")[-1]


async def ingest_repository(
    repo_url: str,
    branch: str = "main",
) -> RepoData:
    """
    Clone and analyze a GitHub repository.

    1. Shallow-clone into an isolated temp directory
    2. Walk the file tree, filtering out noise
    3. Extract file metadata

    The caller is responsible for cleaning up clone_path when done.
    """
    repo_url = repo_url.strip()
    if not validate_github_url(repo_url):
        raise ValueError(f"Invalid GitHub repository URL: {repo_url}")

    repo_name = extract_repo_name(repo_url)

    # Create isolated temp directory
    base_dir = settings.clone_temp_dir
    base_dir.mkdir(parents=True, exist_ok=True)
    clone_dir = Path(tempfile.mkdtemp(prefix=f"{repo_name}_", dir=str(base_dir)))

    try:
        # Shallow clone
        git_repo = GitRepo.clone_from(
            repo_url,
            str(clone_dir),
            branch=branch,
            depth=1,
            single_branch=True,
        )

        # Get HEAD commit SHA
        commit_sha = str(git_repo.head.commit.hexsha)

        # Walk and collect files
        files = _collect_files(clone_dir)

        return RepoData(
            clone_path=clone_dir,
            repo_name=repo_name,
            repo_url=repo_url,
            branch=branch,
            commit_sha=commit_sha,
            files=files,
        )
    except Exception:
        # Clean up on failure
        cleanup_clone(clone_dir)
        raise


def cleanup_clone(clone_path: Path) -> None:
    """Remove a cloned repository directory."""
    if clone_path.exists():
        shutil.rmtree(str(clone_path), ignore_errors=True)


def ingest_local_directory(
    local_path: Path,
    repo_url: str = "https://github.com/local/repo",
    branch: str = "main",
) -> RepoData:
    """Ingest and analyze a local directory (e.g. extracted zip archive)."""
    repo_name = extract_repo_name(repo_url)
    files = _collect_files(local_path)
    return RepoData(
        clone_path=local_path,
        repo_name=repo_name,
        repo_url=repo_url,
        branch=branch,
        commit_sha="local",
        files=files,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _should_skip_dir(dir_name: str) -> bool:
    """Check if a directory should be skipped during traversal."""
    return dir_name in _SKIP_DIRS or dir_name.startswith(".")


def _should_skip_file(file_name: str, extension: str) -> bool:
    """Check if a file should be skipped during traversal."""
    if file_name in _SKIP_FILES:
        return True
    if extension in _BINARY_EXTENSIONS:
        return True
    return False


def _detect_language(extension: str) -> str:
    """Map a file extension to a language name."""
    return _EXTENSION_TO_LANGUAGE.get(extension.lower(), "unknown")


def _count_loc(file_path: Path) -> int:
    """Count non-empty lines in a text file."""
    try:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        return len([line for line in text.splitlines() if line.strip()])
    except Exception:
        return 0


def _collect_files(clone_dir: Path) -> list[FileInfo]:
    """Walk the cloned repo and collect file metadata, filtering noise."""
    files: list[FileInfo] = []

    for item in clone_dir.rglob("*"):
        # Skip noise directories — check all parent parts
        rel = item.relative_to(clone_dir)
        if any(_should_skip_dir(part) for part in rel.parts[:-1]):
            continue

        if not item.is_file():
            continue

        ext = item.suffix
        if _should_skip_file(item.name, ext):
            continue

        language = _detect_language(ext)
        loc = _count_loc(item)
        size_bytes = item.stat().st_size

        # Use forward slashes for cross-platform consistency
        rel_path = str(rel).replace("\\", "/")

        files.append(
            FileInfo(
                path=rel_path,
                language=language,
                loc=loc,
                size_bytes=size_bytes,
            )
        )

    return sorted(files, key=lambda f: f.path)
