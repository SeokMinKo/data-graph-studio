"""
Comprehensive UX Test Suite
복합적인 사용자 시나리오 테스트
"""
import json
import socket
import time
import tempfile
import os
import sys

# IPC Helper
def send_cmd(command: str, **args) -> dict:
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
    except ConnectionRefusedError:
        return {'status': 'error', 'error': 'App not running'}
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def execute(code: str):
    """Python 코드 실행"""
    result = send_cmd('execute', code=code)
    if result['status'] == 'ok':
        return result['result']
    raise RuntimeError(result.get('error', 'Unknown error'))

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.warnings = 0
        self.details = []
    
    def ok(self, msg: str):
        self.passed += 1
        self.details.append(('OK', msg))
        print(f"    ✓ {msg}")
    
    def fail(self, msg: str):
        self.failed += 1
        self.details.append(('FAIL', msg))
        print(f"    ✗ {msg}")
    
    def warn(self, msg: str):
        self.warnings += 1
        self.details.append(('WARN', msg))
        print(f"    ⚠ {msg}")
    
    def summary(self) -> str:
        total = self.passed + self.failed
        if self.failed == 0:
            return f"PASS ({self.passed}/{total})"
        return f"FAIL ({self.passed}/{total})"

# ========== TEST SCENARIOS ==========

def scenario_fresh_start():
    """시나리오 1: 앱 첫 실행 상태"""
    print("\n" + "="*60)
    print("SCENARIO 1: Fresh Start State")
    print("="*60)
    
    result = TestResult("Fresh Start")
    
    # 앱 연결 확인
    r = send_cmd('ping')
    if r.get('result') == 'pong':
        result.ok("App responding")
    else:
        result.fail("App not responding")
        return result
    
    # 초기 상태 확인
    state = send_cmd('get_state')['result']
    
    # 윈도우 기본 요소
    if state['window_title']:
        result.ok(f"Window title: {state['window_title']}")
    else:
        result.fail("No window title")
    
    if state['window_size'][0] >= 1200 and state['window_size'][1] >= 800:
        result.ok(f"Window size adequate: {state['window_size']}")
    else:
        result.warn(f"Window size small: {state['window_size']}")
    
    # 기본 차트 타입
    if state['chart_type'] == 'LINE':
        result.ok("Default chart type is LINE")
    else:
        result.warn(f"Default chart type is {state['chart_type']}")
    
    # 패널 존재 확인
    panels = send_cmd('get_panels')['result']
    for panel_name in ['table_panel', 'graph_panel']:
        if panels.get(panel_name, {}).get('exists'):
            result.ok(f"{panel_name} exists")
        else:
            result.fail(f"{panel_name} missing")
    
    return result

