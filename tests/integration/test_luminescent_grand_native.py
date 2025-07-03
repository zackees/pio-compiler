"""Integration test for LuminescentGrand native compilation scenario."""

import subprocess
import unittest
from pathlib import Path


class LuminescentGrandNativeTest(unittest.TestCase):
    """Test compilation of LuminescentGrand project for native platform using tpo command."""

    def test_tpo_luminescent_grand_native_compilation(self) -> None:
        """Test that tpo can compile LuminescentGrand with --native flag."""

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
        self.assertEqual(result.returncode, 0, "Compilation failed")

        combined_output = result.stdout + result.stderr
        self.assertIn("[BUILD]", combined_output)
        self.assertIn("LuminescentGrand", combined_output)


if __name__ == "__main__":
    unittest.main()
