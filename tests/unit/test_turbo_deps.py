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
    @patch("pio_compiler.global_cache.zipfile.ZipFile")
    def test_download_library_success(self, mock_zipfile, mock_urlopen):
        """Test successful library download and extraction."""
        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = b"fake zip content"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Mock zipfile extraction
        mock_zip = Mock()
        mock_zipfile.return_value.__enter__.return_value = mock_zip

        # Create a fake extracted directory structure
        fake_extract_dir = self.temp_dir / "fake_extract"
        fake_extract_dir.mkdir()
        fake_lib_dir = fake_extract_dir / "fastled-main"
        fake_lib_dir.mkdir()
        (fake_lib_dir / "library.properties").write_text("name=FastLED")

        # Mock the extraction to use our fake directory
        def mock_extractall(path):
            import shutil

            shutil.copytree(fake_extract_dir, Path(path) / "fastled-main")

        mock_zip.extractall.side_effect = mock_extractall

        # Test download
        with patch("tempfile.TemporaryDirectory") as mock_tempdir:
            mock_tempdir.return_value.__enter__.return_value = str(
                fake_extract_dir.parent
            )
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
