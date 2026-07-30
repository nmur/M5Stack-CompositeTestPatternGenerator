#!/usr/bin/env python3
"""Generate and verify the firmware's deterministic compressed pattern assets.

This standalone, standard-library-only tool decodes the source PNGs, composites
RGBA pixels over black, converts them to RGB565, encodes palette-indexed unique
rows, and verifies the codec round trip before emitting C++.
"""

from __future__ import annotations

import argparse
import difflib
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple

SOURCE_WIDTH = 320
SOURCE_HEIGHT = 240
CODEC_VERSION = 1
CODEC_SOLID = "SolidRgb565"
CODEC_PALETTE_RLE_ROWS = "PaletteRleRows"

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_HEADER = REPOSITORY_ROOT / "include" / "generated" / "PatternAssets.h"
DEFAULT_SOURCE = REPOSITORY_ROOT / "src" / "generated" / "PatternAssets.cpp"
PATTERNS = (
    ("colour_bars", "colour_bars.png"),
    ("grid", "grid.png"),
    ("circles", "circles.png"),
    ("gradients", "colour_gradients.png"),
    ("white", "white.png"),
    ("red", "red.png"),
    ("green", "green.png"),
    ("blue", "blue.png"),
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RgbPixel = Tuple[int, int, int, int]


class AssetGenerationError(Exception):
    """Raised for invalid input, an encoding failure, or stale generated files."""


def _paeth_predictor(left: int, above: int, upper_left: int) -> int:
    prediction = left + above - upper_left
    distance_left = abs(prediction - left)
    distance_above = abs(prediction - above)
    distance_upper_left = abs(prediction - upper_left)
    if distance_left <= distance_above and distance_left <= distance_upper_left:
        return left
    if distance_above <= distance_upper_left:
        return above
    return upper_left


def _unfilter_scanline(
    filtered: bytes,
    previous: bytes,
    bytes_per_pixel: int,
    filter_type: int,
) -> bytes:
    reconstructed = bytearray(len(filtered))
    for index, value in enumerate(filtered):
        left = reconstructed[index - bytes_per_pixel] if index >= bytes_per_pixel else 0
        above = previous[index] if previous else 0
        upper_left = (
            previous[index - bytes_per_pixel]
            if previous and index >= bytes_per_pixel
            else 0
        )

        if filter_type == 0:
            predictor = 0
        elif filter_type == 1:
            predictor = left
        elif filter_type == 2:
            predictor = above
        elif filter_type == 3:
            predictor = (left + above) // 2
        elif filter_type == 4:
            predictor = _paeth_predictor(left, above, upper_left)
        else:
            raise AssetGenerationError(
                f"unsupported PNG filter type {filter_type}"
            )

        reconstructed[index] = (value + predictor) & 0xFF
    return bytes(reconstructed)


def decode_png(path: Path) -> Tuple[int, int, List[RgbPixel]]:
    """Decode the non-interlaced, 8-bit PNG variants used by this project."""
    encoded = path.read_bytes()
    if not encoded.startswith(PNG_SIGNATURE):
        raise AssetGenerationError(f"{path}: invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = colour_type = interlace_method = None
    compressed_parts: List[bytes] = []
    saw_iend = False

    while offset < len(encoded):
        if offset + 12 > len(encoded):
            raise AssetGenerationError(f"{path}: truncated PNG chunk")
        length = struct.unpack_from(">I", encoded, offset)[0]
        chunk_type = encoded[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(encoded):
            raise AssetGenerationError(
                f"{path}: truncated {chunk_type!r} chunk"
            )

        chunk_data = encoded[data_start:data_end]
        stored_crc = struct.unpack_from(">I", encoded, data_end)[0]
        computed_crc = zlib.crc32(chunk_type)
        computed_crc = zlib.crc32(chunk_data, computed_crc) & 0xFFFFFFFF
        if computed_crc != stored_crc:
            raise AssetGenerationError(
                f"{path}: bad CRC in {chunk_type!r} chunk"
            )

        if chunk_type == b"IHDR":
            if length != 13 or width is not None:
                raise AssetGenerationError(f"{path}: invalid IHDR chunk")
            (
                width,
                height,
                bit_depth,
                colour_type,
                compression_method,
                filter_method,
                interlace_method,
            ) = struct.unpack(">IIBBBBB", chunk_data)
            if compression_method != 0 or filter_method != 0:
                raise AssetGenerationError(
                    f"{path}: unsupported PNG compression/filter method"
                )
        elif chunk_type == b"IDAT":
            compressed_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0:
                raise AssetGenerationError(f"{path}: invalid IEND chunk")
            saw_iend = True
            offset = crc_end
            break
        elif not (chunk_type[0] & 0x20):
            raise AssetGenerationError(
                f"{path}: unsupported critical chunk {chunk_type!r}"
            )

        offset = crc_end

    if width is None or not compressed_parts or not saw_iend:
        raise AssetGenerationError(f"{path}: incomplete PNG")
    if offset != len(encoded):
        raise AssetGenerationError(f"{path}: data found after IEND")
    if bit_depth != 8 or interlace_method != 0:
        raise AssetGenerationError(
            f"{path}: only non-interlaced 8-bit PNGs are supported"
        )

    channels_by_colour_type = {
        0: 1,
        2: 3,
        4: 2,
        6: 4,
    }
    if colour_type not in channels_by_colour_type:
        raise AssetGenerationError(
            f"{path}: unsupported PNG colour type {colour_type}"
        )
    bytes_per_pixel = channels_by_colour_type[colour_type]
    scanline_size = width * bytes_per_pixel

    try:
        decompressed = zlib.decompress(b"".join(compressed_parts))
    except zlib.error as error:
        raise AssetGenerationError(
            f"{path}: invalid compressed image data: {error}"
        ) from error

    expected_size = height * (scanline_size + 1)
    if len(decompressed) != expected_size:
        raise AssetGenerationError(
            f"{path}: decoded {len(decompressed)} bytes; expected {expected_size}"
        )

    pixels: List[RgbPixel] = []
    previous = b""
    scanline_offset = 0
    for _ in range(height):
        filter_type = decompressed[scanline_offset]
        filtered_start = scanline_offset + 1
        filtered_end = filtered_start + scanline_size
        scanline = _unfilter_scanline(
            decompressed[filtered_start:filtered_end],
            previous,
            bytes_per_pixel,
            filter_type,
        )
        previous = scanline
        scanline_offset = filtered_end

        for pixel_offset in range(0, scanline_size, bytes_per_pixel):
            if colour_type == 0:
                grey = scanline[pixel_offset]
                pixels.append((grey, grey, grey, 255))
            elif colour_type == 2:
                red, green, blue = scanline[pixel_offset : pixel_offset + 3]
                pixels.append((red, green, blue, 255))
            elif colour_type == 4:
                grey, alpha = scanline[pixel_offset : pixel_offset + 2]
                pixels.append((grey, grey, grey, alpha))
            else:
                red, green, blue, alpha = scanline[
                    pixel_offset : pixel_offset + 4
                ]
                pixels.append((red, green, blue, alpha))

    return width, height, pixels


def convert_to_rgb565(pixels: Iterable[RgbPixel]) -> List[int]:
    """Composite straight-alpha pixels over black and convert them to RGB565."""
    converted: List[int] = []
    for red, green, blue, alpha in pixels:
        composited_red = (red * alpha + 127) // 255
        composited_green = (green * alpha + 127) // 255
        composited_blue = (blue * alpha + 127) // 255
        converted.append(
            ((composited_red >> 3) << 11)
            | ((composited_green >> 2) << 5)
            | (composited_blue >> 3)
        )
    return converted


@dataclass(frozen=True)
class EncodedAsset:
    name: str
    symbol: str
    png_path: Path
    codec: str
    palette: Tuple[int, ...]
    row_offsets: Tuple[int, ...]
    row_data: bytes
    row_map: bytes
    source_pixels: Tuple[int, ...]

    @property
    def unique_row_count(self) -> int:
        return max(0, len(self.row_offsets) - 1)

    @property
    def payload_size(self) -> int:
        if self.codec == CODEC_SOLID:
            return len(self.palette) * 2
        return (
            len(self.palette) * 2
            + len(self.row_offsets) * 2
            + len(self.row_data)
            + len(self.row_map)
        )


def _symbol_name(pattern_name: str) -> str:
    return "k" + "".join(part.capitalize() for part in pattern_name.split("_"))


def _uleb128(value: int) -> bytes:
    if value <= 0:
        raise AssetGenerationError(f"run length must be positive, got {value}")
    encoded = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            encoded.append(byte | 0x80)
        else:
            encoded.append(byte)
            return bytes(encoded)


def _encode_row(row: Sequence[int], palette_indexes: Dict[int, int]) -> bytes:
    encoded = bytearray()
    offset = 0
    while offset < len(row):
        pixel = row[offset]
        run_end = offset + 1
        while run_end < len(row) and row[run_end] == pixel:
            run_end += 1
        encoded.append(palette_indexes[pixel])
        encoded.extend(_uleb128(run_end - offset))
        offset = run_end
    return bytes(encoded)


def encode_asset(
    name: str,
    png_path: Path,
    source_pixels: Sequence[int],
) -> EncodedAsset:
    if len(source_pixels) != SOURCE_WIDTH * SOURCE_HEIGHT:
        raise AssetGenerationError(
            f"{name}: got {len(source_pixels)} pixels; "
            f"expected {SOURCE_WIDTH * SOURCE_HEIGHT}"
        )

    palette = tuple(dict.fromkeys(source_pixels))
    if not palette or len(palette) > 256:
        raise AssetGenerationError(
            f"{name}: palette has {len(palette)} entries; format permits 1..256"
        )

    source_tuple = tuple(source_pixels)
    if len(palette) == 1:
        return EncodedAsset(
            name=name,
            symbol=_symbol_name(name),
            png_path=png_path,
            codec=CODEC_SOLID,
            palette=palette,
            row_offsets=(),
            row_data=b"",
            row_map=b"",
            source_pixels=source_tuple,
        )

    rows = [
        tuple(source_pixels[y * SOURCE_WIDTH : (y + 1) * SOURCE_WIDTH])
        for y in range(SOURCE_HEIGHT)
    ]
    unique_rows: List[Tuple[int, ...]] = []
    unique_row_indexes: Dict[Tuple[int, ...], int] = {}
    row_map = bytearray()
    for row in rows:
        row_index = unique_row_indexes.get(row)
        if row_index is None:
            row_index = len(unique_rows)
            if row_index >= 256:
                raise AssetGenerationError(
                    f"{name}: format permits at most 256 unique rows"
                )
            unique_row_indexes[row] = row_index
            unique_rows.append(row)
        row_map.append(row_index)

    palette_indexes = {pixel: index for index, pixel in enumerate(palette)}
    row_offsets = [0]
    row_data = bytearray()
    for row in unique_rows:
        row_data.extend(_encode_row(row, palette_indexes))
        if len(row_data) > 0xFFFF:
            raise AssetGenerationError(
                f"{name}: encoded rows exceed 65,535-byte offset range"
            )
        row_offsets.append(len(row_data))

    return EncodedAsset(
        name=name,
        symbol=_symbol_name(name),
        png_path=png_path,
        codec=CODEC_PALETTE_RLE_ROWS,
        palette=palette,
        row_offsets=tuple(row_offsets),
        row_data=bytes(row_data),
        row_map=bytes(row_map),
        source_pixels=source_tuple,
    )


def _decode_uleb128(data: bytes, offset: int, end: int) -> Tuple[int, int]:
    value = 0
    shift = 0
    for _ in range(3):
        if offset >= end:
            raise AssetGenerationError("truncated ULEB128 run length")
        byte = data[offset]
        offset += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            if value == 0 or value > SOURCE_WIDTH:
                raise AssetGenerationError(f"invalid decoded run length {value}")
            return value, offset
        shift += 7
    raise AssetGenerationError("ULEB128 run length is too long")


def decode_row(asset: EncodedAsset, y: int) -> List[int]:
    """Host reference decoder for the generated firmware format."""
    if y < 0 or y >= SOURCE_HEIGHT:
        raise AssetGenerationError(f"{asset.name}: row {y} is out of range")
    if asset.codec == CODEC_SOLID:
        return [asset.palette[0]] * SOURCE_WIDTH
    if asset.codec != CODEC_PALETTE_RLE_ROWS:
        raise AssetGenerationError(f"{asset.name}: unsupported codec {asset.codec}")

    unique_row_index = asset.row_map[y]
    start = asset.row_offsets[unique_row_index]
    end = asset.row_offsets[unique_row_index + 1]
    offset = start
    decoded: List[int] = []
    while offset < end:
        palette_index = asset.row_data[offset]
        offset += 1
        if palette_index >= len(asset.palette):
            raise AssetGenerationError(
                f"{asset.name}: palette index {palette_index} is out of range"
            )
        run_length, offset = _decode_uleb128(asset.row_data, offset, end)
        if len(decoded) + run_length > SOURCE_WIDTH:
            raise AssetGenerationError(f"{asset.name}: decoded row is too long")
        decoded.extend([asset.palette[palette_index]] * run_length)
    if len(decoded) != SOURCE_WIDTH:
        raise AssetGenerationError(
            f"{asset.name}: decoded row has {len(decoded)} pixels"
        )
    return decoded


def _validate_round_trip(
    asset: EncodedAsset,
) -> None:
    decoded = [
        pixel
        for y in range(SOURCE_HEIGHT)
        for pixel in decode_row(asset, y)
    ]
    if decoded != list(asset.source_pixels):
        mismatch = next(
            index
            for index, (expected, actual) in enumerate(
                zip(asset.source_pixels, decoded)
            )
            if expected != actual
        )
        raise AssetGenerationError(
            f"{asset.name}: codec round-trip mismatch at "
            f"({mismatch % SOURCE_WIDTH}, {mismatch // SOURCE_WIDTH})"
        )


def build_assets() -> List[EncodedAsset]:
    assets: List[EncodedAsset] = []
    include_directory = REPOSITORY_ROOT / "include"
    for pattern_name, png_name in PATTERNS:
        png_path = include_directory / png_name
        width, height, rgba_pixels = decode_png(png_path)
        if (width, height) != (SOURCE_WIDTH, SOURCE_HEIGHT):
            raise AssetGenerationError(
                f"{png_path}: dimensions are {width}x{height}; "
                f"expected {SOURCE_WIDTH}x{SOURCE_HEIGHT}"
            )
        source_pixels = convert_to_rgb565(rgba_pixels)
        asset = encode_asset(pattern_name, png_path, source_pixels)
        _validate_round_trip(asset)
        assets.append(asset)
    return assets


def _format_integer_array(
    c_type: str,
    name: str,
    values: Sequence[int],
    formatter,
    values_per_line: int,
) -> List[str]:
    lines = [f"const {c_type} {name}[] = {{"]
    for offset in range(0, len(values), values_per_line):
        chunk = values[offset : offset + values_per_line]
        lines.append("    " + ", ".join(formatter(value) for value in chunk) + ",")
    lines.append("};")
    return lines


def render_header(assets: Sequence[EncodedAsset]) -> str:
    prefix = """// Generated by tools/generate_pattern_assets.py. DO NOT EDIT.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace PatternAssets {

constexpr uint8_t kCodecVersion = 1;

enum class Codec : uint8_t {
    SolidRgb565 = 0,
    PaletteRleRows = 1,
};

struct Asset {
    uint16_t width;
    uint16_t height;
    uint8_t codecVersion;
    Codec codec;
    uint16_t paletteSize;
    uint16_t uniqueRowCount;
    uint32_t rowDataSize;
    uint32_t payloadSize;
    const uint16_t* palette;
    const uint16_t* rowOffsets;
    const uint8_t* rowData;
    const uint8_t* rowMap;
};
"""
    declarations = "\n".join(
        f"extern const Asset {asset.symbol};" for asset in assets
    )
    suffix = f"""

constexpr size_t kCount = {len(assets)};
extern const Asset* const kAll[kCount];

}}  // namespace PatternAssets
"""
    return prefix + "\n" + declarations + suffix


def render_source(assets: Sequence[EncodedAsset]) -> str:
    lines = [
        "// Generated by tools/generate_pattern_assets.py. DO NOT EDIT.",
        '#include "generated/PatternAssets.h"',
        "",
        "namespace PatternAssets {",
        "namespace {",
        "",
    ]

    backing_names: Dict[str, Tuple[str, str, str, str]] = {}
    for asset in assets:
        prefix = asset.symbol[1:]
        palette_name = f"k{prefix}Palette"
        offset_name = f"k{prefix}RowOffsets"
        data_name = f"k{prefix}RowData"
        map_name = f"k{prefix}RowMap"
        backing_names[asset.name] = (
            palette_name,
            offset_name,
            data_name,
            map_name,
        )
        relative_png = asset.png_path.relative_to(REPOSITORY_ROOT)
        lines.extend(
            [
                f"// {asset.name}: {relative_png}; payload {asset.payload_size} bytes.",
                *_format_integer_array(
                    "uint16_t",
                    palette_name,
                    asset.palette,
                    lambda value: f"0x{value:04x}",
                    12,
                ),
            ]
        )
        if asset.codec == CODEC_PALETTE_RLE_ROWS:
            lines.extend(
                [
                    *_format_integer_array(
                        "uint16_t",
                        offset_name,
                        asset.row_offsets,
                        str,
                        12,
                    ),
                    *_format_integer_array(
                        "uint8_t",
                        data_name,
                        asset.row_data,
                        lambda value: f"0x{value:02x}",
                        16,
                    ),
                    *_format_integer_array(
                        "uint8_t",
                        map_name,
                        asset.row_map,
                        str,
                        20,
                    ),
                ]
            )
        lines.append("")

    lines.extend(["}  // namespace", ""])
    for asset in assets:
        palette_name, offset_name, data_name, map_name = backing_names[asset.name]
        if asset.codec == CODEC_SOLID:
            offsets_pointer = data_pointer = map_pointer = "nullptr"
        else:
            offsets_pointer = offset_name
            data_pointer = data_name
            map_pointer = map_name
        lines.extend(
            [
                f"const Asset {asset.symbol} = {{",
                f"    {SOURCE_WIDTH},",
                f"    {SOURCE_HEIGHT},",
                "    kCodecVersion,",
                f"    Codec::{asset.codec},",
                f"    {len(asset.palette)},",
                f"    {asset.unique_row_count},",
                f"    {len(asset.row_data)},",
                f"    {asset.payload_size},",
                f"    {palette_name},",
                f"    {offsets_pointer},",
                f"    {data_pointer},",
                f"    {map_pointer},",
                "};",
                "",
            ]
        )

    lines.append("const Asset* const kAll[kCount] = {")
    lines.append("    " + ", ".join(f"&{asset.symbol}" for asset in assets) + ",")
    lines.extend(["};", "", "}  // namespace PatternAssets", ""])
    return "\n".join(lines)


def _relative_label(path: Path) -> str:
    try:
        return str(path.relative_to(REPOSITORY_ROOT))
    except ValueError:
        return str(path)


def _check_file(path: Path, expected: str) -> bool:
    try:
        actual = path.read_text()
    except FileNotFoundError:
        print(f"STALE: {_relative_label(path)} is missing", file=sys.stderr)
        return False
    if actual == expected:
        return True
    print(f"STALE: {_relative_label(path)} differs from generator output", file=sys.stderr)
    difference = difflib.unified_diff(
        actual.splitlines(),
        expected.splitlines(),
        fromfile=_relative_label(path),
        tofile=f"{_relative_label(path)} (regenerated)",
        lineterm="",
    )
    for line in list(difference)[:80]:
        print(line, file=sys.stderr)
    return False


def _print_summary(assets: Sequence[EncodedAsset]) -> None:
    print("Pattern asset payloads:")
    for asset in assets:
        print(
            f"  {asset.name:12} {asset.payload_size:5} B  "
            f"palette={len(asset.palette):3}  rows={asset.unique_row_count:3}  "
            f"codec={asset.codec}"
        )
    print(f"  {'TOTAL':12} {sum(asset.payload_size for asset in assets):5} B")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="verify generated files are fresh (the default)",
    )
    mode.add_argument(
        "--write",
        action="store_true",
        help="regenerate the tracked C++ header and source",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        assets = build_assets()
        header = render_header(assets)
        source = render_source(assets)
        if arguments.write:
            DEFAULT_HEADER.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_SOURCE.parent.mkdir(parents=True, exist_ok=True)
            DEFAULT_HEADER.write_text(header)
            DEFAULT_SOURCE.write_text(source)
            print(f"Wrote {_relative_label(DEFAULT_HEADER)}")
            print(f"Wrote {_relative_label(DEFAULT_SOURCE)}")
        else:
            files_are_fresh = all(
                (
                    _check_file(DEFAULT_HEADER, header),
                    _check_file(DEFAULT_SOURCE, source),
                )
            )
            if not files_are_fresh:
                print(
                    "\nRun `python3 tools/generate_pattern_assets.py --write` "
                    "and review the generated changes.",
                    file=sys.stderr,
                )
                return 1
            print("Generated pattern assets are fresh.")
        print(f"Decoded all {len(assets)} assets exactly.")
        _print_summary(assets)
        return 0
    except (AssetGenerationError, OSError, ValueError) as error:
        print(f"Pattern asset generation ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
