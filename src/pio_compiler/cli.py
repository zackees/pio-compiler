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
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from importlib.metadata import PackageNotFoundError
from importlib.metadata import version as _pkg_version
from pathlib import Path
from typing import List

from pio_compiler import PioCompiler, Platform
from pio_compiler.boards import ALL as ALL_BOARDS
from pio_compiler.cache_manager import CacheEntry
from pio_compiler.logging_utils import configure_logging

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
    fast_mode: bool,
    fast_dir: Path | None,
    fast_hit: bool | None,
    cache_dir: str | None,
    clean: bool,
    pio_cache_dir: str | None = None,
) -> None:  # noqa: D401
    """Print a colourful npm-style banner summarising build configuration."""

    header = f"{_BOLD}{_CYAN}{LIGHTNING} pio-compiler v{_tool_version()}{_RESET}"
    print(header)

    if fast_mode and fast_dir is not None:
        status_colour = _GREEN if fast_hit else _YELLOW
        status = "hit" if fast_hit else "miss"
        formatted_fast_dir = _format_path_for_logging(fast_dir)
        print(
            f"  {status_colour}{ROCKET} Fast cache [{status}]: {formatted_fast_dir}{_RESET}"
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
) -> None:
    """Print npm-style info about generated optimization reports and build info."""

    # Determine project directory
    if (src_path / "platformio.ini").exists():
        project_dir = src_path
    else:
        if compiler.fast_mode:
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


