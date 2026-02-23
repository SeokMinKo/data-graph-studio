"""
IPC Server - 외부 프로세스에서 앱 제어 가능하게 해주는 서버

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
    """Write ``{pid}:{port}`` to the port file, creating dirs as needed."""
    _PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    _PORT_FILE.write_text(f"{os.getpid()}:{port}")


def read_port_file() -> Optional[int]:
    """Read the port from ~/.dgs/ipc_port if the owning process is alive."""
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
    """Remove the port file (best-effort)."""
    try:
        _PORT_FILE.unlink(missing_ok=True)
    except OSError:
        pass


class IpcServer:
    """Asyncio-based TCP IPC server."""

    def __init__(self, message_handler: Callable[[dict], object]):
        """
        Args:
            message_handler: Called with parsed JSON dict on each received message.
        """
        self._handler = message_handler
        self._server: Optional[asyncio.Server] = None
        self._port: Optional[int] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def port(self) -> Optional[int]:
        """The port the server is listening on, or None if not started."""
        return self._port

    def start(self) -> int:
        """Start the server in a background thread. Returns bound port."""
        ready = threading.Event()
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, args=(ready,), daemon=True, name=IPC_THREAD_NAME
        )
        self._thread.start()
        ready.wait(timeout=5.0)
        return self._port

    def stop(self) -> None:
        """Stop the server and clean up."""
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
        self._handlers: dict = {}
        super().__init__(message_handler=self._dispatch)

    def register_handler(self, command: str, handler: Callable) -> None:
        """Register a named command handler (old API)."""
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
            except Exception as e:
                logger.warning("ipc_server.dispatch_error", extra={"command": command, "error": str(e)})
                return {IPC_KEY_STATUS: IPC_STATUS_ERROR, IPC_KEY_MESSAGE: str(e)}
        else:
            logger.debug("ipc_server.unknown_command", extra={"command": command})
            return {IPC_KEY_STATUS: IPC_STATUS_ERROR, IPC_KEY_MESSAGE: f"unknown command: {command}"}

    def start(self, port: int = None) -> bool:  # type: ignore[override]
        """Start the server. Returns True on success (old API)."""
        result = super().start()
        return result is not None

    def stop(self) -> None:
        """Stop the IPC server and remove the port file."""
        super().stop()
        remove_port_file()
        logger.info("[IPC] Server stopped")


class IPCClient:
    """IPC 클라이언트 - 외부에서 앱 제어용.

    Automatically discovers the server port from the port file.
    """

    def __init__(self, host: str = "localhost", port: int = None):
        self.host = host
        self._explicit_port = port
        self._socket = None

    @property
    def port(self) -> int:
        """Resolve port: explicit → port-file → default."""
        if self._explicit_port is not None:
            return self._explicit_port
        discovered = read_port_file()
        return discovered if discovered is not None else DEFAULT_PORT

    def connect(self) -> bool:
        """Open a TCP connection to the IPC server. Returns True on success."""
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.settimeout(5.0)
            self._socket.connect((self.host, self.port))
            return True
        except (OSError, socket.timeout) as e:
            logger.debug("[IPC Client] Connection failed: %s", e)
            return False

    def disconnect(self):
        """Close the TCP connection to the IPC server."""
        if self._socket:
            self._socket.close()
            self._socket = None

    def send_command(self, command: str, **args) -> dict:
        """Send a JSON command to the server and return the parsed response dict."""
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
        self.connect()
        return self

    def __exit__(self, *args):
        self.disconnect()


# 편의 함수
def send_command(command: str, port: int = None, **args) -> dict:
    """단일 명령 전송 (자동 연결/해제)"""
    with IPCClient(port=port) as client:
        return client.send_command(command, **args)
