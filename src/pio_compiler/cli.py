"""Command-line interface entry-point for *pio_compiler*.

The CLI provides a very thin wrapper around :class:`pio_compiler.compiler.PioCompilerImpl`.
It supports *positional* platform selection and one or more ``--src`` flags to
compile multiple examples in a single invocation.

The behaviour with *no* arguments is kept intentionally trivial to satisfy the
existing unit-test suite: the function returns *0* immediately, printing a
short informational message.  Users are expected to pass at least one
argument; in that case the full parser is executed.
"""

from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path

from colorama import Fore, Style, init

from pio_compiler import PioCompiler, Platform
from pio_compiler.boards import ALL as ALL_BOARDS
from pio_compiler.cache_manager import CacheEntry
from pio_compiler.global_cache import GlobalCacheManager
from pio_compiler.logging_utils import configure_logging
from pio_compiler.tempdir import cleanup_all

# Initialize colorama for Windows support
init(autoreset=True)

# Configure logging early so that all sub-modules use the same defaults when the
# CLI is the entry-point.  Users can still override the configuration by
# calling :pyfunc:`pio_compiler.configure_logging` *before* executing the CLI
# or by setting the *PIO_COMPILER_LOG_LEVEL* environment variable.
configure_logging()

# Module-level logger – prefer ``logger`` over bare ``print`` for internal
# status messages.  The CLI still uses *print* for user-facing output so that
# scripts expecting *stdout* messages continue to work unchanged.
logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------
# Pretty *npm-style* startup banner helpers.
# Defined **early** so that _run_cli can call them immediately.
# ----------------------------------------------------------------------


def _ansi(code: str) -> str:  # helper – wrap ANSI codes only when supported
    if not sys.stdout.isatty() or os.getenv("NO_COLOR") is not None:
        return ""
    return f"\033[{code}m"


_BOLD = _ansi("1")
_RESET = _ansi("0")
_CYAN = _ansi("36")
_GREEN = _ansi("32")
_YELLOW = _ansi("33")
_MAGENTA = _ansi("35")
_RED = _ansi("31")


def _print_error(message: str, path: str | None = None) -> None:
    """Print a stylish npm-style error message with colorama and emoticons."""
    # Use colorama for cross-platform color support
    error_emoji = "❌"

    # Try to encode the emoji to see if it's supported
    try:
        error_emoji.encode(sys.stdout.encoding or "utf-8")
    except (UnicodeEncodeError, LookupError):
        # Fallback to ASCII if emoji not supported
        error_emoji = "✗"
        try:
            error_emoji.encode(sys.stdout.encoding or "utf-8")
        except (UnicodeEncodeError, LookupError):
            # Final fallback
            error_emoji = "X"

    # Create the styled error message
    if path:
        error_msg = f"{Fore.RED}{Style.BRIGHT}{error_emoji} {message}: {Fore.YELLOW}{path}{Style.RESET_ALL}"
    else:
        error_msg = f"{Fore.RED}{Style.BRIGHT}{error_emoji} {message}{Style.RESET_ALL}"

    print(error_msg, file=sys.stderr)


def _tool_version() -> str:
    try:
        return _pkg_version("pio_compiler")
    except PackageNotFoundError:
        return "dev"


# Determine whether the current stdout encoding supports common Unicode symbols.
_UNICODE_OK = True
try:
    "⚡".encode(sys.stdout.encoding or "utf-8")
except Exception:  # pragma: no cover – fallback when encoding unsupported
    _UNICODE_OK = False


def _sym(unicode_symbol: str, ascii_fallback: str) -> str:
    """Return *unicode_symbol* if terminal encoding supports it, else *ascii_fallback*."""

    return unicode_symbol if _UNICODE_OK else ascii_fallback


def _format_path_for_logging(path: Path) -> str:
    """Format a path for logging according to user preferences.

    - If the path is absolute but under current working directory, convert to relative with forward slashes
    - If the path is absolute but outside current working directory, keep it as-is (Windows/Unix style preserved)
    - If the path is already relative, convert to forward slashes
    """
    try:
        # Convert to Path object if it isn't already
        if not isinstance(path, Path):
            path = Path(path)

        # Try to make absolute paths relative to current working directory
        if path.is_absolute():
            try:
                cwd = Path.cwd()
                # If the path is under the current working directory, make it relative
                relative_path = path.relative_to(cwd)
                # Convert to string with forward slashes
                return str(relative_path).replace("\\", "/")
            except ValueError:
                # Path is not under current working directory, keep it as absolute
                return str(path)
        else:
            # Already relative, just convert to forward slashes
            return str(path).replace("\\", "/")

    except Exception:
        # Fallback to string representation if anything goes wrong
        return str(path)


LIGHTNING = _sym("⚡", "*")
ROCKET = _sym("🚀", "-")
PACKAGE = _sym("📦", "#")
HAMMER = _sym("🔨", "!")


