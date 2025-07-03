"""Unit tests for Platform and Board integration."""

import unittest

from pio_compiler.boards import Board, get_board
from pio_compiler.types import Platform


class PlatformBoardIntegrationTest(unittest.TestCase):
    """Test that Platform can accept Board objects and generate correct platformio.ini content."""

    def test_platform_from_predefined_board(self):
        """Test creating Platform from a predefined Board."""
        board = get_board("uno")
        platform = Platform(board)

        self.assertEqual(platform.name, "uno")
        self.assertIsNotNone(platform.board)
        assert platform.board is not None  # Type narrowing for mypy/pyright
        self.assertEqual(platform.board.board_name, "uno")

        # Verify platformio.ini content is generated from Board
        self.assertIsNotNone(platform.platformio_ini)
        assert platform.platformio_ini is not None  # Type narrowing
        self.assertIn("[env:uno]", platform.platformio_ini)
        self.assertIn("board = uno", platform.platformio_ini)
        self.assertIn("platform = atmelavr", platform.platformio_ini)
        self.assertIn("framework = arduino", platform.platformio_ini)

    def test_platform_from_custom_board(self):
        """Test creating Platform from a custom Board with specific configuration."""
        custom_board = Board(
            board_name="test_board",
            platform="esp32",
            framework="arduino",
            defines=["TEST_DEFINE=1", "DEBUG=1"],
            build_flags=["-Wall", "-O2"],
            build_unflags=["-Os"],
        )

        platform = Platform(custom_board)

        self.assertEqual(platform.name, "test_board")
        self.assertIsNotNone(platform.board)
        assert platform.board is not None  # Type narrowing
        self.assertEqual(platform.board.board_name, "test_board")

        # Verify platformio.ini content includes all Board configurations
        ini_content = platform.platformio_ini
        self.assertIsNotNone(ini_content)
        assert ini_content is not None  # Type narrowing
        self.assertIn("[env:test_board]", ini_content)
        self.assertIn("board = test_board", ini_content)
        self.assertIn("platform = esp32", ini_content)
        self.assertIn("framework = arduino", ini_content)
        self.assertIn("build_flags = -DTEST_DEFINE=1 -DDEBUG=1 -Wall -O2", ini_content)
        self.assertIn("build_unflags = -Os", ini_content)

    def test_platform_from_string_name(self):
        """Test that Platform still works with string names (backward compatibility)."""
        platform = Platform("esp32dev")

        self.assertEqual(platform.name, "esp32dev")
        self.assertIsNone(platform.board)

        # Should generate minimal platformio.ini for unknown board names
        self.assertIsNotNone(platform.platformio_ini)
        assert platform.platformio_ini is not None  # Type narrowing
        self.assertIn("[env:esp32dev]", platform.platformio_ini)
        self.assertIn("platform = esp32dev", platform.platformio_ini)

    def test_platform_from_string_with_custom_ini(self):
        """Test Platform creation with string name and custom platformio.ini."""
        custom_ini = "[env:custom]\nboard = custom_board\nplatform = custom_platform\n"
        platform = Platform("custom", custom_ini)

        self.assertEqual(platform.name, "custom")
        self.assertIsNone(platform.board)
        self.assertEqual(platform.platformio_ini, custom_ini)

    def test_platform_from_board_class_method(self):
        """Test the from_board class method."""
        board = get_board("teensy30")
        platform = Platform.from_board(board)

        self.assertEqual(platform.name, "teensy30")
        self.assertIsNotNone(platform.board)
        assert platform.board is not None  # Type narrowing
        self.assertEqual(platform.board.board_name, "teensy30")

        # Verify content is generated from Board
        self.assertIsNotNone(platform.platformio_ini)
        assert platform.platformio_ini is not None  # Type narrowing
        self.assertIn("[env:teensy30]", platform.platformio_ini)
        self.assertIn("board = teensy30", platform.platformio_ini)

    def test_platform_invalid_input_type(self):
        """Test that Platform raises TypeError for invalid input types."""
        with self.assertRaises(TypeError):
            Platform(123)  # type: ignore[arg-type]  # Invalid type - intentional

        with self.assertRaises(TypeError):
            Platform([])  # type: ignore[arg-type]  # Invalid type - intentional

    def test_board_to_platformio_ini_consistency(self):
        """Test that Platform uses Board's to_platformio_ini() method correctly."""
        board = Board(
            board_name="consistency_test",
            platform="test_platform",
            framework="test_framework",
        )

        # Get platformio.ini directly from Board
        board_ini = board.to_platformio_ini()

        # Get platformio.ini from Platform created with Board
        platform = Platform(board)
        platform_ini = platform.platformio_ini

        # They should be identical
        self.assertEqual(board_ini, platform_ini)


if __name__ == "__main__":
    unittest.main()
