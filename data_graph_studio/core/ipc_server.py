"""
IPC Server — allows external processes to control the app over TCP.

Uses asyncio TCP server (no Qt dependency).
"""
import asyncio
import json
import logging
import os
import socket
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from data_graph_studio.core.constants import (
    IPC_DEFAULT_PORT as DEFAULT_PORT,
    IPC_MAX_PORT_ATTEMPTS as MAX_PORT_ATTEMPTS,
    IPC_KEY_COMMAND,
    IPC_KEY_ARGS,
    IPC_KEY_STATUS,
    IPC_KEY_MESSAGE,
    IPC_STATUS_ERROR,
    IPC_PORT_DIR,
    IPC_PORT_FILE_NAME,
    IPC_SERVER_HOST,
    IPC_THREAD_NAME,
    IPC_HANDLER_TIMEOUT,
)
from data_graph_studio.core.ipc_protocol import make_error_response, parse_request

_PORT_FILE = Path.home() / IPC_PORT_DIR / IPC_PORT_FILE_NAME


def _pid_is_alive(pid: int) -> bool:
    """Return True if pid refers to a running process."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def write_port_file(port: int) -> None:
    """Write the current PID and port to the port file.

    Input: port — int, the TCP port the server is bound to
    Output: None — side-effects only (creates ~/.dgs/ if needed, writes ``{pid}:{port}``)
    """
    _PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PORT_FILE.write_text(f"{os.getpid()}:{port}")


def read_port_file() -> Optional[int]:
    """Read the server port from the port file, validating the owning process is alive.

    Output: Optional[int] — port number if the file exists and the recorded PID is
        running; None if the file is absent, stale (PID dead), or malformed
    """
    try:
        text = _PORT_FILE.read_text().strip()
        pid_str, port_str = text.split(":", 1)
        pid, port = int(pid_str), int(port_str)
        if _pid_is_alive(pid):
            return port
        # Stale file — remove it
        _PORT_FILE.unlink(missing_ok=True)
    except (FileNotFoundError, ValueError, OSError):
        pass
    return None


def remove_port_file() -> None:
    """Remove the port file on a best-effort basis.

    Output: None — side-effects only (deletes ~/.dgs/ipc_port if it exists; OSError silently ignored)
    """
    try:
        _PORT_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class IpcServer:
    """Asyncio-based TCP IPC server."""

    def __init__(self, message_handler: Callable[[dict], object]):
        """Initialize the IPC server without starting it.

        Input: message_handler — Callable[[dict], object], called with the parsed
            JSON dict for each incoming request; must return a JSON-serializable value
        Output: None — side-effects only (stores handler, initializes internal state)
        """
        self._handler = message_handler
        self._server: Optional[asyncio.Server] = None
        self._port: Optional[int] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> Optional[int]:
        """The TCP port the server is listening on.

        Output: Optional[int] — bound port number, or None if the server has not
            been started or failed to bind
        """
        return self._port

    def start(self) -> int:
        """Start the asyncio server in a daemon background thread.

        Output: int — the TCP port the server bound to; None if no port could be
            found within MAX_PORT_ATTEMPTS attempts
        Invariants: after return, the server thread is running and the port file
            has been written (or the event loop has signalled failure)
        """
        ready = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, args=(ready,), daemon=True, name=IPC_THREAD_NAME
        )
        self._thread.start()
        ready.wait(timeout=5.0)
        return self._port

    def stop(self) -> None:
        """Close the asyncio server and delete the port file.

        Output: None — side-effects only (schedules server.close() on the event
            loop, removes port file; OSError on file deletion is logged and ignored)
        """
        if self._loop and self._server:
            self._loop.call_soon_threadsafe(self._server.close)
        try:
            _PORT_FILE.unlink(missing_ok=True)
        except OSError:
            logger.debug("ipc_server.stop.port_file_unlink_failed", exc_info=True)

    def _run_loop(self, ready: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server(ready))
        self._loop.run_forever()

    async def _start_server(self, ready: threading.Event) -> None:
        for attempt in range(MAX_PORT_ATTEMPTS):
            port = DEFAULT_PORT + attempt
            try:
                self._server = await asyncio.start_server(
                    self._handle_client, IPC_SERVER_HOST, port
                )
                self._port = port
                self._write_port_file(port)
                logger.debug("ipc_server.started", extra={"port": port})
                ready.set()
                return
            except OSError:
                continue
        logger.error("ipc_server.no_port_available", extra={"tried": MAX_PORT_ATTEMPTS})
        ready.set()

    async def _handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            data = await asyncio.wait_for(reader.read(65536), timeout=10.0)
            msg = json.loads(data.decode())
            loop = asyncio.get_event_loop()
            try:
                result = await asyncio.wait_for(
                    loop.run_in_executor(None, lambda: self._handler(msg)),
                    timeout=IPC_HANDLER_TIMEOUT,
                )
            except asyncio.TimeoutError:
                cmd = msg.get(IPC_KEY_COMMAND, "<unknown>") if isinstance(msg, dict) else "<unknown>"
                logger.error(
                    "ipc_server.handler_timeout",
                    extra={"command": cmd, "timeout_s": IPC_HANDLER_TIMEOUT},
                )
                result = make_error_response(f"command timed out: {cmd}")
            response = json.dumps(result, ensure_ascii=False, default=str) + "\n"
            writer.write(response.encode("utf-8"))
            await writer.drain()
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as e:
            logger.warning("ipc_server.handle_client_error", extra={"error": str(e)})
            err = json.dumps({IPC_KEY_STATUS: IPC_STATUS_ERROR, "error": str(e)}) + "\n"
            try:
                writer.write(err.encode("utf-8"))
                await writer.drain()
            except OSError:
                logger.debug("ipc_server.handle_client.error_write_failed", exc_info=True)
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except OSError:
                logger.debug("ipc_server.handle_client.writer_close_failed", exc_info=True)

    def _write_port_file(self, port: int) -> None:
        _PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PORT_FILE.write_text(f"{os.getpid()}:{port}")


class IPCServer(IpcServer):
    """Backward-compatible wrapper around IpcServer.

    Preserves the old Qt-style API (register_handler / start() / stop())
    so that existing callers (ipc_controller.py) don't need changes.
    """

    def __init__(self, parent=None):
        """Initialize the backward-compatible IPC server.

        Input: parent — optional Qt parent object (unused; accepted for API compatibility)
        Output: None — side-effects only (initializes handler registry, delegates to IpcServer.__init__)
        """
        self._handlers: dict = {}
        super().__init__(message_handler=self._dispatch)

    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a callable to handle a named IPC command.

        Input: command — str, the command name to match in incoming requests
               handler — Callable, invoked with unpacked args dict as keyword arguments;
                   must return a JSON-serializable value
        Output: None — side-effects only (stores handler in registry; overwrites any
            previously registered handler for the same command)
        """
        self._handlers[command] = handler

    def _dispatch(self, msg: dict) -> object:
        """Dispatch to the registered handler and return its result."""
        try:
            req = parse_request(msg)
        except ValueError as e:
            logger.warning("ipc_server.invalid_request", extra={"error": str(e)})
            return make_error_response(str(e))
        command = req[IPC_KEY_COMMAND]
        args = req[IPC_KEY_ARGS]
        if command in self._handlers:
            try:
                return self._handlers[command](**args)
            except (TypeError, ValueError, RuntimeError, AttributeError) as e:
                logger.warning("ipc_server.dispatch_error", extra={"command": command, "error": str(e)})
                return {IPC_KEY_STATUS: IPC_STATUS_ERROR, IPC_KEY_MESSAGE: str(e)}
        else:
            logger.debug("ipc_server.unknown_command", extra={"command": command})
            return {IPC_KEY_STATUS: IPC_STATUS_ERROR, IPC_KEY_MESSAGE: f"unknown command: {command}"}

    def start(self, port: int = None) -> bool:  # type: ignore[override]
        """Start the IPC server using the old boolean-return API.

        Input: port — int, ignored (port selection is automatic); accepted for
            backward-compatible call signatures
        Output: bool — True if the server bound to a port successfully, False otherwise
        """
        result = super().start()
        return result is not None

    def stop(self) -> None:
        """Stop the IPC server, remove the port file, and log shutdown.

        Output: None — side-effects only (calls IpcServer.stop(), removes port file,
            emits INFO log)
        """
        super().stop()
        remove_port_file()
        logger.info("ipc_server.server.stopped")


