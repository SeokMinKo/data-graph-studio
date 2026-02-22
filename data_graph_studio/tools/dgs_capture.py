"""
dgs_capture — CLI tool for AI-driven panel screenshot capture.

Usage:
    # Connect to running DGS
    python -m data_graph_studio.tools.dgs_capture --connect --target all

    # Specific panel
    python -m data_graph_studio.tools.dgs_capture --connect --target graph_panel

    # Headless (launch + capture + exit)
    python -m data_graph_studio.tools.dgs_capture --headless --target all
"""
import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any, Dict

from data_graph_studio.core.ipc_server import IPCClient

logger = logging.getLogger(__name__)


def run_connect_mode(target: str, output_dir: Path, fmt: str = "png") -> Dict[str, Any]:
    """
    Connect to a running DGS instance via IPC and send a capture command.

    Inputs: target (panel name or "all"), output_dir, fmt
    Outputs: dict with "status" and "captures"
    Raises: nothing — errors returned in dict
    """
    client = IPCClient()
    if not client.connect():
        return {"status": "error", "message": "DGS not running — start DGS first"}

    try:
        response = client.send_command(
            "capture",
            target=target,
            output_dir=str(output_dir),
            format=fmt
        )
        return response
    except Exception as exc:
        logger.warning("dgs_capture.ipc_error", extra={"error": str(exc)})
        return {"status": "error", "message": str(exc)}
    finally:
        client.disconnect()


def run_headless_mode(target: str, output_dir: Path, data_path: str = None) -> Dict[str, Any]:
    """
    Launch DGS in offscreen mode, capture panels, then exit.

    Inputs: target, output_dir, optional data_path to load
    Outputs: dict with "status" and "captures"
    """
    import subprocess

    args = [
        sys.executable, "-m", "data_graph_studio",
        "--capture-mode",
        "--capture-target", target,
        "--capture-output", str(output_dir),
    ]
    if data_path:
        args += ["--data", data_path]

    result_file = output_dir / "_capture_result.json"
    args += ["--capture-result-file", str(result_file)]

    output_dir.mkdir(parents=True, exist_ok=True)

    proc = subprocess.run(args, timeout=30, capture_output=True, text=True)

    if result_file.exists():
        return json.loads(result_file.read_text())
    return {"status": "error", "message": proc.stderr or "headless capture failed"}


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="DGS Panel Capture Tool (AI use)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--connect", action="store_true", help="Connect to running DGS")
    mode.add_argument("--headless", action="store_true", help="Launch DGS headless")

    parser.add_argument("--target", default="all",
                        help="Panel name, 'all', or 'window' (default: all)")
    parser.add_argument("--output-dir", default="/tmp/dgs_captures", type=Path)
    parser.add_argument("--data", help="Data file to load (headless mode only)")
    parser.add_argument("--format", default="png", dest="fmt")

    args = parser.parse_args()

    if args.connect:
        result = run_connect_mode(args.target, args.output_dir, args.fmt)
    else:
        result = run_headless_mode(args.target, args.output_dir, args.data)

    print(json.dumps(result, indent=2, default=str))


if __name__ == "__main__":
    main()
