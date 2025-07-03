"""Integration tests for the *pio_compiler* command-line interface.

The tests exercise the *alternative* argument syntax that allows users to
call the CLI as::

    pio-compile <example> --uno

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

_HERE = Path(__file__).resolve().parent
_PROJECT_ROOT = _HERE.parent


class CliAlternativeSyntaxTest(unittest.TestCase):
    """Ensure that the alternative *example-first* syntax works."""

    def test_example_first_invocation(self) -> None:
        """Run the CLI via *python -m* using the alternative syntax."""

        result = subprocess.run(
            "pio-compile tests/test_data/examples/Blink --native",
            cwd=_PROJECT_ROOT,
            capture_output=True,
            shell=True,
        )

        if result.returncode != 0:  # pragma: no cover – dump output to aid debugging
            print("STDOUT:\n", result.stdout.decode("utf-8"))
            print("STDERR:\n", result.stderr.decode("utf-8"), file=sys.stderr)

        self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")
