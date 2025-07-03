"""pio_compiler.cache_manager – Smart cache directory management.

This module provides proper cache management with human-readable directory names
instead of cryptic hashes. It replaces the dependency on TemporaryDirectory
and gives us full control over cache organization and cleanup.

The cache structure is:
.tpo_fast_cache/
  ├── Blink-native/           # {project_name}-{platform}
  ├── Blur-uno/
  └── LuminescentGrand-teensy30/

Each cache directory contains:
  - The compiled project files
  - PlatformIO build artifacts
  - A metadata file with creation time and source path
"""

from __future__ import annotations

import json
import logging
import shutil
import time
from pathlib import Path
from typing import Any, Dict, Optional

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
        self, cache_dir: Path, project_name: str, platform: str, source_path: Path
    ):
        self.cache_dir = cache_dir
        self.project_name = project_name
        self.platform = platform
        self.source_path = source_path
        self.metadata_file = cache_dir / ".cache_metadata.json"

    @property
    def name(self) -> str:
        """Human-readable cache directory name."""
        return f"{self.project_name}-{self.platform}"

    @property
    def exists(self) -> bool:
        """Check if this cache entry exists on disk."""
        return self.cache_dir.exists() and self.metadata_file.exists()

    def save_metadata(self) -> None:
        """Save cache metadata to disk."""
        metadata = {
            "project_name": self.project_name,
            "platform": self.platform,
            "source_path": str(self.source_path),
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


class CacheManager:
    """Manages the fast cache directory structure with human-readable names."""

    def __init__(self, cache_root: Optional[Path] = None):
        """Initialize the cache manager.

        Args:
            cache_root: Root directory for cache. Defaults to .tpo_fast_cache in current directory.
        """
        self.cache_root = cache_root or (Path.cwd() / ".tpo_fast_cache")
        self.cache_root.mkdir(exist_ok=True)

    def get_cache_entry(self, source_path: Path, platform: str) -> CacheEntry:
        """Get a cache entry for the given source and platform.

        Args:
            source_path: Path to the source project
            platform: Target platform name (e.g., 'native', 'uno', 'teensy30')

        Returns:
            CacheEntry instance with human-readable directory name

        Raises:
            InvalidCacheNameError: If the project name or platform contains invalid characters
        """
        project_name = source_path.stem

        # Pre-sanitize names before validation to ensure they're filesystem-safe
        safe_project_name = self._pre_sanitize_name(project_name)
        safe_platform = self._pre_sanitize_name(platform)

        # Validate that the sanitized names are acceptable
        self._validate_name(safe_project_name, "project name")
        self._validate_name(safe_platform, "platform")

        cache_dir_name = f"{safe_project_name}-{safe_platform}"
        cache_dir = self.cache_root / cache_dir_name

        entry = CacheEntry(cache_dir, safe_project_name, safe_platform, source_path)

        # If this is a new entry or we're accessing an existing one, save/update metadata
        if not entry.exists:
            entry.save_metadata()
        else:
            entry.touch_access_time()

        return entry

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
                project_name = metadata.get(
                    "project_name", cache_dir.name.split("-")[0]
                )
                platform = metadata.get("platform", "unknown")

                entry = CacheEntry(cache_dir, project_name, platform, source_path)
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
        """Migrate old hash-based cache directories to new human-readable names.

        This helps users transition from the old system to the new one.
        """
        if not self.cache_root.exists():
            return

        # Look for directories that look like old hash-based names
        for cache_dir in self.cache_root.iterdir():
            if not cache_dir.is_dir():
                continue

            # Skip if this already has metadata (new format)
            if (cache_dir / ".cache_metadata.json").exists():
                continue

            # Check if this looks like an old hash-based directory (hex characters, 12 chars)
            dir_name = cache_dir.name
            if len(dir_name) == 12 and all(
                c in "0123456789abcdef" for c in dir_name.lower()
            ):
                logger.info(f"Found old-style cache directory: {dir_name}")

                # Try to determine what project this was for by looking at the contents
                project_name = self._guess_project_name_from_cache(cache_dir)
                platform = self._guess_platform_from_cache(cache_dir)

                if project_name and platform:
                    # Create a new entry with the guessed information
                    new_name = f"{project_name}-{platform}"
                    new_cache_dir = self.cache_root / new_name

                    if not new_cache_dir.exists():
                        logger.info(f"Migrating {dir_name} -> {new_name}")
                        cache_dir.rename(new_cache_dir)

                        # Create metadata for the migrated entry
                        entry = CacheEntry(
                            new_cache_dir, project_name, platform, Path("unknown")
                        )
                        entry.save_metadata()
                    else:
                        logger.warning(
                            f"Cannot migrate {dir_name}: {new_name} already exists"
                        )
                        # Remove the old cache dir since we can't migrate it
                        shutil.rmtree(cache_dir, ignore_errors=True)
                else:
                    logger.warning(
                        f"Could not determine project/platform for {dir_name}, removing"
                    )
                    shutil.rmtree(cache_dir, ignore_errors=True)

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

    def _guess_project_name_from_cache(self, cache_dir: Path) -> Optional[str]:
        """Try to guess the project name from cache contents."""
        # Look for project directories or .ino files
        for item in cache_dir.rglob("*"):
            if item.is_file() and item.suffix == ".ino":
                return item.stem
            elif item.is_dir() and item.name not in {
                ".pio",
                ".pio_home",
                "src",
                "lib",
                "test",
                "include",
            }:
                # This might be a project directory
                if any(
                    child.suffix == ".ino"
                    for child in item.iterdir()
                    if child.is_file()
                ):
                    return item.name

        # Fallback: look for directory names that might be projects
        for item in cache_dir.iterdir():
            if item.is_dir() and item.name not in {".pio", ".pio_home"}:
                return item.name

        return None

    def _guess_platform_from_cache(self, cache_dir: Path) -> Optional[str]:
        """Try to guess the platform from cache contents."""
        # Look for PlatformIO build artifacts that might indicate platform
        pio_dir = cache_dir / ".pio"
        if pio_dir.exists():
            build_dir = pio_dir / "build"
            if build_dir.exists():
                # The build directory often contains platform-specific subdirs
                for platform_dir in build_dir.iterdir():
                    if platform_dir.is_dir():
                        platform_name = platform_dir.name
                        # Common platform names
                        if platform_name in {
                            "native",
                            "uno",
                            "teensy30",
                            "esp32",
                            "esp8266",
                        }:
                            return platform_name

        # Fallback to a default
        return "native"
