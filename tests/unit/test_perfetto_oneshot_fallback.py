from __future__ import annotations

from unittest.mock import MagicMock, patch

from data_graph_studio.ui.dialogs.trace_progress_dialog import PerfettoTraceController


def test_start_trace_uses_oneshot_command() -> None:
    ctrl = PerfettoTraceController()

    proc = MagicMock()
    proc.poll.return_value = None
    proc.pid = 4242

    with (
        patch.object(ctrl, "find_trace_processor", return_value="/tmp/trace_processor"),
        patch("subprocess.Popen", return_value=proc) as mock_popen,
        patch("time.sleep", return_value=None),
    ):
        ctrl.start_trace(
            "SERIAL123",
            {
                "buffer_size_mb": 64,
                "events": ["block/block_rq_issue", "block/block_rq_complete"],
                "duration_s": 10,
                "device_trace_path": "/data/misc/perfetto-traces/blocktrace.pftrace",
            },
        )

    assert ctrl._tracing is True

    cmd = mock_popen.call_args.args[0]
    assert cmd[:5] == ["adb", "-s", "SERIAL123", "shell", "perfetto"]
    assert "--time" in cmd and "10s" in cmd
    assert "--buffer" in cmd and "64mb" in cmd
    assert "block/block_rq_issue" in cmd
    assert "block/block_rq_complete" in cmd
    assert "/data/misc/perfetto-traces/blocktrace.pftrace" in cmd
