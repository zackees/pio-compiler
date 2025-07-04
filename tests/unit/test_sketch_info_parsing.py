"""Unit tests for SKETCH-INFO parsing functionality."""

import tempfile
import unittest
from pathlib import Path

from pio_compiler.cli import _parse_sketch_dependencies


class TestSketchInfoParsing(unittest.TestCase):
    """Test SKETCH-INFO parsing from Arduino sketch files."""

    def test_parse_sketch_dependencies_from_directory(self) -> None:
        """Test parsing dependencies from a sketch directory."""
        # Test with the existing Blink example
        blink_path = Path("tests/test_data/examples/Blink")
        dependencies = _parse_sketch_dependencies(blink_path)

        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

    def test_parse_sketch_dependencies_from_file(self) -> None:
        """Test parsing dependencies from a sketch file directly."""
        # Test with the existing Blink.ino file
        blink_ino = Path("tests/test_data/examples/Blink/Blink.ino")
        dependencies = _parse_sketch_dependencies(blink_ino)

        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

    def test_parse_sketch_dependencies_multiple_deps(self) -> None:
        """Test parsing multiple dependencies from a sketch file."""
        # Create a temporary sketch file with multiple dependencies
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """/// SKETCH-INFO
/// dependencies = ["FastLED", "ArduinoJson", "WiFiManager"]
/// SKETCH-INFO

#include <FastLED.h>
#include <ArduinoJson.h>
#include <WiFiManager.h>

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 3)
            self.assertIn("FastLED", dependencies)
            self.assertIn("ArduinoJson", dependencies)
            self.assertIn("WiFiManager", dependencies)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_double_slash_format(self) -> None:
        """Test parsing dependencies using // format instead of ///."""
        # Create a temporary sketch file with double-slash format
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """// SKETCH-INFO
// dependencies = ["FastLED", "ArduinoJson"]
// SKETCH-INFO

#include <FastLED.h>
#include <ArduinoJson.h>

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 2)
            self.assertIn("FastLED", dependencies)
            self.assertIn("ArduinoJson", dependencies)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_mixed_slash_formats(self) -> None:
        """Test parsing dependencies when SKETCH-INFO uses mixed // and /// formats."""
        # Create a temporary sketch file with mixed formats (// for open, /// for close)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """// SKETCH-INFO
// dependencies = ["WiFiManager", "PubSubClient", "SPI"]
/// SKETCH-INFO

