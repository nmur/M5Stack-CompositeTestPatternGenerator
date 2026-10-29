# Pattern asset format

The PNG files are the editable source of truth for two independent native
image sets:

- `include/*.png`: the existing 320×240 NTSC artwork.
- `include/pal/*.png`: 384×288 PAL artwork.

Each selectable pattern has an NTSC and a PAL asset. The firmware selects
the asset for the active video format and decodes it directly to the RCA
framebuffer, without resizing or interpolating the video image.

Run:

```sh
python3 tools/generate_pattern_assets.py --write
```

to regenerate `include/generated/PatternAssets.h` and
`src/generated/PatternAssets.cpp`. Running the tool with no arguments (or with
`--check`) validates every codec round trip and fails if either generated file
is stale. The generator checks the dimensions for both sets and emits sixteen
assets in eight NTSC/PAL pairs; `PatternAssets::kCount` counts selectable
patterns, not the total number of images.

## Native PAL artwork

Generate and check the PAL source images with the standard-library-only tool:

```sh
python3 tools/generate_pal_patterns.py --write
python3 tools/generate_pal_patterns.py --check
python3 tools/generate_pattern_assets.py --write
```

The PAL generator draws the pattern geometry at its target dimensions rather
than enlarging the NTSC bitmap:

- The grid has 24×18 cells with 16-pixel spacing, two-pixel interior lines,
  2×2 centre dots, and a red outer cell border. NTSC retains its 20×15 cells.
- Colour bars use the source colours and section layout with sharp native
  boundaries.
- Circle outlines are rasterised directly, using the existing artwork's
  proportions and arrangement with symmetric placement. The outlines contain
  only black and white pixels.
- Each gradient has 32 equal nine-pixel steps. Its four bands are 40 pixels
  high with eight-pixel gaps; labels are copied from the original bitmap font
  without interpolation.
- Solid-colour images retain the original colours and encode as two-byte
  palette payloads for each format.

The source NTSC images remain editable independently. Regenerate the PAL
artwork and compressed assets after changing a source used by the PAL
generator. Exact regenerated PNG bytes are checked to detect stale artwork.

## Rendering and preview

`ScanlineRenderer::RenderNative()` accepts dimensions from the selected asset
and sends complete rows unchanged to the output. The decoder and renderer
perform no heap allocation; their shared scratch storage is 1,088 bytes.
The framebuffer allocation and video driver configuration remain 320×240
for NTSC and 384×288 for PAL.

The 160×120 LCD preview samples the selected format's asset, using integer
nearest-neighbour coordinates. Scaling is confined to the LCD preview.

Run the standalone host renderer checks with:

```sh
sh tools/test_scanline_renderer.sh
```

Native assets remove firmware interpolation artefacts. Horizontal pixel
expansion inside the composite driver is a separate stage and is unaffected
by this change; final geometry and appearance still need a CRT comparison.

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