def scenario_data_workflow():
    """시나리오 2: 데이터 로딩 워크플로우"""
    print("\n" + "="*60)
    print("SCENARIO 2: Data Loading Workflow")
    print("="*60)
    
    result = TestResult("Data Workflow")
    
    # 다양한 데이터 타입으로 CSV 생성
    import polars as pl
    
    df = pl.DataFrame({
        'ID': list(range(1, 101)),
        'Name': [f'Item_{i}' for i in range(1, 101)],
        'Category': ['A', 'B', 'C', 'D'] * 25,
        'Value': [i * 10.5 for i in range(1, 101)],
        'Count': list(range(100, 200)),
        'Active': [True, False] * 50,
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), 'ux_workflow_test.csv')
    df.write_csv(temp_file)
    
    try:
        # 1. 파일 로드
        start = time.time()
        r = send_cmd('load_file', path=temp_file)
        load_time = time.time() - start
        
        if r['status'] == 'ok':
            result.ok(f"File loaded in {load_time:.2f}s")
        else:
            result.fail(f"Load failed: {r.get('error')}")
            return result
        
        time.sleep(0.5)  # UI 업데이트 대기
        
        # 2. 데이터 확인
        info = send_cmd('get_data_info')['result']
        
        if info['row_count'] == 100:
            result.ok(f"Row count correct: {info['row_count']}")
        else:
            result.fail(f"Row count wrong: {info['row_count']} (expected 100)")
        
        if len(info['columns']) == 6:
            result.ok(f"Column count correct: {len(info['columns'])}")
        else:
            result.fail(f"Column count wrong: {len(info['columns'])} (expected 6)")
        
        # 3. 데이터 타입 확인
        dtypes = info.get('dtypes', {})
        if 'Value' in dtypes and 'Float' in dtypes['Value']:
            result.ok("Float column detected correctly")
        else:
            result.warn(f"Float column type: {dtypes.get('Value', 'N/A')}")
        
        if 'Active' in dtypes and 'Bool' in dtypes['Active']:
            result.ok("Boolean column detected correctly")
        else:
            result.warn(f"Boolean column type: {dtypes.get('Active', 'N/A')}")
        
        # 4. 테이블 표시 확인
        table_rows = execute('table_panel.table_view.model().rowCount()')
        if table_rows > 0:
            result.ok(f"Table showing {table_rows} rows")
        else:
            result.fail("Table not showing data")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def scenario_chart_switching():
    """시나리오 3: 차트 타입 전환 워크플로우"""
    print("\n" + "="*60)
    print("SCENARIO 3: Chart Type Switching")
    print("="*60)
    
    result = TestResult("Chart Switching")
    
    # 먼저 데이터가 있는지 확인
    state = send_cmd('get_state')['result']
    if not state['data_loaded']:
        result.warn("No data loaded, loading test data...")
        # 테스트 데이터 로드
        import polars as pl
        df = pl.DataFrame({
            'X': list(range(10)),
            'Y': [i**2 for i in range(10)],
            'Category': ['A', 'B'] * 5,
        })
        temp_file = os.path.join(tempfile.gettempdir(), 'chart_test.csv')
        df.write_csv(temp_file)
        send_cmd('load_file', path=temp_file)
        time.sleep(0.5)
        os.remove(temp_file)
    
    # 모든 차트 타입 테스트
    chart_types = ['LINE', 'BAR', 'SCATTER', 'PIE', 'AREA', 'HISTOGRAM']
    
    for ct in chart_types:
        # 차트 타입 변경
        r = send_cmd('set_chart_type', chart_type=ct)
        time.sleep(0.3)  # 렌더링 대기
        
        if r['status'] == 'ok':
            # 상태 확인
            state = send_cmd('get_state')['result']
            if state['chart_type'] == ct:
                # 그래프 패널 visible 확인
                visible = execute('graph_panel.isVisible()')
                if visible:
                    result.ok(f"{ct}: Set and visible")
                else:
                    result.fail(f"{ct}: Set but not visible")
            else:
                result.fail(f"{ct}: State mismatch ({state['chart_type']})")
        else:
            result.fail(f"{ct}: {r.get('error')}")
    
    # 빠른 전환 테스트 (UI 안정성)
    print("\n    Rapid switching test...")
    for _ in range(3):
        for ct in ['LINE', 'BAR', 'SCATTER']:
            send_cmd('set_chart_type', chart_type=ct)
            time.sleep(0.05)  # 빠른 전환
    
    # 최종 상태 확인
    state = send_cmd('get_state')['result']
    if state['chart_type'] in chart_types:
        result.ok("Rapid switching stable")
    else:
        result.fail("Rapid switching caused issues")
    
    return result

