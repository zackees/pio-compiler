"""Unit tests for cache manager file locking functionality."""

import shutil
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Tuple

from filelock import Timeout

from pio_compiler.cache_manager import CacheManager

from . import TimedTestCase


class CacheLockingTest(TimedTestCase):
    """Test the cache manager file locking functionality."""

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

[env:native]
platform = platformio/native
lib_deps = FastLED
"""

    def tearDown(self) -> None:
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_lock_file_location(self):
        """Test that lock files are created alongside cache directories."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Get the lock file path
        expected_lock_path = entry.cache_dir.parent / f"{entry.cache_dir.name}.lock"
        self.assertEqual(entry.lock_file, expected_lock_path)

        # The lock file should be next to the cache directory, not inside it
        self.assertEqual(entry.lock_file.parent, entry.cache_dir.parent)
        self.assertTrue(entry.lock_file.name.endswith(".lock"))

    def test_basic_locking(self):
        """Test basic lock acquisition and release."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Initially no lock should exist
        self.assertFalse(entry.lock_file.exists())

        # Acquire lock
        lock = entry.acquire_lock()
        self.assertTrue(lock.is_locked)
        self.assertTrue(entry.lock_file.exists())

        # Release lock
        entry.release_lock()
        self.assertFalse(lock.is_locked)

    def test_context_manager_locking(self):
        """Test that cache entry can be used as a context manager for locking."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        self.assertFalse(entry.lock_file.exists())

        with entry:
            # Inside context, lock should be held
            self.assertTrue(entry.get_lock().is_locked)
            self.assertTrue(entry.lock_file.exists())

        # Outside context, lock should be released
        self.assertFalse(entry.get_lock().is_locked)

    def test_concurrent_access_blocking(self):
        """Test that concurrent access to the same cache entry is properly blocked."""
        start_time = time.time()

        def worker(worker_id: int, delay: float) -> Tuple[int, float, float]:
            """Worker function that acquires lock, does work, then releases."""
            # Get a fresh cache entry (simulates separate processes/threads)
            worker_entry = self.cache_manager.get_cache_entry(
                self.source_dir, "native", self.test_platformio_ini
            )

            with worker_entry:
                work_start = time.time()
                time.sleep(delay)  # Simulate work
                work_end = time.time()

            return worker_id, work_start - start_time, work_end - start_time

        # Start two workers that will compete for the same cache lock
        with ThreadPoolExecutor(max_workers=2) as executor:
            future1 = executor.submit(worker, 1, 0.5)  # Worker 1: 0.5s work
            future2 = executor.submit(worker, 2, 0.3)  # Worker 2: 0.3s work

            result1 = future1.result(timeout=5)
            result2 = future2.result(timeout=5)

        # Both workers should complete
        self.assertEqual(len([result1, result2]), 2)

        # The workers should not have overlapped (one should start after the other finishes)
        worker1_id, worker1_start, worker1_end = result1
        worker2_id, worker2_start, worker2_end = result2

        # Determine which worker went first
        if worker1_start < worker2_start:
            first_worker, first_end = worker1_id, worker1_end
            second_worker, second_start = worker2_id, worker2_start
        else:
            first_worker, first_end = worker2_id, worker2_end
            second_worker, second_start = worker1_id, worker1_start

        # Second worker should start after first worker finishes
        # Allow small timing tolerance
        self.assertGreaterEqual(
            second_start,
            first_end - 0.1,
            f"Worker {second_worker} started before worker {first_worker} finished",
        )

    def test_lock_timeout(self):
        """Test that lock acquisition times out appropriately."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Acquire lock in main thread
        with entry:
            # Try to acquire the same lock from another cache entry instance with short timeout
            another_entry = self.cache_manager.get_cache_entry(
                self.source_dir, "native", self.test_platformio_ini
            )

            start_time = time.time()
            with self.assertRaises(Timeout):
                another_entry.acquire_lock(timeout=0.5)

            elapsed = time.time() - start_time
            # Should timeout in approximately 0.5 seconds
            self.assertGreater(elapsed, 0.4)
            self.assertLess(elapsed, 1.0)

    def test_different_cache_entries_different_locks(self):
        """Test that different cache entries have different locks."""
        entry1 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Different platform should get different lock
        entry2 = self.cache_manager.get_cache_entry(
            self.source_dir, "uno", self.test_platformio_ini
        )

        # Different platformio.ini content should get different lock
        different_ini = self.test_platformio_ini + "\nbuild_flags = -DTEST"
        entry3 = self.cache_manager.get_cache_entry(
            self.source_dir, "native", different_ini
        )

        # All should have different lock files
        self.assertNotEqual(entry1.lock_file, entry2.lock_file)
        self.assertNotEqual(entry1.lock_file, entry3.lock_file)
        self.assertNotEqual(entry2.lock_file, entry3.lock_file)

        # Should be able to acquire all locks simultaneously
        with entry1:
            with entry2:
                with entry3:
                    # All three locks should be held
                    self.assertTrue(entry1.get_lock().is_locked)
                    self.assertTrue(entry2.get_lock().is_locked)
                    self.assertTrue(entry3.get_lock().is_locked)

    def test_lock_cleanup_on_exception(self):
        """Test that locks are properly released even when exceptions occur."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        # Initially no lock
        self.assertFalse(entry.get_lock().is_locked)

        try:
            with entry:
                # Lock should be acquired
                self.assertTrue(entry.get_lock().is_locked)
                # Raise an exception
                raise ValueError("Test exception")
        except ValueError:
            pass

        # Lock should be released despite the exception
        self.assertFalse(entry.get_lock().is_locked)

    def test_multiple_access_same_cache_entry(self):
        """Test multiple sequential access to the same cache entry works correctly."""
        entry = self.cache_manager.get_cache_entry(
            self.source_dir, "native", self.test_platformio_ini
        )

        for i in range(3):
            with entry:
                # Should be able to acquire lock multiple times
                self.assertTrue(entry.get_lock().is_locked)
                time.sleep(0.1)  # Small delay to simulate work

            # Lock should be released after each use
            self.assertFalse(entry.get_lock().is_locked)

    def test_stress_test_concurrent_access(self):
        """Stress test with many concurrent workers accessing the same cache."""
        num_workers = 10

        def stress_worker(worker_id: int) -> int:
            """Worker that acquires lock, does brief work, releases."""
            worker_entry = self.cache_manager.get_cache_entry(
                self.source_dir, "native", self.test_platformio_ini
            )

            with worker_entry:
                time.sleep(0.05)  # Brief work
                return worker_id

        # Run many workers concurrently
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(stress_worker, i) for i in range(num_workers)]
            results = [future.result(timeout=10) for future in futures]

        # All workers should complete successfully
        self.assertEqual(len(results), num_workers)
        self.assertEqual(sorted(results), list(range(num_workers)))


if __name__ == "__main__":
    unittest.main()
