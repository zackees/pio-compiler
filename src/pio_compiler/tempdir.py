"""pio_compiler.tempdir – project-local cache directory management.

The module provides a *single* cache root directory that lives **inside**
the current working directory.  All cache files and directories created by
:pyfunc:`mkdtemp` (and potential future helpers) live below this directory.

The rationale is twofold:

1. Keep all build artefacts confined to one easily discoverable location which
   can be inspected manually during debugging.
2. Provide persistent caching across builds to improve performance while
   avoiding system-wide cache directories that may be cleared unexpectedly.

The cache root is created *lazily* on first access and persists across
interpreter sessions. Users can trigger clean-up manually by calling
:pyfunc:`cleanup` explicitly.

A small public API mirrors the most commonly used functionality from
:pyfunc:`tempfile.mkdtemp` and friends.  More helpers can be added as
required.
"""

from __future__ import annotations

import shutil
import tempfile
import uuid
from pathlib import Path
from typing import Optional

__all__ = [
    "get_temp_root",
    "mkdtemp",
    "TemporaryDirectory",
    "cleanup",
    "cleanup_all",
]

# ---------------------------------------------------------------------------
# Internal state – the cached path to the lazily created cache root.
# ---------------------------------------------------------------------------
_CACHE_ROOT: Optional[Path] = None


def get_temp_root(*, disable_auto_clean: bool = False) -> Path:
    """Return the *project-local* cache directory, creating it if needed.

    Parameters
    ----------
    disable_auto_clean:
        Ignored for compatibility. The cache directory is now persistent
        and never automatically cleaned.
    """

    global _CACHE_ROOT
    if _CACHE_ROOT is None:
        base_root = Path.cwd() / ".pio_cache"
        base_root.mkdir(parents=True, exist_ok=True)

        # Create a unique *session* directory inside the base root so that
        # concurrent test workers or processes never step on each other's toes.
        # Use a simple unique identifier instead of tempfile for better control.
        session_id = uuid.uuid4().hex[:12]
        _CACHE_ROOT = base_root / f"session_{session_id}"
        _CACHE_ROOT.mkdir(parents=True, exist_ok=True)

    return _CACHE_ROOT


def mkdtemp(
    *, prefix: str = "", suffix: str = "", disable_auto_clean: bool = False
) -> Path:
    """Create a new *unique* directory *inside* the cache root and return its :class:`~pathlib.Path`.

    Parameters
    ----------
    prefix, suffix:
        Naming hints for the created directory.
    disable_auto_clean:
        Ignored for compatibility. Cache directories are now persistent.
    """

    return Path(
        tempfile.mkdtemp(
            prefix=prefix,
            suffix=suffix,
            dir=get_temp_root(disable_auto_clean=disable_auto_clean),
        )
    )


# ---------------------------------------------------------------------------
# Clean-up helpers – manual cleanup only.
# ---------------------------------------------------------------------------


def cleanup() -> None:
    """Remove the cache root directory and all its contents (best-effort).

    This is now a manual operation and must be called explicitly.
    The cache directory is no longer automatically cleaned up.
    """

    global _CACHE_ROOT

    if _CACHE_ROOT is None:
        return

    try:
        if _CACHE_ROOT.exists():
            is_empty = not any(_CACHE_ROOT.iterdir())
            if not is_empty:
                print(f"\nInfo: Cleaning cache directory {_CACHE_ROOT}")
            shutil.rmtree(_CACHE_ROOT)
    except FileNotFoundError:
        # The directory may already be gone if cleanup was called manually.
        pass
    except PermissionError as e:
        print(f"\nWarning: Could not clean cache directory {_CACHE_ROOT}: {e}")
        print("This may be due to locked files (e.g., git repositories).")
        print("You can manually remove the directory when files are no longer in use.")
    finally:
        _CACHE_ROOT = None


def cleanup_all() -> None:
    """Remove the entire cache root directory and all session directories.

    This removes the entire .pio_cache directory, not just the current session.
    Use with caution as this will affect all concurrent processes.
    """

    global _CACHE_ROOT

    cache_base = Path.cwd() / ".pio_cache"

    try:
        if cache_base.exists():
            print(f"\nInfo: Cleaning entire cache directory {cache_base}")
            shutil.rmtree(cache_base)
    except FileNotFoundError:
        pass
    except PermissionError as e:
        print(f"\nWarning: Could not clean cache directory {cache_base}: {e}")
        print("This may be due to locked files (e.g., git repositories).")
        print("You can manually remove the directory when files are no longer in use.")
    finally:
        _CACHE_ROOT = None


# ---------------------------------------------------------------------------
# Context-manager helper mirroring *tempfile.TemporaryDirectory*.
# ---------------------------------------------------------------------------


class TemporaryDirectory:  # noqa: D101 – docstring below provides details.
    """Context manager creating a cache directory *inside* the project root.

    The public API matches :pyclass:`tempfile.TemporaryDirectory` so that
    existing code can switch to :pyobj:`pio_compiler.tempdir.TemporaryDirectory`
    by adjusting imports only.  Instead of using the standard library implementation,
    we create directories directly using mkdtemp to have full control over the
    cleanup behavior.

    Note: Unlike the standard library version, this creates persistent
    cache directories that are not automatically cleaned up.
    """

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: Path | None = None,
        disable_auto_clean: bool = False,
    ):
        # Create the directory directly using our mkdtemp instead of stdlib
        if dir is not None:
            # If a specific directory is provided, use tempfile.mkdtemp with that dir
            self.name = Path(
                tempfile.mkdtemp(suffix=suffix or "", prefix=prefix or "", dir=dir)
            )
        else:
            # Use our cache-aware mkdtemp
            self.name = mkdtemp(
                suffix=suffix or "",
                prefix=prefix or "",
                disable_auto_clean=disable_auto_clean,
            )

        # Track whether we should clean up on exit
        self._should_cleanup = False

    # ------------------------------------------------------------------
    # Context manager methods.
    # ------------------------------------------------------------------
    def __enter__(self) -> Path:  # noqa: D401 – context manager return type
        # Return the Path directly
        return self.name

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 – match stdlib typing
        # Only cleanup if explicitly enabled
        if self._should_cleanup:
            self.cleanup()
        return None

    # Provide explicit *cleanup* method to mirror stdlib behaviour.
    def cleanup(self) -> None:  # pragma: no cover – covered via context mgr
        """Manually clean up the cache directory.

        This must be called explicitly if you want to remove the directory.
        """
        try:
            if self.name.exists():
                shutil.rmtree(self.name)
        except (FileNotFoundError, PermissionError):
            # Directory already gone or locked - ignore
            pass

    def enable_cleanup(self) -> None:
        """Enable cleanup on context exit.

        Call this if you want the directory to be cleaned up when the
        context manager exits (restoring stdlib behavior).
        """
        self._should_cleanup = True
