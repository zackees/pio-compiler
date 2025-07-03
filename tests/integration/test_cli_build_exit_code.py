import subprocess
import sys
import unittest
from pathlib import Path


class CliBuildIntegrationTest(unittest.TestCase):
    """Integration test to verify that compiling the *Blink* example for the
    *native* platform succeeds end-to-end via the CLI.

    The test invokes the *console-script* entry point exactly how an end user
    would call it on the command line and therefore executes the full build
    pipeline which can take multiple seconds.  To keep the regular (unit-only)
    test run fast, this test lives in the *integration* suite and is executed
    only when ``bash test --full`` is used.
    """

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def test_build_exit_code_is_zero(self) -> None:
        """Run the CLI in a subprocess and assert that the exit code is zero."""

        project_root = Path(__file__).resolve().parent.parent.parent

        # Compile the Blink example for the *native* platform.  The command
        # mirrors a real user invocation and therefore uses a *full* shell
        # string rather than a pre-split argument list.
        cmd = f"uv run pic --native {self.EXAMPLE_REL_PATH}"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:  # pragma: no cover – helpful log dump
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr, file=sys.stderr)

        # The build is expected to **succeed** – FastLED and the minimal Arduino
        # stub are available for the *native* platform.
        self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")


if __name__ == "__main__":
    unittest.main()
