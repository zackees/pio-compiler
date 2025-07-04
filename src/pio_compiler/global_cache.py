"""Global immutable cache manager for pio_compiler.

This module provides a global cache system for framework dependencies that are
downloaded from GitHub repositories. The cache is stored in ~/.tpo_global/ and
uses a two-stage immutable structure:

1. Binary artifacts (zip files) are downloaded and stored with file locking
2. These are expanded to directories with the same name + "_dir" suffix
3. Completion is marked with a .done file to ensure integrity
4. File locking prevents concurrent access during expansion

Cache structure:
~/.tpo_global/
  ├── github.com/
  │   ├── platformio/
  │   │   └── platform-native/
  │   │       ├── main-a1b2c3d4.zip           # binary artifact
  │   │       ├── main-a1b2c3d4.zip.lock      # lock file for artifact
  │   │       ├── main-a1b2c3d4_dir/          # expanded directory
  │   │       ├── main-a1b2c3d4_dir.lock      # lock file for directory
  │   │       ├── main-a1b2c3d4_dir.done      # completion marker
  │   │       └── v1.2.3-e5f6g7h8.zip         # another version
  │   └── fastled/
  │       └── fastled/
  │           └── main-9i0j1k2l.zip
  └── other-domain.com/
      └── ...

Each cache entry is immutable once created and identified by:
- Domain part of the GitHub URL
- Repository owner and name
- Branch or tag name
- Last 8 digits of the commit hash
"""

from __future__ import annotations

import hashlib
import logging
import shutil
import tempfile
import time
import zipfile
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

from filelock import FileLock

logger = logging.getLogger(__name__)


