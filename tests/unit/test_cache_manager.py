"""Unit tests for the cache manager module."""

import shutil
import tempfile
import unittest
from pathlib import Path

from filelock import Timeout

from pio_compiler.cache_manager import CacheManager, InvalidCacheNameError

from . import TimedTestCase


class CacheManagerTest(TimedTestCase):
    """Test the cache manager functionality."""

    def setUp(self) -> None:
        """Set up test environment with temporary cache directory."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_manager = CacheManager(cache_root=self.temp_dir / "test_cache")

        # Create a fake source path for testing
        self.source_dir = self.temp_dir / "test_project"
        self.source_dir.mkdir()
        (self.source_dir / "test.ino").write_text("// test sketch")

        # Sample platformio.ini content for testing
        self.test_platformio_ini = """[platformio]
src_dir = src

[env:dev]
platform = platformio/native
lib_deps = FastLED
"""

    def tearDown(self) -> None:
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_cache_entry_creation(self):
        """Test creating a cache entry with platform-fingerprint name."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Check that the name follows platform-fingerprint pattern
        self.assertTrue(entry.name.startswith("native-"))
        self.assertEqual(len(entry.name.split("-")), 2)
        self.assertEqual(len(entry.name.split("-")[1]), 8)  # 8-character fingerprint
        self.assertEqual(entry.platform, "native")

        # Check that the cache directory was created
        self.assertTrue(entry.cache_dir.exists())
        self.assertTrue(entry.metadata_file.exists())

    def test_cache_entry_metadata(self):
        """Test that cache metadata is properly saved and loaded."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "uno", self.test_platformio_ini
        )

        # Check metadata was saved
        metadata = entry.load_metadata()
        self.assertEqual(metadata["platform"], "uno")
        self.assertEqual(metadata["source_path"], str(self.source_dir))
        self.assertIn("fingerprint", metadata)
        self.assertIn("platformio_ini_hash", metadata)
        self.assertIn("created_at", metadata)
        self.assertIn("last_accessed", metadata)

    def test_cache_hit_detection(self):
        """Test that cache hits are properly detected."""
        # First access - should be a miss
        entry1 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        self.assertTrue(entry1.exists)  # exists after creation

        # Second access - should be a hit
        entry2 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        self.assertTrue(entry2.exists)
        self.assertEqual(entry1.cache_dir, entry2.cache_dir)

    def test_different_platforms_different_cache(self):
        """Test that different platforms get different cache directories."""
        entry_native = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        entry_uno = self.cache_manager.get_cache_entry(
            self.source_dir, "uno", self.test_platformio_ini
        )

        self.assertNotEqual(entry_native.cache_dir, entry_uno.cache_dir)
        self.assertTrue(entry_native.name.startswith("native-"))
        self.assertTrue(entry_uno.name.startswith("uno-"))

    def test_different_platformio_content_different_cache(self):
        """Test that different platformio.ini content gets different cache directories."""
        different_ini = """[platformio]
src_dir = src

