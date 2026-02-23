# data_graph_studio/tools/dgs_avd_qa_runner.py
"""DGS AVD Block Layer QA Runner.

End-to-end validation of DGS Logger → FtraceParser → Profile → Graph
against a live Android Virtual Device.

Usage:
    # Start DGS first, then AVD
    .venv/bin/python -m data_graph_studio.tools.dgs_avd_qa_runner

    # Or with explicit device:
    .venv/bin/python -m data_graph_studio.tools.dgs_avd_qa_runner --device emulator-5554

    # Use pre-captured trace file (skip AVD):
    .venv/bin/python -m data_graph_studio.tools.dgs_avd_qa_runner --trace-file /path/to/trace.txt
"""
from __future__ import annotations

import argparse
import datetime
import json
import logging
import socket
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import polars as pl

from data_graph_studio.core.ipc_server import read_port_file
from data_graph_studio.core.constants import IPC_DEFAULT_PORT

logger = logging.getLogger("avd_qa_runner")

# IPC settings (must match DGS ipc_server.py)
IPC_HOST = "127.0.0.1"
# Port is discovered at runtime via ~/.dgs/ipc_port; IPC_DEFAULT_PORT is the fallback.
IPC_PORT = IPC_DEFAULT_PORT

# Block layer columns produced by the blocklayer converter
REQUIRED_BLOCK_COLUMNS = [
    "d2c_ms",
    "queue_depth",
    "iops",
    "cmd",
    "size_kb",
]

REPORT_DIR = Path("docs/qa/avd")

# ── IPC helpers ────────────────────────────────────────────────────────


def _ipc_send(payload: Dict[str, Any], timeout: float = 30.0) -> Dict[str, Any]:
    """Send a single IPC command and return the parsed response.

    The server terminates every response with ``\\n``; we read until we see it
    so that large payloads spanning multiple TCP segments are reassembled
    correctly.
    """
    port = read_port_file() or IPC_PORT
    data = json.dumps(payload).encode()
    with socket.create_connection((IPC_HOST, port), timeout=timeout) as sock:
        sock.sendall(data)
        chunks = b""
        while b"\n" not in chunks:
            chunk = sock.recv(4096)
            if not chunk:
                break
            chunks += chunk
        response = chunks
    return json.loads(response)


