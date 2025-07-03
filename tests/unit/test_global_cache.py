"""Unit tests for global cache manager."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from pio_compiler.global_cache import GlobalCacheManager


class GlobalCacheManagerTest(unittest.TestCase):
    """Test global cache manager functionality."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_manager = GlobalCacheManager(cache_root=self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_parse_github_url(self):
        """Test GitHub URL parsing."""
        # Test normal GitHub URL
        domain, owner, repo = self.cache_manager._parse_github_url(
            "https://github.com/fastled/fastled"
        )
        self.assertEqual(domain, "github.com")
        self.assertEqual(owner, "fastled")
        self.assertEqual(repo, "fastled")

        # Test GitHub URL with .git suffix
        domain, owner, repo = self.cache_manager._parse_github_url(
            "https://github.com/platformio/platform-native.git"
        )
        self.assertEqual(domain, "github.com")
        self.assertEqual(owner, "platformio")
        self.assertEqual(repo, "platform-native")

        # Test invalid URL
        with self.assertRaises(ValueError):
            self.cache_manager._parse_github_url("invalid-url")

    def test_get_cache_path(self):
        """Test cache path generation."""
        github_url = "https://github.com/fastled/fastled"
        branch_name = "main"
        commit_hash = "abcdef123456789"

        cache_path = self.cache_manager._get_cache_path(
            github_url, branch_name, commit_hash
        )

        expected_path = (
            self.temp_dir / "github.com" / "fastled" / "fastled" / "main-23456789"
        )
        self.assertEqual(cache_path, expected_path)

    def test_get_commit_hash_from_zip_url(self):
        """Test commit hash extraction from zip URL."""
        zip_url = "https://github.com/fastled/fastled/archive/refs/heads/main.zip"
        commit_hash = self.cache_manager._get_commit_hash_from_zip_url(zip_url)

        # Should return 8 character hash
        self.assertEqual(len(commit_hash), 8)
        self.assertIsInstance(commit_hash, str)

    @patch("pio_compiler.global_cache.urlopen")
    @patch("pio_compiler.global_cache.zipfile.ZipFile")
    @patch("pio_compiler.global_cache.tempfile.TemporaryDirectory")
    @patch("pio_compiler.global_cache.tempfile.NamedTemporaryFile")
    def test_download_and_extract(
        self, mock_temp_file, mock_temp_dir, mock_zip_file, mock_urlopen
    ):
        """Test download and extract functionality."""
        # Mock the temporary directory
        mock_temp_dir.return_value.__enter__.return_value = str(
            self.temp_dir / "temp_extract"
        )

        # Create a mock extracted directory
        extracted_dir = self.temp_dir / "temp_extract" / "fastled-main"
        extracted_dir.mkdir(parents=True)
        (extracted_dir / "test_file.txt").write_text("test content")

        # Mock the temporary file
        mock_temp_zip = self.temp_dir / "temp_test.zip"
        mock_temp_zip.write_bytes(b"fake zip content")
        mock_temp_file.return_value.__enter__.return_value.name = str(mock_temp_zip)

        # Mock the zip file
        mock_zip_file.return_value.__enter__.return_value.extractall = Mock()

        # Mock urlopen
        mock_response = Mock()
        mock_response.read.return_value = b"fake zip content"
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test the download
        target_path = self.temp_dir / "target"
        zip_url = "https://github.com/fastled/fastled/archive/refs/heads/main.zip"

        self.cache_manager._download_and_extract(zip_url, target_path)

        # Verify the target directory was created
        self.assertTrue(target_path.exists())

    def test_list_cached_frameworks(self):
        """Test listing cached frameworks."""
        # Create some fake cache entries
        cache_dir1 = (
            self.temp_dir / "github.com" / "fastled" / "fastled" / "main-abcd1234"
        )
        cache_dir2 = (
            self.temp_dir
            / "github.com"
            / "platformio"
            / "platform-native"
            / "main-efgh5678"
        )

        cache_dir1.mkdir(parents=True)
        cache_dir2.mkdir(parents=True)

        # List cached frameworks
        cached = self.cache_manager.list_cached_frameworks()

        # Should have two repositories
        self.assertEqual(len(cached), 2)
        self.assertIn("https://github.com/fastled/fastled", cached)
        self.assertIn("https://github.com/platformio/platform-native", cached)

    def test_get_cache_size(self):
        """Test cache size calculation."""
        # Create some test files
        test_dir = self.temp_dir / "github.com" / "test" / "repo" / "main-12345678"
        test_dir.mkdir(parents=True)

        test_file = test_dir / "test.txt"
        test_file.write_text("test content")

        # Get cache size
        size = self.cache_manager.get_cache_size()
        self.assertGreater(size, 0)


if __name__ == "__main__":
    unittest.main()
