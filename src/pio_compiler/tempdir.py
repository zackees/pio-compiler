"""pio_compiler.tempdir – project-local temporary directory management.

The module provides a *single* temporary root directory that lives **inside**
the current working directory.  All temporary files and directories created by
:pyfunc:`mkdtemp` (and potential future helpers) live below this directory.

The rationale is twofold:

1. Keep all build artefacts confined to one easily discoverable location which
   can be inspected manually during debugging.
2. Avoid relying on the system‐wide */tmp* which may reside on a small RAM
   disk or be cleared unexpectedly during long‐running test sessions.

The temporary root is created *lazily* on first access and removed
*automatically* at interpreter shutdown (via :pymod:`atexit`).  Users can
trigger clean-up earlier by calling :pyfunc:`cleanup` explicitly.

A small public API mirrors the most commonly used functionality from
:pyfunc:`tempfile.mkdtemp` and friends.  More helpers can be added as
required.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path
from typing import Optional

__all__ = [
    "get_temp_root",
    "mkdtemp",
    "TemporaryDirectory",
    "cleanup",
]

# ---------------------------------------------------------------------------
# Internal state – the cached path to the lazily created temporary root.
# ---------------------------------------------------------------------------
_TEMP_ROOT: Optional[Path] = None


def get_temp_root() -> Path:
    """Return the *project-local* temporary directory, creating it if needed."""

    global _TEMP_ROOT
    if _TEMP_ROOT is None:
        base_root = Path.cwd() / ".pio_compile"
        base_root.mkdir(parents=True, exist_ok=True)
        # Create a unique *session* directory inside the base root so that
        # concurrent test workers or processes never step on each other's toes.
        _TEMP_ROOT = Path(tempfile.mkdtemp(prefix="run_", dir=base_root))

        # Register automatic clean-up at interpreter shutdown.  Registering the
        # handler *once* is sufficient because we only create _TEMP_ROOT once.
        atexit.register(_cleanup_temp_root)

    return _TEMP_ROOT


def mkdtemp(*, prefix: str = "", suffix: str = "") -> Path:
    """Create a new *unique* directory *inside* the temporary root and return its :class:`~pathlib.Path`."""

    return Path(tempfile.mkdtemp(prefix=prefix, suffix=suffix, dir=get_temp_root()))


# ---------------------------------------------------------------------------
# Clean-up helpers – public alias + internal function for atexit.
# ---------------------------------------------------------------------------


def _cleanup_temp_root() -> None:  # pragma: no cover – exercised implicitly
    """Remove the temporary root directory and all its contents (best-effort)."""

    global _TEMP_ROOT

    if _TEMP_ROOT is None:
        return

    try:
        shutil.rmtree(_TEMP_ROOT)
    except FileNotFoundError:
        # The directory may already be gone if *cleanup* was called manually.
        pass
    finally:
        _TEMP_ROOT = None


# Expose the clean-up helper under a nicer public name so that users do not
# accidentally rely on the *internal* underscore variant.
cleanup = _cleanup_temp_root


# ---------------------------------------------------------------------------
# Context-manager helper mirroring *tempfile.TemporaryDirectory*.
# ---------------------------------------------------------------------------


class TemporaryDirectory:  # noqa: D101 – docstring below provides details.
    """Context manager creating a temporary directory *inside* the project root.

    The public API matches :pyclass:`tempfile.TemporaryDirectory` so that
    existing code can switch to :pyobj:`pio_compiler.tempdir.TemporaryDirectory`
    by adjusting imports only.  Internally the class delegates all heavy
    lifting to the standard library implementation but forces the
    ``dir`` argument to :pyfunc:`get_temp_root` so that the resulting path
    lives under the centralised root managed by this module.
    """

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: Path | None = None,
    ):
        # Defer to the stdlib – we merely patch the *dir* argument.
        self._inner = tempfile.TemporaryDirectory(
            suffix=suffix or "",
            prefix=prefix or "",
            dir=(dir or get_temp_root()),
        )

        # Public attribute defined by the stdlib class – expose as Path.
        self.name: Path = Path(self._inner.name)

    # ------------------------------------------------------------------
    # Proxy magic methods to the inner instance.
    # ------------------------------------------------------------------
    def __enter__(self) -> Path:  # noqa: D401 – context manager return type
        # The stdlib returns a *string* – we upgrade to Path for convenience.
        self._inner.__enter__()
        return self.name

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 – match stdlib typing
        return self._inner.__exit__(exc_type, exc, tb)

    # Provide explicit *cleanup* method to mirror stdlib behaviour.
    def cleanup(self) -> None:  # pragma: no cover – covered via context mgr
        self._inner.cleanup()
