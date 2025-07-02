import subprocess
import threading
from queue import Empty, Queue


# --------------------------------------------------------------
# Streaming support
# --------------------------------------------------------------
class CompilerStream:
    """Stream wrapper for an ongoing *platformio* compilation.

    The stream exposes *readline* to fetch the next output line and
    :py:meth:`is_done` so that callers can poll for completion.

    Notes
    -----
    *  ``is_done`` returns *True* **while** there is still data pending
       or the underlying process is running.  Only when *all* output has
       been consumed **and** the process exited will the method return
       *False*.
    *  All **stderr** is redirected to **stdout** – users only deal with
       a *single* combined stream as requested.
    """

    def __init__(
        self,
        popen: subprocess.Popen[bytes] | None = None,
        preloaded_output: str | None = None,
    ) -> None:
        self._popen = popen  # becomes ``None`` in *simulation* mode
        self._queue: "Queue[str]" = Queue()
        # "_process_done" is *True* once the subprocess exited or when no
        # subprocess was used.  The queue may still contain data.
        self._process_done: bool = popen is None

        if preloaded_output is not None:
            for line in preloaded_output.splitlines(keepends=True):
                self._queue.put(line)

        # Spawn a daemon thread that reads the subprocess' *stdout* and
        # buffers individual *lines* in the queue for later consumption.
        if popen is not None:
            threading.Thread(target=self._reader_thread, daemon=True).start()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def readline(self, timeout: float | None = None) -> str | None:
        """Return the *next* available output line or *None*.

        When *timeout* is given the call will block for at most that many
        seconds waiting for new data.  A *None* result indicates that no
        data was available within the timeout **or** that the stream has
        finished and no more data will become available.
        """

        try:
            line = self._queue.get(timeout=timeout)
            return line
        except Empty:
            return None

    def is_done(self) -> bool:  # noqa: D401 – requested naming
        """Return *True* **while** the compilation is still active.

        The method mirrors the slightly counter‐intuitive behaviour
        expressed in the user requirements: it returns *False* only when
        the subprocess finished **and** all output has been consumed.
        """

        # There is still data to read -> *not* done yet.
        if not self._queue.empty():
            return True
        # Queue is empty – rely on subprocess status.
        return not self._process_done

    # ------------------------------------------------------------------
    # Iterator helpers – enable ``for line in stream: …`` style usage.
    # ------------------------------------------------------------------
    def __iter__(self) -> "CompilerStream":  # pragma: no cover – syntactic helper
        return self

    def __next__(self) -> str:  # pragma: no cover – syntactic helper
        line = self.readline()
        if line is None:
            raise StopIteration
        return line

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _reader_thread(self) -> None:
        """Background thread that enqueues stdout lines until EOF."""

        assert self._popen is not None, "_reader_thread called without process"

        try:
            # Iterate over the *text mode* stdout stream line-by‐line.  The
            # iteration stops on EOF automatically.
            for raw in self._popen.stdout:  # type: ignore[union-attr]
                # *raw* is ``bytes`` – decode explicitly using UTF-8 and
                # *replace* invalid sequences so that callers never have
                # to deal with *decode* errors.
                decoded = raw.decode("utf-8", errors="replace")
                self._queue.put(decoded)
        finally:
            # Wait for the process to terminate, then mark things as done
            # and close the stdout handle to free resources.
            try:
                self._popen.wait(timeout=1)
            except subprocess.TimeoutExpired:
                # Should not happen – the process *should* be done once
                # stdout reached EOF.  As a last resort terminate it.
                self._popen.kill()
                self._popen.wait()
            finally:
                if self._popen.stdout is not None:
                    self._popen.stdout.close()
                self._process_done = True
