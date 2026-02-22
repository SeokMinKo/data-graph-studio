# DGS QA Automation Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Automatically launch DGS, run interaction scenarios across 10 test datasets, capture screenshots, analyze with Vision, report issues and fix bugs.

**Architecture:** QA runner script launches DGS subprocess, drives it via existing IPC (load_file, set_chart_type, capture, etc.) plus two new filter commands, then reads screenshots for Vision analysis and writes a report.

**Tech Stack:** Python asyncio, data_graph_studio IPC client (`IPCClient`), subprocess, PySide6 (inside DGS process only), Claude Vision via Read tool on PNG files.

---

## Task 1: Add `apply_filter` + `clear_filters` IPC Commands

**Files:**
- Modify: `data_graph_studio/ui/controllers/ipc_controller.py`
- Test: `tests/unit/test_ipc_filter_handlers.py`

### Step 1: Write the failing tests

Create `tests/unit/test_ipc_filter_handlers.py`:

```python
from unittest.mock import MagicMock, patch
from data_graph_studio.ui.controllers.ipc_controller import IPCController


def _make_controller():
    """Build IPCController with a mock MainWindow."""
    w = MagicMock()
    w.state.add_filter = MagicMock()
    w.state.clear_filters = MagicMock()
    w.engine.apply_filters = MagicMock()
    w.graph_panel.refresh = MagicMock()
    w.table_panel.refresh = MagicMock()
    ctrl = IPCController.__new__(IPCController)
    ctrl._w = w
    return ctrl


def test_ipc_apply_filter_calls_state():
    ctrl = _make_controller()
    result = ctrl._ipc_apply_filter(column="region", op="eq", value="Asia")
    ctrl._w.state.add_filter.assert_called_once_with("region", "eq", "Asia")
    assert result["status"] == "ok"


def test_ipc_clear_filters_calls_state():
    ctrl = _make_controller()
    result = ctrl._ipc_clear_filters()
    ctrl._w.state.clear_filters.assert_called_once()
    assert result["status"] == "ok"


def test_ipc_apply_filter_returns_error_on_exception():
    ctrl = _make_controller()
    ctrl._w.state.add_filter.side_effect = ValueError("bad column")
    result = ctrl._ipc_apply_filter(column="nope", op="eq", value="x")
    assert result["status"] == "error"
    assert "bad column" in result["message"]
```

### Step 2: Run to verify FAIL

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_ipc_filter_handlers.py -v 2>&1 | head -20
```
Expected: `AttributeError: '_ipc_apply_filter'` — method doesn't exist yet.

### Step 3: Add handlers to IPCController

In `data_graph_studio/ui/controllers/ipc_controller.py`, inside `setup()` after the `capture` handler line:

```python
server.register_handler('apply_filter', self._ipc_apply_filter)
server.register_handler('clear_filters', self._ipc_clear_filters)
```

Then add the methods (after `_ipc_capture`):

```python
def _ipc_apply_filter(self, column: str, op: str, value: Any) -> dict:
    """
    Add a filter condition.

    Inputs: column name, operator ("eq","gt","lt","contains"), value
    Outputs: {"status": "ok"} or {"status": "error", "message": ...}
    """
    try:
        self._w.state.add_filter(column, op, value)
        return {"status": "ok", "column": column, "op": op, "value": value}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}

def _ipc_clear_filters(self) -> dict:
    """
    Remove all active filters.

    Outputs: {"status": "ok"}
    """
    try:
        self._w.state.clear_filters()
        return {"status": "ok"}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}
```

Note: `Any` is already imported at the top of the file. Check with `grep "from typing" ipc_controller.py`.

### Step 4: Run tests to verify PASS

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_ipc_filter_handlers.py -v
```
Expected: 3 PASS.

### Step 5: Full suite regression check

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -5
```
Expected: 2052+ passed, 0 failures.

### Step 6: Commit

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/ui/controllers/ipc_controller.py tests/unit/test_ipc_filter_handlers.py && git commit -m "feat: add apply_filter + clear_filters IPC commands"
```

---

## Task 2: Build `tools/dgs_qa_runner.py`

**Files:**
- Create: `data_graph_studio/tools/dgs_qa_runner.py`
- Test: `tests/unit/test_dgs_qa_runner.py`

