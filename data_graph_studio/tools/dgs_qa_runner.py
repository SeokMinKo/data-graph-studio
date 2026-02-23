"""
DGS QA Runner — automated UI/UX inspection via IPC.

Launches DGS, drives scenarios across all test datasets,
captures screenshots, writes a QA report.

Usage:
    python -m data_graph_studio.tools.dgs_qa_runner \\
        --data-dir test_data/ \\
        --output-dir docs/qa/ \\
        --connect
"""
import logging
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_graph_studio.core.ipc_server import IPCClient
from data_graph_studio.core.ipc_server import send_command as _ipc_send

logger = logging.getLogger(__name__)

CHART_TYPES = ["bar", "line", "scatter"]


@dataclass
class QAResult:
    """Result of a single QA scenario."""
    dataset: str
    scenario: str
    status: str           # "pass" | "warn" | "fail" | "skip"
    screenshot: Path
    notes: str
    ipc_response: Optional[Dict[str, Any]] = None


class QARunner:
    """
    Orchestrates QA scenarios across datasets via IPC.

    Inputs: data_dir (CSV/XLSX files), output_dir (screenshots + report)
    Outputs: List[QAResult], markdown report written to output_dir
    """

    def __init__(self, data_dir: Path, output_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._client: Optional[IPCClient] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_all(self, datasets: List[Path]) -> List[QAResult]:
        """Run QA scenarios on all datasets. Returns all results."""
        all_results: List[QAResult] = []
        for path in datasets:
            logger.info("qa_runner.dataset_start", extra={"file": path.name})
            results = self._run_dataset(path)
            all_results.extend(results)
        return all_results

    # ------------------------------------------------------------------
    # Dataset loop
    # ------------------------------------------------------------------

    def _run_dataset(self, path: Path) -> List[QAResult]:
        results: List[QAResult] = []

        # Load file
        load_resp = self._cmd("load_file", path=str(path))
        shot = self._capture(path.stem, "load")
        results.append(QAResult(
            dataset=path.name, scenario="load",
            status="pass" if load_resp and load_resp.get("status") == "ok" else "fail",
            screenshot=shot, notes=str(load_resp), ipc_response=load_resp
        ))

        # Get columns for filter scenario
        info = self._cmd("get_data_info") or {}
        columns: List[str] = info.get("columns", [])

        for scenario in self._build_scenarios(path, columns):
            result = self._run_scenario(path.name, path.stem, scenario)
            results.append(result)

        # Reset for next dataset
        self._cmd("clear_filters")
        return results

    def _build_scenarios(self, dataset_path: Path, columns: List[str]) -> List[Dict]:
        """Build ordered scenario list for a dataset."""
        scenarios = []

        # Filter scenario: use first non-id column
        filter_col = next((c for c in columns if c.lower() not in ("id",)), None)
        if filter_col:
            scenarios.append({
                "name": "filter",
                "cmd": "apply_filter",
                "kwargs": {"column": filter_col, "op": "eq", "value": ""},
                "post_capture": True,
            })

        # Chart type scenarios
        for ct in CHART_TYPES:
            scenarios.append({
                "name": f"chart_{ct}",
                "cmd": "set_chart_type",
                "kwargs": {"chart_type": ct},
                "post_capture": True,
            })

        # Clear filters
        scenarios.append({
            "name": "clear_filters",
            "cmd": "clear_filters",
            "kwargs": {},
            "post_capture": False,
        })

        return scenarios

    def _run_scenario(self, dataset_name: str, stem: str, scenario: Dict) -> QAResult:
        resp = self._cmd(scenario["cmd"], **scenario["kwargs"])
        shot = self._capture(stem, scenario["name"]) if scenario["post_capture"] else Path("/dev/null")
        status = "pass" if resp and resp.get("status") == "ok" else "warn"
        return QAResult(
            dataset=dataset_name, scenario=scenario["name"],
            status=status, screenshot=shot,
            notes=str(resp), ipc_response=resp
        )

    # ------------------------------------------------------------------
    # IPC helpers
    # ------------------------------------------------------------------

    def _connect_to_dgs(self) -> Optional["QARunner"]:
        """Verify DGS is reachable via IPC. Returns self or None."""
        try:
            resp = _ipc_send("ping")
            if resp == "pong" or (isinstance(resp, dict) and resp.get("status") != "error"):
                self._reachable = True
                return self
        except Exception:
            pass
        logger.warning("qa_runner.connect_failed")
        self._reachable = False
        return None

    def _cmd(self, command: str, **kwargs) -> Optional[Dict]:
        """Send IPC command via fresh connection each time (IPC is single-shot per conn)."""
        if not getattr(self, "_reachable", False):
            return None
        try:
            return _ipc_send(command, **kwargs)
        except Exception as exc:
            logger.warning("qa_runner.cmd_error", extra={"cmd": command, "error": str(exc)})
            return None

    def _capture(self, stem: str, scenario: str) -> Path:
        """Capture all panels, return path to first screenshot."""
        out_dir = self.output_dir / stem
        out_dir.mkdir(parents=True, exist_ok=True)
        resp = self._cmd("capture", target="all", output_dir=str(out_dir))
        if resp and resp.get("captures"):
            return Path(resp["captures"][0].get("file", "/dev/null"))
        return out_dir / f"{scenario}_no_capture.png"


# ------------------------------------------------------------------
# Report generation
# ------------------------------------------------------------------

def build_report(results: List[QAResult], output_path: Path) -> None:
    """Write markdown QA report from results list."""
    from datetime import date
    total = len(results)
    fails = sum(1 for r in results if r.status == "fail")
    warns = sum(1 for r in results if r.status == "warn")
    passes = total - fails - warns

    lines = [
        f"# DGS QA Report — {date.today()}",
        "",
        "## Summary",
        f"- Scenarios run: {total}",
        f"- Pass: {passes}  Warn: {warns}  Fail: {fails}",
        "",
        "## Results",
        "",
        "| Dataset | Scenario | Status | Notes |",
        "|---------|----------|--------|-------|",
    ]
    for r in results:
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(r.status, "?")
        notes = r.notes[:80].replace("|", "\\|")
        lines.append(f"| {r.dataset} | {r.scenario} | {icon} {r.status} | {notes} |")

    lines += ["", "## Screenshots", ""]
    for r in results:
        if r.screenshot.exists():
            lines.append(f"### {r.dataset} / {r.scenario}")
            lines.append(f"![{r.scenario}]({r.screenshot})")
            lines.append("")

    output_path.write_text("\n".join(lines))
    logger.info("qa_runner.report_written", extra={"path": str(output_path)})


# ------------------------------------------------------------------
# CLI
# ------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="DGS QA Runner")
    parser.add_argument("--data-dir", type=Path, default=Path("test_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/qa"))
    parser.add_argument("--connect", action="store_true",
                        help="Connect to already-running DGS")
    parser.add_argument("--datasets", nargs="*",
                        help="Specific filenames (default: all CSVs in data-dir)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")

    runner = QARunner(data_dir=args.data_dir, output_dir=args.output_dir)
    client = runner._connect_to_dgs()
    if client is None:
        print("Cannot connect to DGS. Start DGS first, then run with --connect.")
        sys.exit(1)

    if args.datasets:
        datasets = [args.data_dir / name for name in args.datasets]
    else:
        datasets = sorted(args.data_dir.glob("*.csv"))

    print(f"Running QA on {len(datasets)} datasets...")
    results = runner.run_all(datasets)

    report_path = args.output_dir / "qa-report.md"
    build_report(results, report_path)

    passes = sum(1 for r in results if r.status == "pass")
    warns = sum(1 for r in results if r.status == "warn")
    fails = sum(1 for r in results if r.status == "fail")
    print(f"Report saved to {report_path}")
    print(f"   Pass: {passes}  Warn: {warns}  Fail: {fails}")


if __name__ == "__main__":
    main()
