#!/usr/bin/env python3
"""Generate or verify deterministic RGB565 golden-output hashes.

This script intentionally uses only the Python standard library.  It decodes
the project's PNG sources, checks their RGB565 pixels against the legacy C++
headers when those headers are present, and reproduces the current preview and
PAL scaling algorithms from src/ImageScaler.cpp.

The hash input is the byte representation used by the ESP32: row-major RGB565
pixels serialized as little-endian uint16_t values.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import zlib
from pathlib import Path
from typing import Dict, Iterable, List, Sequence, Tuple


SOURCE_WIDTH = 320
SOURCE_HEIGHT = 240
PREVIEW_WIDTH = 160
PREVIEW_HEIGHT = 120
PAL_WIDTH = 384
PAL_HEIGHT = 288

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPOSITORY_ROOT / "test" / "golden_outputs.sha256.json"

# The gradients header and source PNG have different historical names.
PATTERNS = (
    ("colour_bars", "colour_bars.png", "colour_bars.h"),
    ("grid", "grid.png", "grid.h"),
    ("circles", "circles.png", "circles.h"),
    ("gradients", "colour_gradients.png", "gradients.h"),
    ("white", "white.png", "white.h"),
    ("red", "red.png", "red.h"),
    ("green", "green.png", "green.h"),
    ("blue", "blue.png", "blue.h"),
)

OUTPUT_SPECS = (
    ("ntsc_320x240", SOURCE_WIDTH, SOURCE_HEIGHT),
    ("preview_160x120", PREVIEW_WIDTH, PREVIEW_HEIGHT),
    ("pal_384x288", PAL_WIDTH, PAL_HEIGHT),
)

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
HEX_WORD = re.compile(r"0x([0-9a-fA-F]{4})")

RgbPixel = Tuple[int, int, int, int]
BilinearCoordinate = Tuple[int, int, int, int]


class GoldenOutputError(Exception):
    """Raised for malformed source data or a reference mismatch."""


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
            raise GoldenOutputError(f"unsupported PNG filter type {filter_type}")

        reconstructed[index] = (value + predictor) & 0xFF
    return bytes(reconstructed)


def decode_png(path: Path) -> Tuple[int, int, List[RgbPixel]]:
    """Decode the non-interlaced, 8-bit PNG variants used by this project."""
    encoded = path.read_bytes()
    if not encoded.startswith(PNG_SIGNATURE):
        raise GoldenOutputError(f"{path}: invalid PNG signature")

    offset = len(PNG_SIGNATURE)
    width = height = bit_depth = colour_type = interlace_method = None
    compressed_parts: List[bytes] = []
    saw_iend = False

    while offset < len(encoded):
        if offset + 12 > len(encoded):
            raise GoldenOutputError(f"{path}: truncated PNG chunk")
        length = struct.unpack_from(">I", encoded, offset)[0]
        chunk_type = encoded[offset + 4 : offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(encoded):
            raise GoldenOutputError(f"{path}: truncated {chunk_type!r} chunk")

        chunk_data = encoded[data_start:data_end]
        stored_crc = struct.unpack_from(">I", encoded, data_end)[0]
        computed_crc = zlib.crc32(chunk_type)
        computed_crc = zlib.crc32(chunk_data, computed_crc) & 0xFFFFFFFF
        if computed_crc != stored_crc:
            raise GoldenOutputError(f"{path}: bad CRC in {chunk_type!r} chunk")

        if chunk_type == b"IHDR":
            if length != 13 or width is not None:
                raise GoldenOutputError(f"{path}: invalid IHDR chunk")
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
                raise GoldenOutputError(f"{path}: unsupported PNG compression/filter method")
        elif chunk_type == b"IDAT":
            compressed_parts.append(chunk_data)
        elif chunk_type == b"IEND":
            if length != 0:
                raise GoldenOutputError(f"{path}: invalid IEND chunk")
            saw_iend = True
            offset = crc_end
            break
        elif not (chunk_type[0] & 0x20):
            raise GoldenOutputError(f"{path}: unsupported critical chunk {chunk_type!r}")

        offset = crc_end

    if width is None or not compressed_parts or not saw_iend:
        raise GoldenOutputError(f"{path}: incomplete PNG")
    if offset != len(encoded):
        raise GoldenOutputError(f"{path}: data found after IEND")
    if bit_depth != 8 or interlace_method != 0:
        raise GoldenOutputError(f"{path}: only non-interlaced 8-bit PNGs are supported")

    channels_by_colour_type = {
        0: 1,  # grayscale
        2: 3,  # RGB
        4: 2,  # grayscale + alpha
        6: 4,  # RGBA
    }
    if colour_type not in channels_by_colour_type:
        raise GoldenOutputError(f"{path}: unsupported PNG colour type {colour_type}")
    bytes_per_pixel = channels_by_colour_type[colour_type]
    scanline_size = width * bytes_per_pixel

    try:
        decompressed = zlib.decompress(b"".join(compressed_parts))
    except zlib.error as error:
        raise GoldenOutputError(f"{path}: invalid compressed image data: {error}") from error

    expected_size = height * (scanline_size + 1)
    if len(decompressed) != expected_size:
        raise GoldenOutputError(
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
                red, green, blue, alpha = scanline[pixel_offset : pixel_offset + 4]
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


def read_legacy_header(path: Path) -> List[int]:
    words = [int(match, 16) for match in HEX_WORD.findall(path.read_text())]
    expected_words = SOURCE_WIDTH * SOURCE_HEIGHT
    if len(words) != expected_words:
        raise GoldenOutputError(
            f"{path}: found {len(words)} RGB565 words; expected {expected_words}"
        )
    return words


def render_preview(source: Sequence[int]) -> List[int]:
    return [
        source[row * SOURCE_WIDTH + column]
        for row in range(0, SOURCE_HEIGHT, 2)
        for column in range(0, SOURCE_WIDTH, 2)
    ]


def _fixed_point_scale(source_size: int, destination_size: int) -> int:
    return ((source_size - 1) << 16) // (destination_size - 1)


def _bilinear_coordinate(
    destination_index: int,
    fixed_point_scale: int,
    source_size: int,
) -> BilinearCoordinate:
    fixed_point_position = destination_index * fixed_point_scale
    lower_index = fixed_point_position >> 16
    upper_index = lower_index + 1 if lower_index < source_size - 1 else lower_index
    upper_weight = fixed_point_position & 0xFFFF
    lower_weight = 65536 - upper_weight
    return lower_index, upper_index, lower_weight, upper_weight


def _blend_rgb565(
    top_left: int,
    top_right: int,
    bottom_left: int,
    bottom_right: int,
    horizontal: BilinearCoordinate,
    vertical: BilinearCoordinate,
) -> int:
    horizontal_lower_weight = horizontal[2]
    horizontal_upper_weight = horizontal[3]
    vertical_lower_weight = vertical[2]
    vertical_upper_weight = vertical[3]

    top_left_weight = (horizontal_lower_weight * vertical_lower_weight) >> 16
    top_right_weight = (horizontal_upper_weight * vertical_lower_weight) >> 16
    bottom_left_weight = (horizontal_lower_weight * vertical_upper_weight) >> 16
    bottom_right_weight = (horizontal_upper_weight * vertical_upper_weight) >> 16

    weights = (
        top_left_weight,
        top_right_weight,
        bottom_left_weight,
        bottom_right_weight,
    )
    neighbors = (top_left, top_right, bottom_left, bottom_right)

    def blend(shift: int, mask: int) -> int:
        weighted_sum = sum(
            ((pixel >> shift) & mask) * weight
            for pixel, weight in zip(neighbors, weights)
        )
        return (weighted_sum + 32768) >> 16

    red = min(blend(11, 0x1F), 31)
    green = min(blend(5, 0x3F), 63)
    blue = min(blend(0, 0x1F), 31)
    return (red << 11) | (green << 5) | blue


def render_pal(source: Sequence[int]) -> List[int]:
    horizontal_scale = _fixed_point_scale(SOURCE_WIDTH, PAL_WIDTH)
    vertical_scale = _fixed_point_scale(SOURCE_HEIGHT, PAL_HEIGHT)
    horizontal_coordinates = [
        _bilinear_coordinate(column, horizontal_scale, SOURCE_WIDTH)
        for column in range(PAL_WIDTH)
    ]

    destination: List[int] = []
    for row in range(PAL_HEIGHT):
        vertical = _bilinear_coordinate(row, vertical_scale, SOURCE_HEIGHT)
        top_offset = vertical[0] * SOURCE_WIDTH
        bottom_offset = vertical[1] * SOURCE_WIDTH
        for horizontal in horizontal_coordinates:
            destination.append(
                _blend_rgb565(
                    source[top_offset + horizontal[0]],
                    source[top_offset + horizontal[1]],
                    source[bottom_offset + horizontal[0]],
                    source[bottom_offset + horizontal[1]],
                    horizontal,
                    vertical,
                )
            )
    return destination


def rgb565_little_endian_bytes(pixels: Sequence[int]) -> bytes:
    encoded = bytearray(len(pixels) * 2)
    for index, pixel in enumerate(pixels):
        encoded[index * 2] = pixel & 0xFF
        encoded[index * 2 + 1] = pixel >> 8
    return bytes(encoded)


def _output_record(pixels: Sequence[int], width: int, height: int) -> Dict[str, object]:
    if len(pixels) != width * height:
        raise GoldenOutputError(
            f"renderer produced {len(pixels)} pixels for a {width}x{height} output"
        )
    encoded = rgb565_little_endian_bytes(pixels)
    return {
        "width": width,
        "height": height,
        "byte_count": len(encoded),
        "sha256": hashlib.sha256(encoded).hexdigest(),
    }


def build_manifest(require_headers: bool) -> Dict[str, object]:
    patterns: Dict[str, object] = {}
    include_directory = REPOSITORY_ROOT / "include"

    for pattern_name, png_name, header_name in PATTERNS:
        png_path = include_directory / png_name
        header_path = include_directory / header_name
        width, height, rgba_pixels = decode_png(png_path)
        if (width, height) != (SOURCE_WIDTH, SOURCE_HEIGHT):
            raise GoldenOutputError(
                f"{png_path}: dimensions are {width}x{height}; "
                f"expected {SOURCE_WIDTH}x{SOURCE_HEIGHT}"
            )

        source = convert_to_rgb565(rgba_pixels)
        if header_path.exists():
            legacy_source = read_legacy_header(header_path)
            if source != legacy_source:
                mismatch_index = next(
                    index
                    for index, (png_pixel, header_pixel) in enumerate(
                        zip(source, legacy_source)
                    )
                    if png_pixel != header_pixel
                )
                raise GoldenOutputError(
                    f"{pattern_name}: PNG/header RGB565 mismatch at "
                    f"({mismatch_index % SOURCE_WIDTH}, "
                    f"{mismatch_index // SOURCE_WIDTH}): "
                    f"PNG=0x{source[mismatch_index]:04x}, "
                    f"header=0x{legacy_source[mismatch_index]:04x}"
                )
        elif require_headers:
            raise GoldenOutputError(f"{header_path}: legacy header is required but missing")

        preview = render_preview(source)
        pal = render_pal(source)
        output_pixels = (source, preview, pal)
        outputs = {
            output_name: _output_record(pixels, output_width, output_height)
            for (output_name, output_width, output_height), pixels in zip(
                OUTPUT_SPECS, output_pixels
            )
        }
        patterns[pattern_name] = {
            "source_png": str(png_path.relative_to(REPOSITORY_ROOT)),
            "legacy_header": str(header_path.relative_to(REPOSITORY_ROOT)),
            "outputs": outputs,
        }

    return {
        "format_version": 1,
        "hash_encoding": (
            "row-major RGB565 pixels serialized as little-endian uint16_t values"
        ),
        "renderer": (
            "src/ImageScaler.cpp preview sampling and 16.16 fixed-point PAL bilinear"
        ),
        "patterns": patterns,
    }


def _describe_difference(expected: object, actual: object, path: str = "") -> List[str]:
    differences: List[str] = []
    if isinstance(expected, dict) and isinstance(actual, dict):
        for key in sorted(set(expected) | set(actual)):
            child_path = f"{path}.{key}" if path else key
            if key not in expected:
                differences.append(f"{child_path}: unexpected value {actual[key]!r}")
            elif key not in actual:
                differences.append(f"{child_path}: missing")
            else:
                differences.extend(
                    _describe_difference(expected[key], actual[key], child_path)
                )
    elif expected != actual:
        differences.append(f"{path}: expected {expected!r}, got {actual!r}")
    return differences


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"golden manifest to verify (default: {DEFAULT_MANIFEST})",
    )
    parser.add_argument(
        "--emit-manifest",
        action="store_true",
        help="print freshly generated deterministic manifest JSON instead of verifying",
    )
    parser.add_argument(
        "--require-legacy-headers",
        action="store_true",
        help="fail if any pre-compression raw RGB565 header is missing",
    )
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    try:
        actual = build_manifest(require_headers=arguments.require_legacy_headers)
        if arguments.emit_manifest:
            print(json.dumps(actual, indent=2, sort_keys=True))
            return 0

        expected = json.loads(arguments.manifest.read_text())
        differences = _describe_difference(expected, actual)
        if differences:
            print("Golden-output verification FAILED:", file=sys.stderr)
            for difference in differences[:20]:
                print(f"  {difference}", file=sys.stderr)
            if len(differences) > 20:
                print(
                    f"  ... and {len(differences) - 20} more differences",
                    file=sys.stderr,
                )
            print(
                "\nRegenerate with --emit-manifest, then review every changed hash.",
                file=sys.stderr,
            )
            return 1

        print(
            f"Verified {len(PATTERNS)} patterns x {len(OUTPUT_SPECS)} outputs "
            f"({len(PATTERNS) * len(OUTPUT_SPECS)} SHA-256 hashes)."
        )
        if arguments.require_legacy_headers:
            print("All PNG RGB565 pixels match their legacy headers.")
        else:
            print("Any present legacy headers match their PNG RGB565 pixels.")
        try:
            manifest_label = arguments.manifest.relative_to(REPOSITORY_ROOT)
        except ValueError:
            manifest_label = arguments.manifest
        print(f"Golden manifest: {manifest_label}")
        return 0
    except (GoldenOutputError, OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Golden-output verification ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
