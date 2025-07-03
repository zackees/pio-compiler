"""Unit tests for the cache manager module."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from pio_compiler.cache_manager import CacheManager, InvalidCacheNameError


class CacheManagerTest(unittest.TestCase):
    """Test the cache manager functionality."""

    def setUp(self) -> None:
        """Set up test environment with temporary cache directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_manager = CacheManager(cache_root=self.temp_dir / "test_cache")

        # Create a fake source path for testing
        self.source_dir = self.temp_dir / "test_project"
        self.source_dir.mkdir()
        (self.source_dir / "test.ino").write_text("// test sketch")

    def tearDown(self) -> None:
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_creation(self):
        """Test creating a cache entry with human-readable name."""
        entry = self.cache_manager.get_cache_entry(self.source_dir, "native")

        # Check that the name is human-readable
        self.assertEqual(entry.name, "test_project-native")
        self.assertEqual(entry.project_name, "test_project")
        self.assertEqual(entry.platform, "native")

        # Check that the cache directory was created
        self.assertTrue(entry.cache_dir.exists())
        self.assertTrue(entry.metadata_file.exists())

    def test_cache_entry_metadata(self):
        """Test that cache metadata is properly saved and loaded."""
        entry = self.cache_manager.get_cache_entry(self.source_dir, "uno")

        # Check metadata was saved
        metadata = entry.load_metadata()
        self.assertEqual(metadata["project_name"], "test_project")
        self.assertEqual(metadata["platform"], "uno")
        self.assertEqual(metadata["source_path"], str(self.source_dir))
        self.assertIn("created_at", metadata)
        self.assertIn("last_accessed", metadata)

    def test_cache_hit_detection(self):
        """Test that cache hits are properly detected."""
        # First access - should be a miss
        entry1 = self.cache_manager.get_cache_entry(self.source_dir, "native")
        self.assertTrue(entry1.exists)  # exists after creation

        # Second access - should be a hit
        entry2 = self.cache_manager.get_cache_entry(self.source_dir, "native")
        self.assertTrue(entry2.exists)
        self.assertEqual(entry1.cache_dir, entry2.cache_dir)

    def test_different_platforms_different_cache(self):
        """Test that different platforms get different cache directories."""
        entry_native = self.cache_manager.get_cache_entry(self.source_dir, "native")
        entry_uno = self.cache_manager.get_cache_entry(self.source_dir, "uno")

        self.assertNotEqual(entry_native.cache_dir, entry_uno.cache_dir)
        self.assertEqual(entry_native.name, "test_project-native")
        self.assertEqual(entry_uno.name, "test_project-uno")

    def test_invalid_name_validation(self):
        """Test that invalid names raise InvalidCacheNameError."""
        # Test invalid characters in project name
        with self.assertRaises(InvalidCacheNameError) as context:
            # Create a temp directory with a valid name first
            valid_dir = self.temp_dir / "valid_project"
            valid_dir.mkdir()
            # Try to use it with an invalid platform name containing <>
            self.cache_manager.get_cache_entry(valid_dir, "platform<>name")

        self.assertIn("invalid characters", str(context.exception))

        # Test reserved Windows names
        valid_dir2 = self.temp_dir / "another_project"
        valid_dir2.mkdir()
        with self.assertRaises(InvalidCacheNameError) as context:
            self.cache_manager.get_cache_entry(valid_dir2, "CON")

        self.assertIn("reserved name", str(context.exception))

        # Test empty names
        valid_dir3 = self.temp_dir / "third_project"
        valid_dir3.mkdir()
        with self.assertRaises(InvalidCacheNameError) as context:
            self.cache_manager.get_cache_entry(valid_dir3, "")

        self.assertIn("empty", str(context.exception))

    def test_name_pre_sanitization(self):
        """Test that valid names with minor issues are pre-sanitized successfully."""
        # Test that spaces and common separators are replaced with underscores
        valid_dir = self.temp_dir / "my project"  # spaces in directory name
        valid_dir.mkdir()

        entry = self.cache_manager.get_cache_entry(valid_dir, "my platform")

        # Should have underscores instead of spaces
        self.assertEqual(entry.name, "my_project-my_platform")
        self.assertTrue(entry.cache_dir.exists())

    def test_list_cache_entries(self):
        """Test listing all cache entries."""
        # Create several cache entries
        self.cache_manager.get_cache_entry(self.source_dir, "native")
        self.cache_manager.get_cache_entry(self.source_dir, "uno")

        source2 = self.temp_dir / "other_project"
        source2.mkdir()
        self.cache_manager.get_cache_entry(source2, "teensy30")

        entries = self.cache_manager.list_cache_entries()
        self.assertEqual(len(entries), 3)

        entry_names = {entry.name for entry in entries}
        expected_names = {
            "test_project-native",
            "test_project-uno",
            "other_project-teensy30",
        }
        self.assertEqual(entry_names, expected_names)

    def test_cleanup_old_entries(self):
        """Test cleanup of old cache entries."""
        # Create several cache entries
        entries = []
        for i in range(5):
            source = self.temp_dir / f"project_{i}"
            source.mkdir()
            entry = self.cache_manager.get_cache_entry(source, "native")
            entries.append(entry)

        # Verify all entries exist
        self.assertEqual(len(self.cache_manager.list_cache_entries()), 5)

        # Cleanup with max_entries=3
        self.cache_manager.cleanup_old_entries(max_entries=3, max_age_days=30)

        # Should have only 3 entries left
        remaining_entries = self.cache_manager.list_cache_entries()
        self.assertEqual(len(remaining_entries), 3)

    def test_migrate_old_cache_entries(self):
        """Test migration of old hash-based cache directories."""
        # Create a fake old-style cache directory
        old_cache_dir = self.cache_manager.cache_root / "bd255b826d41"
        old_cache_dir.mkdir(parents=True)

        # Create some fake project structure in the old cache
        project_dir = old_cache_dir / "TestProject"
        project_dir.mkdir()
        (project_dir / "TestProject.ino").write_text("// test")

        # Create PlatformIO build structure to indicate platform
        pio_build_dir = old_cache_dir / ".pio" / "build" / "native"
        pio_build_dir.mkdir(parents=True)

        # Run migration
        self.cache_manager.migrate_old_cache_entries()

        # Check that old directory was renamed to new format
        self.assertFalse(old_cache_dir.exists())
        new_cache_dir = self.cache_manager.cache_root / "TestProject-native"
        self.assertTrue(new_cache_dir.exists())

        # Check that metadata was created
        metadata_file = new_cache_dir / ".cache_metadata.json"
        self.assertTrue(metadata_file.exists())

        metadata = json.loads(metadata_file.read_text())
        self.assertEqual(metadata["project_name"], "TestProject")
        self.assertEqual(metadata["platform"], "native")

    def test_cleanup_all(self):
        """Test cleanup of all cache entries."""
        # Create some cache entries
        self.cache_manager.get_cache_entry(self.source_dir, "native")
        self.cache_manager.get_cache_entry(self.source_dir, "uno")

        # Verify cache directory exists and has content
        self.assertTrue(self.cache_manager.cache_root.exists())
        self.assertGreater(len(list(self.cache_manager.cache_root.iterdir())), 0)

        # Cleanup all
        self.cache_manager.cleanup_all()

        # Verify cache directory was removed
        self.assertFalse(self.cache_manager.cache_root.exists())


if __name__ == "__main__":
    unittest.main()
