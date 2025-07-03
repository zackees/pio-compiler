"""Unit test for LuminescentGrand native compilation scenario.

This test is expected to fail initially and demonstrates the tpo command
working with complex Arduino projects that need additional build flags.
"""

import subprocess
import unittest
from pathlib import Path


class LuminescentGrandNativeTest(unittest.TestCase):
    """Test compilation of LuminescentGrand project for native platform using tpo command."""

    def test_tpo_luminescent_grand_native_compilation(self) -> None:
        """Test that tpo can compile LuminescentGrand with --native flag.

        This test exercises the tpo command (turbo pio compile) with a complex
        Arduino project that requires additional build flags for Arduino.h compatibility.

        Expected to fail initially until the build configuration is properly set up.
        """
        project_root = Path(__file__).resolve().parent.parent.parent
        luminescent_grand_path = "tests/test_data/examples/LuminescentGrand/"

        # Use the tpo command (turbo pio compile) as specified in pyproject.toml
        cmd = f"uv run tpo {luminescent_grand_path} --native"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=300,  # 5 minute timeout for complex project
        )

        # Log output for debugging if the test fails
        if result.returncode != 0:
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr)

        # This test expects the compilation to succeed
        # When initially created, this will fail until build flags are properly configured
        self.assertEqual(
            result.returncode,
            0,
            f"tpo compilation failed with exit code {result.returncode}.\n"
            f"Command: {cmd}\n"
            f"The LuminescentGrand project requires proper Arduino.h include paths "
            f"and FastLED compatibility for native platform compilation.\n"
            f"Expected build flags: -Isrc/pio_compiler/assets\n"
            f"STDOUT: {result.stdout[-1000:] if result.stdout else 'None'}\n"  # Last 1000 chars
            f"STDERR: {result.stderr[-1000:] if result.stderr else 'None'}",  # Last 1000 chars
        )

        # Verify that the build process actually started
        combined_output = result.stdout + result.stderr
        self.assertIn(
            "[BUILD]",
            combined_output,
            "Expected build start message in output - build process may not have started",
        )

        # Verify that the project name appears in output
        self.assertIn(
            "LuminescentGrand",
            combined_output,
            "Expected project name to appear in build output",
        )


if __name__ == "__main__":
    unittest.main()
