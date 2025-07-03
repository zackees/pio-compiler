from dataclasses import dataclass, field
from pathlib import Path

# Import Board but use TYPE_CHECKING to avoid circular imports
from typing import TYPE_CHECKING, Any, Optional, Union

if TYPE_CHECKING:
    from .boards import Board


@dataclass(slots=True)
class Platform:
    """Representation of a target platform supported by PlatformIO."""

    name: str
    platformio_ini: str | None = None
    turbo_dependencies: list[str] = field(default_factory=list)
    _board: "Board | None" = field(default=None, init=False)

    def __init__(
        self,
        name_or_board: Union[str, "Board"],
        platformio_ini: str | None = None,
        turbo_dependencies: list[str] | None = None,
    ):
        """Create a Platform from either a string name or a Board object.

        Args:
            name_or_board: Either a string platform name or a Board object
            platformio_ini: Optional platformio.ini content (ignored if Board is provided)
            turbo_dependencies: List of library names for turbo (symlinked) dependencies
        """
        if isinstance(name_or_board, str):
            # Create from string name
            self.name = name_or_board
            self.platformio_ini = platformio_ini
            self.turbo_dependencies = turbo_dependencies or []
            self._board = None
        else:
            # Create from Board object
            from .boards import Board

            if isinstance(name_or_board, Board):
                self.name = name_or_board.board_name
                self.platformio_ini = name_or_board.to_platformio_ini()
                self.turbo_dependencies = turbo_dependencies or []
                self._board = name_or_board
            else:
                raise TypeError(f"Expected str or Board, got {type(name_or_board)}")

        # Call __post_init__ manually since we're overriding __init__
        self.__post_init__()

    @classmethod
    def from_board(cls, board: "Board") -> "Platform":
        """Create a Platform from a Board object.

        Args:
            board: Board object to create Platform from

        Returns:
            Platform instance with platformio_ini generated from the Board
        """
        return cls(board)

    def __post_init__(self) -> None:  # pragma: no cover
        if self.platformio_ini is None:
            # Populate with a minimal default so that the user can still build
            # with *native* or any other platform by name alone.
            self.platformio_ini = _default_platformio_ini(self.name)

    def get_platformio_ini_for_project(self, project_dir: Path) -> str:
        """Get platformio.ini content with project-specific platform paths.

        Args:
            project_dir: The project directory where the build is happening

        Returns:
            platformio.ini content with correct platform paths
        """
        # For native/dev platforms, always regenerate to check for local platform
        if self.name in ["native", "dev"]:
            return _default_platformio_ini_for_project(self.name, project_dir)

        # For other platforms, use the cached platformio_ini if available
        if self.platformio_ini is not None:
            return self.platformio_ini

        # Fallback to generating default
        return _default_platformio_ini_for_project(self.name, project_dir)

    @property
    def board(self) -> "Board | None":
        """Get the associated Board object if this Platform was created from a Board."""
        return self._board


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

    Note: This function is used when no project directory context is available.
    For project-specific configurations, use _default_platformio_ini_for_project.
    """
    return _default_platformio_ini_for_project(platform_name, None)


def _default_platformio_ini_for_project(
    platform_name: str, project_dir: Path | None
) -> str:  # pragma: no cover
    """Return a minimal platformio.ini for *native* builds or a generic platform.

    This function is *not* exhaustive – it only provides a working default for
    the built-in *native* environment and leaves other environments for the
    user to define explicitly.

    Args:
        platform_name: Name of the platform
        project_dir: Project directory (used to check for local platform downloads)
    """
    # Platform aliases that should be expanded to full GitHub URLs
    platform_aliases = {
        "native": "https://github.com/platformio/platform-native.git",
        "dev": "https://github.com/platformio/platform-native.git",
    }

    # Check if this is a platform alias that should be expanded
    if platform_name in platform_aliases:
        # Check if we have a local platform symlink/copy available
        # This will be set up by the compiler when it downloads the platform
        local_platform_path = None
        if project_dir is not None:
            local_platform_path = project_dir / "platforms" / platform_name.lower()

        if local_platform_path and local_platform_path.exists():
            # Use local platform path - PlatformIO supports file:// URLs for local platforms
            platform_spec = f"file://{local_platform_path.resolve()}"
        else:
            # Fall back to GitHub URL if local platform not available
            platform_spec = platform_aliases[platform_name]

        # Provide an opinionated *native* configuration that is suitable for
        # building sketches on the host machine.  The configuration mirrors
        # what users would typically write in a ``platformio.ini`` when
        # experimenting locally with the *native* platform:
        #
        #   * The dedicated ``[platformio]`` section makes the project layout
        #     explicit and avoids PlatformIO searching parent directories for
        #     other configuration files.
        #   * A custom *dev* environment is used instead of the default
        #     *native* one because this is exactly what many real-world
        #     projects do.  It also doubles as a litmus-test that the
        #     compiler does not make any assumptions regarding the exact
        #     environment name.
        #   * ``platform = file://...`` is used to reference the locally downloaded
        #     platform instead of using PlatformIO's platform registry.
        #   * Libraries can be added via --lib flags or by manually specifying
        #     lib_deps in a custom platformio.ini file.
        return f"""[platformio]
src_dir = src

[env:dev]
platform = {platform_spec}

; Allow libraries that do not explicitly declare compatibility with the
; *platformio/native* platform so that libraries become available even though
; their manifests might only list *embedded* targets.
lib_compat_mode = off

build_flags =
    -DFASTLED_STUB_IMPL
    -std=c++17
    -Isrc/pio_compiler/assets
"""

    # ------------------------------------------------------------------
    # Common *board* aliases – map frequently used board IDs directly to a
    # working PlatformIO configuration so that users can compile sketches
    # with the intuitive command‐line form::
    #
    #     pio-compile examples/Blink --uno
    #
    # without having to hand‐craft a custom *platformio.ini* file.  The
    # mapping is intentionally *minimalist* and only covers targets that are
    # surfaced directly via the CLI (e.g. *uno*).  Power users can always
    # override the automatically generated configuration by supplying their
    # own :pyattr:`Platform.platformio_ini` string.
    # ------------------------------------------------------------------

    board_aliases = {
        # Classic 8-bit AVR boards ---------------------------------------
        "uno": {
            "platform": "atmelavr",
            "board": "uno",
            "framework": "arduino",
        },
        "teensy30": {
            "platform": "teensy",
            "board": "teensy30",
            "framework": "arduino",
        },
        # Additional aliases can be added here as the need arises.
    }

    if platform_name in board_aliases:
        env = board_aliases[platform_name]
        ini_lines = ["[platformio]", "src_dir = src", "", f"[env:{platform_name}]"]
        ini_lines.extend(f"{key} = {value}" for key, value in env.items())
        # Ensure file ends with newline for prettiness.
        return "\n".join(ini_lines) + "\n"

    return f"[env:{platform_name}]\nplatform = {platform_name}\n"