def _wait_for_dataset(
    poll_interval: float = 0.5,
    timeout: float = 30.0,
) -> bool:
    """Poll DGS via get_state until a dataset loads (data_loaded=True).

    Returns True if data appeared within timeout.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            resp = _ipc_send({"command": "get_state"}, timeout=5)
            if isinstance(resp, dict) and resp.get("data_loaded"):
                return True
        except Exception:
            pass
        time.sleep(poll_interval)
    return False


# ── Verification ───────────────────────────────────────────────────────


def _verify_block_layer_columns(df: pl.DataFrame) -> Dict[str, Any]:
    """Check that df contains expected block layer output columns."""
    missing = [col for col in REQUIRED_BLOCK_COLUMNS if col not in df.columns]
    return {
        "pass": len(missing) == 0,
        "missing": missing,
        "columns_found": list(df.columns),
    }


# ── Report ─────────────────────────────────────────────────────────────


def _build_report(scenarios: List[Dict], device: str) -> str:
    """Build markdown QA report."""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total = len(scenarios)
    passed = sum(1 for s in scenarios if s["status"] == "PASS")
    failed = sum(1 for s in scenarios if s["status"] == "FAIL")
    warned = sum(1 for s in scenarios if s["status"] == "WARN")

    lines = [
        "# DGS AVD Block Layer QA Report",
        "",
        f"**Generated:** {now}  ",
        f"**Device:** `{device}`  ",
        f"**Result:** {passed} pass / {warned} warn / {failed} fail / {total} total",
        "",
        "---",
        "",
        "| Scenario | Status | Notes |",
        "|----------|--------|-------|",
    ]
    for s in scenarios:
        icon = "✅" if s["status"] == "PASS" else ("⚠️" if s["status"] == "WARN" else "❌")
        lines.append(f"| {s['name']} | {icon} {s['status']} | {s.get('notes', '')} |")

    return "\n".join(lines) + "\n"


# ── Main QA flow ───────────────────────────────────────────────────────


def _write_report(scenarios: List[Dict], device: str, out_dir: Path) -> None:
    report = _build_report(scenarios, device)
    report_path = out_dir / "avd-qa-report.md"
    report_path.write_text(report)
    print(report)
    print(f"\nReport saved to {report_path}")


def run_avd_qa(
    device: Optional[str] = None,
    trace_file: Optional[str] = None,
    duration_sec: int = 5,
    block_count: int = 256,
    report_dir: Optional[str] = None,
) -> int:
    """Run the full AVD block layer QA.

    Returns 0 on success, 1 if any scenario fails.
    """
    from data_graph_studio.tools.avd_tracer import capture_block_trace, list_devices

    out_dir = Path(report_dir or REPORT_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    scenarios: List[Dict] = []

    # ── Step 1: Connect to DGS ─────────────────────────────────────────
    logger.info("step1: connect to DGS")
    try:
        resp = _ipc_send({"command": "ping"}, timeout=5)
        if resp != "pong" and not (isinstance(resp, dict) and resp.get("status") != "error"):
            logger.error("DGS ping failed: %s", resp)
            print("Cannot connect to DGS. Start DGS first, then run this script.")
            return 1
        scenarios.append({"name": "dgs_connect", "status": "PASS", "notes": "pong"})
    except Exception as e:
        print(f"Cannot connect to DGS IPC: {e}\nStart DGS first.")
        return 1

    # ── Step 2: Find AVD (or use pre-captured trace) ───────────────────
    trace_path: Optional[str] = trace_file
    if trace_path is None:
        logger.info("step2: find AVD device")
        if device is None:
            devices = list_devices()
            avd_devices = [d for d in devices if d.startswith("emulator-")]
            if not avd_devices:
                logger.error("No running AVD found.")
                print("No running AVD found. Start an AVD with:")
                print("  emulator -avd <name> -no-snapshot-load &")
                print("Or provide a pre-captured trace with --trace-file")
                return 1
            device = avd_devices[0]
        logger.info("using device: %s", device)
        scenarios.append({"name": "avd_connect", "status": "PASS",
                          "notes": f"serial={device}"})

        # ── Step 3: Capture trace ──────────────────────────────────────
        logger.info("step3: capture block layer trace on %s", device)
        trace_path = str(out_dir / "block_trace.txt")
        try:
            capture_block_trace(
                device,
                output_path=trace_path,
                duration_sec=duration_sec,
                block_count=block_count,
            )
            size = Path(trace_path).stat().st_size
            scenarios.append({"name": "trace_capture", "status": "PASS",
                               "notes": f"{size:,} bytes"})
        except Exception as e:
            logger.error("trace capture failed: %s", e)
            scenarios.append({"name": "trace_capture", "status": "FAIL",
                               "notes": str(e)})
            _write_report(scenarios, device or "unknown", out_dir)
            return 1
    else:
        logger.info("step2: using pre-captured trace: %s", trace_path)
        device = device or "pre-captured"
        scenarios.append({"name": "avd_connect", "status": "WARN",
                          "notes": "using pre-captured trace, no AVD"})
        scenarios.append({"name": "trace_capture", "status": "PASS",
                          "notes": f"pre-captured: {Path(trace_path).name}"})

    # ── Step 4: Parse ftrace via IPC ───────────────────────────────────
    logger.info("step4: parse ftrace via IPC")
    try:
        resp = _ipc_send({"command": "parse_ftrace", "args": {"file_path": trace_path}})
        if resp.get("status") != "ok":
            raise RuntimeError(f"parse_ftrace IPC error: {resp}")

        loaded = _wait_for_dataset(timeout=30)
        if not loaded:
            raise RuntimeError("Timeout waiting for dataset to load after parse_ftrace")

        scenarios.append({"name": "parse_ftrace", "status": "PASS",
                          "notes": "dataset loaded"})
    except Exception as e:
        logger.error("parse_ftrace failed: %s", e)
        scenarios.append({"name": "parse_ftrace", "status": "FAIL",
                          "notes": str(e)})
        _write_report(scenarios, device, out_dir)
        return 1

    # ── Step 5: Verify block layer columns ────────────────────────────
    logger.info("step5: verify block layer columns")
    try:
        from data_graph_studio.parsers.ftrace_parser import FtraceParser
        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        df = parser.parse(trace_path, settings)

        check = _verify_block_layer_columns(df)
        if check["pass"]:
            scenarios.append({"name": "block_layer_columns", "status": "PASS",
                               "notes": f"{len(df)} rows, cols: {', '.join(REQUIRED_BLOCK_COLUMNS)}"})
        else:
            scenarios.append({"name": "block_layer_columns", "status": "FAIL",
                               "notes": f"missing: {check['missing']}"})
    except Exception as e:
        scenarios.append({"name": "block_layer_columns", "status": "FAIL",
                          "notes": str(e)})

    # ── Step 6: Capture screenshots ────────────────────────────────────
    logger.info("step6: capture screenshots")
    screenshots = []
    try:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        for target in ["graph_panel", "summary_panel", "table_panel"]:
            path = str(out_dir / f"{target}_{ts}.png")
            resp = _ipc_send({
                "command": "capture",
                "args": {"target": target, "path": path},
            })
            if resp.get("status") == "ok":
                screenshots.append(path)

        target_count = 3  # graph_panel, summary_panel, table_panel
        status = "PASS" if len(screenshots) == target_count else "WARN"
        scenarios.append({"name": "screenshot", "status": status,
                          "notes": f"{len(screenshots)}/{target_count} captures"})
    except Exception as e:
        scenarios.append({"name": "screenshot", "status": "WARN",
                          "notes": str(e)})

    # ── Step 7: Write report ───────────────────────────────────────────
    _write_report(scenarios, device, out_dir)
    failures = sum(1 for s in scenarios if s["status"] == "FAIL")
    return 1 if failures > 0 else 0


def main() -> None:
    """CLI entry point."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    parser = argparse.ArgumentParser(description="DGS AVD Block Layer QA Runner")
    parser.add_argument("--device", help="adb device serial (default: auto-detect AVD)")
    parser.add_argument("--trace-file", help="Pre-captured trace file (skip AVD)")
    parser.add_argument("--duration", type=int, default=5,
                        help="Trace duration in seconds (default: 5)")
    parser.add_argument("--block-count", type=int, default=256,
                        help="I/O workload size in 4KB blocks (default: 256)")
    parser.add_argument("--report-dir", help="Output directory for report and screenshots")
    args = parser.parse_args()

    import sys
    sys.exit(run_avd_qa(
        device=args.device,
        trace_file=args.trace_file,
        duration_sec=args.duration,
        block_count=args.block_count,
        report_dir=args.report_dir,
    ))


if __name__ == "__main__":
    main()
