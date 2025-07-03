# dataclasses

import json
from dataclasses import dataclass

# An open source version of the esp-idf 5.1 platform for the ESP32 that
# gives esp32 boards the same build environment as the Arduino 2.3.1+.

# Set to a specific release, we may want to update this in the future.
ESP32_IDF_5_1_PIOARDUINO = "https://github.com/pioarduino/platform-espressif32/releases/download/51.03.04/platform-espressif32.zip"

# TODO: Upgrade toolkit to 5.3
ESP32_IDF_5_3_PIOARDUINO = "https://github.com/pioarduino/platform-espressif32/releases/download/53.03.10/platform-espressif32.zip"
ESP32_IDF_5_4_PIOARDUINO = "https://github.com/pioarduino/platform-espressif32/releases/download/54.03.20/platform-espressif32.zip"
ESP32_IDF_5_1_PIOARDUINO_LATEST = (
    "https://github.com/pioarduino/platform-espressif32.git#develop"
)
ESP32_IDF_4_4_LATEST = "platformio/espressif32"
APOLLO3_2_2_0 = "https://github.com/nigelb/platform-apollo3blue"
# Top of trunk.
# ESP32_IDF_5_1_PIOARDUINO = "https://github.com/pioarduino/platform-espressif32"

# Old fork that we were using
# ESP32_IDF_5_1_PIOARDUINO = "https://github.com/zackees/platform-espressif32#Arduino/IDF5"

# ALL will be auto populated in the Board constructor whenever a
# board is defined.
ALL: list["Board"] = []


@dataclass
class Board:
    board_name: str
    real_board_name: str | None = None
    platform: str | None = None
    platform_needs_install: bool = False
    use_pio_run: bool = (
        False  # some platforms like esp32-c2-devkitm-1 will only work with pio run
    )
    platform_packages: str | None = None
    framework: str | None = None
    board_build_mcu: str | None = None
    board_build_core: str | None = None
    board_build_filesystem_size: str | None = None
    build_flags: list[str] | None = None  # Reserved for future use.
    build_unflags: list[str] | None = None  # New: unflag options
    defines: list[str] | None = None
    customsdk: str | None = None
    board_partitions: str | None = None  # Reserved for future use.

    def __post_init__(self) -> None:
        ALL.append(self)

    def get_real_board_name(self) -> str:
        return self.real_board_name if self.real_board_name else self.board_name

    def to_dictionary(self) -> dict[str, list[str]]:
        out: dict[str, list[str]] = {}
        if self.real_board_name:
            out[self.board_name] = [f"board={self.real_board_name}"]
        options = out.setdefault(self.board_name, [])

        if self.platform:
            options.append(f"platform={self.platform}")
            # Add IDF ccache enable flag for ESP32 boards
            if "espressif32" in self.platform:
                if not self.defines:
                    self.defines = []
                self.defines.append("IDF_CCACHE_ENABLE=1")

        if self.platform_needs_install:
            options.append("platform_needs_install=true")
        if self.platform_packages:
            options.append(f"platform_packages={self.platform_packages}")
        if self.framework:
            options.append(f"framework={self.framework}")
        if self.board_build_core:
            options.append(f"board_build.core={self.board_build_core}")
        if self.board_build_mcu:
            options.append(f"board_build.mcu={self.board_build_mcu}")
        if self.board_build_filesystem_size:
            options.append(
                f"board_build.filesystem_size={self.board_build_filesystem_size}"
            )
        if self.defines:
            for define in self.defines:
                options.append(f"build_flags=-D{define}")

        # Handle build_unflags
        if self.build_unflags:
            for uf in self.build_unflags:
                options.append(f"build_unflags={uf}")

        # Handle explicit build_flags (added for native host compilation and other special cases)
        if self.build_flags:
            for bf in self.build_flags:
                options.append(f"build_flags={bf}")

        if self.customsdk:
            options.append(f"custom_sdkconfig={self.customsdk}")

        # Add board-specific build cache directory pointing via symlink directive
        # here = Path(__file__).parent
        # project_root = here.parent.parent  # Move from ci/ci/ to project root
        # cache_dir = project_root / ".pio_cache" / self.board_name
        # absolute_cache_dir = cache_dir.resolve()
        # options.append(f"build_cache_dir=symlink://{absolute_cache_dir}")

        return out

    def __repr__(self) -> str:
        json_str = json.dumps(self.to_dictionary(), indent=4, sort_keys=True)
        return json_str

    def __hash__(self) -> int:
        data_str = self.__repr__()
        return hash(data_str)

    def to_platformio_ini(self) -> str:
        """Return a `platformio.ini` snippet representing this board.

        The output is suitable for directly appending to a *platformio.ini* file
        and follows the same semantics used by the PlatformIO CLI.  Only
        parameters understood by PlatformIO are emitted – internal helper
        fields like ``platform_needs_install`` and ``use_pio_run`` are **not**
        included because they are consumed exclusively by the build helpers in
        the *ci/* folder and would be ignored (or flagged as errors) by
        PlatformIO itself.
        """
        lines: list[str] = []

        # Section header
        lines.append(f"[env:{self.board_name}]")

        # Mandatory board identifier (use the *real* board name if provided)
        lines.append(f"board = {self.get_real_board_name()}")

        # Optional parameters -------------------------------------------------
        if self.platform:
            lines.append(f"platform = {self.platform}")

        if self.platform_packages:
            lines.append(f"platform_packages = {self.platform_packages}")

        if self.framework:
            lines.append(f"framework = {self.framework}")

        if self.board_build_core:
            lines.append(f"board_build.core = {self.board_build_core}")

        if self.board_build_mcu:
            lines.append(f"board_build.mcu = {self.board_build_mcu}")

        if self.board_build_filesystem_size:
            lines.append(
                f"board_build.filesystem_size = {self.board_build_filesystem_size}"
            )

        if self.board_partitions:
            lines.append(f"board_partitions = {self.board_partitions}")

        # Build-time flags and unflags ---------------------------------------
        build_flags_elements: list[str] = []
        if self.defines:
            build_flags_elements.extend(f"-D{define}" for define in self.defines)
        if self.build_flags:
            build_flags_elements.extend(self.build_flags)
        if build_flags_elements:
            # Join all build flags with a space so that PlatformIO parses them
            lines.append(f"build_flags = {' '.join(build_flags_elements)}")

        if self.build_unflags:
            # PlatformIO accepts multiple *build_unflags* separated by spaces.
            # Emit a single line for readability.
            lines.append(f"build_unflags = {' '.join(self.build_unflags)}")

        # Custom ESP-IDF sdkconfig override (ESP32-family boards)
        if self.customsdk:
            lines.append(f"custom_sdkconfig = {self.customsdk}")

        return "\n".join(lines) + "\n"


