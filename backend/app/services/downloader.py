"""
Safe streaming GitHub archive downloader with redirect and size constraints.
"""

from __future__ import annotations

import logging
from pathlib import Path
import re
from typing import Optional
from urllib.parse import urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

ALLOWED_ARCHIVE_HOSTS: frozenset[str] = frozenset(
    {"github.com", "codeload.github.com"}
)


def extract_github_owner_and_repo(url: str) -> tuple[str, str]:
    """Parse and validate canonical owner and repository name from a GitHub HTTPS URL."""
    parsed = urlparse(url.strip())
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS GitHub URLs are supported")
    if parsed.netloc.lower() != "github.com":
        raise ValueError("Only repositories hosted on github.com are supported")

    clean_path = parsed.path.strip("/")
    if clean_path.endswith(".git"):
        clean_path = clean_path[:-4]

    segments = [s for s in clean_path.split("/") if s]
    if len(segments) != 2:
        raise ValueError("Invalid GitHub repository URL structure")

    owner, repo = segments
    valid_name = re.compile(r"^[a-zA-Z0-9_.-]+$")
    if not valid_name.match(owner) or not valid_name.match(repo):
        raise ValueError("Repository owner or name contains invalid characters")

    return owner, repo


def download_github_archive(
    url: str,
    branch: str,
    dest_path: Path,
    max_bytes: Optional[int] = None,
    timeout_secs: float = 30.0,
) -> None:
    """Download public GitHub repository zip archive securely and stream to disk.

    Args:
        url: Validated GitHub repository URL.
        branch: Target branch name.
        dest_path: Destination zip file path.
        max_bytes: Maximum allowed archive size in bytes.
        timeout_secs: Network timeout in seconds.

    Raises:
        ValueError: For not found or invalid repository/branch or exceeded limit.
        RuntimeError: For network or server errors.
    """
    owner, repo = extract_github_owner_and_repo(url)
    max_allowed = max_bytes or (settings.max_archive_mb * 1024 * 1024)

    dest_path.parent.mkdir(parents=True, exist_ok=True)

    current_url = f"https://codeload.github.com/{owner}/{repo}/zip/refs/heads/{branch}"
    max_redirects = 3
    redirect_count = 0

    client_timeout = httpx.Timeout(timeout_secs, connect=10.0)

    try:
        with httpx.Client(timeout=client_timeout, follow_redirects=False) as client:
            while redirect_count <= max_redirects:
                parsed_url = urlparse(current_url)
                if parsed_url.scheme != "https":
                    raise ValueError(f"Insecure redirect scheme: {parsed_url.scheme}")
                if parsed_url.netloc.lower() not in ALLOWED_ARCHIVE_HOSTS:
                    raise ValueError(
                        f"Refusing redirect to untrusted host: {parsed_url.netloc}"
                    )

                with client.stream("GET", current_url) as response:
                    if response.status_code in (301, 302, 307, 308):
                        redirect_count += 1
                        location = response.headers.get("location")
                        if not location:
                            raise RuntimeError("Redirect missing Location header")
                        if location.startswith("/"):
                            current_url = f"https://{parsed_url.netloc}{location}"
                        else:
                            current_url = location
                        continue

                    if response.status_code == 404:
                        raise ValueError(
                            f"Repository '{owner}/{repo}' or branch '{branch}' was not found on GitHub"
                        )
                    if response.status_code in (403, 429):
                        raise RuntimeError(
                            "GitHub rate limit exceeded or access to archive was forbidden"
                        )
                    if response.status_code != 200:
                        raise RuntimeError(
                            f"GitHub returned HTTP status {response.status_code} while downloading archive"
                        )

                    total_bytes = 0
                    with open(dest_path, "wb") as f:
                        for chunk in response.iter_bytes(chunk_size=65536):
                            total_bytes += len(chunk)
                            if total_bytes > max_allowed:
                                dest_path.unlink(missing_ok=True)
                                raise ValueError(
                                    f"Archive exceeded maximum allowed size of {max_allowed // (1024 * 1024)} MB"
                                )
                            f.write(chunk)

                    return

            raise RuntimeError("Exceeded maximum allowed redirects downloading archive")

    except (httpx.TimeoutException, httpx.NetworkError) as err:
        dest_path.unlink(missing_ok=True)
        raise RuntimeError(f"Network error downloading repository archive: {err}") from err
    except Exception:
        dest_path.unlink(missing_ok=True)
        raise
