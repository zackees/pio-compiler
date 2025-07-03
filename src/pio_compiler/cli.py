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
import sys
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
    return parser


def _run_cli(arguments: List[str]) -> int:
    """Internal helper that contains the real CLI implementation."""

    parser = _build_argument_parser()
    ns = parser.parse_args(arguments)

    # ------------------------------------------------------------------
    # Create compiler instance for the requested platform.
    # ------------------------------------------------------------------
    platform = Platform(ns.platform)
    logger.debug("Initialising compiler for platform %s", platform.name)
    compiler = PioCompiler(platform)

    init_result = compiler.initialize()
    if not init_result.ok:
        logger.error("Failed to initialise compiler: %s", init_result.exception)
        return 1

    # Compile requested examples
    logger.debug("Starting compilation for %d example(s)", len(ns.src))
    streams = compiler.multi_compile(ns.src)

    exit_code = 0
    for src_path, future in zip(ns.src, streams):
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
