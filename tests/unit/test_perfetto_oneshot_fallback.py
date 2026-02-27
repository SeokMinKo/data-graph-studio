from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from data_graph_studio.ui.dialogs.trace_progress_dialog import PerfettoTraceController


def test_start_trace_falls_back_to_oneshot_command_on_config_failure() -> None:
    ctrl = PerfettoTraceController()

    # 1st popen: config mode exits immediately with permission error
    first = MagicMock()
    first.poll.return_value = 1
    first.communicate.return_value = (b"", b"Permission denied")
    first.returncode = 1

    # 2nd popen: oneshot mode starts successfully
    second = MagicMock()
    second.poll.return_value = None
    second.pid = 4242

    with patch.object(ctrl, "find_trace_processor", return_value="/tmp/trace_processor"), \
         patch("subprocess.run") as mock_run, \
         patch("subprocess.Popen", side_effect=[first, second]) as mock_popen, \
         patch("time.sleep", return_value=None):

        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout="", stderr=""
        )

        ctrl.start_trace(
            "SERIAL123",
            {
                "buffer_size_mb": 64,
                "events": ["block/block_rq_issue", "block/block_rq_complete"],
                "duration_s": 10,
            },
        )

    assert ctrl._tracing is True

    # Verify second Popen command is the field-proven oneshot form
    second_cmd = mock_popen.call_args_list[1].args[0]
    assert second_cmd[:5] == ["adb", "-s", "SERIAL123", "shell", "perfetto"]
    assert "--time" in second_cmd and "10s" in second_cmd
    assert "--buffer" in second_cmd and "64mb" in second_cmd
    assert "block/block_rq_issue" in second_cmd
    assert "block/block_rq_complete" in second_cmd
    assert "/data/misc/perfetto-traces/blocktrace.pftrace" in second_cmd
