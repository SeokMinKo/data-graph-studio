import logging
from data_graph_studio.core.logging_utils import StructuredFormatter

def test_structured_formatter_outputs_key_value():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0,
        msg="data loaded", args=(),
        exc_info=None
    )
    output = formatter.format(record)
    assert "level=INFO" in output
    assert "msg=data loaded" in output

def test_structured_formatter_includes_extra_fields():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.ERROR,
        pathname="", lineno=0,
        msg="parse error", args=(),
        exc_info=None
    )
    record.__dict__["error"] = "unexpected EOF"
    output = formatter.format(record)
    assert "error=unexpected EOF" in output

def test_structured_formatter_includes_timestamp():
    formatter = StructuredFormatter()
    record = logging.LogRecord(
        name="test", level=logging.INFO,
        pathname="", lineno=0,
        msg="test", args=(),
        exc_info=None
    )
    output = formatter.format(record)
    assert "ts=" in output
