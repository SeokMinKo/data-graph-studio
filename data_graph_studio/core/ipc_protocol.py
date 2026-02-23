"""IPC message protocol schema for data-graph-studio.

All messages use JSON over TCP socket.
Request:  {"command": str, "args": dict}
Response: {"status": "ok", ...} | {"status": "error", "message": str}
"""
from __future__ import annotations

from typing import Any, TypedDict

from .constants import (
    IPC_KEY_COMMAND,
    IPC_KEY_ARGS,
    IPC_KEY_STATUS,
    IPC_KEY_MESSAGE,
    IPC_STATUS_OK,
    IPC_STATUS_ERROR,
)
from .exceptions import ConfigError


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
        ConfigError: if "command" key is missing or not a string.
    """
    if IPC_KEY_COMMAND not in data:
        raise ConfigError("IPC request missing required 'command' key", operation="parse_request", context={"keys": list(data.keys())})
    if not isinstance(data[IPC_KEY_COMMAND], str):
        raise ConfigError(
            f"IPC 'command' must be str, got {type(data[IPC_KEY_COMMAND]).__name__}",
            operation="parse_request",
            context={"command_type": type(data[IPC_KEY_COMMAND]).__name__},
        )
    return IpcRequest(
        command=data[IPC_KEY_COMMAND],
        args=data.get(IPC_KEY_ARGS, {}),
    )


def make_ok_response(**fields: Any) -> dict[str, Any]:
    """Build a success response dict.

    Returns: {"status": "ok", **fields}
    """
    return {IPC_KEY_STATUS: IPC_STATUS_OK, **fields}


def make_error_response(message: str) -> IpcErrorResponse:
    """Build an error response dict.

    Returns: {"status": "error", "message": message}
    """
    return IpcErrorResponse(status=IPC_STATUS_ERROR, message=message)
