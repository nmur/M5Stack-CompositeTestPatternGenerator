#!/usr/bin/env python3
"""Build a release-ready ESP Web Tools bundle for the M5StickC Plus family."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Iterable, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENVIRONMENT = "m5stickc-plus-se-no-psram"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "web-installer" / "dist"
INSTALLER_TEMPLATE = REPOSITORY_ROOT / "web-installer" / "index.template.html"
BUILD_DIRECTORY = REPOSITORY_ROOT / ".pio" / "build"

FLASH_PARTS = (
    ("bootloader.bin", 0x1000),
    ("partitions.bin", 0x8000),
    ("boot_app0.bin", 0xE000),
    ("firmware.bin", 0x10000),
)

# ESP Web Tools can select by chip family, but it cannot distinguish these
# devices because all three use the original ESP32. Separate manifests let the
# web page ask the user to select their device while keeping one common binary.
TARGETS = (
    (
        "m5stickc-plus",
        "M5Stack Composite Test Pattern Generator — M5StickC Plus v1/v1.1 (validation pending)",
        "validation-pending",
    ),
    (
        "m5stickc-plus2",
        "M5Stack Composite Test Pattern Generator — M5StickC Plus2 (validation pending)",
        "validation-pending",
    ),
    (
        "m5stickc-plus-se",
        "M5Stack Composite Test Pattern Generator — M5StickC Plus SE (experimental)",
        "experimental",
    ),
)


class PackagingError(RuntimeError):
    """A user-actionable web-installer packaging failure."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(
    command: Sequence[str],
    *,
    environment: dict[str, str] | None = None,
) -> None:
    printable = " ".join(command)
    print(f"+ {printable}", flush=True)
    try:
        subprocess.run(
            command,
            cwd=REPOSITORY_ROOT,
            env=environment,
            check=True,
        )
    except FileNotFoundError as error:
        raise PackagingError(f"command not found: {command[0]}") from error
    except subprocess.CalledProcessError as error:
        raise PackagingError(
            f"command failed with exit status {error.returncode}: {printable}"
        ) from error


def platformio_command(explicit: str | None) -> list[str]:
    if explicit:
        return [explicit]

    for executable in ("pio", "platformio"):
        path = shutil.which(executable)
        if path:
            return [path]

    candidate = Path.home() / ".platformio" / "penv" / "bin" / "platformio"
    if candidate.is_file():
        return [str(candidate)]

    raise PackagingError(
        "PlatformIO was not found; install it or pass --platformio PATH"
    )


def platformio_core_directory() -> Path:
    configured = os.environ.get("PLATFORMIO_CORE_DIR")
    return Path(configured).expanduser() if configured else Path.home() / ".platformio"