def _print_startup_banner(
    *,
    incremental: bool,
    fast_dir: Path | None,
    fast_hit: bool | None,
    cache_dir: str | None,
    clean: bool,
    pio_cache_dir: str | None = None,
) -> None:  # noqa: D401
    """Print a colourful npm-style banner summarising build configuration."""

    header = f"{_BOLD}{_CYAN}{LIGHTNING} pio-compiler v{_tool_version()}{_RESET}"
    print(header)

    if incremental and fast_dir is not None:
        status_colour = _GREEN if fast_hit else _YELLOW
        status = "hit" if fast_hit else "miss"
        formatted_fast_dir = _format_path_for_logging(fast_dir)
        print(
            f"  {status_colour}{ROCKET} Fast cache [{status}]: {formatted_fast_dir}{_RESET}"
        )
    elif clean and fast_dir is not None:
        formatted_fast_dir = _format_path_for_logging(fast_dir)
        print(
            f"  {_MAGENTA}{HAMMER} Clean build using cache: {formatted_fast_dir}{_RESET}"
        )
    elif clean:
        print(f"  {_MAGENTA}{HAMMER} Full clean build – no incremental cache{_RESET}")

    # Show PlatformIO build cache directory with color coding
    if pio_cache_dir is not None:
        # Yellow for clean build, Green for incremental build
        cache_colour = _YELLOW if clean else _GREEN
        cache_status = "clean build" if clean else "incremental"
        formatted_pio_cache_dir = _format_path_for_logging(Path(pio_cache_dir))
        print(
            f"  {cache_colour}{PACKAGE} PIO cache [{cache_status}]: {formatted_pio_cache_dir}{_RESET}"
        )

    if cache_dir is not None:
        formatted_cache_dir = _format_path_for_logging(Path(cache_dir))
        print(f"  {_CYAN}{PACKAGE} Global PIO cache: {formatted_cache_dir}{_RESET}")

    # Trailing newline for separation before build output.
    print()


def _print_info_reports(
    compiler: PioCompiler,
    src_path: Path,
    platform_name: str,
    report_dir: Path | None = None,
    clean_build: bool = False,
) -> None:
    """Print npm-style info about generated optimization reports and build info."""

    # Determine project directory
    if (src_path / "platformio.ini").exists():
        project_dir = src_path
    else:
        if not clean_build:
            project_dir = compiler._work_dir
        else:
            project_dir = compiler._work_dir / src_path.stem

    # Record build start time
    build_start_time = time.time()

    # Generate optimization report
    opt_report_path = compiler.generate_optimization_report(
        project_dir, src_path, report_dir
    )

    # Generate build info
    build_info_path = compiler.generate_build_info(
        project_dir, src_path, build_start_time, report_dir
    )

    # Generate symbols report
    symbols_report_path = compiler.generate_symbols_report(
        project_dir, src_path, report_dir
    )

    # Save platformio.ini as platformio.ini.tpo when --report is specified
    platformio_ini_path = None
    if report_dir is not None:
        platformio_ini_source = project_dir / "platformio.ini"
        if platformio_ini_source.exists():
            try:
                platformio_ini_dest = report_dir / "platformio.ini.tpo"
                import shutil

                shutil.copy(platformio_ini_source, platformio_ini_dest)
                platformio_ini_path = platformio_ini_dest
                logger.debug(f"Saved platformio.ini to: {platformio_ini_path}")
            except Exception as e:
                logger.warning(f"Failed to save platformio.ini.tpo: {e}")

    # Print npm-style output
    header = f"{_BOLD}{_CYAN}build info{_RESET}"
    print(f"\n{header}")

    # Show optimization report
    if opt_report_path:
        formatted_path = _format_path_for_logging(opt_report_path)
        print(
            f"  {_GREEN}[x]{_RESET} Optimization report: {_YELLOW}{formatted_path}{_RESET}"
        )
    else:
        print(f"  {_YELLOW}[ ]{_RESET} Optimization report: generation failed")

    # Show build info
    if build_info_path:
        formatted_path = _format_path_for_logging(build_info_path)
        print(f"  {_GREEN}[x]{_RESET} build_info: {_YELLOW}{formatted_path}{_RESET}")
    else:
        print(f"  {_YELLOW}[ ]{_RESET} build_info: generation failed")

    # Show symbols report
    if symbols_report_path:
        formatted_path = _format_path_for_logging(symbols_report_path)
        print(
            f"  {_GREEN}[x]{_RESET} symbols_report: {_YELLOW}{formatted_path}{_RESET}"
        )
    else:
        print(f"  {_YELLOW}[ ]{_RESET} symbols_report: generation failed")

    # Show platformio.ini.tpo
    if platformio_ini_path:
        formatted_path = _format_path_for_logging(platformio_ini_path)
        print(
            f"  {_GREEN}[x]{_RESET} platformio.ini.tpo: {_YELLOW}{formatted_path}{_RESET}"
        )
    elif report_dir is not None:
        print(f"  {_YELLOW}[ ]{_RESET} platformio.ini.tpo: platformio.ini not found")

    print()  # Trailing newline


