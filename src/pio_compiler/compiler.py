from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

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

    def __init__(self, platform: Platform, work_dir: Optional[Path] = None) -> None:
        self.platform = platform
        logger.debug("Creating PioCompilerImpl for platform %s", platform.name)
        # Work in a dedicated temporary directory unless the caller wants a
        # persistent *work_dir*.
        self._work_dir = (
            Path(work_dir)
            if work_dir is not None
            else Path(tempfile.mkdtemp(prefix="pio_compiler_"))
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
        if not example_path.exists():
            logger.warning("Example path does not exist: %s", example_path)
            return CompilerStream(
                popen=None,
                preloaded_output=f"Example path does not exist: {example_path}",
            )

        # ------------------------------------------------------------------
        # Prepare a PlatformIO *project directory*.
        # ------------------------------------------------------------------
        if (example_path / "platformio.ini").exists():
            project_dir = example_path
        else:
            # Create a dedicated project inside the compiler's work dir.
            project_dir = self._work_dir / example_path.stem
            logger.debug("Creating isolated project directory %s", project_dir)
            src_dir = project_dir / "src"
            src_dir.mkdir(parents=True, exist_ok=True)

            if example_path.is_dir():
                # Copy everything from the example directory into *src*.
                for file in example_path.iterdir():
                    shutil.copy(file, src_dir / file.name)

                # ------------------------------------------------------------------
                # *Native* platform special-case – PlatformIO's **native** platform
                # does **not** understand Arduino ``*.ino`` sketches directly.  To
                # let users point the compiler at an Arduino example and still
                # compile for the host we auto-generate a tiny C++ translation unit
                # that simply includes the sketch source.  When the "FastLED stub"
                # is used (activated via the ``FASTLED_STUB_IMPL`` /
                # ``FASTLED_STUB_MAIN_INCLUDE_INO`` defines) the stub provides a
                # valid *main()* implementation so that the host compiler is
                # satisfied.
                #
                # The generated file lives inside *src* so that the default
                # ``src_dir = src`` setting picks it up automatically.
                # ------------------------------------------------------------------
                if self.platform.name == "native":
                    ino_files = list(src_dir.glob("*.ino"))
                    if ino_files:
                        logger.debug(
                            "Generating native wrapper for sketch %s", ino_files[0]
                        )
                        sketch = ino_files[0]
                        wrapper_path = src_dir / "_pio_main.cpp"
                        if not wrapper_path.exists():
                            wrapper_content = (
                                "// Auto-generated by pio_compiler – do **NOT** edit.\n"
                                "// This wrapper allows PlatformIO's *native* environment to compile an\n"
                                "// Arduino sketch by pulling it into a regular C++ translation unit.\n\n"
                                f'#include "{sketch.name}"\n'
                            )
                            wrapper_path.write_text(wrapper_content, encoding="utf-8")
            else:
                # Single file – copy and rename to *main*.
                shutil.copy(example_path, src_dir / f"main{example_path.suffix}")

            # Write platformio.ini in project_dir with user-provided contents.
            (project_dir / "platformio.ini").write_text(
                self.platform.platformio_ini or "", encoding="utf-8"
            )

        # The real PlatformIO build can be *expensive* and requires external
        # tools.  To make the library usable in restrictive environments (CI
        # sandboxes, unit-test runners, …) we fall back to a *simulation* mode
        # when the dedicated environment variable is set *or* when the
        # platformio executable cannot be found.
        simulate_env = self._env(self._SIMULATE_ENV)
        simulate = bool(
            simulate_env and simulate_env not in {"0", "false", "False", "no", "NO"}
        )
        pio_executable = shutil.which("platformio")
        if pio_executable is None:
            simulate = True

        if simulate:
            logger.info("Simulation mode active – returning fake CompilerStream")
            # Return a *fake* but plausible looking result.
            return CompilerStream(
                popen=None, preloaded_output="[simulated] platformio run …"
            )

        # ------------------------------------------------------------------
        # Real build – invoke ``platformio`` and capture its output.
        # ------------------------------------------------------------------
        cmd = [pio_executable, "run", "-d", str(project_dir)]
        logger.debug("Executing command: %s", cmd)
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # merge stderr into stdout
            bufsize=1,
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
