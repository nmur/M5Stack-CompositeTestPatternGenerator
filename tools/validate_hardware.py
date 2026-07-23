#!/usr/bin/env python3
"""Build, upload, and validate the firmware hardware self-test.

The serial-log parser intentionally has no third-party dependencies. Running
the hardware workflow additionally requires pyserial; PlatformIO installs it
in its own Python environment.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENVIRONMENT = "m5stickc-plus-se-no-psram"
DEFAULT_TIMEOUT_SECONDS = 900.0
DEFAULT_SETTLE_SECONDS = 3.0
DEFAULT_PERSISTENCE_TOGGLES = 4
SERIAL_OPEN_TIMEOUT_SECONDS = 10.0
EXPECTED_PATTERNS = (
    "colour_bars",
    "grid",
    "circles",
    "gradients",
    "white",
    "red",
    "green",
    "blue",
)

DEVICE_BOARD_NAMES = {
    "plus1": "M5StickC Plus / Plus SE",
    "plus2": "M5StickC Plus2",
    "plus-se": "M5StickC Plus / Plus SE",
}

MODE_DIMENSIONS = {
    "pal": (384, 288),
    "ntsc": (320, 240),
}

SAFE_ENVIRONMENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
RESET_RE = re.compile(
    r"^\[diag\] reset_reason=(?P<reason>.+?) \((?P<code>\d+)\)$",
    re.MULTILINE,
)
BOARD_RE = re.compile(
    r"^\[diag\] detected_board=(?P<name>.+?) \((?P<code>\d+)\)$",
    re.MULTILINE,
)
PSRAM_RE = re.compile(
    r"^\[diag\] psramFound\(\)=(?P<found>true|false)$",
    re.MULTILINE,
)
FORCED_MODE_RE = re.compile(
    r"^\[diag\] video preference bypassed for hardware test "
    r"mode=(?P<mode>PAL|NTSC)$",
    re.MULTILINE,
)
RCA_SETUP_RE = re.compile(
    r"^\[diag\] RCA setup mode=(?P<mode>PAL|NTSC) "
    r"size=(?P<width>\d+)x(?P<height>\d+) psram=(?P<psram>\S+)$",
    re.MULTILINE,
)
RCA_INIT_RE = re.compile(
    r"^\[diag\] RCA init result=(?P<result>\S+)$",
    re.MULTILINE,
)
RCA_FRAMEBUFFER_RE = re.compile(
    r"^\[diag\] RCA framebuffer .* result=(?P<result>\S+)$",
    re.MULTILINE,
)
SELF_TEST_BEGIN_RE = re.compile(
    r"^\[diag\] pattern self-test begin cycles=(?P<cycles>\d+) "
    r"patterns=(?P<patterns>\d+)$",
    re.MULTILINE,
)
SELF_TEST_COMPLETE_RE = re.compile(
    r"^\[diag\] pattern self-test complete$",
    re.MULTILINE,
)
PATTERN_RESULT_RE = re.compile(
    r"^\[diag\] pattern result=(?P<name>\S+) "
    r"preview=(?P<preview>\S+) rca=(?P<rca>\S+)$",
    re.MULTILINE,
)
RENDER_HEAP_RE = re.compile(
    r"^\[diag\] render_heap output=(?P<output>\S+) "
    r"before=(?P<before>\d+) after=(?P<after>\d+) "
    r"result=(?P<result>\S+)$",
    re.MULTILINE,
)
HEAP_STAGE_RE = re.compile(
    r"^\[diag\] heap stage=(?P<stage>.+?) "
    r"free_internal=(?P<free_internal>\d+) "
    r"largest_8bit=(?P<largest_8bit>\d+) "
    r"largest_dma=(?P<largest_dma>\d+)$",
    re.MULTILINE,
)

FATAL_MARKERS = (
    re.compile(r"^\[error\]", re.IGNORECASE | re.MULTILINE),
    re.compile(r"guru meditation", re.IGNORECASE),
    re.compile(r"core \d+ panic", re.IGNORECASE),
    re.compile(r"assert failed", re.IGNORECASE),
    re.compile(r"abort\(\) was called", re.IGNORECASE),
    re.compile(r"backtrace:", re.IGNORECASE),
    re.compile(r"corrupt heap|heap corruption", re.IGNORECASE),
    re.compile(r"brownout detector", re.IGNORECASE),
    re.compile(r"watchdog|task_wdt|interrupt wdt", re.IGNORECASE),
    re.compile(r"rebooting\.\.\.", re.IGNORECASE),
    re.compile(r"allocation failed", re.IGNORECASE),
    re.compile(r"\bresult=failure\b", re.IGNORECASE),
)


class HardwareValidationError(RuntimeError):
    """A clear, expected validation or workflow error."""


@dataclass(frozen=True)
class ValidationSpec:
    device: str
    environment: str
    mode: str
    cycles: int

    @property
    def expected_board_name(self) -> str:
        return DEVICE_BOARD_NAMES[self.device]

    @property
    def expected_mode_name(self) -> str:
        return self.mode.upper()


@dataclass
class HeapMetrics:
    free_internal: int
    largest_8bit: int
    largest_dma: int


@dataclass
class ValidationReport:
    passed: bool
    device: str
    environment: str
    mode: str
    cycles: int
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    board: str | None = None
    reset_reason: str | None = None
    psram_found: bool | None = None
    pattern_result_count: int = 0
    pattern_counts: dict[str, int] = field(default_factory=dict)
    render_heap_check_count: int = 0
    render_heap_value: int | None = None
    initial_heap: HeapMetrics | None = None
    final_heap: HeapMetrics | None = None

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class PersistenceSpec:
    device: str
    environment: str
    minimum_toggles: int
    final_mode: str | None

    @property
    def expected_board_name(self) -> str:
        return DEVICE_BOARD_NAMES[self.device]


@dataclass
class PersistenceBoot:
    index: int
    reset_reason: str | None = None
    board: str | None = None
    psram_found: bool | None = None
    mode: str | None = None
    width: int | None = None
    height: int | None = None
    colour_bars_rendered: bool = False
    toggle_command_after: bool = False


@dataclass
class PersistenceReport:
    passed: bool
    device: str
    environment: str
    minimum_toggles: int
    final_mode_required: str | None
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    boot_count: int = 0
    toggle_count: int = 0
    final_mode: str | None = None
    boots: list[PersistenceBoot] = field(default_factory=list)

    def to_json_dict(self) -> dict[str, Any]:
        return asdict(self)


def _one_match(
    matches: Sequence[re.Match[str]],
    description: str,
    errors: list[str],
) -> re.Match[str] | None:
    if len(matches) != 1:
        errors.append(
            f"expected exactly one {description} record, found {len(matches)}"
        )
        return None
    return matches[0]


def _heap_from_match(match: re.Match[str]) -> HeapMetrics:
    return HeapMetrics(
        free_internal=int(match.group("free_internal")),
        largest_8bit=int(match.group("largest_8bit")),
        largest_dma=int(match.group("largest_dma")),
    )


def validate_serial_log(text: str, spec: ValidationSpec) -> ValidationReport:
    """Validate one complete firmware self-test serial transcript."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    errors: list[str] = []
    warnings: list[str] = []

    for marker in FATAL_MARKERS:
        match = marker.search(text)
        if match:
            excerpt = match.group(0).strip()
            errors.append(f"fatal/error marker found in serial log: {excerpt!r}")

    reset_match = _one_match(
        list(RESET_RE.finditer(text)), "reset reason", errors
    )
    board_match = _one_match(
        list(BOARD_RE.finditer(text)), "detected board", errors
    )
    psram_match = _one_match(
        list(PSRAM_RE.finditer(text)), "PSRAM diagnostic", errors
    )
    setup_match = _one_match(
        list(RCA_SETUP_RE.finditer(text)), "RCA setup", errors
    )
    forced_mode_match = _one_match(
        list(FORCED_MODE_RE.finditer(text)),
        "forced hardware-test video mode",
        errors,
    )
    init_match = _one_match(
        list(RCA_INIT_RE.finditer(text)), "RCA initialization", errors
    )
    framebuffer_match = _one_match(
        list(RCA_FRAMEBUFFER_RE.finditer(text)), "RCA framebuffer", errors
    )
    self_test_match = _one_match(
        list(SELF_TEST_BEGIN_RE.finditer(text)), "self-test start", errors
    )
    complete_matches = list(SELF_TEST_COMPLETE_RE.finditer(text))
    _one_match(complete_matches, "self-test completion", errors)

    board_name: str | None = None
    if board_match:
        board_name = board_match.group("name")
        if board_name != spec.expected_board_name:
            errors.append(
                f"detected board {board_name!r}, expected "
                f"{spec.expected_board_name!r} for {spec.device}"
            )

    reset_reason = reset_match.group("reason") if reset_match else None
    if reset_reason not in {"power-on", "external", "software"}:
        errors.append(
            f"unsafe reset reason {reset_reason!r}; expected a clean "
            "power-on, external, or software reset"
        )
    psram_found: bool | None = None
    if psram_match:
        psram_found = psram_match.group("found") == "true"
        if (
            spec.environment == "m5stickc-plus-se-no-psram"
            and spec.device in {"plus1", "plus-se"}
            and psram_found
        ):
            errors.append("no-PSRAM environment unexpectedly reported PSRAM")
        if (
            spec.environment == "m5stickc-plus2-regression"
            and spec.device == "plus2"
            and not psram_found
        ):
            errors.append("Plus2 regression environment did not detect PSRAM")

    if setup_match:
        actual_mode = setup_match.group("mode")
        actual_dimensions = (
            int(setup_match.group("width")),
            int(setup_match.group("height")),
        )
        expected_dimensions = MODE_DIMENSIONS[spec.mode]
        if actual_mode != spec.expected_mode_name:
            errors.append(
                f"firmware entered {actual_mode}, expected "
                f"{spec.expected_mode_name}; verify the hardware-test build "
                "flags and serial transcript"
            )
        if actual_dimensions != expected_dimensions:
            errors.append(
                f"RCA dimensions were {actual_dimensions[0]}x"
                f"{actual_dimensions[1]}, expected "
                f"{expected_dimensions[0]}x{expected_dimensions[1]}"
            )
        if setup_match.group("psram") != "disabled":
            errors.append("RCA framebuffer did not report psram=disabled")
    if (
        forced_mode_match
        and forced_mode_match.group("mode") != spec.expected_mode_name
    ):
        errors.append(
            "forced hardware-test mode was "
            f"{forced_mode_match.group('mode')}, expected "
            f"{spec.expected_mode_name}"
        )

    if init_match and init_match.group("result") != "success":
        errors.append("RCA initialization did not succeed")
    if (
        framebuffer_match
        and framebuffer_match.group("result") != "success"
    ):
        errors.append("RCA framebuffer validation did not succeed")

    if self_test_match:
        actual_cycles = int(self_test_match.group("cycles"))
        actual_patterns = int(self_test_match.group("patterns"))
        if actual_cycles != spec.cycles:
            errors.append(
                f"self-test ran {actual_cycles} cycles, expected {spec.cycles}"
            )
        if actual_patterns != len(EXPECTED_PATTERNS):
            errors.append(
                f"self-test reported {actual_patterns} patterns, expected "
                f"{len(EXPECTED_PATTERNS)}"
            )

    pattern_matches = list(PATTERN_RESULT_RE.finditer(text))
    expected_total_results = 1 + spec.cycles * len(EXPECTED_PATTERNS)
    if len(pattern_matches) != expected_total_results:
        errors.append(
            f"found {len(pattern_matches)} pattern results, expected "
            f"{expected_total_results}"
        )

    pattern_counts = {name: 0 for name in EXPECTED_PATTERNS}
    for match in pattern_matches:
        name = match.group("name")
        if name not in pattern_counts:
            errors.append(f"unexpected pattern result {name!r}")
            continue
        pattern_counts[name] += 1
        if (
            match.group("preview") != "success"
            or match.group("rca") != "success"
        ):
            errors.append(
                f"pattern {name!r} did not render successfully: "
                f"preview={match.group('preview')} rca={match.group('rca')}"
            )

    expected_counts = {name: spec.cycles for name in EXPECTED_PATTERNS}
    expected_counts[EXPECTED_PATTERNS[0]] += 1
    for name, expected_count in expected_counts.items():
        if pattern_counts[name] != expected_count:
            errors.append(
                f"pattern {name!r} completed {pattern_counts[name]} times, "
                f"expected {expected_count}"
            )

    render_matches = list(RENDER_HEAP_RE.finditer(text))
    expected_render_checks = expected_total_results * 2
    if len(render_matches) != expected_render_checks:
        errors.append(
            f"found {len(render_matches)} render heap checks, expected "
            f"{expected_render_checks}"
        )

    expected_outputs = {"preview", spec.expected_mode_name}
    render_values: set[int] = set()
    output_counts: dict[str, int] = {}
    for match in render_matches:
        output_name = match.group("output")
        before = int(match.group("before"))
        after = int(match.group("after"))
        result = match.group("result")
        output_counts[output_name] = output_counts.get(output_name, 0) + 1
        render_values.update((before, after))
        if output_name not in expected_outputs:
            errors.append(f"unexpected render heap output {output_name!r}")
        if before != after or result != "stable":
            errors.append(
                f"render heap changed for {output_name}: "
                f"before={before} after={after} result={result}"
            )

    for output_name in expected_outputs:
        actual_count = output_counts.get(output_name, 0)
        if actual_count != expected_total_results:
            errors.append(
                f"found {actual_count} {output_name} heap checks, expected "
                f"{expected_total_results}"
            )
    if len(render_values) > 1:
        errors.append(
            "render heap baseline was not constant across the suite: "
            + ", ".join(str(value) for value in sorted(render_values))
        )
    render_heap_value = (
        next(iter(render_values)) if len(render_values) == 1 else None
    )

    heap_stages: dict[str, list[HeapMetrics]] = {}
    for match in HEAP_STAGE_RE.finditer(text):
        heap_stages.setdefault(match.group("stage"), []).append(
            _heap_from_match(match)
        )
    initial_matches = heap_stages.get("after RCA init", [])
    final_matches = heap_stages.get("after pattern self-test", [])
    initial_heap: HeapMetrics | None = None
    final_heap: HeapMetrics | None = None
    if len(initial_matches) != 1:
        errors.append(
            "expected exactly one 'after RCA init' heap record, found "
            f"{len(initial_matches)}"
        )
    else:
        initial_heap = initial_matches[0]
    if len(final_matches) != 1:
        errors.append(
            "expected exactly one 'after pattern self-test' heap record, "
            f"found {len(final_matches)}"
        )
    else:
        final_heap = final_matches[0]
    if initial_heap and final_heap and initial_heap != final_heap:
        errors.append(
            "final heap metrics differ from the post-RCA baseline: "
            f"initial={asdict(initial_heap)} final={asdict(final_heap)}"
        )
    if (
        initial_heap
        and render_heap_value is not None
        and render_heap_value != initial_heap.free_internal
    ):
        errors.append(
            "render heap baseline differs from the post-RCA free heap: "
            f"render={render_heap_value} "
            f"post_rca={initial_heap.free_internal}"
        )

    if spec.device == "plus-se":
        warnings.append(
            "Plus SE and Plus1 share the same M5GFX board diagnostic; "
            "confirm the physical unit identity in the test record"
        )

    return ValidationReport(
        passed=not errors,
        device=spec.device,
        environment=spec.environment,
        mode=spec.mode,
        cycles=spec.cycles,
        errors=errors,
        warnings=warnings,
        board=board_name,
        reset_reason=reset_reason,
        psram_found=psram_found,
        pattern_result_count=len(pattern_matches),
        pattern_counts=pattern_counts,
        render_heap_check_count=len(render_matches),
        render_heap_value=render_heap_value,
        initial_heap=initial_heap,
        final_heap=final_heap,
    )


