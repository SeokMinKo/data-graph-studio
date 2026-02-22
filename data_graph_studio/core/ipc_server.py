"""
IPC Server - 외부 프로세스에서 앱 제어 가능하게 해주는 서버

Uses asyncio TCP server (no Qt dependency).
"""
import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from typing import Callable, Optional

logger = logging.getLogger(__name__)

from data_graph_studio.core.constants import (
    IPC_DEFAULT_PORT as DEFAULT_PORT,
    IPC_MAX_PORT_ATTEMPTS as MAX_PORT_ATTEMPTS,
)

_PORT_FILE = Path.home() / ".dgs" / "ipc_port"


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

    def __init__(self, message_handler: Callable[[dict], None]):
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
            target=self._run_loop, args=(ready,), daemon=True, name="ipc-server"
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
        except Exception:
            pass

    def _run_loop(self, ready: threading.Event) -> None:
        asyncio.set_event_loop(self._loop)
        self._loop.run_until_complete(self._start_server(ready))
        self._loop.run_forever()

    async def _start_server(self, ready: threading.Event) -> None:
        for attempt in range(MAX_PORT_ATTEMPTS):
            port = DEFAULT_PORT + attempt
            try:
                self._server = await asyncio.start_server(
                    self._handle_client, "127.0.0.1", port
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
            self._handler(msg)
        except Exception as e:
            logger.warning("ipc_server.handle_client_error", extra={"error": str(e)})
        finally:
            try:
                writer.close()
                await writer.wait_closed()
            except Exception:
                pass

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

    def _dispatch(self, msg: dict) -> None:
        command = msg.get("command", "")
        args = msg.get("args", {})
        if command in self._handlers:
            try:
                self._handlers[command](**args)
            except Exception as e:
                logger.warning("ipc_server.dispatch_error", extra={"command": command, "error": str(e)})
        else:
            logger.debug("ipc_server.unknown_command", extra={"command": command})

    def start(self, port: int = None) -> bool:  # type: ignore[override]
        """Start the server. Returns True on success (old API)."""
        result = super().start()
        return result is not None

    def stop(self) -> None:
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
        import socket

        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(5.0)
            return True
        except Exception as e:
            logger.debug("[IPC Client] Connection failed: %s", e)
            return False

    def disconnect(self):
        if self._socket:
            self._socket.close()
            self._socket = None

    def send_command(self, command: str, **args) -> dict:
        if not self._socket:
            return {"status": "error", "error": "Not connected"}

        try:
            data = json.dumps({"command": command, "args": args}, ensure_ascii=False)
            self._socket.sendall((data + "\n").encode("utf-8"))

            response = b""
            while True:
                chunk = self._socket.recv(4096)
                response += chunk
                if b"\n" in response:
                    break

            return json.loads(response.decode("utf-8").strip())
        except Exception as e:
            return {"status": "error", "error": str(e)}

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
