import os
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform


class NativeCompileTest(unittest.TestCase):
    """Ensure that the compiler can build Arduino sketches for the *native* platform.

    The test verifies *behaviour* (wrapper generation) rather than calling the
    real PlatformIO toolchain – that would make the test brittle and slow.  We
    therefore enable the built-in *simulation* mode via the
    ``PIO_COMPILER_SIMULATE`` environment variable.
    """

    EXAMPLE_PATH = Path(__file__).parent / "test_data" / "examples" / "Blink"

    def setUp(self) -> None:  # noqa: D401 – unittest naming
        os.environ["PIO_COMPILER_SIMULATE"] = "1"

    def tearDown(self) -> None:  # noqa: D401
        os.environ.pop("PIO_COMPILER_SIMULATE", None)

    def test_compile_blink_native(self) -> None:  # noqa: D401
        platform = Platform("native")  # Use built-in default configuration
        compiler = PioCompiler(platform)

        init_res = compiler.initialize()
        if isinstance(init_res, Exception):
            self.fail(f"Initialization failed unexpectedly: {init_res}")

        result = compiler.compile(self.EXAMPLE_PATH)
        if isinstance(result, Exception):
            self.fail(f"Compile raised unexpected exception: {result}")

        self.assertTrue(
            result.ok, "Compilation result flagged as failed (simulation mode)"
        )

        # The compiler should have generated a *wrapper* C++ file so that
        # PlatformIO can compile the sketch in a native environment.
        project_dir = compiler._work_dir / "Blink"  # Matches example.stem
        wrapper = project_dir / "src" / "_pio_main.cpp"
        self.assertTrue(wrapper.exists(), f"Expected wrapper not found: {wrapper}")

        content = wrapper.read_text(encoding="utf-8")
        self.assertIn(
            '#include "Blink.ino"',
            content,
            "Wrapper does not reference the sketch correctly",
        )


if __name__ == "__main__":
    unittest.main()
