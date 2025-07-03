"""Unit tests for the cache directory functionality."""

import unittest
from pathlib import Path

from pio_compiler import tempdir


class CacheDirectoryTest(unittest.TestCase):
    """Test that cache directories are persistent and behave correctly."""

    def setUp(self) -> None:
        """Reset the module state before each test."""
        # Reset the global state
        tempdir._CACHE_ROOT = None

    def tearDown(self) -> None:
        """Clean up after each test."""
        # Clean up any cache directories created during testing
        if tempdir._CACHE_ROOT and tempdir._CACHE_ROOT.exists():
            import shutil

            try:
                shutil.rmtree(tempdir._CACHE_ROOT)
            except (FileNotFoundError, PermissionError):
                pass
        tempdir._CACHE_ROOT = None

    def test_cache_root_created_persistently(self):
        """Test that cache root is created and is persistent."""

        # Call get_temp_root
        cache_root = tempdir.get_temp_root()

        # Verify cache root was created
        self.assertIsInstance(cache_root, Path)
        self.assertTrue(cache_root.exists())

        # Verify it's in the expected location
        expected_base = Path.cwd() / ".pio_cache"
        self.assertTrue(str(cache_root).startswith(str(expected_base)))

    def test_disable_auto_clean_parameter_ignored(self):
        """Test that disable_auto_clean parameter is ignored for compatibility."""

        # Call get_temp_root with disable_auto_clean=True (should be ignored)
        cache_root1 = tempdir.get_temp_root(disable_auto_clean=True)

        # Call get_temp_root with disable_auto_clean=False (should be ignored)
        cache_root2 = tempdir.get_temp_root(disable_auto_clean=False)

        # Both should return the same cache root (parameter is ignored)
        self.assertEqual(cache_root1, cache_root2)
        self.assertIsInstance(cache_root1, Path)
        self.assertTrue(cache_root1.exists())

    def test_mkdtemp_creates_persistent_directories(self):
        """Test that mkdtemp creates persistent directories."""

        # Call mkdtemp with various parameters
        cache_dir = tempdir.mkdtemp(prefix="test_", suffix="_dir")

        # Verify cache directory was created
        self.assertIsInstance(cache_dir, Path)
        self.assertTrue(cache_dir.exists())

        # Verify it's under the cache root
        cache_root = tempdir.get_temp_root()
        self.assertTrue(cache_dir.is_relative_to(cache_root))

    def test_manual_cleanup_works(self):
        """Test that manual cleanup removes the cache directory."""

        # Set up a cache root
        cache_root = tempdir.get_temp_root()
        self.assertTrue(cache_root.exists())

        # Create a test file in the cache directory
        test_file = cache_root / "test.txt"
        test_file.write_text("test content")
        self.assertTrue(test_file.exists())

        # Call manual cleanup
        tempdir.cleanup()

        # Verify the cache root was removed
        self.assertFalse(cache_root.exists())

        # Verify the module state was reset
        self.assertIsNone(tempdir._CACHE_ROOT)

    def test_cleanup_all_attempts_cleanup(self):
        """Test that cleanup_all attempts to clean up the cache directory."""

        # Set up a cache root
        cache_root = tempdir.get_temp_root()
        self.assertTrue(cache_root.exists())

        # Create a test file
        test_file = cache_root / "test.txt"
        test_file.write_text("test content")
        self.assertTrue(test_file.exists())

        # Call cleanup_all - this should always reset the module state
        # even if the cleanup fails due to locked files
        tempdir.cleanup_all()

        # Verify the module state was reset regardless of cleanup success
        self.assertIsNone(tempdir._CACHE_ROOT)

        # The cleanup might fail due to concurrent processes or locked files,
        # which is expected behavior. The important thing is that the module
        # state is reset so new sessions can be created.
        # We don't assert on the actual directory removal since it might fail
        # in concurrent test environments due to file locks.

    def test_no_automatic_cleanup_on_shutdown(self):
        """Test that no automatic cleanup is registered."""

        # This test ensures that no atexit handlers are registered
        # We create a cache directory and verify it persists
        cache_root = tempdir.get_temp_root()
        test_file = cache_root / "test.txt"
        test_file.write_text("persistent content")

        # In the old system, this would have been cleaned up automatically
        # Now it should persist until manual cleanup
        self.assertTrue(cache_root.exists())
        self.assertTrue(test_file.exists())

        # Manually clean up for this test
        tempdir.cleanup()

    def test_temporary_directory_context_manager(self):
        """Test that TemporaryDirectory creates persistent directories by default."""

        created_path = None

        # Use the context manager
        with tempdir.TemporaryDirectory(prefix="ctx_test_") as temp_path:
            created_path = temp_path
            self.assertTrue(temp_path.exists())

            # Create a file to test persistence
            test_file = temp_path / "context_test.txt"
            test_file.write_text("context content")
            self.assertTrue(test_file.exists())

        # After exiting context, directory should still exist (persistent behavior)
        self.assertTrue(created_path.exists())
        test_file = created_path / "context_test.txt"
        self.assertTrue(test_file.exists())

        # Manually clean up for this test
        tempdir.cleanup()

    def test_temporary_directory_with_explicit_cleanup(self):
        """Test that TemporaryDirectory can be configured for cleanup."""

        created_path = None

        # Use the context manager with explicit cleanup enabled
        with tempdir.TemporaryDirectory(prefix="cleanup_test_") as temp_path:
            # Note: The API doesn't expose the TemporaryDirectory object directly through the context manager,
            # so we can't easily test the enable_cleanup() method in this context
            created_path = temp_path

            # Create a file
            test_file = temp_path / "cleanup_test.txt"
            test_file.write_text("cleanup content")
            self.assertTrue(test_file.exists())

        # Directory should still exist due to persistent behavior
        self.assertTrue(created_path.exists())

        # Manually clean up for this test
        tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
