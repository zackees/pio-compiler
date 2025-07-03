"""
Unit test file.
"""

import unittest

from pio_compiler.cli import main

from . import TimedTestCase


class MainTester(TimedTestCase):
    """Main tester class."""

    def test_cli_main(self) -> None:
        """Call the CLI main entry point directly."""
        self.assertEqual(main([]), 0)

    def test_nonexistent_sketch_path_validation(self) -> None:
        """Test that non-existent sketch paths are detected early with proper error handling."""
        from pio_compiler.cli import _run_cli

        # Test with a non-existent path
        exit_code = _run_cli(["examples/NonExistentFolder", "--native"])
        self.assertEqual(
            exit_code, 1, "Should return exit code 1 for non-existent path"
        )

        # Test with multiple paths where one doesn't exist
        exit_code = _run_cli(
            ["tests/test_data/examples/Blink", "examples/NonExistentFolder", "--native"]
        )
        self.assertEqual(
            exit_code, 1, "Should return exit code 1 when any path doesn't exist"
        )


if __name__ == "__main__":
    unittest.main()
