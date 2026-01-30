"""
IPC Server - 외부 프로세스에서 앱 제어 가능하게 해주는 서버
"""
import json
import threading
from typing import Optional, Callable, Any
from PySide6.QtCore import QObject, Signal, QThread
from PySide6.QtNetwork import QTcpServer, QTcpSocket, QHostAddress


class IPCServer(QObject):
    """로컬 TCP 서버로 외부 프로세스와 통신"""
    
    command_received = Signal(str, object)  # command, args
    response_ready = Signal(str)
    
    DEFAULT_PORT = 52849  # Data Graph Studio port
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._server = QTcpServer(self)
        self._clients: list[QTcpSocket] = []
        self._handlers: dict[str, Callable] = {}
        
        self._server.newConnection.connect(self._on_new_connection)
    
    def start(self, port: int = None) -> bool:
        """서버 시작"""
        port = port or self.DEFAULT_PORT
        
        if self._server.listen(QHostAddress.LocalHost, port):
            print(f"[IPC] Server listening on localhost:{port}")
            return True
        else:
            print(f"[IPC] Failed to start server: {self._server.errorString()}")
            return False
    
    def stop(self):
        """서버 중지"""
        for client in self._clients:
            client.close()
        self._clients.clear()
        self._server.close()
        print("[IPC] Server stopped")
    
    def register_handler(self, command: str, handler: Callable):
        """명령 핸들러 등록"""
        self._handlers[command] = handler
    
    def _on_new_connection(self):
        """새 연결 처리"""
        while self._server.hasPendingConnections():
            client = self._server.nextPendingConnection()
            self._clients.append(client)
            client.readyRead.connect(lambda c=client: self._on_data_ready(c))
            client.disconnected.connect(lambda c=client: self._on_disconnected(c))
            print(f"[IPC] Client connected: {client.peerAddress().toString()}")
    
    def _on_data_ready(self, client: QTcpSocket):
        """데이터 수신"""
        while client.canReadLine():
            line = client.readLine().data().decode('utf-8').strip()
            if line:
                self._process_command(client, line)
    
    def _on_disconnected(self, client: QTcpSocket):
        """연결 종료"""
        if client in self._clients:
            self._clients.remove(client)
        print("[IPC] Client disconnected")
    
    def _process_command(self, client: QTcpSocket, line: str):
        """명령 처리"""
        try:
            data = json.loads(line)
            command = data.get('command', '')
            args = data.get('args', {})
            
            if command in self._handlers:
                try:
                    result = self._handlers[command](**args)
                    response = {'status': 'ok', 'result': result}
                except Exception as e:
                    response = {'status': 'error', 'error': str(e)}
            else:
                response = {'status': 'error', 'error': f'Unknown command: {command}'}
            
            self._send_response(client, response)
            
        except json.JSONDecodeError as e:
            self._send_response(client, {'status': 'error', 'error': f'Invalid JSON: {e}'})
    
    def _send_response(self, client: QTcpSocket, response: dict):
        """응답 전송"""
        line = json.dumps(response, ensure_ascii=False, default=str) + '\n'
        client.write(line.encode('utf-8'))
        client.flush()


class IPCClient:
    """IPC 클라이언트 - 외부에서 앱 제어용"""
    
    def __init__(self, host: str = 'localhost', port: int = 52849):
        self.host = host
        self.port = port
        self._socket = None
    
    def connect(self) -> bool:
        """서버에 연결"""
        import socket
        try:
            self._socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._socket.connect((self.host, self.port))
            self._socket.settimeout(5.0)
            return True
        except Exception as e:
            print(f"[IPC Client] Connection failed: {e}")
            return False
    
    def disconnect(self):
        """연결 종료"""
        if self._socket:
            self._socket.close()
            self._socket = None
    
    def send_command(self, command: str, **args) -> dict:
        """명령 전송 및 응답 수신"""
        if not self._socket:
            return {'status': 'error', 'error': 'Not connected'}
        
        try:
            data = json.dumps({'command': command, 'args': args}, ensure_ascii=False)
            self._socket.sendall((data + '\n').encode('utf-8'))
            
            # 응답 수신
            response = b''
            while True:
                chunk = self._socket.recv(4096)
                response += chunk
                if b'\n' in response:
                    break
            
            return json.loads(response.decode('utf-8').strip())
        except Exception as e:
            return {'status': 'error', 'error': str(e)}
    
    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args):
        self.disconnect()


# 편의 함수
def send_command(command: str, **args) -> dict:
    """단일 명령 전송 (자동 연결/해제)"""
    with IPCClient() as client:
        return client.send_command(command, **args)
