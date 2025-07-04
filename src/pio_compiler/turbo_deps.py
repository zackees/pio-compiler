"""Turbo dependencies management for pio_compiler.

This module handles downloading libraries and platforms from GitHub and extracting them
directly into projects without using PlatformIO's lib_deps system or symlinks.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Dict

from .global_cache import GlobalCacheManager

logger = logging.getLogger(__name__)


class TurboDependencyManager:
    """Manages turbo dependencies - libraries and platforms downloaded and extracted directly."""

    def __init__(self, cache_dir: Path | None = None):
        """Initialize the turbo dependency manager.

        Args:
            cache_dir: Directory to cache downloaded libraries. Defaults to .tpo/turbo_libs
        """
        if cache_dir is None:
            cache_dir = Path.cwd() / ".tpo" / "turbo_libs"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Platform cache directory (local project cache)
        self.platform_cache_dir = cache_dir / "platforms"
        self.platform_cache_dir.mkdir(parents=True, exist_ok=True)

        # Global cache manager for framework dependencies
        self.global_cache = GlobalCacheManager()

        # Known library mappings - maps library name to GitHub repo
        self.library_mappings: Dict[str, str] = {
            "fastled": "fastled/fastled",
            "adafruit_neopixel": "adafruit/Adafruit_NeoPixel",
            "arduino_json": "bblanchon/ArduinoJson",
            "wifi_manager": "tzapu/WiFiManager",
            "pubsub_client": "knolleary/pubsubclient",
            "esp_async_webserver": "me-no-dev/ESPAsyncWebServer",
            # Add more mappings as needed
        }

        # Known platform mappings - maps platform name to GitHub repo
        self.platform_mappings: Dict[str, str] = {
            "native": "platformio/platform-native",
            "dev": "platformio/platform-native",  # dev is an alias for native
            "platform-native": "platformio/platform-native",
        }

    def get_github_url(self, library_name: str) -> str:
        """Get the GitHub repository URL for a library name.

        Args:
            library_name: Name of the library (case-insensitive)

        Returns:
            GitHub repository URL

        Raises:
            ValueError: If library mapping is not found
        """
        normalized_name = library_name.lower()

        if normalized_name in self.library_mappings:
            repo = self.library_mappings[normalized_name]
            return f"https://github.com/{repo}"

        # Fallback: try to construct URL from library name
        # Assumes library name matches repo name under common org
        common_orgs = ["arduino-libraries", "adafruit", "sparkfun"]

        for org in common_orgs:
            # Try variations of the library name
            variations = [
                library_name,
                library_name.replace("_", "-"),
                f"Arduino-{library_name}",
                f"Adafruit_{library_name}",
            ]

            for variation in variations:
                potential_url = f"https://github.com/{org}/{variation}"
                # Note: In a real implementation, you might want to check if the repo exists
                # For now, we'll use the first variation with the first org
                if org == common_orgs[0]:  # Just use arduino-libraries as default
                    logger.warning(
                        f"Library '{library_name}' not in known mappings, "
                        f"trying fallback: {potential_url}"
                    )
                    return potential_url

        raise ValueError(
            f"Could not determine GitHub URL for library '{library_name}'. "
            f"Known libraries: {list(self.library_mappings.keys())}"
        )

    def download_library(self, library_name: str) -> Path:
        """Download a library from GitHub and extract it to cache.

        Args:
            library_name: Name of the library to download

        Returns:
            Path to the extracted library directory

        Raises:
            Exception: If download or extraction fails
        """
        # Check if library is already cached locally
        library_dir = self.cache_dir / library_name.lower()
        if library_dir.exists():
            logger.debug(f"Library '{library_name}' already cached at {library_dir}")
            return library_dir

        # Get GitHub URL and download
        github_url = self.get_github_url(library_name)

        try:
            # Use global cache for library download
            logger.info(
                f"Downloading library '{library_name}' from {github_url} using global cache"
            )
            logger.debug(
                f"Attempting to get or download framework from global cache: {github_url}"
            )
            global_cache_path = self.global_cache.get_or_download_framework(github_url)
            logger.debug(f"Global cache returned path: {global_cache_path}")

            # Extract directly from global cache to local cache (no symlinks)
            if library_dir.exists():
                logger.debug(f"Removing existing library directory: {library_dir}")
                shutil.rmtree(library_dir)

            # Always copy the directory to avoid symlink issues
            logger.info(
                f"Extracting library '{library_name}' from global cache to local cache"
            )
            logger.debug(f"Copying from {global_cache_path} to {library_dir}")
            shutil.copytree(global_cache_path, library_dir)
            logger.info(f"Library '{library_name}' extracted to {library_dir}")

            return library_dir

        except Exception as e:
            logger.error(
                f"Failed to download library '{library_name}' using global cache: {e}"
            )
            logger.debug(
                f"Library download error details for '{library_name}'", exc_info=True
            )
            raise

    def extract_library(self, library_name: str, target_project_dir: Path) -> Path:
        """Extract a library directly into a project's lib directory.

        Args:
            library_name: Name of the library to extract
            target_project_dir: Project directory where to extract the library

        Returns:
            Path to the extracted library in the project

        Raises:
            Exception: If extraction fails
        """
        # Download library if not cached
        library_source = self.download_library(library_name)

        # Create lib directory in project if it doesn't exist
        project_lib_dir = target_project_dir / "lib"
        project_lib_dir.mkdir(exist_ok=True)

        # Extract directly to project lib directory
        extract_target = project_lib_dir / library_name.lower()

        # Remove existing directory if it exists
        if extract_target.exists():
            shutil.rmtree(extract_target)

        # Copy the library directly (no symlinks)
        logger.info(f"Extracting library '{library_name}' to {extract_target}")
        shutil.copytree(library_source, extract_target)
        logger.info(f"Library '{library_name}' extracted to {extract_target}")
        return extract_target

    def setup_turbo_dependencies(
        self, library_names: list[str], project_dir: Path
    ) -> list[Path]:
        """Set up all turbo dependencies for a project.

        Args:
            library_names: List of library names to set up
            project_dir: Project directory

        Returns:
            List of paths to extracted libraries
        """
        if not library_names:
            return []

        logger.info(f"Setting up turbo dependencies: {library_names}")

        extracted_paths = []
        for lib_name in library_names:
            try:
                logger.debug(f"Starting extraction of library '{lib_name}'")
                extract_path = self.extract_library(lib_name, project_dir)
                extracted_paths.append(extract_path)
                logger.debug(
                    f"Successfully extracted library '{lib_name}' to {extract_path}"
                )
            except Exception as e:
                logger.error(f"Failed to setup turbo dependency '{lib_name}': {e}")
                logger.debug(
                    f"Turbo dependency setup error details for '{lib_name}'",
                    exc_info=True,
                )
                # Continue with other libraries even if one fails

        logger.info(f"Successfully set up {len(extracted_paths)} turbo dependencies")
        return extracted_paths

    def download_platform(self, platform_name: str) -> Path:
        """Download a platform from GitHub and extract it to cache.

        Args:
            platform_name: Name of the platform to download

        Returns:
            Path to the extracted platform directory

        Raises:
            Exception: If download or extraction fails
        """
        # Normalize platform name
        normalized_name = platform_name.lower()

        # Check if platform is already cached locally
        platform_dir = self.platform_cache_dir / normalized_name
        if platform_dir.exists():
            logger.debug(f"Platform '{platform_name}' already cached at {platform_dir}")
            return platform_dir

        # Get GitHub URL for platform
        if normalized_name not in self.platform_mappings:
            raise ValueError(
                f"Platform '{platform_name}' not supported. "
                f"Known platforms: {list(self.platform_mappings.keys())}"
            )

        github_url = f"https://github.com/{self.platform_mappings[normalized_name]}"

        try:
            # Use global cache for framework download
            logger.info(
                f"Downloading platform '{platform_name}' from {github_url} using global cache"
            )
            global_cache_path = self.global_cache.get_or_download_framework(github_url)

            # Extract directly from global cache to local cache (no symlinks)
            if platform_dir.exists():
                shutil.rmtree(platform_dir)

            # Always copy the directory to avoid symlink issues
            logger.info(
                f"Extracting platform '{platform_name}' from global cache to local cache"
            )
            shutil.copytree(global_cache_path, platform_dir)
            logger.info(f"Platform '{platform_name}' extracted to {platform_dir}")

            return platform_dir

        except Exception as e:
            logger.error(
                f"Failed to download platform '{platform_name}' using global cache: {e}"
            )
            raise

    def extract_platform(self, platform_name: str, target_project_dir: Path) -> Path:
        """Extract a platform directly into a project's platforms directory.

        Args:
            platform_name: Name of the platform to extract
            target_project_dir: Project directory where to extract the platform

        Returns:
            Path to the extracted platform in the project

        Raises:
            Exception: If extraction fails
        """
        # Download platform if not cached
        platform_source = self.download_platform(platform_name)

        # Create platforms directory in project if it doesn't exist
        project_platforms_dir = target_project_dir / "platforms"
        project_platforms_dir.mkdir(exist_ok=True)

        # Extract directly to project platforms directory
        normalized_name = platform_name.lower()
        extract_target = project_platforms_dir / normalized_name

        # Remove existing directory if it exists
        if extract_target.exists():
            shutil.rmtree(extract_target)

        # Copy the platform directly (no symlinks)
        logger.info(f"Extracting platform '{platform_name}' to {extract_target}")
        shutil.copytree(platform_source, extract_target)
        logger.info(f"Platform '{platform_name}' extracted to {extract_target}")
        return extract_target
