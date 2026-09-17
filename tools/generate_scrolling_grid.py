#!/usr/bin/env python3
"""Generate the white, dotless scrolling grid from the static grid PNG."""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from typing import Iterable, Tuple

from generate_pattern_assets import PNG_SIGNATURE, RgbPixel, decode_png


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_PATH = REPOSITORY_ROOT / "include" / "grid.png"
OUTPUT_PATH = REPOSITORY_ROOT / "include" / "scrolling_grid.png"
RED: RgbPixel = (255, 0, 0, 255)
WHITE: RgbPixel = (255, 255, 255, 255)
BLACK: RgbPixel = (0, 0, 0, 255)
GRID_SPACING = 16
DOT_OFFSETS = (7, 8)


def _png_chunk(chunk_type: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(chunk_type)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", checksum)


def encode_rgba_png(width: int, height: int, pixels: Iterable[RgbPixel]) -> bytes:
    pixel_list = list(pixels)
    if len(pixel_list) != width * height:
        raise ValueError("pixel count does not match the image dimensions")

    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)  # PNG filter: None
        for pixel in pixel_list[y * width : (y + 1) * width]:
            scanlines.extend(pixel)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    return b"".join(
        (
            PNG_SIGNATURE,
            _png_chunk(b"IHDR", ihdr),
            _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)),
            _png_chunk(b"IEND", b""),
        )
    )


def build_scrolling_grid() -> Tuple[bytes, int, int]:
    width, height, source_pixels = decode_png(SOURCE_PATH)
    output_pixels = []
    removed_dot_pixels = 0
    for index, pixel in enumerate(source_pixels):
        x = index % width
        y = index // width
        is_dot = (
            x % GRID_SPACING in DOT_OFFSETS
            and y % GRID_SPACING in DOT_OFFSETS
        )
        if is_dot:
            if pixel not in (RED, WHITE):
                raise ValueError(f"expected a dot pixel at ({x}, {y})")
            output_pixels.append(BLACK)
            removed_dot_pixels += 1
        else:
            output_pixels.append(WHITE if pixel == RED else pixel)

    replaced_pixels = sum(pixel == RED for pixel in source_pixels)
    if replaced_pixels == 0:
        raise ValueError("the source grid contains no opaque red pixels")
    expected_dot_pixels = (width // GRID_SPACING) * (height // GRID_SPACING) * 4
    if removed_dot_pixels != expected_dot_pixels:
        raise ValueError(
            f"removed {removed_dot_pixels} dot pixels; expected {expected_dot_pixels}"
        )
    if any(pixel not in (BLACK, WHITE) for pixel in output_pixels):
        raise ValueError("the generated grid contains a colour other than black or white")
    return (
        encode_rgba_png(width, height, output_pixels),
        replaced_pixels,
        removed_dot_pixels,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="write the derived PNG instead of only checking it",
    )
    arguments = parser.parse_args()

    expected, replaced_pixels, removed_dot_pixels = build_scrolling_grid()
    if arguments.write:
        OUTPUT_PATH.write_bytes(expected)
        print(f"Wrote {OUTPUT_PATH.relative_to(REPOSITORY_ROOT)}")
    elif not OUTPUT_PATH.exists() or OUTPUT_PATH.read_bytes() != expected:
        print(
            f"STALE: {OUTPUT_PATH.relative_to(REPOSITORY_ROOT)} differs from generator output",
            file=sys.stderr,
        )
        return 1

    print(
        f"Verified {replaced_pixels} red pixels changed to white and "
        f"{removed_dot_pixels} center-dot pixels removed"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