def _print_project_info(
    project_path: Path,
    platform_name: str,
    cache_dir: Path | None,
    turbo_dependencies: list[str],
) -> None:
    """Print npm-style project info section with project details and dependencies."""

    # Project info header with gear emoji
    header = f"{_BOLD}{_CYAN}{_sym('⚙️', '#')} Project Info{_RESET}"
    print(header)

    # Project path
    project_emoji = _sym("📁", "[>]")
    formatted_project = _format_path_for_logging(project_path)
    print(
        f"  {_CYAN}{project_emoji}{_RESET} Project: {_YELLOW}{formatted_project}{_RESET}"
    )

    # Platform
    platform_emoji = _sym("🎯", ">")
    print(
        f"  {_CYAN}{platform_emoji}{_RESET} Platform: {_YELLOW}{platform_name}{_RESET}"
    )

    # Platform cache destination
    cache_emoji = _sym("📂", "[+]")
    if cache_dir:
        formatted_cache = _format_path_for_logging(cache_dir)
        print(
            f"  {_CYAN}{cache_emoji}{_RESET} Cache: {_YELLOW}{formatted_cache}{_RESET}"
        )
    else:
        print(
            f"  {_CYAN}{cache_emoji}{_RESET} Cache: {_YELLOW}temporary directory{_RESET}"
        )

    # Turbo Dependencies
    deps_emoji = _sym("⚡", "*")
    if turbo_dependencies:
        print(
            f"  {_GREEN}{deps_emoji}{_RESET} Turbo dependencies ({len(turbo_dependencies)}):"
        )
        for dep in turbo_dependencies:
            check_emoji = _sym("✓", "+")
            print(f"    {_GREEN}{check_emoji}{_RESET} {dep}")
    else:
        print(
            f"  {_YELLOW}{deps_emoji}{_RESET} Turbo dependencies: {_YELLOW}none{_RESET}"
        )

    print()  # Trailing newline for separation


# ----------------------------------------------------------------------
# *CLIArguments* – typed container for parsed command-line options.
# ----------------------------------------------------------------------


@dataclass(slots=True)
class BuildResult:
    """Track the result of a single build."""

    src_path: Path
    platform: str
    success: bool
    time_taken: float
    error_message: str | None = None


@dataclass(slots=True)
class CLIArguments:
    """Structured representation of user-supplied CLI arguments."""

    # List of source paths (sketches)
    src: list[str]
    # List of target platforms
    platforms: list[str]
    # Optional path to a *global* PlatformIO build cache directory.  When
    # provided *pio_compiler* injects the corresponding ``build_cache_dir``
    # option into the generated *platformio.ini* so that subsequent builds
    # share artefacts across independent project directories.
    cache: str | None = None
    # Force a full clean build (inverse of incremental mode)
    clean: bool = False
    # Enable info mode (generate optimization reports and build info)
    info: bool = False
    # Optional path where to save optimization reports and build info
    report: str | None = None
    # List of turbo dependencies (libraries to download and symlink)
    turbo_libs: list[str] = field(default_factory=list)
    # Purge all caches (global and local)
    purge: bool = False


def _parse_arguments(ns: argparse.Namespace) -> CLIArguments:
    """Convert argparse namespace to typed CLIArguments."""

    # Combine positional sketches and --src flags
    src_list: list[str] = []
    if hasattr(ns, "sketch") and ns.sketch:
        src_list.extend(ns.sketch)
    if hasattr(ns, "src") and ns.src:
        src_list.extend(ns.src)

    # Determine platform targets (default to 'native' if none provided)
    platforms_list: list[str] = []
    if hasattr(ns, "platforms") and ns.platforms:
        platforms_list = ns.platforms
    else:
        platforms_list = ["native"]

    return CLIArguments(
        src=src_list,
        platforms=platforms_list,
        cache=getattr(ns, "cache", None),
        clean=getattr(ns, "clean", False),
        info=getattr(ns, "info", False),
        report=getattr(ns, "report", None),
        turbo_libs=getattr(ns, "turbo_libs", []),
        purge=getattr(ns, "purge", False),
    )


