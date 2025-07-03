import subprocess
import unittest
from pathlib import Path


class CliFailureTest(unittest.TestCase):
    """Ensure that the CLI returns **non-zero** when the build fails."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    # NOTE: The slow-running build test was moved to the *integration* test
    # suite to keep the default (unit-only) test run fast.  See
    # ``tests/integration/test_cli_build_exit_code.py`` for the migrated test.

    def test_nonexistent_path_error_message(self) -> None:
        """Test that attempting to compile a nonexistent path produces a helpful error message."""
        project_root = Path(__file__).resolve().parent.parent.parent
        nonexistent_path = "tests/test_data/examples/NonexistentProject"

        cmd = f"uv run pic --native {nonexistent_path}"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(
            result.returncode, 0, "Expected non-zero exit code for nonexistent path"
        )

        # Check that the error message is helpful and explains what went wrong
        combined_output = result.stdout + result.stderr
        self.assertIn("Example path does not exist", combined_output)
        self.assertIn(
            "Expected: Either a directory containing .ino files", combined_output
        )
        self.assertIn("Point to a directory:", combined_output)
        self.assertIn("Point to a single file:", combined_output)

    def test_directory_without_ino_files_error_message(self) -> None:
        """Test that attempting to compile a directory without .ino files produces a helpful error message."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Use the tests directory itself, which doesn't contain .ino files
        test_dir = "tests/unit"

        cmd = f"uv run pic --native {test_dir}"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertNotEqual(
            result.returncode,
            0,
            "Expected non-zero exit code for directory without .ino files",
        )

        # Check that the error message explains the problem and provides guidance
        combined_output = result.stdout + result.stderr
        self.assertIn("No Arduino sketch (.ino) files found", combined_output)
        self.assertIn(
            "Expected: A directory containing at least one .ino file", combined_output
        )
        self.assertIn(
            "Found", combined_output
        )  # Should show what files were actually found


if __name__ == "__main__":
    unittest.main()
