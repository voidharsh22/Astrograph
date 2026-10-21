"""Application configuration loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Central configuration — reads from .env or environment variables."""

    app_env: Literal["development", "staging", "production"] = "development"
    app_version: str = "0.1.0"

    # Database & Storage
    database_url: str = "sqlite+aiosqlite:///./astral.db"
    data_dir: Path = Path("./data")
    db_path: Path = Path("./data/astral.db")

    # Security & Archive Limits
    max_archive_mb: int = 100
    max_extracted_mb: int = 500
    max_single_file_mb: int = 25
    max_files: int = 20000
    max_concurrent_jobs: int = 2

    # Google Gemini (Phase 3+)
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"

    # GitHub (Phase 2+)
    github_token: str = ""

    # Temp storage for shallow clones
    clone_temp_dir: Path = Path("./tmp/clones")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


# Singleton — import this everywhere
settings = Settings()
