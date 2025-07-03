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
        """Test that sketch dependencies are parsed correctly from embedded headers."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Clean cache to ensure we get a cache miss and turbo deps are set up
        cache_dir = project_root / ".tpo"
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir)

        # Test CLI without --lib flag - dependencies should be auto-detected from sketch header
        with patch(
            "pio_compiler.turbo_deps.TurboDependencyManager.setup_turbo_dependencies"
        ) as mock_setup:
            mock_setup.return_value = []  # Return empty list for successful setup

            cmd = f"uv run tpo {self.EXAMPLE_REL_PATH} --native"

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
                result.returncode,
                0,
                "CLI should parse embedded sketch dependencies successfully",
            )

            # Verify that setup_turbo_dependencies was called with FastLED
            # Note: With cache optimization, this might not be called on cache hits
            mock_setup.assert_called()
            call_args = mock_setup.call_args
            self.assertIn(
                "FastLED", call_args[0][0]
            )  # First argument should contain FastLED from sketch header

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

    def test_sketch_dependency_parsing(self) -> None:
        """Test that sketch dependencies are parsed correctly from embedded headers."""
        from pio_compiler.cli import _parse_sketch_dependencies

        # Test parsing dependencies from the Blink sketch
        blink_path = Path("tests/test_data/examples/Blink")
        dependencies = _parse_sketch_dependencies(blink_path)

        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

        # Test parsing from a sketch file directly
        blink_ino = blink_path / "Blink.ino"
        dependencies = _parse_sketch_dependencies(blink_ino)

        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

    def test_cli_and_sketch_dependency_combination(self) -> None:
        """Test that CLI --lib arguments are combined with sketch dependencies."""
        project_root = Path(__file__).resolve().parent.parent.parent

        # Clean cache to ensure we get a cache miss and turbo deps are set up
        cache_dir = project_root / ".tpo"
        if cache_dir.exists():
            import shutil

            shutil.rmtree(cache_dir)

        # Test CLI with additional --lib flag combined with sketch dependencies
        with patch(
            "pio_compiler.turbo_deps.TurboDependencyManager.setup_turbo_dependencies"
        ) as mock_setup:
            mock_setup.return_value = []  # Return empty list for successful setup

            cmd = f"uv run tpo {self.EXAMPLE_REL_PATH} --native --lib ArduinoJson"

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
            self.assertEqual(
                result.returncode,
                0,
                "CLI should combine --lib arguments with sketch dependencies",
            )

            # Verify that setup_turbo_dependencies was called with both FastLED and ArduinoJson
            mock_setup.assert_called()
            call_args = mock_setup.call_args
            dependencies = call_args[0][0]
            self.assertIn("FastLED", dependencies)  # From sketch header
            self.assertIn("ArduinoJson", dependencies)  # From CLI --lib

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