def _build_argument_parser() -> argparse.ArgumentParser:
    """Return an :class:`argparse.ArgumentParser` configured for this CLI."""

    parser = argparse.ArgumentParser(
        prog="tpo",
        usage="%(prog)s <sketch_path> [additional_sketches…] --<platform> [options]",
        description=(
            "Compile PlatformIO sketches with optional caching and fast-build capabilities.\n\n"
            "Typical usage:\n"
            "  tpo examples/Blink --uno           # Build Blink.ino for Arduino UNO\n"
            "  tpo examples/Blink --native       # Build for the host (native) platform\n"
            "  tpo project/Sketch --native --fast\n"
            "  tpo project/Sketch --native --clean --cache .pio_cache\n\n"
            "Multiple sketches can be supplied using repeated --src flags or by listing them "
            "sequentially before the platform flag."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=True,
    )
    # --------------------------------------------------------------
    # Platform flags ("--native", "--uno", …) – users can specify one or
    # more.  When omitted the CLI defaults to *native*.
    # --------------------------------------------------------------

    # Get all board names from boards.py
    _PLATFORM_ALIASES = list(set(board.board_name for board in ALL_BOARDS))
    # Ensure native is included (it should already be in ALL_BOARDS)
    if "native" not in _PLATFORM_ALIASES:
        _PLATFORM_ALIASES.append("native")
    # Sort for consistent help output
    _PLATFORM_ALIASES.sort()

    platform_group = parser.add_argument_group("target platforms")

    for _plat in _PLATFORM_ALIASES:
        platform_group.add_argument(
            f"--{_plat}",
            dest="platforms",
            action="append_const",
            const=_plat,
            help=f"Compile for the '{_plat}' platform",
        )
    # Positional sketch paths (one or more)
    parser.add_argument(
        "sketch",
        nargs="*",
        help="Path(s) to PlatformIO project directories or .ino files",
    )

    parser.add_argument(
        "--src",
        metavar="PATH",
        dest="src",
        action="append",
        required=False,
        help=argparse.SUPPRESS,
    )
    # ------------------------------------------------------------------
    # Cache directory is *independent* of build mode.  Users may combine
    # --cache with either fast (default) **or** --clean.
    # ------------------------------------------------------------------

    parser.add_argument(
        "--cache",
        metavar="PATH",
        dest="cache",
        required=False,
        help=(
            "Path to a *global* PlatformIO build cache directory.  Injects the "
            "'build_cache_dir' option into the temporary platformio.ini that "
            "pio_compiler generates for each build.  Re-uses cached object files "
            "between independent compilations for significantly faster builds."
        ),
    )

    # Build mode selection – exactly **one** of the following may be chosen.
    mutex = parser.add_mutually_exclusive_group()

    # (1) Force a *full* clean build – inverse of the default incremental mode.
    mutex.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        help=(
            "Force a full clean build by running 'platformio run --target clean' "
            "before compilation. This removes all build artifacts and starts fresh."
        ),
    )

    # Info flag for generating optimization reports and build info
    parser.add_argument(
        "--info",
        dest="info",
        action="store_true",
        help=(
            "Generate optimization reports and build_info.json files. "
            "This includes memory usage analysis, compilation statistics, "
            "and build information similar to npm build outputs."
        ),
    )

    # Report directory for saving optimization reports and build info
    parser.add_argument(
        "--report",
        metavar="PATH",
        dest="report",
        nargs="?",
        const="",  # Use empty string as const when --report is provided without value
        required=False,
        help=(
            "Generate optimization reports and build_info.json files. "
            "If PATH is provided, saves reports to that directory. "
            "If no PATH is provided, saves reports to the work directory (cache root). "
            "Use '.' to save in the current working directory. "
            "Automatically enables --info mode."
        ),
    )

    # Turbo dependencies (library management)
    parser.add_argument(
        "--lib",
        metavar="LIBRARY",
        dest="turbo_libs",
        action="append",
        required=False,
        help=(
            "Add a turbo dependency library. Downloads the library from GitHub "
            "and symlinks it into the project without using PlatformIO's lib_deps. "
            "Use library name (e.g., 'FastLED') which maps to github.com/fastled/fastled. "
            "Can be used multiple times to add multiple libraries."
        ),
    )

    # Purge all caches
    parser.add_argument(
        "--purge",
        dest="purge",
        action="store_true",
        help=(
            "Purge all caches (both global and local). This removes the global "
            "cache directory (~/.tpo_global) and the local cache directory "
            "(.pio_cache) if they exist. This operation runs immediately and "
            "exits without performing any builds."
        ),
    )

    return parser


def _expand_glob_patterns(patterns: list[str]) -> list[str]:
    """Expand glob patterns to find directories containing .ino files.

    Args:
        patterns: List of paths that may contain glob patterns

    Returns:
        List of expanded paths to directories containing .ino files
    """
    expanded_paths = []

    for pattern in patterns:
        # Check if this looks like a glob pattern
        if any(char in pattern for char in ["*", "?", "["]):
            # Expand the glob pattern
            matches = glob.glob(pattern, recursive=True)

            # Filter to only include directories that contain .ino files
            for match in matches:
                match_path = Path(match)
                if match_path.is_dir():
                    # Check if this directory contains any .ino files
                    ino_files = list(match_path.glob("*.ino"))
                    if ino_files:
                        expanded_paths.append(str(match_path))
                elif match_path.is_file() and match_path.suffix.lower() == ".ino":
                    # If it's an .ino file directly, include its parent directory
                    expanded_paths.append(str(match_path.parent))
        else:
            # Not a glob pattern, keep as-is
            expanded_paths.append(pattern)

    # Remove duplicates while preserving order
    seen = set()
    unique_paths = []
    for path in expanded_paths:
        normalized = str(Path(path).resolve())
        if normalized not in seen:
            seen.add(normalized)
            unique_paths.append(path)

    return unique_paths


