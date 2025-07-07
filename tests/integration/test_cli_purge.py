"""Integration test for CLI purge functionality."""

import subprocess
import unittest
from pathlib import Path


class CliPurgeIntegrationTest(unittest.TestCase):
    """Integration tests for the --purge CLI option."""

    def test_purge_command_exit_code(self) -> None:
        """Test that --purge command exits with code 0."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Run the purge command
        result = subprocess.run(
            ["uv", "run", "tpo", "--purge"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        # Should exit with code 0
        self.assertEqual(result.returncode, 0, f"Purge command failed: {result.stderr}")

        # Should contain expected output
        self.assertIn("tpo purge", result.stdout)
        self.assertIn("Cache purge completed", result.stdout)

    def test_purge_command_output_format(self) -> None:
        """Test that --purge command produces expected output format."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Run the purge command
        result = subprocess.run(
            ["uv", "run", "tpo", "--purge"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        # Should exit with code 0
        self.assertEqual(result.returncode, 0, f"Purge command failed: {result.stderr}")

        # Check output format
        lines = result.stdout.strip().split("\n")

        # Should start with banner
        self.assertTrue(
            lines[0].startswith("⚡ tpo purge") or lines[0].startswith("* tpo purge")
        )

        # Should end with completion message
        self.assertTrue(any("Cache purge completed" in line for line in lines))

    def test_purge_with_help_shows_description(self) -> None:
        """Test that --help shows the --purge option with correct description."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Run the help command
        result = subprocess.run(
            ["uv", "run", "tpo", "--help"],
            cwd=project_root,
            capture_output=True,
            text=True,
        )

        # Should exit with code 0
        self.assertEqual(result.returncode, 0, f"Help command failed: {result.stderr}")

        # Should contain purge option
        self.assertIn("--purge", result.stdout)
        self.assertIn("Purge all caches", result.stdout)
        self.assertIn("global cache directory", result.stdout)
        self.assertIn("local cache directory", result.stdout)


if __name__ == "__main__":
    unittest.main()
