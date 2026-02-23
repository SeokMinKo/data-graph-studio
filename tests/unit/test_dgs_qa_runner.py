from pathlib import Path
from unittest.mock import MagicMock, patch
from data_graph_studio.tools.dgs_qa_runner import QARunner, QAResult, build_report


def test_qa_result_has_required_fields():
    r = QAResult(dataset="01_sales.csv", scenario="load", status="pass",
                 screenshot=Path("/tmp/foo.png"), notes="")
    assert r.dataset == "01_sales.csv"
    assert r.status == "pass"
    assert r.ipc_response is None


def test_runner_builds_scenario_list():
    runner = QARunner(data_dir=Path("/fake"), output_dir=Path("/tmp"))
    scenarios = runner._build_scenarios(
        dataset_path=Path("/fake/01_sales.csv"),
        columns=["region", "sales"]
    )
    names = [s["name"] for s in scenarios]
    assert "filter" in names
    assert "chart_bar" in names
    assert "chart_line" in names
    assert "chart_scatter" in names
    assert "clear_filters" in names


def test_runner_connect_returns_none_when_dgs_not_running():
    runner = QARunner(data_dir=Path("/fake"), output_dir=Path("/tmp"))
    with patch("data_graph_studio.tools.dgs_qa_runner.IPCClient") as MockClient:
        instance = MockClient.return_value
        instance.connect.return_value = False
        result = runner._connect_to_dgs()
    assert result is None


def test_build_report_creates_markdown(tmp_path):
    results = [
        QAResult(dataset="01_sales.csv", scenario="load", status="pass",
                 screenshot=Path("/tmp/x.png"), notes="ok"),
        QAResult(dataset="01_sales.csv", scenario="filter", status="warn",
                 screenshot=Path("/tmp/y.png"), notes="slow"),
    ]
    report_path = tmp_path / "report.md"
    build_report(results, report_path)
    content = report_path.read_text()
    assert "01_sales.csv" in content
    assert "pass" in content
    assert "warn" in content