def validate_persistence_log(
    text: str,
    spec: PersistenceSpec,
) -> PersistenceReport:
    """Validate complete boots separated by diagnostic mode toggles."""

    text = text.replace("\r\n", "\n").replace("\r", "\n")
    errors: list[str] = []
    warnings: list[str] = []

    for marker in FATAL_MARKERS:
        match = marker.search(text)
        if match:
            errors.append(
                "fatal/error marker found in serial log: "
                f"{match.group(0).strip()!r}"
            )

    if FORCED_MODE_RE.search(text):
        errors.append(
            "persistence firmware bypassed NVS with a forced video mode"
        )
    if SELF_TEST_BEGIN_RE.search(text) or SELF_TEST_COMPLETE_RE.search(text):
        errors.append(
            "persistence firmware unexpectedly ran the pattern self-test"
        )

    reset_matches = list(RESET_RE.finditer(text))
    segments = [
        text[match.start():(
            reset_matches[index + 1].start()
            if index + 1 < len(reset_matches)
            else len(text)
        )]
        for index, match in enumerate(reset_matches)
    ]
    boots: list[PersistenceBoot] = []

    for index, segment in enumerate(segments):
        boot_errors: list[str] = []
        reset_match = _one_match(
            list(RESET_RE.finditer(segment)),
            f"reset reason in boot {index}",
            boot_errors,
        )
        board_match = _one_match(
            list(BOARD_RE.finditer(segment)),
            f"detected board in boot {index}",
            boot_errors,
        )
        psram_match = _one_match(
            list(PSRAM_RE.finditer(segment)),
            f"PSRAM diagnostic in boot {index}",
            boot_errors,
        )
        setup_match = _one_match(
            list(RCA_SETUP_RE.finditer(segment)),
            f"RCA setup in boot {index}",
            boot_errors,
        )
        init_match = _one_match(
            list(RCA_INIT_RE.finditer(segment)),
            f"RCA initialization in boot {index}",
            boot_errors,
        )
        framebuffer_match = _one_match(
            list(RCA_FRAMEBUFFER_RE.finditer(segment)),
            f"RCA framebuffer in boot {index}",
            boot_errors,
        )
        pattern_match = _one_match(
            list(PATTERN_RESULT_RE.finditer(segment)),
            f"pattern result in boot {index}",
            boot_errors,
        )

        reset_reason = reset_match.group("reason") if reset_match else None
        board_name = board_match.group("name") if board_match else None
        psram_found = (
            psram_match.group("found") == "true" if psram_match else None
        )
        mode = setup_match.group("mode").lower() if setup_match else None
        width = int(setup_match.group("width")) if setup_match else None
        height = int(setup_match.group("height")) if setup_match else None

        if index == 0:
            if reset_reason not in {"power-on", "external", "software"}:
                boot_errors.append(
                    f"initial boot has unsafe reset reason {reset_reason!r}"
                )
        elif reset_reason != "software":
            boot_errors.append(
                f"boot {index} reset reason is {reset_reason!r}, "
                "expected 'software'"
            )
        if board_name and board_name != spec.expected_board_name:
            boot_errors.append(
                f"boot {index} detected board {board_name!r}, expected "
                f"{spec.expected_board_name!r}"
            )
        if (
            spec.environment == "m5stickc-plus-se-no-psram"
            and spec.device in {"plus1", "plus-se"}
            and psram_found is True
        ):
            boot_errors.append(
                f"boot {index} unexpectedly reported PSRAM"
            )
        if (
            spec.environment == "m5stickc-plus2-regression"
            and spec.device == "plus2"
            and psram_found is False
        ):
            boot_errors.append(
                f"boot {index} did not detect Plus2 PSRAM"
            )
        if setup_match:
            expected_dimensions = MODE_DIMENSIONS[mode]
            actual_dimensions = (width, height)
            if actual_dimensions != expected_dimensions:
                boot_errors.append(
                    f"boot {index} {mode.upper()} dimensions were "
                    f"{width}x{height}, expected "
                    f"{expected_dimensions[0]}x{expected_dimensions[1]}"
                )
            if setup_match.group("psram") != "disabled":
                boot_errors.append(
                    f"boot {index} RCA framebuffer did not report "
                    "psram=disabled"
                )
        if init_match and init_match.group("result") != "success":
            boot_errors.append(
                f"boot {index} RCA initialization did not succeed"
            )
        if (
            framebuffer_match
            and framebuffer_match.group("result") != "success"
        ):
            boot_errors.append(
                f"boot {index} RCA framebuffer validation did not succeed"
            )

        colour_bars_rendered = False
        if pattern_match:
            colour_bars_rendered = (
                pattern_match.group("name") == "colour_bars"
                and pattern_match.group("preview") == "success"
                and pattern_match.group("rca") == "success"
            )
            if not colour_bars_rendered:
                boot_errors.append(
                    f"boot {index} did not render colour_bars successfully"
                )

        render_matches = list(RENDER_HEAP_RE.finditer(segment))
        if len(render_matches) != 2:
            boot_errors.append(
                f"boot {index} has {len(render_matches)} render heap checks, "
                "expected 2"
            )
        expected_outputs = {"preview", mode.upper()} if mode else {"preview"}
        actual_outputs: set[str] = set()
        for render_match in render_matches:
            actual_outputs.add(render_match.group("output"))
            before = int(render_match.group("before"))
            after = int(render_match.group("after"))
            if (
                before != after
                or render_match.group("result") != "stable"
            ):
                boot_errors.append(
                    f"boot {index} render heap changed for "
                    f"{render_match.group('output')}"
                )
        if actual_outputs != expected_outputs:
            boot_errors.append(
                f"boot {index} render outputs were "
                f"{sorted(actual_outputs)}, expected "
                f"{sorted(expected_outputs)}"
            )

        toggle_count_after = segment.count(
            "[diag] serial command=toggle-mode"
        )
        expected_toggle_count = 0 if index == len(segments) - 1 else 1
        if toggle_count_after != expected_toggle_count:
            boot_errors.append(
                f"boot {index} has {toggle_count_after} toggle commands "
                f"after rendering, expected {expected_toggle_count}"
            )

        boots.append(
            PersistenceBoot(
                index=index,
                reset_reason=reset_reason,
                board=board_name,
                psram_found=psram_found,
                mode=mode,
                width=width,
                height=height,
                colour_bars_rendered=colour_bars_rendered,
                toggle_command_after=toggle_count_after == 1,
            )
        )
        errors.extend(boot_errors)

    if not boots:
        errors.append("no complete diagnostic boots found")

    for previous, current in zip(boots, boots[1:]):
        if (
            previous.mode is not None
            and current.mode is not None
            and previous.mode == current.mode
        ):
            errors.append(
                f"video mode did not alternate between boots "
                f"{previous.index} and {current.index}: {current.mode.upper()}"
            )

    actual_transitions = max(0, len(boots) - 1)
    toggle_count = text.count("[diag] serial command=toggle-mode")
    if actual_transitions < spec.minimum_toggles:
        errors.append(
            f"completed {actual_transitions} toggle/reboot transitions, "
            f"required at least {spec.minimum_toggles}"
        )
    if toggle_count != actual_transitions:
        errors.append(
            f"found {toggle_count} toggle commands for "
            f"{actual_transitions} completed reboot transitions"
        )

    final_mode = boots[-1].mode if boots else None
    if spec.final_mode is not None and final_mode != spec.final_mode:
        errors.append(
            f"final video mode is {final_mode!r}, expected "
            f"{spec.final_mode!r}"
        )

    if spec.device == "plus-se":
        warnings.append(
            "Plus SE and Plus1 share the same M5GFX board diagnostic; "
            "confirm the physical unit identity in the test record"
        )

    return PersistenceReport(
        passed=not errors,
        device=spec.device,
        environment=spec.environment,
        minimum_toggles=spec.minimum_toggles,
        final_mode_required=spec.final_mode,
        errors=errors,
        warnings=warnings,
        boot_count=len(boots),
        toggle_count=toggle_count,
        final_mode=final_mode,
        boots=boots,
    )