[env:dev]
platform = atmelavr
board = uno
lib_deps = FastLED
"""

        entry1 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        entry2 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", different_ini
        )

        # Should have different fingerprints due to different content
        self.assertNotEqual(entry1.cache_dir, entry2.cache_dir)
        self.assertNotEqual(entry1.fingerprint, entry2.fingerprint)

    def test_cache_invalidation_on_content_change(self):
        """Test that cache is invalidated when platformio.ini content changes."""
        # Create initial cache entry
        entry1 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        old_cache_dir = entry1.cache_dir

        # Modify platformio.ini content
        modified_ini = self.test_platformio_ini + "\nbuild_flags = -DTEST"

        # Should get a different cache entry
        entry2 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", modified_ini
        )

        self.assertNotEqual(old_cache_dir, entry2.cache_dir)
        self.assertNotEqual(entry1.fingerprint, entry2.fingerprint)

    def test_fingerprint_generation(self):
        """Test that fingerprint generation is consistent and follows expected format."""
        fingerprint1 = self.cache_manager._generate_fingerprint(
            self.test_platformio_ini
        )
        fingerprint2 = self.cache_manager._generate_fingerprint(
            self.test_platformio_ini
        )

        # Should be consistent
        self.assertEqual(fingerprint1, fingerprint2)

        # Should be 8 characters of hex
        self.assertEqual(len(fingerprint1), 8)
        self.assertTrue(all(c in "0123456789abcdef" for c in fingerprint1))

        # Different content should give different fingerprint
        different_content = self.test_platformio_ini + "\n# comment"
        fingerprint3 = self.cache_manager._generate_fingerprint(different_content)
        self.assertNotEqual(fingerprint1, fingerprint3)

    def test_invalid_name_validation(self):
        """Test that invalid names raise InvalidCacheNameError."""
        # Test invalid characters in platform name
        with self.assertRaises(InvalidCacheNameError) as context:
            self.cache_manager.get_cache_entry(
                self.source_dir, "platform<>name", self.test_platformio_ini
            )

        self.assertIn("invalid characters", str(context.exception))

        # Test reserved Windows names
        with self.assertRaises(InvalidCacheNameError) as context:
            self.cache_manager.get_cache_entry(
                self.source_dir, "CON", self.test_platformio_ini
            )

        self.assertIn("reserved name", str(context.exception))

        # Test empty names
        with self.assertRaises(InvalidCacheNameError) as context:
            self.cache_manager.get_cache_entry(
                self.source_dir, "", self.test_platformio_ini
            )

        self.assertIn("empty", str(context.exception))

    def test_name_pre_sanitization(self):
        """Test that valid names with minor issues are pre-sanitized successfully."""
        # Test that spaces and common separators are replaced with underscores
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "my platform", self.test_platformio_ini
        )

        # Should have underscores instead of spaces in platform name
        self.assertTrue(entry.name.startswith("my_platform-"))
        self.assertTrue(entry.cache_dir.exists())

    def test_list_cache_entries(self):
        """Test listing all cache entries."""
        # Create several cache entries
        self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        self.cache_manager.get_cache_entry(
            self.source_dir, "uno", self.test_platformio_ini
        )

        source2 = self.temp_dir / "other_project"
        source2.mkdir()
        self.cache_manager.get_cache_entry(
            source2, "teensy30", self.test_platformio_ini
        )

        entries = self.cache_manager.list_cache_entries()
        self.assertEqual(len(entries), 3)

        # Check that entries have expected platforms
        platforms = {entry.platform for entry in entries}
        expected_platforms = {"native", "uno", "teensy30"}
        self.assertEqual(platforms, expected_platforms)

    def test_cleanup_old_entries(self):
        """Test cleanup of old cache entries."""
        # Create several cache entries with different platformio.ini content to ensure different fingerprints
        entries = []
        for i in range(5):
            source = self.temp_dir / f"project_{i}"
            source.mkdir()
            # Make each entry unique by adding actual content differences (not just comments)
            unique_ini = self.test_platformio_ini + f"\nbuild_flags = -DPROJECT_{i}"
            entry = self.cache_manager.get_cache_entry(source, "native", unique_ini)
            entries.append(entry)

        # Verify all entries exist
        self.assertEqual(len(self.cache_manager.list_cache_entries()), 5)

        # Cleanup with max_entries=3
        self.cache_manager.cleanup_old_entries(max_entries=3, max_age_days=30)

        # Should have only 3 entries left
        remaining_entries = self.cache_manager.list_cache_entries()
        self.assertEqual(len(remaining_entries), 3)

    def test_migrate_old_cache_entries(self):
        """Test migration removes old-format cache directories."""
        # Create a fake old .tpo_fast_cache directory
        old_cache_root = self.cache_manager.cache_root.parent / ".tpo_fast_cache"
        old_cache_root.mkdir()
        old_project_dir = old_cache_root / "TestProject-native"
        old_project_dir.mkdir()
        (old_project_dir / "test.txt").write_text("old cache content")

        # Create a fake old-style cache directory in new location
        old_cache_dir = self.cache_manager.cache_root / "TestProject-native"
        old_cache_dir.mkdir(parents=True)
        (old_cache_dir / "test.txt").write_text("old format cache")

        # Run migration
        self.cache_manager.migrate_old_cache_entries()

        # Check that old .tpo_fast_cache directory was removed
        self.assertFalse(old_cache_root.exists())

        # Check that old format cache in new location was removed
        self.assertFalse(old_cache_dir.exists())

    def test_looks_like_fingerprint_format(self):
        """Test the fingerprint format detection helper."""
        # Valid fingerprint format
        self.assertTrue(
            self.cache_manager._looks_like_fingerprint_format("native-a1b2c3d4")
        )
        self.assertTrue(
            self.cache_manager._looks_like_fingerprint_format("uno-12345678")
        )

        # Invalid fingerprint format
        self.assertFalse(
            self.cache_manager._looks_like_fingerprint_format("TestProject-native")
        )
        self.assertFalse(
            self.cache_manager._looks_like_fingerprint_format("native-toolong")
        )
        self.assertFalse(
            self.cache_manager._looks_like_fingerprint_format("native-short")
        )
        self.assertFalse(
            self.cache_manager._looks_like_fingerprint_format("native-xyz123gh")
        )  # non-hex chars
        self.assertFalse(
            self.cache_manager._looks_like_fingerprint_format("just-one-part")
        )

    def test_cleanup_all(self):
        """Test cleanup of all cache entries."""
        # Create some cache entries
        self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )
        self.cache_manager.get_cache_entry(
            self.source_dir, "uno", self.test_platformio_ini
        )

        # Verify cache directory exists and has content
        self.assertTrue(self.cache_manager.cache_root.exists())
        self.assertGreater(len(list(self.cache_manager.cache_root.iterdir())), 0)

        # Cleanup all
        self.cache_manager.cleanup_all()

        # Verify cache directory was removed
        self.assertFalse(self.cache_manager.cache_root.exists())

    def test_platformio_content_cleaning_comments(self) -> None:
        """Test that semicolon comments are properly removed."""
        content = """[env:uno]