### Step 1: Write the failing tests

Create `tests/unit/test_dgs_qa_runner.py`:

```python
from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.tools.dgs_qa_runner import QARunner, QAResult


def test_qa_result_has_required_fields():
    r = QAResult(dataset="01_sales.csv", scenario="load", status="pass",
                 screenshot=Path("/tmp/foo.png"), notes="")
    assert r.dataset == "01_sales.csv"
    assert r.status == "pass"


def test_runner_builds_scenario_list():
    runner = QARunner(data_dir=Path("/fake"), output_dir=Path("/tmp"))
    scenarios = runner._build_scenarios(
        dataset_path=Path("/fake/01_sales.csv"),
        columns=["region", "sales"]
    )
    names = [s["name"] for s in scenarios]
    assert "load" in names
    assert "filter" in names
    assert "chart_bar" in names
    assert "chart_line" in names


def test_runner_connects_or_returns_error():
    runner = QARunner(data_dir=Path("/fake"), output_dir=Path("/tmp"))
    with patch("data_graph_studio.tools.dgs_qa_runner.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = False
        result = runner._connect_to_dgs()
    assert result is None
```

### Step 2: Run to verify FAIL

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_dgs_qa_runner.py -v 2>&1 | head -15
```
Expected: ImportError.

### Step 3: Create `data_graph_studio/tools/dgs_qa_runner.py`

```python
"""
DGS QA Runner — automated UI/UX inspection via IPC.

Launches DGS, drives scenarios across all test datasets,
captures screenshots, writes a QA report.

Usage:
    python -m data_graph_studio.tools.dgs_qa_runner \\
        --data-dir test_data/ \\
        --output-dir docs/qa/
"""
import json
import logging
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from data_graph_studio.core.ipc_server import IPCClient

logger = logging.getLogger(__name__)

CHART_TYPES = ["bar", "line", "scatter"]


@dataclass
class QAResult:
    dataset: str
    scenario: str
    status: str           # "pass" | "warn" | "fail" | "skip"
    screenshot: Path
    notes: str
    ipc_response: Optional[Dict[str, Any]] = None


