#!/usr/bin/env python3
"""Host-only tests for the ESP Web Tools release packager."""

from __future__ import annotations

import argparse
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock


SCRIPT = Path(__file__).with_name("package_web_installer.py")
SPEC = importlib.util.spec_from_file_location("package_web_installer", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
packager = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(packager)


def arguments(output: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "version": "1.2.3",
        "output": output,
        "build": False,
        "platformio": None,
        "esptool": None,
        "boot_app0": None,
        "force": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


class ManifestTests(unittest.TestCase):
    def test_manifest_has_esp_web_tools_shape(self) -> None:
        value = packager.manifest("Composite patterns", "1.2.3", "bin/firmware.bin")

        self.assertEqual(value["name"], "Composite patterns")
        self.assertEqual(value["version"], "1.2.3")
        self.assertIs(value["new_install_prompt_erase"], True)
        self.assertEqual(value["new_install_improv_wait_time"], 0)
        self.assertEqual(
            value["builds"],
            [
                {
                    "chipFamily": "ESP32",
                    "parts": [{"path": "bin/firmware.bin", "offset": 0}],
                }
            ],
        )

    def test_package_normalizes_version_and_writes_consistent_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build_root = root / "build"
            environment_dir = build_root / packager.DEFAULT_ENVIRONMENT
            environment_dir.mkdir(parents=True)

            source_bytes = {
                "bootloader.bin": b"bootloader",
                "partitions.bin": b"partitions",
                "firmware.bin": b"application",
            }
            for filename, data in source_bytes.items():
                (environment_dir / filename).write_bytes(data)

            boot_app0 = root / "boot_app0.bin"
            boot_app0.write_bytes(b"ota-stub")
            esptool = root / "esptool.py"
            esptool.write_text("# test double\n")
            template = root / "index.template.html"
            template.write_text("<p>@@VERSION@@</p>\n")
            output = root / "dist"

            def fake_merge(
                command: list[str],
                destination: Path,
                components: dict[str, Path],
            ) -> None:
                self.assertEqual(command, [sys.executable, str(esptool.resolve())])
                self.assertEqual(set(components), {item[0] for item in packager.FLASH_PARTS})
                image = bytearray(0x10001)
                image[0x10000] = 0xE9
                destination.write_bytes(image)

            with (
                mock.patch.object(packager, "BUILD_DIRECTORY", build_root),
                mock.patch.object(packager, "INSTALLER_TEMPLATE", template),
                mock.patch.object(packager, "merge_firmware", side_effect=fake_merge),
                contextlib.redirect_stdout(io.StringIO()),
            ):
                packager.package(
                    arguments(
                        output,
                        version="v1.2.3-rc.1",
                        esptool=esptool,
                        boot_app0=boot_app0,
                    )
                )

            common_manifest = json.loads((output / "manifest.json").read_text())
            self.assertEqual(common_manifest["version"], "1.2.3-rc.1")
            self.assertEqual(
                common_manifest["builds"][0]["parts"],
                [
                    {
                        "path": "bin/v1.2.3-rc.1/common/firmware.bin",
                        "offset": 0,
                    }
                ],
            )
            self.assertEqual((output / "index.html").read_text(), "<p>1.2.3-rc.1</p>\n")

            release = json.loads((output / "release-index.json").read_text())
            self.assertEqual(release["version"], "1.2.3-rc.1")
            self.assertEqual(
                [target["id"] for target in release["targets"]],
                [target[0] for target in packager.TARGETS],
            )
            self.assertEqual(
                [target["support"] for target in release["targets"]],
                [target[2] for target in packager.TARGETS],
            )
            self.assertEqual(
                [component["offset"] for component in release["source_components"]],
                [part[1] for part in packager.FLASH_PARTS],
            )

            expected_path = "bin/v1.2.3-rc.1/common/firmware.bin"
            for slug, _name, _support in packager.TARGETS:
                target_manifest = json.loads(
                    (output / f"manifest-{slug}.json").read_text()
                )
                self.assertEqual(target_manifest["version"], "1.2.3-rc.1")
                self.assertEqual(
                    target_manifest["builds"][0]["parts"][0],
                    {"path": expected_path, "offset": 0},
                )

            hash_paths = [
                line.split("  ", 1)[1]
                for line in (output / "SHA256SUMS").read_text().splitlines()
            ]
            self.assertEqual(hash_paths, sorted(hash_paths))
            self.assertNotIn("SHA256SUMS", hash_paths)
            self.assertIn(expected_path, hash_paths)

    def test_invalid_versions_fail_before_touching_output(self) -> None:
        invalid_versions = ("", "v", "../1.2.3", "1/2", "1 beta", "release💥")
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "existing"
            output.mkdir()
            sentinel = output / "keep.txt"
            sentinel.write_text("keep")

            for version in invalid_versions:
                with self.subTest(version=version):
                    with self.assertRaisesRegex(packager.PackagingError, "version"):
                        packager.package(
                            arguments(output, version=version, force=True)
                        )
                    self.assertEqual(sentinel.read_text(), "keep")


class OutputSafetyTests(unittest.TestCase):
    def test_existing_output_requires_force(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dist"
            output.mkdir()
            sentinel = output / "old.txt"
            sentinel.write_text("old")

            with self.assertRaisesRegex(packager.PackagingError, "already exists"):
                packager.prepare_output(output, force=False)
            self.assertTrue(sentinel.is_file())

            packager.prepare_output(output, force=True)
            self.assertTrue(output.is_dir())
            self.assertEqual(list(output.iterdir()), [])

    def test_force_refuses_known_unsafe_directories(self) -> None:
        with mock.patch.object(packager.shutil, "rmtree") as remove:
            with self.assertRaisesRegex(packager.PackagingError, "unsafe output path"):
                packager.prepare_output(Path.home(), force=True)
            remove.assert_not_called()


class HelperTests(unittest.TestCase):
    def test_release_build_drops_ambient_diagnostic_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "dist"
            captured_environment: dict[str, str] | None = None

            def fake_run(
                command: list[str],
                *,
                environment: dict[str, str] | None = None,
            ) -> None:
                nonlocal captured_environment
                captured_environment = environment
                raise packager.PackagingError("stop after build")

            with (
                mock.patch.object(packager, "platformio_command", return_value=["pio"]),
                mock.patch.object(packager, "run", side_effect=fake_run),
                mock.patch.dict(
                    packager.os.environ,
                    {
                        "PLATFORMIO_BUILD_FLAGS": (
                            "-DPATTERN_SELF_TEST_CYCLES=100 "
                            "-DHARDWARE_TEST_FORCE_DEFAULT_MODE=1"
                        )
                    },
                ),
                self.assertRaisesRegex(packager.PackagingError, "stop after build"),
            ):
                packager.package(arguments(output, build=True))

            self.assertIsNotNone(captured_environment)
            assert captured_environment is not None
            self.assertNotIn("PLATFORMIO_BUILD_FLAGS", captured_environment)
            self.assertEqual(
                captured_environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"],
                "no",
            )

    def test_hash_list_is_sorted_and_does_not_hash_itself(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary)
            (output / "z.bin").write_bytes(b"z")
            (output / "nested").mkdir()
            (output / "nested" / "a.bin").write_bytes(b"a")

            packager.write_hashes(output)

            expected = [
                f"{packager.sha256(output / 'nested' / 'a.bin')}  nested/a.bin",
                f"{packager.sha256(output / 'z.bin')}  z.bin",
            ]
            self.assertEqual(
                (output / "SHA256SUMS").read_text().splitlines(),
                expected,
            )

    def test_boot_app0_discovery_accepts_identical_copies_and_rejects_mismatch(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            core = Path(temporary)
            candidates = []
            for package_name in (
                "framework-arduinoespressif32",
                "framework-arduinoespressif32@src-test",
            ):
                path = core / "packages" / package_name / "tools" / "partitions"
                path.mkdir(parents=True)
                candidate = path / "boot_app0.bin"
                candidate.write_bytes(b"same")
                candidates.append(candidate)

            with mock.patch.object(
                packager, "platformio_core_directory", return_value=core
            ):
                self.assertEqual(
                    packager.find_boot_app0(None),
                    sorted(candidates)[0].resolve(),
                )
                candidates[1].write_bytes(b"different")
                with self.assertRaisesRegex(
                    packager.PackagingError, "multiple different"
                ):
                    packager.find_boot_app0(None)

    def test_merge_command_uses_the_expected_esp32_flash_layout(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "merged.bin"
            components: dict[str, Path] = {}
            for filename, _offset in packager.FLASH_PARTS:
                component = root / filename
                component.write_bytes(filename.encode())
                components[filename] = component

            captured: list[list[str]] = []

            def fake_run(command: list[str]) -> None:
                captured.append(command)
                image = bytearray(0x10001)
                image[0x10000] = 0xE9
                output.write_bytes(image)

            with mock.patch.object(packager, "run", side_effect=fake_run):
                packager.merge_firmware(["fake-esptool"], output, components)

            self.assertEqual(len(captured), 1)
            command = captured[0]
            self.assertEqual(
                command[:12],
                [
                    "fake-esptool",
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
                ],
            )
            for filename, offset in packager.FLASH_PARTS:
                offset_index = command.index(hex(offset))
                self.assertEqual(command[offset_index + 1], str(components[filename]))

    def test_explicit_python_esptool_uses_the_current_interpreter(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            esptool = Path(temporary) / "esptool.py"
            esptool.write_text("# test double\n")
            self.assertEqual(
                packager.find_esptool(esptool),
                [sys.executable, str(esptool.resolve())],
            )


if __name__ == "__main__":
    unittest.main()
