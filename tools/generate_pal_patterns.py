#!/usr/bin/env python3
"""Create deterministic 384x288 PAL artwork without resizing a bitmap.

The existing 320x240 NTSC PNGs remain the reference artwork. PAL grids and
ellipse outlines are rasterised on their own pixel lattice; bars are recreated
as rectangles at integer boundaries. Gradients have equal-width intensity
steps and retain the original small pixel-font glyphs at their native size.
Only the Python standard library is required.
"""

from __future__ import annotations

import argparse
import struct
import sys
import zlib
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple

from generate_pattern_assets import (
    AssetGenerationError,
    convert_to_rgb565,
    decode_png,
)

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
SOURCE_WIDTH = 320
SOURCE_HEIGHT = 240
WIDTH = 384
HEIGHT = 288
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

Rgb = Tuple[int, int, int]
Image = List[Rgb]
BLACK: Rgb = (0, 0, 0)
WHITE: Rgb = (255, 255, 255)
RED: Rgb = (255, 0, 0)
GREEN: Rgb = (0, 255, 0)
BLUE: Rgb = (0, 0, 255)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    checksum = zlib.crc32(kind)
    checksum = zlib.crc32(data, checksum) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", checksum)


def encode_png(pixels: Sequence[Rgb]) -> bytes:
    """Write opaque RGB PNGs with no timestamps, metadata, or optional filters."""
    if len(pixels) != WIDTH * HEIGHT:
        raise AssetGenerationError("wrong pixel count for PAL artwork")
    scanlines = bytearray()
    for y in range(HEIGHT):
        scanlines.append(0)
        for pixel in pixels[y * WIDTH : (y + 1) * WIDTH]:
            scanlines.extend(pixel)
    return b"".join(
        (
            PNG_SIGNATURE,
            png_chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)),
            png_chunk(b"IDAT", zlib.compress(bytes(scanlines), level=9)),
            png_chunk(b"IEND", b""),
        )
    )


