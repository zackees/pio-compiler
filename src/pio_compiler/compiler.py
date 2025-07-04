from __future__ import annotations

import logging
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from colorama import Fore, Style, init

from . import tempdir
from .compiler_stream import CompilerStream
from .types import Platform, Result

__all__ = [
    "Platform",
    "Result",
    "PioCompilerImpl",
]

# Initialize colorama for Windows support
init(autoreset=True)

logger = logging.getLogger(__name__)

# Define color constants for consistent styling
INFO_PREFIX = f"{Fore.CYAN}[INFO]{Style.RESET_ALL}"
UNO_PREFIX = f"{Fore.GREEN}[UNO]{Style.RESET_ALL}"
PATH_COLOR = f"{Fore.YELLOW}"


class PioCompilerImpl:
    """High-level wrapper around the *platformio* command-line interface.

    The class purposefully avoids depending on the PlatformIO *Python* API
    because that API is considered *internal* and is subject to change.  Using
    the CLI guarantees compatibility with the wide range of PlatformIO
    versions that users may have installed.
    """

    #: Environment variable used internally to disable *actual* compilation in
    #: test environments that do not have PlatformIO installed.
    _SIMULATE_ENV = "PIO_COMPILER_SIMULATE"

    def __init__(
        self,
        platform: Platform,
        work_dir: Optional[Path] = None,
        *,
        fast_mode: bool = False,
        disable_auto_clean: bool = False,
        force_rebuild: bool = False,
        info_mode: bool = False,
        cache_entry=None,
    ) -> None:
        self.platform = platform
        self.fast_mode = fast_mode
        self.disable_auto_clean = disable_auto_clean
        self.force_rebuild = force_rebuild
        self.info_mode = info_mode
        self.cache_entry = cache_entry
        logger.debug(
            "Creating PioCompilerImpl for platform %s (fast_mode=%s, disable_auto_clean=%s, force_rebuild=%s, info_mode=%s)",
            platform.name,
            fast_mode,
            disable_auto_clean,
            force_rebuild,
            info_mode,
        )
        # Work in a dedicated temporary directory unless the caller wants a
        # persistent *work_dir*.
        self._work_dir = (
            Path(work_dir)
            if work_dir is not None
            else tempdir.mkdtemp(
                prefix="pio_compiler_", disable_auto_clean=disable_auto_clean
            )
        )
        self._ini_path = self._work_dir / "platformio.ini"

    # ---------------------------------------------------------------------
    # Public helper – can be called by users to clean-up temp directories.
    # ---------------------------------------------------------------------
    def cleanup(self) -> None:  # pragma: no cover
        """Remove the temporary *work_dir* created by the constructor."""

        try:
            shutil.rmtree(self._work_dir)
        except FileNotFoundError:
            # Already removed – nothing to do.
            pass

    # ------------------------------------------------------------------
    # API mandated by the README – initialise, build_info, compile, …
    # ------------------------------------------------------------------
    def initialize(self) -> Result:
        """Create *platformio.ini* so that subsequent builds can run.

        The method now always returns a :class:`Result` instance.  On failure
        the returned object has ``ok = False`` and the raised exception is
        captured in :pyattr:`Result.exception`.
        """

        try:
            logger.debug("Writing platformio.ini to %s", self._ini_path)
            self._ini_path.write_text(
                self.platform.platformio_ini or "", encoding="utf-8"
            )
            return Result(ok=True, platform=self.platform, stdout="", stderr="")
        except Exception as exc:  # pragma: no cover
            # Never propagate the raw exception – instead encapsulate it in
            # the Result so that callers do not have to implement special
            # ``isinstance`` checks.
            return Result(ok=False, platform=self.platform, exception=exc)

    def build_info(self) -> Dict[str, Any]:
        """Return a small JSON-serialisable dict with environment information."""

        return {
            "platform": self.platform.name,
            "work_dir": str(self._work_dir),
            "has_platformio_ini": self._ini_path.exists(),
        }

    def get_pio_cache_dir(self, example: Path | str) -> str | None:
        """Get the PlatformIO cache directory path that will be used for this build.

        Returns the path to the .pio_home/.cache directory that PlatformIO uses
        for caching build artifacts, or None if the path cannot be determined.
        """
        try:
            example_path = Path(example).expanduser().resolve()

            # Determine project directory
            if (example_path / "platformio.ini").exists():
                project_dir = example_path
            else:
                # In fast mode, the work_dir is already the cache directory for this project/platform
                # (e.g., ".tpo/native-a03a3ffa"), so we don't need to add the project name again
                if self.fast_mode:
                    project_dir = self._work_dir
                else:
                    project_dir = self._work_dir / example_path.stem

            # PlatformIO cache is inside .pio_home/.cache/tmp/
            pio_home = project_dir / ".pio_home"
            pio_cache = pio_home / ".cache" / "tmp"

            return str(pio_cache)
        except Exception:
            return None

    def generate_optimization_report(
        self, project_dir: Path, example_path: Path, output_dir: Path | None = None
    ) -> Path | None:
        """Generate PlatformIO optimization report and return the path to the report file.

        Args:
            project_dir: The PlatformIO project directory
            example_path: The source example path
            output_dir: Optional directory where to save the report. If None, saves to project_dir

        Returns:
            Path to the optimization report file or None if generation failed
        """
        try:
            # Generate report filename
            report_name = (
                f"optimization_report_{self.platform.name}_{example_path.stem}.txt"
            )
            # Use custom output directory if provided, otherwise use project directory
            report_base_dir = output_dir if output_dir is not None else project_dir
            report_path = report_base_dir / report_name

            # Run PlatformIO with verbose output to capture memory usage
            pio_executable = shutil.which("platformio")
            if not pio_executable:
                logger.warning(
                    "PlatformIO executable not found for optimization report"
                )
                return None

            import os

            env = os.environ.copy()
            pio_home = project_dir / ".pio_home"
            env["PLATFORMIO_CORE_DIR"] = str(pio_home)

            # Run platformio check for static analysis (if available)
            check_cmd = [pio_executable, "check", "-d", str(project_dir), "--verbose"]

            report_content = []
            report_content.append("=" * 80)
            report_content.append(f"OPTIMIZATION REPORT for {example_path.name}")
            report_content.append(f"Platform: {self.platform.name}")
            report_content.append(f"Generated: {datetime.now().isoformat()}")
            report_content.append("=" * 80)
            report_content.append("")

            # Try to get static analysis report
            try:
                logger.debug("Running PlatformIO check for static analysis")
                check_result = subprocess.run(
                    check_cmd, capture_output=True, text=True, env=env, timeout=120
                )

                if check_result.returncode == 0:
                    report_content.append("STATIC ANALYSIS REPORT:")
                    report_content.append("-" * 40)
                    report_content.append(check_result.stdout)
                    report_content.append("")
                else:
                    report_content.append("STATIC ANALYSIS: Not available or failed")
                    report_content.append("")

            except (subprocess.TimeoutExpired, subprocess.SubprocessError) as e:
                logger.debug(f"Static analysis failed: {e}")
                report_content.append("STATIC ANALYSIS: Not available")
                report_content.append("")

            # Get build size information
            build_dir = project_dir / ".pio" / "build" / self.platform.name
            firmware_elf = build_dir / "firmware.elf"

            if firmware_elf.exists():
                report_content.append("MEMORY USAGE ANALYSIS:")
                report_content.append("-" * 40)

                # Use arm-none-eabi-size or equivalent to get memory info
                size_tools = ["arm-none-eabi-size", "size", "avr-size"]
                size_cmd = None

                for tool in size_tools:
                    if shutil.which(tool):
                        size_cmd = [tool, "-A", str(firmware_elf)]
                        break

                if size_cmd:
                    try:
                        size_result = subprocess.run(
                            size_cmd, capture_output=True, text=True, timeout=30
                        )
                        if size_result.returncode == 0:
                            report_content.append(size_result.stdout)
                        else:
                            report_content.append(
                                f"Size analysis failed: {size_result.stderr}"
                            )
                    except subprocess.SubprocessError as e:
                        report_content.append(f"Size analysis error: {e}")
                else:
                    report_content.append("Size analysis tool not found")

                report_content.append("")

                # Get detailed section information
                try:
                    file_size = firmware_elf.stat().st_size
                    report_content.append(f"Firmware file size: {file_size} bytes")
                    report_content.append("")
                except OSError:
                    pass

            # Write report to file
            report_path.write_text("\n".join(report_content), encoding="utf-8")
            logger.debug(f"Optimization report written to: {report_path}")
            return report_path

        except Exception as e:
            logger.warning(f"Failed to generate optimization report: {e}")
            return None

    def generate_build_info(
        self,
        project_dir: Path,
        example_path: Path,
        build_start_time: float,
        output_dir: Path | None = None,
    ) -> Path | None:
        """Generate build_info.json file with comprehensive build information.

        Args:
            project_dir: The PlatformIO project directory
            example_path: The source example path
            build_start_time: Unix timestamp when build started
            output_dir: Optional directory where to save the file. If None, saves to project_dir

        Returns:
            Path to the build_info.json file or None if generation failed
        """
        try:
            import json
            from datetime import datetime

            # Use custom output directory if provided, otherwise use project directory
            report_base_dir = output_dir if output_dir is not None else project_dir
            build_info_path = report_base_dir / "build_info.json"
            build_end_time = time.time()

            # Collect build information
            build_info = {
                "project": {
                    "name": example_path.stem,
                    "path": str(example_path),
                    "platform": self.platform.name,
                    "work_dir": str(project_dir),
                },
                "build": {
                    "start_time": build_start_time,
                    "end_time": build_end_time,
                    "duration_seconds": build_end_time - build_start_time,
                    "start_time_iso": datetime.fromtimestamp(
                        build_start_time
                    ).isoformat(),
                    "end_time_iso": datetime.fromtimestamp(build_end_time).isoformat(),
                    "fast_mode": self.fast_mode,
                    "force_rebuild": self.force_rebuild,
                    "info_mode": self.info_mode,
                },
                "environment": {
                    "pio_compiler_version": "1.0.0",  # This should be dynamic
                    "platform_config": self.platform.platformio_ini or "",
                    "cache_dir": self.get_pio_cache_dir(example_path),
                },
                "artifacts": {"firmware_files": [], "size_info": {}},
            }

            # Collect firmware artifacts
            build_dir = project_dir / ".pio" / "build" / self.platform.name
            if build_dir.exists():
                for pattern in ["*.elf", "*.bin", "*.hex"]:
                    for artifact in build_dir.glob(pattern):
                        try:
                            size = artifact.stat().st_size
                            build_info["artifacts"]["firmware_files"].append(
                                {
                                    "name": artifact.name,
                                    "path": str(artifact.relative_to(project_dir)),
                                    "size_bytes": size,
                                    "modified": artifact.stat().st_mtime,
                                }
                            )
                        except OSError:
                            continue

            # Get memory usage info if available
            firmware_elf = build_dir / "firmware.elf"
            if firmware_elf.exists():
                # Try to get size information
                size_tools = ["arm-none-eabi-size", "size", "avr-size"]
                for tool in size_tools:
                    if shutil.which(tool):
                        try:
                            size_result = subprocess.run(
                                [tool, "-A", str(firmware_elf)],
                                capture_output=True,
                                text=True,
                                timeout=30,
                            )
                            if size_result.returncode == 0:
                                build_info["artifacts"]["size_info"][
                                    "raw_output"
                                ] = size_result.stdout
                                break
                        except subprocess.SubprocessError:
                            continue

            # Write build_info.json
            with open(build_info_path, "w", encoding="utf-8") as f:
                json.dump(build_info, f, indent=2, sort_keys=True)

            logger.debug(f"Build info written to: {build_info_path}")
            return build_info_path

        except Exception as e:
            logger.warning(f"Failed to generate build_info.json: {e}")
            return None

    def generate_symbols_report(
        self, project_dir: Path, example_path: Path, output_dir: Path | None = None
    ) -> Path | None:
        """Generate symbols analysis report using nm and objdump tools.

        This method analyzes the compiled ELF file to extract symbol size information,
        helping identify large symbols for optimization purposes.

        Args:
            project_dir: The PlatformIO project directory
            example_path: The source example path
            output_dir: Optional directory where to save the report. If None, saves to project_dir

        Returns:
            Path to the symbols_report.txt file or None if generation failed
        """
        try:
            # Use custom output directory if provided, otherwise use project directory
            report_base_dir = output_dir if output_dir is not None else project_dir
            symbols_report_path = report_base_dir / "symbols_report.txt"

            # Find the compiled binary file (search in all build subdirectories)
            build_root = project_dir / ".pio" / "build"

            # Search for binaries in all build subdirectories
            firmware_binary = None
            binary_patterns = ["*.elf", "*.exe", "program*", "firmware*"]

            if build_root.exists():
                for pattern in binary_patterns:
                    # Search recursively for binary files
                    for candidate in build_root.rglob(pattern):
                        if candidate.is_file() and candidate.stat().st_size > 0:
                            # Prefer .elf files over .exe files
                            if firmware_binary is None or candidate.suffix == ".elf":
                                firmware_binary = candidate
                                if candidate.suffix == ".elf":
                                    break  # Found ELF, stop searching

            if firmware_binary is None:
                logger.warning(f"No binary file found in {build_root}")
                logger.debug(f"Searched patterns: {binary_patterns}")
                return None

            report_content = []
            report_content.append("=" * 80)
            report_content.append(f"SYMBOLS ANALYSIS REPORT for {example_path.name}")
            report_content.append(f"Platform: {self.platform.name}")
            report_content.append(f"Generated: {datetime.now().isoformat()}")
            report_content.append(f"Binary File: {firmware_binary}")
            report_content.append("=" * 80)
            report_content.append("")

            # Try to find appropriate tools for symbol analysis
            nm_tools = ["arm-none-eabi-nm", "nm", "avr-nm"]
            objdump_tools = ["arm-none-eabi-objdump", "objdump", "avr-objdump"]
            size_tools = ["arm-none-eabi-size", "size", "avr-size"]

            nm_cmd = None
            objdump_cmd = None
            size_cmd = None

            for tool in nm_tools:
                if shutil.which(tool):
                    nm_cmd = tool
                    break

            for tool in objdump_tools:
                if shutil.which(tool):
                    objdump_cmd = tool
                    break

            for tool in size_tools:
                if shutil.which(tool):
                    size_cmd = tool
                    break

            # 1. Overall size analysis
            if size_cmd:
                report_content.append("1. OVERALL MEMORY USAGE")
                report_content.append("-" * 40)
                try:
                    size_result = subprocess.run(
                        [size_cmd, "-A", str(firmware_binary)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if size_result.returncode == 0:
                        report_content.append(size_result.stdout)
                    else:
                        report_content.append(
                            f"Size analysis failed: {size_result.stderr}"
                        )
                except subprocess.SubprocessError as e:
                    report_content.append(f"Size analysis error: {e}")
                report_content.append("")

                # Also get traditional size output
                try:
                    size_result = subprocess.run(
                        [size_cmd, str(firmware_binary)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )
                    if size_result.returncode == 0:
                        report_content.append("Traditional size output:")
                        report_content.append(size_result.stdout)
                except subprocess.SubprocessError:
                    pass
                report_content.append("")

            # 2. Symbol size analysis using nm
            symbols = []  # Initialize symbols list early
            if nm_cmd:
                report_content.append("2. SYMBOL SIZE ANALYSIS (Largest Symbols)")
                report_content.append("-" * 40)
                try:
                    # Get all symbols with sizes, sorted by size (descending)
                    nm_result = subprocess.run(
                        [nm_cmd, "-S", "-s", str(firmware_binary)],
                        capture_output=True,
                        text=True,
                        timeout=60,
                    )

                    if nm_result.returncode == 0:
                        # Parse nm output and sort by size
                        for line in nm_result.stdout.strip().split("\n"):
                            if not line.strip():
                                continue

                            parts = line.split()
                            if len(parts) >= 4:
                                try:
                                    # Format: address size type name
                                    address = parts[0]
                                    size_hex = parts[1]
                                    symbol_type = parts[2]
                                    symbol_name = " ".join(parts[3:])

                                    # Convert hex size to decimal
                                    size_bytes = (
                                        int(size_hex, 16) if size_hex != "0" else 0
                                    )

                                    if size_bytes > 0:  # Only include symbols with size
                                        symbols.append(
                                            (
                                                size_bytes,
                                                symbol_name,
                                                symbol_type,
                                                address,
                                            )
                                        )
                                except (ValueError, IndexError):
                                    continue

                        # Sort by size (descending) and show top 50
                        symbols.sort(reverse=True, key=lambda x: x[0])

                        report_content.append(
                            f"Top 50 largest symbols (out of {len(symbols)} total):"
                        )
                        report_content.append("")
                        report_content.append(
                            f"{'Size (bytes)':<12} {'Type':<4} {'Symbol Name':<50} {'Address'}"
                        )
                        report_content.append("-" * 100)

                        for i, (size_bytes, name, sym_type, addr) in enumerate(
                            symbols[:50]
                        ):
                            # Truncate very long symbol names
                            display_name = (
                                name if len(name) <= 50 else name[:47] + "..."
                            )
                            report_content.append(
                                f"{size_bytes:<12} {sym_type:<4} {display_name:<50} {addr}"
                            )

                        # Show FastLED-related symbols separately if detected
                        fastled_symbols = [
                            s
                            for s in symbols
                            if "fastled" in s[1].lower() or "led" in s[1].lower()
                        ]
                        if fastled_symbols:
                            report_content.append("")
                            report_content.append("FastLED-related symbols:")
                            report_content.append("-" * 40)
                            for size_bytes, name, sym_type, addr in fastled_symbols[
                                :20
                            ]:
                                display_name = (
                                    name if len(name) <= 50 else name[:47] + "..."
                                )
                                report_content.append(
                                    f"{size_bytes:<12} {sym_type:<4} {display_name}"
                                )

                    else:
                        report_content.append(f"nm analysis failed: {nm_result.stderr}")

                except subprocess.SubprocessError as e:
                    report_content.append(f"nm analysis error: {e}")

                report_content.append("")

            # 3. Section analysis using objdump
            if objdump_cmd:
                report_content.append("3. SECTION ANALYSIS")
                report_content.append("-" * 40)
                try:
                    # Get section headers
                    objdump_result = subprocess.run(
                        [objdump_cmd, "-h", str(firmware_binary)],
                        capture_output=True,
                        text=True,
                        timeout=30,
                    )

                    if objdump_result.returncode == 0:
                        report_content.append("Section headers:")
                        report_content.append(objdump_result.stdout)
                    else:
                        report_content.append(
                            f"objdump section analysis failed: {objdump_result.stderr}"
                        )

                except subprocess.SubprocessError as e:
                    report_content.append(f"objdump analysis error: {e}")

                report_content.append("")

            # 4. Object file analysis (if available)
            obj_files = list(build_root.glob("**/*.o"))
            if obj_files and nm_cmd:
                report_content.append("4. OBJECT FILE SIZE CONTRIBUTION")
                report_content.append("-" * 40)

                obj_sizes = []
                for obj_file in obj_files[
                    :20
                ]:  # Limit to first 20 to avoid huge output
                    try:
                        nm_obj_result = subprocess.run(
                            [nm_cmd, "-S", str(obj_file)],
                            capture_output=True,
                            text=True,
                            timeout=10,
                        )

                        if nm_obj_result.returncode == 0:
                            total_size = 0
                            for line in nm_obj_result.stdout.strip().split("\n"):
                                parts = line.split()
                                if len(parts) >= 4:
                                    try:
                                        size_hex = parts[1]
                                        size_bytes = (
                                            int(size_hex, 16) if size_hex != "0" else 0
                                        )
                                        total_size += size_bytes
                                    except (ValueError, IndexError):
                                        continue

                            if total_size > 0:
                                obj_sizes.append((total_size, obj_file.name))

                    except subprocess.SubprocessError:
                        continue

                # Sort by size and display
                obj_sizes.sort(reverse=True, key=lambda x: x[0])
                report_content.append(
                    f"Object files by symbol size contribution (top {min(len(obj_sizes), 20)}):"
                )
                report_content.append("")
                for size_bytes, filename in obj_sizes[:20]:
                    report_content.append(f"{size_bytes:<12} bytes - {filename}")

                report_content.append("")

            # 5. Summary and recommendations
            report_content.append("5. OPTIMIZATION RECOMMENDATIONS")
            report_content.append("-" * 40)

            if nm_cmd and symbols:
                # Analyze largest symbols for recommendations
                large_symbols = [
                    s for s in symbols if s[0] > 1000
                ]  # Symbols larger than 1KB

                report_content.append(
                    "Symbols larger than 1KB that could be optimization targets:"
                )
                for size_bytes, name, sym_type, addr in large_symbols[:10]:
                    report_content.append(f"  {size_bytes:>6} bytes: {name[:60]}")

                report_content.append("")
                report_content.append("General optimization suggestions:")
                report_content.append(
                    "- Consider using compiler optimization flags (-Os for size)"
                )
                report_content.append("- Look for unused code that can be removed")
                report_content.append(
                    "- Consider replacing large libraries with smaller alternatives"
                )
                report_content.append("- Use PROGMEM for constants on AVR platforms")
                report_content.append(
                    "- Enable link-time optimization (LTO) if available"
                )

            if not nm_cmd and not objdump_cmd and not size_cmd:
                report_content.append("No symbol analysis tools found.")
                report_content.append(
                    "Install appropriate toolchain (e.g., arm-none-eabi-gcc, avr-gcc) for detailed analysis."
                )

            # Write report to file
            symbols_report_path.write_text("\n".join(report_content), encoding="utf-8")
            logger.debug(f"Symbols report written to: {symbols_report_path}")
            return symbols_report_path

        except Exception as e:
            logger.warning(f"Failed to generate symbols report: {e}")
            return None

    # --------------------------------------------------------------
    # *compile* – build a single example.
    # --------------------------------------------------------------
    def compile(self, example: Path | str) -> CompilerStream:
        """Compile *example* and return a :class:`CompilerStream` instance.

        The method starts the PlatformIO build in the background (unless it
        operates in *simulation* mode) and immediately returns a
        :class:`CompilerStream` that allows the caller to *stream* the
        combined (stdout + stderr) output.
        """

        example_path = Path(example).expanduser().resolve()
        logger.debug("Starting compile for %s", example)

        # Validate the input path and provide helpful error messages
        validation_error = self._validate_example_path(example_path)
        if validation_error:
            logger.warning(validation_error)
            return CompilerStream(
                popen=None,
                preloaded_output=validation_error,
            )

        # ------------------------------------------------------------------
        # Prepare a PlatformIO *project directory*.
        # ------------------------------------------------------------------
        if (example_path / "platformio.ini").exists():
            project_dir = example_path
        else:
            # Create a dedicated project inside the compiler's work dir.
            # In fast mode, the work_dir is already the cache directory for this project/platform
            # (e.g., ".tpo/native-a03a3ffa"), so we don't need to add the project name again
            if self.fast_mode:
                project_dir = self._work_dir
            else:
                project_dir = self._work_dir / example_path.stem
            logger.debug("Creating isolated project directory %s", project_dir)
            src_dir = project_dir / "src"
            src_dir.mkdir(parents=True, exist_ok=True)

            # Set up platform downloads for native/dev platforms BEFORE other setup
            if self.platform.name in ["native", "dev"]:
                # Check if platform is already set up in cache to avoid redundant work
                skip_platform_setup = False
                if (
                    self.fast_mode
                    and self.cache_entry
                    and hasattr(self.cache_entry, "is_platform_setup")
                ):
                    skip_platform_setup = self.cache_entry.is_platform_setup()
                    if skip_platform_setup:
                        logger.info(
                            "Platform '%s' already set up in cache, skipping download",
                            self.platform.name,
                        )

                if not skip_platform_setup:
                    logger.info(
                        "Setting up platform '%s' by downloading from GitHub",
                        self.platform.name,
                    )
                    try:
                        from .turbo_deps import TurboDependencyManager

                        turbo_manager = TurboDependencyManager()
                        turbo_manager.extract_platform(self.platform.name, project_dir)
                    except Exception as exc:
                        logger.warning(
                            "Failed to setup platform '%s': %s", self.platform.name, exc
                        )
                        # Continue with compilation even if platform setup fails

            # Set up turbo dependencies (libraries downloaded and symlinked)
            if self.platform.turbo_dependencies:
                # Check if dependencies are already set up in cache to avoid redundant work
                skip_turbo_setup = False
                if (
                    self.fast_mode
                    and self.cache_entry
                    and hasattr(self.cache_entry, "are_turbo_dependencies_setup")
                ):
                    skip_turbo_setup = self.cache_entry.are_turbo_dependencies_setup()
                    if skip_turbo_setup:
                        logger.info(
                            "Turbo dependencies already set up in cache, skipping: %s",
                            self.platform.turbo_dependencies,
                        )

                if not skip_turbo_setup:
                    logger.info(
                        "Setting up turbo dependencies: %s",
                        self.platform.turbo_dependencies,
                    )
                    try:
                        from .turbo_deps import TurboDependencyManager

                        turbo_manager = TurboDependencyManager()
                        turbo_manager.setup_turbo_dependencies(
                            self.platform.turbo_dependencies, project_dir
                        )
                    except Exception as exc:
                        logger.warning("Failed to setup turbo dependencies: %s", exc)
                        # Continue with compilation even if turbo dependencies fail

            # --------------------------------------------------------------
            # When compiling for the *uno* platform we emit user-friendly
            # *print* statements that highlight the directories and build
            # artefacts involved.  The messages are intentionally kept very
            # lightweight so that they do not overwhelm normal output but
            # still provide helpful breadcrumbs when users wonder where the
            # temporary files live.
            # --------------------------------------------------------------
            if self.platform.name == "uno":
                print(
                    f"{UNO_PREFIX} Project directory: {PATH_COLOR}{project_dir}{Style.RESET_ALL}"
                )
                print(
                    f"{UNO_PREFIX} Source directory:   {PATH_COLOR}{src_dir}{Style.RESET_ALL}"
                )

            copied_paths: list[str] = []

            if example_path.is_dir():
                # Copy everything from the example directory into *src*.
                for item in example_path.iterdir():
                    dest_path = src_dir / item.name
                    if item.is_file():
                        shutil.copy(item, dest_path)
                        copied_paths.append(str(dest_path.relative_to(project_dir)))
                    elif item.is_dir():
                        # Avoid *FileExistsError* when reusing the same work
                        # directory (fast mode) across multiple invocations.
                        if dest_path.exists():
                            continue
                        shutil.copytree(item, dest_path)
                        copied_paths.append(str(dest_path.relative_to(project_dir)))
                    else:
                        # Handle other types (symlinks, etc.) gracefully
                        logger.warning(f"Skipping unknown file type: {item}")
                        continue

                # ------------------------------------------------------------------
                # *Native* platform special-case – PlatformIO's **native** platform
                # does **not** understand Arduino ``*.ino`` sketches directly.  To
                # let users point the compiler at an Arduino example and still
                # compile for the host we auto-generate a tiny C++ translation unit
                # that simply includes the sketch source along with comprehensive
                # Arduino compatibility headers.
                #
                # The generated files live inside *src* so that the default
                # ``src_dir = src`` setting picks them up automatically.
                # ------------------------------------------------------------------
                if self.platform.name == "native":
                    ino_files = list(src_dir.glob("*.ino"))
                    if ino_files:
                        logger.debug(
                            "Generating native wrapper for sketch %s", ino_files[0]
                        )
                        sketch = ino_files[0]
                        wrapper_path = src_dir / "_pio_main.cpp"

                        # Inject comprehensive Arduino compatibility files
                        # Always inject, but handle FastLED projects differently
                        # (FastLED provides headers but not native implementations)
                        fastled_detected = self._detect_fastled_usage(src_dir)
                        self._inject_arduino_compatibility(
                            src_dir, fastled_mode=fastled_detected
                        )

                        # --------------------------------------------------
                        # Generate *wrapper* file (sketch include + main()).
                        # Handle FastLED projects differently since they provide their own Arduino compatibility
                        # --------------------------------------------------
                        if not wrapper_path.exists():
                            fastled_detected = self._detect_fastled_usage(src_dir)

                            if fastled_detected:
                                # For FastLED projects, don't include Arduino.h since FastLED provides compatibility
                                wrapper_content = (
                                    "// Auto-generated by pio_compiler – do **NOT** edit.\n"
                                    "// Minimal wrapper for FastLED projects on native platform.\n"
                                    "// FastLED provides its own Arduino compatibility layer.\n\n"
                                    f'#include "{sketch.name}"\n\n'
                                    "int main() {\n"
                                    "    setup();\n"
                                    "    while (true) { loop(); }\n"
                                    "    return 0;\n"
                                    "}\n"
                                )
                            else:
                                wrapper_content = (
                                    "// Auto-generated by pio_compiler – do **NOT** edit.\n"
                                    "// Minimal wrapper so that PlatformIO's *native* environment compiles a\n"
                                    "// plain Arduino *.ino* sketch with full Arduino API compatibility.\n\n"
                                    '#include "Arduino.h"\n'
                                    f'#include "{sketch.name}"\n\n'
                                    "int main() {\n"
                                    "    setup();\n"
                                    "    while (true) { loop(); }\n"
                                    "    return 0;\n"
                                    "}\n"
                                )
                            wrapper_path.write_text(wrapper_content, encoding="utf-8")
                            copied_paths.append(
                                str(wrapper_path.relative_to(project_dir))
                            )
            else:
                # Single file – copy and rename to *main*.
                dest_file = src_dir / f"main{example_path.suffix}"
                shutil.copy(example_path, dest_file)
                copied_paths.append(str(dest_file.relative_to(project_dir)))

            # Write platformio.ini in project_dir with user-provided contents.
            ini_path = project_dir / "platformio.ini"
            # Use project-specific platformio.ini generation that can handle local platform paths
            ini_content = self.platform.get_platformio_ini_for_project(project_dir)
            ini_path.write_text(ini_content, encoding="utf-8")

            # ------------------------------------------------------------------
            # Persist list of copied/generated paths so that external tools (and
            # the *fast compile* cache eviction logic) can remove artefacts
            # deterministically.
            # ------------------------------------------------------------------

            if copied_paths:
                cleanup_file = project_dir / "_pio_cleanup.txt"
                # Ensure parent exists (it always should) and write one path per
                # line – use POSIX style for portability across OSes.
                cleanup_file.write_text(
                    "\n".join(sorted(set(copied_paths))) + "\n", encoding="utf-8"
                )

        # Ensure that the *platformio* executable is present – without it the
        # compiler cannot proceed.  Fail early with a clear message instead of
        # silently falling back to *simulation*.
        pio_executable = shutil.which("platformio")
        assert (
            pio_executable is not None
        ), "PlatformIO executable not found in PATH – cannot compile."

        # ------------------------------------------------------------------
        # Set up environment for PlatformIO commands
        # ------------------------------------------------------------------
        import os

        pio_home = project_dir / ".pio_home"
        pio_home.mkdir(exist_ok=True)
        env = os.environ.copy()
        env["PLATFORMIO_CORE_DIR"] = str(pio_home)

        # ------------------------------------------------------------------
        # Real build – invoke ``platformio`` and capture its output.
        # ------------------------------------------------------------------

        # First, handle force rebuild by cleaning unconditionally if requested
        if self.force_rebuild:
            logger.debug("Force clean build requested - cleaning all build artifacts")

            # Clean the PlatformIO build directory unconditionally
            pio_build_dir = project_dir / ".pio"
            if pio_build_dir.exists():
                logger.debug("Removing PlatformIO build directory: %s", pio_build_dir)
                try:
                    shutil.rmtree(pio_build_dir)
                    logger.debug("Successfully removed PlatformIO build directory")
                except Exception as e:
                    logger.warning("Failed to remove PlatformIO build directory: %s", e)
                    # Continue with build anyway

            # Also run platformio clean command for any additional cleanup
            clean_cmd = [
                pio_executable,
                "run",
                "-d",
                str(project_dir),
                "--target",
                "clean",
            ]
            logger.debug("Executing clean command: %s", clean_cmd)

            # Run clean command synchronously
            clean_result = subprocess.run(
                clean_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                env=env,
            )

            if clean_result.returncode != 0:
                logger.warning(
                    "Clean command failed with exit code %d: %s",
                    clean_result.returncode,
                    clean_result.stdout,
                )
                # Continue with build anyway - sometimes clean fails but build still works
            else:
                logger.debug("Clean completed successfully")

        # Build the main compile command
        cmd = [pio_executable, "run", "-d", str(project_dir)]

        # Always pass --disable-auto-clean to platformio (new default behavior)
        cmd.append("--disable-auto-clean")

        # Enable a *light* verbose mode for the *uno* platform so that
        # PlatformIO prints the executed commands as well as the paths of
        # generated object files and firmware images.  This, in combination
        # with the additional *print* statements above, gives users a clear
        # picture of where artefacts are placed during the build.
        if self.platform.name == "uno":
            cmd.append("-v")

            # Pre-announce the expected build output directory to improve
            # discoverability for users who only skim the logs.
            build_dir = project_dir / ".pio" / "build" / "uno"
            firmware_elf = build_dir / "firmware.elf"
            print(
                f"{UNO_PREFIX} Build directory (will be created by PlatformIO): {PATH_COLOR}{build_dir}{Style.RESET_ALL}"
            )
            print(
                f"{UNO_PREFIX} Expected firmware artefact:                   {PATH_COLOR}{firmware_elf}{Style.RESET_ALL}"
            )

        logger.debug("Executing command: %s", cmd)
        # Use default buffering for the subprocess pipe.  Passing *bufsize=1*
        # triggers a *RuntimeWarning* on Python ≥3.9 when the stream is opened
        # in *binary* mode (the default when *text* is *False*).  Default
        # buffering avoids the warning while still providing timely output.

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout
            env=env,
        )

        return CompilerStream(popen=proc)

    # --------------------------------------------------------------
    # *multi_compile* – convenience wrapper.
    # --------------------------------------------------------------
    def multi_compile(self, examples: Sequence[Path | str]) -> List["CompilerStream"]:
        """Compile *multiple* examples and return their streams."""

        return [self.compile(ex) for ex in examples]

    # --------------------------------------------------------------
    # Internal helpers.
    # --------------------------------------------------------------
    @staticmethod
    def _env(key: str, default: str | None = None) -> str | None:  # pragma: no cover
        """Return value of *key* from the environment or *default*."""

        import os

        return os.environ.get(key, default)

    def _detect_fastled_usage(self, src_dir: Path) -> bool:
        """Detect if FastLED is being used in the project.

        FastLED provides its own Arduino compatibility layer, so we don't need
        to inject our own if FastLED is present.
        """
        # Check for FastLED includes in .ino files
        for ino_file in src_dir.glob("*.ino"):
            try:
                content = ino_file.read_text(encoding="utf-8")
                if (
                    "#include <FastLED.h>" in content
                    or '#include "FastLED.h"' in content
                ):
                    logger.debug(
                        "FastLED detected in %s - skipping Arduino compatibility injection",
                        ino_file,
                    )
                    return True
            except (UnicodeDecodeError, OSError):
                continue

        # Check for FastLED includes in .cpp/.c files
        for cpp_file in src_dir.glob("*.cpp"):
            try:
                content = cpp_file.read_text(encoding="utf-8")
                if (
                    "#include <FastLED.h>" in content
                    or '#include "FastLED.h"' in content
                ):
                    logger.debug(
                        "FastLED detected in %s - skipping Arduino compatibility injection",
                        cpp_file,
                    )
                    return True
            except (UnicodeDecodeError, OSError):
                continue

        return False

    def _inject_arduino_compatibility(
        self, src_dir: Path, fastled_mode: bool = False
    ) -> None:
        """Inject Arduino.h and arduino.cpp compatibility files for native compilation.

        These files provide a comprehensive Arduino API implementation that works
        on native platforms, allowing Arduino sketches to compile and run on host systems.

        Args:
            src_dir: Directory to inject the files into
            fastled_mode: If True, inject FastLED-specific implementation alongside Arduino.h
        """
        # Get the assets directory relative to this module
        assets_dir = Path(__file__).parent / "assets"

        arduino_h_source = assets_dir / "Arduino.h"
        arduino_cpp_source = assets_dir / "arduino.cpp"

        arduino_h_dest = src_dir / "Arduino.h"
        arduino_cpp_dest = src_dir / "arduino.cpp"

        # Always inject Arduino.h header for native platform compatibility
        if arduino_h_source.exists() and not arduino_h_dest.exists():
            logger.debug("Injecting Arduino.h compatibility header")
            shutil.copy(arduino_h_source, arduino_h_dest)

        # For FastLED projects, inject FastLED-specific implementation
        # For non-FastLED projects, inject standard Arduino implementation
        if fastled_mode:
            fastled_impl_source = assets_dir / "fastled_arduino_impl.cpp"
            fastled_impl_dest = src_dir / "fastled_arduino_impl.cpp"
            if fastled_impl_source.exists() and not fastled_impl_dest.exists():
                logger.debug("Injecting FastLED-specific Arduino implementation")
                shutil.copy(fastled_impl_source, fastled_impl_dest)
        else:
            # For non-FastLED projects, inject standard Arduino implementation
            if arduino_cpp_source.exists() and not arduino_cpp_dest.exists():
                logger.debug("Injecting arduino.cpp compatibility implementation")
                shutil.copy(arduino_cpp_source, arduino_cpp_dest)

    def _validate_example_path(self, example_path: Path) -> str | None:
        """Validate that the example path is suitable for compilation.

        Returns None if valid, or an error message string if invalid.
        Provides helpful guidance on what the caller should provide.
        """
        if not example_path.exists():
            return (
                f"Example path does not exist: {example_path}\n"
                f"Expected: Either a directory containing .ino files, or a single .ino file.\n"
                f"Example usage:\n"
                f"  - Point to a directory: /path/to/MyProject/ (containing MyProject.ino)\n"
                f"  - Point to a single file: /path/to/MyProject/MyProject.ino"
            )

        if example_path.is_file():
            if example_path.suffix.lower() != ".ino":
                return (
                    f"Expected an Arduino sketch (.ino) file, but got: {example_path}\n"
                    f"File extension: {example_path.suffix}\n"
                    f"Arduino sketches must have a .ino extension.\n"
                    f"Example: MyProject.ino"
                )
            # Single .ino file is valid
            return None

        if example_path.is_dir():
            # Check if it's already a PlatformIO project
            if (example_path / "platformio.ini").exists():
                # Existing PlatformIO project is always valid
                return None

            # For regular directories, we expect .ino files
            ino_files = list(example_path.glob("*.ino"))

            if not ino_files:
                dir_contents = list(example_path.iterdir())
                content_summary = f"Found {len(dir_contents)} files/directories"
                if dir_contents:
                    sample_files = [f.name for f in dir_contents[:3]]
                    if len(dir_contents) > 3:
                        sample_files.append("...")
                    content_summary += f": {', '.join(sample_files)}"

                return (
                    f"No Arduino sketch (.ino) files found in directory: {example_path}\n"
                    f"{content_summary}\n"
                    f"Expected: A directory containing at least one .ino file, such as:\n"
                    f"  {example_path}/MyProject.ino\n"
                    f"Or provide a path to an existing PlatformIO project with platformio.ini"
                )

            if len(ino_files) > 1:
                ino_names = [f.name for f in ino_files]
                logger.info(
                    f"{INFO_PREFIX} Found multiple .ino files in %s: %s. Using first one: %s",
                    example_path,
                    ino_names,
                    ino_files[0].name,
                )

            # Directory with .ino files is valid
            return None

        # Not a file or directory (shouldn't happen, but handle gracefully)
        return (
            f"Invalid path type: {example_path}\n"
            f"Expected either a file or directory, but got something else.\n"
            f"Please provide either:\n"
            f"  - A directory containing .ino files\n"
            f"  - A single .ino file"
        )
