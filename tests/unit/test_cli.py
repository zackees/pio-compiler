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


if __name__ == "__main__":
    unittest.main()
