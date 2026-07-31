# M5Stack-CompositeTestPatternGenerator

[![demonstration](./img/demonstration_thumb.jpg)](./img/demonstration.jpg)    [![board](./img/device_thumb.jpg)](./img/device.jpg)

A portable composite video test pattern generator for the original
ESP32-based M5StickC Plus family. This tool is aimed to be used as a quick and portable way of performing tests of basic functionality for CRT TVs in situations where hooking up an entire console would be inconvenient.

It is *not* intended to be a precision tool for diagnostics and fine tuning.

Features:

- PAL/NTSC support
- Multiple test patterns
- Refresh-synchronised vertical and horizontal scrolling tests
- 16-bit colour (RGB565)
- Built-in battery and screen

## Device Compatibility

| Device | Compatibility |
|---|---|
| M5StickC Plus v1 | ✅ |
| M5StickC Plus v1.1 | ✅ |
| M5StickC Plus2 | ✅ |
| M5StickC Plus SE | ✅ |
| M5StickS3 | ❌ |

## Setting up the Hardware

There are a couple of ways to assemble the composite video adapter. See
[Setting up the hardware](docs/setting-up-hardware.md) for details.

The [schematic](plot/schematic.png) is also available.

## Uploading the Firmware

Navigate to the [Installation page](https://nmur.github.io/M5Stack-CompositeTestPatternGenerator-WebInstaller/) to connect to your device and flash the firmware from your browser directly.

You'll need to install [CH340 drivers](https://www.wch-ic.com/downloads/CH341SER_ZIP.html) in order to connect to your device.

## How to use

Power the device on by holding the small power button on the left side, then
connect the composite cable to your CRT TV. Cycle through test patterns with
the large face button, and toggle between video formats with the small button
on the right side.

Hold the large face button for 750 ms to enter the scrolling grid in vertical
mode. Short presses then alternate between vertical and horizontal scrolling.
Hold the large button again to return to the previously selected static test
pattern.

Power the device off by holding the small power button for 5 seconds.

The device remembers the last video format, so you do not need to select it
again every time it boots.

## Roadmap

- [x] More patterns
- [x] Scrolling tests
- [ ] Custom image support

## Acknowledgements

- [lovyan03](https://github.com/lovyan03) for [LovyanGFX](https://github.com/lovyan03/LovyanGFX)
- [Artemio Urbina](https://github.com/ArtemioUrbina) for his test patterns
- Mostly developed using Codex
