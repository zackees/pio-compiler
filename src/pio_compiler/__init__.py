from concurrent.futures import Future
from pathlib import Path
from typing import Any

from .compiler_stream import CompilerStream
from .logging_utils import configure_logging
from .types import Platform, Result


class PioCompiler:
    def __init__(
        self,
        platform: Platform,
        *,
        work_dir: Path | None = None,
        force_rebuild: bool = False,
        info_mode: bool = False,
        cache_entry=None,
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
            allows callers to re-use a previous build directory so that
            subsequent invocations can benefit from incremental compilation.
        force_rebuild:
            When *True*, forces a full clean rebuild by running 'platformio run
            --target clean' before compilation. This removes all build artifacts
            and starts fresh. When *False* (default), performs an incremental
            build reusing cached artifacts.
        info_mode:
            When *True*, enables generation of optimization reports and build
            information files after successful compilation.
        cache_entry:
            Optional cache entry information for optimized library handling.
        """

        from .compiler import PioCompilerImpl

        self.__impl: PioCompilerImpl = PioCompilerImpl(
            platform,
            work_dir=work_dir,
            force_rebuild=force_rebuild,
            info_mode=info_mode,
            cache_entry=cache_entry,
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

    def build_info(self) -> dict[str, Any]:
        """Return build information."""
        return self.__impl.build_info()

    def get_pio_cache_dir(self, example: Path | str) -> str | None:
        """Get the PlatformIO cache directory path that will be used for this build."""
        return self.__impl.get_pio_cache_dir(example)

    def generate_optimization_report(
        self, project_dir: Path, example_path: Path, output_dir: Path | None = None
    ) -> Path | None:
        """Generate optimization report and return the path to the report file."""
        return self.__impl.generate_optimization_report(
            project_dir, example_path, output_dir
        )

    def generate_build_info(
        self,
        project_dir: Path,
        example_path: Path,
        build_start_time: float,
        output_dir: Path | None = None,
    ) -> Path | None:
        """Generate build_info.json file and return the path to the file."""
        return self.__impl.generate_build_info(
            project_dir, example_path, build_start_time, output_dir
        )

    def generate_symbols_report(
        self, project_dir: Path, example_path: Path, output_dir: Path | None = None
    ) -> Path | None:
        """Generate symbols analysis report and return the path to the report file."""
        return self.__impl.generate_symbols_report(
            project_dir, example_path, output_dir
        )

    def handle_library_archives(
        self,
        project_dir: Path,
        library_name: str = "FastLED",
        library_version: str = "3.10.1",
    ) -> bool:
        """Handle library archive creation after successful build."""
        return self.__impl.handle_library_archives(
            project_dir, library_name, library_version
        )

    @property
    def _work_dir(self) -> Path:
        """Return the work directory path."""
        return self.__impl._work_dir


__all__ = [
    "Platform",
    "Result",
    "PioCompiler",
    "CompilerStream",
    "configure_logging",
]
