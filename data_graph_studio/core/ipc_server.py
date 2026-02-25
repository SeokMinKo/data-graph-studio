"""
IPC Server - 외부 프로세스에서 앱 제어 가능하게 해주는 서버

Uses QLocalServer (Unix Domain Socket) for secure local-only IPC.
Records connection info in ~/.dgs/ipc_port as ``{pid}:{socket_path}:{token}``
so that clients can discover it automatically.

Authentication: each request must include a ``token`` field matching
the server's randomly generated token.
"""
import json
import logging
import os
import secrets
import signal
import tempfile
from pathlib import Path
from typing import Callable, Optional

from PySide6.QtCore import QObject, Signal
from PySide6.QtNetwork import QLocalServer, QLocalSocket

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Port-file helpers (shared by server & client)
# ---------------------------------------------------------------------------

_PORT_FILE = Path.home() / ".dgs" / "ipc_port"
_SOCKET_PATH = Path.home() / ".dgs" / "ipc.sock"
DEFAULT_PORT = 52849  # kept for backward compat reference
MAX_PORT_ATTEMPTS = 100  # kept for backward compat reference

# Buffer limit: 1 MB
_MAX_BUFFER_SIZE = 1 * 1024 * 1024


def _pid_is_alive(pid: int) -> bool:
    """Return True if *pid* refers to a running process."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def write_port_file(port: int, token: str = "") -> None:
    """Write ``{pid}:{port}:{token}`` to the port file atomically."""
    _PORT_FILE.parent.mkdir(parents=True, exist_ok=True)
    content = f"{os.getpid()}:{port}:{token}"
    # Atomic write: write to temp file then rename
    tmp_fd, tmp_path = tempfile.mkstemp(
        dir=str(_PORT_FILE.parent), prefix=".ipc_port_"
    )
    fd_closed = False
    try:
        os.write(tmp_fd, content.encode("utf-8"))
        os.close(tmp_fd)
        fd_closed = True
        os.replace(tmp_path, str(_PORT_FILE))
    except Exception:
        if not fd_closed:
            try:
                os.close(tmp_fd)
            except OSError:
                pass
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def read_port_file() -> Optional[tuple]:
    """Read port and token from the port file.

    Returns ``(port, token)`` if the file exists and the owning process
    is alive, otherwise cleans up the stale file and returns ``None``.
    """
    try:
        text = _PORT_FILE.read_text().strip()
        parts = text.split(":")
        if len(parts) >= 3:
            pid, port, token = int(parts[0]), int(parts[1]), parts[2]
        elif len(parts) == 2:
            pid, port = int(parts[0]), int(parts[1])
            token = ""
        else:
            return None
        if _pid_is_alive(pid):
            return (port, token)
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


def is_another_instance_running() -> bool:
    """Check if another DGS instance is already running."""
    result = read_port_file()
    return result is not None


def send_files_to_existing_instance(file_paths: list[str]) -> bool:
    """Send file paths to the existing instance via IPC.

    Returns True if successful, False otherwise.
    """
    result = read_port_file()
    if result is None:
        return False
    port, token = result
    try:
        client = IPCClient(port=port, token=token)
        if not client.connect():
            return False
        for path in file_paths:
            resp = client.send_command("load_file", path=path)
            if resp.get("status") != "ok":
                logger.warning("[IPC] Failed to send file to existing instance: %s", path)
        client.disconnect()
        return True
    except Exception as e:
        logger.debug("[IPC] Failed to contact existing instance: %s", e)
        return False


class IPCServer(QObject):
    """로컬 Unix Domain Socket 서버로 외부 프로세스와 통신.

    Uses QLocalServer for secure local-only communication.
    Authenticates clients via a random token stored in the port file.
    """

    command_received = Signal(str, object)  # command, args
    response_ready = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QLocalServer(self)
        self._clients: list[QLocalSocket] = []
        self._handlers: dict[str, Callable] = {}
        self._port: Optional[int] = None
        self._token: str = ""
        self._buffers: dict[int, bytearray] = {}  # client id -> buffer

        self._server.newConnection.connect(self._on_new_connection)

    @property
    def port(self) -> Optional[int]:
        """Return the port the server is listening on, or None."""
        return self._port

    @property
    def token(self) -> str:
        """Return the authentication token."""
        return self._token

    def start(self, port: int = None) -> bool:
        """Start the server on a Unix Domain Socket.

        The *port* parameter is kept for backward compatibility but is
        written to the port file for client discovery.  On success,
        writes the port file with the authentication token.
        """
        self._token = secrets.token_hex(16)
        base_port = port or DEFAULT_PORT

        # Remove stale socket file
        socket_name = "dgs-ipc"
        QLocalServer.removeServer(socket_name)

        if self._server.listen(socket_name):
            self._port = base_port
            write_port_file(base_port, self._token)
            logger.info("[IPC] Server listening on local socket '%s'", socket_name)
            return True

        logger.warning(
            "[IPC] Failed to create local socket '%s': %s. IPC disabled.",
            socket_name,
            self._server.errorString(),
        )
        return False

    def stop(self):
        """서버 중지"""
        for client in self._clients:
            client.close()
        self._clients.clear()
        self._server.close()
        self._port = None
        self._token = ""
        self._buffers.clear()
        remove_port_file()
        logger.info("[IPC] Server stopped")

    def register_handler(self, command: str, handler: Callable):
        """명령 핸들러 등록"""
        self._handlers[command] = handler

    # ----- connection handling -----

    def _on_new_connection(self):
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            if client is None:
                continue
            self._clients.append(client)
            client_id = id(client)
            self._buffers[client_id] = bytearray()
            client.readyRead.connect(lambda c=client: self._on_data_ready(c))
            client.disconnected.connect(lambda c=client: self._on_disconnected(c))
            logger.debug("[IPC] Client connected")

    def _on_data_ready(self, client: QLocalSocket):
        client_id = id(client)
        buf = self._buffers.get(client_id)
        if buf is None:
            buf = bytearray()
            self._buffers[client_id] = buf

        data = client.readAll().data()
        buf.extend(data)

        # Buffer size limit check
        if len(buf) > _MAX_BUFFER_SIZE:
            logger.warning("[IPC] Client buffer exceeded %d bytes, disconnecting", _MAX_BUFFER_SIZE)
            self._buffers.pop(client_id, None)
            client.disconnectFromServer()
            return

        # Process complete lines
        while b"\n" in buf:
            idx = buf.index(b"\n")
            line = buf[:idx].decode("utf-8", errors="replace").strip()
            del buf[:idx + 1]
            if line:
                self._process_command(client, line)

    def _on_disconnected(self, client: QLocalSocket):
        if client in self._clients:
            self._clients.remove(client)
        self._buffers.pop(id(client), None)
        client.deleteLater()
        logger.debug("[IPC] Client disconnected")

    def _process_command(self, client: QLocalSocket, line: str):
        try:
            data = json.loads(line)

            # Token authentication
            request_token = data.get("token", "")
            if self._token and request_token != self._token:
                self._send_response(client, {
                    "status": "error",
                    "error": "Authentication failed: invalid token",
                })
                return

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

    def _send_response(self, client: QLocalSocket, response: dict):
        line = json.dumps(response, ensure_ascii=False, default=str) + "\n"
        client.write(line.encode("utf-8"))
        client.flush()


class IPCClient:
    """IPC 클라이언트 - 외부에서 앱 제어용.

    Connects via Unix Domain Socket. Automatically discovers the server
    and authenticates using the token from the port file.
    """

    def __init__(self, host: str = "localhost", port: int = None, token: str = None):
        self.host = host
        self._explicit_port = port
        self._token = token
        self._socket: Optional[QLocalSocket] = None
        # Also support raw socket for non-Qt contexts
        self._raw_socket = None

    @property
    def port(self) -> int:
        """Resolve port: explicit → port-file → default."""
        if self._explicit_port is not None:
            return self._explicit_port
        result = read_port_file()
        if result is not None:
            return result[0]
        return DEFAULT_PORT

    @property
    def token(self) -> str:
        """Resolve token: explicit → port-file → empty."""
        if self._token is not None:
            return self._token
        result = read_port_file()
        if result is not None:
            return result[1]
        return ""

    def connect(self) -> bool:
        """Connect to the IPC server via Unix Domain Socket."""
        import socket as _socket

        socket_name = "dgs-ipc"
        try:
            self._socket = QLocalSocket()
            self._socket.connectToServer(socket_name)
            if self._socket.waitForConnected(3000):
                return True
            logger.debug("[IPC Client] Connection failed: %s", self._socket.errorString())
            self._socket = None
            return False
        except Exception as e:
            logger.debug("[IPC Client] Connection failed: %s", e)
            self._socket = None
            return False

    def disconnect(self):
        if self._socket:
            self._socket.disconnectFromServer()
            self._socket = None

    def send_command(self, command: str, **args) -> dict:
        if not self._socket:
            return {"status": "error", "error": "Not connected"}

        try:
            payload = {
                "command": command,
                "args": args,
                "token": self.token,
            }
            data = json.dumps(payload, ensure_ascii=False)
            self._socket.write((data + "\n").encode("utf-8"))
            self._socket.flush()

            response = b""
            max_attempts = 256  # prevent infinite loop
            attempts = 0
            while attempts < max_attempts:
                if self._socket.waitForReadyRead(5000):
                    chunk = self._socket.readAll().data()
                    response += chunk
                    if b"\n" in response:
                        break
                else:
                    break
                attempts += 1

                if len(response) > _MAX_BUFFER_SIZE:
                    return {"status": "error", "error": "Response too large"}

            if not response:
                return {"status": "error", "error": "No response (timeout)"}

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
    result = read_port_file()
    token = result[1] if result else ""
    with IPCClient(port=port, token=token) as client:
        return client.send_command(command, **args)