def find_boot_app0(explicit: Path | None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise PackagingError(f"boot_app0 binary does not exist: {explicit}")
        return explicit.resolve()

    pattern = "framework-arduinoespressif32*/tools/partitions/boot_app0.bin"
    candidates = sorted((platformio_core_directory() / "packages").glob(pattern))
    if not candidates:
        raise PackagingError(
            "boot_app0.bin was not found in the PlatformIO package directory; "
            "pass --boot-app0 PATH"
        )

    # Versioned and unversioned framework packages can coexist. Their OTA
    # boot stubs are normally identical; refusing an ambiguous mismatch avoids
    # silently packaging a binary from the wrong framework installation.
    hashes = {sha256(candidate) for candidate in candidates}
    if len(hashes) != 1:
        rendered = "\n  ".join(str(candidate) for candidate in candidates)
        raise PackagingError(
            "multiple different boot_app0.bin files were found; select the "
            f"matching framework with --boot-app0:\n  {rendered}"
        )
    return candidates[0].resolve()


def find_esptool(explicit: Path | None) -> list[str]:
    if explicit:
        if not explicit.is_file():
            raise PackagingError(f"esptool does not exist: {explicit}")
        if explicit.suffix == ".py":
            return [sys.executable, str(explicit.resolve())]
        return [str(explicit.resolve())]

    executable = shutil.which("esptool") or shutil.which("esptool.py")
    if executable:
        return [executable]

    package_root = platformio_core_directory() / "packages"
    candidates = sorted(package_root.glob("tool-esptoolpy*/esptool.py"))
    if candidates:
        core_root = platformio_core_directory()
        platformio_python_candidates = (
            core_root / "penv" / "bin" / "python",
            core_root / "penv" / "Scripts" / "python.exe",
        )
        platformio_python = next(
            (
                candidate
                for candidate in platformio_python_candidates
                if candidate.is_file()
            ),
            None,
        )
        if platformio_python is None:
            raise PackagingError(
                "PlatformIO's esptool was found, but its Python environment "
                "was not; pass --esptool PATH"
            )
        # Keep the venv launcher path intact. Resolving its symlink would bypass
        # the PlatformIO environment and lose esptool's Python dependencies.
        return [str(platformio_python), str(candidates[0].resolve())]

    raise PackagingError(
        "esptool was not found; install it or pass --esptool PATH"
    )


def require_build_outputs(environment: str, boot_app0: Path) -> dict[str, Path]:
    environment_directory = BUILD_DIRECTORY / environment
    paths = {
        "bootloader.bin": environment_directory / "bootloader.bin",
        "partitions.bin": environment_directory / "partitions.bin",
        "boot_app0.bin": boot_app0,
        "firmware.bin": environment_directory / "firmware.bin",
    }
    missing = [str(path) for path in paths.values() if not path.is_file()]
    if missing:
        raise PackagingError(
            "required build output is missing:\n  " + "\n  ".join(missing)
        )
    empty = [str(path) for path in paths.values() if path.stat().st_size == 0]
    if empty:
        raise PackagingError("build output is empty:\n  " + "\n  ".join(empty))
    return paths


def prepare_output(output: Path, force: bool) -> None:
    if output.exists():
        if not force:
            raise PackagingError(
                f"output directory already exists: {output}\n"
                "Choose a new --output path or pass --force to replace it."
            )
        unsafe_paths = {
            Path("/").resolve(),
            Path.home().resolve(),
            REPOSITORY_ROOT.resolve(),
            REPOSITORY_ROOT.parent.resolve(),
            Path("/tmp").resolve(),
            Path("/private/tmp").resolve(),
        }
        if output.resolve() in unsafe_paths:
            raise PackagingError(f"refusing to replace unsafe output path: {output}")
        shutil.rmtree(output)
    output.mkdir(parents=True)


def merge_firmware(
    esptool: Sequence[str],
    output: Path,
    components: dict[str, Path],
) -> None:
    command = [
        *esptool,
        "--chip",
        "esp32",
        "merge_bin",
        "-o",
        str(output),
        "--flash_mode",
        "dio",
        "--flash_freq",
        "40m",
        "--flash_size",
        "4MB",
    ]
    for filename, offset in FLASH_PARTS:
        command.extend((hex(offset), str(components[filename])))
    run(command)

    if output.stat().st_size <= 0x10000:
        raise PackagingError(
            f"merged firmware is unexpectedly small: {output.stat().st_size} bytes"
        )
    if output.read_bytes()[0x10000] != 0xE9:
        raise PackagingError("merged firmware has no ESP32 application at 0x10000")


def manifest(name: str, version: str, firmware_path: str) -> dict[str, object]:
    return {
        "name": name,
        "version": version,
        "new_install_prompt_erase": True,
        "new_install_improv_wait_time": 0,
        "builds": [
            {
                "chipFamily": "ESP32",
                "parts": [{"path": firmware_path, "offset": 0}],
            }
        ],
    }


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=False) + "\n")


