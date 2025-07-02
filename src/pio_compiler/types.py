from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


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
    build_info: dict[str, Any] = field(default_factory=dict)
    exception: Optional[Exception] = None

    # A user-friendly ``__bool__`` is handy in client code (e.g. ``if result: …``)
    def __bool__(self) -> bool:  # pragma: no cover
        return self.ok


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