#include <WiFiManager.h>
#include <PubSubClient.h>
#include <SPI.h>

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 3)
            self.assertIn("WiFiManager", dependencies)
            self.assertIn("PubSubClient", dependencies)
            self.assertIn("SPI", dependencies)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_no_deps(self) -> None:
        """Test parsing a sketch file with no dependencies."""
        # Create a temporary sketch file without dependencies
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """/// SKETCH-INFO
/// SKETCH-INFO

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 0)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_no_sketch_info(self) -> None:
        """Test parsing a sketch file without SKETCH-INFO block."""
        # Create a temporary sketch file without SKETCH-INFO
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """#include <FastLED.h>

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            self.assertEqual(len(dependencies), 0)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_malformed_deps(self) -> None:
        """Test parsing a sketch file with malformed dependencies."""
        # Create a temporary sketch file with malformed dependencies
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ino", delete=False) as f:
            f.write(
                """/// SKETCH-INFO
/// dependencies = FastLED, ArduinoJson
/// SKETCH-INFO

#include <FastLED.h>

void setup() {
    // Setup code
}

void loop() {
    // Loop code
}
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            # Should return empty list for malformed dependencies
            self.assertEqual(len(dependencies), 0)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_non_ino_file(self) -> None:
        """Test parsing a non-.ino file returns empty dependencies."""
        # Create a temporary non-.ino file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".cpp", delete=False) as f:
            f.write(
                """/// SKETCH-INFO
/// dependencies = ["FastLED"]
/// SKETCH-INFO

#include <FastLED.h>
"""
            )
            temp_path = Path(f.name)

        try:
            dependencies = _parse_sketch_dependencies(temp_path)

            # Should return empty list for non-.ino files
            self.assertEqual(len(dependencies), 0)
        finally:
            temp_path.unlink()

    def test_parse_sketch_dependencies_empty_directory(self) -> None:
        """Test parsing an empty directory returns empty dependencies."""
        # Create a temporary empty directory
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            dependencies = _parse_sketch_dependencies(temp_path)

            # Should return empty list for empty directory
            self.assertEqual(len(dependencies), 0)

    def test_parse_sketch_dependencies_nonexistent_path(self) -> None:
        """Test parsing a nonexistent path returns empty dependencies."""
        nonexistent_path = Path("/nonexistent/path/sketch.ino")
        dependencies = _parse_sketch_dependencies(nonexistent_path)

        # Should return empty list for nonexistent path
        self.assertEqual(len(dependencies), 0)

    def test_cli_argument_parsing_with_sketch_info(self) -> None:
        """Test that CLI argument parsing correctly extracts SKETCH-INFO dependencies."""
        from pio_compiler.cli import _build_argument_parser, _parse_arguments

        # Test argument parsing with the Blink example
        parser = _build_argument_parser()
        ns = parser.parse_args(["tests/test_data/examples/Blink", "--native"])
        args = _parse_arguments(ns)

        # Should have the correct source and platform
        self.assertEqual(args.src, ["tests/test_data/examples/Blink"])
        self.assertEqual(args.platforms, ["native"])

        # Test that _parse_sketch_dependencies works with the parsed path
        dependencies = _parse_sketch_dependencies(Path(args.src[0]))
        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

    def test_cli_argument_parsing_without_platform_defaults_to_native(self) -> None:
        """Test that CLI argument parsing defaults to native platform when none specified."""
        from pio_compiler.cli import _build_argument_parser, _parse_arguments

        # Test argument parsing without platform - should default to native
        parser = _build_argument_parser()
        ns = parser.parse_args(["tests/test_data/examples/Blink"])
        args = _parse_arguments(ns)

        # Should default to native platform
        self.assertEqual(args.src, ["tests/test_data/examples/Blink"])
        self.assertEqual(args.platforms, ["native"])

        # Test that _parse_sketch_dependencies works with the parsed path
        dependencies = _parse_sketch_dependencies(Path(args.src[0]))
        self.assertEqual(len(dependencies), 1)
        self.assertIn("FastLED", dependencies)

    def test_cli_argument_parsing_combines_sketch_info_and_lib_args(self) -> None:
        """Test that CLI argument parsing handles both SKETCH-INFO deps and --lib arguments."""
        from pio_compiler.cli import _build_argument_parser, _parse_arguments

        # Test argument parsing with additional --lib argument
        parser = _build_argument_parser()
        ns = parser.parse_args(
            ["tests/test_data/examples/Blink", "--native", "--lib", "ArduinoJson"]
        )
        args = _parse_arguments(ns)

        # Should have the correct source, platform, and lib args
        self.assertEqual(args.src, ["tests/test_data/examples/Blink"])
        self.assertEqual(args.platforms, ["native"])
        self.assertEqual(args.turbo_libs, ["ArduinoJson"])

        # Test dependency combination logic from CLI
        sketch_dependencies = []
        for src_path in args.src:
            sketch_path = Path(src_path).expanduser().resolve()
            sketch_deps = _parse_sketch_dependencies(sketch_path)
            sketch_dependencies.extend(sketch_deps)

        # Combine CLI --lib arguments with sketch dependencies (CLI takes precedence)
        all_turbo_libs = list(args.turbo_libs or [])
        for dep in sketch_dependencies:
            if dep not in all_turbo_libs:
                all_turbo_libs.append(dep)

        # Should contain both FastLED (from SKETCH-INFO) and ArduinoJson (from --lib)
        self.assertEqual(len(all_turbo_libs), 2)
        self.assertIn("FastLED", all_turbo_libs)
        self.assertIn("ArduinoJson", all_turbo_libs)


if __name__ == "__main__":
    unittest.main()
