# Pattern asset and rendering tools

Run the complete native firmware-pipeline verification from the repository
root:

```sh
python3 tools/verify_firmware_pipeline.py
```

This compiles the actual C++ asset decoder, row scaler, and scanline renderer
with the host C++ compiler. It verifies decoder error handling and compares all
eight patterns in NTSC, LCD-preview, and PAL form against the 24 tracked
SHA-256 hashes.

## Generated assets

PNG files under `include/` are the editable pattern sources. Regenerate the
compressed C++ assets with:

```sh
python3 tools/generate_pattern_assets.py --write
```

Check codec round trips and generated-file freshness without writing:

```sh
python3 tools/generate_pattern_assets.py --check
```

PlatformIO runs this freshness check before every firmware build.

## Golden-output reference

Run this command from the repository root:

```sh
python3 tools/verify_golden_outputs.py
```

The verifier has no third-party dependencies. It performs four checks for all
eight patterns:

1. Decodes the source PNG with a small standard-library-only PNG decoder.
2. Converts each pixel to the same RGB565 value stored in the legacy header.
3. Reproduces the current 160×120 preview sampling and the current 384×288
   16.16 fixed-point PAL bilinear scaler.
4. SHA-256 checks the NTSC, preview, and PAL byte streams against
   `test/golden_outputs.sha256.json`.

Hashes use row-major RGB565 pixels encoded as little-endian 16-bit words, which
matches their representation on the ESP32. Pixels are composited over black
before RGB565 conversion. Any legacy raw C++ headers still present are checked
as an additional migration safeguard.

To regenerate a candidate manifest without modifying tracked files:

```sh
python3 tools/verify_golden_outputs.py --emit-manifest > /tmp/golden_outputs.sha256.json
diff -u test/golden_outputs.sha256.json /tmp/golden_outputs.sha256.json
```

Treat a changed hash as a rendering change: inspect and approve it deliberately
before replacing the tracked manifest.

Use `--require-legacy-headers` only when auditing a revision from before the
compressed assets replaced those headers.
