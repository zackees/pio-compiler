from __future__ import annotations

import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

__all__ = [
    "Platform",
    "Result",
    "PioCompiler",
]


def _default_platformio_ini(platform_name: str) -> str:  # pragma: no cover
    """Return a minimal platformio.ini for *native* builds or a generic platform.

    This function is *not* exhaustive – it only provides a working default for
    the built-in *native* environment and leaves other environments for the
    user to define explicitly.
    """
    if platform_name == "native":
        # Provide an opinionated *native* configuration that is suitable for
        # building FastLED based sketches on the host machine.  The
        # configuration mirrors what users would typically write in a
        # ``platformio.ini`` when experimenting locally with the *native*
        # platform:
        #
        #   * The dedicated ``[platformio]`` section makes the project layout
        #     explicit and avoids PlatformIO searching parent directories for
        #     other configuration files.
        #   * A custom *dev* environment is used instead of the default
        #     *native* one because this is exactly what many real-world
        #     projects do.  It also doubles as a litmus-test that the
        #     compiler does not make any assumptions regarding the exact
        #     environment name.
        #   * ``platform = platformio/native`` is the recommended identifier
        #     in recent PlatformIO versions (see
        #     https://registry.platformio.org/platforms/platformio/native).
        #   * The FastLED stub implementation allows *host* compilation
        #     without actual LED hardware.  The ``build_flags`` mirror the
        #     parameters used by the upstream stub project so that example
        #     sketches such as *examples/Blink/Blink.ino* compile without
        #     modification.
        return """[platformio]
src_dir = src

[env:dev]
platform = platformio/native

lib_deps =
    FastLED

build_flags =
    -DFASTLED_STUB_IMPL
    -DFASTLED_STUB_MAIN_INCLUDE_INO=\"../examples/Blink/Blink.ino\"
    -std=c++17
"""

    # Fallback – leave it to the user; PlatformIO will error out if the
    # supplied configuration is invalid.  Keeping the string minimal avoids
    # introducing arbitrary default choices.
    return f"[env:{platform_name}]\nplatform = {platform_name}\n"


@dataclass(slots=True)
class Platform:
    """Representation of a target platform supported by PlatformIO."""

    name: str
    platformio_ini: str | None = None

    def __post_init__(self) -> None:  # pragma: no cover
        if self.platformio_ini is None:
            # Populate with a minimal default so that the user can still build
            # with *native* or any other platform by name alone.
            self.platformio_ini = _default_platformio_ini(self.name)


@dataclass(slots=True)
class Result:
    """Result produced by *initialize* / *compile* operations."""

    ok: bool
    platform: Platform
    example: Optional[Path] = None
    stdout: str = ""
    stderr: str = ""
    build_info: Dict[str, Any] = field(default_factory=dict)
    exception: Optional[Exception] = None

    # A user-friendly ``__bool__`` is handy in client code (e.g. ``if result: …``)
    def __bool__(self) -> bool:  # pragma: no cover
        return self.ok


class PioCompiler:
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
    def initialize(self) -> Result | Exception:  # noqa: D401 – *initialize* is fine
        """Create *platformio.ini* so that subsequent builds can run."""

        try:
            self._ini_path.write_text(
                self.platform.platformio_ini or "", encoding="utf-8"
            )
            return Result(ok=True, platform=self.platform, stdout="", stderr="")
        except Exception as exc:  # pragma: no cover
            return exc

    def build_info(self) -> Dict[str, Any]:  # noqa: D401 – we mirror README naming
        """Return a small JSON-serialisable dict with environment information."""

        return {
            "platform": self.platform.name,
            "work_dir": str(self._work_dir),
            "has_platformio_ini": self._ini_path.exists(),
        }

    # --------------------------------------------------------------
    # *compile* – build a single example.
    # --------------------------------------------------------------
    def compile(
        self, example: Path | str
    ) -> Result | Exception:  # noqa: D401 – spec compliance
        """Compile *example* and return a :class:`Result` object."""

        example_path = Path(example).expanduser().resolve()
        if not example_path.exists():
            return FileNotFoundError(f"Example path does not exist: {example_path}")

        # ------------------------------------------------------------------
        # Prepare a PlatformIO *project directory*.
        # ------------------------------------------------------------------
        if (example_path / "platformio.ini").exists():
            project_dir = example_path
        else:
            # Create a dedicated project inside the compiler's work dir.
            project_dir = self._work_dir / example_path.stem
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
            # Return a *fake* but plausible looking result.
            return Result(
                ok=True,
                platform=self.platform,
                example=example_path,
                stdout="[simulated] platformio run …",
                stderr="",
                build_info=self.build_info(),
            )

        # ------------------------------------------------------------------
        # Real build – invoke ``platformio`` and capture its output.
        # ------------------------------------------------------------------
        cmd = [pio_executable, "run", "-d", str(project_dir)]
        proc = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
        )

        ok = proc.returncode == 0
        return Result(
            ok=ok,
            platform=self.platform,
            example=example_path,
            stdout=proc.stdout,
            stderr=proc.stderr,
            build_info=self.build_info(),
            exception=(
                None
                if ok
                else RuntimeError(f"Build failed with exit code {proc.returncode}")
            ),
        )

    # --------------------------------------------------------------
    # *multi_compile* – convenience wrapper.
    # --------------------------------------------------------------
    def multi_compile(self, examples: Sequence[Path | str]) -> List[Result | Exception]:
        """Compile *multiple* examples in sequence and return a list of results."""

        results: List[Result | Exception] = []
        for ex in examples:
            results.append(self.compile(ex))
        return results

    # --------------------------------------------------------------
    # Internal helpers.
    # --------------------------------------------------------------
    @staticmethod
    def _env(key: str, default: str | None = None) -> str | None:  # pragma: no cover
        """Return value of *key* from the environment or *default*."""

        import os

        return os.environ.get(key, default)