platform = atmelavr ; this is a comment
board = uno ; another comment
framework = arduino"""

        expected = """[env:uno]
platform = atmelavr
board = uno
framework = arduino"""

        cleaned = self.cache_manager._clean_platformio_content(content)
        self.assertEqual(cleaned, expected)

    def test_platformio_content_cleaning_whitespace(self) -> None:
        """Test that lines are properly trimmed."""
        content = """  [env:uno]  
  platform = atmelavr  
  board = uno  
  framework = arduino  """

        expected = """[env:uno]
platform = atmelavr
board = uno
framework = arduino"""

        cleaned = self.cache_manager._clean_platformio_content(content)
        self.assertEqual(cleaned, expected)

    def test_platformio_content_cleaning_double_empty_lines(self) -> None:
        """Test that double empty lines are removed repeatedly."""
        content = """[env:uno]
platform = atmelavr


board = uno



framework = arduino



"""

        expected = """[env:uno]
platform = atmelavr

board = uno

framework = arduino"""

        cleaned = self.cache_manager._clean_platformio_content(content)
        self.assertEqual(cleaned, expected)

    def test_platformio_content_cleaning_complex_case(self) -> None:
        """Test cleaning with comments, whitespace, and double empty lines combined."""
        content = """  [platformio]  ; project config
  build_cache_dir = .cache  ; cache location


  [env:uno]  ; target configuration
  platform = atmelavr ; AVR platform
  board = uno ; Arduino Uno



  framework = arduino ; Arduino framework

  ; Full line comment


  upload_port = COM3 ; Windows port"""

        expected = """[platformio]
build_cache_dir = .cache

[env:uno]
platform = atmelavr
board = uno

framework = arduino

upload_port = COM3"""

        cleaned = self.cache_manager._clean_platformio_content(content)
        self.assertEqual(cleaned, expected)

    def test_platformio_content_cleaning_empty_input(self) -> None:
        """Test cleaning empty or whitespace-only input."""
        self.assertEqual(self.cache_manager._clean_platformio_content(""), "")
        self.assertEqual(self.cache_manager._clean_platformio_content("   "), "")
        self.assertEqual(self.cache_manager._clean_platformio_content("\n\n\n"), "")

    def test_platformio_content_cleaning_only_comments(self) -> None:
        """Test cleaning content that becomes empty after comment removal."""
        content = """; This is a comment
; Another comment
   ; Indented comment"""

        expected = ""

        cleaned = self.cache_manager._clean_platformio_content(content)
        self.assertEqual(cleaned, expected)

    def test_fingerprint_consistency(self) -> None:
        """Test that the same content (after cleaning) produces the same fingerprint."""
        content1 = """[env:uno]
platform = atmelavr ; comment
board = uno"""

        content2 = """  [env:uno]  
  platform = atmelavr  
  board = uno  """

        fingerprint1 = self.cache_manager._generate_fingerprint(content1)
        fingerprint2 = self.cache_manager._generate_fingerprint(content2)

        # Both should produce the same fingerprint since they clean to the same content
        self.assertEqual(fingerprint1, fingerprint2)
        self.assertEqual(len(fingerprint1), 8)
        self.assertEqual(len(fingerprint2), 8)

    def test_fingerprint_different_for_different_content(self) -> None:
        """Test that different content produces different fingerprints."""
        content1 = """[env:uno]
platform = atmelavr
board = uno"""

        content2 = """[env:nano]
platform = atmelavr
board = nano"""

        fingerprint1 = self.cache_manager._generate_fingerprint(content1)
        fingerprint2 = self.cache_manager._generate_fingerprint(content2)

        # Different content should produce different fingerprints
        self.assertNotEqual(fingerprint1, fingerprint2)

    def test_cache_entry_has_lock_file(self) -> None:
        """Test that cache entries have properly configured lock files."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Lock file should be next to cache directory, not inside it
        expected_lock_path = entry.cache_dir.parent / f"{entry.cache_dir.name}.lock"
        self.assertEqual(entry.lock_file, expected_lock_path)
        self.assertTrue(entry.lock_file.name.endswith(".lock"))

    def test_cache_entry_locking_basic(self) -> None:
        """Test basic cache entry locking functionality."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Initially no lock should be held
        self.assertFalse(entry.lock_file.exists())

        # Test context manager usage
        with entry:
            self.assertTrue(entry.get_lock().is_locked)
            self.assertTrue(entry.lock_file.exists())

        # Lock should be released
        self.assertFalse(entry.get_lock().is_locked)

    def test_cache_entry_lock_timeout(self) -> None:
        """Test that cache entry locking properly times out."""
        entry1 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Get another reference to the same cache entry
        entry2 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        with entry1:
            # Should not be able to acquire lock with short timeout
            with self.assertRaises(Timeout):
                entry2.acquire_lock(timeout=0.1)


if __name__ == "__main__":
    unittest.main()