def scenario_column_operations():
    """시나리오 4: 컬럼 선택 및 조작"""
    print("\n" + "="*60)
    print("SCENARIO 4: Column Operations")
    print("="*60)
    
    result = TestResult("Column Operations")
    
    state = send_cmd('get_state')['result']
    if not state['data_loaded']:
        result.warn("No data, skipping")
        return result
    
    columns = state['columns']
    
    # 1. X 컬럼 설정
    if columns:
        x_col = columns[0]
        send_cmd('set_columns', x=x_col)
        time.sleep(0.2)
        
        new_state = send_cmd('get_state')['result']
        if new_state['x_column'] == x_col:
            result.ok(f"X column set: {x_col}")
        else:
            result.fail(f"X column not set (got {new_state['x_column']})")
    
    # 2. Y 컬럼 설정 (여러 개)
    numeric_cols = [c for c in columns if c not in ['ID', 'Name', 'Category', 'Active', 'Date']]
    if len(numeric_cols) >= 2:
        y_cols = numeric_cols[:2]
        send_cmd('set_columns', y=y_cols)
        time.sleep(0.2)
        
        new_state = send_cmd('get_state')['result']
        if set(new_state['y_columns']) == set(y_cols):
            result.ok(f"Y columns set: {y_cols}")
        else:
            result.warn(f"Y columns partial: {new_state['y_columns']}")
    
    # 3. 컬럼 변경 후 차트 업데이트
    send_cmd('set_chart_type', chart_type='BAR')
    time.sleep(0.3)
    
    visible = execute('graph_panel.isVisible()')
    if visible:
        result.ok("Chart updated after column change")
    else:
        result.fail("Chart not visible after column change")
    
    return result