def _run_cli(arguments: list[str]) -> int:
    """Internal helper that contains the real CLI implementation."""

    # Handle built-in help before any custom preprocessing so that users can
    # always rely on "tpo --help" regardless of argument order.
    if any(tok in {"-h", "--help"} for tok in arguments):
        _build_argument_parser().print_help(sys.stdout)
        return 0

    parser = _build_argument_parser()
    ns = parser.parse_args(arguments)

    # Parse namespace into typed arguments
    args = _parse_arguments(ns)

    # ------------------------------------------------------------------
    # Handle purge operation - runs immediately and exits
    # ------------------------------------------------------------------
    if args.purge:
        print(f"{_BOLD}{_CYAN}{LIGHTNING} pio-compiler purge{_RESET}")
        print()

        # Purge global cache
        global_cache_manager = GlobalCacheManager()
        global_cache_root = global_cache_manager.cache_root

        if global_cache_root.exists():
            print(
                f"  {_YELLOW}{_sym('🗑️', 'X')}{_RESET}  Purging global cache: {_format_path_for_logging(global_cache_root)}"
            )
            try:
                successfully_removed, failed_to_remove = (
                    global_cache_manager.purge_cache()
                )

                if successfully_removed:
                    print(
                        f"  {_GREEN}{_sym('✓', 'OK')}{_RESET} Global cache purged successfully ({len(successfully_removed)} items removed)"
                    )

                if failed_to_remove:
                    print(
                        f"  {_YELLOW}{_sym('⚠', 'WARN')}{_RESET} Some items could not be removed due to file locks ({len(failed_to_remove)} items):"
                    )
                    for item in failed_to_remove[:5]:  # Show first 5 items
                        print(
                            f"    {_CYAN}• {_format_path_for_logging(Path(item))}{_RESET}"
                        )
                    if len(failed_to_remove) > 5:
                        print(
                            f"    {_CYAN}... and {len(failed_to_remove) - 5} more{_RESET}"
                        )
                    print(
                        f"  {_CYAN}{_sym('ℹ', 'i')}{_RESET} Locked files are likely in use by other processes"
                    )

                if not successfully_removed and not failed_to_remove:
                    print(
                        f"  {_CYAN}{_sym('ℹ', 'i')}{_RESET} Global cache was already empty"
                    )

            except Exception as e:
                print(
                    f"  {_RED}{_sym('✗', 'ERR')}{_RESET} Failed to purge global cache: {e}"
                )
        else:
            print(
                f"  {_CYAN}{_sym('ℹ', 'i')}{_RESET} Global cache directory does not exist"
            )

        # Purge local cache
        local_cache_root = Path.cwd() / ".pio_cache"

        if local_cache_root.exists():
            print(
                f"  {_YELLOW}{_sym('🗑️', 'X')}{_RESET}  Purging local cache: {_format_path_for_logging(local_cache_root)}"
            )
            try:
                cleanup_all()
                print(
                    f"  {_GREEN}{_sym('✓', 'OK')}{_RESET} Local cache purged successfully"
                )
            except Exception as e:
                print(
                    f"  {_RED}{_sym('✗', 'ERR')}{_RESET} Failed to purge local cache: {e}"
                )
        else:
            print(
                f"  {_CYAN}{_sym('ℹ', 'i')}{_RESET} Local cache directory does not exist"
            )

        print()
        print(f"{_GREEN}Cache purge completed.{_RESET}")
        return 0

    # ------------------------------------------------------------------
    # Derive the incremental boolean according to the selected build mode.
    # Precedence order:
    #   1. --clean     → incremental = False
    #   2. default     → incremental = True
    # ------------------------------------------------------------------

    # Always use CacheManager for structured cache directories
    # The force_rebuild parameter will handle clean build behavior
    use_cache_manager: bool = True

    # Incremental build mode (opposite of force_rebuild)
    incremental: bool = True  # default – incremental builds

    if args.clean:
        incremental = False  # Show clean build in banner

    if not args.src:
        logger.error(
            "No sketch paths supplied. Provide at least one path or use --help for usage."
        )
        return 1

    # Expand glob patterns in source paths
    expanded_src = _expand_glob_patterns(args.src)

    if not expanded_src:
        logger.error("No sketches found matching the provided patterns.")
        _print_error("No sketches found matching pattern", None)
        return 1

    # Log if we expanded any patterns
    if len(expanded_src) != len(args.src):
        logger.info(
            f"Expanded {len(args.src)} patterns to {len(expanded_src)} sketch paths"
        )

    # Update args.src with expanded paths
    args.src = expanded_src

    # Validate that all source paths exist
    for src_path in args.src:
        path = Path(src_path).expanduser().resolve()
        if not path.exists():
            logger.error(f"Sketch path does not exist: {src_path}")
            _print_error("Sketch path does not exist", src_path)
            return 1
        if not path.is_dir() and not path.is_file():
            logger.error(f"Sketch path is not a valid file or directory: {src_path}")
            _print_error("Sketch path is not a valid file or directory", src_path)
            return 1

    # Safety: *cache manager* only makes sense for a single platform.
    # Multiple sketches are OK since we use multi_compile.
    if use_cache_manager and len(args.platforms) != 1:
        use_cache_manager = False  # silently fall back to tempdir semantics

    # ------------------------------------------------------------------
    # Inject *build_cache_dir* into the generated *platformio.ini* when the
    # user supplied a ``--cache`` directory.  The helper keeps the modification
    # logic contained so that the rest of the compiler remains unchanged.
    # ------------------------------------------------------------------

    if args.cache:

        from pathlib import Path as _Path

        abs_cache_dir = str(_Path(args.cache).expanduser().resolve())
        # platform.platformio_ini = _with_build_cache_dir(
        #     platform.platformio_ini, abs_cache_dir
        # )

    # ------------------------------------------------------------------
    # *Cache Manager* – always use structured cache directories
    # ------------------------------------------------------------------

    # Initialize cache manager for all builds (replaces legacy tempdir system)
    cache_manager = None
    if use_cache_manager:
        from pio_compiler.cache_manager import CacheManager

        cache_manager = CacheManager()

        # Migrate any old hash-based cache directories to new format
        cache_manager.migrate_old_cache_entries()

    # Parse sketch dependencies from all source files
    sketch_dependencies = []
    for src_path in args.src:
        sketch_path = Path(src_path).expanduser().resolve()
        sketch_deps = _parse_sketch_dependencies(sketch_path)
        sketch_dependencies.extend(sketch_deps)

    # Combine CLI --lib arguments with sketch dependencies (CLI takes precedence)
    all_turbo_libs = list(
        args.turbo_libs or []
    )  # Start with CLI arguments, handle None case
    for dep in sketch_dependencies:
        if dep not in all_turbo_libs:
            all_turbo_libs.append(dep)

    if sketch_dependencies:
        logger.info(f"Found sketch dependencies: {sketch_dependencies}")
    if all_turbo_libs:
        logger.info(f"Using turbo dependencies: {all_turbo_libs}")

    compilers: list[tuple[str, PioCompiler]] = []

    for plat_name in args.platforms:
        # For native, use the string name to get the special native configuration
        # For other platforms, try to get board configuration first
        if plat_name == "native":
            plat_obj = Platform(plat_name, turbo_dependencies=all_turbo_libs)
        else:
            from pio_compiler.boards import get_board

            board = get_board(plat_name)
            plat_obj = Platform(board, turbo_dependencies=all_turbo_libs)

        if args.cache:
            from pathlib import Path as _Path

            abs_cache_dir = str(_Path(args.cache).expanduser().resolve())

            def _inject_cache(base_ini: str | None) -> str:
                if base_ini is None:
                    base_ini = ""
                if "[platformio]" not in base_ini:
                    base_ini = (
                        f"[platformio]\nbuild_cache_dir = {abs_cache_dir}\n\n"
                        + base_ini
                    )
                elif "build_cache_dir" not in base_ini:
                    base_ini = base_ini.replace(
                        "[platformio]",
                        f"[platformio]\nbuild_cache_dir = {abs_cache_dir}",
                    )
                return base_ini

            plat_obj.platformio_ini = _inject_cache(plat_obj.platformio_ini)

        # ---------------- cache directory per platform ----------------
        cache_dir: Path | None = None
        cache_hit: bool | None = None
        cache_entry: CacheEntry | None = None

        if use_cache_manager and cache_manager:
            src_path = Path(args.src[0]).expanduser().resolve()
            cache_entry = cache_manager.get_cache_entry(
                src_path, plat_name, plat_obj.platformio_ini or "", all_turbo_libs
            )

            cache_dir = cache_entry.cache_dir
            cache_hit = cache_entry.exists

            if cache_hit and incremental:
                pass
            elif not cache_hit and incremental:
                cache_dir.mkdir(parents=True, exist_ok=True)
            elif args.clean:
                cache_dir.mkdir(parents=True, exist_ok=True)

        compiler = PioCompiler(
            plat_obj,
            work_dir=cache_dir if use_cache_manager else None,
            force_rebuild=args.clean,
            info_mode=args.info,
            cache_entry=cache_entry if use_cache_manager and cache_manager else None,
        )
        init_result = compiler.initialize()
        if not init_result.ok:
            logger.error(
                "Failed to initialise compiler (%s): %s",
                plat_name,
                init_result.exception,
            )
            return 1

        # Get PlatformIO cache directory for banner display
        pio_cache_dir = None
        if args.src:
            pio_cache_dir = compiler.get_pio_cache_dir(args.src[0])

        compilers.append((plat_name, compiler))

        # Display banner after compiler is initialized
        if incremental:
            _print_startup_banner(
                incremental=True,
                fast_dir=cache_dir,
                fast_hit=cache_hit,
                cache_dir=args.cache,
                clean=False,
                pio_cache_dir=pio_cache_dir,
            )
        else:
            _print_startup_banner(
                incremental=False,
                fast_dir=cache_dir,
                fast_hit=cache_hit,
                cache_dir=args.cache,
                clean=True,
                pio_cache_dir=pio_cache_dir,
            )

    # Compile for each platform
    src_paths = [Path(p) for p in args.src]

    exit_code = 0
    build_results: list[BuildResult] = []  # Track all build results

    for plat_name, compiler in compilers:
        streams = compiler.multi_compile(src_paths)

        for src_path, future in zip(src_paths, streams):
            build_start_time = time.time()  # Record start time

            # Resolve the compilation *Future* – this yields the actual
            # :class:`CompilerStream` instance.
            try:
                stream = future.result()
            except Exception as exc:  # pragma: no cover – treat failures gracefully
                formatted_path = _format_path_for_logging(src_path)
                logger.error("Compilation failed for %s: %s", formatted_path, exc)
                _print_error("Compilation failed", formatted_path)
                exit_code = 1
                # Track failed build
                build_results.append(
                    BuildResult(
                        src_path=src_path,
                        platform=plat_name,
                        success=False,
                        time_taken=time.time() - build_start_time,
                        error_message=f"Compilation failed: {exc}",
                    )
                )
                continue

            formatted_path = _format_path_for_logging(src_path)
            logger.info("[BUILD] %s …", formatted_path)

            # Display project info for this specific project
            _print_project_info(
                project_path=src_path,
                platform_name=plat_name,
                cache_dir=(
                    compiler._work_dir if hasattr(compiler, "_work_dir") else None
                ),
                turbo_dependencies=all_turbo_libs,
            )

            # Use npm-style build message with hammer emoji
            build_emoji = _sym("🔨", ">")
            print(
                f"{_CYAN}{build_emoji}{_RESET} Building: {_YELLOW}{formatted_path}{_RESET} …"
            )

            # Consume stream output until completion.
            accumulated: list[str] = []
            while not stream.is_done():
                line = stream.readline(timeout=0.1)
                if line is None:
                    # No new data yet – continue polling.
                    continue
                accumulated.append(line)
                # Echo live so that users see progress immediately.
                try:
                    print(line, end="")
                except UnicodeEncodeError:
                    # Replace problematic characters to avoid IO errors on narrow encodings.
                    safe = line.encode(errors="replace").decode(
                        sys.stdout.encoding, errors="ignore"
                    )
                    print(safe, end="")

            # Build finished – summarise.
            total_bytes = sum(len(line_) for line_ in accumulated)
            logger.info(
                "[DONE] %s – captured %d bytes of output", formatted_path, total_bytes
            )

            # Don't print the old [DONE] message, it will be replaced by success/failure message below

            # --------------------------------------------------------------
            # Determine build success – propagate non-zero *exit codes* from
            # the underlying *platformio* process so that callers (scripts,
            # CI pipelines, unit tests, …) can reliably detect compilation
            # failures.  *stream._popen* is *None* when the compiler runs in
            # *simulation* mode or when the *example* path was invalid.
            # Treat both situations as *failure* (exit code = 1) so that
            # mis-configurations cannot masquerade as successful builds.
            # --------------------------------------------------------------

            proc_rc: int | None = None
            if getattr(stream, "_popen", None) is not None:
                proc_rc = stream._popen.returncode  # type: ignore[attr-defined]

            build_time_taken = time.time() - build_start_time  # Calculate time taken

            if proc_rc is None:
                # No subprocess – consider this a failure because the build
                # could not even start (e.g. invalid *example* path).
                exit_code = 1
                _print_error("Build could not start", formatted_path)
                # Track failed build
                build_results.append(
                    BuildResult(
                        src_path=src_path,
                        platform=plat_name,
                        success=False,
                        time_taken=build_time_taken,
                        error_message="Build could not start",
                    )
                )
            elif proc_rc != 0:
                # Underlying *platformio run* command failed – propagate.
                logger.error(
                    "[FAILED] %s – platformio exited with %d", formatted_path, proc_rc
                )
                _print_error(f"Build failed (exit code: {proc_rc})", formatted_path)
                exit_code = 1
                # Track failed build
                build_results.append(
                    BuildResult(
                        src_path=src_path,
                        platform=plat_name,
                        success=False,
                        time_taken=build_time_taken,
                        error_message=f"Build failed (exit code: {proc_rc})",
                    )
                )
            else:
                # Build succeeded
                success_emoji = _sym("✅", "[OK]")
                print(
                    f"{_GREEN}{success_emoji} Build successful:{_RESET} {_YELLOW}{formatted_path}{_RESET}"
                )

                # Track successful build
                build_results.append(
                    BuildResult(
                        src_path=src_path,
                        platform=plat_name,
                        success=True,
                        time_taken=build_time_taken,
                    )
                )

                # cleanup old cache entries if needed.
                if use_cache_manager and cache_manager is not None:
                    try:
                        # Clean up old cache entries to keep the cache manageable
                        cache_manager.cleanup_old_entries(
                            max_entries=10, max_age_days=30
                        )
                    except Exception as exc:  # pragma: no cover – best-effort
                        logger.warning("Failed to cleanup cache entries: %s", exc)

                # Generate info reports if --info flag was provided or --report was specified
                if args.info or args.report is not None:
                    report_dir = None
                    if args.report is not None:
                        if args.report == "":
                            # --report flag used without value, use work directory (cache root)
                            report_dir = compiler.work_dir()
                        else:
                            report_dir = Path(args.report).expanduser().resolve()
                        # Ensure the report directory exists
                        report_dir.mkdir(parents=True, exist_ok=True)
                    _print_info_reports(
                        compiler, src_path, plat_name, report_dir, args.clean
                    )

    # Print build summary footer for all builds (single or multiple)
    if len(build_results) > 0:
        print()  # Empty line before footer
        print(f"{_BOLD}{_CYAN}{'=' * 60}{_RESET}")

        # Count successes and failures
        successful_builds = [r for r in build_results if r.success]
        failed_builds = [r for r in build_results if not r.success]

        # Calculate total time
        total_time = sum(r.time_taken for r in build_results)

        # Print summary message
        if len(failed_builds) == 0:
            print(f"{_BOLD}{_GREEN}All Builds Succeed!{_RESET}")
        else:
            if len(build_results) == 1:
                # Single build case
                print(f"{_BOLD}{_RED}Build Failed!{_RESET}")
            else:
                # Multiple builds case
                print(
                    f"{_BOLD}{_YELLOW}{len(successful_builds)} Builds Passed, "
                    f"{len(failed_builds)} Builds failed to compile{_RESET}"
                )

        # Print total time
        print(f"{_BOLD}{_CYAN}Total time: {_YELLOW}{total_time:.2f}s{_RESET}")

        print()
        print(f"{_BOLD}{_CYAN}Build Info:{_RESET}")

        # Print individual build results
        for result in build_results:
            # Format path
            formatted_path = _format_path_for_logging(result.src_path)

            # Choose icon and color based on success
            if result.success:
                status_icon = f"{_GREEN}{_sym('✓', '[✓]')}{_RESET}"
            else:
                status_icon = f"{_RED}{_sym('✗', '[x]')}{_RESET}"

            # Format time taken
            time_str = f"{result.time_taken:.2f}s"

            # Build the output line
            if len(result.platform) > 1 and result.platform != "native":
                # Include platform name if not native
                build_line = f"  {status_icon} - {_YELLOW}{time_str:<8}{_RESET} {formatted_path} ({result.platform})"
            else:
                build_line = (
                    f"  {status_icon} - {_YELLOW}{time_str:<8}{_RESET} {formatted_path}"
                )

            print(build_line)

        print(f"{_BOLD}{_CYAN}{'=' * 60}{_RESET}")
        print()  # Empty line after footer

    return exit_code


