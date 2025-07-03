import subprocess
import sys
import unittest
from pathlib import Path

_ENABLE = False


class CliFailureTest(unittest.TestCase):
    """Ensure that the CLI returns **non-zero** when the build fails."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def test_build_failure_exit_code(self) -> None:
        """Run the CLI in a *subprocess* and assert that the exit code indicates failure."""

        project_root = Path(__file__).resolve().parent.parent

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

        if result.returncode == 0:  # pragma: no cover – dump logs to aid debugging
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr, file=sys.stderr)

        if not _ENABLE:
            self.assertNotEqual(
                result.returncode,
                0,
                "CLI returned zero exit code despite a compilation failure",
            )
        else:
            self.assertEqual(
                result.returncode,
                0,
                "CLI returned zero exit code despite a compilation failure",
            )


if __name__ == "__main__":
    unittest.main()