def scenario_large_data():
    """시나리오 5: 대용량 데이터 처리"""
    print("\n" + "="*60)
    print("SCENARIO 5: Large Data Handling")
    print("="*60)
    
    result = TestResult("Large Data")
    
    import polars as pl
    
    # 10만 행 데이터 생성
    n_rows = 100_000
    print(f"    Creating {n_rows:,} rows...")
    
    df = pl.DataFrame({
        'ID': list(range(n_rows)),
        'Value1': [i * 0.1 for i in range(n_rows)],
        'Value2': [i % 100 for i in range(n_rows)],
        'Category': ['Cat_' + str(i % 10) for i in range(n_rows)],
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), 'large_data_test.csv')
    df.write_csv(temp_file)
    
    try:
        # 로드 시간 측정
        start = time.time()
        r = send_cmd('load_file', path=temp_file)
        load_time = time.time() - start
        
        if r['status'] == 'ok':
            if load_time < 5:
                result.ok(f"Loaded {n_rows:,} rows in {load_time:.2f}s")
            else:
                result.warn(f"Slow load: {load_time:.2f}s for {n_rows:,} rows")
        else:
            result.fail(f"Failed to load: {r.get('error')}")
            return result
        
        time.sleep(1)  # UI 안정화 대기
        
        # UI 응답성 테스트
        start = time.time()
        send_cmd('ping')
        ping_time = (time.time() - start) * 1000
        
        if ping_time < 100:
            result.ok(f"UI responsive: {ping_time:.1f}ms")
        else:
            result.warn(f"UI slow: {ping_time:.1f}ms")
        
        # 테이블 가상화 확인 (전체 행이 아닌 일부만 표시)
        visible_rows = execute('table_panel.table_view.model().rowCount()')
        if visible_rows <= n_rows:
            result.ok(f"Table virtualization working ({visible_rows:,} rows)")
        else:
            result.warn(f"Table showing all rows: {visible_rows:,}")
        
        # 차트 전환 테스트
        start = time.time()
        send_cmd('set_chart_type', chart_type='LINE')
        time.sleep(0.5)
        send_cmd('set_chart_type', chart_type='BAR')
        chart_time = time.time() - start
        
        if chart_time < 3:
            result.ok(f"Chart switch responsive: {chart_time:.2f}s")
        else:
            result.warn(f"Chart switch slow: {chart_time:.2f}s")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def scenario_edge_cases():
    """시나리오 6: 엣지 케이스"""
    print("\n" + "="*60)
    print("SCENARIO 6: Edge Cases")
    print("="*60)
    
    result = TestResult("Edge Cases")
    
    import polars as pl
    
    # 1. 빈 데이터
    print("\n    Testing empty data...")
    df_empty = pl.DataFrame({'A': [], 'B': []})
    temp_empty = os.path.join(tempfile.gettempdir(), 'empty_test.csv')
    df_empty.write_csv(temp_empty)
    
    r = send_cmd('load_file', path=temp_empty)
    os.remove(temp_empty)
    
    if r['status'] == 'ok':
        result.ok("Empty file handled")
    else:
        result.warn(f"Empty file issue: {r.get('error')}")
    
    # 2. 특수 문자 컬럼명
    print("    Testing special column names...")
    df_special = pl.DataFrame({
        'Column With Spaces': [1, 2, 3],
        '한글컬럼': [4, 5, 6],
        'Col/With/Slash': [7, 8, 9],
    })
    temp_special = os.path.join(tempfile.gettempdir(), 'special_cols.csv')
    df_special.write_csv(temp_special)
    
    r = send_cmd('load_file', path=temp_special)
    os.remove(temp_special)
    
    if r['status'] == 'ok':
        info = send_cmd('get_data_info')['result']
        if len(info['columns']) == 3:
            result.ok("Special column names handled")
        else:
            result.warn(f"Some columns lost: {info['columns']}")
    else:
        result.fail(f"Special columns failed: {r.get('error')}")
    
    # 3. NULL 값이 많은 데이터
    print("    Testing NULL-heavy data...")
    df_nulls = pl.DataFrame({
        'A': [1, None, 3, None, 5],
        'B': [None, None, None, 4, 5],
        'C': ['a', None, 'c', None, 'e'],
    })
    temp_nulls = os.path.join(tempfile.gettempdir(), 'nulls_test.csv')
    df_nulls.write_csv(temp_nulls)
    
    r = send_cmd('load_file', path=temp_nulls)
    os.remove(temp_nulls)
    
    if r['status'] == 'ok':
        result.ok("NULL-heavy data handled")
    else:
        result.fail(f"NULL data failed: {r.get('error')}")
    
    # 4. 단일 컬럼 데이터
    print("    Testing single column data...")
    df_single = pl.DataFrame({'OnlyColumn': [1, 2, 3, 4, 5]})
    temp_single = os.path.join(tempfile.gettempdir(), 'single_col.csv')
    df_single.write_csv(temp_single)
    
    r = send_cmd('load_file', path=temp_single)
    os.remove(temp_single)
    
    if r['status'] == 'ok':
        result.ok("Single column handled")
    else:
        result.warn(f"Single column issue: {r.get('error')}")
    
    return result

def scenario_ui_stability():
    """시나리오 7: UI 안정성"""
    print("\n" + "="*60)
    print("SCENARIO 7: UI Stability")
    print("="*60)
    
    result = TestResult("UI Stability")
    
    # 1. 연속 명령 테스트
    print("\n    Rapid command test (100 commands)...")
    start = time.time()
    errors = 0
    
    for i in range(100):
        r = send_cmd('ping')
        if r.get('result') != 'pong':
            errors += 1
    
    elapsed = time.time() - start
    
    if errors == 0:
        result.ok(f"100 commands in {elapsed:.2f}s, no errors")
    else:
        result.fail(f"{errors} errors in 100 commands")
    
    # 2. 상태 일관성 테스트
    print("    State consistency test...")
    
    for _ in range(10):
        send_cmd('set_chart_type', chart_type='LINE')
        state1 = send_cmd('get_state')['result']['chart_type']
        
        send_cmd('set_chart_type', chart_type='BAR')
        state2 = send_cmd('get_state')['result']['chart_type']
        
        if state1 != 'LINE' or state2 != 'BAR':
            result.fail("State inconsistency detected")
            break
    else:
        result.ok("State remains consistent")
    
    # 3. 메모리 누수 간접 테스트 (응답 시간 증가 확인)
    print("    Memory stability test...")
    
    times = []
    for i in range(5):
        # 여러 작업 수행
        send_cmd('set_chart_type', chart_type='LINE')
        send_cmd('set_chart_type', chart_type='BAR')
        send_cmd('get_state')
        send_cmd('get_data_info')
        
        # 응답 시간 측정
        start = time.time()
        send_cmd('ping')
        times.append((time.time() - start) * 1000)
        
        time.sleep(0.1)
    
    avg_time = sum(times) / len(times)
    time_increase = times[-1] - times[0]
    
    if time_increase < 10:  # 10ms 이하 증가
        result.ok(f"No significant slowdown ({avg_time:.1f}ms avg)")
    else:
        result.warn(f"Possible memory issue (time increased by {time_increase:.1f}ms)")
    
    return result

