"""Library archive manager for pio_compiler.

This module provides functionality to create and reuse library archives (.a files)
to avoid recompiling the same libraries multiple times.

The key idea is:
1. After a library (like FastLED) is compiled, create an archive from all object files
2. Store this archive with a fingerprint based on the library version and build settings
3. For subsequent builds, reuse the archive instead of recompiling

Archive structure in cache:
.tpo/
  └── lib_archives/
      └── native/
          └── fastled-3.10.1-<hash>.a
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


class LibraryArchiveManager:
    """Manages library archives to enable reuse across builds."""

    def __init__(self, cache_root: Optional[Path] = None):
        """Initialize the library archive manager.

        Args:
            cache_root: Root directory for cache. Defaults to .tpo in current directory.
        """
        self.cache_root = cache_root or (Path.cwd() / ".tpo")
        self.archive_root = self.cache_root / "lib_archives"

    def _get_library_fingerprint(
        self,
        library_name: str,
        library_version: str,
        platform: str,
        build_flags: Optional[List[str]] = None,
    ) -> str:
        """Generate a fingerprint for a library build configuration.

        Args:
            library_name: Name of the library (e.g., "FastLED")
            library_version: Version of the library (e.g., "3.10.1")
            platform: Target platform (e.g., "native", "uno")
            build_flags: Additional build flags that affect compilation

        Returns:
            8-character hexadecimal fingerprint
        """
        # Create a string that uniquely identifies this library build
        components = [
            library_name.lower(),
            library_version,
            platform,
        ]

        if build_flags:
            # Sort flags for consistent fingerprinting
            components.extend(sorted(build_flags))

        fingerprint_str = "|".join(components)
        hash_obj = hashlib.sha256(fingerprint_str.encode("utf-8"))
        return hash_obj.hexdigest()[:8]

    def get_archive_path(
        self,
        library_name: str,
        library_version: str,
        platform: str,
        build_flags: Optional[List[str]] = None,
    ) -> Path:
        """Get the path where a library archive should be stored.

        Args:
            library_name: Name of the library
            library_version: Version of the library
            platform: Target platform
            build_flags: Additional build flags

        Returns:
            Path to the archive file
        """
        fingerprint = self._get_library_fingerprint(
            library_name, library_version, platform, build_flags
        )

        # Create platform-specific subdirectory
        platform_dir = self.archive_root / platform
        platform_dir.mkdir(parents=True, exist_ok=True)

        # Archive filename includes library name, version, and fingerprint
        archive_name = f"{library_name.lower()}-{library_version}-{fingerprint}.a"
        return platform_dir / archive_name

    def create_archive_from_objects(
        self, object_files: List[Path], archive_path: Path, ar_tool: str = "ar"
    ) -> bool:
        """Create a static library archive from object files.

        Args:
            object_files: List of .o files to archive
            archive_path: Path where to create the archive
            ar_tool: Archive tool to use (default: "ar")

        Returns:
            True if archive was created successfully
        """
        if not object_files:
            logger.warning("No object files provided for archive creation")
            return False

        # Ensure parent directory exists
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove existing archive if it exists
        if archive_path.exists():
            archive_path.unlink()

        try:
            # Use 'ar' command to create archive
            # 'rcs' flags: r=insert files, c=create archive, s=write index
            cmd = [ar_tool, "rcs", str(archive_path)]
            cmd.extend(str(f) for f in object_files)

            logger.debug(
                f"Creating archive with command: {' '.join(cmd[:4])}... ({len(object_files)} files)"
            )

            result = subprocess.run(cmd, capture_output=True, text=True, check=True)

            if result.returncode == 0:
                logger.info(f"Successfully created archive: {archive_path}")
                logger.info(f"Archive size: {archive_path.stat().st_size:,} bytes")
                return True
            else:
                logger.error(f"Failed to create archive: {result.stderr}")
                return False

        except subprocess.CalledProcessError as e:
            logger.error(f"Archive creation failed: {e}")
            if e.stderr:
                logger.error(f"Error output: {e.stderr}")
            return False
        except FileNotFoundError:
            logger.error(
                f"Archive tool '{ar_tool}' not found. Please install build tools."
            )
            return False

    def archive_exists(self, archive_path: Path) -> bool:
        """Check if an archive exists and is valid.

        Args:
            archive_path: Path to the archive file

        Returns:
            True if archive exists and appears valid
        """
        if not archive_path.exists():
            return False

        # Check if file has reasonable size (at least 8 bytes for archive header)
        if archive_path.stat().st_size < 8:
            logger.warning(f"Archive {archive_path} is too small, likely corrupted")
            return False

        return True

    def find_library_objects(self, build_dir: Path, library_name: str) -> List[Path]:
        """Find all object files for a specific library in the build directory.

        Args:
            build_dir: PlatformIO build directory (e.g., .pio/build/dev)
            library_name: Name of the library to find objects for

        Returns:
            List of paths to object files
        """
        object_files = []

        # Look for library build directories (e.g., lib75f/fastled)
        for lib_dir in build_dir.glob("lib*"):
            if not lib_dir.is_dir():
                continue

            # Check if this is the library we're looking for
            lib_subdir = lib_dir / library_name.lower()
            if lib_subdir.exists() and lib_subdir.is_dir():
                # Find all .o files recursively
                for obj_file in lib_subdir.rglob("*.o"):
                    object_files.append(obj_file)

        logger.debug(f"Found {len(object_files)} object files for {library_name}")
        return object_files

    def copy_archive_to_build(self, archive_path: Path, build_lib_dir: Path) -> bool:
        """Copy a library archive to the build directory for linking.

        Args:
            archive_path: Path to the source archive
            build_lib_dir: Target library directory in build (e.g., .pio/build/dev/lib75f)

        Returns:
            True if copy was successful
        """
        if not archive_path.exists():
            logger.error(f"Archive not found: {archive_path}")
            return False

        try:
            # Ensure target directory exists
            build_lib_dir.mkdir(parents=True, exist_ok=True)

            # Copy archive to build directory
            target_path = build_lib_dir / archive_path.name
            shutil.copy2(archive_path, target_path)

            logger.info(f"Copied archive to build directory: {target_path}")
            return True

        except Exception as e:
            logger.error(f"Failed to copy archive: {e}")
            return False
