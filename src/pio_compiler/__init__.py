from concurrent.futures import Future
from pathlib import Path

from .compiler_stream import CompilerStream
from .logging_utils import configure_logging
from .types import Platform, Result


class PioCompiler:
    def __init__(
        self,
        platform: Platform,
        *,
        work_dir: Path | None = None,
        fast_mode: bool = False,
        disable_auto_clean: bool = False,
    ) -> None:
        """Create a new *PioCompiler* instance.

        Parameters
        ----------
        platform:
            Target *PlatformIO* platform.
        work_dir:
            Optional path to a *persistent* work directory.  When *None* the
            compiler allocates a fresh temporary directory via
            :pyfunc:`pio_compiler.tempdir.mkdtemp`.  Supplying an explicit path
            allows callers – notably the *--fast* CLI mode – to re-use a
            previous build directory so that subsequent invocations can
            benefit from incremental compilation.
        fast_mode:
            When *True* the underlying implementation enables additional
            optimisations such as ``--disable-auto-clean`` and
            ``--disable-ldf`` on cache *hits* to minimise build latency.
        disable_auto_clean:
            When *True*, disables automatic cleanup of temporary directories
            at interpreter shutdown. Useful for debugging build artifacts.
        """

        from .compiler import PioCompilerImpl

        self.__impl: PioCompilerImpl = PioCompilerImpl(
            platform,
            work_dir=work_dir,
            fast_mode=fast_mode,
            disable_auto_clean=disable_auto_clean,
        )

    def initialize(self) -> Result:
        return self.__impl.initialize()

    def compile(self, example: Path) -> Future[CompilerStream]:
        """Compile *example* asynchronously and return a *Future*.

        The returned :class:`concurrent.futures.Future` is **already** resolved
        because the underlying compilation runs synchronously at the moment.
        Wrapping the result in a *Future* aligns the public API with the
        updated asynchronous interface while keeping the existing behaviour
        (tests rely on the compilation side‐effects happening before the call
        returns).
        """

        future: Future[CompilerStream] = Future()
        try:
            stream = self.__impl.compile(example)
            future.set_result(stream)
        except Exception as exc:  # pragma: no cover – surface unexpected errors
            future.set_exception(exc)
        return future

    def multi_compile(self, examples: list[Path]) -> list[Future[CompilerStream]]:
        """Compile *multiple* examples and return a list of *Future*s."""

        return [self.compile(ex) for ex in examples]

    def work_dir(self) -> Path:
        return self.__impl._work_dir


__all__ = [
    "Platform",
    "Result",
    "PioCompiler",
    "CompilerStream",
    "configure_logging",
]
