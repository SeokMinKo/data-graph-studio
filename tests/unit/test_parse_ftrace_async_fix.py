"""
Regression test: _parse_ftrace_async must call parser.parse() (full pipeline),
not parser.parse_raw() (step 1 only).

We test this by verifying that the converter runs and the result contains
block layer columns (d2c_ms) rather than raw event columns (event, details).
"""


BLOCK_TRACE = """\
     kworker/0:1-100 [000] .... 1000.000000: block_rq_issue: 8,0 R 4096 () 1000 + 8 [kworker]
     kworker/0:1-100 [000] .... 1000.001000: block_rq_complete: 8,0 R () 1000 + 8 [0]
"""


def test_ftrace_parser_parse_produces_block_layer_columns(tmp_path):
    """parser.parse() with converter=blocklayer must produce d2c_ms, queue_depth."""
    from data_graph_studio.parsers.ftrace_parser import FtraceParser

    trace_file = tmp_path / "trace.txt"
    trace_file.write_text(BLOCK_TRACE)

    parser = FtraceParser()
    settings = parser.default_settings()
    settings["converter"] = "blocklayer"

    df = parser.parse(str(trace_file), settings)

    assert "d2c_ms" in df.columns, f"d2c_ms missing. Got: {df.columns}"
    assert "queue_depth" in df.columns, f"queue_depth missing. Got: {df.columns}"
    assert len(df) >= 1


def test_ftrace_parser_parse_raw_does_not_produce_block_layer_columns(tmp_path):
    """parser.parse_raw() must NOT produce d2c_ms — that's the bug we're fixing.

    parse_raw() is step 1 only (raw events). The async wrapper was calling this
    instead of parse() (full pipeline), so the blocklayer converter never ran.
    """
    from data_graph_studio.parsers.ftrace_parser import FtraceParser

    trace_file = tmp_path / "trace.txt"
    trace_file.write_text(BLOCK_TRACE)

    parser = FtraceParser()
    settings = parser.default_settings()
    settings["converter"] = "blocklayer"

    # parse_raw = step 1 only, no conversion
    df = parser.parse_raw(str(trace_file), settings)

    # Raw output has event columns, NOT block layer analysis columns
    assert "event" in df.columns, "parse_raw should have 'event' column"
    assert "d2c_ms" not in df.columns, "parse_raw should NOT have d2c_ms (no conversion)"
