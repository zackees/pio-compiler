"""Low-level infrastructure for managing project-local temporary directories."""

import os
import shutil
import tempfile
import time
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


def get_temp_root() -> Path:
    """Return the root directory for the current session's temporary files.

    Creates a session-specific subdirectory under .pio_cache/ that persists
    throughout the process lifetime. The directory is NOT automatically cleaned up
    to avoid build interruptions.
    """
    global _CACHE_ROOT

    if _CACHE_ROOT is None:
        cache_base = Path.cwd() / ".pio_cache"
        cache_base.mkdir(exist_ok=True)

        # Session-specific subdirectory
        session_id = f"session_{os.getpid()}_{int(time.time())}"
        _CACHE_ROOT = cache_base / session_id
        _CACHE_ROOT.mkdir(exist_ok=True)

    return _CACHE_ROOT


def mkdtemp(*, prefix: str = "", suffix: str = "") -> Path:
    """Create a temporary directory inside the project-local cache.

    Parameters
    ----------
    prefix:
        Prefix for the directory name.
    suffix:
        Suffix for the directory name.
    """
    return Path(
        tempfile.mkdtemp(
            prefix=prefix,
            suffix=suffix,
            dir=get_temp_root(),
        )
    )


async def mkdtemp_async(
    prefix: str = "",
    suffix: str = "",
) -> Path:
    """Asynchronous version of mkdtemp.

    Creates a temporary directory inside the project-local cache.
    This is a thin async wrapper around the synchronous mkdtemp function.

    Parameters
    ----------
    prefix:
        Prefix for the directory name.
    suffix:
        Suffix for the directory name.
    """
    import asyncio

    return await asyncio.to_thread(
        mkdtemp,
        prefix=prefix,
        suffix=suffix,
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


class TemporaryDirectory:
    """Context manager for creating persistent temporary directories.

    Unlike Python's standard tempfile.TemporaryDirectory, this creates
    directories in the project-local cache that persist after the context
    exits by default.
    """

    def __init__(
        self,
        suffix: str | None = None,
        prefix: str | None = None,
        dir: Path | None = None,
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
            )
        self._cleanup_enabled = False

    # ------------------------------------------------------------------
    # Context manager methods.
    # ------------------------------------------------------------------
    def __enter__(self) -> Path:  # noqa: D401 – context manager return type
        # Return the Path directly
        return self.name

    def __exit__(self, exc_type, exc, tb):  # noqa: D401 – match stdlib typing
        # Only cleanup if explicitly enabled
        if self._cleanup_enabled:
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
        self._cleanup_enabled = True