# [env:sparkfun_xrp_controller]
# platform = https://github.com/maxgerhardt/platform-raspberrypi
# board = sparkfun_xrp_controller
# framework = arduino
# lib_deps = fastled/FastLED @ ^3.9.16


WEBTARGET = Board(
    board_name="web",
)

# Native host compilation target using PlatformIO's "native" platform.
# This allows compiling FastLED for the host machine (Linux/macOS/Windows)
# which is useful for CI compile-tests and static analysis.  We replicate
# the build flags present in ci/native/platformio.ini so that the same
# stub implementation and main-file inclusion are used.

NATIVE = Board(
    board_name="native",
    platform="platformio/native",
    build_flags=[
        "-DFASTLED_STUB_IMPL",
        '-DFASTLED_STUB_MAIN_INCLUDE_INO="../examples/Blink/Blink.ino"',
        "-std=c++17",
    ],
)

DUE = Board(
    board_name="due",
    platform="atmelsam",
)


SPARKFUN_XRP_CONTROLLER_2350B = Board(
    board_name="sparkfun_xrp_controller",
    platform="https://github.com/maxgerhardt/platform-raspberrypi",
    platform_needs_install=True,
)

APOLLO3_RED_BOARD = Board(
    board_name="apollo3_red",
    real_board_name="SparkFun_RedBoard_Artemis_ATP",
    platform=APOLLO3_2_2_0,
    platform_packages="framework-arduinoapollo3@https://github.com/sparkfun/Arduino_Apollo3#v2.2.0",
    platform_needs_install=True,
)

APOLLO3_SPARKFUN_THING_PLUS_EXPLORABLE = Board(
    board_name="apollo3_thing_explorable",
    real_board_name="SparkFun_Thing_Plus_expLoRaBLE",
    platform=APOLLO3_2_2_0,
    platform_packages="framework-arduinoapollo3@https://github.com/sparkfun/Arduino_Apollo3#v2.2.0",
    platform_needs_install=True,
)

ESP32DEV = Board(
    board_name="esp32dev",
    platform=ESP32_IDF_5_3_PIOARDUINO,
)

ESP32DEV_IDF3_3 = Board(
    board_name="esp32dev_idf33",
    real_board_name="esp32dev",
    platform="espressif32@1.11.2",
)

