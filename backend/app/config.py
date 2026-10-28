"""Configuration settings for Astral Cartographer backend."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

# backend/.env, resolved from this file so it loads regardless of the working directory.
# Real environment variables take precedence over the file (override=False).
ENV_FILE: Path = Path(__file__).resolve().parents[1] / ".env"
ENV_FILE_LOADED: bool = load_dotenv(ENV_FILE, override=False) if ENV_FILE.exists() else False


class Settings:
    """Application settings loaded from environment variables with safe defaults."""

    def __init__(self) -> None:
        # Base Data Directory
        raw_data_dir = os.environ.get("ASTRAL_DATA_DIR", "data")
        self.data_dir: Path = Path(raw_data_dir).resolve()

        # Ingestion and Archive Limits
        self.max_archive_mb: int = int(os.environ.get("ASTRAL_MAX_ARCHIVE_MB", "100"))
        self.max_extracted_mb: int = int(os.environ.get("ASTRAL_MAX_EXTRACTED_MB", "500"))
        self.max_files: int = int(os.environ.get("ASTRAL_MAX_FILES", "20000"))
        self.max_single_file_mb: int = int(
            os.environ.get("ASTRAL_MAX_SINGLE_FILE_MB", "20")
        )

        # Source File Response Limits
        self.max_source_response_mb: int = int(
            os.environ.get("ASTRAL_MAX_SOURCE_RESPONSE_MB", "1")
        )

        # Concurrency Limits
        self.max_concurrent_jobs: int = int(
            os.environ.get("ASTRAL_MAX_CONCURRENT_JOBS", "2")
        )

        # CORS Allowed Origins
        raw_cors = os.environ.get(
            "ASTRAL_CORS_ORIGINS",
            "http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173,http://[::1]:3000,http://[::1]:5173",
        )
        self.cors_origins: list[str] = [
            origin.strip() for origin in raw_cors.split(",") if origin.strip()
        ]

        # Server Host and Port
        self.host: str = os.environ.get("ASTRAL_HOST", "127.0.0.1")
        self.port: int = int(os.environ.get("ASTRAL_PORT", "8000"))

        # AI and Gemini Configuration
        self.gemini_api_key: str = os.environ.get("GEMINI_API_KEY", "")
        self.gemini_model: str = os.environ.get("GEMINI_MODEL", "gemini-3.1-flash-lite")

        # Astral AI Copilot (Anthropic Claude) - key stays server-side, never sent to the browser
        self.anthropic_api_key: str = os.environ.get("ANTHROPIC_API_KEY", "")
        self.anthropic_model: str = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-5-5")

        # Provider selection: "gemini" | "anthropic" | "" (auto: first provider with a key)
        self.ai_provider: str = os.environ.get("AI_PROVIDER", "").strip().lower()
        self.ai_timeout_seconds: float = float(os.environ.get("AI_TIMEOUT_SECONDS", "60"))
        self.ai_max_output_tokens: int = int(os.environ.get("AI_MAX_OUTPUT_TOKENS", "2048"))
        self.ai_max_context_chars: int = int(os.environ.get("AI_MAX_CONTEXT_CHARS", "24000"))

        # GitHub App (private repository access). All optional: public imports never need these.
        self.github_app_id: str = os.environ.get("GITHUB_APP_ID", "").strip()
        self.github_app_slug: str = os.environ.get("GITHUB_APP_SLUG", "").strip()
        self.github_app_client_id: str = os.environ.get("GITHUB_APP_CLIENT_ID", "").strip()
        self.github_app_client_secret: str = os.environ.get("GITHUB_APP_CLIENT_SECRET", "").strip()
        self.github_app_private_key: str = os.environ.get("GITHUB_APP_PRIVATE_KEY", "").replace("\\n", "\n").strip()
        self.github_app_private_key_path: str = os.environ.get("GITHUB_APP_PRIVATE_KEY_PATH", "").strip()
        # Origin of this backend as GitHub reaches it (OAuth callback) and of the web UI (post-login redirect).
        self.public_backend_url: str = os.environ.get("ASTRAL_PUBLIC_BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
        self.frontend_url: str = os.environ.get("ASTRAL_FRONTEND_URL", "http://localhost:5173").rstrip("/")
        self.github_session_ttl_minutes: int = int(os.environ.get("ASTRAL_GITHUB_SESSION_TTL_MINUTES", "480"))
        # Account authentication (email/password + Google OpenID Connect). Credentials stay server-side.
        self.google_client_id: str = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
        self.google_client_secret: str = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
        self._google_redirect_uri: str = os.environ.get("GOOGLE_REDIRECT_URI", "").strip()
        self.session_days: int = int(os.environ.get("ASTRAL_SESSION_DAYS", "7"))

        # Private source is never sent to Gemini/Anthropic unless the operator opts in.
        self.allow_ai_on_private_repos: bool = os.environ.get(
            "ASTRAL_ALLOW_AI_ON_PRIVATE_REPOS", "false"
        ).strip().lower() in ("1", "true", "yes")

    @property
    def google_redirect_uri(self) -> str:
        """Must match an "Authorized redirect URI" in Google Cloud Console exactly."""
        return self._google_redirect_uri or f"{self.frontend_url}/api/auth/google/callback"

    @property
    def cookies_secure(self) -> bool:
        return self.frontend_url.startswith("https://")

    @property
    def db_path(self) -> Path:
        """Absolute path to the SQLite database file."""
        return self.data_dir / "astral.db"

    @property
    def repositories_dir(self) -> Path:
        """Absolute path to the directory storing repository workspaces."""
        return self.data_dir / "repositories"

    def get_repo_dir(self, repo_id: str) -> Path:
        """Return the root directory for a specific indexed repository."""
        return self.repositories_dir / repo_id

    def get_repo_source_dir(self, repo_id: str) -> Path:
        """Return the extracted source directory for a specific repository."""
        return self.get_repo_dir(repo_id) / "source"

    def get_repo_artifact_dir(self, repo_id: str) -> Path:
        """Return the artifacts directory for a specific repository."""
        return self.get_repo_dir(repo_id) / "artifacts"

    def ensure_directories(self) -> None:
        """Ensure all required base directories exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.repositories_dir.mkdir(parents=True, exist_ok=True)


# Global settings singleton
settings = Settings()
