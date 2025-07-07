"""Integration tests for the --report flag functionality.

This module tests that the --report command line argument correctly generates
report files including the platformio.ini.tpo file that contains the generated
PlatformIO configuration.
"""

from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path
from shutil import which


class CliReportTest(unittest.TestCase):
    """Test the --report flag functionality."""

    EXAMPLE_REL_PATH = Path("tests/test_data/examples/Blink")

    def setUp(self) -> None:  # pragma: no cover – purely for early exit
        # The compiler automatically falls back to *simulation* mode when
        # PlatformIO is unavailable, therefore we do not skip the test if the
        # executable is missing.
        _ = which("platformio")

    def test_report_flag_creates_platformio_ini_tpo(self) -> None:
        """Test that --report flag creates platformio.ini.tpo file."""

        # Change to the repository root so that the relative example path
        # resolves correctly during the test run.
        project_root = Path(__file__).resolve().parent.parent.parent

        # Create a temporary directory for the report output
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_report_dir = Path(temp_dir)

            # Run the CLI with --report flag
            cmd = f"tpo {self.EXAMPLE_REL_PATH} --native --report {temp_report_dir}"

            result = subprocess.run(
                cmd,
                cwd=project_root,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )

            # The command should succeed
            if (
                result.returncode != 0
            ):  # pragma: no cover – dump output to aid debugging
                print("STDOUT:\n", result.stdout)
                print("STDERR:\n", result.stderr)

            self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")

            # Check that platformio.ini.tpo was created
            platformio_ini_tpo = temp_report_dir / "platformio.ini.tpo"
            self.assertTrue(
                platformio_ini_tpo.exists(),
                f"platformio.ini.tpo should be created at {platformio_ini_tpo}",
            )

            # Verify the file has content (should contain PlatformIO configuration)
            content = platformio_ini_tpo.read_text()
            self.assertGreater(
                len(content), 0, "platformio.ini.tpo should not be empty"
            )

            # Should contain native environment configuration
            self.assertIn(
                "native",
                content,
                "platformio.ini.tpo should contain native environment",
            )

            # Verify that the output mentions the platformio.ini.tpo file
            self.assertIn(
                "platformio.ini.tpo",
                result.stdout,
                "CLI output should mention the platformio.ini.tpo file",
            )

    def test_report_flag_without_directory_still_works(self) -> None:
        """Test that --info flag works without --report directory."""

        # Change to the repository root so that the relative example path
        # resolves correctly during the test run.
        project_root = Path(__file__).resolve().parent.parent.parent

        # Run the CLI with --info flag (should work without creating platformio.ini.tpo)
        cmd = f"tpo {self.EXAMPLE_REL_PATH} --native --info"

        result = subprocess.run(
            cmd,
            cwd=project_root,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # The command should succeed
        if result.returncode != 0:  # pragma: no cover – dump output to aid debugging
            print("STDOUT:\n", result.stdout)
            print("STDERR:\n", result.stderr)

        self.assertEqual(result.returncode, 0, "CLI returned non-zero exit code")

        # Should show build info output
        self.assertIn("build info", result.stdout, "CLI output should show build info")

        # Should NOT mention platformio.ini.tpo since no --report directory was specified
        self.assertNotIn(
            "platformio.ini.tpo",
            result.stdout,
            "CLI output should not mention platformio.ini.tpo without --report",
        )
