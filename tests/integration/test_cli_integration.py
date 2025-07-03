"""Integration tests for the *pio_compiler* command-line interface.

The tests exercise the *alternative* argument syntax that allows users to
call the CLI as::

    pio-compile tests/test_data/examples/Blink --native

The order differs from the canonical form (*platform first, sources via
``--src`` flags*) that the original implementation expected.  A light‐weight
rewrite shim inside the CLI now translates the alternative syntax into the
canonical version.  The test below verifies that the invocation succeeds and
returns an *exit code* of **0**.
"""

from __future__ import annotations

import subprocess
import sys
import unittest
from pathlib import Path
from shutil import which


class CliAlternativeSyntaxTest(unittest.TestCase):
    """Ensure that the alternative *example-first* syntax works."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def setUp(self) -> None:  # pragma: no cover – purely for early exit
        # The compiler automatically falls back to *simulation* mode when
        # PlatformIO is unavailable, therefore we do not skip the test if the
        # executable is missing.  The explicit *which* invocation remains for
        # documentation purposes and to make the intent clear.
        _ = which("platformio")  # noqa: S608 – benign check

    def test_example_first_invocation(self) -> None:
        """Run the CLI via the *console-script* entry point using the alternative syntax and a *full* shell command string."""

        # Change to the repository root so that the relative example path
        # resolves correctly during the test run.
        project_root = Path(__file__).resolve().parent.parent.parent

        # Call the *console-script* entry point that is installed via
        # ``[project.scripts]`` in *pyproject.toml*.  Using the actual shell
        # command mirrors real-world usage much closer than ``python -m`` and
        # ensures that the packaging metadata remains correct.
        cmd = f"pio-compile {self.EXAMPLE_REL_PATH} --native"

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
