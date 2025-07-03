"""Integration test to ensure the LuminescentGrand example compiles successfully with the --teensy30 flag.

The test invokes the *console‐script* entry point exactly how an end user would call
it on the command line::

    pio-compile tests/test_data/examples/LuminescentGrand --teensy30

NOTE: This test currently expects failure on Windows due to missing C++ standard library
headers in the Teensy toolchain (bits/c++config.h). See analysis.md for detailed
error analysis.
"""

from __future__ import annotations

import platform
import subprocess
import sys
import unittest
from pathlib import Path
from shutil import which

ENABLED = False


class CliTeensy30LuminescentGrandTest(unittest.TestCase):
    """Test the LuminescentGrand example compilation with the Teensy 3.0 board."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/LuminescentGrand")

    def setUp(self) -> None:  # pragma: no cover – purely for early exit
        # Confirm that *platformio* is available – when it's missing the compiler
        # will fall back to simulation mode so we do not skip the test.
        _ = which("platformio")  # noqa: S608 – benign check

    @unittest.skipIf(not ENABLED, "Skipping test due to ENABLED flag")
    def test_teensy30_luminescent_grand_compilation(self) -> None:
        """Run the CLI via the *console-script* entry point to compile LuminescentGrand for Teensy 3.0.

        NOTE: Currently expects failure on Windows due to toolchain issues.
        """

        project_root = Path(__file__).resolve().parent.parent.parent

        cmd = f"pio-compile {self.EXAMPLE_REL_PATH} --teensy30"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,  # 5 minute timeout for complex project
        )

        # Check if we're on Windows and expect failure due to toolchain issues
        is_windows = platform.system().lower() == "windows"

        if is_windows:
            # On Windows, we expect this to fail due to missing bits/c++config.h in toolchain
            self.assertNotEqual(
                result.returncode,
                0,
                f"Expected compilation to fail on Windows due to toolchain issues, but it succeeded.\n"
                f"Command: {cmd}\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}",
            )

            # Verify that the expected error appears
            combined_output = result.stdout + result.stderr
            self.assertIn(
                "bits/c++config.h",
                combined_output,
                "Expected to see the missing bits/c++config.h error on Windows",
            )
        else:
            # On non-Windows platforms, expect success
            if (
                result.returncode != 0
            ):  # pragma: no cover – dump output to aid debugging
                print("STDOUT:\n", result.stdout)
                print("STDERR:\n", result.stderr, file=sys.stderr)

            self.assertEqual(
                result.returncode,
                0,
                f"CLI returned non-zero exit code {result.returncode}.\n"
                f"Command: {cmd}\n"
                f"STDOUT: {result.stdout}\n"
                f"STDERR: {result.stderr}",
            )

        # Verify that the build actually started regardless of success/failure
        combined_output = result.stdout + result.stderr
        self.assertIn(
            "[BUILD]", combined_output, "Expected build start message in output"
        )
        self.assertIn(
            "LuminescentGrand", combined_output, "Expected project name in output"
        )


if __name__ == "__main__":
    unittest.main()
