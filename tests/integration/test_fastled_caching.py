"""Integration tests for FastLED library caching functionality."""

import logging
import subprocess
import tempfile
from pathlib import Path
from unittest import TestCase

logger = logging.getLogger(__name__)


class FastLEDCachingTest(TestCase):
    """Test FastLED library caching functionality."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.test_dir = Path(tempfile.mkdtemp())
        self.cache_dir = self.test_dir / ".tpo"
        self.blink_example = Path("tests/test_data/examples/Blink").resolve()

    def tearDown(self) -> None:
        """Clean up test environment."""
        import shutil

        if self.test_dir.exists():
            shutil.rmtree(self.test_dir)

    def test_fastled_archive_creation(self) -> None:
        """Test that FastLED archive is created after successful build."""
        # First build - should create the archive
        cmd = f'tpo "{self.blink_example}" --native --cache "{self.cache_dir}"'

        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,  # 5 minutes timeout
        )

        # Build should succeed
        self.assertEqual(
            result.returncode, 0, f"Build failed: {result.stdout}\n{result.stderr}"
        )

        # Check if archive was created
        archive_dir = self.cache_dir / "lib_archives" / "native"
        self.assertTrue(archive_dir.exists(), "Archive directory should exist")

        # Look for FastLED archive
        archives = list(archive_dir.glob("fastled-*.a"))
        self.assertEqual(
            len(archives),
            1,
            f"Expected exactly one FastLED archive, found {len(archives)}",
        )

        archive_path = archives[0]
        self.assertGreater(
            archive_path.stat().st_size, 1000, "Archive should have reasonable size"
        )

        logger.info(
            f"FastLED archive created: {archive_path} ({archive_path.stat().st_size} bytes)"
        )

    def test_fastled_cache_reuse(self) -> None:
        """Test that cached FastLED archive is reused in subsequent builds."""
        # First build - create the archive
        cmd = f'tpo "{self.blink_example}" --native --cache "{self.cache_dir}"'

        result1 = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        self.assertEqual(
            result1.returncode,
            0,
            f"First build failed: {result1.stdout}\n{result1.stderr}",
        )

        # Record first build time
        first_build_time = result1.stdout.count("Compiling")

        # Clear the build directory to force a rebuild
        # But keep the archive cache
        build_dirs = list(self.cache_dir.glob("*/src"))
        for build_dir in build_dirs:
            parent = build_dir.parent
            if (parent / ".pio").exists():
                import shutil

                shutil.rmtree(parent / ".pio")

        # Second build - should use cached archive
        result2 = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        self.assertEqual(
            result2.returncode,
            0,
            f"Second build failed: {result2.stdout}\n{result2.stderr}",
        )

        # Check that cached library was used
        self.assertIn(
            "Using cached FastLED library archive",
            result2.stdout,
            "Should report using cached library",
        )
        self.assertIn(
            "Configured to use cached fastled library",
            result2.stdout,
            "Extra script should report cached library usage",
        )

        # Second build should compile fewer files (no FastLED sources)
        second_build_time = result2.stdout.count("Compiling")
        self.assertLess(
            second_build_time,
            first_build_time,
            f"Second build should compile fewer files: {second_build_time} vs {first_build_time}",
        )

    def test_force_rebuild_ignores_cache(self) -> None:
        """Test that --force-rebuild ignores cached archives."""
        # First build - create the archive
        cmd1 = f'tpo "{self.blink_example}" --native --cache "{self.cache_dir}"'

        result1 = subprocess.run(
            cmd1,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        self.assertEqual(result1.returncode, 0, "First build failed")

        # Force rebuild - should not use cache
        cmd2 = f'tpo "{self.blink_example}" --native --cache "{self.cache_dir}" --clean'

        result2 = subprocess.run(
            cmd2,
            shell=True,
            capture_output=True,
            text=True,
            timeout=300,
        )

        self.assertEqual(result2.returncode, 0, "Force rebuild failed")

        # Should NOT report using cached library
        self.assertNotIn(
            "Using cached FastLED library archive",
            result2.stdout,
            "Force rebuild should not use cached library",
        )
