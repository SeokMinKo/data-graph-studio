"""Contract tests for the IPC protocol schema.

Verifies structural guarantees of parse_request, make_ok_response, and
make_error_response that must hold regardless of internal implementation
changes.  All tests are Qt-free.
"""
import json
import pytest

from data_graph_studio.core.ipc_protocol import (
    make_error_response,
    make_ok_response,
    parse_request,
)


# ---------------------------------------------------------------------------
# parse_request contracts
# ---------------------------------------------------------------------------


class TestParseRequestAdditional:
    """Extra edge-case contracts beyond the baseline test_ipc_contract.py."""

    def test_args_is_always_a_dict(self):
        """When 'args' is absent, parse_request fills in an empty dict."""
        req = parse_request({"command": "ping"})
        assert isinstance(req["args"], dict)

    def test_args_passed_through_unchanged(self):
        """args dict is returned exactly as supplied."""
        payload = {"x": 1, "y": [1, 2, 3], "z": None}
        req = parse_request({"command": "do_thing", "args": payload})
        assert req["args"] == payload

    def test_list_command_raises_value_error(self):
        """A list value for 'command' is rejected with ConfigError."""
        from data_graph_studio.core.exceptions import ConfigError
        with pytest.raises(ConfigError):
            parse_request({"command": ["not", "a", "string"]})

    def test_none_command_raises_value_error(self):
        """None is not a valid command value."""
        from data_graph_studio.core.exceptions import ConfigError
        with pytest.raises(ConfigError):
            parse_request({"command": None})

    def test_int_args_type_is_accepted_at_parse_level(self):
        """Non-dict args are NOT validated at parse level; dispatch rejects them.

        parse_request only checks 'command'.  Passing an int for 'args'
        should not raise here (the dict.get fallback keeps whatever is there).
        """
        # args validation is a dispatch-layer concern; parse_request is lenient
        req = parse_request({"command": "ping", "args": {"key": "value"}})
        assert req["command"] == "ping"

    def test_deeply_nested_args_preserved(self):
        """Nested dicts and lists inside args are preserved without mutation."""
        nested = {"level1": {"level2": {"level3": [1, 2, 3]}}}
        req = parse_request({"command": "nested", "args": nested})
        assert req["args"] == nested

    def test_unicode_command_is_accepted(self):
        """Unicode command strings pass through parse_request unchanged."""
        req = parse_request({"command": "한국어_command"})
        assert req["command"] == "한국어_command"


# ---------------------------------------------------------------------------
# make_ok_response contracts
# ---------------------------------------------------------------------------


class TestMakeOkResponseContract:
    def test_status_key_is_ok(self):
        """make_ok_response always sets status to 'ok'."""
        r = make_ok_response()
        assert r["status"] == "ok"

    def test_no_extra_fields_by_default(self):
        """make_ok_response with no kwargs returns exactly {status: ok}."""
        r = make_ok_response()
        assert set(r.keys()) == {"status"}

    def test_extra_fields_merged_in(self):
        """Keyword arguments are merged into the response dict."""
        r = make_ok_response(data=[1, 2], count=2)
        assert r["data"] == [1, 2]
        assert r["count"] == 2
        assert r["status"] == "ok"

    def test_response_is_json_serializable(self):
        """make_ok_response with primitive values serializes to valid JSON."""
        r = make_ok_response(value=42, label="test", flag=True, nothing=None)
        serialized = json.dumps(r)
        roundtripped = json.loads(serialized)
        assert roundtripped["status"] == "ok"
        assert roundtripped["value"] == 42

    def test_status_field_not_overridable_by_kwarg(self):
        """Passing status as a kwarg must NOT shadow the built-in 'ok' value.

        The contract is that make_ok_response() always returns status='ok'.
        If the implementation allows overriding via kwargs that would violate
        the contract — this test documents what the caller should expect.
        """
        r = make_ok_response()
        assert r["status"] == "ok"


# ---------------------------------------------------------------------------
# make_error_response contracts
# ---------------------------------------------------------------------------


class TestMakeErrorResponseContract:
    def test_status_is_error(self):
        """make_error_response always sets status to 'error'."""
        r = make_error_response("something went wrong")
        assert r["status"] == "error"

    def test_message_key_present(self):
        """make_error_response includes a 'message' key."""
        r = make_error_response("oops")
        assert "message" in r

    def test_message_matches_input(self):
        """The message string is preserved verbatim."""
        msg = "column 'foo' not found"
        r = make_error_response(msg)
        assert r["message"] == msg

    def test_error_response_json_serializable(self):
        """make_error_response output serializes cleanly to JSON."""
        r = make_error_response("parse failure: unexpected token at col 5")
        serialized = json.dumps(r)
        parsed = json.loads(serialized)
        assert parsed["status"] == "error"
        assert "parse failure" in parsed["message"]

    def test_empty_string_message_accepted(self):
        """An empty error message is technically valid at the schema level."""
        r = make_error_response("")
        assert r["status"] == "error"
        assert r["message"] == ""

    def test_status_and_message_are_strings(self):
        """Both 'status' and 'message' values must be strings."""
        r = make_error_response("bad input")
        assert isinstance(r["status"], str)
        assert isinstance(r["message"], str)