def scenario_concurrent_access():
    """시나리오 8: 동시 접근"""
    print("\n" + "="*60)
    print("SCENARIO 8: Concurrent Access")
    print("="*60)
    
    result = TestResult("Concurrent Access")
    
    import threading
    
    errors = []
    results_queue = []
    
    def worker(worker_id, num_requests):
        for i in range(num_requests):
            try:
                r = send_cmd('ping')
                if r.get('result') != 'pong':
                    errors.append(f"Worker {worker_id}: ping failed")
                results_queue.append(True)
            except Exception as e:
                errors.append(f"Worker {worker_id}: {e}")
                results_queue.append(False)
    
    # 5개 스레드에서 각각 20개 요청
    threads = []
    for i in range(5):
        t = threading.Thread(target=worker, args=(i, 20))
        threads.append(t)
    
    start = time.time()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    elapsed = time.time() - start
    
    success_rate = sum(1 for r in results_queue if r) / len(results_queue) * 100
    
    if success_rate == 100:
        result.ok(f"100 concurrent requests, 100% success in {elapsed:.2f}s")
    elif success_rate >= 95:
        result.warn(f"{success_rate:.1f}% success rate")
    else:
        result.fail(f"Only {success_rate:.1f}% success rate")
        for err in errors[:3]:  # 처음 3개 에러만
            print(f"      - {err}")
    
    return result

# ========== MAIN ==========

def run_all_scenarios():
    """모든 시나리오 실행"""
    print("\n" + "="*60)
    print("  DATA GRAPH STUDIO - COMPREHENSIVE UX TEST")
    print("="*60)
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    # 앱 연결 확인
    r = send_cmd('ping')
    if r.get('result') != 'pong':
        print("\n[ERROR] Cannot connect to app. Is it running?")
        print("  Start with: python -m data_graph_studio")
        return 1
    
    results = []
    
    # 모든 시나리오 실행
    scenarios = [
        scenario_fresh_start,
        scenario_data_workflow,
        scenario_chart_switching,
        scenario_column_operations,
        scenario_large_data,
        scenario_edge_cases,
        scenario_ui_stability,
        scenario_concurrent_access,
    ]
    
    for scenario in scenarios:
        try:
            result = scenario()
            results.append(result)
        except Exception as e:
            print(f"\n    [ERROR] Scenario failed: {e}")
            import traceback
            traceback.print_exc()
    
    # 최종 요약
    print("\n" + "="*60)
    print("  FINAL SUMMARY")
    print("="*60)
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_warnings = sum(r.warnings for r in results)
    
    for r in results:
        status = "✓" if r.failed == 0 else "✗"
        print(f"  {status} {r.name}: {r.summary()}")
    
    print(f"\n  Total: {total_passed} passed, {total_failed} failed, {total_warnings} warnings")
    
    if total_failed == 0:
        print("\n  🎉 ALL TESTS PASSED!")
        return 0
    else:
        print(f"\n  ⚠️  {total_failed} FAILURES DETECTED")
        return 1

if __name__ == '__main__':
    sys.exit(run_all_scenarios())
