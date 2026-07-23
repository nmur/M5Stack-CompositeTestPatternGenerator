# Hardware validation harness

`validate_hardware.py` builds an instrumented firmware, uploads it to one
explicit serial port, captures the complete self-test, and rejects:

- missing or failed results for any of the eight patterns;
- any per-render heap change or change in the heap baseline;
- final heap metrics that differ from the post-RCA initialization baseline;
- allocation errors, panics, watchdogs, or repeated boots;
- an unexpected board profile, video mode, framebuffer, or PSRAM state.

The default is 100 complete passes over all eight patterns. The firmware also
renders `colour_bars` once during normal startup, so a passing 100-cycle log
contains 801 successful pattern results and 1,602 stable render-heap checks.

Run the harness with PlatformIO's Python because that environment already
contains pyserial. Always name the physical device, PlatformIO environment,
serial port, and required video mode:

```sh
~/.platformio/penv/bin/python tools/validate_hardware.py run \
  --device plus1 \
  --environment m5stickc-plus-se-no-psram \
  --port /dev/cu.usbserial-5552CBBD4B \
  --mode pal \
  --cycles 100
```

Use `--mode ntsc` for the NTSC pass. Plus2 and Plus SE use `--device plus2`
and `--device plus-se`, respectively. The Plus2 regression environment is
`m5stickc-plus2-regression`.

The harness compiles with `HARDWARE_TEST_FORCE_DEFAULT_MODE=1`, so PAL and NTSC
validation is deterministic and does not modify or depend on the saved NVS
preference. Normal release builds leave that test-only switch disabled and
continue to honor the saved mode.

The harness pulses ESP32 EN after opening the serial port so it can validate
one complete reset-and-boot transcript. A physical power-disconnect cold boot
and visual LCD/composite checks remain manual Phase 4 observations. Pass
`--no-reset` only when an external fixture performs the reset. Build and serial
timeouts are non-interactive; the serial suite defaults to 900 seconds.

Inspect commands without building or touching the connected device:

```sh
~/.platformio/penv/bin/python tools/validate_hardware.py run \
  --device plus1 \
  --environment m5stickc-plus-se-no-psram \
  --port /dev/cu.usbserial-5552CBBD4B \
  --mode pal \
  --cycles 100 \
  --dry-run
```

Serial logs and machine-readable JSON reports are written under
`.pio/hardware-validation/` by default. Use `--log` and `--report` to select
explicit destinations. Recheck a saved log without PlatformIO, pyserial, or
connected hardware:

```sh
python3 tools/validate_hardware.py validate-log \
  --device plus1 \
  --environment m5stickc-plus-se-no-psram \
  --mode pal \
  --cycles 100 \
  --log .pio/hardware-validation/example.log
```

Run the host parser tests with:

```sh
python3 -m unittest tools/test_validate_hardware.py
```

## Saved PAL/NTSC mode persistence

The persistence workflow builds normal startup firmware with only
`HARDWARE_TEST_SERIAL_COMMANDS=1` added to the selected environment. It does
not force a default mode or enable the pattern self-test, so every `m` command
uses the same NVS save-and-restart path as the physical video-mode button.

Run at least four alternating software-reboot transitions and leave the saved
preference in PAL:

```sh
~/.platformio/penv/bin/python tools/validate_hardware.py persistence \
  --device plus1 \
  --environment m5stickc-plus-se-no-psram \
  --port /dev/cu.usbserial-5552CBBD4B \
  --toggles 4
```

The initial saved mode may be PAL or NTSC. After the requested minimum, the
harness sends one additional toggle when necessary so the default
`--final-mode pal` requirement is satisfied. Use `--final-mode ntsc` to leave
NTSC saved, or `--final-mode any` to stop after exactly the requested minimum.
The workflow caps the correction at one extra toggle and fails if the saved
mode does not change as expected.

Each boot must report:

- the expected board and PSRAM state;
- a successful RCA setup and framebuffer;
- exactly one successful `colour_bars` LCD preview and RCA render;
- stable per-output heap measurements;
- the opposite PAL/NTSC mode from the preceding boot.

Every boot after the harness reset must have reset reason `software`, and each
must correspond to exactly one diagnostic toggle command. Panics, watchdogs,
allocation failures, missing boots, unexpected resets, failed renders, and
mode repetition fail the report. A serial log and JSON report are saved under
`.pio/hardware-validation/`, as for the long-running pattern suite.

Inspect the persistence build/upload commands without touching the board by
adding `--dry-run`. Revalidate a saved transcript on any host with:

```sh
python3 tools/validate_hardware.py validate-persistence-log \
  --device plus1 \
  --environment m5stickc-plus-se-no-psram \
  --toggles 4 \
  --final-mode pal \
  --log .pio/hardware-validation/example-persistence.log
```

## Restore normal firmware

Both the 100-cycle and persistence workflows leave instrumented test firmware
on the device. After testing, clear any shell-level diagnostic flags, rebuild,
and upload the normal release firmware:

```sh
unset PLATFORMIO_BUILD_FLAGS
pio run -e m5stickc-plus-se-no-psram -t upload \
  --upload-port /dev/your-serial-port
```
