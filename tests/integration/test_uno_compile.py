import logging
import shutil
import subprocess  # local import to avoid polluting global namespace
import time
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform
from pio_compiler.logging_utils import configure_logging


class UnoCompileTest(unittest.TestCase):
    """End-to-end test that ensures a *real* PlatformIO build for the *uno* alias succeeds and produces a non-empty firmware artefact."""

    EXAMPLE_PATH = Path("tests/test_data/examples/Blink")

    @classmethod
    def setUpClass(cls):
        """Set up logging for the test suite."""
        configure_logging()
        cls.logger = logging.getLogger("UnoCompileTest")

    # ------------------------------------------------------------------
    # Test lifecycle helpers
    # ------------------------------------------------------------------
    def setUp(self) -> None:
        """Create a fresh compiler instance for every test."""
        self.logger.info("Setting up new test with Uno platform and compiler")

        self.platform = Platform("uno")
        self.compiler = PioCompiler(self.platform)
        # Track any spawned subprocesses so that *tearDown* can terminate them if needed.
        self._processes: list["subprocess.Popen"] = []

        self.logger.info("Initializing PioCompiler...")
        init_result = self.compiler.initialize()
        self.assertTrue(
            init_result.ok, f"Initialisation failed: {init_result.exception}"
        )
        self.logger.info("PioCompiler initialized successfully")

    def tearDown(self) -> None:  # noqa: D401 – imperative mood is fine here
        """Clean up the temporary work directory created by the compiler."""
        self.logger.info("Starting test cleanup...")

        # Terminate any subprocesses that may still be running.
        for proc in getattr(self, "_processes", []):
            if proc.poll() is None:  # still running
                self.logger.info("Terminating running subprocess...")
                proc.terminate()
                try:
                    proc.wait(timeout=2)
                except Exception:
                    self.logger.warning("Process did not terminate, forcing kill...")
                    proc.kill()
                    proc.wait(timeout=2)

        work_dir = getattr(self, "work_dir", None)
        if work_dir is not None and work_dir.exists():
            self.logger.info(f"Cleaning up work directory: {work_dir}")
            shutil.rmtree(work_dir, ignore_errors=True)
        self.logger.info("Cleanup completed")

    # ------------------------------------------------------------------
    # Actual test logic
    # ------------------------------------------------------------------
    def test_uno_build_creates_valid_firmware_elf(self) -> None:
        """Compile the Blink example and verify the *firmware.elf* artefact exists and is non-empty."""
        self.logger.info(f"Starting compilation of example: {self.EXAMPLE_PATH}")

        # Start compilation (synchronous under the hood – future resolves immediately)
        future = self.compiler.compile(self.EXAMPLE_PATH)
        stream = future.result()
        if stream._popen is not None and isinstance(stream._popen, subprocess.Popen):  # type: ignore[attr-defined]
            self._processes.append(stream._popen)
            self.logger.info("Compilation process started")

        # Drain the output stream until compilation is finished.  *is_done()*
        # returns *True* once the build **completed** and all output has been
        # consumed.  Loop until it reports completion (i.e. returns *True*).
        self.logger.info("Waiting for compilation to complete...")
        while not stream.is_done():
            output = stream.readline(timeout=0.1)
            if output:
                self.logger.debug(f"Build output: {output.strip()}")
            time.sleep(0.01)
        self.logger.info("Compilation completed")

        # Persist the work_dir for tearDown so that we can remove it later.
        self.work_dir = self.compiler.work_dir()
        self.logger.info(f"Work directory set to: {self.work_dir}")

        # Expected artefact location inside the compiler's temporary work dir
        artefact_path = self.work_dir.joinpath(
            self.EXAMPLE_PATH.stem,
            ".pio",
            "build",
            "uno",
            "firmware.elf",
        )
        self.logger.info(f"Looking for firmware artifact at: {artefact_path}")

        # 1. File exists   2. File is a regular file   3. File has non-zero size
        self.assertTrue(artefact_path.exists(), f"{artefact_path} does not exist")
        self.logger.info("Firmware file exists")

        self.assertTrue(
            artefact_path.is_file(),
            f"Expected a regular file but got something else: {artefact_path}",
        )
        self.logger.info("Firmware is a regular file")

        # Validate file size and ELF magic (0x7F 45 4C 46 ⇒ "\x7FELF").
        file_bytes = artefact_path.read_bytes()
        self.assertGreater(
            len(file_bytes),
            0,
            f"{artefact_path} appears to be empty",
        )
        self.logger.info(f"Firmware file size: {len(file_bytes)} bytes")

        self.assertTrue(
            file_bytes.startswith(b"\x7fELF"),
            "firmware.elf does not start with the expected ELF magic number",
        )
        self.logger.info("Firmware has valid ELF magic number - test passed!")


if __name__ == "__main__":
    unittest.main()