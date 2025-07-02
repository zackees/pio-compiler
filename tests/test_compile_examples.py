import shutil
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform

# Define UNO platform configuration – downloads are relatively small compared to ESP32.
UNO_PLATFORM = Platform(
    "uno",
    """[env:uno]
platform = atmelavr
board = uno
framework = arduino
lib_deps = fastled
""",
)


class CompileExamplesTest(unittest.TestCase):
    """Compile all sketches in *tests/test_data/examples* with the *uno* config."""

    EXAMPLES_DIR = Path(__file__).parent / "test_data" / "examples"

    def setUp(self) -> None:  # noqa: D401 – unittest naming
        # Skip test early if platformio is unavailable (e.g. offline CI environment).
        if not shutil.which("platformio"):
            self.skipTest(
                "PlatformIO executable not found – skipping integration compile test."
            )

    def _compile_example(self, example_path: Path) -> None:
        compiler = PioCompiler(UNO_PLATFORM)
        init_res = compiler.initialize()
        if isinstance(init_res, Exception):
            self.fail(f"Initialization failed: {init_res}")

        result = compiler.compile(example_path)
        if isinstance(result, Exception):
            self.fail(f"Compile raised unexpected exception: {result}")

        self.assertTrue(
            result.ok, f"Compilation failed for {example_path}: {result.stderr}"
        )

    def test_compile_all_examples(self) -> None:  # noqa: D401
        for example in self.EXAMPLES_DIR.iterdir():
            with self.subTest(example=example.name):
                self._compile_example(example)
