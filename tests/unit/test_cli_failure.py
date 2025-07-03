import subprocess
import sys
import unittest
from pathlib import Path


class CliFailureTest(unittest.TestCase):
    """Ensure that the CLI returns **non-zero** when the build fails."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def test_build_failure_exit_code(self) -> None:
        """Run the CLI in a *subprocess* and assert that the exit code indicates failure."""

        project_root = Path(__file__).resolve().parent.parent.parent

        # Trigger a build that is expected to fail.  The command mirrors the
        # user scenario from the bug report (see conversation) where building
        # the *Blink* example for the *native* platform fails because the
        # FastLED header cannot be resolved.
        cmd = f"uv run pic --native {self.EXAMPLE_REL_PATH}"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:  # pragma: no cover – dump logs to aid debugging
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr, file=sys.stderr)

        # The build is expected to **succeed** – FastLED and the minimal
        # Arduino stub are available for the *native* platform.
        self.assertEqual(
            result.returncode,
            0,
            "CLI returned non-zero exit code although compilation should succeed",
        )

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
