"""pio_compiler.logging_utils – shared logging helpers.

This tiny utility centralises logging configuration so that *all* modules
within the *pio_compiler* package use the *same* formatting and honour the
same environment variables.

Usage
-----
Call :pyfunc:`configure_logging` *once* – ideally at program start – to set up
Python's root logger with sensible defaults.  The function is idempotent; it
can be invoked multiple times safely.

By default the log-level is controlled via the *PIO_COMPILER_LOG_LEVEL*
environment variable (``DEBUG``, ``INFO``, …).  When the variable is not set
the *INFO* level is used.
"""

from __future__ import annotations

import logging
import os
from typing import Any

# Public helper -----------------------------------------------------------------


def configure_logging(
    level: str | int | None = None, *, overwrite: bool = False, **kwargs: Any
) -> None:  # noqa: D401,E501
    """Initialise the *root* logger with a standard configuration.

    Parameters
    ----------
    level
        Desired *log-level*.  Can be either an *int* (e.g. ``logging.DEBUG``)
        or a *str* such as ``"info"`` or ``"WARNING"``.  When *None* the
        function falls back to the *PIO_COMPILER_LOG_LEVEL* environment
        variable or *INFO* if the variable is unset.
    overwrite
        When *True* the *force* parameter of :pyfunc:`logging.basicConfig` is
        used to **replace** a previously installed root handler.  Leaving it
        at *False* means the first invocation wins and subsequent calls become
        no‐ops – mirroring :pyfunc:`logging.basicConfig`'s default behaviour.
    **kwargs
        Additional keyword arguments are forwarded verbatim to
        :pyfunc:`logging.basicConfig` to allow advanced customisation.
    """

    # ------------------------------------------------------------------
    # Determine desired *log-level* (environment variable takes priority).
    # ------------------------------------------------------------------
    if level is None:
        env_level = os.getenv("PIO_COMPILER_LOG_LEVEL", "INFO")
        # Accept both integer values and named levels.
        if env_level.isdigit():
            level = int(env_level)
        else:
            level = env_level.upper()

    # ------------------------------------------------------------------
    # Set a reasonable default format unless the caller provided one.
    # ------------------------------------------------------------------
    fmt = kwargs.pop("format", "%(asctime)s [%(levelname)-8s] %(name)s: %(message)s")

    # *force* is available starting with Python 3.8 – safe per "requires-python".
    logging.basicConfig(level=level, format=fmt, force=overwrite, **kwargs)
