# M5StickC Plus and Plus SE Compatibility Plan

Status: In progress — Phases 0–3 complete; Plus1 automated Phase 4 validation passed; Phase 5 release handoff prepared  
Last updated: 2026-07-23  
Targets: M5StickC Plus v1/v1.1, M5StickC Plus2, and M5StickC Plus SE

## Goals

- Run PAL and NTSC output reliably without requiring PSRAM.
- Preserve the current RGB565 source pixels, LCD preview, and PAL bilinear output exactly.
- Support all eight existing test patterns.
- Fit the common firmware comfortably in the 4 MB Plus/SE devices.
- Keep Plus2 compatibility without making it a separate implementation.

## Confirmed Findings

- [x] PSRAM is not intrinsically required by `M5UnitRCA`; its CVBS implementation supports `psram_no_use` and internal DMA-capable RAM.
- [x] Reproduced the boot loop on the connected Plus1 without uploading new firmware.
- [x] Decoded the Plus1 panic to the unchecked null image passed by `displayPalRca()`.
- [x] Confirmed that a fresh installation defaults to PAL.
- [x] Confirmed that the PAL scaler allocates 221,184 bytes and never frees it.
- [x] Confirmed that every raw header is stored in flash `.rodata`, not PSRAM or normal heap.
- [x] Verified every existing PNG converted byte-for-byte to its legacy RGB565 header before removal.
- [x] Verified the current PlatformIO and M5 library support situation for the new Plus SE.

The pre-Phase 2 PAL path held an RCA framebuffer and then attempted to allocate a second full PAL image:

| Allocation | NTSC RGB565 | PAL RGB565 |
|---|---:|---:|
| RCA framebuffer | 153,600 B | 221,184 B |
| RCA supporting allocations | ~6,712 B | ~9,868 B |
| Current scaling temporary | 0 B | 221,184 B |
| Current LCD preview temporary | 38,400 B | 38,400 B |
| Proposed renderer scratch | ~2–3 KB | ~2–3 KB |

The original missing-PSRAM warning on Plus1 occurred because that build enabled
`BOARD_HAS_PSRAM`. The actual panic followed PAL scaling returning `nullptr`
and the old [main.cpp](../src/main.cpp) passing it to `pushImage()`. Both
full-image allocation paths have now been removed.

Phase 0 baseline flash measurements:

| Item | Size |
|---|---:|
| One raw 320×240 RGB565 pattern | 153,600 B |
| Five currently enabled patterns | 768,000 B |
| All eight patterns as raw RGB565 | 1,228,800 B |
| Current firmware | 1,267,985 B |
| Current app partition | 1,310,720 B |
| All eight source PNGs | 13,500 B |
| Proposed generated row assets | approximately 8.8 KB |

Hardware references:

