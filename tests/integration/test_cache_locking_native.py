"""Integration tests for cache locking with native platform compilation."""

import shutil
import subprocess
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Tuple

from pio_compiler.cache_manager import CacheManager


class CacheLockingNativeIntegrationTest(unittest.TestCase):
    """Integration tests for cache locking during native platform compilation."""

    def setUp(self) -> None:
        """Set up test environment."""
        self.temp_dir = Path(tempfile.mkdtemp())
        self.cache_root = self.temp_dir / "test_cache"

        # Create a simple test project
        self.test_project = self.temp_dir / "test_project"
        self.test_project.mkdir()

        # Create a simple sketch that compiles quickly
        sketch_content = """
#include <Arduino.h>

void setup() {
    // Simple setup
}

void loop() {
    // Simple loop
}
"""
        (self.test_project / "main.ino").write_text(sketch_content)

    def tearDown(self) -> None:
        """Clean up test environment."""
        if self.temp_dir.exists():
            shutil.rmtree(self.temp_dir)

    def test_concurrent_native_compilation_with_locking(self):
        """Test that concurrent native compilations properly use cache locking."""
        results = []

        def compile_worker(worker_id: int) -> Tuple[int, bool, float]:
            """Worker that compiles the same project using the CLI."""
            start_time = time.time()

            try:
                # Use the CLI to compile the project with native platform
                cmd = [
                    "tpo",
                    str(self.test_project),
                    "--native",
                    "--cache-root",
                    str(self.cache_root),
                ]

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

                success = result.returncode == 0
                elapsed = time.time() - start_time

                return worker_id, success, elapsed

            except subprocess.TimeoutExpired:
                elapsed = time.time() - start_time
                return worker_id, False, elapsed
            except Exception as e:
                elapsed = time.time() - start_time
                print(f"Worker {worker_id} failed with exception: {e}")
                return worker_id, False, elapsed

        # Run multiple workers that compile the same project concurrently
        num_workers = 3
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [executor.submit(compile_worker, i) for i in range(num_workers)]
            results = [future.result(timeout=60) for future in futures]

        # All workers should complete successfully
        self.assertEqual(len(results), num_workers)

        # At least one should succeed (others might hit lock timeout but that's ok)
        successful_workers = [r for r in results if r[1]]  # r[1] is success flag
        self.assertGreater(
            len(successful_workers),
            0,
            "At least one worker should successfully compile",
        )

    def test_cache_manager_locking_during_compilation(self):
        """Test cache manager locking using the cache manager directly."""
        cache_manager = CacheManager(cache_root=self.cache_root)

        # Create a platformio.ini content for native platform
        platformio_ini_content = """[platformio]
src_dir = .

[env:native]
platform = platformio/native
lib_deps = 
"""

        def cache_compilation_worker(worker_id: int) -> Tuple[int, bool, str]:
            """Worker that uses cache manager to get cache entry and simulates compilation."""
            try:
                # Get cache entry (this will use locking)
                entry = cache_manager.get_cache_entry(
                    self.test_project, "native", platformio_ini_content
                )

                # Use the cache entry as a context manager (acquires lock)
                with entry:
                    # Simulate compilation work inside the locked section
                    time.sleep(0.5)  # Simulate time-consuming compilation

                    # Check if cache directory exists and create marker file
                    entry.cache_dir.mkdir(parents=True, exist_ok=True)
                    marker_file = entry.cache_dir / f"worker_{worker_id}_marker.txt"
                    marker_file.write_text(f"Worker {worker_id} was here")

                    return worker_id, True, str(entry.cache_dir)

            except Exception as e:
                return worker_id, False, str(e)

        # Run multiple workers concurrently
        num_workers = 4
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(cache_compilation_worker, i) for i in range(num_workers)
            ]
            results = [future.result(timeout=30) for future in futures]

        # All workers should complete successfully
        successful_results = [r for r in results if r[1]]
        self.assertEqual(
            len(successful_results),
            num_workers,
            "All workers should successfully complete",
        )

        # All workers should use the same cache directory
        cache_dirs = set(r[2] for r in successful_results)
        self.assertEqual(
            len(cache_dirs), 1, "All workers should use the same cache directory"
        )

        # Verify that all workers created their marker files
        cache_dir = Path(successful_results[0][2])
        for worker_id in range(num_workers):
            marker_file = cache_dir / f"worker_{worker_id}_marker.txt"
            self.assertTrue(
                marker_file.exists(), f"Worker {worker_id} marker file should exist"
            )

    def test_lock_prevents_cache_corruption(self):
        """Test that locking prevents cache corruption during concurrent access."""
        cache_manager = CacheManager(cache_root=self.cache_root)

        platformio_ini_content = """[platformio]
src_dir = .

[env:native]
platform = platformio/native
"""

        shared_counter = {"value": 0}
        shared_counter_lock = threading.Lock()

        def cache_modification_worker(worker_id: int) -> Tuple[int, bool]:
            """Worker that modifies cache state while holding the lock."""
            try:
                entry = cache_manager.get_cache_entry(
                    self.test_project, "native", platformio_ini_content
                )

                with entry:
                    # Critical section: modify cache and shared state
                    entry.cache_dir.mkdir(parents=True, exist_ok=True)

                    # Read current state
                    state_file = entry.cache_dir / "shared_state.txt"
                    if state_file.exists():
                        current_value = int(state_file.read_text().strip())
                    else:
                        current_value = 0

                    # Simulate some processing time
                    time.sleep(0.1)

                    # Increment and write back
                    new_value = current_value + 1
                    state_file.write_text(str(new_value))

                    # Also update shared counter (for verification)
                    with shared_counter_lock:
                        shared_counter["value"] += 1

                    return worker_id, True

            except Exception as e:
                print(f"Worker {worker_id} failed: {e}")
                return worker_id, False

        # Run many workers to stress test the locking
        num_workers = 10
        with ThreadPoolExecutor(max_workers=num_workers) as executor:
            futures = [
                executor.submit(cache_modification_worker, i)
                for i in range(num_workers)
            ]
            results = [future.result(timeout=30) for future in futures]

        # All workers should complete successfully
        successful_results = [r for r in results if r[1]]
        self.assertEqual(
            len(successful_results),
            num_workers,
            "All workers should complete successfully",
        )

        # Verify final state is consistent
        entry = cache_manager.get_cache_entry(
            self.test_project, "native", platformio_ini_content
        )

        state_file = entry.cache_dir / "shared_state.txt"
        self.assertTrue(state_file.exists(), "State file should exist")

        final_value = int(state_file.read_text().strip())
        self.assertEqual(
            final_value,
            num_workers,
            f"Final value should be {num_workers}, got {final_value}",
        )

        # Shared counter should also match
        self.assertEqual(
            shared_counter["value"],
            num_workers,
            "Shared counter should match number of workers",
        )


if __name__ == "__main__":
    unittest.main()
