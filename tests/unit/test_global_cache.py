"""Unit tests for global cache manager with two-stage caching."""

import tempfile
import threading
import unittest
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

from filelock import FileLock

from pio_compiler.global_cache import GlobalCacheManager

from . import TimedTestCase


class GlobalCacheManagerTest(TimedTestCase):
    """Test the global cache manager functionality."""

    def setUp(self) -> None:
        """Set up test environment with temporary cache directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_manager = GlobalCacheManager(
            cache_root=self.temp_dir / "global_cache"
        )

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_parse_github_url_valid(self):
        """Test parsing valid GitHub URLs."""
        domain, owner, repo = self.cache_manager._parse_github_url(
            "https://github.com/fastled/fastled"
        )
        self.assertEqual(domain, "github.com")
        self.assertEqual(owner, "fastled")
        self.assertEqual(repo, "fastled")

    def test_parse_github_url_with_git_suffix(self):
        """Test parsing GitHub URLs with .git suffix."""
        domain, owner, repo = self.cache_manager._parse_github_url(
            "https://github.com/fastled/fastled.git"
        )
        self.assertEqual(domain, "github.com")
        self.assertEqual(owner, "fastled")
        self.assertEqual(repo, "fastled")

    def test_parse_github_url_invalid(self):
        """Test parsing invalid GitHub URLs."""
        with self.assertRaises(ValueError):
            self.cache_manager._parse_github_url("not-a-url")

        with self.assertRaises(ValueError):
            self.cache_manager._parse_github_url("https://github.com/incomplete")

    def test_get_cache_paths(self):
        """Test cache path generation."""
        github_url = "https://github.com/fastled/fastled"
        branch_name = "main"
        commit_hash = "abcdef123456"

        archive_path, archive_lock_path, dir_path, dir_lock_path, done_path = (
            self.cache_manager._get_cache_paths(github_url, branch_name, commit_hash)
        )

        # Check that paths are correctly structured
        self.assertTrue(archive_path.name.endswith(".zip"))
        self.assertTrue(archive_lock_path.name.endswith(".zip.lock"))
        self.assertTrue(dir_path.name.endswith("_dir"))
        self.assertTrue(dir_lock_path.name.endswith("_dir.lock"))
        self.assertTrue(done_path.name.endswith("_dir.done"))

        # Check that all paths are in the same directory
        self.assertEqual(archive_path.parent, archive_lock_path.parent)
        self.assertEqual(archive_path.parent, dir_path.parent)
        self.assertEqual(archive_path.parent, dir_lock_path.parent)
        self.assertEqual(archive_path.parent, done_path.parent)

    def test_commit_hash_generation(self):
        """Test commit hash generation from URL."""
        url1 = "https://github.com/fastled/fastled/archive/refs/heads/main.zip"
        url2 = "https://github.com/fastled/fastled/archive/refs/heads/develop.zip"

        hash1 = self.cache_manager._get_commit_hash_from_zip_url(url1)
        hash2 = self.cache_manager._get_commit_hash_from_zip_url(url2)

        # Hashes should be different for different URLs
        self.assertNotEqual(hash1, hash2)
        # Hashes should be 8 characters long
        self.assertEqual(len(hash1), 8)
        self.assertEqual(len(hash2), 8)

    def _create_test_zip(
        self, zip_path: Path, content_dir_name: str = "test-repo-main"
    ):
        """Create a test zip file with a directory structure."""
        zip_path.parent.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(zip_path, "w") as zip_file:
            # Create a directory structure inside the zip
            zip_file.writestr(f"{content_dir_name}/", "")
            zip_file.writestr(f"{content_dir_name}/README.md", "# Test Repository")
            zip_file.writestr(
                f"{content_dir_name}/src/main.cpp", "int main() { return 0; }"
            )
            zip_file.writestr(f"{content_dir_name}/library.properties", "name=TestLib")

    @patch("pio_compiler.global_cache.urlopen")
    def test_download_archive_success(self, mock_urlopen):
        """Test successful archive download."""
        # Create a test zip file
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path)

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test download
        archive_path = self.temp_dir / "downloaded.zip"
        self.cache_manager._download_archive(
            "https://example.com/test.zip", archive_path
        )

        # Verify archive was downloaded
        self.assertTrue(archive_path.exists())
        self.assertGreater(archive_path.stat().st_size, 0)

    def test_expand_archive_success(self):
        """Test successful archive expansion."""
        # Create a test zip file
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Test expansion
        dir_path = self.temp_dir / "expanded"
        self.cache_manager._expand_archive(test_zip_path, dir_path)

        # Verify expansion
        self.assertTrue(dir_path.exists())
        self.assertTrue((dir_path / "README.md").exists())
        self.assertTrue((dir_path / "src" / "main.cpp").exists())
        self.assertTrue((dir_path / "library.properties").exists())

    def test_expansion_completion_markers(self):
        """Test expansion completion markers."""
        dir_path = self.temp_dir / "test_dir"
        done_path = self.temp_dir / "test_dir.done"

        # Initially not complete
        self.assertFalse(self.cache_manager._is_expansion_complete(dir_path, done_path))

        # Create directory but no done file
        dir_path.mkdir()
        self.assertFalse(self.cache_manager._is_expansion_complete(dir_path, done_path))

        # Mark as complete
        self.cache_manager._mark_expansion_complete(done_path)
        self.assertTrue(self.cache_manager._is_expansion_complete(dir_path, done_path))

        # Verify done file content
        self.assertTrue(done_path.exists())
        content = done_path.read_text()
        self.assertIn("completed at", content)

    @patch("pio_compiler.global_cache.urlopen")
    def test_get_or_download_framework_success(self, mock_urlopen):
        """Test successful framework download and caching."""
        # Create a test zip file
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Test download
        github_url = "https://github.com/fastled/fastled"
        result_path = self.cache_manager.get_or_download_framework(github_url, ["main"])

        # Verify result
        self.assertTrue(result_path.exists())
        self.assertTrue(result_path.is_dir())
        self.assertTrue(result_path.name.endswith("_dir"))

        # Verify content was extracted
        self.assertTrue((result_path / "README.md").exists())
        self.assertTrue((result_path / "src" / "main.cpp").exists())

        # Verify completion marker exists
        done_path = result_path.parent / f"{result_path.name}.done"
        self.assertTrue(done_path.exists())

    @patch("pio_compiler.global_cache.urlopen")
    def test_get_or_download_framework_cached(self, mock_urlopen):
        """Test that cached frameworks are returned without re-downloading."""
        # Create a test zip file
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        github_url = "https://github.com/fastled/fastled"

        # First call should download
        result_path1 = self.cache_manager.get_or_download_framework(
            github_url, ["main"]
        )
        self.assertTrue(result_path1.exists())

        # Reset mock to ensure no additional calls
        mock_urlopen.reset_mock()

        # Second call should use cache
        result_path2 = self.cache_manager.get_or_download_framework(
            github_url, ["main"]
        )
        self.assertEqual(result_path1, result_path2)

        # Verify no additional HTTP calls were made
        mock_urlopen.assert_not_called()

    def test_get_or_download_framework_multiple_branches(self):
        """Test framework download with multiple branch attempts."""
        github_url = "https://github.com/nonexistent/repo"

        # Should try multiple branches and fail
        with self.assertRaises(Exception) as context:
            self.cache_manager.get_or_download_framework(
                github_url, ["main", "master", "develop"]
            )

        self.assertIn("Failed to download framework", str(context.exception))
        self.assertIn("tried branches", str(context.exception))

    @patch("pio_compiler.global_cache.urlopen")
    def test_concurrent_access_locking(self, mock_urlopen):
        """Test that concurrent access is properly locked."""
        # Create a test zip file
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        github_url = "https://github.com/fastled/fastled"
        results = []
        errors = []

        def download_worker():
            try:
                result = self.cache_manager.get_or_download_framework(
                    github_url, ["main"]
                )
                results.append(result)
            except Exception as e:
                errors.append(e)

        # Start multiple threads
        threads = []
        for _ in range(3):
            thread = threading.Thread(target=download_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # All should succeed and return the same path
        self.assertEqual(len(errors), 0)
        self.assertEqual(len(results), 3)
        self.assertTrue(all(r == results[0] for r in results))

    @patch("pio_compiler.global_cache.urlopen")
    def test_list_cached_frameworks(self, mock_urlopen):
        """Test listing cached frameworks."""
        # Create test zip files
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Initially empty
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached), 0)

        # Download a framework
        github_url = "https://github.com/fastled/fastled"
        self.cache_manager.get_or_download_framework(github_url, ["main"])

        # Should now be listed
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached), 1)
        self.assertIn(github_url, cached)
        self.assertEqual(len(cached[github_url]), 1)

    @patch("pio_compiler.global_cache.urlopen")
    def test_cleanup_cache(self, mock_urlopen):
        """Test cache cleanup functionality."""
        # Create test zip files
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        github_url = "https://github.com/fastled/fastled"

        # Create multiple versions by modifying the commit hash
        with patch.object(
            self.cache_manager, "_get_commit_hash_from_zip_url"
        ) as mock_hash:
            # Create 3 versions
            for i in range(3):
                mock_hash.return_value = f"hash000{i}"
                self.cache_manager.get_or_download_framework(github_url, ["main"])

        # Should have 3 versions
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached[github_url]), 3)

        # Cleanup keeping only 1 recent
        successfully_removed, failed_to_remove = self.cache_manager.cleanup_cache(
            keep_recent=1
        )

        # Should have removed 2 versions
        self.assertEqual(len(successfully_removed), 2)
        self.assertEqual(len(failed_to_remove), 0)

        # Should have only 1 version left
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached[github_url]), 1)

    def test_cleanup_cache_with_locked_files(self):
        """Test cache cleanup with locked files."""
        # Create a fake cached directory structure
        repo_dir = self.cache_manager.cache_root / "github.com" / "fastled" / "fastled"
        repo_dir.mkdir(parents=True)

        # Create a directory and completion marker
        test_dir = repo_dir / "main-12345678_dir"
        test_dir.mkdir()
        done_file = repo_dir / "main-12345678_dir.done"
        done_file.write_text("completed")

        # Create a lock file and acquire it
        lock_file = repo_dir / "main-12345678_dir.lock"
        lock = FileLock(lock_file)
        lock.acquire()

        try:
            # Attempt cleanup
            successfully_removed, failed_to_remove = self.cache_manager.cleanup_cache(
                keep_recent=0
            )

            # Should fail to remove the locked directory
            self.assertIn(str(test_dir), failed_to_remove)
            self.assertTrue(test_dir.exists())

        finally:
            lock.release()

    @patch("pio_compiler.global_cache.urlopen")
    def test_purge_cache(self, mock_urlopen):
        """Test cache purging functionality."""
        # Create test zip files
        test_zip_path = self.temp_dir / "test.zip"
        self._create_test_zip(test_zip_path, "fastled-main")

        # Mock the HTTP response
        mock_response = Mock()
        mock_response.read.return_value = test_zip_path.read_bytes()
        mock_urlopen.return_value.__enter__.return_value = mock_response

        # Download a framework
        github_url = "https://github.com/fastled/fastled"
        self.cache_manager.get_or_download_framework(github_url, ["main"])

        # Verify cache exists
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached), 1)

        # Purge cache
        successfully_removed, failed_to_remove = self.cache_manager.purge_cache()

        # Should have removed items
        self.assertGreater(len(successfully_removed), 0)
        self.assertEqual(len(failed_to_remove), 0)

        # Cache should be empty
        cached = self.cache_manager.list_cached_frameworks()
        self.assertEqual(len(cached), 0)

    def test_purge_cache_with_locked_files(self):
        """Test cache purging with locked files."""
        # Create a fake cached directory structure
        repo_dir = self.cache_manager.cache_root / "github.com" / "fastled" / "fastled"
        repo_dir.mkdir(parents=True)

        # Create a directory and completion marker
        test_dir = repo_dir / "main-12345678_dir"
        test_dir.mkdir()
        done_file = repo_dir / "main-12345678_dir.done"
        done_file.write_text("completed")

        # Create a lock file and acquire it
        lock_file = repo_dir / "main-12345678_dir.lock"
        lock = FileLock(lock_file)
        lock.acquire()

        try:
            # Attempt purge
            successfully_removed, failed_to_remove = self.cache_manager.purge_cache()

            # Should fail to remove the locked directory
            self.assertIn(str(test_dir), failed_to_remove)
            self.assertTrue(test_dir.exists())

        finally:
            lock.release()

    def test_cache_size_calculation(self):
        """Test cache size calculation."""
        # Initially empty
        size = self.cache_manager.get_cache_size()
        self.assertEqual(size, 0)

        # Create some test files
        test_dir = self.cache_manager.cache_root / "test"
        test_dir.mkdir(parents=True)
        test_file = test_dir / "test.txt"
        test_file.write_text("Hello, World!")

        # Should now have non-zero size
        size = self.cache_manager.get_cache_size()
        self.assertGreater(size, 0)


if __name__ == "__main__":
    unittest.main()