# ----------------------------------------------------------------------
# *CLIArguments* – typed container for parsed command-line options.
# ----------------------------------------------------------------------


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
    # Force a full clean build (inverse of fast mode)
    clean: bool = False
    # Legacy fast flag (hidden, for backwards compatibility)
    fast_flag: bool = False
    # Enable info mode (generate optimization reports and build info)
    info: bool = False
    # Optional path where to save optimization reports and build info
    report: str | None = None
    # List of turbo dependencies (libraries to download and symlink)
    turbo_libs: list[str] = field(default_factory=list)


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
        fast_flag=getattr(ns, "fast_flag", False),
        info=getattr(ns, "info", False),
        report=getattr(ns, "report", None),
        turbo_libs=getattr(ns, "turbo_libs", []),
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

    # (1) Force a *full* clean build – inverse of the default *fast* mode.
    mutex.add_argument(
        "--clean",
        dest="clean",
        action="store_true",
        help=(
            "Force a full clean build by running 'platformio run --target clean' "
            "before compilation. This removes all build artifacts and starts fresh."
        ),
    )

    # (2) Keep the legacy --fast flag for backwards-compatibility but hide it
    mutex.add_argument(
        "--fast",
        dest="fast_flag",
        action="store_true",
        help=argparse.SUPPRESS,
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

    return parser


def _run_cli(arguments: List[str]) -> int:
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
    # Derive the *fast* boolean according to the selected build mode.  The
    # precedence order is:
    #   1. --clean     → fast = False
    #   2. --cache     → fast = False (cannot combine with fast mode)
    #   3. --fast flag → fast = True  (legacy alias, already default)
    #   4. default     → fast = True
    # ------------------------------------------------------------------

    fast_mode: bool = True  # default – incremental fast builds

    if args.clean:
        fast_mode = False
    elif args.fast_flag:
        fast_mode = True

    if not args.src:
        logger.error(
            "No sketch paths supplied. Provide at least one path or use --help for usage."
        )
        return 1

    # Safety: *fast* mode only makes sense for a single platform & single sketch.
    if fast_mode and (len(args.platforms) != 1 or len(args.src) != 1):
        fast_mode = False  # silently fall back to rebuild semantics

    # ------------------------------------------------------------------
    # Inject *build_cache_dir* into the generated *platformio.ini* when the
    # user supplied a ``--cache`` directory.  The helper keeps the modification
    # logic contained so that the rest of the compiler remains unchanged.
    # ------------------------------------------------------------------

    if args.cache:

        def _with_build_cache_dir(base_ini: str | None, cache_dir: str) -> str:
            """Return *base_ini* with a 'build_cache_dir' setting injected.

            The function ensures that a ``[platformio]`` section exists and
            adds or updates the ``build_cache_dir`` option accordingly.
            """

            if base_ini is None:
                base_ini = ""

            lines = base_ini.splitlines()

            # Locate the [platformio] section.
            try:
                section_idx = next(
                    idx
                    for idx, line in enumerate(lines)
                    if line.strip().lower() == "[platformio]"
                )
            except StopIteration:
                # Section missing – prepend a new one.
                header = f"[platformio]\nbuild_cache_dir = {cache_dir}\n"
                # Keep existing INI content after an empty line for readability.
                if lines:
                    header += "\n"
                return header + "\n".join(lines)

            # Section exists – determine where it ends (next section header or EOF).
            next_section_idx = next(
                (
                    idx
                    for idx, line in enumerate(
                        lines[section_idx + 1 :], start=section_idx + 1
                    )
                    if line.lstrip().startswith("[")
                ),
                len(lines),
            )

            # Scan for an existing build_cache_dir setting.
            for idx in range(section_idx + 1, next_section_idx):
                if lines[idx].split("=")[0].strip() == "build_cache_dir":
                    lines[idx] = f"build_cache_dir = {cache_dir}"
                    break
            else:
                # Not present – insert right after the section header.
                lines.insert(section_idx + 1, f"build_cache_dir = {cache_dir}")

            return "\n".join(lines) + ("\n" if base_ini.endswith("\n") else "")

        from pathlib import Path as _Path

        abs_cache_dir = str(_Path(args.cache).expanduser().resolve())
        # platform.platformio_ini = _with_build_cache_dir(
        #     platform.platformio_ini, abs_cache_dir
        # )

    # ------------------------------------------------------------------
    # *Fast* mode – use cache manager for human-readable cache directories
    # ------------------------------------------------------------------

    # Initialize cache manager once
    cache_manager = None
    if fast_mode:
        from .cache_manager import CacheManager

        cache_manager = CacheManager()

        # Migrate any old hash-based cache directories to new format
        cache_manager.migrate_old_cache_entries()

    compilers: list[tuple[str, PioCompiler]] = []

    for plat_name in args.platforms:
        # For native, use the string name to get the special native configuration
        # For other platforms, try to get board configuration first
        if plat_name == "native":
            plat_obj = Platform(plat_name, turbo_dependencies=args.turbo_libs)
        else:
            from pio_compiler.boards import get_board

            board = get_board(plat_name)
            plat_obj = Platform(board, turbo_dependencies=args.turbo_libs)

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

        # ---------------- fast-cache per platform ----------------
        fast_dir: Path | None = None
        fast_hit: bool | None = None
        cache_entry: CacheEntry | None = None

        if fast_mode and cache_manager:
            src_path = Path(args.src[0]).expanduser().resolve()
            cache_entry = cache_manager.get_cache_entry(
                src_path, plat_name, plat_obj.platformio_ini or "", args.turbo_libs
            )

            fast_dir = cache_entry.cache_dir
            fast_hit = cache_entry.exists

            if fast_hit:
                print(f"[FAST] Using cache directory: {fast_dir}")
            else:
                print("[FAST] Cache miss – creating cache directory…")
                fast_dir.mkdir(parents=True, exist_ok=True)
                print(f"[FAST] Using cache directory: {fast_dir}")

        compiler = PioCompiler(
            plat_obj,
            work_dir=fast_dir if fast_mode else None,
            fast_mode=fast_mode,
            disable_auto_clean=False,
            force_rebuild=args.clean,
            info_mode=args.info,
            cache_entry=cache_entry if fast_mode and cache_manager else None,
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
        if fast_mode:
            _print_startup_banner(
                fast_mode=True,
                fast_dir=fast_dir,
                fast_hit=fast_hit,
                cache_dir=args.cache,
                clean=False,
                pio_cache_dir=pio_cache_dir,
            )
        else:
            _print_startup_banner(
                fast_mode=False,
                fast_dir=None,
                fast_hit=None,
                cache_dir=args.cache,
                clean=True,
                pio_cache_dir=pio_cache_dir,
            )

    # Compile for each platform
    src_paths = [Path(p) for p in args.src]

    exit_code = 0

    for plat_name, compiler in compilers:
        logger.info("[PLATFORM] %s", plat_name)

        streams = compiler.multi_compile(src_paths)

        for src_path, future in zip(src_paths, streams):
            # Resolve the compilation *Future* – this yields the actual
            # :class:`CompilerStream` instance.
            try:
                stream = future.result()
            except Exception as exc:  # pragma: no cover – treat failures gracefully
                formatted_path = _format_path_for_logging(src_path)
                logger.error("Compilation failed for %s: %s", formatted_path, exc)
                print(f"[ERROR] {formatted_path} – {exc}")
                exit_code = 1
                continue

            formatted_path = _format_path_for_logging(src_path)
            logger.info("[BUILD] %s …", formatted_path)
            print(f"[BUILD] {formatted_path} …")

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
            print(f"[DONE] {formatted_path} – captured {total_bytes} bytes of output\n")

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

            if proc_rc is None:
                # No subprocess – consider this a failure because the build
                # could not even start (e.g. invalid *example* path).
                exit_code = 1
            elif proc_rc != 0:
                # Underlying *platformio run* command failed – propagate.
                logger.error(
                    "[FAILED] %s – platformio exited with %d", formatted_path, proc_rc
                )
                print(f"[FAILED] {formatted_path} – platformio exited with {proc_rc}\n")
                exit_code = 1
            else:
                # Build succeeded – cleanup old cache entries if needed.
                if fast_mode and cache_manager is not None:
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
                    _print_info_reports(compiler, src_path, plat_name, report_dir)

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


if __name__ == "__main__":
    sys.exit(main())
