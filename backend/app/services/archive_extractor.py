"""
Safe zip archive extraction preventing zip-slip, symlinks, and zip bombs.
"""

from __future__ import annotations

import logging
from pathlib import Path
import shutil
from typing import Optional
import zipfile

from app.config import settings

logger = logging.getLogger(__name__)


def is_symlink_zip_entry(info: zipfile.ZipInfo) -> bool:
    """Detect if a ZipInfo entry represents a UNIX symbolic link."""
    mode = info.external_attr >> 16
    return (mode & 0o120000) == 0o120000


def extract_archive_safely(
    zip_path: Path,
    target_source_dir: Path,
    max_extracted_bytes: Optional[int] = None,
    max_files: Optional[int] = None,
    max_single_file_bytes: Optional[int] = None,
) -> int:
    """Safely extract a repository zip archive into target_source_dir.

    Strips any GitHub root wrapper directory so repository contents
    reside directly at target_source_dir.

    Args:
        zip_path: Path to local zip archive.
        target_source_dir: Target directory for extracted contents.
        max_extracted_bytes: Maximum total uncompressed bytes permitted.
        max_files: Maximum number of files permitted.
        max_single_file_bytes: Maximum uncompressed bytes for any single file.

    Returns:
        Number of files successfully extracted.

    Raises:
        ValueError: On unsafe path traversal, zip bombs, or limit violations.
    """
    resolved_target = target_source_dir.resolve()
    resolved_target.mkdir(parents=True, exist_ok=True)

    max_total = max_extracted_bytes or (settings.max_extracted_mb * 1024 * 1024)
    file_limit = max_files or settings.max_files
    max_single = max_single_file_bytes or (settings.max_single_file_mb * 1024 * 1024)

    total_extracted_bytes = 0
    extracted_file_count = 0

    try:
        with zipfile.ZipFile(zip_path, "r") as zf:
            members = zf.infolist()

            # Determine GitHub top-level wrapper directory if present
            wrapper_prefix = ""
            valid_names = [m.filename for m in members if not m.is_dir()]
            if valid_names:
                parts_list = [p.replace("\\", "/").split("/") for p in valid_names]
                first_segment = parts_list[0][0]
                if not first_segment.startswith(".") and all(parts[0] == first_segment for parts in parts_list if len(parts) > 1):
                    wrapper_prefix = f"{first_segment}/"

            for info in members:
                # 1. Skip symlinks
                if is_symlink_zip_entry(info):
                    logger.warning("Skipping symbolic link archive entry: %s", info.filename)
                    continue

                raw_name = info.filename.replace("\\", "/")

                # Path traversal check on raw name first
                raw_parts = Path(raw_name).parts
                if ".." in raw_parts or ".." in raw_name.split("/"):
                    raise ValueError(f"Path traversal sequence detected in archive entry: {raw_name}")
                if raw_name.startswith("/") or ":" in raw_name:
                    raise ValueError(f"Unsafe absolute or drive path in archive: {raw_name}")

                # Strip wrapper prefix
                if wrapper_prefix and raw_name.startswith(wrapper_prefix):
                    rel_name = raw_name[len(wrapper_prefix) :]
                else:
                    rel_name = raw_name

                rel_name = rel_name.strip("/")
                if not rel_name:
                    continue

                dest_file_path = (resolved_target / rel_name).resolve()
                if not dest_file_path.is_relative_to(resolved_target):
                    raise ValueError(f"Archive entry escapes target directory: {rel_name}")

                # 3. Directory handling
                if info.is_dir():
                    dest_file_path.mkdir(parents=True, exist_ok=True)
                    continue

                # 4. Limit checks
                extracted_file_count += 1
                if extracted_file_count > file_limit:
                    raise ValueError(
                        f"Archive exceeds maximum file count limit of {file_limit} files"
                    )

                if info.file_size > max_single:
                    raise ValueError(
                        f"File '{rel_name}' size ({info.file_size} bytes) exceeds limit of {max_single // (1024 * 1024)} MB"
                    )

                # 5. Extract file streaming bytes
                dest_file_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as source, open(dest_file_path, "wb") as target:
                    while True:
                        chunk = source.read(65536)
                        if not chunk:
                            break
                        total_extracted_bytes += len(chunk)
                        if total_extracted_bytes > max_total:
                            raise ValueError(
                                f"Extracted archive size exceeds maximum limit of {max_total // (1024 * 1024)} MB"
                            )
                        target.write(chunk)

        return extracted_file_count

    except Exception:
        # Clean up corrupted or partially extracted target directory
        shutil.rmtree(resolved_target, ignore_errors=True)
        resolved_target.mkdir(parents=True, exist_ok=True)
        raise