- [M5StickC Plus/Plus2 comparison](https://docs.m5stack.com/en/core/M5StickC%20PLUS2)
- [M5StickC Plus SE specifications and pin map](https://docs.m5stack.com/en/core/StickC-Plus_SE)
- [M5StickC Plus SE compilation requirements](https://docs.m5stack.com/en/arduino/m5stickc-plus_se/display)
- [PlatformIO M5Stick-C board definition](https://docs.platformio.org/en/latest/boards/espressif32/m5stick-c.html)

## Phase 0/1 Implementation Record

- Host verification covers all eight patterns and all three output forms: NTSC
  320×240, LCD preview 160×120, and PAL 384×288. The tracked manifest contains
  24 SHA-256 hashes and the verifier also checks every PNG against its legacy
  RGB565 header.
- The no-PSRAM Plus/SE build uses 25,724 bytes of static RAM and 1,252,753 bytes
  of the 1,310,720-byte app partition. The Plus2 regression build uses 25,788
  bytes of static RAM and 1,270,465 bytes of the same app partition.
- On the connected Plus1, `psramFound()` reports false and no PSRAM
  initialization warning occurs. The RGB565 NTSC framebuffer initialized in
  internal RAM with 108,612 bytes free afterward; the PAL framebuffer also
  initialized in internal RAM with 37,780 bytes free afterward.
- The current full-image PAL scaler and LCD preview allocations do not fit
  after the PAL framebuffer. They now fail with visible and serial diagnostics
  instead of causing a null dereference or boot loop. Removing those
  allocations remains the explicit Phase 2 boundary.
- The released/default environment is the common no-PSRAM build. The separate
  Plus2 regression environment enables PSRAM initialization only for hardware
  diagnostics; the RCA and rendering path remains configured for internal RAM.

## Phase 2/3 Implementation Record

- `ScanlineRenderer::Scratch` is exactly 2,048 bytes: two decoded 320-pixel
  source rows and one 384-pixel output row. Rendering contains no allocator
  calls and firmware checks that free internal heap is unchanged across every
  pattern transfer.
- The native host test compiles the actual C++ decoder, scaler, and scanline
  renderer. All eight assets decode exactly and all 24 NTSC, preview, and PAL
  SHA-256 outputs match the Phase 0 goldens.
- The generated payload is 8,791 bytes total:

| Pattern | Payload |
|---|---:|
| Colour bars | 316 B |
| Grid | 766 B |
| Circles | 3,726 B |
| Gradients | 3,975 B |
| White | 2 B |
| Red | 2 B |
| Green | 2 B |
| Blue | 2 B |

- The final no-PSRAM Plus/SE build uses 27,756 bytes of static RAM and 496,561
  bytes of flash (37.9% of the app partition). The Plus2 regression build uses
  27,820 bytes of static RAM and 514,281 bytes of flash (39.2%).
- Instrumented Plus1 runs rendered all eight patterns in both PAL and NTSC.
  Internal free heap remained constant across every preview and composite
  transfer: 35,708 bytes in PAL and 106,532 bytes in NTSC.
- The eight legacy raw RGB565 headers were removed after the exact decoder and
  renderer comparisons passed. PNG files remain the editable source of truth,
  and every PlatformIO build now rejects stale generated assets.

## Definition of Done

- [ ] One low-memory rendering implementation works on Plus v1/v1.1, Plus2, and Plus SE.
- [x] PAL and NTSC boot successfully without PSRAM.
- [x] All eight patterns are enabled.
- [x] Generated NTSC, preview, and PAL pixels match the current implementation exactly.
- [x] Pattern rendering performs no full-image heap allocation.
- [x] Repeated pattern changes do not reduce free heap on the connected Plus1.
- [x] Firmware fits the default 4 MB device app partition with substantial headroom.
- [ ] Plus1 and Plus2 pass hardware testing.
- [ ] Plus SE passes the same hardware suite when a unit is available.

## Phase 0 — Golden Baseline and Diagnostics

- [x] `P0.1` Record the current firmware and partition sizes.
- [x] `P0.2` Record the current framebuffer and temporary allocation sizes.
- [x] `P0.3` Capture and symbolicate the Plus1 boot-loop backtrace.
- [x] `P0.4` Confirm the PNG-to-RGB565 conversion matches all eight headers.
- [x] `P0.5` Add a host-side reference renderer for:
  - 320×240 NTSC output
  - 160×120 LCD preview sampling
  - 384×288 fixed-point PAL bilinear output
- [x] `P0.6` Generate golden CRC32 or SHA-256 values for every pattern and output type.
- [x] `P0.7` Add firmware diagnostics for:
  - reset reason
  - detected board
  - `psramFound()`
  - free internal heap
  - largest 8-bit heap block
  - largest DMA-capable block
  - RCA initialization result
- [x] `P0.8` Add graceful error handling so initialization or decoding failure displays/logs an error instead of dereferencing null data.

Exit criteria:

- [x] Golden output can be regenerated deterministically on the host.
- [x] Current failure and memory pressure can be observed without relying on a panic.

## Phase 1 — Build Targets and PSRAM Independence

- [x] `P1.1` Refactor [platformio.ini](../platformio.ini) into shared settings plus explicit target environments.
- [x] `P1.2` Add a Plus/Plus SE environment using:
  - `board = m5stick-c`
  - 4 MB flash settings
  - no `BOARD_HAS_PSRAM`
  - no PSRAM cache workaround
- [x] `P1.3` Pin M5Unified and M5GFX to versions known to satisfy the Plus SE requirements.
- [x] `P1.4` Retain a Plus2 environment for regression testing.
- [x] `P1.5` Decide whether the released Plus2 artifact should:
  - use the same no-PSRAM configuration as Plus/SE; or
  - enable PSRAM as an optional optimization while retaining the same renderer.
- [x] `P1.6` Configure RCA with `M5UnitRCA::psram_no_use` in the common path.
- [x] `P1.7` Verify both PAL and NTSC RCA framebuffers can initialize in internal RAM.
- [x] `P1.8` Document that PlatformIO currently has no dedicated Plus SE manifest and that `m5stick-c` plus M5GFX runtime detection is the selected target.

Exit criteria:

- [x] Plus1 firmware builds without any PSRAM flags.
- [x] Boot no longer emits a PSRAM initialization failure.
- [x] RCA initialization failures are detected and reported.

## Phase 2 — Scanline Renderer

- [x] `P2.1` Introduce a renderer API that consumes one decoded 320-pixel RGB565 row at a time.
- [x] `P2.2` Render NTSC by pushing each decoded 320-pixel row directly into the RCA framebuffer.
- [x] `P2.3` Render the LCD preview from every second source row and every second source column.
- [x] `P2.4` Replace `ScaleImageForPalBilinear()` with a scanline implementation that retains:
  - two 320-pixel source rows
  - one 384-pixel destination row
- [x] `P2.5` Reuse the current fixed-point coordinate and channel blending calculations unchanged.
- [x] `P2.6` Push each completed PAL row directly into the RCA framebuffer.
- [x] `P2.7` Wrap row transfers in `startWrite()`/`endWrite()` where supported.
- [x] `P2.8` Remove the 38,400-byte preview allocation.
- [x] `P2.9` Remove the 221,184-byte PAL allocation and its leak.
- [x] `P2.10` Assert that rendering performs no per-pattern heap allocation.
- [x] `P2.11` Golden-compare every NTSC, preview, and PAL output pixel.

Exit criteria:

- [x] Renderer scratch memory is no more than 4 KB.
- [x] All golden output comparisons pass.
- [x] Plus1 can boot and display all eight patterns in both modes using compressed row assets.

## Phase 3 — Lossless Pattern Asset Format

Preferred format:

- PNG files remain the editable source of truth.
- A deterministic host tool converts pixels to RGB565.
- Each asset contains:
  - an RGB565 palette
  - a dictionary of unique encoded rows
  - offsets for the encoded rows
  - a 240-entry source-row-to-dictionary map
  - dimensions, codec version, compressed size, and decoded CRC
- Row pixels use palette indexes with variable-length run lengths.
- Uniform patterns use a solid-colour descriptor.

Tasks:

- [x] `P3.1` Specify and document the binary/generated C++ asset format.
- [x] `P3.2` Define alpha handling as composition over black before RGB565 conversion.
- [x] `P3.3` Add a deterministic asset generator under `tools/`.
- [x] `P3.4` Generate assets for:
  - colour bars
  - grid
  - circles
  - gradients
  - white
  - red
  - green
  - blue
- [x] `P3.5` Implement `decodeRow(asset, y, destination)`.
- [x] `P3.6` Validate each decoded 320×240 image against its legacy raw header.
- [x] `P3.7` Connect the decoder to the scanline renderer.
- [x] `P3.8` Enable the red, green, and blue patterns.
- [x] `P3.9` Add a generated-file freshness check for local builds or CI.
- [x] `P3.10` Remove the giant raw headers only after all golden tests pass.
- [x] `P3.11` Record final per-asset and total payload sizes.
- [x] `P3.12` Record final firmware and partition utilization.

Targets:

- [x] Generated payload for all eight patterns is at most 16 KB.
- [x] Common no-PSRAM firmware is 496,561 bytes (37.9% of the app partition).

Exit criteria:

- [x] All eight compressed assets decode exactly.
- [x] All renderer golden tests still pass.
- [x] The firmware has ample space in the default 1,310,720-byte app partition.

## Phase 4 — Hardware Validation

Implementation record:

- The reusable [hardware validator](../tools/HARDWARE_VALIDATION.md) builds,
  uploads, captures serial output, rejects crashes/resets/render failures, and
  writes JSON evidence under `.pio/hardware-validation/`.
- Plus1 PAL passed 100 complete eight-pattern cycles: 801 successful pattern
  results, 1,602 stable render-heap checks, and 35,708 bytes free before and
  after the suite.
- Plus1 NTSC passed the same suite with 106,532 bytes free before and after.
- The saved preference passed four transitions across five boots:
  PAL → NTSC → PAL → NTSC → PAL. Every transition used the production NVS
  save/restart function and the following boot reported a software reset.
- A clean 496,561-byte release build was restored afterward and its saved PAL
  boot successfully initialized RCA and rendered colour bars.
- These automated results prove decoding and LCD/RCA transfer success, not
  visible signal quality. Physical cold-power and visual-display checks remain
  manual.

### Plus v1/v1.1

- [x] `P4.1` Upload the no-PSRAM build to Plus1.
- [ ] `P4.2` Verify a physical cold-power boot in PAL.
  - [x] Automated EN reset/`POWERON_RESET` PAL boot passed.
- [ ] `P4.3` Verify a physical cold-power boot in NTSC.
  - [x] Automated EN reset/`POWERON_RESET` NTSC boot passed.
- [ ] `P4.4` Verify LCD preview and composite output for all eight patterns.
  - [x] Firmware reported successful LCD and RCA transfers for every pattern
    in both modes.
  - [ ] Inspect both outputs visually.
- [x] `P4.5` Cycle patterns at least 100 times and confirm free heap does not trend downward.
- [x] `P4.6` Switch PAL/NTSC repeatedly and verify the persisted preference.
- [ ] `P4.7` Check composite output visually on representative PAL and NTSC displays.

### Plus2

- [ ] `P4.8` Repeat boot, pattern, mode, and persistence tests.
- [ ] `P4.9` Confirm Plus2 power-hold behavior remains correct.
- [ ] `P4.10` Compare no-PSRAM and optional PSRAM configurations if both are retained.

### Plus SE

- [ ] `P4.11` Confirm M5GFX detects the device as the Plus-compatible hardware profile.
- [ ] `P4.12` Verify LCD, buttons, AXP192 power behavior, and GPIO26 RCA output.
- [ ] `P4.13` Repeat the complete PAL/NTSC and 100-cycle test suite.
- [ ] `P4.14` Record any SE-specific upload-speed or serial-port requirements.

Exit criteria:

- [ ] No boot loops, allocation failures, or declining heap are observed on
  every target.
  - [x] Plus1 automated PAL/NTSC suites passed.
  - [ ] Plus2 and Plus SE hardware suites remain.
- [ ] Composite and LCD output are correct on every available target.

## Phase 5 — Documentation and Release

- [x] `P5.1` Update the README compatibility table.
- [x] `P5.2` Replace the Plus2-only/EOL warning with supported-device guidance.
- [x] `P5.3` Document PlatformIO environments and upload commands.
- [x] `P5.4` Document Plus SE status and any temporary PlatformIO workaround.
- [ ] `P5.5` Update web-installer artifacts for each supported target.
  - [x] Add a reproducible packager, device-labelled manifests, installer page,
    release metadata, and checksums for Plus v1/v1.1, Plus2, and Plus SE.
  - [x] Generate and validate a local `1.2.0-dev` handoff from the clean common
    release build.
  - [ ] Publish the reviewed handoff in the separate web-installer repository
    after the release hardware gates pass.
- [x] `P5.6` Publish final flash/RAM measurements.
- [x] `P5.7` Add asset-generation instructions for future patterns.
- [ ] `P5.8` Tag a release only after Plus1 and Plus2 pass; label SE support experimental until hardware validation is complete.

Release status:

- The common release and optional Plus2 regression environments both build.
- Plus v1/v1.1 and Plus2 remain validation-pending, and Plus SE remains
  experimental, in the installer metadata.
- No external installer deployment, git tag, or release publication was made;
  Plus2 hardware validation is still a required gate.

## Decisions and Alternatives

### Selected: Palette and Unique-Row Assets

This provides exact RGB565 output, approximately 8.8 KB for all eight current patterns, independent row decoding, and only a few KB of runtime scratch memory.

### Not Selected: Direct PNG Rendering

The PNG files are compact and pixel-equivalent to the current headers, but the M5GFX PNG decoder needs roughly 44–46 KB of working memory and its zoomed path does not reproduce the current PAL bilinear output exactly.

### Not Selected: RGB332 RCA Framebuffer

RGB332 would save approximately 110 KB in PAL, but it reduces colour fidelity. It should only be considered as an emergency fallback if RGB565 proves unreliable after eliminating the full-frame temporaries.

### Not Selected: SPIFFS/LittleFS as the Primary Fix

A filesystem moves assets out of the application partition but does not reduce physical flash use. It also adds a separate filesystem image and deployment step. Embedded compressed assets keep installation self-contained.

### Optional Alternative: Pre-rendered PAL Assets

If scanline bilinear scaling proves too costly, the generator can pre-render exact 384×288 PAL variants using the current algorithm. This trades additional flash for simpler firmware while retaining exact output.
