#!/usr/bin/env python3
"""Compile and verify the exact C++ asset decoder and scanline renderer."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_MANIFEST = REPOSITORY_ROOT / "test" / "golden_outputs.sha256.json"

COMMON_SOURCES = (
    REPOSITORY_ROOT / "src" / "PatternDecoder.cpp",
    REPOSITORY_ROOT / "src" / "generated" / "PatternAssets.cpp",
)
RENDER_SOURCES = (
    REPOSITORY_ROOT / "src" / "ImageScaler.cpp",
    REPOSITORY_ROOT / "src" / "ScanlineRenderer.cpp",
)


class PipelineVerificationError(Exception):
    """Raised when the native firmware pipeline cannot be built or verified."""


def _run(command: list[str], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
    try:
        return subprocess.run(command, check=True, **kwargs)
    except subprocess.CalledProcessError as error:
        raise PipelineVerificationError(
            f"command failed with exit code {error.returncode}: {' '.join(command)}"
        ) from error


def _compile(
    compiler: str,
    source: Path,
    output: Path,
    extra_sources: tuple[Path, ...],
) -> None:
    command = [
        compiler,
        "-std=c++17",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-I",
        str(REPOSITORY_ROOT / "include"),
        str(source),
        *(str(path) for path in COMMON_SOURCES),
        *(str(path) for path in extra_sources),
        "-o",
        str(output),
    ]
    _run(command)


def main() -> int:
    compiler_name = os.environ.get("CXX", "c++")
    compiler = shutil.which(compiler_name)
    if compiler is None:
        print(
            f"Firmware pipeline verification ERROR: compiler not found: {compiler_name}",
            file=sys.stderr,
        )
        return 2

    try:
        _run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "tools" / "generate_pattern_assets.py"),
                "--check",
            ]
        )
        _run(
            [
                sys.executable,
                str(REPOSITORY_ROOT / "tools" / "verify_golden_outputs.py"),
            ]
        )

        manifest = json.loads(GOLDEN_MANIFEST.read_text())
        patterns = manifest["patterns"]

        with tempfile.TemporaryDirectory(prefix="pattern-pipeline-") as directory:
            temporary_directory = Path(directory)
            decoder_test = temporary_directory / "test_pattern_decoder"
            renderer_test = temporary_directory / "test_render_pipeline"

            _compile(
                compiler,
                REPOSITORY_ROOT / "tools" / "test_pattern_decoder.cpp",
                decoder_test,
                (),
            )
            _run([str(decoder_test)])

            _compile(
                compiler,
                REPOSITORY_ROOT / "tools" / "test_render_pipeline.cpp",
                renderer_test,
                RENDER_SOURCES,
            )

            checked_outputs = 0
            for pattern_name, pattern_record in patterns.items():
                for output_name, expected in pattern_record["outputs"].items():
                    result = _run(
                        [str(renderer_test), pattern_name, output_name],
                        stdout=subprocess.PIPE,
                    )
                    actual_bytes = result.stdout
                    actual_hash = hashlib.sha256(actual_bytes).hexdigest()
                    if len(actual_bytes) != expected["byte_count"]:
                        raise PipelineVerificationError(
                            f"{pattern_name}/{output_name}: expected "
                            f"{expected['byte_count']} bytes, got {len(actual_bytes)}"
                        )
                    if actual_hash != expected["sha256"]:
                        raise PipelineVerificationError(
                            f"{pattern_name}/{output_name}: expected SHA-256 "
                            f"{expected['sha256']}, got {actual_hash}"
                        )
                    checked_outputs += 1

        print(
            "Verified the native C++ decoder and scanline renderer: "
            f"{len(patterns)} patterns x 3 outputs "
            f"({checked_outputs} golden SHA-256 hashes)."
        )
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError,
            PipelineVerificationError) as error:
        print(f"Firmware pipeline verification ERROR: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
