"""Tests for the repository ingestor service."""

from __future__ import annotations

import pytest

from app.services.ingestor import (
    FileInfo,
    _collect_files,
    _detect_language,
    _should_skip_dir,
    _should_skip_file,
    extract_repo_name,
    validate_github_url,
)


class TestGitHubUrlValidation:
    """URL validation tests."""

    def test_valid_https_url(self) -> None:
        assert validate_github_url("https://github.com/owner/repo")

    def test_valid_https_url_with_git(self) -> None:
        assert validate_github_url("https://github.com/owner/repo.git")

    def test_valid_https_url_with_trailing_slash(self) -> None:
        assert validate_github_url("https://github.com/owner/repo/")

    def test_valid_url_with_dots_and_dashes(self) -> None:
        assert validate_github_url("https://github.com/my-org/my-repo.js")

    def test_rejects_non_github_url(self) -> None:
        assert not validate_github_url("https://gitlab.com/owner/repo")

    def test_rejects_plain_string(self) -> None:
        assert not validate_github_url("not-a-url")

    def test_rejects_empty(self) -> None:
        assert not validate_github_url("")


class TestRepoNameExtraction:
    """Repo name extraction tests."""

    def test_basic_url(self) -> None:
        assert extract_repo_name("https://github.com/pallets/flask") == "flask"

    def test_url_with_git_suffix(self) -> None:
        assert extract_repo_name("https://github.com/pallets/flask.git") == "flask"

    def test_url_with_trailing_slash(self) -> None:
        assert extract_repo_name("https://github.com/pallets/flask/") == "flask"


class TestNoiseFiltering:
    """Tests for directory and file skip logic."""

    def test_skip_node_modules(self) -> None:
        assert _should_skip_dir("node_modules")

    def test_skip_git(self) -> None:
        assert _should_skip_dir(".git")

    def test_skip_pycache(self) -> None:
        assert _should_skip_dir("__pycache__")

    def test_skip_dotdirs(self) -> None:
        assert _should_skip_dir(".mypy_cache")

    def test_allow_normal_dirs(self) -> None:
        assert not _should_skip_dir("src")
        assert not _should_skip_dir("app")

    def test_skip_lockfiles(self) -> None:
        assert _should_skip_file("package-lock.json", ".json")
        assert _should_skip_file("poetry.lock", ".lock")

    def test_skip_binary_files(self) -> None:
        assert _should_skip_file("logo.png", ".png")
        assert _should_skip_file("font.woff2", ".woff2")

    def test_allow_source_files(self) -> None:
        assert not _should_skip_file("main.py", ".py")
        assert not _should_skip_file("app.tsx", ".tsx")


class TestLanguageDetection:
    """Tests for file extension to language mapping."""

    def test_python(self) -> None:
        assert _detect_language(".py") == "python"

    def test_javascript(self) -> None:
        assert _detect_language(".js") == "javascript"

    def test_typescript(self) -> None:
        assert _detect_language(".ts") == "typescript"

    def test_unknown(self) -> None:
        assert _detect_language(".xyz") == "unknown"
