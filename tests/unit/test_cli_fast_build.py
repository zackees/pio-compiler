import re
import shutil
import subprocess
import sys
import time
import unittest
from pathlib import Path


class CliFastBuildIntegrationTest(unittest.TestCase):
    """Verify that the *--fast* flag re-uses a fingerprinted build directory and speeds up warm builds."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def setUp(self) -> None:  # noqa: D401 – imperative mood is fine here
        self.project_root = Path(__file__).resolve().parent.parent.parent
        # Ensure a clean slate by removing the global fast cache directory.
        self.fast_cache_root = self.project_root / ".tpo_fast_cache"
        if self.fast_cache_root.exists():
            shutil.rmtree(self.fast_cache_root, ignore_errors=True)

    def tearDown(self) -> None:  # noqa: D401 – imperative mood is fine here
        # Remove the cache directory to keep the workspace clean so that other
        # tests start from a predictable state.
        if self.fast_cache_root.exists():
            shutil.rmtree(self.fast_cache_root, ignore_errors=True)

    # ------------------------------------------------------------------
    # Actual test logic.
    # ------------------------------------------------------------------
    def test_fast_build_is_cached(self) -> None:
        """Run the CLI twice with *--fast* and assert the 2nd run hits the cache."""

        cmd = f"uv run tpo --fast --native {self.EXAMPLE_REL_PATH}"

        # ------------------------- cold build -------------------------
        t0 = time.time()
        result1 = subprocess.run(
            cmd,
            cwd=self.project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        cold_duration = time.time() - t0

        if result1.returncode != 0:  # pragma: no cover – diagnostic helper
            print("COLD BUILD STDOUT:\n", result1.stdout)
            print("COLD BUILD STDERR:\n", result1.stderr, file=sys.stderr)
        self.assertEqual(result1.returncode, 0, "First build failed")

        # Extract cache directory path from output – the CLI prints a marker
        cache_match = re.search(r"\[FAST\] Using cache directory: (.+)", result1.stdout)
        self.assertIsNotNone(cache_match, "CLI did not report the cache directory")
        assert cache_match is not None  # type checker hint
        cache_dir = Path(cache_match.group(1).strip())
        self.assertTrue(
            cache_dir.exists(), "Cache directory does not exist after first build"
        )
        self.assertGreater(
            len(list(cache_dir.rglob("*"))),
            0,
            "Cache directory is empty after first build",
        )

        # ------------------------- warm build -------------------------
        t1 = time.time()
        result2 = subprocess.run(
            cmd,
            cwd=self.project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        warm_duration = time.time() - t1

        if result2.returncode != 0:  # pragma: no cover – diagnostic helper
            print("WARM BUILD STDOUT:\n", result2.stdout)
            print("WARM BUILD STDERR:\n", result2.stderr, file=sys.stderr)
        self.assertEqual(result2.returncode, 0, "Second build failed")

        # The second build must report a cache *hit*.
        self.assertIn("[FAST] Cache hit", result2.stdout)

        # And it should be at least *somewhat* faster.  Do not be too strict –
        # CI machines are unpredictable.  Require a 20 % speed-up which is easy
        # to achieve even on slow hardware.
        self.assertLess(
            warm_duration,
            cold_duration * 0.8,
            f"Warm build was not faster (cold={cold_duration:.1f}s, warm={warm_duration:.1f}s)",
        )


if __name__ == "__main__":
    unittest.main()