def relative_files(root: Path) -> Iterable[Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def write_hashes(output: Path) -> None:
    hashes_path = output / "SHA256SUMS"
    lines = []
    for path in relative_files(output):
        if path == hashes_path:
            continue
        lines.append(f"{sha256(path)}  {path.relative_to(output).as_posix()}")
    hashes_path.write_text("\n".join(lines) + "\n")


def package(arguments: argparse.Namespace) -> None:
    version = arguments.version.removeprefix("v")
    if not re.fullmatch(r"[0-9A-Za-z][0-9A-Za-z._+-]*", version):
        raise PackagingError(
            "version must contain only letters, digits, '.', '_', '+', or '-'"
        )
    version_directory = f"v{version}"
    environment = DEFAULT_ENVIRONMENT

    if arguments.build:
        command = platformio_command(arguments.platformio)
        build_environment = dict(os.environ)
        # Release packaging must not inherit one-off diagnostic firmware flags
        # from a developer's shell (self-test cycles, forced mode, or serial
        # test commands).
        build_environment.pop("PLATFORMIO_BUILD_FLAGS", None)
        build_environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
        run(
            [*command, "run", "-e", environment],
            environment=build_environment,
        )

    boot_app0 = find_boot_app0(arguments.boot_app0)
    components = require_build_outputs(environment, boot_app0)
    output = arguments.output.resolve()
    prepare_output(output, arguments.force)

    firmware_directory = output / "bin" / version_directory / "common"
    firmware_directory.mkdir(parents=True)
    merged_firmware = firmware_directory / "firmware.bin"
    merge_firmware(find_esptool(arguments.esptool), merged_firmware, components)

    relative_firmware = merged_firmware.relative_to(output).as_posix()
    common_name = "M5Stack Composite Test Pattern Generator — M5StickC Plus family"
    write_json(output / "manifest.json", manifest(common_name, version, relative_firmware))

    target_index = []
    for slug, display_name, support in TARGETS:
        manifest_filename = f"manifest-{slug}.json"
        write_json(
            output / manifest_filename,
            manifest(display_name, version, relative_firmware),
        )
        target_index.append(
            {
                "id": slug,
                "name": display_name,
                "support": support,
                "manifest": manifest_filename,
            }
        )

    if not INSTALLER_TEMPLATE.is_file():
        raise PackagingError(f"installer page template is missing: {INSTALLER_TEMPLATE}")
    installer_html = INSTALLER_TEMPLATE.read_text().replace("@@VERSION@@", version)
    if "@@VERSION@@" in installer_html:
        raise PackagingError("installer page contains an unresolved version placeholder")
    (output / "index.html").write_text(installer_html)

    component_metadata = []
    for filename, offset in FLASH_PARTS:
        path = components[filename]
        component_metadata.append(
            {
                "filename": filename,
                "offset": offset,
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )

    write_json(
        output / "release-index.json",
        {
            "name": "M5Stack-CompositeTestPatternGenerator",
            "version": version,
            "platformio_environment": environment,
            "flash": {
                "chip_family": "ESP32",
                "mode": "dio",
                "frequency": "40m",
                "size": "4MB",
            },
            "firmware": {
                "path": relative_firmware,
                "offset": 0,
                "size": merged_firmware.stat().st_size,
                "sha256": sha256(merged_firmware),
            },
            "source_components": component_metadata,
            "targets": target_index,
        },
    )
    write_hashes(output)

    print(
        f"Packaged ESP Web Tools bundle for {len(TARGETS)} targets at "
        f"{output.relative_to(REPOSITORY_ROOT) if output.is_relative_to(REPOSITORY_ROOT) else output}"
    )
    print(
        f"Merged firmware: {merged_firmware.stat().st_size} bytes, "
        f"sha256={sha256(merged_firmware)}"
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build and package the common no-PSRAM firmware as a merged ESP32 "
            "image plus ESP Web Tools manifests."
        )
    )
    parser.add_argument(
        "--version",
        required=True,
        help="release version embedded in the manifests (a leading v is optional)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help=f"bundle output directory (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--no-build",
        action="store_false",
        dest="build",
        help="package existing PlatformIO build outputs without rebuilding",
    )
    parser.set_defaults(build=True)
    parser.add_argument("--platformio", help="path to the PlatformIO executable")
    parser.add_argument(
        "--esptool",
        type=Path,
        help="path to esptool or esptool.py",
    )
    parser.add_argument(
        "--boot-app0",
        type=Path,
        help="path to the framework's boot_app0.bin",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="replace an existing output directory",
    )
    return parser.parse_args()


def main() -> int:
    try:
        package(parse_arguments())
    except (OSError, PackagingError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
