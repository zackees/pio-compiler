import shutil
import subprocess  # local import to avoid polluting global namespace
import time
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform


class UnoCompileTest(unittest.TestCase):
    """End-to-end test that ensures a *real* PlatformIO build for the *uno* alias succeeds and produces a non-empty firmware artefact."""

    EXAMPLE_PATH = Path("tests/test_data/examples/Blink")

    # ------------------------------------------------------------------
    # Test lifecycle helpers
    # ------------------------------------------------------------------
    def setUp(self) -> None:
        """Create a fresh compiler instance for every test."""

        self.platform = Platform("uno")
        self.compiler = PioCompiler(self.platform)
        # Track any spawned subprocesses so that *tearDown* can terminate them if needed.
        self._processes: list["subprocess.Popen"] = []

        init_result = self.compiler.initialize()
        self.assertTrue(
            init_result.ok, f"Initialisation failed: {init_result.exception}"
        )

    def tearDown(self) -> None:  # noqa: D401 – imperative mood is fine here
        """Clean up the temporary work directory created by the compiler."""

        # Terminate any subprocesses that may still be running.
        for proc in getattr(self, "_processes", []):
            if proc.poll() is None:  # still running
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    proc.kill()
                    proc.wait(timeout=2)

        work_dir = getattr(self, "work_dir", None)
        if work_dir is not None and work_dir.exists():
            shutil.rmtree(work_dir, ignore_errors=True)

    # ------------------------------------------------------------------
    # Actual test logic
    # ------------------------------------------------------------------
    def test_uno_build_creates_valid_firmware_elf(self) -> None:
        """Compile the Blink example and verify the *firmware.elf* artefact exists and is non-empty."""

        # Start compilation (synchronous under the hood – future resolves immediately)
        future = self.compiler.compile(self.EXAMPLE_PATH)
        stream = future.result()
        if stream._popen is not None and isinstance(stream._popen, subprocess.Popen):  # type: ignore[attr-defined]
            self._processes.append(stream._popen)

        # Drain the output stream until compilation is finished.  *is_done()*
        # returns *True* once the build **completed** and all output has been
        # consumed.  Loop until it reports completion (i.e. returns *True*).
        while not stream.is_done():
            _ = stream.readline(timeout=0.1)
            time.sleep(0.01)

        # Persist the work_dir for tearDown so that we can remove it later.
        self.work_dir = self.compiler.work_dir()

        # Expected artefact location inside the compiler's temporary work dir
        artefact_path = self.work_dir.joinpath(
            self.EXAMPLE_PATH.stem,
            ".pio",
            "build",
            "uno",
            "firmware.elf",
        )

        # 1. File exists   2. File is a regular file   3. File has non-zero size
        self.assertTrue(artefact_path.exists(), f"{artefact_path} does not exist")
        self.assertTrue(
            artefact_path.is_file(),
            f"Expected a regular file but got something else: {artefact_path}",
        )
        # Validate file size and ELF magic (0x7F 45 4C 46 ⇒ "\x7FELF").
        file_bytes = artefact_path.read_bytes()
        self.assertGreater(
            len(file_bytes),
            0,
            f"{artefact_path} appears to be empty",
        )
        self.assertTrue(
            file_bytes.startswith(b"\x7fELF"),
            "firmware.elf does not start with the expected ELF magic number",
        )


if __name__ == "__main__":
    unittest.main()
