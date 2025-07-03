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
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List

from pio_compiler import PioCompiler, Platform
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
# *CLIArguments* – typed container for parsed command-line options.
# ----------------------------------------------------------------------


@dataclass(slots=True)
class CLIArguments:
    """Structured representation of user-supplied CLI arguments."""

    platform: str
    src: list[str]
    # Optional path to a *global* PlatformIO build cache directory.  When
    # provided *pio_compiler* injects the corresponding ``build_cache_dir``
    # option into the generated *platformio.ini* so that subsequent builds
    # share artefacts across independent project directories.
    cache: str | None = None
    # Enable *fast* mode (persistent work directory with incremental builds)
    fast: bool = False


def _build_argument_parser() -> argparse.ArgumentParser:
    """Return an :class:`argparse.ArgumentParser` configured for this CLI."""

    parser = argparse.ArgumentParser(
        prog="poi-compiler",
        description="Compile PlatformIO examples efficiently.",
        add_help=True,
    )
    parser.add_argument(
        "platform",
        help="Target platform name as understood by PlatformIO (e.g. 'native', 'esp32', …).",
    )
    parser.add_argument(
        "--src",
        metavar="PATH",
        dest="src",
        action="append",
        required=True,
        help="Path to a PlatformIO example or project to compile.  Can be supplied multiple times.",
    )
    mutex = parser.add_mutually_exclusive_group()
    mutex.add_argument(
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
    mutex.add_argument(
        "--fast",
        dest="fast",
        action="store_true",
        help=(
            "Enable *fast* compile mode.  The compiler fingerprints the sketch "
            "and platform configuration and re-uses a persistent build "
            "directory between invocations, dramatically reducing latency "
            "for subsequent builds of the same sketch."
        ),
    )
    return parser


def _run_cli(arguments: List[str]) -> int:
    """Internal helper that contains the real CLI implementation."""

    # ------------------------------------------------------------------
    # Support *alternative* call style:  ``pio-compile <example> --native``
    # ------------------------------------------------------------------
    # Historically the CLI expected the *platform* as **positional** first
    # followed by one or more ``--src`` flags.  Users, however, may find the
    # more natural order "*example first – platform second*" easier to
    # remember.  To preserve backwards-compatibility **and** accept the new
    # order we perform a lightweight *pre-processing* step that detects the
    # pattern and rewrites the argument list accordingly before handing it
    # to the regular parser.

    def _rewrite_alt_syntax(argv: List[str]) -> List[str]:
        """Return *argv* rewritten into the canonical format if needed.

        The *alternative* syntax is recognised when **no** "--src" flag is
        present *and* at least one argument starts with "--".  The first
        such "--<platform>" token is interpreted as the *platform* flag.
        All *non* dash-prefixed tokens are treated as *source* paths.  The
        function converts the token sequence into the canonical form

            <platform> --src <path1> --src <path2> …

        Compatible with the existing argument parser.
        """

        if "--src" in argv:
            # Already in canonical form – nothing to do.
            return argv

        # ------------------------------------------------------------------
        # The alternative syntax supports additional **global** flags such as
        # ``--cache`` which themselves accept a *value* argument.  We need to
        # preserve these flag/value pairs verbatim while still rewriting the
        # positional tokens into the canonical form.
        # ------------------------------------------------------------------

        platform_name: str | None = None
        src_paths: list[str] = []
        extra_flags: list[str] = []

        i = 0
        while i < len(argv):
            token = argv[i]

            # Handle recognised *flag* tokens that take exactly **one** value
            # argument which needs to be kept together with the flag.
            if token == "--cache":
                # Ensure that a *value* follows the flag to avoid *IndexError*
                # in malformed invocations.
                if i + 1 < len(argv):
                    extra_flags.extend([token, argv[i + 1]])
                    i += 2
                    continue
                # Malformed – no value after --cache – fall through and let
                # argparse report the error later.

            # Handle *boolean* flags that do not take a value.
            if token == "--fast":
                extra_flags.append(token)
                i += 1
                continue

            # Detect the *platform* token (first dash-prefixed argument that is
            # **not** a recognised flag).
            if (
                token.startswith("--")
                and token not in {"--src", "--cache", "--fast"}
                and platform_name is None
            ):
                platform_name = token.lstrip("-")
                i += 1
                continue

            # Everything else is considered a *source* path.
            src_paths.append(token)
            i += 1

        if platform_name is None:
            # No recognisable alternative syntax – return unchanged.
            return argv

        # Build canonical argv:  <platform> --src <path1> --src <path2> … <extra_flags>
        new_argv: list[str] = [platform_name]
        for path in src_paths:
            new_argv.extend(["--src", path])

        # Append the preserved *flag* tokens at the end so that argparse sees
        # them in their original form.
        new_argv.extend(extra_flags)

        return new_argv

    arguments = _rewrite_alt_syntax(arguments)

    parser = _build_argument_parser()
    ns = parser.parse_args(arguments)

    # Convert argparse.Namespace → dataclass instance for type-safety.
    cli_args = CLIArguments(
        platform=ns.platform, src=ns.src, cache=ns.cache, fast=ns.fast
    )

    # ------------------------------------------------------------------
    # Create compiler instance for the requested platform.
    # ------------------------------------------------------------------
    platform = Platform(cli_args.platform)

    # ------------------------------------------------------------------
    # Inject *build_cache_dir* into the generated *platformio.ini* when the
    # user supplied a ``--cache`` directory.  The helper keeps the modification
    # logic contained so that the rest of the compiler remains unchanged.
    # ------------------------------------------------------------------

    if cli_args.cache:

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

        abs_cache_dir = str(_Path(cli_args.cache).expanduser().resolve())
        platform.platformio_ini = _with_build_cache_dir(
            platform.platformio_ini, abs_cache_dir
        )

    # ------------------------------------------------------------------
    # *Fast* mode – compute fingerprinted work directory and configure
    # incremental build behaviour.
    # ------------------------------------------------------------------

    # *Optional* values filled only when --fast is active.  Pre-declare so that
    # static type checkers do not report "possibly unbound" accesses later.
    fast_root: Path | None = None
    fast_dir: Path | None = None
    fingerprint: str | None = None

    if cli_args.fast:
        if len(cli_args.src) != 1:
            logger.error("--fast mode supports exactly one --src path at the moment.")
            return 1

        import hashlib

        src_path = Path(cli_args.src[0]).expanduser().resolve()
        hash_input = f"{src_path}:{platform.name}".encode()
        fingerprint = hashlib.sha256(hash_input).hexdigest()[:12]

        fast_root = Path.cwd() / ".tpo_fast_cache"
        fast_root.mkdir(exist_ok=True)
        fast_dir = fast_root / fingerprint

        if fast_dir.exists():
            print(f"[FAST] Cache hit – using cache directory: {fast_dir}")
        else:
            print(f"[FAST] Cache miss – creating cache directory: {fast_dir}")
            fast_dir.mkdir(parents=True, exist_ok=True)

        print(f"[FAST] Using cache directory: {fast_dir}")

    compiler = PioCompiler(
        platform,
        work_dir=fast_dir,
        fast_mode=cli_args.fast,
    )

    init_result = compiler.initialize()
    if not init_result.ok:
        logger.error("Failed to initialise compiler: %s", init_result.exception)
        return 1

    # Compile requested examples
    src_paths = [Path(p) for p in cli_args.src]

    logger.debug("Starting compilation for %d example(s)", len(src_paths))
    streams = compiler.multi_compile(src_paths)

    exit_code = 0
    for src_path, future in zip(src_paths, streams):
        # Resolve the compilation *Future* – this yields the actual
        # :class:`CompilerStream` instance.
        try:
            stream = future.result()
        except Exception as exc:  # pragma: no cover – treat failures gracefully
            logger.error("Compilation failed for %s: %s", src_path, exc)
            print(f"[ERROR] {src_path} – {exc}")
            exit_code = 1
            continue

        logger.info("[BUILD] %s …", src_path)
        print(f"[BUILD] {src_path} …")

        # Consume stream output until completion.
        accumulated: list[str] = []
        while not stream.is_done():
            line = stream.readline(timeout=0.1)
            if line is None:
                # No new data yet – continue polling.
                continue
            accumulated.append(line)
            # Echo live so that users see progress immediately.
            print(line, end="")

        # Build finished – summarise.
        total_bytes = sum(len(line_) for line_ in accumulated)
        logger.info("[DONE] %s – captured %d bytes of output", src_path, total_bytes)
        print(f"[DONE] {src_path} – captured {total_bytes} bytes of output\n")

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
            logger.error("[FAILED] %s – platformio exited with %d", src_path, proc_rc)
            print(f"[FAILED] {src_path} – platformio exited with {proc_rc}\n")
            exit_code = 1
        else:
            # Build succeeded – when running in *fast* mode we need to update
            # the on-disk LRU index **after** the first successful build** so
            # that failed/partial builds never pollute the cache.
            if (
                cli_args.fast
                and fast_root is not None
                and fast_dir is not None
                and fingerprint is not None
            ):
                try:
                    from disklru import DiskLRUCache

                    index_path = fast_root / "build_index.db"
                    lru = DiskLRUCache(str(index_path), max_entries=10)

                    # Put/refresh entry for the current fingerprint.  The
                    # returned value is not used – DiskLRUCache handles
                    # eviction transparently.
                    lru.put(fingerprint, str(fast_dir))

                    # Clean up directories that are **no longer** referenced
                    # by the index (e.g. after eviction).
                    valid_keys = set(lru.keys())  # type: ignore[attr-defined]
                    for dir_entry in fast_root.iterdir():
                        if not dir_entry.is_dir():
                            continue
                        if dir_entry.name not in valid_keys:
                            shutil.rmtree(dir_entry, ignore_errors=True)
                except Exception as exc:  # pragma: no cover – best-effort
                    logger.warning("Failed to update fast-cache index: %s", exc)

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
