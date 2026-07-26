#!/usr/bin/env python3
"""adb helpers for the gallery benchmark harness (stdlib only)."""

from __future__ import annotations

import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Callable, Iterable, Sequence


class AdbError(RuntimeError):
    """Raised when an adb command fails or times out."""


@dataclass(frozen=True)
class UiNode:
    text: str
    content_desc: str
    resource_id: str
    bounds: tuple[int, int, int, int]  # left, top, right, bottom
    clickable: bool
    enabled: bool

    @property
    def center(self) -> tuple[int, int]:
        left, top, right, bottom = self.bounds
        return (left + right) // 2, (top + bottom) // 2


_BOUNDS_RE = re.compile(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]")
_BENCH_LINE_RE = re.compile(
    r"GalleryBench[^:]*:\s*(?P<body>.+)$"
)


def run_adb(
    args: Sequence[str],
    *,
    timeout: float | None = 60.0,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    cmd = ["adb", *args]
    try:
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        raise AdbError(
            "adb not found on PATH. Install Android platform-tools and retry."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AdbError(f"adb timed out: {' '.join(cmd)}") from exc

    if check and completed.returncode != 0:
        stderr = (completed.stderr or "").strip()
        stdout = (completed.stdout or "").strip()
        detail = stderr or stdout or f"exit {completed.returncode}"
        raise AdbError(f"adb {' '.join(args)} failed: {detail}")
    return completed


def require_device() -> str:
    completed = run_adb(["devices"])
    lines = [
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and not line.startswith("List of devices")
    ]
    ready = [line.split("\t", 1)[0] for line in lines if "\tdevice" in line]
    if not ready:
        raise AdbError(
            "No adb device in 'device' state. Connect an emulator/device and enable USB debugging."
        )
    return ready[0]


def shell(command: str, *, timeout: float | None = 60.0, check: bool = True) -> str:
    return run_adb(["shell", command], timeout=timeout, check=check).stdout


def force_stop(package: str) -> None:
    shell(f"am force-stop {package}", check=False)


def clear_logcat() -> None:
    run_adb(["logcat", "-c"], check=False)


def start_activity(component: str) -> None:
    # Do not use -W alone for timing; gallery_ready covers decode + grid.
    shell(f"am start -n {component}", check=True)


def input_tap(x: int, y: int) -> None:
    shell(f"input tap {x} {y}")


def input_swipe(x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300) -> None:
    shell(f"input swipe {x1} {y1} {x2} {y2} {duration_ms}")


def input_keyevent(keycode: str | int) -> None:
    shell(f"input keyevent {keycode}")


def dump_ui_xml() -> str:
    # Write on device then pull via cat (works without host-side pull path issues).
    shell("uiautomator dump /sdcard/gallery_bench_ui.xml", timeout=30.0)
    return shell("cat /sdcard/gallery_bench_ui.xml", timeout=30.0)


def parse_ui_nodes(xml_text: str) -> list[UiNode]:
    # uiautomator dump may include a leading status line before the XML.
    start = xml_text.find("<?xml")
    if start < 0:
        start = xml_text.find("<hierarchy")
    if start < 0:
        raise AdbError("uiautomator dump did not return XML hierarchy")
    root = ET.fromstring(xml_text[start:])
    nodes: list[UiNode] = []
    for elem in root.iter("node"):
        bounds_raw = elem.attrib.get("bounds", "")
        match = _BOUNDS_RE.fullmatch(bounds_raw)
        if not match:
            continue
        bounds = tuple(int(match.group(i)) for i in range(1, 5))
        nodes.append(
            UiNode(
                text=elem.attrib.get("text", "") or "",
                content_desc=elem.attrib.get("content-desc", "") or "",
                resource_id=elem.attrib.get("resource-id", "") or "",
                bounds=bounds,  # type: ignore[arg-type]
                clickable=elem.attrib.get("clickable", "false") == "true",
                enabled=elem.attrib.get("enabled", "true") == "true",
            )
        )
    return nodes


def find_nodes_by_content_desc(
    nodes: Iterable[UiNode],
    predicate: Callable[[str], bool],
) -> list[UiNode]:
    return [n for n in nodes if predicate(n.content_desc)]


def tap_content_desc(
    exact: str | None = None,
    *,
    contains: str | None = None,
    retries: int = 8,
    delay_sec: float = 0.35,
) -> UiNode:
    last_error = "no matching node"
    for _ in range(retries):
        try:
            nodes = parse_ui_nodes(dump_ui_xml())
        except (AdbError, ET.ParseError) as exc:
            last_error = str(exc)
            time.sleep(delay_sec)
            continue

        if exact is not None:
            matches = [n for n in nodes if n.content_desc == exact]
        else:
            assert contains is not None
            matches = [n for n in nodes if contains in n.content_desc]

        # Prefer clickable/enabled nodes; fall back to any match (ImageView parent may be clickable).
        preferred = [n for n in matches if n.enabled]
        preferred.sort(key=lambda n: (not n.clickable, -(n.bounds[2] - n.bounds[0])))
        if preferred:
            node = preferred[0]
            x, y = node.center
            input_tap(x, y)
            return node
        last_error = f"content-desc not found (exact={exact!r}, contains={contains!r})"
        time.sleep(delay_sec)
    raise AdbError(last_error)


def wait_for_bench_event(
    event: str,
    *,
    timeout_sec: float,
) -> dict[str, str]:
    """
    Poll logcat for a GalleryBench line whose body starts with ``event``.

    Returns parsed key=value fields (always includes elapsed_ms when present).
    """
    deadline = time.monotonic() + timeout_sec
    # Use logcat dump rather than a long-lived stream so Windows/host cancels cleanly.
    seen: set[str] = set()
    while time.monotonic() < deadline:
        completed = run_adb(
            ["logcat", "-d", "-s", "GalleryBench:I"],
            timeout=15.0,
            check=False,
        )
        for line in completed.stdout.splitlines():
            if line in seen:
                continue
            seen.add(line)
            match = _BENCH_LINE_RE.search(line)
            if not match:
                if "GalleryBench" not in line or event not in line:
                    continue
                body = line.split(":", 1)[-1].strip()
            else:
                body = match.group("body").strip()

            if not body.startswith(event):
                continue
            fields = _parse_fields(body[len(event) :].strip())
            fields["event"] = event
            fields["_raw"] = body
            return fields
        time.sleep(0.15)
    raise AdbError(f"Timed out after {timeout_sec:.0f}s waiting for GalleryBench event '{event}'")


def _parse_fields(fragment: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for token in fragment.split():
        if "=" not in token:
            continue
        key, value = token.split("=", 1)
        fields[key] = value
    return fields


def gfxinfo_reset(package: str) -> None:
    shell(f"dumpsys gfxinfo {package} reset", check=False)


def gfxinfo_framestats(package: str) -> str:
    return shell(f"dumpsys gfxinfo {package} framestats", timeout=30.0, check=False)


def meminfo(package: str) -> str:
    return shell(f"dumpsys meminfo {package}", timeout=30.0, check=False)


def parse_meminfo(text: str) -> dict[str, float]:
    """
    Extract TOTAL PSS and App Summary heap figures when present (values in KB).
    """
    result: dict[str, float] = {}
    # TOTAL line variants across API levels:
    # "TOTAL    12345    ..." or "TOTAL PSS: 12345"
    total_match = re.search(
        r"^TOTAL(?:\s+PSS)?:\s*([\d,]+)",
        text,
        flags=re.MULTILINE,
    )
    if not total_match:
        total_match = re.search(
            r"^TOTAL\s+([\d,]+)\s+",
            text,
            flags=re.MULTILINE,
        )
    if total_match:
        result["pss_kb"] = float(total_match.group(1).replace(",", ""))

    java_match = re.search(
        r"Java Heap:\s*([\d,]+)",
        text,
        flags=re.IGNORECASE,
    )
    if java_match:
        result["java_heap_kb"] = float(java_match.group(1).replace(",", ""))

    native_match = re.search(
        r"Native Heap:\s*([\d,]+)",
        text,
        flags=re.IGNORECASE,
    )
    if native_match:
        result["native_heap_kb"] = float(native_match.group(1).replace(",", ""))

    if not result:
        raise AdbError("Could not parse dumpsys meminfo output")
    return result


def parse_framestats(text: str) -> list[float]:
    """
    Parse frame durations (ms) from ``dumpsys gfxinfo … framestats``.

    Prefer IntendedVsync → FrameCompleted columns when the CSV profile section exists;
    otherwise fall back to historic janky/total counters if present.
    """
    durations: list[float] = []
    in_profile = False
    header_cols: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("---PROFILEDATA---"):
            if in_profile:
                break
            in_profile = True
            header_cols = []
            continue
        if not in_profile:
            continue
        if not stripped:
            continue
        if stripped.startswith("Flags") or "IntendedVsync" in stripped:
            header_cols = [c.strip() for c in stripped.split(",")]
            continue
        parts = [p.strip() for p in stripped.split(",")]
        if len(parts) < 2:
            continue
        try:
            # Columns: Flags, IntendedVsync, Vsync, ..., FrameCompleted (ns)
            if header_cols and "IntendedVsync" in header_cols and "FrameCompleted" in header_cols:
                i_vsync = header_cols.index("IntendedVsync")
                i_done = header_cols.index("FrameCompleted")
                intended = float(parts[i_vsync])
                completed = float(parts[i_done])
                if completed > intended > 0:
                    durations.append((completed - intended) / 1_000_000.0)
            else:
                intended = float(parts[1])
                completed = float(parts[-1])
                if completed > intended > 0:
                    durations.append((completed - intended) / 1_000_000.0)
        except (ValueError, IndexError):
            continue

    return durations


def window_size() -> tuple[int, int]:
    out = shell("wm size")
    match = re.search(r"Physical size:\s*(\d+)x(\d+)", out)
    if not match:
        # Override size
        match = re.search(r"(\d+)x(\d+)", out)
    if not match:
        return 1080, 1920
    return int(match.group(1)), int(match.group(2))
