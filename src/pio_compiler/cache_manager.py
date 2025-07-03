"""pio_compiler.cache_manager – Smart cache directory management.

This module provides proper cache management with fingerprint-based directory names
based on the platformio.ini file content. It replaces the dependency on TemporaryDirectory
and gives us full control over cache organization and cleanup.

The cache structure is:
.tpo/
  ├── native-a03a3ffa/           # {platform}-{fingerprint:8}
  ├── native-a03a3ffa.lock       # Lock file for the cache directory
  ├── uno-b4f2e8cd/
  ├── uno-b4f2e8cd.lock
  └── teensy30-c9d1a7ef/
  └── teensy30-c9d1a7ef.lock

Each cache directory contains:
  - The compiled project files
  - PlatformIO build artifacts
  - A metadata file with creation time and source path

Lock files are placed alongside cache directories to prevent concurrent access.
"""

from __future__ import annotations

import hashlib
import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

from filelock import BaseFileLock, FileLock

__all__ = [
    "CacheManager",
    "CacheEntry",
    "InvalidCacheNameError",
]

logger = logging.getLogger(__name__)


class InvalidCacheNameError(Exception):
    """Raised when a cache name contains invalid characters for filesystem use."""

    pass


class CacheEntry:
    """Represents a single cache entry with metadata."""

    def __init__(
        self,
        cache_dir: Path,
        platform: str,
        fingerprint: str,
        source_path: Path,
        platformio_ini_content: str,
        turbo_dependencies: list[str] | None = None,
    ):
        self.cache_dir = cache_dir
        self.platform = platform
        self.fingerprint = fingerprint
        self.source_path = source_path
        self.platformio_ini_content = platformio_ini_content
        self.turbo_dependencies = turbo_dependencies or []
        self.metadata_file = cache_dir / ".cache_metadata.json"
        self.lock_file = cache_dir.parent / f"{cache_dir.name}.lock"
        self._file_lock: Optional[BaseFileLock] = None

    @property
    def name(self) -> str:
        """Cache directory name with platform-fingerprint pattern."""
        return f"{self.platform}-{self.fingerprint}"

    @property
    def exists(self) -> bool:
        """Check if this cache entry exists on disk."""
        return self.cache_dir.exists() and self.metadata_file.exists()

    def save_metadata(self) -> None:
        """Save cache metadata to disk."""
        metadata = {
            "platform": self.platform,
            "fingerprint": self.fingerprint,
            "source_path": str(self.source_path),
            "platformio_ini_hash": hashlib.sha256(
                self.platformio_ini_content.encode()
            ).hexdigest(),
            "turbo_dependencies": self.turbo_dependencies,
            "created_at": time.time(),
            "last_accessed": time.time(),
        }

        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.metadata_file.write_text(json.dumps(metadata, indent=2))

    def load_metadata(self) -> Dict[str, Any]:
        """Load cache metadata from disk."""
        if not self.metadata_file.exists():
            return {}

        try:
            return json.loads(self.metadata_file.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(
                f"Failed to load cache metadata from {self.metadata_file}: {e}"
            )
            return {}

    def touch_access_time(self) -> None:
        """Update the last accessed time for this cache entry."""
        if self.metadata_file.exists():
            metadata = self.load_metadata()
            metadata["last_accessed"] = time.time()
            self.metadata_file.write_text(json.dumps(metadata, indent=2))

    def is_valid_for_platformio_content(self, platformio_ini_content: str) -> bool:
        """Check if this cache entry is still valid for the given platformio.ini content."""
        if not self.exists:
            return False

        metadata = self.load_metadata()
        stored_hash = metadata.get("platformio_ini_hash", "")
        current_hash = hashlib.sha256(platformio_ini_content.encode()).hexdigest()

        return stored_hash == current_hash

    def get_lock(self) -> BaseFileLock:
        """Get the FileLock instance for this cache entry.

        Returns:
            FileLock instance for controlling concurrent access to this cache entry
        """
        if self._file_lock is None:
            # Ensure the parent directory exists for the lock file (cache root)
            self.lock_file.parent.mkdir(parents=True, exist_ok=True)
            self._file_lock = FileLock(self.lock_file, timeout=30)
        return self._file_lock

    def acquire_lock(self, timeout: float = 30.0) -> BaseFileLock:
        """Acquire the file lock for this cache entry.

        Args:
            timeout: Maximum time in seconds to wait for the lock

        Returns:
            Acquired FileLock instance (can be used as context manager)

        Raises:
            TimeoutError: If lock cannot be acquired within timeout
        """
        lock = self.get_lock()
        lock.acquire(timeout=timeout)
        return lock

    def release_lock(self) -> None:
        """Release the file lock for this cache entry if it's currently held."""
        if self._file_lock is not None and self._file_lock.is_locked:
            self._file_lock.release()

    def __enter__(self) -> "CacheEntry":
        """Context manager entry - acquire lock."""
        self.acquire_lock()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Context manager exit - release lock."""
        self.release_lock()

    def are_turbo_dependencies_setup(self) -> bool:
        """Check if turbo dependencies are already set up in this cache entry.

        Returns:
            True if all required turbo dependencies are present as symlinks/directories
        """
        if not self.turbo_dependencies:
            return True  # No dependencies needed

        lib_dir = self.cache_dir / "lib"
        if not lib_dir.exists():
            return False

        for dep in self.turbo_dependencies:
            dep_path = lib_dir / dep.lower()
            if not dep_path.exists():
                return False

        return True


class CacheManager:
    """Manages the fast cache directory structure with platform-fingerprint names."""

    def __init__(self, cache_root: Optional[Path] = None):
        """Initialize the cache manager.

        Args:
            cache_root: Root directory for cache. Defaults to .tpo in current directory.
        """
        self.cache_root = cache_root or (Path.cwd() / ".tpo")
        self.cache_root.mkdir(exist_ok=True)

    def get_cache_entry(
        self,
        source_path: Path,
        platform: str,
        platformio_ini_content: str,
        turbo_dependencies: list[str] | None = None,
    ) -> CacheEntry:
        """Get a cache entry for the given source, platform, and platformio.ini content.

        Args:
            source_path: Path to the source project
            platform: Target platform name (e.g., 'native', 'uno', 'teensy30')
            platformio_ini_content: Content of the platformio.ini file
            turbo_dependencies: List of turbo dependency library names

        Returns:
            CacheEntry instance with platform-fingerprint directory name

        Raises:
            InvalidCacheNameError: If the platform contains invalid characters
        """
        # Pre-sanitize platform name before validation to ensure it's filesystem-safe
        safe_platform = self._pre_sanitize_name(platform)

        # Validate the sanitized platform name
        self._validate_name(safe_platform, "platform")

        # Include turbo dependencies in fingerprint calculation
        content_for_fingerprint = platformio_ini_content
        if turbo_dependencies:
            # Sort dependencies for consistent fingerprinting
            sorted_deps = sorted(turbo_dependencies)
            deps_string = "\n".join(f"turbo_dep:{dep}" for dep in sorted_deps)
            content_for_fingerprint = f"{platformio_ini_content}\n{deps_string}"

        fingerprint = self._generate_fingerprint(content_for_fingerprint)
        cache_dir = self.cache_root / f"{safe_platform}-{fingerprint}"

        entry = CacheEntry(
            cache_dir=cache_dir,
            platform=safe_platform,
            fingerprint=fingerprint,
            source_path=source_path,
            platformio_ini_content=platformio_ini_content,
            turbo_dependencies=turbo_dependencies or [],
        )

        # Create metadata if this is a new cache entry
        if not entry.exists:
            entry.save_metadata()
        else:
            # Update access time for existing entries
            entry.touch_access_time()

        return entry

    def _generate_fingerprint(self, platformio_ini_content: str) -> str:
        """Generate an 8-character fingerprint from platformio.ini content.

        Args:
            platformio_ini_content: Content of the platformio.ini file

        Returns:
            8-character hexadecimal fingerprint
        """
        # Clean the content using our specialized cleaning logic
        cleaned_content = self._clean_platformio_content(platformio_ini_content)

        # Create SHA256 hash of the cleaned content
        hash_obj = hashlib.sha256(cleaned_content.encode("utf-8"))
        # Take first 8 characters of the hex digest
        return hash_obj.hexdigest()[:8]

    def _clean_platformio_content(self, content: str) -> str:
        """Clean PlatformIO file content for consistent fingerprinting.

        This method implements specific cleaning rules:
        1. For each line, truncate everything from ';' onwards (including the ';')
        2. Trim each line
        3. Remove all double empty lines repeatedly
        4. Join lines and trim the final string

        Args:
            content: Raw PlatformIO file content

        Returns:
            Cleaned content string ready for hashing
        """
        # Break the string into lines
        lines = content.splitlines()

        # Process each line: remove comments and trim
        cleaned_lines = []
        for line in lines:
            # Find semicolon and truncate everything from there (including the semicolon)
            semicolon_pos = line.find(";")
            if semicolon_pos != -1:
                line = line[:semicolon_pos]

            # Trim the line
            line = line.strip()
            cleaned_lines.append(line)

        # Remove double empty lines repeatedly
        while True:
            # Find consecutive empty lines and replace double+ empty lines with single empty line
            new_lines = []
            prev_was_empty = False

            for line in cleaned_lines:
                is_empty = line == ""

                # If current line is empty and previous was also empty, skip this line
                if is_empty and prev_was_empty:
                    continue

                new_lines.append(line)
                prev_was_empty = is_empty

            # If no changes were made, we're done
            if len(new_lines) == len(cleaned_lines):
                break

            cleaned_lines = new_lines

        # Join all remaining lines into a string
        result = "\n".join(cleaned_lines)

        # Trim the final string
        result = result.strip()

        return result

    def list_cache_entries(self) -> list[CacheEntry]:
        """List all cache entries in the cache root."""
        entries = []

        for cache_dir in self.cache_root.iterdir():
            if not cache_dir.is_dir():
                continue

            metadata_file = cache_dir / ".cache_metadata.json"
            if not metadata_file.exists():
                # This might be an old-style cache directory, skip it
                continue

            try:
                metadata = json.loads(metadata_file.read_text())
                source_path = Path(metadata.get("source_path", ""))
                platform = metadata.get("platform", "unknown")
                fingerprint = metadata.get("fingerprint", cache_dir.name.split("-")[-1])

                # We don't have the platformio_ini_content here, so use empty string
                entry = CacheEntry(cache_dir, platform, fingerprint, source_path, "")
                entries.append(entry)
            except (json.JSONDecodeError, OSError, KeyError) as e:
                logger.warning(f"Failed to load cache entry from {cache_dir}: {e}")
                continue

        return entries

    def cleanup_old_entries(
        self, max_entries: int = 10, max_age_days: int = 30
    ) -> None:
        """Clean up old cache entries based on age and count limits.

        Args:
            max_entries: Maximum number of cache entries to keep
            max_age_days: Maximum age in days for cache entries
        """
        entries = self.list_cache_entries()

        # Remove entries older than max_age_days
        current_time = time.time()
        age_cutoff = current_time - (max_age_days * 24 * 60 * 60)

        for entry in entries[:]:
            metadata = entry.load_metadata()
            created_at = metadata.get("created_at", 0)

            if created_at < age_cutoff:
                logger.info(f"Removing old cache entry: {entry.name}")
                self._remove_cache_entry(entry)
                entries.remove(entry)

        # If we still have too many entries, remove the least recently accessed
        if len(entries) > max_entries:
            # Sort by last accessed time (oldest first)
            entries.sort(key=lambda e: e.load_metadata().get("last_accessed", 0))

            entries_to_remove = entries[: len(entries) - max_entries]
            for entry in entries_to_remove:
                logger.info(f"Removing excess cache entry: {entry.name}")
                self._remove_cache_entry(entry)

    def cleanup_all(self) -> None:
        """Remove all cache entries and the cache root directory."""
        if self.cache_root.exists():
            logger.info(f"Removing entire cache directory: {self.cache_root}")
            shutil.rmtree(self.cache_root)

    def migrate_old_cache_entries(self) -> None:
        """Migrate old cache directories to new platform-fingerprint format.

        This helps users transition from the old system to the new one.
        """
        if not self.cache_root.exists():
            return

        # Also check for old .tpo_fast_cache directory and migrate it
        old_cache_root = self.cache_root.parent / ".tpo_fast_cache"
        if old_cache_root.exists():
            logger.info(f"Found old cache directory: {old_cache_root}")
            logger.info(
                "Migrating from .tpo_fast_cache to .tpo format requires rebuilding cache"
            )
            # Since we can't determine platformio.ini content from old cache, we'll just remove it
            shutil.rmtree(old_cache_root, ignore_errors=True)
            logger.info(
                "Old cache directory removed - new builds will create fresh cache entries"
            )

        # Look for directories that look like old project-platform names
        for cache_dir in self.cache_root.iterdir():
            if not cache_dir.is_dir():
                continue

            # Skip if this already has metadata (new format)
            if (cache_dir / ".cache_metadata.json").exists():
                continue

            # Check if this looks like an old project-platform directory
            dir_name = cache_dir.name
            if "-" in dir_name and not self._looks_like_fingerprint_format(dir_name):
                logger.info(f"Found old-style cache directory: {dir_name}")
                # Remove old format cache since we can't migrate without platformio.ini content
                shutil.rmtree(cache_dir, ignore_errors=True)
                logger.info(f"Removed old cache directory: {dir_name}")

    def _looks_like_fingerprint_format(self, dir_name: str) -> bool:
        """Check if a directory name looks like the new platform-fingerprint format."""
        parts = dir_name.split("-")
        if len(parts) != 2:
            return False

        platform, fingerprint = parts
        # Fingerprint should be 8 hex characters
        return len(fingerprint) == 8 and all(
            c in "0123456789abcdef" for c in fingerprint.lower()
        )

    @staticmethod
    def _pre_sanitize_name(name: str) -> str:
        """Pre-sanitize a name by applying basic transformations before validation.

        This method applies minimal transformations to make names more likely to pass
        validation, but still rejects fundamentally problematic names.
        """
        if not name or not name.strip():
            raise InvalidCacheNameError("Name cannot be empty or only whitespace")

        # Remove leading/trailing whitespace
        sanitized = name.strip()

        # Replace common filesystem-unsafe characters with safe alternatives
        replacements = {
            "/": "_",  # Path separator
            "\\": "_",  # Windows path separator
            ":": "_",  # Drive separator on Windows
            " ": "_",  # Spaces can be problematic
        }

        for old, new in replacements.items():
            sanitized = sanitized.replace(old, new)

        return sanitized

    @staticmethod
    def _validate_name(name: str, name_type: str) -> None:
        """Validate that a name is safe for filesystem use.

        Args:
            name: The name to validate
            name_type: Description of what the name represents (for error messages)

        Raises:
            InvalidCacheNameError: If the name contains invalid characters
        """
        if not name or not name.strip():
            raise InvalidCacheNameError(
                f"{name_type} cannot be empty or only whitespace"
            )

        # Check for problematic characters that should never be in filesystem names
        invalid_chars = set('<>:"|?*')
        found_invalid = [c for c in name if c in invalid_chars]
        if found_invalid:
            raise InvalidCacheNameError(
                f"{name_type} '{name}' contains invalid characters: {found_invalid}. "
                f"Names must be filesystem-safe."
            )

        # Check for names that are reserved on Windows
        reserved_names = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            "COM1",
            "COM2",
            "COM3",
            "COM4",
            "COM5",
            "COM6",
            "COM7",
            "COM8",
            "COM9",
            "LPT1",
            "LPT2",
            "LPT3",
            "LPT4",
            "LPT5",
            "LPT6",
            "LPT7",
            "LPT8",
            "LPT9",
        }
        if name.upper() in reserved_names:
            raise InvalidCacheNameError(
                f"{name_type} '{name}' is a reserved name on Windows"
            )

        # Check for names ending with dots or spaces (problematic on Windows)
        if name.endswith(".") or name.endswith(" "):
            raise InvalidCacheNameError(
                f"{name_type} '{name}' cannot end with dots or spaces"
            )

        # Ensure name isn't too long (filesystem limits)
        if len(name) > 100:  # Conservative limit
            raise InvalidCacheNameError(
                f"{name_type} '{name}' is too long (max 100 characters)"
            )

    def _remove_cache_entry(self, entry: CacheEntry) -> None:
        """Safely remove a cache entry."""
        try:
            if entry.cache_dir.exists():
                shutil.rmtree(entry.cache_dir)
        except OSError as e:
            logger.warning(f"Failed to remove cache entry {entry.name}: {e}")
