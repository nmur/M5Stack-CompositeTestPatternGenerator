# Pattern asset format

The PNG files under `include/` are the editable source of truth. Run:

```sh
python3 tools/generate_pattern_assets.py --write
```

to regenerate `include/generated/PatternAssets.h` and
`src/generated/PatternAssets.cpp`. Running the tool with no arguments (or with
`--check`) validates every codec round trip, checks any legacy RGB565 headers
still present, and fails if either generated file is stale.

## Pixel conversion

The generator accepts the non-interlaced, 8-bit PNG colour types supported by
the golden-output verifier. Each straight-alpha channel is composited over
black with:

```text
composited = (channel * alpha + 127) / 255
```

using integer division. The composited channels are then truncated to RGB565:

```text
((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
```

Seven current PNGs are opaque. `circles.png` uses binary alpha, and every fully
transparent pixel already has black RGB channels. Compositing therefore remains
byte-for-byte identical to all eight legacy headers.

## Metadata

Format version 1 is represented by `PatternAssets::Asset`:

| Field | Meaning |
|---|---|
| `width`, `height` | Decoded dimensions in pixels |
| `codecVersion` | Must equal `PatternAssets::kCodecVersion` |
| `codec` | Solid RGB565 or palette/RLE unique rows |
| `paletteSize` | Number of RGB565 entries, from 1 through 256 |
| `uniqueRowCount` | Number of entries in the unique-row dictionary |
| `rowDataSize` | Byte length of the encoded unique-row stream |
| `payloadSize` | Palette, offsets, row stream, and row-map bytes |
| `decodedCrc32` | CRC32 of row-major, little-endian RGB565 pixels |
| `palette` | RGB565 values in first-pixel-appearance order |
| `rowOffsets` | `uniqueRowCount + 1` offsets into `rowData` |
| `rowData` | Concatenated encoded unique rows |
| `rowMap` | `height` byte indexes into the unique-row dictionary |

`payloadSize` excludes the fixed metadata structure and compiler alignment. It
is exactly:

```text
paletteSize * 2
  + (uniqueRowCount + 1) * 2
  + rowDataSize
  + height
```

for palette/RLE assets.

## Palette/RLE unique rows

Rows are deduplicated in first-source-row order. `rowMap[y]` selects a unique
row, whose half-open encoded range is:

```text
rowData[rowOffsets[index] : rowOffsets[index + 1]]
```

Each run is a one-byte palette index followed by a positive ULEB128 run length.
Runs must decode to exactly `width` pixels and end exactly at the next row
offset. Version 1 uses 16-bit offsets, byte row indexes, and therefore permits
at most 65,535 encoded row bytes and 256 unique rows per asset.

## Solid assets

A single-colour image uses `Codec::SolidRgb565`. Its palette contains exactly
one value; its row count and row-data size are zero; and its row offsets, row
data, and row map are null. Its payload size is two bytes.

## Firmware decoder

`decodePatternRow()` in `PatternDecoder.h` writes into caller-owned storage and
performs no heap allocation. The caller supplies the destination capacity in
pixels. It validates the codec/version, dimensions, payload accounting,
pointers, row indexes, offsets, palette indexes, ULEB128 lengths, decoded
width, and trailing data. It returns a `PatternDecodeResult`;
`patternDecodeResultMessage()` provides a stable diagnostic string.

The decoder can also be compiled and exercised without the embedded toolchain:

```sh
c++ -std=c++11 -Wall -Wextra -Werror -Iinclude \
  tools/test_pattern_decoder.cpp src/PatternDecoder.cpp \
  src/generated/PatternAssets.cpp -o /tmp/test_pattern_decoder
/tmp/test_pattern_decoder
```
