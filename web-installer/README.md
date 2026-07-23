# Web-installer release artifacts

The public installer is maintained in the separate
[`M5Stack-CompositeTestPatternGenerator-WebInstaller`](https://github.com/nmur/M5Stack-CompositeTestPatternGenerator-WebInstaller)
repository. This directory defines the reproducible handoff from the firmware
repository; generated binaries under `dist/` are intentionally ignored.

## Generate a bundle

From the firmware repository root, run:

```sh
python3 tools/package_web_installer.py --version 1.2.0
```

The command first builds the common `m5stickc-plus-se-no-psram` PlatformIO
environment. To package build outputs that have already been verified, add
`--no-build`. That option cannot tell a normal build from a diagnostic build;
use it only after rebuilding without `PLATFORMIO_BUILD_FLAGS`.

The output contains:

- `index.html`, with a device choice and install button for each target;
- `manifest.json`, for one family-wide install button;
- a device-labelled manifest for Plus v1/v1.1, Plus2, and Plus SE;
- `bin/v<version>/common/firmware.bin`, a merged image flashed at offset zero;
- `release-index.json`, with target, build, size, and source-component metadata;
- `SHA256SUMS`, covering every generated artifact.

The three devices use the same common no-PSRAM firmware. M5GFX detects the
specific board at runtime. Plus v1/v1.1 and Plus2 remain labelled
validation-pending, while Plus SE remains labelled experimental, until their
remaining hardware suites pass.

ESP Web Tools can identify an ESP32 chip but cannot distinguish Plus, Plus2,
and Plus SE hardware. A web page that offers device-specific choices must wire
each button to its matching manifest. The manifests currently reference the
same binary, but keeping separate entry points prevents future target-specific
artifacts from becoming an installer-breaking change.

## Publish to the installer repository

Review `release-index.json` and verify `SHA256SUMS`, then copy the generated
bundle contents into the installer repository. The generated `index.html`
already points at the manifests beside it. Publishing the GitHub Pages site
and tagging a firmware release are deliberate maintainer actions and are not
performed by the packaging script.

The package is merged with esptool using the ESP32 layout and settings required
by the current PlatformIO board definition:

| Part | Source offset |
|---|---:|
| Bootloader | `0x1000` |
| Partition table | `0x8000` |
| OTA boot stub | `0xE000` |
| Application | `0x10000` |

The merged artifact is configured for DIO, 40 MHz, and 4 MB flash. This follows
ESP Web Tools guidance for firmware based on ESP-IDF 4 or later and avoids
depending on the browser to patch flash parameters in separate images.
