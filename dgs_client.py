#!/usr/bin/env python
"""
Data Graph Studio IPC Client
외부에서 실행 중인 앱 제어

Usage:
    python dgs_client.py ping
    python dgs_client.py state
    python dgs_client.py data
    python dgs_client.py chart line
    python dgs_client.py load path/to/file.csv
    python dgs_client.py exec "window.windowTitle()"
"""
import sys
import json
import socket

DEFAULT_HOST = 'localhost'
DEFAULT_PORT = 52849


def send_command(command: str, **args) -> dict:
    """명령 전송"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((DEFAULT_HOST, DEFAULT_PORT))
        sock.settimeout(5.0)
        
        data = json.dumps({'command': command, 'args': args}, ensure_ascii=False)
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
    
    elif cmd == 'exec':
        if len(sys.argv) < 3:
            print("Usage: python dgs_client.py exec <code>")
            return 1
        result = send_command('execute', code=sys.argv[2])
    
    else:
        print(f"Unknown command: {cmd}")
        print(__doc__)
        return 1
    
    # Pretty print result
    print(json.dumps(result, indent=2, ensure_ascii=False))
    
    return 0 if result.get('status') == 'ok' else 1


if __name__ == '__main__':
    sys.exit(main())
