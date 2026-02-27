#!/usr/bin/env python
"""
Data Graph Studio IPC Client
외부에서 실행 중인 앱 제어

Uses Unix Domain Socket to communicate with the running DGS instance.

Usage:
    python dgs_client.py ping
    python dgs_client.py state
    python dgs_client.py data
    python dgs_client.py chart line
    python dgs_client.py load path/to/file.csv
"""
import sys
import json
import os
import socket

DEFAULT_PORT = 52849
_PORT_FILE = os.path.expanduser("~/.dgs/ipc_port")
_SOCKET_NAME = "dgs-ipc"


def _read_port_file():
    """Read port and token from ~/.dgs/ipc_port (pid:port:token).

    Returns (port, token) if the owning process is alive, else None.
    """
    try:
        with open(_PORT_FILE) as f:
            text = f.read().strip()
        parts = text.split(":")
        if len(parts) >= 3:
            pid, port, token = int(parts[0]), int(parts[1]), parts[2]
        elif len(parts) == 2:
            pid, port = int(parts[0]), int(parts[1])
            token = ""
        else:
            return None
        # Check if owning process is alive
        try:
            os.kill(pid, 0)
        except (OSError, ProcessLookupError):
            return None  # stale
        return (port, token)
    except (FileNotFoundError, ValueError, OSError):
        return None


def _get_socket_path():
    """Resolve the abstract/filesystem socket path used by QLocalServer."""
    # QLocalServer on Linux uses abstract namespace: '\0' + name
    # For a raw Python socket, we connect to the abstract namespace.
    # On macOS, QLocalServer uses /tmp/<name>
    if sys.platform == 'darwin':
        return f"/tmp/{_SOCKET_NAME}"
    # Linux: abstract namespace
    return f"\0{_SOCKET_NAME}"


def send_command(command: str, **args) -> dict:
    """명령 전송 (Unix Domain Socket)"""
    port_info = _read_port_file()
    token = port_info[1] if port_info else ""

    socket_path = _get_socket_path()
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_path)
        sock.settimeout(5.0)

        data = json.dumps({
            'command': command,
            'args': args,
            'token': token,
        }, ensure_ascii=False)
        sock.sendall((data + '\n').encode('utf-8'))

        response = b''
        while True:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
            if b'\n' in response:
                break

        sock.close()
        return json.loads(response.decode('utf-8').strip())
    except ConnectionRefusedError:
        return {'status': 'error', 'error': 'App not running or IPC server not started'}
    except FileNotFoundError:
        return {'status': 'error', 'error': 'IPC socket not found. Is the app running?'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    cmd = sys.argv[1].lower()

    if cmd == 'ping':
        result = send_command('ping')

    elif cmd == 'state':
        result = send_command('get_state')

    elif cmd == 'data':
        result = send_command('get_data_info')

    elif cmd == 'panels':
        result = send_command('get_panels')

    elif cmd == 'chart':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py chart <type>")
            print("Types: LINE, BAR, SCATTER, PIE, AREA, HISTOGRAM")
            return 1
        result = send_command('set_chart_type', chart_type=sys.argv[2])

    elif cmd == 'columns':
        x = sys.argv[2] if len(sys.argv) > 2 else None
        y = sys.argv[3:] if len(sys.argv) > 3 else None
        result = send_command('set_columns', x=x, y=y)

    elif cmd == 'load':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py load <file_path>")
            return 1
        result = send_command('load_file', path=sys.argv[2])

    # ==================== Profile Comparison ====================

    elif cmd == 'list-profiles':
        kwargs = {}
        if len(sys.argv) > 2:
            kwargs['dataset_id'] = sys.argv[2]
        result = send_command('list_profiles', **kwargs)

    elif cmd == 'create-profile':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py create-profile <name> [dataset_id]")
            return 1
        kwargs = {'name': sys.argv[2]}
        if len(sys.argv) > 3:
            kwargs['dataset_id'] = sys.argv[3]
        result = send_command('create_profile', **kwargs)

    elif cmd == 'apply-profile':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py apply-profile <profile_id>")
            return 1
        result = send_command('apply_profile', profile_id=sys.argv[2])

    elif cmd == 'delete-profile':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py delete-profile <profile_id>")
            return 1
        result = send_command('delete_profile', profile_id=sys.argv[2])

    elif cmd == 'duplicate-profile':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py duplicate-profile <profile_id>")
            return 1
        result = send_command('duplicate_profile', profile_id=sys.argv[2])

    elif cmd == 'start-comparison':
        if len(sys.argv) < 4:
            print("Usage: python dgs_client.py start-comparison <mode> <profile_id1> <profile_id2> [...]")
            print("Modes: side_by_side, overlay, difference")
            return 1
        mode = sys.argv[2]
        profile_ids = sys.argv[3:]
        result = send_command('start_profile_comparison', profile_ids=profile_ids, mode=mode)

    elif cmd == 'stop-comparison':
        result = send_command('stop_profile_comparison')

    elif cmd == 'comparison-state':
        result = send_command('get_profile_comparison_state')

    elif cmd == 'set-sync':
        kwargs = {}
        for arg in sys.argv[2:]:
            key, _, val = arg.partition('=')
            if key in ('sync_x', 'sync_y', 'sync_selection'):
                kwargs[key] = val.lower() in ('true', '1', 'yes')
        if not kwargs:
            print("Usage: python dgs_client.py set-sync sync_x=true sync_y=false sync_selection=true")
            return 1
        result = send_command('set_comparison_sync', **kwargs)

    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1

    # Pretty print result
    print(json.dumps(result, indent=2, ensure_ascii=False))

    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