ESP32DEV_IDF4_4 = Board(
    board_name="esp32dev_idf44",
    real_board_name="esp32dev",
    platform=ESP32_IDF_4_4_LATEST,
)

GIGA_R1 = Board(
    board_name="giga_r1",
    platform="ststm32",
    framework="arduino",
    real_board_name="giga_r1_m7",
)

# ESP01 = Board(
#     board_name="esp01",
#     platform=ESP32_IDF_5_1_PIOARDUINO,
# )

ESP32_C2_DEVKITM_1 = Board(
    board_name="esp32c2",
    real_board_name="esp32-c2-devkitm-1",
    use_pio_run=True,
    platform="https://github.com/pioarduino/platform-espressif32.git#develop",
    defines=["CONFIG_IDF_TARGET_ESP32C2=1"],
    customsdk="CONFIG_IDF_TARGET=esp32c2",
)

ESP32_C3_DEVKITM_1 = Board(
    board_name="esp32c3",
    real_board_name="esp32-c3-devkitm-1",
    platform=ESP32_IDF_5_3_PIOARDUINO,
)

ESP32_C6_DEVKITC_1 = Board(
    board_name="esp32c6",
    real_board_name="esp32-c6-devkitc-1",
    platform=ESP32_IDF_5_3_PIOARDUINO,
)

ESP32_S3_DEVKITC_1 = Board(
    board_name="esp32s3",
    real_board_name="esp32-s3-devkitc-1",
    platform=ESP32_IDF_5_4_PIOARDUINO,
    board_partitions="huge_app.csv",
    build_unflags=["-DFASTLED_RMT5=0", "-DFASTLED_RMT5"],
)

ESP32_S2_DEVKITM_1 = Board(
    board_name="esp32s2",
    real_board_name="esp32dev",
    board_build_mcu="esp32s2",
    platform=ESP32_IDF_5_3_PIOARDUINO,
)

ESP32_H2_DEVKITM_1 = Board(
    board_name="esp32-h2-devkitm-1",
    platform_needs_install=True,  # Install platform package to get the boards
    platform=ESP32_IDF_5_3_PIOARDUINO,
)

ESP32_P4 = Board(
    board_name="esp32p4",
    real_board_name="esp32-p4-evboard",
    platform_needs_install=True,  # Install platform package to get the boards
    platform="https://github.com/pioarduino/platform-espressif32/releases/download/stable/platform-espressif32.zip",
)

ADA_FEATHER_NRF52840_SENSE = Board(
    board_name="adafruit_feather_nrf52840_sense",
    platform="nordicnrf52",
)

XIAOBLESENSE_ADAFRUIT_NRF52 = Board(
    board_name="xiaoblesense_adafruit",
    platform="https://github.com/maxgerhardt/platform-nordicnrf52",
    platform_needs_install=True,  # Install platform package to get the boards
)

# Alias: handle common misspelling without the trailing 't'
XIAOBLESENSE_ADAFRUI_ALIAS = Board(
    board_name="xiaoblesense_adafrui",  # missing 't'
    real_board_name="xiaoblesense_adafruit",  # map to the correct board name
    platform="https://github.com/maxgerhardt/platform-nordicnrf52",
    platform_needs_install=True,
)

XIAOBLESENSE_NRF52 = Board(
    board_name="xiaoblesense",
    real_board_name="xiaoble_adafruit",
    platform="https://github.com/maxgerhardt/platform-nordicnrf52",
    platform_needs_install=True,
)

# Correct nRF52840 DK board definition
# The Nordic nRF52840 DK is directly supported by the default PlatformIO
# `nordicnrf52` platform under the board name `nrf52840_dk`, so we don't
# need a custom platform package or extra installation steps.  Point the
# Board definition at the stock platform and use the canonical board name.
# This fixes compilation failures introduced during the build-system
# migration where the board was temporarily mapped to the XIAO variant.
NRF52840 = Board(
    board_name="nrf52840_dk",
    real_board_name="nrf52840_dk_adafruit",  # Use Adafruit BSP variant which includes full Nordic SDK headers
    platform="nordicnrf52",
    framework="arduino",
    platform_needs_install=False,
    platform_packages="framework-arduinoadafruitnrf52@^1.10601.0",
    defines=[
        "FASTLED_USE_COMPILE_TESTS=0",
    ],
    board_build_core="nRF5",  # Ensure correct core directory
)

