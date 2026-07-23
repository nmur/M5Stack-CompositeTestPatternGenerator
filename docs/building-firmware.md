# Building and maintaining the firmware

The repository has two explicit PlatformIO environments. The default is the
common no-PSRAM release build used by M5StickC Plus v1/v1.1, Plus2, and Plus
SE.

| Environment | Intended target | PSRAM configuration |
|---|---|---|
| `m5stickc-plus-se-no-psram` | Plus v1/v1.1, Plus2, and Plus SE release firmware | No PSRAM flags; RCA and rendering use internal RAM |
| `m5stickc-plus2-regression` | Optional Plus2 maintainer diagnostics | Initializes Plus2 PSRAM for diagnostics, but RCA and rendering still use internal RAM |

Both environments pin M5GFX 0.2.26 and M5Unified 0.2.19.

## Build and upload

Run commands from the repository root.

Build the default common Plus-family firmware:

```sh
pio run -e m5stickc-plus-se-no-psram
```

Upload it to an attached device:

```sh
pio run -e m5stickc-plus-se-no-psram -t upload
```

For the normal Plus2 firmware, use the default commands above. To build and
upload the optional Plus2 diagnostic configuration:

```sh
pio run -e m5stickc-plus2-regression
pio run -e m5stickc-plus2-regression -t upload
```

If PlatformIO finds more than one serial device, select the target explicitly:

```sh
pio run -e m5stickc-plus-se-no-psram -t upload \
  --upload-port /dev/your-serial-port
pio device monitor --port /dev/your-serial-port -b 115200
```

Serial-port names vary by operating system. The monitor baud rate is 115200.

## Plus SE PlatformIO status

PlatformIO does not currently provide a dedicated M5StickC Plus SE board
manifest. The `m5stickc-plus-se-no-psram` environment therefore uses
`board = m5stick-c`, explicitly selects 4 MB flash, and relies on M5GFX runtime
hardware detection for Plus-family displays.

This target builds successfully, but it has not yet been run on a Plus SE.
Treat SE support as experimental until its LCD, buttons, AXP192 power behavior,
GPIO26 composite output, serial upload, PAL/NTSC operation, and repeated pattern
changes have been checked on real hardware.

Do not add `BOARD_HAS_PSRAM` to the common release environment. Plus v1/v1.1
and Plus SE have no PSRAM, while the common Plus2 firmware deliberately leaves
its PSRAM unused. The renderer operates entirely from internal RAM on every
target.

## Recorded build footprint

These measurements use the 1,310,720-byte application partition:

| Environment | Static RAM | Application flash |
|---|---:|---:|
| Common no-PSRAM | 27,756 B (8.5%) | 496,561 B (37.9%) |
| Plus2 regression | 27,820 B (8.5%) | 514,281 B (39.2%) |

These are compile-time size reports, not claims of hardware validation.
M5StickC Plus v1 is the only device on which this revision has currently been
exercised. Plus v1.1, Plus2, and Plus SE testing remains pending, and composite
output has not yet received an external visual-validation pass.

## Pattern assets

The 320×240 PNG files in `include/` are the editable source of truth. Generated
files under `include/generated/` and `src/generated/` must not be edited by
hand.

After changing a source PNG, regenerate the compressed assets:

```sh
python3 tools/generate_pattern_assets.py --write
```

Then verify asset freshness, exact decoding, and all NTSC, preview, and PAL
golden outputs:

```sh
python3 tools/generate_pattern_assets.py --check
python3 tools/verify_firmware_pipeline.py
```

PlatformIO also runs the freshness check before every firmware build.

When adding a new pattern:

1. Add a 320×240 PNG under `include/`.
2. Add its name and filename to `PATTERNS` in
   `tools/verify_golden_outputs.py`.
3. Add the same name to `EXPECTED_PATTERNS` in
   `tools/validate_hardware.py`.
4. Update the expected pattern-count assertion in `src/main.cpp`.
5. Regenerate the C++ assets. The generator derives its declarations and
   `kCount` from `PATTERNS`.
6. Generate a candidate golden manifest, inspect every new or changed hash,
   then deliberately update the tracked manifest:

   ```sh
   python3 tools/verify_golden_outputs.py --emit-manifest \
     > /tmp/golden_outputs.sha256.json
   diff -u test/golden_outputs.sha256.json \
     /tmp/golden_outputs.sha256.json
   ```

7. Run the full native verification and both PlatformIO builds.
8. Exercise the new pattern on each available hardware target.

The [pattern asset format](pattern-asset-format.md) documents RGB565
conversion, alpha handling, the palette/RLE row codec, metadata, limits, and
the allocation-free decoder. The more detailed
[tool reference](../tools/README.md) covers the golden-output workflow.
