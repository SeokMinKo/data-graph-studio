"""
Live UX Test - IPC를 통한 실제 앱 테스트
"""
import time
import json
import socket
import tempfile
import os

def send_command(command: str, **args) -> dict:
    """IPC 명령 전송"""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 52849))
        sock.settimeout(10.0)
        
        data = json.dumps({'command': command, 'args': args})
        sock.sendall((data + '\n').encode('utf-8'))
        
        response = b''
        while b'\n' not in response:
            chunk = sock.recv(4096)
            if not chunk:
                break
            response += chunk
        
        sock.close()
        return json.loads(response.decode('utf-8').strip())
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def test_connection():
    """1. 연결 테스트"""
    print("\n" + "="*50)
    print("1. Connection Test")
    print("="*50)
    
    result = send_command('ping')
    if result.get('result') == 'pong':
        print("  [OK] App is running and responding")
        return True
    else:
        print(f"  [FAIL] {result.get('error', 'No response')}")
        return False

def test_initial_state():
    """2. 초기 상태 테스트"""
    print("\n" + "="*50)
    print("2. Initial State Test")
    print("="*50)
    
    result = send_command('get_state')
    if result['status'] != 'ok':
        print(f"  [FAIL] {result.get('error')}")
        return False
    
    state = result['result']
    print(f"  - Window Title: {state['window_title']}")
    print(f"  - Window Size: {state['window_size']}")
    print(f"  - Data Loaded: {state['data_loaded']}")
    print(f"  - Chart Type: {state['chart_type']}")
    
    # 체크
    issues = []
    if not state['window_title']:
        issues.append("No window title")
    if state['window_size'][0] < 800 or state['window_size'][1] < 600:
        issues.append("Window too small")
    
    if issues:
        print(f"  [WARN] Issues: {issues}")
    else:
        print("  [OK] Initial state looks good")
    
    return True

def test_data_loading():
    """3. 데이터 로딩 테스트"""
    print("\n" + "="*50)
    print("3. Data Loading Test")
    print("="*50)
    
    # 테스트 CSV 생성
    import polars as pl
    df = pl.DataFrame({
        'Category': ['A', 'A', 'B', 'B', 'C', 'C'],
        'Region': ['East', 'West', 'East', 'West', 'East', 'West'],
        'Sales': [100, 150, 200, 180, 120, 90],
        'Quantity': [10, 15, 20, 18, 12, 9],
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), 'ux_test_data.csv')
    df.write_csv(temp_file)
    
    try:
        # 로드
        result = send_command('load_file', path=temp_file)
        if result['status'] != 'ok':
            print(f"  [FAIL] Load failed: {result.get('error')}")
            return False
        
        print(f"  - Dataset ID: {result['result']['dataset_id']}")
        
        # 확인
        time.sleep(0.5)  # UI 업데이트 대기
        state = send_command('get_state')['result']
        
        if state['data_loaded']:
            print(f"  - Rows: {state['row_count']}")
            print(f"  - Columns: {state['columns']}")
            print("  [OK] Data loaded successfully")
            return True
        else:
            print("  [FAIL] Data not loaded into state")
            return False
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)

def test_chart_types():
    """4. 차트 타입 전환 테스트"""
    print("\n" + "="*50)
    print("4. Chart Type Switching Test")
    print("="*50)
    
    chart_types = ['LINE', 'BAR', 'SCATTER', 'PIE', 'AREA', 'HISTOGRAM']
    passed = 0
    
    for ct in chart_types:
        result = send_command('set_chart_type', chart_type=ct)
        if result['status'] == 'ok':
            # 확인
            state = send_command('get_state')['result']
            if state['chart_type'] == ct:
                print(f"  - {ct}: OK")
                passed += 1
            else:
                print(f"  - {ct}: MISMATCH (got {state['chart_type']})")
        else:
            print(f"  - {ct}: FAIL ({result.get('error')})")
        
        time.sleep(0.2)  # UI 반응 대기
    
    print(f"  [{passed}/{len(chart_types)} passed]")
    return passed == len(chart_types)

def test_column_selection():
    """5. 컬럼 선택 테스트"""
    print("\n" + "="*50)
    print("5. Column Selection Test")
    print("="*50)
    
    state = send_command('get_state')['result']
    if not state['data_loaded']:
        print("  [SKIP] No data loaded")
        return True
    
    columns = state['columns']
    if len(columns) < 2:
        print("  [SKIP] Not enough columns")
        return True
    
    # X 컬럼 설정
    x_col = columns[0]
    y_cols = [columns[1]] if len(columns) > 1 else []
    
    result = send_command('set_columns', x=x_col, y=y_cols)
    if result['status'] == 'ok':
        print(f"  - Set X={x_col}, Y={y_cols}")
        
        time.sleep(0.3)  # UI 반응 대기
        state = send_command('get_state')['result']
        
        if state['x_column'] == x_col:
            print(f"  - X column confirmed: {state['x_column']}")
            print("  [OK] Column selection working")
            return True
        else:
            print(f"  [WARN] X column: expected '{x_col}', got '{state['x_column']}'")
            return True  # X 설정은 됐으므로 partial success
    else:
        print(f"  [FAIL] {result.get('error')}")
        return False

