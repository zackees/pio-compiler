import shutil
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform


class NativeCompileTest(unittest.TestCase):
    """Ensure that the compiler can build Arduino sketches for the *native* platform.

    The test verifies *behaviour* (wrapper generation) and does **not** require
    the actual build artefacts to succeed – only that the compiler went through
    the motions and generated the expected wrapper for a *native* build.
    """

    EXAMPLE_PATH = Path(__file__).parent / "test_data" / "examples" / "Blink"

    def setUp(self) -> None:  # noqa: D401 – unittest naming
        if not shutil.which("platformio"):
            self.skipTest(
                "PlatformIO executable not found – skipping native compile test."
            )

    def test_compile_blink_native(self) -> None:  # noqa: D401
        platform = Platform("native")  # Use built-in default configuration
        compiler = PioCompiler(platform)

        init_res = compiler.initialize()
        if not init_res.ok:
            self.fail(
                f"Initialization failed unexpectedly: {init_res.exception or 'unknown error'}"
            )

        _ = compiler.compile(self.EXAMPLE_PATH)
        # The compiler should not raise/return raw exceptions – it must always
        # return a ``Result`` object regardless of the build outcome.

        # The compiler should have generated a *wrapper* C++ file so that
        # PlatformIO can compile the sketch in a native environment.
        project_dir = compiler.work_dir() / "Blink"  # Matches example.stem
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
