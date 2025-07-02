from pathlib import Path

from .compiler_stream import CompilerStream
from .types import Platform, Result


class PioCompiler:
    def __init__(self, platform: Platform):
        from .compiler import PioCompilerImpl

        self.__impl: PioCompilerImpl = PioCompilerImpl(platform)

    def initialize(self) -> Result:
        return self.__impl.initialize()

    def compile(self, example: Path) -> CompilerStream:
        return self.__impl.compile(example)

    def multi_compile(self, examples: list[Path]) -> list[CompilerStream]:
        return self.__impl.multi_compile(examples)


__all__ = [
    "Platform",
    "Result",
    "PioCompiler",
    "CompilerStream",
]
