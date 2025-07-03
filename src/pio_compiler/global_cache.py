"""Global immutable cache manager for pio_compiler.

This module provides a global cache system for framework dependencies that are
downloaded from GitHub repositories. The cache is stored in ~/.tpo_global/ and
uses an immutable structure based on repository URL and branch/tag information.

Cache structure:
~/.tpo_global/
  ├── github.com/
  │   ├── platformio/
  │   │   └── platform-native/
  │   │       ├── main-a1b2c3d4/           # branch-hash
  │   │       └── v1.2.3-e5f6g7h8/         # tag-hash
  │   └── fastled/
  │       └── fastled/
  │           └── main-9i0j1k2l/
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
import zipfile
from pathlib import Path
from typing import Dict, Optional, Tuple
from urllib.parse import urlparse
from urllib.request import urlopen

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

    def _get_cache_path(
        self, github_url: str, branch_name: str, commit_hash: str
    ) -> Path:
        """Get the cache path for a specific repository, branch, and commit.

        Args:
            github_url: GitHub repository URL
            branch_name: Branch or tag name
            commit_hash: Full commit hash

        Returns:
            Path to the cache directory for this specific version
        """
        domain, owner, repo_name = self._parse_github_url(github_url)
        hash_suffix = commit_hash[-8:] if len(commit_hash) >= 8 else commit_hash
        cache_name = f"{branch_name}-{hash_suffix}"

        return self.cache_root / domain / owner / repo_name / cache_name

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

    def _download_and_extract(self, zip_url: str, target_path: Path) -> None:
        """Download and extract a zip file to the target path.

        Args:
            zip_url: URL to the zip file
            target_path: Directory where to extract the contents

        Raises:
            Exception: If download or extraction fails
        """
        logger.info(f"Downloading from {zip_url}")

        temp_zip_path = None
        try:
            # Create temporary file for download
            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
                temp_zip_path = Path(temp_file.name)

                # Download the zip file
                with urlopen(zip_url) as response:
                    temp_file.write(response.read())
                    temp_file.flush()  # Ensure data is written

            # Extract the zip file (after temp_file is closed)
            with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                # Extract to temporary directory first
                with tempfile.TemporaryDirectory() as temp_extract_dir:
                    zip_ref.extractall(temp_extract_dir)

                    # Find the extracted directory (usually has format "repo-branch")
                    extract_path = Path(temp_extract_dir)
                    extracted_dirs = [d for d in extract_path.iterdir() if d.is_dir()]

                    if not extracted_dirs:
                        raise Exception(
                            f"No directories found in extracted zip from {zip_url}"
                        )

                    # Use the first (and typically only) directory
                    source_dir = extracted_dirs[0]

                    # Move to final cache location
                    if target_path.exists():
                        shutil.rmtree(target_path)
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    shutil.move(str(source_dir), str(target_path))

        finally:
            # Clean up temporary zip file
            if temp_zip_path and temp_zip_path.exists():
                try:
                    temp_zip_path.unlink()
                except OSError:
                    # On Windows, file might still be locked, try again after a short delay
                    import time

                    time.sleep(0.1)
                    try:
                        temp_zip_path.unlink()
                    except OSError:
                        # If still can't delete, log warning but continue
                        logger.warning(
                            f"Could not delete temporary file {temp_zip_path}"
                        )

    def get_or_download_framework(
        self, github_url: str, branch_names: Optional[list[str]] = None
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
                zip_url = f"{github_url}/archive/refs/heads/{branch_name}.zip"

                # Get commit hash from URL (in real implementation, use GitHub API)
                commit_hash = self._get_commit_hash_from_zip_url(zip_url)

                # Get cache path
                cache_path = self._get_cache_path(github_url, branch_name, commit_hash)

                # Check if already cached
                if cache_path.exists():
                    logger.debug(f"Framework already cached at {cache_path}")
                    return cache_path

                # Download and cache
                logger.info(
                    f"Downloading framework from {github_url} (branch: {branch_name})"
                )
                self._download_and_extract(zip_url, cache_path)

                logger.info(f"Framework cached at {cache_path}")
                return cache_path

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

    def list_cached_frameworks(self) -> Dict[str, list[Path]]:
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

                    # Collect all cached versions
                    versions = []
                    for version_dir in repo_dir.iterdir():
                        if version_dir.is_dir():
                            versions.append(version_dir)

                    if versions:
                        cached_frameworks[repo_url] = versions

        return cached_frameworks

    def cleanup_cache(self, keep_recent: int = 5) -> None:
        """Clean up old cache entries, keeping only the most recent ones.

        Args:
            keep_recent: Number of recent versions to keep per repository
        """
        cached_frameworks = self.list_cached_frameworks()

        for repo_url, versions in cached_frameworks.items():
            if len(versions) <= keep_recent:
                continue

            # Sort by modification time (newest first)
            versions.sort(key=lambda p: p.stat().st_mtime, reverse=True)

            # Remove old versions
            for old_version in versions[keep_recent:]:
                logger.info(f"Removing old cached version: {old_version}")
                shutil.rmtree(old_version)

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
