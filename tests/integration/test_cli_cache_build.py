import shutil
import subprocess
import sys
import unittest
from pathlib import Path


class CliBuildCacheIntegrationTest(unittest.TestCase):
    """Ensure that the global --cache flag injects *build_cache_dir* into the generated project and that
    PlatformIO creates the directory with build artefacts during compilation."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")
    CACHE_DIR_NAME = ".tpo_test_cache"

    def setUp(self) -> None:  # noqa: D401 – simple description
        self.project_root = Path(__file__).resolve().parent.parent.parent
        self.cache_dir = self.project_root / self.CACHE_DIR_NAME
        # Start from a clean state to avoid interference from previous runs
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)

    def tearDown(self) -> None:  # noqa: D401 – simple description
        # Clean up cache directory to keep the workspace tidy
        if self.cache_dir.exists():
            shutil.rmtree(self.cache_dir)

    def test_build_creates_cache_directory(self) -> None:
        """Run the CLI with --cache and assert that the directory is populated."""

        # Invoke the *console‐script* entry point using the *alternative* syntax
        cmd = (
            f"uv run tpo --cache {self.CACHE_DIR_NAME} --native {self.EXAMPLE_REL_PATH}"
        )

        result = subprocess.run(
            cmd,
            cwd=self.project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Dump output when the build fails to aid debugging
        if result.returncode != 0:  # pragma: no cover – helpful context
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr, file=sys.stderr)

        # Compilation is expected to succeed
        self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")

        # The cache directory must exist and contain at least one file
        self.assertTrue(self.cache_dir.exists(), "Cache directory was not created")
        # Check for non-empty directory (any file/sub-directory is enough)
        contents = list(self.cache_dir.rglob("*"))
        self.assertGreater(
            len(contents), 0, "Cache directory is empty – no artefacts were generated"
        )


if __name__ == "__main__":
    unittest.main()
