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
import sys
from typing import List

from pio_compiler import (  # noqa: F401 – imported for type completeness
    CompilerStream,
    PioCompiler,
    Platform,
)


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
    compiler = PioCompiler(platform)

    init_result = compiler.initialize()
    if not init_result.ok:
        print(
            f"[ERROR] Failed to initialise compiler: {init_result.exception or 'unknown error'}"
        )
        return 1

    # Compile requested examples.
    streams = compiler.multi_compile(ns.src)

    exit_code = 0
    for src_path, stream in zip(ns.src, streams):
        print(f"[BUILD] {src_path} …")

        # Consume stream output until completion.
        accumulated: list[str] = []
        while stream.is_done():
            line = stream.readline(timeout=0.1)
            if line is None:
                # No new data yet – continue polling.
                continue
            accumulated.append(line)
            # Echo live so that users see progress immediately.
            print(line, end="")

        # Build finished – summarise.
        total_bytes = sum(len(line_) for line_ in accumulated)
        print(f"[DONE] {src_path} – captured {total_bytes} bytes of output\n")

    return exit_code


def main(argv: list[str] | None = None) -> int:  # noqa: D401 – *main* is fine
    """The public entry-point consumed by :pymod:`setuptools` *console_scripts*.

    When called *without* arguments (as done in the unit tests) the function
    prints a small help message and returns *0* to keep the contract with the
    existing test-suite.
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
