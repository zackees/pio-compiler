"""Integration test to ensure the *example‐first* CLI syntax works with the --teensy30 flag.

The test invokes the *console‐script* entry point exactly how an end user would call
it on the command line::

    pio-compile tests/test_data/examples/Blink --teensy30

It asserts that the command exits with a *zero* status code which means the build
succeeded.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from shutil import which


class CliTeensy30AlternativeSyntaxTest(unittest.TestCase):
    """Ensure that the alternative *example-first* syntax works for the Teensy 3.0 board."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def setUp(self) -> None:  # pragma: no cover – purely for early exit
        # Confirm that *platformio* is available – when it's missing the compiler
        # will fall back to simulation mode so we do not skip the test.
        _ = which("platformio")  # noqa: S608 – benign check

    def test_teensy30_example_first_invocation(self) -> None:
        """Run the CLI via the *console-script* entry point using the alternative syntax."""

        project_root = Path(__file__).resolve().parent.parent.parent

        cmd = f"pio-compile {self.EXAMPLE_REL_PATH} --teensy30"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:  # pragma: no cover – dump output to aid debugging
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr, file=sys.stderr)

        self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")


if __name__ == "__main__":
    unittest.main()
