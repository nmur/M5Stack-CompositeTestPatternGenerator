# M5Stack-CompositeTestPatternGenerator

[![demonstration](./img/demonstration_thumb.jpg)](./img/demonstration.jpg)    [![board](./img/device_thumb.jpg)](./img/device.jpg)

A portable composite video test pattern generator for the original
ESP32-based M5StickC Plus family. It provides a quick way to perform basic CRT
TV checks when connecting an entire console would be inconvenient.

> [!IMPORTANT]
> The firmware no longer requires PSRAM. M5StickC Plus v1 has been tested on
> hardware; Plus v1.1, Plus2, and the new Plus SE still require the validation
> noted below. ESP32-S3-based devices are not currently supported.

Features:

- PAL/NTSC support
- Multiple test patterns
- 16-bit colour (RGB565)
- Built-in battery and screen

## Device Compatibility

| Device | PlatformIO environment | Current status |
|---|---|---|
| M5StickC Plus v1 | `m5stickc-plus-se-no-psram` | The automated hardware suite transferred all eight patterns to the LCD and RCA outputs in PAL and NTSC with stable heap. Physical cold-power and visual LCD/composite checks are still pending. |
| M5StickC Plus v1.1 | `m5stickc-plus-se-no-psram` | Uses the same hardware profile, but has not been tested separately. |
| M5StickC Plus2 | `m5stickc-plus-se-no-psram` | Uses the common release firmware. The optional `m5stickc-plus2-regression` environment builds successfully, but testing this revision on Plus2 hardware is pending. |
| M5StickC Plus SE | `m5stickc-plus-se-no-psram` | Build passes using the temporary PlatformIO workaround. Hardware validation is pending, so support remains experimental. |

See [Building and maintaining the firmware](docs/building-firmware.md) for the
exact build/upload commands, the Plus SE workaround, and measured firmware
size.

## Setting up the Hardware

There are a couple of ways to assemble the composite adapter. See
[Setting up the hardware](docs/setting-up-hardware.md) for details.

The [schematic](plot/schematic.png) is also available in the repository.

## Uploading the Firmware

Navigate to the
[Installation page](https://nmur.github.io/M5Stack-CompositeTestPatternGenerator-WebInstaller/)
to connect to your device and flash a published firmware build from your
browser. The prepared multi-device bundle in this repository has not been
published to that separate site; use the local PlatformIO workflow for this
revision until the bundle is reviewed and published.

You may need to install the
[CH340 drivers](https://www.wch-ic.com/downloads/CH341SER_ZIP.html) before the
device can connect.

For local builds, including the experimental Plus SE target, follow the
[PlatformIO instructions](docs/building-firmware.md#build-and-upload).

## How to Use

Power the device on by holding the small power button on the left side, then
connect the composite cable to your CRT TV. Cycle through test patterns with
the large face button, and toggle between video formats with the small button
on the right side.

Power the device off by holding the small power button for 5 seconds.

The device remembers the last video format, so you do not need to select it
again every time it boots.

## Pattern Assets

The eight source PNG files under `include/` are converted deterministically to
compact, lossless RGB565 assets during development. See the
[asset-generation workflow](docs/building-firmware.md#pattern-assets) and the
[format specification](docs/pattern-asset-format.md) before adding or changing
a pattern.

The generated payload for all eight patterns is 8,791 bytes. The common
Plus-family build occupies 496,561 bytes of application flash and 27,756 bytes
of static RAM.

## Roadmap

- [ ] More patterns
- [ ] Scrolling tests
- [ ] Custom image support (using SPIFFS)

## Acknowledgements

- [lovyan03](https://github.com/lovyan03) for their [LovyanGFX](https://github.com/lovyan03/LovyanGFX) library
- [Artemio Urbina](https://github.com/ArtemioUrbina) for his test patterns
