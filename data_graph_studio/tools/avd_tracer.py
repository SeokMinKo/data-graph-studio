# data_graph_studio/tools/avd_tracer.py
"""AVD ftrace capture utility — no Qt, pure subprocess.

Provides functions to:
- list connected adb devices
- enable block layer ftrace on an AVD
- run a synthetic I/O workload
- pull the trace file

Usage:
    from data_graph_studio.tools.avd_tracer import capture_block_trace

    path = capture_block_trace("emulator-5554", "/tmp/trace.txt", duration_sec=5)
"""
from __future__ import annotations

import logging
import subprocess
import time
from pathlib import Path
from typing import List

logger = logging.getLogger(__name__)

# Ftrace device path on Android
_TRACEFS = "/sys/kernel/tracing"
_DEBUGFS  = "/sys/kernel/debug/tracing"

# Block layer events to enable
_BLOCK_EVENTS = [
    "block/block_rq_insert",
    "block/block_rq_issue",
    "block/block_rq_complete",
]

# On-device trace output path
_DEVICE_TRACE_PATH = "/data/local/tmp/dgs_block_trace.txt"


def _adb(serial: str, *args: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run an adb command against the given device serial."""
    cmd = ["adb", "-s", serial, *args]
    logger.debug("avd_tracer.adb", extra={"cmd": " ".join(cmd)})
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _adb_shell(serial: str, shell_cmd: str, timeout: int = 30) -> subprocess.CompletedProcess:
    """Run a shell command on the device (tries with root, falls back if su unavailable)."""
    result = _adb(serial, "shell", "su", "0", shell_cmd, timeout=timeout)
    if result.returncode != 0 and "not found" in result.stderr.lower():
        result = _adb(serial, "shell", shell_cmd, timeout=timeout)
    return result


def list_devices() -> List[str]:
    """Return list of connected adb device serials (state=device only)."""
    result = subprocess.run(
        ["adb", "devices"], capture_output=True, text=True, timeout=10
    )
    devices = []
    for line in result.stdout.splitlines()[1:]:
        parts = line.strip().split()
        if len(parts) == 2 and parts[1] == "device":
            devices.append(parts[0])
    return devices


def find_tracefs(serial: str) -> str:
    """Detect which tracefs path is available on the device."""
    for path in (_TRACEFS, _DEBUGFS):
        r = _adb(serial, "shell", f"test -d {path} && echo ok")
        if "ok" in r.stdout:
            return path
    raise RuntimeError(f"No tracefs found on device {serial!r}")


def enable_block_tracing(serial: str, tracefs: str) -> None:
    """Enable block layer events in ftrace."""
    # Clear old trace
    _adb_shell(serial, f"echo 0 > {tracefs}/tracing_on")
    _adb_shell(serial, f"echo > {tracefs}/trace")
    _adb_shell(serial, f"echo nop > {tracefs}/current_tracer")

    # Enable block events (best-effort with warning)
    for event in _BLOCK_EVENTS:
        path = f"{tracefs}/events/{event}/enable"
        r = _adb_shell(serial, f"echo 1 > {path}")
        if r.returncode != 0:
            logger.warning("avd_tracer.enable_event.failed", extra={"event": event, "stderr": r.stderr.strip()})

    # Start tracing (load-bearing — raise if this fails)
    r = _adb_shell(serial, f"echo 1 > {tracefs}/tracing_on")
    if r.returncode != 0:
        raise RuntimeError(f"Failed to enable tracing on {serial}: {r.stderr.strip()}")
    logger.info("avd_tracer.block_tracing.enabled", extra={"serial": serial})


def disable_block_tracing(serial: str, tracefs: str) -> None:
    """Stop tracing and disable block events."""
    _adb_shell(serial, f"echo 0 > {tracefs}/tracing_on")
    for event in _BLOCK_EVENTS:
        path = f"{tracefs}/events/{event}/enable"
        _adb_shell(serial, f"echo 0 > {path}")


def run_io_workload(serial: str, block_count: int = 256) -> None:
    """Run a synthetic I/O workload on the device using dd.

    Writes `block_count * 4KB` to /sdcard/dgs_test_io.bin.
    """
    cmd = f"dd if=/dev/zero of=/sdcard/dgs_test_io.bin bs=4096 count={block_count} conv=fsync"
    result = _adb(serial, "shell", cmd, timeout=60)
    logger.info("avd_tracer.io_workload.done", extra={"output": result.stderr.strip() or "ok"})


def dump_trace(serial: str, tracefs: str) -> None:
    """Dump current trace to a file on the device."""
    _adb_shell(serial, f"cat {tracefs}/trace > {_DEVICE_TRACE_PATH}")


def pull_trace(serial: str, output_path: str) -> str:
    """Pull the trace file from device to host.

    Returns the output_path on success.
    """
    result = _adb(serial, "pull", _DEVICE_TRACE_PATH, output_path, timeout=30)
    if result.returncode != 0:
        raise RuntimeError(f"adb pull failed: {result.stderr}")
    return output_path


def capture_block_trace(
    serial: str,
    output_path: str,
    duration_sec: int = 5,
    block_count: int = 256,
) -> str:
    """Full capture pipeline: enable → workload → disable → pull.

    Args:
        serial: adb device serial (e.g. "emulator-5554").
        output_path: Host path to save the trace file.
        duration_sec: Seconds to wait after enabling tracing (before workload).
        block_count: Number of 4KB blocks to write for the workload.

    Returns:
        output_path on success.

    Raises:
        RuntimeError: If adb commands fail or tracefs not found.
    """
    tracefs = find_tracefs(serial)
    logger.info("avd_tracer.capture_block_trace", extra={"serial": serial, "tracefs": tracefs, "output": output_path})

    try:
        enable_block_tracing(serial, tracefs)
        if duration_sec > 0:
            time.sleep(duration_sec)
        run_io_workload(serial, block_count)
        disable_block_tracing(serial, tracefs)
        dump_trace(serial, tracefs)
        return pull_trace(serial, output_path)
    except Exception:
        # Always try to disable tracing on failure
        try:
            disable_block_tracing(serial, tracefs)
        except Exception:
            pass
        raise
