"""Integration test for --lib (turbo dependencies) CLI functionality."""

import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


class CliTurboDependenciesTest(unittest.TestCase):
    """Integration test for --lib CLI functionality."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def test_cli_lib_argument_parsing(self) -> None:
        """Test that --lib argument is parsed correctly."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Test CLI with --lib flag - we'll mock the actual download to avoid network calls
        with patch(
            "pio_compiler.turbo_deps.TurboDependencyManager.setup_turbo_dependencies"
        ) as mock_setup:
            mock_setup.return_value = []  # Return empty list for successful setup

            cmd = f"uv run tpo {self.EXAMPLE_REL_PATH} --native --lib FastLED"

            result = subprocess.run(
                cmd,
                cwd=project_root,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=60,  # Reasonable timeout for this test
            )

            # Check that the command completed successfully
            if result.returncode != 0:
                print("STDOUT:\n", result.stdout)
                print("STDERR:\n", result.stderr, file=sys.stderr)

            # The command should parse successfully and attempt to setup turbo dependencies
            # Even if the actual download is mocked, the parsing should work
            self.assertEqual(
                result.returncode, 0, "CLI should parse --lib argument successfully"
            )

            # Verify that setup_turbo_dependencies was called with FastLED
            mock_setup.assert_called()
            call_args = mock_setup.call_args
            self.assertIn(
                "FastLED", call_args[0][0]
            )  # First argument should contain FastLED

    def test_cli_multiple_lib_arguments(self) -> None:
        """Test that multiple --lib arguments are parsed correctly."""
        import argparse

        from pio_compiler.cli import _parse_arguments

        # Create a namespace that simulates multiple --lib arguments
        ns = argparse.Namespace()
        ns.sketch = ["tests/test_data/examples/Blink"]
        ns.platforms = ["native"]
        ns.cache = None
        ns.clean = False
        ns.fast_flag = False
        ns.info = False
        ns.report = None
        ns.turbo_libs = ["FastLED", "ArduinoJson", "WiFiManager"]  # Multiple libraries

        args = _parse_arguments(ns)

        self.assertEqual(len(args.turbo_libs), 3)
        self.assertIn("FastLED", args.turbo_libs)
        self.assertIn("ArduinoJson", args.turbo_libs)
        self.assertIn("WiFiManager", args.turbo_libs)

    def test_platform_gets_turbo_dependencies(self) -> None:
        """Test that Platform objects receive turbo dependencies from CLI."""
        from pio_compiler.types import Platform

        # Test that Platform can be created with turbo dependencies
        platform = Platform("native", turbo_dependencies=["FastLED", "ArduinoJson"])

        self.assertEqual(len(platform.turbo_dependencies), 2)
        self.assertIn("FastLED", platform.turbo_dependencies)
        self.assertIn("ArduinoJson", platform.turbo_dependencies)

    def test_help_shows_lib_option(self) -> None:
        """Test that --help shows the --lib option."""
        project_root = Path(__file__).resolve().parent.parent.parent

        cmd = "uv run tpo --help"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("--lib", result.stdout)
        self.assertIn("turbo dependency", result.stdout)
        self.assertIn("GitHub", result.stdout)


if __name__ == "__main__":
    unittest.main()
