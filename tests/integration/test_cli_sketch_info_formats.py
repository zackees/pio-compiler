"""Integration tests for SKETCH-INFO format support in CLI."""

import tempfile
import unittest
from pathlib import Path

from pio_compiler.cli import _build_argument_parser, _parse_sketch_dependencies


class TestSketchInfoFormatsIntegration(unittest.TestCase):
    """Test that both /// and // SKETCH-INFO formats work through the CLI."""

    def test_cli_handles_double_slash_sketch_info(self) -> None:
        """Test that CLI correctly parses dependencies from // SKETCH-INFO format."""
        # Create a temporary sketch with double-slash format
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """// SKETCH-INFO
// dependencies = ["FastLED", "WiFiManager"]
// SKETCH-INFO

#include <FastLED.h>
#include <WiFiManager.h>

void setup() {}
void loop() {}
"""
            )
            temp_path = Path(f.name)

        try:
            parser = _build_argument_parser()
            ns = parser.parse_args([str(temp_path), "--native"])
            # Validate parsing succeeded
            self.assertIsNotNone(ns)

            # Parse dependencies
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 2)
            self.assertIn("FastLED", dependencies)
            self.assertIn("WiFiManager", dependencies)
        finally:
            temp_path.unlink()

    def test_cli_handles_mixed_format_sketch_files(self) -> None:
        """Test that CLI can process multiple sketches with different SKETCH-INFO formats."""
        # Create a temporary sketch with mixed format
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """// SKETCH-INFO
// dependencies = ["ArduinoOTA", "ESPAsyncWebServer"]  
/// SKETCH-INFO

#include <ArduinoOTA.h>
#include <ESPAsyncWebServer.h>

void setup() {}
void loop() {}
"""
            )
            temp_path = Path(f.name)

        try:
            # Parse with CLI argument parser
            parser = _build_argument_parser()
            ns = parser.parse_args([str(temp_path), "--esp32dev"])
            # Validate parsing succeeded
            self.assertIsNotNone(ns)

            # Parse dependencies
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 2)
            self.assertIn("ArduinoOTA", dependencies)
            self.assertIn("ESPAsyncWebServer", dependencies)
        finally:
            temp_path.unlink()

    def test_backwards_compatibility_with_triple_slash(self) -> None:
        """Ensure that existing /// format still works correctly."""
        # Test with the existing Blink example
        blink_path = Path("tests/test_data/examples/Blink")

        parser = _build_argument_parser()
        ns = parser.parse_args([str(blink_path), "--uno"])
        # Validate parsing succeeded
        self.assertIsNotNone(ns)

        # Parse dependencies
        dependencies = _parse_sketch_dependencies(blink_path)

        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)


if __name__ == "__main__":
    unittest.main()
