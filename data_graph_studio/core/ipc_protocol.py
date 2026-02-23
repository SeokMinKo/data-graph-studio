"""IPC message protocol schema for data-graph-studio.

All messages use JSON over TCP socket.
Request:  {"command": str, "args": dict}
Response: {"status": "ok", ...} | {"status": "error", "message": str}
"""
from __future__ import annotations

from typing import Any, TypedDict


class IpcRequest(TypedDict):
    """Incoming IPC request message."""

    command: str
    args: dict[str, Any]


class IpcErrorResponse(TypedDict):
    """Error response with human-readable message."""

    status: str
    message: str


def parse_request(data: dict[str, Any]) -> IpcRequest:
    """Validate and parse a raw dict into an IpcRequest.

    Raises:
        ValueError: if "command" key is missing or not a string.
    """
    if "command" not in data:
        raise ValueError("IPC request missing required 'command' key")
    if not isinstance(data["command"], str):
        raise ValueError(
            f"IPC 'command' must be str, got {type(data['command']).__name__}"
        )
    return IpcRequest(
        command=data["command"],
        args=data.get("args", {}),
    )


def make_ok_response(**fields: Any) -> dict[str, Any]:
    """Build a success response dict.

    Returns: {"status": "ok", **fields}
    """
    return {"status": "ok", **fields}


def make_error_response(message: str) -> IpcErrorResponse:
    """Build an error response dict.

    Returns: {"status": "error", "message": message}
    """
    return IpcErrorResponse(status="error", message=message)