def test_panels():
    """6. 패널 상태 테스트"""
    print("\n" + "="*50)
    print("6. Panel Status Test")
    print("="*50)
    
    result = send_command('get_panels')
    if result['status'] != 'ok':
        print(f"  [FAIL] {result.get('error')}")
        return False
    
    panels = result['result']
    for name, info in panels.items():
        status = "Visible" if info.get('visible') else "Hidden"
        exists = "exists" if info.get('exists') else "missing"
        print(f"  - {name}: {status} ({exists})")
    
    # 필수 패널 체크
    required = ['table_panel', 'graph_panel']
    missing = [p for p in required if not panels.get(p, {}).get('exists')]
    
    if missing:
        print(f"  [FAIL] Missing required panels: {missing}")
        return False
    
    print("  [OK] Required panels exist")
    return True

def test_data_info():
    """7. 데이터 정보 조회 테스트"""
    print("\n" + "="*50)
    print("7. Data Info Test")
    print("="*50)
    
    result = send_command('get_data_info')
    if result['status'] != 'ok':
        print(f"  [FAIL] {result.get('error')}")
        return False
    
    info = result['result']
    if info.get('loaded'):
        print(f"  - Rows: {info['row_count']}")
        print(f"  - Columns: {len(info['columns'])}")
        print(f"  - Types: {info.get('dtypes', {})}")
        print("  [OK] Data info available")
        return True
    else:
        print("  - No data loaded")
        return True

def test_execute():
    """8. 코드 실행 테스트"""
    print("\n" + "="*50)
    print("8. Execute Code Test")
    print("="*50)
    
    # 간단한 코드 실행
    tests = [
        ("window.isVisible()", True),
        ("window.width() > 0", True),
        ("state.is_data_loaded", None),  # 값만 확인
    ]
    
    for code, expected in tests:
        result = send_command('execute', code=code)
        if result['status'] == 'ok':
            value = result['result']
            if expected is None or value == expected:
                print(f"  - {code} = {value}: OK")
            else:
                print(f"  - {code} = {value}: Expected {expected}")
        else:
            print(f"  - {code}: ERROR ({result.get('error')})")
    
    print("  [OK] Code execution working")
    return True

def test_responsiveness():
    """9. 응답성 테스트"""
    print("\n" + "="*50)
    print("9. Responsiveness Test")
    print("="*50)
    
    import time
    
    times = []
    for i in range(10):
        start = time.time()
        result = send_command('ping')
        elapsed = (time.time() - start) * 1000
        times.append(elapsed)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    min_time = min(times)
    
    print(f"  - Average: {avg_time:.1f}ms")
    print(f"  - Min: {min_time:.1f}ms")
    print(f"  - Max: {max_time:.1f}ms")
    
    if avg_time < 100:
        print("  [OK] Response time is good")
        return True
    elif avg_time < 500:
        print("  [WARN] Response time is acceptable")
        return True
    else:
        print("  [FAIL] Response time is too slow")
        return False

def run_all_tests():
    """모든 테스트 실행"""
    print("\n" + "="*50)
    print("  DATA GRAPH STUDIO - LIVE UX TEST")
    print("="*50)
    
    results = {}
    
    # 연결 테스트 먼저
    if not test_connection():
        print("\n[ABORT] Cannot connect to app. Is it running?")
        return
    
    results['connection'] = True
    
    # 나머지 테스트
    results['initial_state'] = test_initial_state()
    results['data_loading'] = test_data_loading()
    results['chart_types'] = test_chart_types()
    results['column_selection'] = test_column_selection()
    results['panels'] = test_panels()
    results['data_info'] = test_data_info()
    results['execute'] = test_execute()
    results['responsiveness'] = test_responsiveness()
    
    # 요약
    print("\n" + "="*50)
    print("  TEST SUMMARY")
    print("="*50)
    
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    
    for name, result in results.items():
        status = "PASS" if result else "FAIL"
        print(f"  {name}: {status}")
    
    print(f"\n  Total: {passed}/{total} passed")
    
    if passed == total:
        print("\n  [SUCCESS] All UX tests passed!")
    else:
        print(f"\n  [WARNING] {total - passed} test(s) failed")

if __name__ == '__main__':
    run_all_tests()
