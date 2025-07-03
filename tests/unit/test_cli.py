"""
Unit test file.
"""

import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from pio_compiler.cli import main

from . import TimedTestCase


class MainTester(TimedTestCase):
    """Main tester class."""

    def test_cli_main(self) -> None:
        """Call the CLI main entry point directly."""
        self.assertEqual(main([]), 0)

    def test_nonexistent_sketch_path_validation(self) -> None:
        """Test that non-existent sketch paths are detected early with proper error handling."""
        from pio_compiler.cli import _run_cli

        # Test with a non-existent path
        exit_code = _run_cli(["examples/NonExistentFolder", "--native"])
        self.assertEqual(
            exit_code, 1, "Should return exit code 1 for non-existent path"
        )

        # Test with multiple paths where one doesn't exist
        exit_code = _run_cli(
            ["tests/test_data/examples/Blink", "examples/NonExistentFolder", "--native"]
        )
        self.assertEqual(
            exit_code, 1, "Should return exit code 1 when any path doesn't exist"
        )

    def test_purge_functionality(self) -> None:
        """Test that --purge clears both global and local caches."""
        from pio_compiler.cli import _run_cli
        from pio_compiler.global_cache import GlobalCacheManager

        # Create temporary directories to simulate caches
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            # Create fake global cache
            fake_global_cache = temp_path / "fake_global_cache"
            fake_global_cache.mkdir()
            (fake_global_cache / "test_file.txt").write_text("test content")

            # Create fake local cache with the expected name
            fake_local_cache = temp_path / ".pio_cache"
            fake_local_cache.mkdir()
            (fake_local_cache / "test_file.txt").write_text("test content")

            # Verify caches exist before purge
            self.assertTrue(fake_global_cache.exists())
            self.assertTrue(fake_local_cache.exists())

            # Mock the cache paths
            def mock_global_cache_init(self, cache_root=None):
                self.cache_root = fake_global_cache

            def mock_purge_cache(self):
                # Mock purge to simulate successful removal
                if fake_global_cache.exists():
                    shutil.rmtree(fake_global_cache)
                return [str(fake_global_cache)], []

            def mock_cwd():
                return temp_path

            cleanup_all_called = False

            def mock_cleanup_all():
                nonlocal cleanup_all_called
                cleanup_all_called = True
                # Simulate cleanup_all removing the local cache
                if fake_local_cache.exists():
                    shutil.rmtree(fake_local_cache)

            with (
                patch.object(GlobalCacheManager, "__init__", mock_global_cache_init),
                patch.object(GlobalCacheManager, "purge_cache", mock_purge_cache),
                patch("pio_compiler.cli.Path.cwd", mock_cwd),
                patch("pio_compiler.cli.cleanup_all", mock_cleanup_all),
            ):

                # Run purge command
                exit_code = _run_cli(["--purge"])

                # Verify exit code is 0 (success)
                self.assertEqual(exit_code, 0, "Purge should return exit code 0")

                # Verify global cache was removed
                self.assertFalse(
                    fake_global_cache.exists(), "Global cache should be removed"
                )

                # Verify cleanup_all was called
                self.assertTrue(
                    cleanup_all_called, "cleanup_all should have been called"
                )

                # Verify local cache was removed by our mock
                self.assertFalse(
                    fake_local_cache.exists(), "Local cache should be removed"
                )


if __name__ == "__main__":
    unittest.main()