class IPCClient:
    """IPC client for controlling the app from an external process.

    Automatically discovers the server port from the port file.
    """

    def __init__(self, host: str = "localhost", port: int = None):
        """Initialize the IPC client without opening a connection.

        Input: host — str, hostname or IP to connect to (default: "localhost")
               port — Optional[int], explicit port; if None, port is resolved from
                   the port file or falls back to DEFAULT_PORT
        Output: None — side-effects only (stores connection parameters)
        """
        self.host = host
        self._explicit_port = port
        self._socket = None

    @property
    def port(self) -> int:
        """Resolve the server port using explicit value, port file, or default.

        Output: int — the explicit port if provided at construction; otherwise the
            port from the port file if the owning process is alive; otherwise DEFAULT_PORT
        """
        if self._explicit_port is not None:
            return self._explicit_port
        discovered = read_port_file()
        return discovered if discovered is not None else DEFAULT_PORT

    def connect(self) -> bool:
        """Open a TCP connection to the IPC server.

        Output: bool — True if the connection was established; False if the server
            refused or a timeout occurred (OSError / socket.timeout caught internally)
        Invariants: on True, self._socket is a connected socket with a 5-second timeout
        """
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((self.host, self.port))
            return True
        except (OSError, socket.timeout) as e:
            logger.debug("ipc_client.connect.failed", extra={"error": str(e)})
            return False

    def disconnect(self) -> None:
        """Close the TCP connection to the IPC server.

        Output: None — side-effects only (closes and nulls self._socket; no-op if
            already disconnected)
        """
        if self._socket:
            self._socket.close()
            self._socket = None

    def send_command(self, command: str, **args) -> dict:
        """Send a JSON command to the server and return the parsed response.

        Input: command — str, the command name
               **args — keyword arguments forwarded as the ``args`` field of the request
        Output: dict — parsed server response; on socket or decode error, returns an
            error dict with ``status="error"`` and an ``"error"`` key describing the failure
        Raises: nothing — all OSError / socket.timeout / decode errors are caught and
            returned as error dicts
        """
        if not self._socket:
            return {IPC_KEY_STATUS: IPC_STATUS_ERROR, "error": "Not connected"}

        try:
            data = json.dumps({IPC_KEY_COMMAND: command, IPC_KEY_ARGS: args}, ensure_ascii=False)
            self._socket.sendall((data + "\n").encode("utf-8"))

            response = b""
            while True:
                chunk = self._socket.recv(4096)
                response += chunk
                if b"\n" in response:
                    break

            return json.loads(response.decode("utf-8").strip())
        except (OSError, socket.timeout, UnicodeDecodeError, json.JSONDecodeError) as e:
            return {IPC_KEY_STATUS: IPC_STATUS_ERROR, "error": str(e)}

    def __enter__(self):
        """Connect to the IPC server and return self for context manager use.

        Output: IPCClient — self, with an open socket connection
        """
        self.connect()
        return self

    def __exit__(self, *args):
        """Disconnect from the IPC server on context manager exit.

        Output: None
        Invariants: socket is closed and set to None regardless of exception type
        """
        self.disconnect()


def send_command(command: str, port: int = None, **args) -> dict:
    """Send a single IPC command with automatic connect and disconnect.

    Input: command — str, the command name to send
           port — Optional[int], explicit port override; None uses port-file discovery
           **args — keyword arguments forwarded to the command handler
    Output: dict — parsed server response, or an error dict if the connection or
        send fails
    """
    with IPCClient(port=port) as client:
        return client.send_command(command, **args)
