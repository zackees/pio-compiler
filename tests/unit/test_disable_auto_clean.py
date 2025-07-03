"""Unit tests for the disable_auto_clean functionality."""

import unittest
from pathlib import Path
from unittest.mock import patch

from pio_compiler import tempdir


class DisableAutoCleanTest(unittest.TestCase):
    """Test that disable_auto_clean parameter controls automatic cleanup."""

    def setUp(self) -> None:
        """Reset the module state before each test."""
        # Reset the global state
        tempdir._TEMP_ROOT = None
        tempdir._AUTO_CLEAN_DISABLED = False

    def tearDown(self) -> None:
        """Clean up after each test."""
        # Clean up any temp directories created during testing
        if tempdir._TEMP_ROOT and tempdir._TEMP_ROOT.exists():
            import shutil

            try:
                shutil.rmtree(tempdir._TEMP_ROOT)
            except (FileNotFoundError, PermissionError):
                pass
        tempdir._TEMP_ROOT = None
        tempdir._AUTO_CLEAN_DISABLED = False

    @patch("atexit.register")
    def test_auto_clean_enabled_by_default(self, mock_atexit_register):
        """Test that auto-clean is enabled by default and registers atexit handler."""

        # Call get_temp_root without disable_auto_clean flag
        temp_root = tempdir.get_temp_root()

        # Verify temp root was created
        self.assertIsInstance(temp_root, Path)
        self.assertTrue(temp_root.exists())

        # Verify atexit handler was registered
        mock_atexit_register.assert_called_once_with(tempdir._cleanup_temp_root)

        # Verify the global flag is False (auto-clean enabled)
        self.assertFalse(tempdir._AUTO_CLEAN_DISABLED)

    @patch("atexit.register")
    def test_auto_clean_disabled_when_requested(self, mock_atexit_register):
        """Test that auto-clean is disabled when requested and doesn't register atexit handler."""

        # Call get_temp_root with disable_auto_clean=True
        temp_root = tempdir.get_temp_root(disable_auto_clean=True)

        # Verify temp root was created
        self.assertIsInstance(temp_root, Path)
        self.assertTrue(temp_root.exists())

        # Verify atexit handler was NOT registered
        mock_atexit_register.assert_not_called()

        # Verify the global flag is True (auto-clean disabled)
        self.assertTrue(tempdir._AUTO_CLEAN_DISABLED)

    @patch("atexit.register")
    def test_mkdtemp_passes_disable_flag(self, mock_atexit_register):
        """Test that mkdtemp passes disable_auto_clean to get_temp_root."""

        # Call mkdtemp with disable_auto_clean=True
        temp_dir = tempdir.mkdtemp(prefix="test_", disable_auto_clean=True)

        # Verify temp directory was created
        self.assertIsInstance(temp_dir, Path)
        self.assertTrue(temp_dir.exists())

        # Verify atexit handler was NOT registered
        mock_atexit_register.assert_not_called()

        # Verify the global flag is True (auto-clean disabled)
        self.assertTrue(tempdir._AUTO_CLEAN_DISABLED)

    def test_cleanup_respects_disable_flag(self):
        """Test that _cleanup_temp_root respects the disable flag."""

        # Set up a temp root with auto-clean disabled
        temp_root = tempdir.get_temp_root(disable_auto_clean=True)
        self.assertTrue(temp_root.exists())

        # Create a test file in the temp directory
        test_file = temp_root / "test.txt"
        test_file.write_text("test content")
        self.assertTrue(test_file.exists())

        # Call the cleanup function directly
        tempdir._cleanup_temp_root()

        # Verify the temp root still exists (cleanup was skipped)
        self.assertTrue(temp_root.exists())
        self.assertTrue(test_file.exists())

    def test_cleanup_works_when_enabled(self):
        """Test that _cleanup_temp_root works normally when auto-clean is enabled."""

        # Set up a temp root with auto-clean enabled (default)
        temp_root = tempdir.get_temp_root(disable_auto_clean=False)
        self.assertTrue(temp_root.exists())

        # Create a test file in the temp directory
        test_file = temp_root / "test.txt"
        test_file.write_text("test content")
        self.assertTrue(test_file.exists())

        # Call the cleanup function directly
        tempdir._cleanup_temp_root()

        # Verify the temp root was removed
        self.assertFalse(temp_root.exists())


if __name__ == "__main__":
    unittest.main()
