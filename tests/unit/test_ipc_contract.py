"""Contract tests for IPC protocol schema.

Verifies that parse_request and response builders enforce the protocol
contract regardless of internal implementation changes.
"""
import pytest

from data_graph_studio.core.ipc_protocol import (
    make_error_response,
    make_ok_response,
    parse_request,
)


class TestParseRequest:
    def test_valid_request_returns_typed_dict(self):
        result = parse_request({"command": "get_state", "args": {"key": "val"}})
        assert result["command"] == "get_state"
        assert result["args"] == {"key": "val"}

    def test_missing_command_raises_value_error(self):
        with pytest.raises(ValueError, match="command"):
            parse_request({"args": {}})

    def test_non_string_command_raises_value_error(self):
        with pytest.raises(ValueError, match="str"):
            parse_request({"command": 42})

    def test_missing_args_defaults_to_empty_dict(self):
        result = parse_request({"command": "ping"})
        assert result["args"] == {}

    def test_extra_keys_ignored(self):
        result = parse_request({"command": "ping", "args": {}, "extra": "ignored"})
        assert result["command"] == "ping"

    def test_empty_command_string_is_allowed(self):
        # Empty command is valid at parse level; dispatch layer rejects it
        result = parse_request({"command": ""})
        assert result["command"] == ""


class TestResponseBuilders:
    def test_ok_response_has_ok_status(self):
        r = make_ok_response(data=[1, 2, 3])
        assert r["status"] == "ok"
        assert r["data"] == [1, 2, 3]

    def test_error_response_has_error_status(self):
        r = make_error_response("unknown command: foo")
        assert r["status"] == "error"
        assert "foo" in r["message"]

    def test_ok_response_with_no_extra_fields(self):
        r = make_ok_response()
        assert r == {"status": "ok"}
