"""Turbo dependencies management for pio_compiler.

This module handles downloading libraries from GitHub and symlinking them
into projects without using PlatformIO's lib_deps system.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Dict
from urllib.request import urlopen

logger = logging.getLogger(__name__)


class TurboDependencyManager:
    """Manages turbo dependencies - libraries downloaded and symlinked directly."""

    def __init__(self, cache_dir: Path | None = None):
        """Initialize the turbo dependency manager.

        Args:
            cache_dir: Directory to cache downloaded libraries. Defaults to .tpo/turbo_libs
        """
        if cache_dir is None:
            cache_dir = Path.cwd() / ".tpo" / "turbo_libs"

        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)

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
        # Check if library is already cached
        library_dir = self.cache_dir / library_name.lower()
        if library_dir.exists():
            logger.debug(f"Library '{library_name}' already cached at {library_dir}")
            return library_dir

        # Get GitHub URL and download
        github_url = self.get_github_url(library_name)

        # Try multiple branch names
        branch_names = ["main", "master", "develop"]

        logger.info(f"Downloading library '{library_name}' from {github_url}")

        for branch_name in branch_names:
            zip_url = f"{github_url}/archive/refs/heads/{branch_name}.zip"
            temp_zip_path = None

            try:
                logger.debug(f"Trying branch '{branch_name}' at {zip_url}")

                # Download the zip file
                with tempfile.NamedTemporaryFile(
                    suffix=".zip", delete=False
                ) as temp_file:
                    temp_zip_path = Path(temp_file.name)

                    with urlopen(zip_url) as response:
                        temp_file.write(response.read())

                # Extract the zip file
                with zipfile.ZipFile(temp_zip_path, "r") as zip_ref:
                    # Extract to temporary directory first
                    with tempfile.TemporaryDirectory() as temp_extract_dir:
                        zip_ref.extractall(temp_extract_dir)

                        # Find the extracted directory (usually has format "repo-branch")
                        extract_path = Path(temp_extract_dir)
                        extracted_dirs = [
                            d for d in extract_path.iterdir() if d.is_dir()
                        ]

                        if not extracted_dirs:
                            raise Exception(
                                f"No directories found in extracted zip for {library_name}"
                            )

                        # Use the first (and typically only) directory
                        source_dir = extracted_dirs[0]

                        # Move to final cache location
                        if library_dir.exists():
                            shutil.rmtree(library_dir)
                        shutil.move(str(source_dir), str(library_dir))

                # Clean up temporary zip file
                temp_zip_path.unlink()

                logger.info(
                    f"Library '{library_name}' downloaded and cached at {library_dir}"
                )
                return library_dir

            except Exception as e:
                logger.debug(f"Branch '{branch_name}' failed: {e}")
                # Clean up on failure for this branch
                if temp_zip_path and temp_zip_path.exists():
                    temp_zip_path.unlink()
                if library_dir.exists():
                    shutil.rmtree(library_dir)

                # Continue to next branch
                continue

        # If we get here, all branches failed
        error_msg = f"Failed to download library '{library_name}' from any branch: {branch_names}"
        logger.error(error_msg)
        raise Exception(error_msg)

    def symlink_library(self, library_name: str, target_project_dir: Path) -> Path:
        """Symlink a library into a project's lib directory.

        Args:
            library_name: Name of the library to symlink
            target_project_dir: Project directory where to create the symlink

        Returns:
            Path to the symlinked library in the project

        Raises:
            Exception: If symlinking fails
        """
        # Download library if not cached
        library_source = self.download_library(library_name)

        # Create lib directory in project if it doesn't exist
        project_lib_dir = target_project_dir / "lib"
        project_lib_dir.mkdir(exist_ok=True)

        # Create symlink
        symlink_target = project_lib_dir / library_name.lower()

        # Remove existing symlink/directory if it exists
        if symlink_target.exists() or symlink_target.is_symlink():
            if symlink_target.is_symlink():
                symlink_target.unlink()
            else:
                shutil.rmtree(symlink_target)

        try:
            # Create the symlink
            symlink_target.symlink_to(library_source, target_is_directory=True)
            logger.info(f"Symlinked library '{library_name}' to {symlink_target}")
            return symlink_target
        except OSError as e:
            # On Windows, symlinks might fail due to permissions
            # Fall back to copying the directory
            logger.warning(f"Symlink failed, copying library instead: {e}")
            shutil.copytree(library_source, symlink_target)
            logger.info(f"Copied library '{library_name}' to {symlink_target}")
            return symlink_target

    def setup_turbo_dependencies(
        self, library_names: list[str], project_dir: Path
    ) -> list[Path]:
        """Set up all turbo dependencies for a project.

        Args:
            library_names: List of library names to set up
            project_dir: Project directory

        Returns:
            List of paths to symlinked libraries
        """
        if not library_names:
            return []

        logger.info(f"Setting up turbo dependencies: {library_names}")

        symlinked_paths = []
        for lib_name in library_names:
            try:
                symlink_path = self.symlink_library(lib_name, project_dir)
                symlinked_paths.append(symlink_path)
            except Exception as e:
                logger.error(f"Failed to setup turbo dependency '{lib_name}': {e}")
                # Continue with other libraries even if one fails

        logger.info(f"Successfully set up {len(symlinked_paths)} turbo dependencies")
        return symlinked_paths
