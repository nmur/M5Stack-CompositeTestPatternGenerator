# Pattern asset format

The 320×240 PNG files under `include/` are the editable source of truth. Run:

```sh
python3 tools/generate_pattern_assets.py --write
```

to regenerate `include/generated/PatternAssets.h` and
`src/generated/PatternAssets.cpp`. Running the tool with no arguments (or with
`--check`) validates every codec round trip and fails if either generated file
is stale.

`include/scrolling_grid.png` is derived from `include/grid.png`, with its red
border pixels changed to white. Regenerate and verify it with:

```sh
python3 tools/generate_scrolling_grid.py --write
python3 tools/generate_scrolling_grid.py
```

## Pixel conversion

The standalone generator accepts non-interlaced, 8-bit grayscale, RGB,
grayscale-alpha, and RGBA PNG files. Each straight-alpha channel is composited
over black using integer arithmetic:

```text
composited = (channel * alpha + 127) / 255
```

The composited channels are then truncated to RGB565:

```text
((red >> 3) << 11) | ((green >> 2) << 5) | (blue >> 3)
```

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
| `palette` | RGB565 values in first-pixel-appearance order |
| `rowOffsets` | `uniqueRowCount + 1` offsets into `rowData` |
| `rowData` | Concatenated encoded unique rows |
| `rowMap` | `height` byte indexes into the unique-row dictionary |

For palette/RLE assets, `payloadSize` is:

```text
paletteSize * 2
  + (uniqueRowCount + 1) * 2
  + rowDataSize
  + height
```

## Palette/RLE unique rows

Rows are deduplicated in first-source-row order. `rowMap[y]` selects a unique
row, whose half-open encoded range is:

```text
rowData[rowOffsets[index] : rowOffsets[index + 1]]
```

Each run is a one-byte palette index followed by a positive ULEB128 run length.
Runs must decode to exactly `width` pixels and end at the next row offset.
Version 1 uses 16-bit offsets and byte row indexes, allowing at most 65,535
encoded row bytes and 256 unique rows per asset.

## Solid assets

A single-colour image uses `Codec::SolidRgb565`. Its palette contains one
value; its row count and row-data size are zero; and its row offsets, row data,
and row map are null. Its payload size is two bytes.

## Firmware decoder

`decodePatternRow()` writes into caller-owned storage and performs no heap
allocation. The caller supplies the destination capacity in pixels. The
decoder validates the codec and version, dimensions, payload accounting,
pointers, row indexes, offsets, palette indexes, ULEB128 lengths, decoded
width, and trailing data.