class QARunner:
    """
    Orchestrates QA scenarios across datasets.

    Inputs: data_dir (folder with CSV/XLSX files), output_dir (screenshots + report)
    Outputs: List[QAResult], markdown report
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

        # Filter scenario: use first non-numeric column if any
        filter_col = next((c for c in columns if c not in ("id",)), None)
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

        # Clear filters + state check
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

    def _connect_to_dgs(self) -> Optional[IPCClient]:
        client = IPCClient()
        if not client.connect():
            logger.warning("qa_runner.connect_failed")
            return None
        self._client = client
        return client

    def _cmd(self, command: str, **kwargs) -> Optional[Dict]:
        if self._client is None:
            return None
        try:
            return self._client.send_command(command, **kwargs)
        except Exception as exc:
            logger.warning("qa_runner.cmd_error", extra={"cmd": command, "error": str(exc)})
            return None

    def _capture(self, stem: str, scenario: str) -> Path:
        out_dir = self.output_dir / stem
        out_dir.mkdir(parents=True, exist_ok=True)
        resp = self._cmd("capture", target="all", output_dir=str(out_dir))
        if resp and resp.get("captures"):
            return Path(resp["captures"][0].get("file", "/dev/null"))
        return out_dir / f"{scenario}_failed.png"


# ------------------------------------------------------------------
# Report generation
# ------------------------------------------------------------------

def build_report(results: List[QAResult], output_path: Path) -> None:
    """Write markdown QA report from results list."""
    from datetime import date
    total = len(results)
    fails = sum(1 for r in results if r.status == "fail")
    warns = sum(1 for r in results if r.status == "warn")

    lines = [
        f"# DGS QA Report — {date.today()}",
        "",
        "## Summary",
        f"- Scenarios run: {total}",
        f"- Pass: {total - fails - warns}  Warn: {warns}  Fail: {fails}",
        "",
        "## Results",
        "",
        "| Dataset | Scenario | Status | Notes |",
        "|---------|----------|--------|-------|",
    ]
    for r in results:
        icon = {"pass": "✅", "warn": "⚠️", "fail": "❌", "skip": "⏭️"}.get(r.status, "?")
        lines.append(f"| {r.dataset} | {r.scenario} | {icon} {r.status} | {r.notes[:80]} |")

    lines += ["", "## Screenshots", ""]
    for r in results:
        if r.screenshot.exists():
            lines.append(f"### {r.dataset} / {r.scenario}")
            lines.append(f"![{r.scenario}]({r.screenshot})")
            lines.append("")

    output_path.write_text("\n".join(lines))
    logger.info("qa_runner.report_written", extra={"path": str(output_path)})


# ------------------------------------------------------------------
# CLI entry point
# ------------------------------------------------------------------

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="DGS QA Runner")
    parser.add_argument("--data-dir", type=Path, default=Path("test_data"))
    parser.add_argument("--output-dir", type=Path, default=Path("docs/qa"))
    parser.add_argument("--connect", action="store_true",
                        help="Connect to already-running DGS (default: launch new)")
    parser.add_argument("--datasets", nargs="*",
                        help="Specific dataset filenames (default: all in data-dir)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO)

    runner = QARunner(data_dir=args.data_dir, output_dir=args.output_dir)

    if not args.connect:
        print("Launch DGS manually and pass --connect, or use --connect with running DGS.")
        print("Trying to connect anyway...")

    client = runner._connect_to_dgs()
    if client is None:
        print("❌ Cannot connect to DGS. Is it running?")
        sys.exit(1)

    # Select datasets
    if args.datasets:
        datasets = [args.data_dir / name for name in args.datasets]
    else:
        datasets = sorted(args.data_dir.glob("*.csv"))

    print(f"Running QA on {len(datasets)} datasets...")
    results = runner.run_all(datasets)

    report_path = args.output_dir / "qa-report.md"
    build_report(results, report_path)
    print(f"✅ Report saved to {report_path}")
    print(f"   Pass: {sum(1 for r in results if r.status=='pass')}  "
          f"Warn: {sum(1 for r in results if r.status=='warn')}  "
          f"Fail: {sum(1 for r in results if r.status=='fail')}")


if __name__ == "__main__":
    main()
```

### Step 4: Run tests to verify PASS

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/unit/test_dgs_qa_runner.py -v
```
Expected: 3 PASS.

### Step 5: Full suite check

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -5
```

### Step 6: Commit

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add data_graph_studio/tools/dgs_qa_runner.py tests/unit/test_dgs_qa_runner.py && git commit -m "feat: add QA runner with IPC-driven scenarios and report generation"
```

---

## Task 3: Run QA + Analyze Screenshots

> This task is operational — run the tool, then use Claude Vision to analyze each screenshot.

### Step 1: Launch DGS (in background)

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && python -m data_graph_studio &
sleep 5  # wait for IPC server to start
```

### Step 2: Run QA runner

```bash
cd /Users/lov2fn/Projects/data-graph-studio && source .venv/bin/activate && python -m data_graph_studio.tools.dgs_qa_runner \
    --connect \
    --data-dir test_data/ \
    --output-dir docs/qa/
```

### Step 3: Analyze screenshots with Claude Vision

For each PNG in `docs/qa/`:
- Read the image with the Read tool (Claude can see images)
- Check: panel rendered? data visible? layout issues? error messages?
- Note findings per dataset/scenario

### Step 4: Supplement QA report

Edit `docs/qa/qa-report.md` to add:
- Vision analysis findings per panel
- Specific bugs identified (with file:line references)
- Severity (Critical / Warning / Info)

### Step 5: Commit report

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git add docs/qa/ && git commit -m "docs: add QA run results and screenshots"
```

---

## Task 4: Fix Discovered Bugs

> This task will be defined during Task 3 based on findings.

For each Critical/Warning issue found:

1. Read the relevant source file to understand the bug
2. Write a failing regression test that reproduces it
3. Fix the code
4. Run full test suite to confirm fix
5. Commit with `fix: <description> (found in QA run)`

Pattern:
```bash
git add <changed_files>
git commit -m "fix: <what was wrong> — found in QA run 2026-02-23"
```

---

## Task 5: Final Merge

```bash
cd /Users/lov2fn/Projects/data-graph-studio && git checkout master && git merge qa/automated-inspection --no-ff -m "feat: QA automation + bug fixes from automated inspection" && git push origin master
```
