"""Unit tests for turbo dependencies management."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pio_compiler.turbo_deps import TurboDependencyManager

from . import TimedTestCase


class TurboDependencyManagerTest(TimedTestCase):
    """Test the turbo dependency manager functionality."""

    def setUp(self) -> None:
        """Set up test environment with temporary cache directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.turbo_manager = TurboDependencyManager(
            cache_dir=self.temp_dir / "turbo_cache"
        )

        # Create a test project directory
        self.project_dir = self.temp_dir / "test_project"
        self.project_dir.mkdir()

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_library_mapping_fastled(self):
        """Test that FastLED maps to the correct GitHub URL."""
        url = self.turbo_manager.get_github_url("FastLED")
        self.assertEqual(url, "https://github.com/fastled/fastled")

    def test_library_mapping_case_insensitive(self):
        """Test that library mappings are case-insensitive."""
        url1 = self.turbo_manager.get_github_url("FastLED")
        url2 = self.turbo_manager.get_github_url("fastled")
        url3 = self.turbo_manager.get_github_url("FASTLED")

        self.assertEqual(url1, url2)
        self.assertEqual(url2, url3)

    def test_unknown_library_fallback(self):
        """Test that unknown libraries get a fallback URL."""
        url = self.turbo_manager.get_github_url("UnknownLibrary")
        self.assertIn("github.com/arduino-libraries/UnknownLibrary", url)

    @patch("pio_compiler.global_cache.urlopen")
    def test_download_library_success(self, mock_urlopen):
        """Test successful library download and extraction."""
        # Create a test zip file with proper structure
        import zipfile

        test_zip_path = self.temp_dir / "test.zip"
        test_zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(test_zip_path, "w") as zip_file:
            zip_file.writestr("fastled-main/", "")
            zip_file.writestr("fastled-main/library.properties", "name=FastLED")
            zip_file.writestr("fastled-main/FastLED.h", "// FastLED header")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test download
        result = self.turbo_manager.download_library("FastLED")

        self.assertTrue(result.exists())
        self.assertEqual(result.name, "fastled")

    def test_setup_empty_dependencies(self):
        """Test that empty dependencies list is handled correctly."""
        result = self.turbo_manager.setup_turbo_dependencies([], self.project_dir)
        self.assertEqual(result, [])

    @patch.object(TurboDependencyManager, "download_library")
    def test_symlink_library(self, mock_download):
        """Test library symlinking functionality."""
        # Create a fake downloaded library
        fake_lib_dir = self.temp_dir / "fake_fastled"
        fake_lib_dir.mkdir()
        (fake_lib_dir / "FastLED.h").write_text("// FastLED header")

        mock_download.return_value = fake_lib_dir

        # Test symlinking
        result = self.turbo_manager.symlink_library("FastLED", self.project_dir)

        # Check that lib directory was created
        lib_dir = self.project_dir / "lib"
        self.assertTrue(lib_dir.exists())

        # Check that symlink was created
        symlink_path = lib_dir / "fastled"
        self.assertTrue(symlink_path.exists())
        self.assertEqual(result, symlink_path)

        # Verify mock was called
        mock_download.assert_called_once_with("FastLED")

    @patch.object(TurboDependencyManager, "symlink_library")
    def test_setup_multiple_dependencies(self, mock_symlink):
        """Test setting up multiple turbo dependencies."""
        mock_symlink.side_effect = [
            self.project_dir / "lib" / "fastled",
            self.project_dir / "lib" / "arduino_json",
        ]

        libraries = ["FastLED", "Arduino_Json"]
        result = self.turbo_manager.setup_turbo_dependencies(
            libraries, self.project_dir
        )

        self.assertEqual(len(result), 2)
        self.assertEqual(mock_symlink.call_count, 2)


if __name__ == "__main__":
    unittest.main()