RPI_PICO = Board(
    board_name="rpipico",
    platform="https://github.com/maxgerhardt/platform-raspberrypi.git",
    platform_needs_install=True,  # Install platform package to get the boards
    platform_packages="framework-arduinopico@https://github.com/earlephilhower/arduino-pico.git",
    framework="arduino",
    board_build_core="earlephilhower",
    board_build_filesystem_size="0.5m",
)

RPI_PICO2 = Board(
    board_name="rpipico2",
    real_board_name="rpipico",  # Use the existing Pico board definition until PlatformIO adds native Pico 2 support
    platform="https://github.com/maxgerhardt/platform-raspberrypi.git",
    platform_needs_install=True,  # Install platform package to get the boards
    platform_packages="framework-arduinopico@https://github.com/earlephilhower/arduino-pico.git",
    framework="arduino",
    board_build_core="earlephilhower",
    board_build_filesystem_size="0.5m",
)

BLUEPILL = Board(
    board_name="bluepill",
    real_board_name="bluepill_f103c8",
    platform="ststm32",
)

# maple_mini_b20
MAPLE_MINI = Board(
    board_name="maple_mini",
    real_board_name="maple_mini_b20",
    platform="ststm32",
)

ATTINY88 = Board(
    board_name="attiny88",
    platform="atmelavr",
)

# ATtiny1604
ATTINY1616 = Board(
    board_name="ATtiny1616",
    platform="atmelmegaavr",
)

UNO_R4_WIFI = Board(
    board_name="uno_r4_wifi",
    platform="renesas-ra",
)

NANO_EVERY = Board(
    board_name="nano_every",
    platform="atmelmegaavr",
)

ESP32DEV_I2S = Board(
    board_name="esp32dev_i2s",
    real_board_name="esp32dev",
    platform=ESP32_IDF_4_4_LATEST,
)

ESP32S3_RMT51 = Board(
    board_name="esp32rmt_51",
    real_board_name="esp32-s3-devkitc-1",
    platform_needs_install=True,
    platform=ESP32_IDF_5_3_PIOARDUINO,
    defines=[
        "FASTLED_RMT5=1",
    ],
)

# Teensy boards
TEENSY_LC = Board(
    board_name="teensylc",
    platform="teensy",
    framework="arduino",
)

TEENSY30 = Board(
    board_name="teensy30",
    platform="teensy",
    framework="arduino",
)

TEENSY31 = Board(
    board_name="teensy31",
    platform="teensy",
    framework="arduino",
)

TEENSY40 = Board(
    board_name="teensy40",
    platform="teensy",
    framework="arduino",
)

TEENSY41 = Board(
    board_name="teensy41",
    platform="teensy",
    framework="arduino",
)

# Basic Arduino boards
UNO = Board(
    board_name="uno",
    platform="atmelavr",
    framework="arduino",
)

YUN = Board(
    board_name="yun",
    platform="atmelavr",
    framework="arduino",
)

DIGIX = Board(
    board_name="digix",
    real_board_name="due",  # Digix is Arduino Due compatible
    platform="atmelsam",
    framework="arduino",
)

# ESP8266 boards
ESP01 = Board(
    board_name="esp01",
    platform="espressif8266",
    framework="arduino",
)

# ATtiny boards
ATTINY85 = Board(
    board_name="attiny85",
    platform="atmelavr",
    framework="arduino",
)

# Seeed XIAO ESP32S3 board – same platform, needs FASTLED_RMT5 macro removal
XIAO_ESP32S3 = Board(
    board_name="seeed_xiao_esp32s3",
    real_board_name="seeed_xiao_esp32s3",
    platform=ESP32_IDF_5_4_PIOARDUINO,
    board_partitions="huge_app.csv",
    defines=None,
    build_unflags=["-DFASTLED_RMT5=0", "-DFASTLED_RMT5"],
)


def _make_board_map(boards: list[Board]) -> dict[str, Board]:
    # make board map, but assert on duplicate board names
    board_map: dict[str, Board] = {}
    for board in boards:
        assert (
            board.board_name not in board_map
        ), f"Duplicate board name: {board.board_name}"
        board_map[board.board_name] = board
    return board_map


_BOARD_MAP: dict[str, Board] = _make_board_map(ALL)


def get_board(board_name: str, no_project_options: bool = False) -> Board:
    if no_project_options:
        return Board(board_name=board_name)
    if board_name not in _BOARD_MAP:
        # empty board without any special overrides, assume platformio will know what to do with it.
        return Board(board_name=board_name)
    else:
        return _BOARD_MAP[board_name]
