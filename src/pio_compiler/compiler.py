from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from . import tempdir
from .compiler_stream import CompilerStream
from .types import Platform, Result

__all__ = [
    "Platform",
    "Result",
    "PioCompilerImpl",
]

logger = logging.getLogger(__name__)


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
    ) -> None:
        self.platform = platform
        self.fast_mode = fast_mode
        self.disable_auto_clean = disable_auto_clean
        self.force_rebuild = force_rebuild
        logger.debug(
            "Creating PioCompilerImpl for platform %s (fast_mode=%s, disable_auto_clean=%s, force_rebuild=%s)",
            platform.name,
            fast_mode,
            disable_auto_clean,
            force_rebuild,
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
                # (e.g., ".tpo_fast_cache/Blink-native"), so we don't need to add the project name again
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
            # (e.g., ".tpo_fast_cache/Blink-native"), so we don't need to add the project name again
            if self.fast_mode:
                project_dir = self._work_dir
            else:
                project_dir = self._work_dir / example_path.stem
            logger.debug("Creating isolated project directory %s", project_dir)
            src_dir = project_dir / "src"
            src_dir.mkdir(parents=True, exist_ok=True)

            # --------------------------------------------------------------
            # When compiling for the *uno* platform we emit user-friendly
            # *print* statements that highlight the directories and build
            # artefacts involved.  The messages are intentionally kept very
            # lightweight so that they do not overwhelm normal output but
            # still provide helpful breadcrumbs when users wonder where the
            # temporary files live.
            # --------------------------------------------------------------
            if self.platform.name == "uno":
                print(f"[UNO] Project directory: {project_dir}")
                print(f"[UNO] Source directory:   {src_dir}")

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
            ini_path.write_text(self.platform.platformio_ini or "", encoding="utf-8")

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

        # First, handle force rebuild by running clean if requested
        if self.force_rebuild:
            logger.debug("Force rebuild requested - running clean first")
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
            print(f"[UNO] Build directory (will be created by PlatformIO): {build_dir}")
            print(f"[UNO] Expected firmware artefact:                   {firmware_elf}")

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
                    "Found multiple .ino files in %s: %s. Using first one: %s",
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
