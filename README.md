# pio-comile

This is a special project to efficiently compile code using platformio.

## Runtime

  * `pio-compile native --src test/test_data/example/Blink --src test/test_data/example/Blur`


## Implimentation details

@dataclass
class Platform(str):
  name: str
  platformio_ini: str

@dataclass
class Result:
  bool ok: bool
  platform: Platform
  example: Path | None
  stdout: str
  stderr: str
  build_info: str
  exception: Exception | None

class PioCompilerImpl:
  def __init__(platform: Platform) -> None
  def initialize() -> Result | Exception
  def build_info() -> dict
  def compile(example: Path) -> Result | Exception
  def multi_compile(examples: list[Path]) -> list[Result | Exception]


## Examples

ESP32_S3 = Platform(
    "esp32s3",
    platformio_ini = "..."
)

s3_compiler = PioCompilerImpl(ESPESP32_S332)
result_or_err = s3_compiler.initialize()
if isisntance(result_or_error, Exception)
  raise result_or_error

print(f"\nInitializing {ESP32_S3} success!")

result_or_error = s3_compiler.compile("examples/Blink")
if !ok:
  print(f"Error happened with {result_or_error}")
  raise Exception from result_or_error

print(f"Compiling examples/Blink successful!")
sys.exit(0)
  

  