def main(argv: list[str] | None = None) -> int:
    """Run the *pio_compiler* command-line interface and return its exit code.

    When called *without* arguments (as done in the unit tests) the function
    prints a short informational message and returns *0* to keep compatibility
    with the existing test-suite.
    """

    if argv is None:
        argv = sys.argv[1:]

    if not argv:
        print("poi-compiler – run with --help to see available options.")
        return 0

    try:
        return _run_cli(argv)
    except KeyboardInterrupt:  # pragma: no cover – user interruption
        print("Interrupted by user – aborting.")
        return 1


def _parse_sketch_dependencies(sketch_path: Path) -> list[str]:
    """Parse dependencies from sketch header comments.

    Looks for embedded dependencies in the first 5 lines of a sketch file.
    Supports both triple-slash and double-slash formats:

    Triple-slash format:
    /// SKETCH-INFO
    /// dependencies = ["FastLED", "ArduinoJson"]
    /// SKETCH-INFO

    Double-slash format:
    // SKETCH-INFO
    // dependencies = ["FastLED", "ArduinoJson"]
    // SKETCH-INFO

    Args:
        sketch_path: Path to the sketch file (.ino) or directory containing sketch

    Returns:
        List of dependency names found in the sketch header
    """
    dependencies = []

    try:
        # If it's a directory, look for .ino files
        if sketch_path.is_dir():
            ino_files = list(sketch_path.glob("*.ino"))
            if not ino_files:
                return dependencies
            sketch_file = ino_files[0]  # Use the first .ino file found
        else:
            sketch_file = sketch_path

        # Only process .ino files
        if not sketch_file.suffix.lower() == ".ino":
            return dependencies

        # Read the first 5 lines of the sketch file
        with open(sketch_file, "r", encoding="utf-8") as f:
            lines = []
            for _ in range(5):
                try:
                    line = next(f).strip()
                    lines.append(line)
                except StopIteration:
                    break

        # Look for the dependency block
        in_dependency_block = False
        for line in lines:
            # Support both /// and // formats
            if line == "/// SKETCH-INFO" or line == "// SKETCH-INFO":
                if in_dependency_block:
                    # Second SKETCH-INFO marker - end of block
                    break
                else:
                    # First SKETCH-INFO marker - start of block
                    in_dependency_block = True
                    continue
            elif in_dependency_block and (
                line.startswith("/// dependencies = ")
                or line.startswith("// dependencies = ")
            ):
                # Parse the dependencies list
                if line.startswith("/// dependencies = "):
                    deps_str = line[len("/// dependencies = ") :].strip()
                else:  # line.startswith("// dependencies = ")
                    deps_str = line[len("// dependencies = ") :].strip()

                if deps_str.startswith("[") and deps_str.endswith("]"):
                    # Simple parsing of the list format
                    deps_str = deps_str[1:-1]  # Remove brackets
                    for dep in deps_str.split(","):
                        dep = dep.strip().strip('"').strip("'")
                        if dep:
                            dependencies.append(dep)
                break

    except Exception as e:
        logger.debug(f"Error parsing sketch dependencies from {sketch_path}: {e}")

    return dependencies


if __name__ == "__main__":
    sys.exit(main())
