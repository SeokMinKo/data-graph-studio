"""
IPC Server - 외부 프로세스에서 앱 제어 가능하게 해주는 서버

Supports dynamic port selection: tries DEFAULT_PORT, then increments up to
MAX_PORT_ATTEMPTS times.  Records the chosen port in ~/.dgs/ipc_port as
``{pid}:{port}`` so that clients can discover it automatically.
"""
import json
import logging
import os
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port-file helpers (shared by server & client)
# ---------------------------------------------------------------------------

from data_graph_studio.core.constants import (
    IPC_DEFAULT_PORT as DEFAULT_PORT,
    IPC_MAX_PORT_ATTEMPTS as MAX_PORT_ATTEMPTS,
)

_PORT_FILE = Path.home() / ".dgs" / "ipc_port"


def _pid_is_alive(pid: int) -> bool:
    """Return True if *pid* refers to a running process."""
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
    """Read port from the port file.

    Returns the port if the file exists and the owning process is alive,
    otherwise cleans up the stale file and returns ``None``.
    """
    try:
        text = _PORT_FILE.read_text().strip()
        pid_s, port_s = text.split(":", 1)
        pid, port = int(pid_s), int(port_s)
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


class IPCServer(QObject):
    """로컬 TCP 서버로 외부 프로세스와 통신.

    Supports automatic port selection when the default port is in use.
    """

    command_received = Signal(str, object)  # command, args
    response_ready = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QTcpServer(self)
        self._clients: list[QTcpSocket] = []
        self._handlers: dict[str, Callable] = {}
        self._port: Optional[int] = None

        self._server.newConnection.connect(self._on_new_connection)

    @property
    def port(self) -> Optional[int]:
        """Return the port the server is listening on, or None."""
        return self._port

    def start(self, port: int = None) -> bool:
        """Start the server with automatic port selection.

        Tries *port* (default ``DEFAULT_PORT``), then increments up to
        ``MAX_PORT_ATTEMPTS`` times.  On success, writes the port file.
        On failure, logs a warning and returns ``False`` (IPC disabled).
        """
        base_port = port or DEFAULT_PORT

        for offset in range(MAX_PORT_ATTEMPTS):
            candidate = base_port + offset
            if self._server.listen(QHostAddress.LocalHost, candidate):
                self._port = candidate
                write_port_file(candidate)
                logger.info("[IPC] Server listening on localhost:%d", candidate)
                return True
            # Port busy — try next
            logger.debug(
                "[IPC] Port %d unavailable (%s), trying next",
                candidate,
                self._server.errorString(),
            )

        logger.warning(
            "[IPC] Failed to bind any port in range %d–%d. IPC disabled.",
            base_port,
            base_port + MAX_PORT_ATTEMPTS - 1,
        )
        return False

    def stop(self):
        """서버 중지"""
        for client in self._clients:
            client.close()
        self._clients.clear()
        self._server.close()
        self._port = None
        remove_port_file()
        logger.info("[IPC] Server stopped")

    def register_handler(self, command: str, handler: Callable):
        """명령 핸들러 등록"""
        self._handlers[command] = handler

    # ----- connection handling -----

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            self._clients.append(client)
            client.readyRead.connect(lambda c=client: self._on_data_ready(c))
            client.disconnected.connect(lambda c=client: self._on_disconnected(c))
            logger.debug("[IPC] Client connected: %s", client.peerAddress().toString())

    def _on_data_ready(self, client: QTcpSocket):
        while client.canReadLine():
            line = client.readLine().data().decode("utf-8").strip()
            if line:
                self._process_command(client, line)

    def _on_disconnected(self, client: QTcpSocket):
        if client in self._clients:
            self._clients.remove(client)
        logger.debug("[IPC] Client disconnected")

    def _process_command(self, client: QTcpSocket, line: str):
        try:
            data = json.loads(line)
            command = data.get("command", "")
            args = data.get("args", {})

            if command in self._handlers:
                try:
                    result = self._handlers[command](**args)
                    response = {"status": "ok", "result": result}
                except Exception as e:
                    response = {"status": "error", "error": str(e)}
            else:
                response = {"status": "error", "error": f"Unknown command: {command}"}

            self._send_response(client, response)

        except json.JSONDecodeError as e:
            self._send_response(client, {"status": "error", "error": f"Invalid JSON: {e}"})

    def _send_response(self, client: QTcpSocket, response: dict):
        line = json.dumps(response, ensure_ascii=False, default=str) + "\n"
        client.write(line.encode("utf-8"))
        client.flush()


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
