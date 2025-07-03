from concurrent.futures import Future
from pathlib import Path

from .compiler_stream import CompilerStream
from .logging_utils import configure_logging
from .types import Platform, Result


class PioCompiler:
    def __init__(self, platform: Platform) -> None:
        from .compiler import PioCompilerImpl

        self.__impl: PioCompilerImpl = PioCompilerImpl(platform)

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
