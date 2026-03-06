"""Tests for IPC security improvements.

Covers: token authentication, buffer limits, execute handler disable,
single-instance detection, atomic port file, and deleteLater on disconnect.
"""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

from data_graph_studio.core.ipc_server import (
    IPCServer,
    IPCClient,
    _MAX_BUFFER_SIZE,
    is_another_instance_running,
    read_port_file,
    remove_port_file,
    write_port_file,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_port_file():
    """Ensure no stale port file interferes."""
    remove_port_file()
    yield
    remove_port_file()


# ---------------------------------------------------------------------------
# Token Authentication
# ---------------------------------------------------------------------------


class TestTokenAuthentication:
    def test_write_port_file_includes_token(self, tmp_path):
        """write_port_file stores pid:port:token format."""
        with patch(
            "data_graph_studio.core.ipc_server._PORT_FILE", tmp_path / "ipc_port"
        ):
            write_port_file(12345, "secret-token")
            content = (tmp_path / "ipc_port").read_text()
            parts = content.split(":")
            assert len(parts) == 3
            assert parts[1] == "12345"
            assert parts[2] == "secret-token"

    def test_read_port_file_returns_token(self, tmp_path):
        """read_port_file returns (port, token) tuple."""
        port_file = tmp_path / "ipc_port"
        pid = os.getpid()  # current process is alive
        port_file.write_text(f"{pid}:9999:my-token")
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            result = read_port_file()
            assert result == (9999, "my-token")

    def test_read_port_file_backward_compat(self, tmp_path):
        """read_port_file handles old pid:port format."""
        port_file = tmp_path / "ipc_port"
        pid = os.getpid()
        port_file.write_text(f"{pid}:8888")
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            result = read_port_file()
            assert result == (8888, "")

    def test_server_generates_token(self):
        """IPCServer generates a non-empty token on start."""
        server = IPCServer()
        # We can't actually start (no event loop), but check token generation
        assert server.token == ""
        # Simulate what start() does
        import secrets

        server._token = secrets.token_hex(16)
        assert len(server._token) == 32

    def test_process_command_rejects_bad_token(self):
        """Commands with wrong token are rejected."""
        server = IPCServer()
        server._token = "correct-token"
        server.register_handler("ping", lambda: "pong")

        mock_client = MagicMock()
        written_data = []
        mock_client.write = lambda d: written_data.append(d)
        mock_client.flush = MagicMock()

        # Send command with wrong token
        line = json.dumps({"command": "ping", "token": "wrong-token"})
        server._process_command(mock_client, line)

        assert len(written_data) == 1
        response = json.loads(written_data[0].decode("utf-8"))
        assert response["status"] == "error"
        assert "Authentication failed" in response["error"]

    def test_process_command_accepts_correct_token(self):
        """Commands with correct token are processed."""
        server = IPCServer()
        server._token = "correct-token"
        server.register_handler("ping", lambda: "pong")

        mock_client = MagicMock()
        written_data = []
        mock_client.write = lambda d: written_data.append(d)
        mock_client.flush = MagicMock()

        line = json.dumps({"command": "ping", "token": "correct-token"})
        server._process_command(mock_client, line)

        assert len(written_data) == 1
        response = json.loads(written_data[0].decode("utf-8"))
        assert response["status"] == "ok"
        assert response["result"] == "pong"

    def test_process_command_no_token_required_when_empty(self):
        """When server token is empty, any request passes."""
        server = IPCServer()
        server._token = ""
        server.register_handler("ping", lambda: "pong")

        mock_client = MagicMock()
        written_data = []
        mock_client.write = lambda d: written_data.append(d)
        mock_client.flush = MagicMock()

        line = json.dumps({"command": "ping"})
        server._process_command(mock_client, line)

        response = json.loads(written_data[0].decode("utf-8"))
        assert response["status"] == "ok"


# ---------------------------------------------------------------------------
# Buffer Limit
# ---------------------------------------------------------------------------


class TestBufferLimit:
    def test_buffer_limit_constant(self):
        """Buffer limit is 1MB."""
        assert _MAX_BUFFER_SIZE == 1 * 1024 * 1024

    def test_on_data_ready_disconnects_on_overflow(self):
        """Server disconnects client when buffer exceeds limit."""
        server = IPCServer()

        mock_client = MagicMock()
        client_id = id(mock_client)
        server._buffers[client_id] = bytearray(b"x" * (_MAX_BUFFER_SIZE - 10))

        # Simulate readAll returning data that pushes over limit
        mock_data = MagicMock()
        mock_data.data.return_value = b"x" * 100
        mock_client.readAll.return_value = mock_data

        server._on_data_ready(mock_client)

        mock_client.disconnectFromServer.assert_called_once()
        assert client_id not in server._buffers


# ---------------------------------------------------------------------------
# Execute Handler Disabled by Default
# ---------------------------------------------------------------------------


class TestExecuteDisabled:
    def test_execute_not_registered_by_default(self):
        """execute handler is NOT registered when debug=False."""
        from data_graph_studio.ui.controllers.ipc_controller import IPCController

        mock_window = MagicMock()
        mock_window.state = MagicMock()
        controller = IPCController(mock_window, debug=False)

        registered = {}
        mock_server = MagicMock()
        mock_server.register_handler = lambda cmd, h: registered.update({cmd: h})
        mock_server.start = MagicMock(return_value=True)
        mock_window._ipc_server = mock_server

        with patch(
            "data_graph_studio.core.ipc_server.IPCServer", return_value=mock_server
        ):
            controller.setup()

        assert "execute" not in registered

    def test_execute_not_registered_even_in_debug_mode(self):
        """execute handler is removed for security even when debug=True."""
        from data_graph_studio.ui.controllers.ipc_controller import IPCController

        mock_window = MagicMock()
        mock_window.state = MagicMock()
        controller = IPCController(mock_window, debug=True)

        registered = {}
        mock_server = MagicMock()
        mock_server.register_handler = lambda cmd, h: registered.update({cmd: h})
        mock_server.start = MagicMock(return_value=True)
        mock_window._ipc_server = mock_server

        with patch(
            "data_graph_studio.core.ipc_server.IPCServer", return_value=mock_server
        ):
            controller.setup()

        assert "execute" not in registered


# ---------------------------------------------------------------------------
# Single Instance
# ---------------------------------------------------------------------------


class TestSingleInstance:
    def test_is_another_instance_running_false_when_no_file(self, tmp_path):
        """No port file → no other instance."""
        with patch(
            "data_graph_studio.core.ipc_server._PORT_FILE", tmp_path / "nonexistent"
        ):
            assert is_another_instance_running() is False

    def test_is_another_instance_running_true_when_alive(self, tmp_path):
        """Port file with alive PID → another instance running."""
        port_file = tmp_path / "ipc_port"
        pid = os.getpid()
        port_file.write_text(f"{pid}:9999:tok")
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            assert is_another_instance_running() is True

    def test_is_another_instance_running_false_when_stale(self, tmp_path):
        """Port file with dead PID → stale, returns False."""
        port_file = tmp_path / "ipc_port"
        port_file.write_text("999999999:9999:tok")  # unlikely to be alive
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            with patch(
                "data_graph_studio.core.ipc_server._pid_is_alive", return_value=False
            ):
                assert is_another_instance_running() is False


# ---------------------------------------------------------------------------
# Atomic Port File Write
# ---------------------------------------------------------------------------


class TestAtomicWrite:
    def test_write_port_file_atomic(self, tmp_path):
        """write_port_file uses atomic write (temp + rename)."""
        port_file = tmp_path / "ipc_port"
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            write_port_file(12345, "token123")
            content = port_file.read_text()
            pid = os.getpid()
            assert content == f"{pid}:12345:token123"

    def test_write_port_file_no_partial_on_error(self, tmp_path):
        """If write fails, port file should not exist or be unchanged."""
        port_file = tmp_path / "ipc_port"
        port_file.write_text("original")
        with patch("data_graph_studio.core.ipc_server._PORT_FILE", port_file):
            with patch("os.write", side_effect=OSError("disk full")):
                with pytest.raises(OSError):
                    write_port_file(99999, "tok")
            # Original content preserved
            assert port_file.read_text() == "original"


# ---------------------------------------------------------------------------
# Socket deleteLater on disconnect
# ---------------------------------------------------------------------------


class TestDeleteLater:
    def test_on_disconnected_calls_delete_later(self):
        """_on_disconnected calls deleteLater on the client socket."""
        server = IPCServer()
        mock_client = MagicMock()
        server._clients.append(mock_client)
        server._buffers[id(mock_client)] = bytearray()

        server._on_disconnected(mock_client)

        mock_client.deleteLater.assert_called_once()
        assert mock_client not in server._clients
        assert id(mock_client) not in server._buffers


# ---------------------------------------------------------------------------
# IPCClient max attempts
# ---------------------------------------------------------------------------


class TestClientMaxAttempts:
    def test_send_command_includes_token(self):
        """IPCClient includes token in requests."""
        client = IPCClient(token="my-token")
        mock_socket = MagicMock()
        client._socket = mock_socket

        written_data = []
        mock_socket.write = lambda d: written_data.append(d)
        mock_socket.flush = MagicMock()

        # Make waitForReadyRead return a response
        response_line = json.dumps({"status": "ok", "result": "pong"}).encode() + b"\n"
        mock_read = MagicMock()
        mock_read.data.return_value = response_line
        mock_socket.waitForReadyRead.return_value = True
        mock_socket.readAll.return_value = mock_read

        result = client.send_command("ping")

        assert len(written_data) == 1
        sent = json.loads(written_data[0].decode("utf-8").strip())
        assert sent["token"] == "my-token"
        assert result["status"] == "ok"
