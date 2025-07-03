import logging
import shutil
import subprocess  # local import to avoid polluting global namespace
import time
import unittest
from pathlib import Path

from pio_compiler import PioCompiler, Platform
from pio_compiler.logging_utils import configure_logging


class ComplexProjectTestCase(unittest.TestCase):
    """Test complex Arduino projects compilation and error handling."""

    BLINK_EXAMPLE = Path("tests/test_data/examples/Blink")
    LUMINESCENT_GRAND_EXAMPLE = Path("tests/test_data/examples/LuminescentGrand")

    @classmethod
    def setUpClass(cls):
        """Set up logging for the test suite."""
        configure_logging()
        cls.logger = logging.getLogger("ComplexProjectTestCase")

    def test_cli_compile_blink_native_success(self) -> None:
        """Test CLI compilation of simple Blink example for native platform (should succeed)."""
        self.logger.info(f"Starting CLI compilation test for: {self.BLINK_EXAMPLE}")

        # Get the project root (two levels up from this test file)
        project_root = Path(__file__).resolve().parent.parent.parent

        # Use the CLI command that users would actually run
        cmd = f"uv run pic --src {self.BLINK_EXAMPLE} native"

        self.logger.info(f"Running command: {cmd}")

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        # Log output for debugging if needed
        if result.stdout:
            self.logger.debug(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            self.logger.debug(f"STDERR:\n{result.stderr}")

        # Check that the compilation succeeded
        self.assertEqual(
            result.returncode,
            0,
            f"CLI compilation failed with exit code {result.returncode}.\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}",
        )

        # Check that success messages appear in output
        combined_output = result.stdout + result.stderr
        self.assertIn(
            "[BUILD]", combined_output, "Expected build start message in output"
        )
        self.assertIn(
            "[DONE]", combined_output, "Expected build completion message in output"
        )
        self.assertIn("Blink", combined_output, "Expected project name in output")

        self.logger.info("CLI compilation test completed successfully")

    def test_cli_compile_complex_project_native_expected_failure(self) -> None:
        """Test CLI compilation of complex LuminescentGrand project for native platform (should fail gracefully)."""
        self.logger.info(
            f"Starting CLI compilation test for complex project: {self.LUMINESCENT_GRAND_EXAMPLE}"
        )

        # Get the project root (two levels up from this test file)
        project_root = Path(__file__).resolve().parent.parent.parent

        # Use the CLI command that users would actually run
        cmd = f"uv run pic --src {self.LUMINESCENT_GRAND_EXAMPLE} native"

        self.logger.info(f"Running command: {cmd}")

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,  # 2 minute timeout
        )

        # Log output for debugging
        if result.stdout:
            self.logger.debug(f"STDOUT:\n{result.stdout}")
        if result.stderr:
            self.logger.debug(f"STDERR:\n{result.stderr}")

        # Check that the compilation failed as expected (complex Arduino projects may not be compatible with native)
        self.assertNotEqual(
            result.returncode,
            0,
            f"Expected compilation to fail for complex Arduino project on native platform, but it succeeded.\n"
            f"STDOUT: {result.stdout}\n"
            f"STDERR: {result.stderr}",
        )

        # Check that appropriate error messages appear
        combined_output = result.stdout + result.stderr
        self.assertIn(
            "[BUILD]", combined_output, "Expected build start message in output"
        )
        self.assertIn(
            "LuminescentGrand", combined_output, "Expected project name in output"
        )

        # Should have compilation errors related to missing Arduino.h or similar
        self.assertTrue(
            "Arduino.h" in combined_output
            or "Error" in combined_output
            or "error:" in combined_output,
            f"Expected compilation error messages, but got: {combined_output[:500]}...",
        )

        self.logger.info(
            "Complex project correctly failed to compile on native platform as expected"
        )

    def test_api_compile_blink_native(self) -> None:
        """Test API compilation of Blink example for native platform (for comparison)."""
        self.logger.info(f"Starting API compilation test for: {self.BLINK_EXAMPLE}")

        # Set up compiler using the API directly
        platform = Platform("native")
        compiler = PioCompiler(platform)

        # Track any spawned subprocesses so that tearDown can terminate them if needed
        self._processes: list["subprocess.Popen"] = []

        # Initialize the compiler
        init_result = compiler.initialize()
        self.assertTrue(
            init_result.ok, f"Initialization failed: {init_result.exception}"
        )

        # Start compilation
        future = compiler.compile(self.BLINK_EXAMPLE)
        stream = future.result()

        if stream._popen is not None and isinstance(stream._popen, subprocess.Popen):  # type: ignore[attr-defined]
            self._processes.append(stream._popen)
            self.logger.info("Compilation process started")

        # Drain the output stream until compilation is finished
        self.logger.info("Waiting for compilation to complete...")
        output_lines = []
        while not stream.is_done():
            output = stream.readline(timeout=0.5)
            if output:
                output_lines.append(output.strip())
                self.logger.debug(f"Build output: {output.strip()}")
            time.sleep(0.01)

        self.logger.info("Compilation completed")

        # Store work dir for potential cleanup in tearDown
        self.work_dir = compiler.work_dir()

        # Check that we got some build output
        self.assertGreater(
            len(output_lines), 0, "Expected some build output from compilation process"
        )

        # Check that the compilation process completed successfully
        if hasattr(stream, "_popen") and stream._popen is not None:
            return_code = stream._popen.returncode
            self.assertIsNotNone(return_code, "Process should have completed")
            self.assertEqual(
                return_code,
                0,
                f"Compilation failed with return code {return_code}. "
                f"Output: {chr(10).join(output_lines[-10:])}",  # Show last 10 lines
            )

        self.logger.info("API compilation test completed successfully")

    def test_directory_copying_with_subdirectories(self) -> None:
        """Test that the compiler correctly handles projects with subdirectories (even if compilation fails)."""
        self.logger.info(
            f"Testing directory structure handling for: {self.LUMINESCENT_GRAND_EXAMPLE}"
        )

        # Set up compiler using the API directly
        platform = Platform("native")
        compiler = PioCompiler(platform)

        # Initialize the compiler
        init_result = compiler.initialize()
        self.assertTrue(
            init_result.ok, f"Initialization failed: {init_result.exception}"
        )

        # Start compilation (we expect it to fail, but we want to verify directory copying works)
        future = compiler.compile(self.LUMINESCENT_GRAND_EXAMPLE)
        future.result()  # Just wait for completion, don't need to store the stream

        # Store work dir for inspection
        self.work_dir = compiler.work_dir()

        # Verify that the subdirectories were copied correctly
        project_dir = self.work_dir / "LuminescentGrand"
        src_dir = project_dir / "src"

        self.assertTrue(src_dir.exists(), f"Source directory should exist: {src_dir}")
        self.assertTrue(
            (src_dir / "LuminescentGrand.ino").exists(),
            "Main .ino file should be copied",
        )
        self.assertTrue(
            (src_dir / "arduino").exists(), "arduino subdirectory should be copied"
        )
        self.assertTrue(
            (src_dir / "shared").exists(), "shared subdirectory should be copied"
        )

        # Check that files within subdirectories were copied
        self.assertTrue(
            (src_dir / "arduino" / "LedRopeTCL.cpp").exists(),
            "Files in arduino/ should be copied",
        )
        self.assertTrue(
            (src_dir / "shared" / "color.cpp").exists(),
            "Files in shared/ should be copied",
        )

        self.logger.info(
            "Directory structure was correctly copied despite compilation failure"
        )

    def tearDown(self) -> None:
        """Clean up any resources created during the test."""
        # Terminate any background processes
        if hasattr(self, "_processes"):
            for proc in self._processes:
                if proc.poll() is None:  # Still running
                    self.logger.debug(f"Terminating process {proc.pid}")
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:  # pragma: no cover
                        self.logger.warning(f"Force killing process {proc.pid}")
                        proc.kill()

        # Clean up work directory if it exists
        if hasattr(self, "work_dir") and self.work_dir.exists():
            self.logger.debug(f"Cleaning up work directory: {self.work_dir}")
            try:
                shutil.rmtree(self.work_dir)
            except Exception as e:  # pragma: no cover
                self.logger.warning(f"Failed to clean up {self.work_dir}: {e}")


if __name__ == "__main__":
    unittest.main()
