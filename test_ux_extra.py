"""추가 UX 체크"""
import json
import socket

def cmd(command, **args):
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.connect(('localhost', 52849))
    sock.settimeout(5.0)
    data = json.dumps({'command': command, 'args': args})
    sock.sendall((data + '\n').encode('utf-8'))
    response = b''
    while b'\n' not in response:
        response += sock.recv(4096)
    sock.close()
    return json.loads(response.decode('utf-8').strip())

print('=== Additional UX Checks ===')
print()

# 테이블 모델 체크
result = cmd('execute', code='table_panel.table_view.model().rowCount()')
print(f"Table rows visible: {result.get('result', 'N/A')}")

result = cmd('execute', code='table_panel.table_view.model().columnCount()')
print(f"Table columns visible: {result.get('result', 'N/A')}")

# 그래프 아이템 체크
result = cmd('execute', code='len(graph_panel.graph._plot_items)')
print(f"Graph plot items: {result.get('result', 'N/A')}")

# 메뉴 액션 체크
result = cmd('execute', code='len([a for a in window.menuBar().actions() if a.text()])')
print(f"Menu items: {result.get('result', 'N/A')}")

# 윈도우 상태 체크
result = cmd('execute', code='window.isMaximized()')
print(f"Window maximized: {result.get('result', 'N/A')}")

result = cmd('execute', code='window.isMinimized()')
print(f"Window minimized: {result.get('result', 'N/A')}")

# 상태바 체크
result = cmd('execute', code='window.statusBar().isVisible()')
print(f"StatusBar visible: {result.get('result', 'N/A')}")

print()
print('=== All checks complete ===')