def _validate_environment_name(environment: str) -> None:
    if not SAFE_ENVIRONMENT_RE.fullmatch(environment):
        raise HardwareValidationError(
            f"unsafe PlatformIO environment name: {environment!r}"
        )


def _validate_device_environment(device: str, environment: str) -> None:
    if environment == "m5stickc-plus2-regression" and device != "plus2":
        raise HardwareValidationError(
            "m5stickc-plus2-regression enables Plus2 PSRAM and must not be "
            f"uploaded to {device}"
        )


def _bounded_integer(
    value: str,
    *,
    option_name: str,
    minimum: int,
    maximum: int,
) -> int:
    try:
        parsed = int(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError(
            f"{option_name} must be an integer"
        ) from error
    if not minimum <= parsed <= maximum:
        raise argparse.ArgumentTypeError(
            f"{option_name} must be between {minimum} and {maximum}"
        )
    return parsed


def _cycle_count(value: str) -> int:
    return _bounded_integer(
        value,
        option_name="cycles",
        minimum=1,
        maximum=10_000,
    )


def _toggle_count(value: str) -> int:
    return _bounded_integer(
        value,
        option_name="toggles",
        minimum=1,
        maximum=1_000,
    )


def _baud_rate(value: str) -> int:
    return _bounded_integer(
        value,
        option_name="baud",
        minimum=1_200,
        maximum=4_000_000,
    )


def _validate_serial_port(port: str, *, dry_run: bool) -> None:
    if not port or any(character in port for character in "*?[]\r\n"):
        raise HardwareValidationError(
            "serial port must be an explicit device path or COM port"
        )
    is_windows_com_port = bool(re.fullmatch(r"COM\d+", port, re.IGNORECASE))
    if not dry_run and not is_windows_com_port and not Path(port).exists():
        raise HardwareValidationError(f"serial port does not exist: {port}")


def _find_pio(explicit_path: str | None) -> str:
    candidates: list[str | None] = [
        explicit_path,
        shutil.which("pio"),
        str(Path.home() / ".platformio" / "penv" / "bin" / "pio"),
        str(Path.home() / ".platformio" / "penv" / "Scripts" / "pio.exe"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return str(Path(candidate).resolve())
    raise HardwareValidationError(
        "could not find PlatformIO; pass its executable with --pio"
    )


def _platformio_environment(
    base: dict[str, str],
    build_flags: Sequence[str],
) -> dict[str, str]:
    environment = dict(base)
    environment["PLATFORMIO_BUILD_FLAGS"] = " ".join(build_flags)
    environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    return environment


def _load_platformio_build_flags(
    pio: str,
    environment: str,
) -> list[str]:
    config_environment = dict(os.environ)
    config_environment.pop("PLATFORMIO_BUILD_FLAGS", None)
    config_environment["PLATFORMIO_SETTING_ENABLE_TELEMETRY"] = "no"
    completed = subprocess.run(
        [pio, "project", "config", "--json-output"],
        cwd=REPOSITORY_ROOT,
        env=config_environment,
        check=False,
        capture_output=True,
        text=True,
    )
    if completed.returncode != 0:
        raise HardwareValidationError(
            "PlatformIO could not resolve project configuration:\n"
            + completed.stderr.strip()
        )
    try:
        sections = dict(json.loads(completed.stdout))
        options = dict(sections[f"env:{environment}"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise HardwareValidationError(
            f"could not find env:{environment} in PlatformIO configuration"
        ) from error
    flags = options.get("build_flags", [])
    if isinstance(flags, str):
        return flags.split()
    if not isinstance(flags, list) or not all(
        isinstance(flag, str) for flag in flags
    ):
        raise HardwareValidationError(
            f"unexpected build_flags value for env:{environment}: {flags!r}"
        )
    return flags


def _run_command(
    command: Sequence[str],
    *,
    environment: dict[str, str],
    dry_run: bool,
) -> None:
    print("+", " ".join(command), flush=True)
    if dry_run:
        return
    completed = subprocess.run(
        list(command),
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=False,
    )
    if completed.returncode != 0:
        raise HardwareValidationError(
            f"command failed with exit status {completed.returncode}: "
            + " ".join(command)
        )


def _reset_into_application(serial_port: Any) -> None:
    # DTR controls GPIO0 and RTS controls EN on the common ESP32 USB bridge.
    # Keep GPIO0 high while pulsing EN so the device boots the application.
    serial_port.dtr = False
    serial_port.rts = False
    serial_port.reset_input_buffer()
    serial_port.rts = True
    time.sleep(0.1)
    serial_port.rts = False


def capture_serial_log(
    port: str,
    baud: int,
    timeout_seconds: float,
    settle_seconds: float,
    reset_after_open: bool,
    log_path: Path,
) -> str:
    try:
        import serial  # type: ignore[import-not-found]
    except ModuleNotFoundError as error:
        raise HardwareValidationError(
            "pyserial is unavailable. Run this tool with PlatformIO's Python, "
            "for example ~/.platformio/penv/bin/python"
        ) from error

    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Capturing serial output in {log_path}", flush=True)
    fragments: list[str] = []
    started = time.monotonic()
    completed_at: float | None = None
    completion_tail = ""

    try:
        open_deadline = time.monotonic() + SERIAL_OPEN_TIMEOUT_SECONDS
        while True:
            try:
                serial_port = serial.Serial(port, baud, timeout=0.2)
                break
            except serial.SerialException:
                if time.monotonic() >= open_deadline:
                    raise
                time.sleep(0.25)

        with serial_port:
            if reset_after_open:
                _reset_into_application(serial_port)
            while True:
                now = time.monotonic()
                if now - started >= timeout_seconds:
                    raise HardwareValidationError(
                        f"serial validation timed out after "
                        f"{timeout_seconds:g} seconds"
                    )
                payload = serial_port.read(4096)
                if payload:
                    fragment = payload.decode("utf-8", errors="replace")
                    fragments.append(fragment)
                    sys.stdout.write(fragment)
                    sys.stdout.flush()
                    completion_tail = (completion_tail + fragment)[-128:]
                    if (
                        completed_at is None
                        and "[diag] pattern self-test complete"
                        in completion_tail
                    ):
                        completed_at = now
                if (
                    completed_at is not None
                    and now - completed_at >= settle_seconds
                ):
                    break
    except HardwareValidationError:
        raise
    except Exception as error:
        raise HardwareValidationError(
            f"serial capture failed on {port}: {error}"
        ) from error
    finally:
        log_path.write_text("".join(fragments), encoding="utf-8")

    return "".join(fragments)


def capture_persistence_log(
    port: str,
    baud: int,
    timeout_seconds: float,
    settle_seconds: float,
    minimum_toggles: int,
    final_mode: str | None,
    log_path: Path,
) -> str:
    """Reset once, toggle through software reboots, and capture every boot."""

    try:
        import serial  # type: ignore[import-not-found]
    except ModuleNotFoundError as error:
        raise HardwareValidationError(
            "pyserial is unavailable. Run this tool with PlatformIO's Python, "
            "for example ~/.platformio/penv/bin/python"
        ) from error

    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Capturing persistence output in {log_path}", flush=True)
    fragments: list[str] = []
    started = time.monotonic()
    completed_at: float | None = None
    commands_sent = 0

    try:
        open_deadline = time.monotonic() + SERIAL_OPEN_TIMEOUT_SECONDS
        while True:
            try:
                serial_port = serial.Serial(port, baud, timeout=0.2)
                break
            except serial.SerialException:
                if time.monotonic() >= open_deadline:
                    raise
                time.sleep(0.25)

        with serial_port:
            _reset_into_application(serial_port)
            while True:
                now = time.monotonic()
                if now - started >= timeout_seconds:
                    raise HardwareValidationError(
                        "persistence validation timed out after "
                        f"{timeout_seconds:g} seconds"
                    )

                payload = serial_port.read(4096)
                if payload:
                    fragment = payload.decode("utf-8", errors="replace")
                    fragments.append(fragment)
                    sys.stdout.write(fragment)
                    sys.stdout.flush()

                text = "".join(fragments)
                for marker in FATAL_MARKERS:
                    match = marker.search(text)
                    if match:
                        raise HardwareValidationError(
                            "fatal/error marker appeared during persistence "
                            f"capture: {match.group(0).strip()!r}"
                        )
                reset_count = len(list(RESET_RE.finditer(text)))
                pattern_matches = list(PATTERN_RESULT_RE.finditer(text))
                completion_count = len(pattern_matches)
                expected_boot_count = commands_sent + 1
                if reset_count > expected_boot_count:
                    raise HardwareValidationError(
                        "an unexpected reset occurred during persistence "
                        "capture"
                    )
                if (
                    completed_at is None
                    and reset_count == expected_boot_count
                    and completion_count == expected_boot_count
                ):
                    completed_at = now

                if (
                    completed_at is None
                    or now - completed_at < settle_seconds
                ):
                    continue

                setup_matches = list(RCA_SETUP_RE.finditer(text))
                if len(setup_matches) != expected_boot_count:
                    raise HardwareValidationError(
                        "a boot completed without exactly one RCA setup "
                        "diagnostic"
                    )
                last_pattern = pattern_matches[-1]
                if (
                    last_pattern.group("name") != "colour_bars"
                    or last_pattern.group("preview") != "success"
                    or last_pattern.group("rca") != "success"
                ):
                    raise HardwareValidationError(
                        "a boot did not reach a successful colour_bars render"
                    )
                current_mode = setup_matches[-1].group("mode").lower()
                needs_more_toggles = commands_sent < minimum_toggles
                needs_final_mode = (
                    final_mode is not None and current_mode != final_mode
                )
                if not needs_more_toggles and not needs_final_mode:
                    break
                maximum_toggles = minimum_toggles + (
                    1 if final_mode is not None else 0
                )
                if commands_sent >= maximum_toggles:
                    raise HardwareValidationError(
                        "final video mode was not reached after the one "
                        "permitted restoration toggle"
                    )

                print(
                    f"\nSending mode toggle {commands_sent + 1}; "
                    f"current mode is {current_mode.upper()}",
                    flush=True,
                )
                if serial_port.write(b"m") != 1:
                    raise HardwareValidationError(
                        "serial port did not accept the mode-toggle command"
                    )
                serial_port.flush()
                commands_sent += 1
                completed_at = None
    except HardwareValidationError:
        raise
    except Exception as error:
        raise HardwareValidationError(
            f"persistence serial capture failed on {port}: {error}"
        ) from error
    finally:
        log_path.write_text("".join(fragments), encoding="utf-8")

    return "".join(fragments)


def _default_artifact_paths(spec: ValidationSpec) -> tuple[Path, Path]:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    stem = (
        f"{timestamp}-{spec.device}-{spec.mode}-{spec.cycles}-cycles"
    )
    directory = REPOSITORY_ROOT / ".pio" / "hardware-validation"
    return directory / f"{stem}.log", directory / f"{stem}.json"


def _default_persistence_artifact_paths(
    spec: PersistenceSpec,
) -> tuple[Path, Path]:
    timestamp = dt.datetime.now(dt.timezone.utc).strftime(
        "%Y%m%dT%H%M%S%fZ"
    )
    final_mode = spec.final_mode or "any"
    stem = (
        f"{timestamp}-{spec.device}-persistence-"
        f"{spec.minimum_toggles}-toggles-final-{final_mode}"
    )
    directory = REPOSITORY_ROOT / ".pio" / "hardware-validation"
    return directory / f"{stem}.log", directory / f"{stem}.json"


def _write_report(
    report: ValidationReport | PersistenceReport,
    path: Path,
) -> None:
    if path.exists():
        raise HardwareValidationError(
            f"refusing to overwrite existing report: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_json_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _print_report(report: ValidationReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    print(
        f"\nHardware validation {status}: {report.device} "
        f"{report.mode.upper()}, {report.cycles} cycles"
    )
    print(
        f"Patterns: {report.pattern_result_count}; "
        f"render heap checks: {report.render_heap_check_count}; "
        f"stable heap: {report.render_heap_value}"
    )
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")


def _print_persistence_report(report: PersistenceReport) -> None:
    status = "PASS" if report.passed else "FAIL"
    final_mode = report.final_mode.upper() if report.final_mode else "unknown"
    print(
        f"\nPersistence validation {status}: {report.device}; "
        f"{report.toggle_count} toggles, {report.boot_count} boots, "
        f"final mode {final_mode}"
    )
    for boot in report.boots:
        mode = boot.mode.upper() if boot.mode else "unknown"
        print(
            f"Boot {boot.index}: reset={boot.reset_reason} mode={mode} "
            f"colour_bars={'success' if boot.colour_bars_rendered else 'failure'}"
        )
    for warning in report.warnings:
        print(f"WARNING: {warning}")
    for error in report.errors:
        print(f"ERROR: {error}")


def _make_spec(args: argparse.Namespace) -> ValidationSpec:
    _validate_environment_name(args.environment)
    _validate_device_environment(args.device, args.environment)
    return ValidationSpec(
        device=args.device,
        environment=args.environment,
        mode=args.mode,
        cycles=args.cycles,
    )


def _make_persistence_spec(args: argparse.Namespace) -> PersistenceSpec:
    _validate_environment_name(args.environment)
    _validate_device_environment(args.device, args.environment)
    return PersistenceSpec(
        device=args.device,
        environment=args.environment,
        minimum_toggles=args.toggles,
        final_mode=None if args.final_mode == "any" else args.final_mode,
    )


def _persistence_build_flags(base_flags: Sequence[str]) -> list[str]:
    return [*base_flags, "-DHARDWARE_TEST_SERIAL_COMMANDS=1"]


def _run_hardware(args: argparse.Namespace) -> int:
    spec = _make_spec(args)
    _validate_serial_port(args.port, dry_run=args.dry_run)
    pio = _find_pio(args.pio)
    base_flags = _load_platformio_build_flags(pio, spec.environment)
    test_flags = [
        *base_flags,
        f"-DDEFAULT_VIDEO_MODE_PAL={1 if spec.mode == 'pal' else 0}",
        f"-DPATTERN_SELF_TEST_CYCLES={spec.cycles}",
        "-DHARDWARE_TEST_FORCE_DEFAULT_MODE=1",
    ]
    process_environment = _platformio_environment(os.environ, test_flags)

    log_path, report_path = _default_artifact_paths(spec)
    if args.log:
        log_path = Path(args.log).expanduser().resolve()
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
    if not args.dry_run:
        for artifact_path in (log_path, report_path):
            if artifact_path.exists():
                raise HardwareValidationError(
                    f"refusing to overwrite existing artifact: {artifact_path}"
                )

    print(
        f"Validation target: device={spec.device} "
        f"environment={spec.environment} mode={spec.mode.upper()} "
        f"cycles={spec.cycles}"
    )
    print("Build flags:", " ".join(test_flags))
    _run_command(
        [pio, "run", "--environment", spec.environment],
        environment=process_environment,
        dry_run=args.dry_run,
    )
    _run_command(
        [
            pio,
            "run",
            "--environment",
            spec.environment,
            "--target",
            "upload",
            "--upload-port",
            args.port,
        ],
        environment=process_environment,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(
            f"Would capture {args.port} at {args.baud} baud, then validate "
            f"and write {log_path} and {report_path}"
        )
        return 0

    text = capture_serial_log(
        port=args.port,
        baud=args.baud,
        timeout_seconds=args.timeout,
        settle_seconds=args.settle_seconds,
        reset_after_open=not args.no_reset,
        log_path=log_path,
    )
    report = validate_serial_log(text, spec)
    _write_report(report, report_path)
    _print_report(report)
    print(f"Serial log: {log_path}")
    print(f"JSON report: {report_path}")
    return 0 if report.passed else 1


def _run_persistence_hardware(args: argparse.Namespace) -> int:
    spec = _make_persistence_spec(args)
    _validate_serial_port(args.port, dry_run=args.dry_run)
    pio = _find_pio(args.pio)
    base_flags = _load_platformio_build_flags(pio, spec.environment)
    test_flags = _persistence_build_flags(base_flags)
    process_environment = _platformio_environment(os.environ, test_flags)

    log_path, report_path = _default_persistence_artifact_paths(spec)
    if args.log:
        log_path = Path(args.log).expanduser().resolve()
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
    if not args.dry_run:
        for artifact_path in (log_path, report_path):
            if artifact_path.exists():
                raise HardwareValidationError(
                    f"refusing to overwrite existing artifact: {artifact_path}"
                )

    final_mode = spec.final_mode.upper() if spec.final_mode else "ANY"
    print(
        f"Persistence target: device={spec.device} "
        f"environment={spec.environment} minimum_toggles="
        f"{spec.minimum_toggles} final_mode={final_mode}"
    )
    print("Build flags:", " ".join(test_flags))
    _run_command(
        [pio, "run", "--environment", spec.environment],
        environment=process_environment,
        dry_run=args.dry_run,
    )
    _run_command(
        [
            pio,
            "run",
            "--environment",
            spec.environment,
            "--target",
            "upload",
            "--upload-port",
            args.port,
        ],
        environment=process_environment,
        dry_run=args.dry_run,
    )
    if args.dry_run:
        print(
            f"Would reset and capture {args.port} at {args.baud} baud, send "
            "mode toggles, then validate and write "
            f"{log_path} and {report_path}"
        )
        return 0

    capture_error: str | None = None
    try:
        text = capture_persistence_log(
            port=args.port,
            baud=args.baud,
            timeout_seconds=args.timeout,
            settle_seconds=args.settle_seconds,
            minimum_toggles=spec.minimum_toggles,
            final_mode=spec.final_mode,
            log_path=log_path,
        )
    except HardwareValidationError as error:
        capture_error = str(error)
        text = (
            log_path.read_text(encoding="utf-8", errors="replace")
            if log_path.exists()
            else ""
        )

    report = validate_persistence_log(text, spec)
    if capture_error:
        report.errors.append(f"capture workflow failed: {capture_error}")
        report.passed = False
    _write_report(report, report_path)
    _print_persistence_report(report)
    print(f"Serial log: {log_path}")
    print(f"JSON report: {report_path}")
    return 0 if report.passed else 1


def _validate_existing_log(args: argparse.Namespace) -> int:
    spec = _make_spec(args)
    log_path = Path(args.log).expanduser().resolve()
    if not log_path.is_file():
        raise HardwareValidationError(f"serial log does not exist: {log_path}")
    report = validate_serial_log(
        log_path.read_text(encoding="utf-8", errors="replace"),
        spec,
    )
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        _write_report(report, report_path)
        print(f"JSON report: {report_path}")
    _print_report(report)
    return 0 if report.passed else 1


def _validate_existing_persistence_log(args: argparse.Namespace) -> int:
    spec = _make_persistence_spec(args)
    log_path = Path(args.log).expanduser().resolve()
    if not log_path.is_file():
        raise HardwareValidationError(f"serial log does not exist: {log_path}")
    report = validate_persistence_log(
        log_path.read_text(encoding="utf-8", errors="replace"),
        spec,
    )
    if args.report:
        report_path = Path(args.report).expanduser().resolve()
        _write_report(report, report_path)
        print(f"JSON report: {report_path}")
    _print_persistence_report(report)
    return 0 if report.passed else 1


def _add_validation_spec_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--device",
        choices=tuple(DEVICE_BOARD_NAMES),
        required=True,
        help="physical device being tested",
    )
    parser.add_argument(
        "--environment",
        required=True,
        help="explicit PlatformIO environment name",
    )
    parser.add_argument(
        "--mode",
        choices=tuple(MODE_DIMENSIONS),
        required=True,
        help="video mode that must appear in the serial diagnostics",
    )
    parser.add_argument(
        "--cycles",
        type=_cycle_count,
        default=100,
        metavar="N",
        help="complete eight-pattern cycles (default: 100)",
    )


def _add_persistence_spec_arguments(
    parser: argparse.ArgumentParser,
) -> None:
    parser.add_argument(
        "--device",
        choices=tuple(DEVICE_BOARD_NAMES),
        required=True,
        help="physical device being tested",
    )
    parser.add_argument(
        "--environment",
        required=True,
        help="explicit PlatformIO environment name",
    )
    parser.add_argument(
        "--toggles",
        type=_toggle_count,
        default=DEFAULT_PERSISTENCE_TOGGLES,
        metavar="N",
        help=(
            "minimum software-reboot mode transitions "
            f"(default: {DEFAULT_PERSISTENCE_TOGGLES})"
        ),
    )
    parser.add_argument(
        "--final-mode",
        choices=("pal", "ntsc", "any"),
        default="pal",
        help=(
            "leave and verify the saved mode after the minimum transitions; "
            "one extra toggle may be sent (default: pal)"
        ),
    )


def parse_arguments(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build, upload, capture, and validate the firmware Phase 4 "
            "hardware self-test."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser(
        "run",
        help="build, upload, and validate a connected device",
    )
    _add_validation_spec_arguments(run_parser)
    run_parser.add_argument(
        "--port",
        required=True,
        help="explicit serial/upload port, such as /dev/cu.usbserial-1234",
    )
    run_parser.add_argument(
        "--pio",
        help="path to the PlatformIO pio executable",
    )
    run_parser.add_argument(
        "--baud",
        type=_baud_rate,
        default=115200,
        metavar="RATE",
        help="serial baud rate (default: 115200)",
    )
    run_parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"serial suite timeout in seconds (default: "
        f"{DEFAULT_TIMEOUT_SECONDS:g})",
    )
    run_parser.add_argument(
        "--settle-seconds",
        type=float,
        default=DEFAULT_SETTLE_SECONDS,
        help=(
            "continue watching for crashes/resets after completion "
            f"(default: {DEFAULT_SETTLE_SECONDS:g})"
        ),
    )
    run_parser.add_argument(
        "--no-reset",
        action="store_true",
        help="do not pulse ESP32 EN after opening the serial port",
    )
    run_parser.add_argument(
        "--log",
        help="serial log destination (default: .pio/hardware-validation/...)",
    )
    run_parser.add_argument(
        "--report",
        help="JSON report destination (default: .pio/hardware-validation/...)",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve configuration and print commands without building/uploading",
    )
    run_parser.set_defaults(handler=_run_hardware)

    persistence_parser = subparsers.add_parser(
        "persistence",
        aliases=["persist"],
        help="build, upload, and validate saved PAL/NTSC mode toggles",
    )
    _add_persistence_spec_arguments(persistence_parser)
    persistence_parser.add_argument(
        "--port",
        required=True,
        help="explicit serial/upload port, such as /dev/cu.usbserial-1234",
    )
    persistence_parser.add_argument(
        "--pio",
        help="path to the PlatformIO pio executable",
    )
    persistence_parser.add_argument(
        "--baud",
        type=_baud_rate,
        default=115200,
        metavar="RATE",
        help="serial baud rate (default: 115200)",
    )
    persistence_parser.add_argument(
        "--timeout",
        type=float,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=(
            "complete persistence workflow timeout in seconds "
            f"(default: {DEFAULT_TIMEOUT_SECONDS:g})"
        ),
    )
    persistence_parser.add_argument(
        "--settle-seconds",
        type=float,
        default=DEFAULT_SETTLE_SECONDS,
        help=(
            "watch each completed boot before sending the next toggle "
            f"(default: {DEFAULT_SETTLE_SECONDS:g})"
        ),
    )
    persistence_parser.add_argument(
        "--log",
        help="serial log destination (default: .pio/hardware-validation/...)",
    )
    persistence_parser.add_argument(
        "--report",
        help="JSON report destination (default: .pio/hardware-validation/...)",
    )
    persistence_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="resolve configuration and print commands without building/uploading",
    )
    persistence_parser.set_defaults(handler=_run_persistence_hardware)

    validate_parser = subparsers.add_parser(
        "validate-log",
        help="validate an existing serial transcript without hardware",
    )
    _add_validation_spec_arguments(validate_parser)
    validate_parser.add_argument("--log", required=True)
    validate_parser.add_argument("--report")
    validate_parser.set_defaults(handler=_validate_existing_log)

    validate_persistence_parser = subparsers.add_parser(
        "validate-persistence-log",
        help="validate a saved mode-persistence transcript",
    )
    _add_persistence_spec_arguments(validate_persistence_parser)
    validate_persistence_parser.add_argument("--log", required=True)
    validate_persistence_parser.add_argument("--report")
    validate_persistence_parser.set_defaults(
        handler=_validate_existing_persistence_log
    )

    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = parse_arguments(argv)
        if getattr(args, "timeout", 1) <= 0:
            raise HardwareValidationError("--timeout must be positive")
        if getattr(args, "settle_seconds", 0) < 0:
            raise HardwareValidationError("--settle-seconds must not be negative")
        return int(args.handler(args))
    except HardwareValidationError as error:
        print(f"ERROR: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