class GlobalCacheManager:
    """Manages the global immutable cache for framework dependencies."""

    def __init__(self, cache_root: Optional[Path] = None):
        """Initialize the global cache manager.

        Args:
            cache_root: Root directory for the global cache. Defaults to ~/.tpo_global
        """
        if cache_root is None:
            cache_root = Path.home() / ".tpo_global"

        self.cache_root = cache_root
        self.cache_root.mkdir(parents=True, exist_ok=True)

    def _parse_github_url(self, github_url: str) -> Tuple[str, str, str]:
        """Parse a GitHub URL to extract domain, owner, and repo name.

        Args:
            github_url: GitHub repository URL

        Returns:
            Tuple of (domain, owner, repo_name)

        Raises:
            ValueError: If URL is not a valid GitHub URL
        """
        parsed = urlparse(github_url)
        if not parsed.netloc:
            raise ValueError(f"Invalid GitHub URL: {github_url}")

        domain = parsed.netloc
        path_parts = parsed.path.strip("/").split("/")

        if len(path_parts) < 2:
            raise ValueError(f"Invalid GitHub URL format: {github_url}")

        owner = path_parts[0]
        repo_name = path_parts[1]

        # Remove .git suffix if present
        if repo_name.endswith(".git"):
            repo_name = repo_name[:-4]

        return domain, owner, repo_name

    def _get_cache_paths(
        self, github_url: str, branch_name: str, commit_hash: str
    ) -> Tuple[Path, Path, Path, Path, Path]:
        """Get the cache paths for a specific repository, branch, and commit.

        Args:
            github_url: GitHub repository URL
            branch_name: Branch or tag name
            commit_hash: Full commit hash

        Returns:
            Tuple of (archive_path, archive_lock_path, dir_path, dir_lock_path, done_path)
        """
        domain, owner, repo_name = self._parse_github_url(github_url)
        hash_suffix = commit_hash[-8:] if len(commit_hash) >= 8 else commit_hash
        cache_name = f"{branch_name}-{hash_suffix}"

        base_path = self.cache_root / domain / owner / repo_name
        archive_path = base_path / f"{cache_name}.zip"
        archive_lock_path = base_path / f"{cache_name}.zip.lock"
        dir_path = base_path / f"{cache_name}_dir"
        dir_lock_path = base_path / f"{cache_name}_dir.lock"
        done_path = base_path / f"{cache_name}_dir.done"

        return archive_path, archive_lock_path, dir_path, dir_lock_path, done_path

    def _get_commit_hash_from_zip_url(self, zip_url: str) -> str:
        """Extract commit hash from a GitHub zip URL.

        Args:
            zip_url: GitHub zip download URL

        Returns:
            Commit hash (first 8 characters for brevity)
        """
        # For now, we'll use a hash of the URL as a proxy for the commit hash
        # In a real implementation, you might want to query the GitHub API
        # to get the actual commit hash for the branch/tag
        url_hash = hashlib.sha256(zip_url.encode()).hexdigest()
        return url_hash[:8]

    def _download_archive(self, zip_url: str, archive_path: Path) -> None:
        """Download a zip file to the archive path.

        Args:
            zip_url: URL to the zip file
            archive_path: Path where to save the archive

        Raises:
            Exception: If download fails
        """
        logger.info(f"Downloading archive from {zip_url}")

        # Ensure parent directory exists
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Download to a temporary file first, then move to final location
        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                suffix=".zip", dir=archive_path.parent, delete=False
            ) as temp_file:
                temp_path = Path(temp_file.name)
                with urlopen(zip_url) as response:
                    temp_file.write(response.read())
                    temp_file.flush()

            # Move to final location (after temp_file is closed)
            temp_path.replace(archive_path)
            logger.info(f"Archive downloaded to {archive_path}")

        except Exception:
            # Clean up temporary file on error
            if temp_path and temp_path.exists():
                try:
                    temp_path.unlink()
                except OSError:
                    pass  # Ignore if we can't clean up
            raise

    def _expand_archive(self, archive_path: Path, dir_path: Path) -> None:
        """Expand an archive to the directory path.

        Args:
            archive_path: Path to the zip archive
            dir_path: Directory where to extract the contents

        Raises:
            Exception: If extraction fails
        """
        logger.info(f"Expanding archive {archive_path} to {dir_path}")

        # Remove existing directory if it exists
        if dir_path.exists():
            shutil.rmtree(dir_path)

        # Extract to temporary directory first
        with tempfile.TemporaryDirectory(dir=dir_path.parent) as temp_extract_dir:
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(temp_extract_dir)

            # Find the extracted directory (usually has format "repo-branch")
            extract_path = Path(temp_extract_dir)
            extracted_dirs = [d for d in extract_path.iterdir() if d.is_dir()]

            if not extracted_dirs:
                raise Exception(
                    f"No directories found in extracted archive {archive_path}"
                )

            # Use the first (and typically only) directory
            source_dir = extracted_dirs[0]

            # Move to final location
            shutil.move(str(source_dir), str(dir_path))

        logger.info(f"Archive expanded to {dir_path}")

    def _is_expansion_complete(self, dir_path: Path, done_path: Path) -> bool:
        """Check if archive expansion is complete.

        Args:
            dir_path: Path to the expanded directory
            done_path: Path to the completion marker file

        Returns:
            True if expansion is complete and valid
        """
        return dir_path.exists() and done_path.exists()

    def _mark_expansion_complete(self, done_path: Path) -> None:
        """Mark archive expansion as complete.

        Args:
            done_path: Path to the completion marker file
        """
        done_path.write_text(f"completed at {time.time()}")

    def get_or_download_framework(
        self, github_url: str, branch_names: Optional[List[str]] = None
    ) -> Path:
        """Get a framework from the global cache or download it if not present.

        Args:
            github_url: GitHub repository URL
            branch_names: List of branch names to try (defaults to ["main", "master", "develop"])

        Returns:
            Path to the cached framework directory

        Raises:
            Exception: If download fails for all branches
        """
        if branch_names is None:
            branch_names = ["main", "master", "develop"]

        last_exception = None

        for branch_name in branch_names:
            try:
                # Remove .git suffix from URL if present for archive download
                clean_url = github_url.rstrip(".git")
                zip_url = f"{clean_url}/archive/refs/heads/{branch_name}.zip"
                commit_hash = self._get_commit_hash_from_zip_url(zip_url)

                archive_path, archive_lock_path, dir_path, dir_lock_path, done_path = (
                    self._get_cache_paths(github_url, branch_name, commit_hash)
                )

                # Check if already expanded and complete
                if self._is_expansion_complete(dir_path, done_path):
                    logger.debug(f"Framework already cached and expanded at {dir_path}")
                    return dir_path

                # Acquire lock for the directory to prevent concurrent expansion
                with FileLock(dir_lock_path, timeout=60):
                    # Double-check after acquiring lock
                    if self._is_expansion_complete(dir_path, done_path):
                        logger.debug(
                            f"Framework already cached and expanded at {dir_path}"
                        )
                        return dir_path

                    # Check if archive exists, if not download it
                    if not archive_path.exists():
                        # Acquire lock for archive download
                        with FileLock(archive_lock_path, timeout=60):
                            # Double-check after acquiring archive lock
                            if not archive_path.exists():
                                logger.info(
                                    f"Downloading framework from {github_url} (branch: {branch_name})"
                                )
                                self._download_archive(zip_url, archive_path)

                    # Expand the archive
                    if not self._is_expansion_complete(dir_path, done_path):
                        # Clean up any incomplete expansion
                        if dir_path.exists():
                            shutil.rmtree(dir_path)
                        if done_path.exists():
                            done_path.unlink()

                        # Expand the archive
                        self._expand_archive(archive_path, dir_path)

                        # Mark as complete
                        self._mark_expansion_complete(done_path)

                logger.info(f"Framework cached at {dir_path}")
                return dir_path

            except Exception as e:
                logger.debug(f"Branch '{branch_name}' failed: {e}")
                last_exception = e
                continue

        # If we get here, all branches failed
        error_msg = f"Failed to download framework from {github_url} (tried branches: {branch_names})"
        if last_exception:
            error_msg += f". Last error: {last_exception}"
        logger.error(error_msg)
        raise Exception(error_msg)

    def list_cached_frameworks(self) -> Dict[str, List[Path]]:
        """List all cached frameworks organized by repository.

        Returns:
            Dictionary mapping repository URLs to lists of cached versions
        """
        cached_frameworks = {}

        if not self.cache_root.exists():
            return cached_frameworks

        # Walk through the cache directory structure
        for domain_dir in self.cache_root.iterdir():
            if not domain_dir.is_dir():
                continue

            for owner_dir in domain_dir.iterdir():
                if not owner_dir.is_dir():
                    continue

                for repo_dir in owner_dir.iterdir():
                    if not repo_dir.is_dir():
                        continue

                    # Reconstruct the repository URL
                    repo_url = (
                        f"https://{domain_dir.name}/{owner_dir.name}/{repo_dir.name}"
                    )

                    # Collect all cached versions (directories with _dir suffix)
                    versions = []
                    for item in repo_dir.iterdir():
                        if item.is_dir() and item.name.endswith("_dir"):
                            # Check if expansion is complete
                            done_file = repo_dir / f"{item.name}.done"
                            if done_file.exists():
                                versions.append(item)

                    if versions:
                        cached_frameworks[repo_url] = versions

        return cached_frameworks

    def cleanup_cache(self, keep_recent: int = 5) -> Tuple[List[str], List[str]]:
        """Clean up old cache entries, keeping only the most recent ones.

        Args:
            keep_recent: Number of recent versions to keep per repository

        Returns:
            Tuple of (successfully_removed, failed_to_remove) file paths
        """
        cached_frameworks = self.list_cached_frameworks()
        successfully_removed = []
        failed_to_remove = []

        for repo_url, versions in cached_frameworks.items():
            if len(versions) <= keep_recent:
                continue

            # Sort by modification time (newest first)
            versions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Remove old versions
            for old_version in versions[keep_recent:]:
                try:
                    # Try to acquire lock before removing
                    lock_path = old_version.parent / f"{old_version.name}.lock"

                    try:
                        with FileLock(
                            lock_path, timeout=5.0
                        ):  # Longer timeout to respect active compilations
                            # Remove the directory
                            shutil.rmtree(old_version)

                            # Remove associated files
                            done_path = old_version.parent / f"{old_version.name}.done"
                            if done_path.exists():
                                done_path.unlink()

                            # Remove archive if it exists
                            archive_name = old_version.name.replace("_dir", ".zip")
                            archive_path = old_version.parent / archive_name
                            if archive_path.exists():
                                archive_path.unlink()

                            # Remove archive lock if it exists
                            archive_lock_path = (
                                old_version.parent / f"{archive_name}.lock"
                            )
                            if archive_lock_path.exists():
                                archive_lock_path.unlink()

                            successfully_removed.append(str(old_version))
                            logger.info(f"Removed old cached version: {old_version}")

                    except Exception:
                        # Could not acquire lock, skip this entry
                        failed_to_remove.append(str(old_version))
                        logger.debug(
                            f"Could not acquire lock for {old_version}, skipping"
                        )

                except Exception as e:
                    failed_to_remove.append(str(old_version))
                    logger.warning(
                        f"Failed to remove old cached version {old_version}: {e}"
                    )

        return successfully_removed, failed_to_remove

    def purge_cache(self) -> Tuple[List[str], List[str]]:
        """Purge the entire cache, respecting file locks.

        Returns:
            Tuple of (successfully_removed, failed_to_remove) file paths
        """
        successfully_removed = []
        failed_to_remove = []

        if not self.cache_root.exists():
            return successfully_removed, failed_to_remove

        # First pass: try to remove all unlocked items
        self._purge_cache_pass(successfully_removed, failed_to_remove)

        # Second pass: retry previously locked items
        if failed_to_remove:
            retry_failed = []
            for item_path in failed_to_remove:
                path = Path(item_path)
                if path.exists():
                    try:
                        # Try to acquire lock with short timeout
                        if path.name.endswith("_dir"):
                            lock_path = path.parent / f"{path.name}.lock"
                        else:
                            lock_path = path.parent / f"{path.name}.lock"

                        try:
                            with FileLock(lock_path, timeout=5.0):
                                if path.is_dir():
                                    shutil.rmtree(path)
                                else:
                                    path.unlink()
                                successfully_removed.append(item_path)
                        except Exception:
                            retry_failed.append(item_path)
                    except Exception:
                        retry_failed.append(item_path)

            failed_to_remove = retry_failed

        # Try to remove the entire cache root if it's empty
        try:
            if not any(self.cache_root.rglob("*")):
                shutil.rmtree(self.cache_root)
                successfully_removed.append(str(self.cache_root))
        except Exception:
            pass

        return successfully_removed, failed_to_remove

    def _purge_cache_pass(
        self, successfully_removed: List[str], failed_to_remove: List[str]
    ) -> None:
        """Single pass of cache purging, respecting locks.

        Args:
            successfully_removed: List to append successfully removed paths
            failed_to_remove: List to append failed removal paths
        """
        # Walk through all cache items
        for domain_dir in self.cache_root.iterdir():
            if not domain_dir.is_dir():
                continue

            for owner_dir in domain_dir.iterdir():
                if not owner_dir.is_dir():
                    continue

                for repo_dir in owner_dir.iterdir():
                    if not repo_dir.is_dir():
                        continue

                    # Try to remove all items in this repo directory
                    for item in repo_dir.iterdir():
                        try:
                            # Determine lock path based on item type
                            if item.is_dir() and item.name.endswith("_dir"):
                                lock_path = item.parent / f"{item.name}.lock"
                            elif item.name.endswith(".zip"):
                                lock_path = item.parent / f"{item.name}.lock"
                            else:
                                # For other files (.done, .lock), try to remove directly
                                item.unlink()
                                successfully_removed.append(str(item))
                                continue

                            # Try to acquire lock
                            try:
                                with FileLock(lock_path, timeout=5.0):
                                    if item.is_dir():
                                        shutil.rmtree(item)
                                    else:
                                        item.unlink()
                                    successfully_removed.append(str(item))
                            except Exception:
                                failed_to_remove.append(str(item))

                        except Exception as e:
                            failed_to_remove.append(str(item))
                            logger.debug(f"Failed to remove {item}: {e}")

    def get_cache_size(self) -> int:
        """Get the total size of the cache in bytes.

        Returns:
            Total cache size in bytes
        """
        total_size = 0

        if not self.cache_root.exists():
            return total_size

        import os

        for root, dirs, files in os.walk(self.cache_root):
            for file in files:
                file_path = Path(root) / file
                try:
                    total_size += file_path.stat().st_size
                except (OSError, FileNotFoundError):
                    # Skip files that can't be accessed
                    continue

        return total_size
