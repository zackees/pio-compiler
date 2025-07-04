"""Unit tests for library archive manager."""

import tempfile
import unittest
from pathlib import Path

from pio_compiler.lib_archive_manager import LibraryArchiveManager


class LibraryArchiveManagerTest(unittest.TestCase):
    """Test cases for LibraryArchiveManager."""

    def setUp(self):
        """Set up test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.cache_root = Path(self.temp_dir)
        self.manager = LibraryArchiveManager(cache_root=self.cache_root)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_fingerprint_generation(self):
        """Test that library fingerprints are generated correctly."""
        fp1 = self.manager._get_library_fingerprint("FastLED", "3.10.1", "native")
        fp2 = self.manager._get_library_fingerprint("FastLED", "3.10.1", "native")
        fp3 = self.manager._get_library_fingerprint("FastLED", "3.10.2", "native")
        fp4 = self.manager._get_library_fingerprint("FastLED", "3.10.1", "uno")

        # Same inputs should produce same fingerprint
        self.assertEqual(fp1, fp2)

        # Different version should produce different fingerprint
        self.assertNotEqual(fp1, fp3)

        # Different platform should produce different fingerprint
        self.assertNotEqual(fp1, fp4)

        # Fingerprint should be 8 characters
        self.assertEqual(len(fp1), 8)

    def test_archive_path_generation(self):
        """Test that archive paths are generated correctly."""
        path = self.manager.get_archive_path("FastLED", "3.10.1", "native")

        # Check path structure
        self.assertEqual(path.parent.name, "native")
        self.assertEqual(path.parent.parent, self.manager.archive_root)

        # Check filename format
        self.assertTrue(path.name.startswith("fastled-3.10.1-"))
        self.assertTrue(path.name.endswith(".a"))

    def test_archive_exists_empty_file(self):
        """Test that empty archive files are detected as invalid."""
        archive_path = self.manager.archive_root / "test.a"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Create empty file
        archive_path.touch()

        # Should be invalid because it's empty
        self.assertFalse(self.manager.archive_exists(archive_path))

    def test_archive_exists_valid_file(self):
        """Test that valid archive files are detected correctly."""
        archive_path = self.manager.archive_root / "test.a"
        archive_path.parent.mkdir(parents=True, exist_ok=True)

        # Create file with some content
        archive_path.write_bytes(b"!<arch>\n" + b"x" * 100)

        # Should be valid
        self.assertTrue(self.manager.archive_exists(archive_path))

    def test_find_library_objects(self):
        """Test finding object files for a library."""
        # Create mock build directory structure
        build_dir = self.cache_root / ".pio" / "build" / "dev"
        lib_dir = build_dir / "lib75f" / "fastled"
        lib_dir.mkdir(parents=True, exist_ok=True)

        # Create some object files
        obj_files = []
        for name in ["test1.o", "test2.o", "subdir/test3.o"]:
            obj_path = lib_dir / name
            obj_path.parent.mkdir(parents=True, exist_ok=True)
            obj_path.touch()
            obj_files.append(obj_path)

        # Find objects
        found = self.manager.find_library_objects(build_dir, "FastLED")

        self.assertEqual(len(found), 3)
        self.assertEqual(set(found), set(obj_files))

    def test_create_archive_empty_list(self):
        """Test that empty object file list returns False."""
        archive_path = self.cache_root / "test.a"

        # Create archive with empty list
        result = self.manager.create_archive_from_objects(
            [], archive_path, ar_tool="ar"
        )

        self.assertFalse(result)

    def test_fingerprint_with_build_flags(self):
        """Test that build flags affect the fingerprint."""
        fp1 = self.manager._get_library_fingerprint(
            "FastLED", "3.10.1", "native", ["--optimize"]
        )
        fp2 = self.manager._get_library_fingerprint(
            "FastLED", "3.10.1", "native", ["--debug"]
        )
        fp3 = self.manager._get_library_fingerprint(
            "FastLED", "3.10.1", "native", ["--optimize"]
        )

        # Different flags should produce different fingerprints
        self.assertNotEqual(fp1, fp2)

        # Same flags should produce same fingerprint
        self.assertEqual(fp1, fp3)

    def test_copy_archive_to_build(self):
        """Test copying archive to build directory."""
        # Create source archive
        archive_path = self.cache_root / "test.a"
        archive_path.write_text("archive content")

        # Target directory
        build_lib_dir = self.cache_root / "build" / "lib"

        # Copy
        result = self.manager.copy_archive_to_build(archive_path, build_lib_dir)

        self.assertTrue(result)

        # Check target exists
        target_path = build_lib_dir / "test.a"
        self.assertTrue(target_path.exists())
        self.assertEqual(target_path.read_text(), "archive content")


if __name__ == "__main__":
    unittest.main()
