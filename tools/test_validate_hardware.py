#!/usr/bin/env python3
"""Host tests for the Phase 4 serial-log validator."""

from __future__ import annotations

import unittest

from tools.validate_hardware import (
    EXPECTED_PATTERNS,
    PersistenceSpec,
    ValidationSpec,
    _persistence_build_flags,
    _validate_device_environment,
    parse_arguments,
    validate_persistence_log,
    validate_serial_log,
)


def make_valid_log(cycles: int = 2, mode: str = "pal") -> str:
    mode_name = mode.upper()
    width, height = (384, 288) if mode == "pal" else (320, 240)
    framebuffer_bytes = width * height * 2
    lines = [
        "[diag] reset_reason=power-on (1)",
        "[diag] detected_board=M5StickC Plus / Plus SE (4)",
        "[diag] psramFound()=false",
        f"[diag] video preference bypassed for hardware test mode={mode_name}",
        (
            f"[diag] RCA setup mode={mode_name} size={width}x{height} "
            "psram=disabled"
        ),
        "[diag] RCA init result=success",
        (
            f"[diag] RCA framebuffer expected={framebuffer_bytes} "
            f"observed_dma={framebuffer_bytes + 8000} depth=16 "
            f"actual={width}x{height} result=success"
        ),
        (
            "[diag] heap stage=after RCA init free_internal=35708 "
            "largest_8bit=20468 largest_dma=20468"
        ),
    ]

    def add_pattern(name: str) -> None:
        lines.extend(
            (
                f"[diag] pattern name={name} payload=2 decoded_crc32=12345678",
                (
                    "[diag] render_heap output=preview before=35708 "
                    "after=35708 result=stable"
                ),
                (
                    f"[diag] render_heap output={mode_name} before=35708 "
                    "after=35708 result=stable"
                ),
                (
                    f"[diag] pattern result={name} "
                    "preview=success rca=success"
                ),
            )
        )

    add_pattern(EXPECTED_PATTERNS[0])
    lines.append(
        f"[diag] pattern self-test begin cycles={cycles} "
        f"patterns={len(EXPECTED_PATTERNS)}"
    )
    for _ in range(cycles):
        for name in EXPECTED_PATTERNS:
            add_pattern(name)
    lines.extend(
        (
            (
                "[diag] heap stage=after pattern self-test "
                "free_internal=35708 largest_8bit=20468 largest_dma=20468"
            ),
            "[diag] pattern self-test complete",
        )
    )
    return "\n".join(lines) + "\n"


def make_valid_persistence_log(
    toggles: int = 4,
    initial_mode: str = "pal",
) -> str:
    lines: list[str] = []
    mode = initial_mode
    for boot_index in range(toggles + 1):
        mode_name = mode.upper()
        width, height = (384, 288) if mode == "pal" else (320, 240)
        reset_reason = "external" if boot_index == 0 else "software"
        reset_code = 2 if boot_index == 0 else 3
        lines.extend(
            (
                f"[diag] reset_reason={reset_reason} ({reset_code})",
                "[diag] detected_board=M5StickC Plus / Plus SE (4)",
                "[diag] psramFound()=false",
                (
                    f"[diag] RCA setup mode={mode_name} "
                    f"size={width}x{height} psram=disabled"
                ),
                "[diag] RCA init result=success",
                (
                    "[diag] RCA framebuffer expected=123 observed_dma=456 "
                    f"depth=16 actual={width}x{height} result=success"
                ),
                (
                    "[diag] render_heap output=preview before=35708 "
                    "after=35708 result=stable"
                ),
                (
                    f"[diag] render_heap output={mode_name} before=35708 "
                    "after=35708 result=stable"
                ),
                (
                    "[diag] pattern result=colour_bars "
                    "preview=success rca=success"
                ),
            )
        )
        if boot_index < toggles:
            lines.append("[diag] serial command=toggle-mode")
        mode = "ntsc" if mode == "pal" else "pal"
    return "\n".join(lines) + "\n"


class ValidateHardwareLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = ValidationSpec(
            device="plus1",
            environment="m5stickc-plus-se-no-psram",
            mode="pal",
            cycles=2,
        )

    def test_valid_complete_log_passes(self) -> None:
        report = validate_serial_log(make_valid_log(), self.spec)
        self.assertTrue(report.passed, report.errors)
        self.assertEqual(report.pattern_result_count, 17)
        self.assertEqual(report.render_heap_check_count, 34)
        self.assertEqual(report.render_heap_value, 35708)
        self.assertEqual(report.initial_heap, report.final_heap)

    def test_crlf_log_passes(self) -> None:
        report = validate_serial_log(
            make_valid_log().replace("\n", "\r\n"),
            self.spec,
        )
        self.assertTrue(report.passed, report.errors)

    def test_changed_render_heap_fails(self) -> None:
        log = make_valid_log().replace(
            "output=PAL before=35708 after=35708 result=stable",
            "output=PAL before=35708 after=35704 result=changed",
            1,
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("render heap changed" in error for error in report.errors)
        )

    def test_final_heap_must_equal_initial_heap(self) -> None:
        log = make_valid_log().replace(
            "free_internal=35708 largest_8bit=20468 largest_dma=20468\n"
            "[diag] pattern self-test complete",
            "free_internal=35704 largest_8bit=20468 largest_dma=20468\n"
            "[diag] pattern self-test complete",
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("final heap metrics differ" in error for error in report.errors)
        )

    def test_missing_pattern_result_fails(self) -> None:
        log = make_valid_log().replace(
            "[diag] pattern result=blue preview=success rca=success\n",
            "",
            1,
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertEqual(report.pattern_counts["blue"], 1)

    def test_panic_and_second_boot_fail(self) -> None:
        log = (
            make_valid_log()
            + "Guru Meditation Error: Core 1 panic'ed\n"
            + "[diag] reset_reason=software (3)\n"
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("fatal/error marker" in error for error in report.errors)
        )
        self.assertTrue(
            any("reset reason" in error for error in report.errors)
        )

    def test_panic_reset_reason_fails_without_panic_text(self) -> None:
        log = make_valid_log().replace(
            "[diag] reset_reason=power-on (1)",
            "[diag] reset_reason=panic (4)",
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(any(
            "unsafe reset reason" in error for error in report.errors
        ))

    def test_common_plus2_build_may_report_physical_psram(self) -> None:
        plus2_spec = ValidationSpec(
            device="plus2",
            environment="m5stickc-plus-se-no-psram",
            mode="pal",
            cycles=2,
        )
        log = make_valid_log().replace(
            "M5StickC Plus / Plus SE",
            "M5StickC Plus2",
        ).replace(
            "psramFound()=false",
            "psramFound()=true",
        )
        report = validate_serial_log(log, plus2_spec)
        self.assertTrue(report.passed, report.errors)

    def test_plus2_regression_environment_rejects_no_psram_devices(self) -> None:
        for device in ("plus1", "plus-se"):
            with self.subTest(device=device), self.assertRaisesRegex(
                RuntimeError,
                "must not be uploaded",
            ):
                _validate_device_environment(
                    device,
                    "m5stickc-plus2-regression",
                )
        _validate_device_environment(
            "plus2",
            "m5stickc-plus2-regression",
        )

    def test_opposite_mode_fails(self) -> None:
        log = make_valid_log().replace(
            "RCA setup mode=PAL size=384x288",
            "RCA setup mode=NTSC size=320x240",
        )
        report = validate_serial_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("hardware-test build flags" in error for error in report.errors)
        )


class ValidatePersistenceLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.spec = PersistenceSpec(
            device="plus1",
            environment="m5stickc-plus-se-no-psram",
            minimum_toggles=4,
            final_mode="pal",
        )

    def test_valid_alternating_boots_pass(self) -> None:
        report = validate_persistence_log(
            make_valid_persistence_log(),
            self.spec,
        )
        self.assertTrue(report.passed, report.errors)
        self.assertEqual(report.boot_count, 5)
        self.assertEqual(report.toggle_count, 4)
        self.assertEqual(report.final_mode, "pal")
        self.assertTrue(all(
            boot.colour_bars_rendered for boot in report.boots
        ))

    def test_extra_toggle_can_restore_default_pal(self) -> None:
        report = validate_persistence_log(
            make_valid_persistence_log(toggles=5, initial_mode="ntsc"),
            self.spec,
        )
        self.assertTrue(report.passed, report.errors)
        self.assertEqual(report.toggle_count, 5)
        self.assertEqual(report.final_mode, "pal")

    def test_mode_must_alternate(self) -> None:
        log = make_valid_persistence_log().replace(
            "RCA setup mode=NTSC size=320x240",
            "RCA setup mode=PAL size=384x288",
            1,
        ).replace(
            "render_heap output=NTSC",
            "render_heap output=PAL",
            1,
        )
        report = validate_persistence_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(
            any("did not alternate" in error for error in report.errors)
        )

    def test_every_toggle_boot_must_be_software_reset(self) -> None:
        log = make_valid_persistence_log().replace(
            "[diag] reset_reason=software (3)",
            "[diag] reset_reason=brownout (9)",
            1,
        )
        report = validate_persistence_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(any(
            "expected 'software'" in error for error in report.errors
        ))

    def test_failed_colour_bars_and_crash_fail(self) -> None:
        log = make_valid_persistence_log().replace(
            "preview=success rca=success",
            "preview=failure rca=success",
            1,
        )
        log += "Guru Meditation Error: Core 1 panic'ed\n"
        report = validate_persistence_log(log, self.spec)
        self.assertFalse(report.passed)
        self.assertTrue(any(
            "fatal/error marker" in error for error in report.errors
        ))
        self.assertTrue(any(
            "did not render colour_bars" in error for error in report.errors
        ))

    def test_persistence_build_adds_only_serial_test_flag(self) -> None:
        flags = _persistence_build_flags(["-DCORE_DEBUG_LEVEL=3"])
        self.assertEqual(
            flags,
            [
                "-DCORE_DEBUG_LEVEL=3",
                "-DHARDWARE_TEST_SERIAL_COMMANDS=1",
            ],
        )
        self.assertFalse(any(
            "FORCE_DEFAULT" in flag or "SELF_TEST" in flag
            for flag in flags
        ))

    def test_common_plus2_persistence_may_report_physical_psram(self) -> None:
        plus2_spec = PersistenceSpec(
            device="plus2",
            environment="m5stickc-plus-se-no-psram",
            minimum_toggles=4,
            final_mode="pal",
        )
        log = make_valid_persistence_log().replace(
            "M5StickC Plus / Plus SE",
            "M5StickC Plus2",
        ).replace(
            "psramFound()=false",
            "psramFound()=true",
        )
        report = validate_persistence_log(log, plus2_spec)
        self.assertTrue(report.passed, report.errors)

    def test_persistence_cli_defaults_to_final_pal(self) -> None:
        args = parse_arguments([
            "persistence",
            "--device",
            "plus1",
            "--environment",
            "m5stickc-plus-se-no-psram",
            "--port",
            "/dev/example",
        ])
        self.assertEqual(args.toggles, 4)
        self.assertEqual(args.final_mode, "pal")


if __name__ == "__main__":
    unittest.main()