def source_image(source_directory: Path, filename: str) -> Image:
    width, height, rgba = decode_png(source_directory / filename)
    if (width, height) != (SOURCE_WIDTH, SOURCE_HEIGHT):
        raise AssetGenerationError(
            f"{filename}: expected {SOURCE_WIDTH}x{SOURCE_HEIGHT} reference artwork"
        )
    return [
        tuple((channel * alpha + 127) // 255 for channel in (red, green, blue))
        for red, green, blue, alpha in rgba
    ]


def fill_rectangle(
    pixels: Image, x0: int, y0: int, x1: int, y1: int, colour: Rgb
) -> None:
    if not (0 <= x0 <= x1 <= WIDTH and 0 <= y0 <= y1 <= HEIGHT):
        raise AssetGenerationError("rectangle outside PAL artwork")
    for y in range(y0, y1):
        pixels[y * WIDTH + x0 : y * WIDTH + x1] = [colour] * (x1 - x0)


def rounded_boundary(coordinate: int, target_size: int, source_size: int) -> int:
    """Round rectangle boundaries once, using integer arithmetic and half-up ties."""
    return (coordinate * target_size * 2 + source_size) // (2 * source_size)


def colour_bars(source: Image) -> Image:
    """Rebuild all three source bar sections with sharp, snapped boundaries.

    The source sections start at rows 0, 160, and 180; their PAL equivalents
    are 0, 192, and 216. Each section keeps its own measured colour-run widths,
    including the narrow black-level reference patches in the bottom section.
    No interpolated pixels are introduced at section or colour boundaries.
    """
    pixels = [BLACK] * (WIDTH * HEIGHT)
    y0 = 0
    while y0 < SOURCE_HEIGHT:
        reference_row = source[y0 * SOURCE_WIDTH : (y0 + 1) * SOURCE_WIDTH]
        y1 = y0 + 1
        while y1 < SOURCE_HEIGHT:
            if source[y1 * SOURCE_WIDTH : (y1 + 1) * SOURCE_WIDTH] != reference_row:
                break
            y1 += 1
        x0 = 0
        while x0 < SOURCE_WIDTH:
            colour = reference_row[x0]
            x1 = x0 + 1
            while x1 < SOURCE_WIDTH and reference_row[x1] == colour:
                x1 += 1
            fill_rectangle(
                pixels,
                rounded_boundary(x0, WIDTH, SOURCE_WIDTH),
                rounded_boundary(y0, HEIGHT, SOURCE_HEIGHT),
                rounded_boundary(x1, WIDTH, SOURCE_WIDTH),
                rounded_boundary(y1, HEIGHT, SOURCE_HEIGHT),
                colour,
            )
            x0 = x1
        y0 = y1
    return pixels


def grid() -> Image:
    """Draw 24x18 cells, with uniform 16-pixel spacing and two-pixel strokes.

    Each internal boundary occupies the pixel immediately before and after
    a multiple of 16. Screen edges clip that stroke to one pixel, matching
    the NTSC pattern. Every cell has a two-by-two centre dot; the outermost
    row/column of cells is red and the remaining cells are white.
    """
    cell_size = 16
    pixels = [BLACK] * (WIDTH * HEIGHT)
    for y in range(HEIGHT):
        for x in range(WIDTH):
            line = x % cell_size in (0, 15) or y % cell_size in (0, 15)
            dot = x % cell_size in (7, 8) and y % cell_size in (7, 8)
            if line or dot:
                outer_cell = (
                    x < cell_size
                    or x >= WIDTH - cell_size
                    or y < cell_size
                    or y >= HEIGHT - cell_size
                )
                pixels[y * WIDTH + x] = RED if outer_cell else WHITE
    return pixels


def ellipse_outline(
    pixels: Image, centre_x2: int, centre_y2: int, radius_x2: int, radius_y2: int
) -> None:
    """Draw the one-pixel inside boundary of an ellipse using exact integers.

    All coordinates are doubled, so half-pixel centres and radii can be used
    without floating-point rounding. Removing pixels whose four neighbours
    are inside the ellipse leaves a sharp outline with exact mirror symmetry.
    """
    squared_x = radius_x2 * radius_x2
    squared_y = radius_y2 * radius_y2
    limit = squared_x * squared_y

    def inside(x: int, y: int) -> bool:
        dx = 2 * x - centre_x2
        dy = 2 * y - centre_y2
        return dx * dx * squared_y + dy * dy * squared_x <= limit

    x0 = max(0, (centre_x2 - radius_x2) // 2)
    x1 = min(WIDTH - 1, (centre_x2 + radius_x2 + 1) // 2)
    y0 = max(0, (centre_y2 - radius_y2) // 2)
    y1 = min(HEIGHT - 1, (centre_y2 + radius_y2 + 1) // 2)
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            if inside(x, y) and not all(
                inside(nx, ny)
                for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1))
            ):
                pixels[y * WIDTH + x] = WHITE


def circles() -> Image:
    """Reconstruct the central ellipse and four smaller corner ellipses.

    The reference's central outline spans about 250x228 pixels: it is an
    ellipse in the framebuffer, so PAL retains that intended ratio with
    radii 150x137. The corner outlines span about 60x56 reference pixels;
    PAL uses radii 35.5x33. Their placement preserves the reference margins
    after snapping to the native grid. Unlike small offsets in the reference,
    both axes of the reconstructed pattern are exactly mirror symmetric.
    """
    pixels = [BLACK] * (WIDTH * HEIGHT)
    ellipse_outline(pixels, WIDTH - 1, HEIGHT - 1, 300, 274)
    for centre_x2 in (81, 2 * (WIDTH - 1) - 81):
        for centre_y2 in (75, 2 * (HEIGHT - 1) - 75):
            ellipse_outline(pixels, centre_x2, centre_y2, 71, 66)
    return pixels


def copy_glyph(
    pixels: Image,
    source: Image,
    source_x: int,
    source_y: int,
    glyph_width: int,
    glyph_height: int,
    target_x: int,
    target_y: int,
) -> None:
    """Position the existing pixel-font glyphs without enlarging their raster."""
    for y in range(glyph_height):
        for x in range(glyph_width):
            colour = source[(source_y + y) * SOURCE_WIDTH + source_x + x]
            if colour != BLACK:
                pixels[(target_y + y) * WIDTH + target_x + x] = colour


def gradients(source: Image) -> Image:
    """Draw four bands with uniform nine-pixel steps and unchanged intensities.

    The original contains 32 eight-pixel intensity steps starting at x=53.
    PAL uses 32 nine-pixel steps at x=64..351, leaving a 32-pixel right margin.
    Bands are 40 pixels high, separated by eight black rows. This deliberate
    layout change avoids alternating nine/ten-pixel step widths. The original
    seven-pixel-high name and hexadecimal glyphs are repositioned unchanged.
    """
    pixels = [BLACK] * (WIDTH * HEIGHT)
    band_x = 64
    step_width = 9
    for band_index, source_y in enumerate((40, 80, 120, 160)):
        target_y = 48 + band_index * 48
        for step in range(32):
            colour = source[source_y * SOURCE_WIDTH + 53 + step * 8]
            fill_rectangle(
                pixels,
                band_x + step * step_width,
                target_y,
                band_x + (step + 1) * step_width,
                target_y + 40,
                colour,
            )
        # Keep the original font and ten-pixel gap after the rightmost glyph.
        copy_glyph(pixels, source, 0, source_y, 53, 7, 9, target_y)
    for index in range(16):
        # Each hexadecimal label is centred over a pair of intensity steps.
        copy_glyph(pixels, source, 61 + index * 16, 32, 8, 7, 69 + index * 18, 40)
    return pixels


def check_codec_limits(filename: str, pixels: Sequence[Rgb]) -> Tuple[int, int]:
    rgba = ((red, green, blue, 255) for red, green, blue in pixels)
    rgb565 = convert_to_rgb565(rgba)
    palette_count = len(set(rgb565))
    unique_rows = len(
        {tuple(rgb565[y * WIDTH : (y + 1) * WIDTH]) for y in range(HEIGHT)}
    )
    if palette_count > 256 or unique_rows > 256:
        raise AssetGenerationError(
            f"{filename}: exceeds the codec's 256 colours/unique rows "
            f"({palette_count} colours, {unique_rows} rows)"
        )
    return palette_count, unique_rows


def generate(source_directory: Path) -> Iterable[Tuple[str, Image]]:
    yield "colour_bars.png", colour_bars(source_image(source_directory, "colour_bars.png"))
    yield "grid.png", grid()
    yield "circles.png", circles()
    yield "colour_gradients.png", gradients(
        source_image(source_directory, "colour_gradients.png")
    )
    for filename, colour in (
        ("white.png", WHITE),
        ("red.png", RED),
        ("green.png", GREEN),
        ("blue.png", BLUE),
    ):
        yield filename, [colour] * (WIDTH * HEIGHT)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="write native PAL PNGs")
    mode.add_argument("--check", action="store_true", help="verify checked-in PNGs are current")
    parser.add_argument("--source-dir", type=Path, default=REPOSITORY_ROOT / "include")
    parser.add_argument("--output-dir", type=Path, default=REPOSITORY_ROOT / "include" / "pal")
    arguments = parser.parse_args()
    try:
        if arguments.write:
            arguments.output_dir.mkdir(parents=True, exist_ok=True)
        for filename, pixels in generate(arguments.source_dir):
            palette_count, unique_rows = check_codec_limits(filename, pixels)
            encoded = encode_png(pixels)
            target = arguments.output_dir / filename
            if arguments.write:
                target.write_bytes(encoded)
            elif not target.exists() or target.read_bytes() != encoded:
                raise AssetGenerationError(f"{target}: stale or missing; run --write")
            print(
                f"{filename}: {WIDTH}x{HEIGHT}, {palette_count} RGB565 colours, "
                f"{unique_rows} unique rows, {len(encoded)} PNG bytes"
            )
    except (AssetGenerationError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
