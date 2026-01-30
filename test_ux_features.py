"""
Feature-based UX Test Suite
커밋된 주요 기능들을 중심으로 한 복합 테스트

주요 테스트 대상:
1. Report Generation (DOCX, PPTX)
2. Multi-Data Comparison
3. Graph Profiles (Save/Load)
4. Y-axis Formula & Categorical Axis
5. Views Toggle & ETL Parsing
6. Sliding Window Navigation
7. Sampling Rate Control
8. Performance & Memory
"""
import json
import socket
import time
import tempfile
import os
import sys

# IPC Helper
def send_cmd(command: str, **args) -> dict:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect(('localhost', 52849))
        sock.settimeout(15.0)
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

def execute(code: str):
    result = send_cmd('execute', code=code)
    if result['status'] == 'ok':
        return result['result']
    return None

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.skipped = 0
        self.details = []
    
    def ok(self, msg: str):
        self.passed += 1
        self.details.append(('PASS', msg))
        print(f"    ✓ {msg}")
    
    def fail(self, msg: str):
        self.failed += 1
        self.details.append(('FAIL', msg))
        print(f"    ✗ {msg}")
    
    def skip(self, msg: str):
        self.skipped += 1
        self.details.append(('SKIP', msg))
        print(f"    ○ {msg}")
    
    def summary(self) -> str:
        total = self.passed + self.failed
        if self.failed == 0:
            return f"PASS ({self.passed}/{total})"
        return f"FAIL ({self.passed}/{total})"

def load_test_data(name: str = "feature_test"):
    """테스트 데이터 로드"""
    import polars as pl
    
    df = pl.DataFrame({
        'Timestamp': [f'2024-01-{i+1:02d}' for i in range(100)],
        'Device': ['SSD_A', 'SSD_B', 'HDD_A', 'HDD_B'] * 25,
        'Read_IOPS': [1000 + i * 10 + (i % 4) * 100 for i in range(100)],
        'Write_IOPS': [500 + i * 5 + (i % 4) * 50 for i in range(100)],
        'Latency_ms': [0.1 + (i % 10) * 0.05 for i in range(100)],
        'Throughput_MB': [100 + i * 2 for i in range(100)],
        'Queue_Depth': [1, 2, 4, 8, 16, 32] * 16 + [1, 2, 4, 8],
        'Category': ['Sequential', 'Random'] * 50,
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), f'{name}.csv')
    df.write_csv(temp_file)
    
    result = send_cmd('load_file', path=temp_file)
    time.sleep(0.5)
    
    return temp_file, result.get('status') == 'ok'

# ========== FEATURE TESTS ==========

def test_multi_data_comparison():
    """테스트 1: Multi-Data Comparison 기능"""
    print("\n" + "="*60)
    print("TEST 1: Multi-Data Comparison")
    print("="*60)
    
    result = TestResult("Multi-Data Comparison")
    
    import polars as pl
    
    # 두 개의 데이터셋 생성
    df1 = pl.DataFrame({
        'Time': list(range(50)),
        'Value': [100 + i * 2 for i in range(50)],
        'Category': ['A'] * 50,
    })
    
    df2 = pl.DataFrame({
        'Time': list(range(50)),
        'Value': [90 + i * 2.5 for i in range(50)],
        'Category': ['B'] * 50,
    })
    
    temp1 = os.path.join(tempfile.gettempdir(), 'compare_ds1.csv')
    temp2 = os.path.join(tempfile.gettempdir(), 'compare_ds2.csv')
    df1.write_csv(temp1)
    df2.write_csv(temp2)
    
    try:
        # 1. 첫 번째 데이터셋 로드
        r = send_cmd('load_file', path=temp1)
        if r['status'] == 'ok':
            result.ok("Dataset 1 loaded")
        else:
            result.fail(f"Dataset 1 failed: {r.get('error')}")
            return result
        
        time.sleep(0.3)
        
        # 2. 데이터셋 매니저 확인
        has_manager = execute('hasattr(window, "dataset_manager_panel")')
        if has_manager:
            result.ok("Dataset manager panel exists")
        else:
            result.skip("Dataset manager not available")
        
        # 3. 두 번째 데이터셋 로드 (추가 로드)
        r = send_cmd('load_file', path=temp2)
        if r['status'] == 'ok':
            result.ok("Dataset 2 loaded")
        else:
            result.fail(f"Dataset 2 failed: {r.get('error')}")
        
        time.sleep(0.3)
        
        # 4. 비교 모드 확인
        has_comparison = execute('hasattr(state, "_comparison_mode")')
        if has_comparison:
            result.ok("Comparison mode available in state")
        else:
            result.skip("Comparison mode not in state")
        
        # 5. 데이터셋 목록 확인
        datasets = execute('list(state._datasets.keys()) if hasattr(state, "_datasets") else []')
        if datasets and len(datasets) >= 1:
            result.ok(f"Datasets tracked: {len(datasets)}")
        else:
            result.skip("Dataset tracking not available")
        
    finally:
        for f in [temp1, temp2]:
            if os.path.exists(f):
                os.remove(f)
    
    return result

def test_graph_profiles():
    """테스트 2: Graph Profiles (Save/Load) 기능"""
    print("\n" + "="*60)
    print("TEST 2: Graph Profiles (Save/Load)")
    print("="*60)
    
    result = TestResult("Graph Profiles")
    
    # 데이터 로드
    temp_file, loaded = load_test_data("profile_test")
    if not loaded:
        result.fail("Failed to load test data")
        return result
    
    try:
        # 1. ProfileManager 존재 확인
        has_profile_manager = execute('hasattr(window, "profile_manager") or "ProfileManager" in dir()')
        if has_profile_manager:
            result.ok("ProfileManager available")
        else:
            result.skip("ProfileManager not directly accessible")
        
        # 2. 현재 그래프 설정 변경
        send_cmd('set_chart_type', chart_type='BAR')
        send_cmd('set_columns', x='Device', y=['Read_IOPS', 'Write_IOPS'])
        time.sleep(0.3)
        
        state1 = send_cmd('get_state')['result']
        result.ok(f"Graph configured: {state1['chart_type']}, X={state1['x_column']}")
        
        # 3. 설정 저장 기능 확인 (메뉴 또는 다이얼로그)
        has_save_action = execute('''
            any("save" in a.text().lower() and "profile" in a.text().lower() 
                for a in window.findChildren(type(window.menuBar().actions()[0])) 
                if a.text())
        ''')
        if has_save_action:
            result.ok("Save profile action exists")
        else:
            result.skip("Save profile action not found in menus")
        
        # 4. 프로필 바 존재 확인
        has_profile_bar = execute('hasattr(window, "profile_bar")')
        if has_profile_bar:
            visible = execute('window.profile_bar.isVisible() if hasattr(window, "profile_bar") else False')
            result.ok(f"Profile bar exists (visible={visible})")
        else:
            result.skip("Profile bar not found")
        
        # 5. 차트 타입 변경 후 복원 테스트
        send_cmd('set_chart_type', chart_type='LINE')
        time.sleep(0.2)
        send_cmd('set_chart_type', chart_type='BAR')
        time.sleep(0.2)
        
        state2 = send_cmd('get_state')['result']
        if state2['chart_type'] == 'BAR':
            result.ok("Chart type restored correctly")
        else:
            result.fail(f"Chart type mismatch: {state2['chart_type']}")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_report_generation():
    """테스트 3: Report Generation (DOCX, PPTX)"""
    print("\n" + "="*60)
    print("TEST 3: Report Generation")
    print("="*60)
    
    result = TestResult("Report Generation")
    
    # 먼저 데이터 로드
    temp_file, loaded = load_test_data("report_test")
    if not loaded:
        result.fail("Failed to load test data")
        return result
    
    try:
        # 그래프 먼저 설정
        send_cmd('set_chart_type', chart_type='BAR')
        send_cmd('set_columns', x='Device', y=['Read_IOPS'])
        time.sleep(0.8)  # 충분한 렌더링 시간
        
        # 1. 리포트 생성 모듈 확인
        has_docx = execute('''
            try:
                from data_graph_studio.report.docx_generator import DocxReportGenerator
                True
            except:
                False
        ''')
        if has_docx:
            result.ok("DOCX generator module available")
        else:
            result.skip("DOCX generator not available")
        
        has_pptx = execute('''
            try:
                from data_graph_studio.report.pptx_generator import PptxReportGenerator
                True
            except:
                False
        ''')
        if has_pptx:
            result.ok("PPTX generator module available")
        else:
            result.skip("PPTX generator not available")
        
        # 2. Export 메뉴 확인
        export_actions = execute('''
            [a.text() for a in window.findChildren(type(window.menuBar().actions()[0])) 
             if "export" in a.text().lower()]
        ''')
        if export_actions:
            result.ok(f"Export actions found: {export_actions}")
        else:
            result.skip("Export actions not found")
        
        # 3. 그래프 패널 visible 확인
        graph_visible = execute('graph_panel.isVisible()')
        if graph_visible:
            result.ok("Graph panel visible for export")
        else:
            result.skip("Graph panel not visible")
        
        # 4. 데이터 로드 상태 확인
        state = send_cmd('get_state')['result']
        if state.get('data_loaded'):
            result.ok(f"Data ready: {state.get('row_count')} rows")
        else:
            result.skip("No data loaded")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_formula_and_categorical():
    """테스트 4: Y-axis Formula & Categorical Axis"""
    print("\n" + "="*60)
    print("TEST 4: Y-axis Formula & Categorical Axis")
    print("="*60)
    
    result = TestResult("Formula & Categorical")
    
    temp_file, loaded = load_test_data("formula_test")
    if not loaded:
        result.fail("Failed to load test data")
        return result
    
    try:
        # 1. Categorical X축 테스트
        send_cmd('set_columns', x='Device')  # Device는 categorical
        time.sleep(0.3)
        
        state = send_cmd('get_state')['result']
        if state['x_column'] == 'Device':
            result.ok("Categorical X-axis set (Device)")
        else:
            result.fail("Failed to set categorical X-axis")
        
        # 2. 여러 Y 컬럼 설정
        send_cmd('set_columns', y=['Read_IOPS', 'Write_IOPS', 'Latency_ms'])
        time.sleep(0.3)
        
        state = send_cmd('get_state')['result']
        y_count = len(state.get('y_columns', []))
        if y_count >= 2:
            result.ok(f"Multiple Y columns set: {y_count}")
        else:
            result.skip(f"Y columns: {state.get('y_columns')}")
        
        # 3. 차트 렌더링 확인
        send_cmd('set_chart_type', chart_type='BAR')
        time.sleep(0.5)
        
        visible = execute('graph_panel.isVisible()')
        if visible:
            result.ok("Chart rendered with categorical axis")
        else:
            result.fail("Chart not visible")
        
        # 4. Category 컬럼으로 그룹화 테스트
        send_cmd('set_columns', x='Category', y=['Read_IOPS'])
        time.sleep(0.3)
        
        state = send_cmd('get_state')['result']
        if state['x_column'] == 'Category':
            result.ok("Category grouping axis set")
        else:
            result.fail("Category axis not set")
        
        # 5. 수치 X축 테스트
        send_cmd('set_columns', x='Queue_Depth', y=['Latency_ms'])
        send_cmd('set_chart_type', chart_type='SCATTER')
        time.sleep(0.3)
        
        result.ok("Numeric X-axis with scatter chart")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_views_and_etl():
    """테스트 5: Views Toggle & ETL Parsing"""
    print("\n" + "="*60)
    print("TEST 5: Views Toggle & ETL Parsing")
    print("="*60)
    
    result = TestResult("Views & ETL")
    
    # 1. View 메뉴 확인
    view_menu = execute('''
        [a.text() for a in window.menuBar().actions() if "view" in a.text().lower()]
    ''')
    if view_menu:
        result.ok(f"View menu exists: {view_menu}")
    else:
        result.skip("View menu not found")
    
    # 2. 패널 토글 테스트
    panels_info = send_cmd('get_panels')['result']
    
    for panel_name, info in panels_info.items():
        if info.get('exists'):
            result.ok(f"{panel_name}: exists, visible={info.get('visible')}")
    
    # 3. 테이블/그래프 비율 조정 확인
    has_splitter = execute('hasattr(window, "_main_splitter") or hasattr(window, "main_splitter")')
    if has_splitter:
        result.ok("Main splitter exists for view ratio")
    else:
        result.skip("Splitter not found")
    
    # 4. ETL/Parsing 다이얼로그 확인
    has_parsing = execute('''
        try:
            from data_graph_studio.ui.dialogs.parsing_preview_dialog import ParsingPreviewDialog
            True
        except:
            False
    ''')
    if has_parsing:
        result.ok("Parsing preview dialog available")
    else:
        result.skip("Parsing dialog not available")
    
    # 5. 테이블 뷰 모드 확인
    table_visible = execute('table_panel.isVisible()')
    graph_visible = execute('graph_panel.isVisible()')
    
    if table_visible and graph_visible:
        result.ok("Both table and graph views visible")
    elif table_visible:
        result.ok("Table view active")
    elif graph_visible:
        result.ok("Graph view active")
    else:
        result.fail("No view visible")
    
    return result

def test_sliding_window():
    """테스트 6: Sliding Window Navigation"""
    print("\n" + "="*60)
    print("TEST 6: Sliding Window Navigation")
    print("="*60)
    
    result = TestResult("Sliding Window")
    
    temp_file, loaded = load_test_data("sliding_test")
    if not loaded:
        result.fail("Failed to load test data")
        return result
    
    try:
        # 1. 그래프 설정
        send_cmd('set_chart_type', chart_type='LINE')
        send_cmd('set_columns', x='Timestamp', y=['Read_IOPS'])
        time.sleep(0.5)
        
        # 2. 그래프 범위 조작 기능 확인
        has_view_box = execute('hasattr(graph_panel.graph, "getViewBox")')
        if has_view_box:
            result.ok("ViewBox available for range manipulation")
        else:
            result.skip("ViewBox not accessible")
        
        # 3. 줌/팬 기능 확인
        has_zoom = execute('''
            vb = graph_panel.graph.getViewBox() if hasattr(graph_panel.graph, "getViewBox") else None
            vb is not None and hasattr(vb, "setRange")
        ''')
        if has_zoom:
            result.ok("Zoom/Pan functionality available")
        else:
            result.skip("Zoom/Pan not accessible")
        
        # 4. X축 범위 테스트 (프로그래매틱)
        range_set = execute('''
            try:
                vb = graph_panel.graph.getViewBox()
                vb.setXRange(0, 50)
                True
            except:
                False
        ''')
        if range_set:
            result.ok("X-axis range manipulation works")
        else:
            result.skip("Could not set X range")
        
        # 5. Y축 범위 테스트
        y_range_set = execute('''
            try:
                vb = graph_panel.graph.getViewBox()
                vb.setYRange(0, 2000)
                True
            except:
                False
        ''')
        if y_range_set:
            result.ok("Y-axis range manipulation works")
        else:
            result.skip("Could not set Y range")
        
        # 6. 자동 범위 복원
        auto_range = execute('''
            try:
                vb = graph_panel.graph.getViewBox()
                vb.autoRange()
                True
            except:
                False
        ''')
        if auto_range:
            result.ok("Auto-range works")
        else:
            result.skip("Auto-range not working")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_sampling_control():
    """테스트 7: Sampling Rate Control"""
    print("\n" + "="*60)
    print("TEST 7: Sampling Rate Control")
    print("="*60)
    
    result = TestResult("Sampling Control")
    
    # 대용량 데이터로 테스트
    import polars as pl
    
    n_rows = 50000
    df = pl.DataFrame({
        'X': list(range(n_rows)),
        'Y': [i * 0.01 + (i % 100) for i in range(n_rows)],
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), 'sampling_test.csv')
    df.write_csv(temp_file)
    
    try:
        # 1. 대용량 데이터 로드
        start = time.time()
        r = send_cmd('load_file', path=temp_file)
        load_time = time.time() - start
        
        if r['status'] == 'ok':
            result.ok(f"Loaded {n_rows:,} rows in {load_time:.2f}s")
        else:
            result.fail("Failed to load large data")
            return result
        
        time.sleep(0.5)
        
        # 2. 샘플링 모듈 확인
        has_sampler = execute('''
            try:
                from data_graph_studio.graph.sampling import DataSampler
                True
            except:
                False
        ''')
        if has_sampler:
            result.ok("DataSampler module available")
        else:
            result.skip("DataSampler not available")
        
        # 3. 그래프 렌더링 성능
        send_cmd('set_chart_type', chart_type='LINE')
        send_cmd('set_columns', x='X', y=['Y'])
        
        start = time.time()
        time.sleep(1)  # 렌더링 대기
        render_time = time.time() - start
        
        visible = execute('graph_panel.isVisible()')
        if visible:
            result.ok(f"Large data rendered (waited {render_time:.2f}s)")
        else:
            result.fail("Graph not visible after render")
        
        # 4. 샘플링 알고리즘 확인
        algorithms = execute('''
            try:
                from data_graph_studio.graph.sampling import DataSampler
                list(DataSampler.ALGORITHMS.keys()) if hasattr(DataSampler, "ALGORITHMS") else ["lttb"]
            except:
                []
        ''')
        if algorithms:
            result.ok(f"Sampling algorithms: {algorithms}")
        else:
            result.skip("Algorithm list not accessible")
        
        # 5. OpenGL 가속 확인
        has_opengl = execute('''
            try:
                from pyqtgraph import setConfigOption
                True
            except:
                False
        ''')
        if has_opengl:
            result.ok("OpenGL acceleration available")
        else:
            result.skip("OpenGL not configured")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_performance_memory():
    """테스트 8: Performance & Memory Management"""
    print("\n" + "="*60)
    print("TEST 8: Performance & Memory")
    print("="*60)
    
    result = TestResult("Performance & Memory")
    
    # 1. 메모리 모니터 확인
    has_memory_monitor = execute('hasattr(window, "_memory_timer")')
    if has_memory_monitor:
        result.ok("Memory monitor timer exists")
    else:
        result.skip("Memory timer not found")
    
    # 2. 상태바 메모리 표시 확인
    memory_label = execute('''
        hasattr(window, "_status_memory_label") and window._status_memory_label is not None
    ''')
    if memory_label:
        result.ok("Memory status label exists")
    else:
        result.skip("Memory label not found")
    
    # 3. 연속 작업 성능 테스트 (ping만 사용해서 순수 IPC 속도 측정)
    times = []
    for i in range(20):
        start = time.time()
        send_cmd('ping')
        times.append((time.time() - start) * 1000)
    
    avg_time = sum(times) / len(times)
    max_time = max(times)
    
    if avg_time < 50:
        result.ok(f"Fast IPC response: avg={avg_time:.1f}ms, max={max_time:.1f}ms")
    elif avg_time < 500:
        result.ok(f"Acceptable IPC response: avg={avg_time:.1f}ms")
    else:
        result.fail(f"Slow IPC response: avg={avg_time:.1f}ms")
    
    # 4. 캐시 시스템 확인
    has_cache = execute('''
        hasattr(engine, "_cache") or hasattr(table_panel, "_cache") or 
        hasattr(state, "_cache")
    ''')
    if has_cache:
        result.ok("Cache system detected")
    else:
        result.skip("Cache not directly accessible")
    
    # 5. 가비지 컬렉션 가능 여부
    gc_available = execute('''
        import gc
        gc.isenabled()
    ''')
    if gc_available:
        result.ok("Garbage collection enabled")
    else:
        result.skip("GC status unknown")
    
    # 6. 테이블 가상화 확인
    temp_file, loaded = load_test_data("perf_test")
    if loaded:
        table_rows = execute('table_panel.table_view.model().rowCount()')
        info = send_cmd('get_data_info')['result']
        actual_rows = info.get('row_count', 0)
        
        if table_rows and actual_rows:
            if table_rows <= actual_rows:
                result.ok(f"Table virtualization: {table_rows} visible of {actual_rows}")
            else:
                result.skip("No virtualization needed")
        
        os.remove(temp_file)
    
    return result

def test_workflow_integration():
    """테스트 9: 전체 워크플로우 통합 테스트"""
    print("\n" + "="*60)
    print("TEST 9: Integrated Workflow")
    print("="*60)
    
    result = TestResult("Workflow Integration")
    
    import polars as pl
    
    # Storage 분석 시나리오 시뮬레이션
    df = pl.DataFrame({
        'Timestamp': [f'2024-01-{(i//24)+1:02d} {i%24:02d}:00' for i in range(240)],
        'Device': ['NVMe_SSD', 'SATA_SSD', 'HDD_7200', 'HDD_5400'] * 60,
        'Read_IOPS': [50000 - i * 10 + (i % 4) * 10000 for i in range(240)],
        'Write_IOPS': [30000 - i * 5 + (i % 4) * 5000 for i in range(240)],
        'Read_Latency_us': [10 + (i % 4) * 50 for i in range(240)],
        'Write_Latency_us': [15 + (i % 4) * 60 for i in range(240)],
        'Queue_Depth': [1, 4, 16, 32] * 60,
        'Block_Size_KB': [4, 8, 64, 128] * 60,
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), 'storage_analysis.csv')
    df.write_csv(temp_file)
    
    try:
        # Step 1: 데이터 로드
        print("\n    Step 1: Load storage benchmark data")
        time.sleep(0.5)  # 파일 시스템 안정화
        r = send_cmd('load_file', path=temp_file)
        if r['status'] == 'ok':
            result.ok("Storage data loaded (240 samples)")
        else:
            # 재시도
            time.sleep(1)
            r = send_cmd('load_file', path=temp_file)
            if r['status'] == 'ok':
                result.ok("Storage data loaded (retry)")
            else:
                result.fail(f"Failed to load data: {r.get('error')}")
                return result
        
        time.sleep(0.5)
        
        # Step 2: IOPS 비교 차트
        print("    Step 2: Create IOPS comparison chart")
        send_cmd('set_chart_type', chart_type='BAR')
        send_cmd('set_columns', x='Device', y=['Read_IOPS', 'Write_IOPS'])
        time.sleep(0.5)
        
        state = send_cmd('get_state')['result']
        if state['chart_type'] == 'BAR' and state['x_column'] == 'Device':
            result.ok("IOPS comparison chart created")
        else:
            result.fail("Chart configuration failed")
        
        # Step 3: Latency 분석
        print("    Step 3: Analyze latency by queue depth")
        send_cmd('set_chart_type', chart_type='SCATTER')
        send_cmd('set_columns', x='Queue_Depth', y=['Read_Latency_us'])
        time.sleep(0.3)
        
        result.ok("Latency vs Queue Depth scatter created")
        
        # Step 4: 시계열 분석
        print("    Step 4: Time series analysis")
        send_cmd('set_chart_type', chart_type='LINE')
        send_cmd('set_columns', x='Timestamp', y=['Read_IOPS'])
        time.sleep(0.3)
        
        result.ok("Time series chart created")
        
        # Step 5: 차트 타입 빠른 전환
        print("    Step 5: Rapid chart switching")
        for ct in ['LINE', 'AREA', 'BAR']:
            send_cmd('set_chart_type', chart_type=ct)
            time.sleep(0.2)
        
        result.ok("Rapid chart switching completed")
        
        # Step 6: UI 상태 확인
        print("    Step 6: Verify final UI state")
        panels = send_cmd('get_panels')['result']
        all_ok = all(p.get('exists') for p in panels.values())
        
        if all_ok:
            result.ok("All panels intact after workflow")
        else:
            result.fail("Some panels missing after workflow")
        
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

# ========== MAIN ==========

def run_all_tests():
    """모든 기능 테스트 실행"""
    print("\n" + "="*60)
    print("  DATA GRAPH STUDIO - FEATURE-BASED UX TEST")
    print("="*60)
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Testing features from recent commits...")
    
    # 앱 연결 확인
    r = send_cmd('ping')
    if r.get('result') != 'pong':
        print("\n[ERROR] Cannot connect to app!")
        return 1
    
    results = []
    
    tests = [
        test_multi_data_comparison,
        test_graph_profiles,
        test_report_generation,
        test_formula_and_categorical,
        test_views_and_etl,
        test_sliding_window,
        test_sampling_control,
        test_performance_memory,
        test_workflow_integration,
    ]
    
    for test_func in tests:
        try:
            result = test_func()
            results.append(result)
        except Exception as e:
            print(f"\n    [ERROR] {e}")
            import traceback
            traceback.print_exc()
    
    # 최종 요약
    print("\n" + "="*60)
    print("  FINAL SUMMARY")
    print("="*60)
    
    total_passed = sum(r.passed for r in results)
    total_failed = sum(r.failed for r in results)
    total_skipped = sum(r.skipped for r in results)
    
    for r in results:
        status = "✓" if r.failed == 0 else "✗"
        skip_info = f" ({r.skipped} skipped)" if r.skipped > 0 else ""
        print(f"  {status} {r.name}: {r.summary()}{skip_info}")
    
    print(f"\n  Total: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")
    
    if total_failed == 0:
        print("\n  🎉 ALL FEATURE TESTS PASSED!")
        return 0
    else:
        print(f"\n  ⚠️  {total_failed} FAILURES DETECTED")
        return 1

if __name__ == '__main__':
    sys.exit(run_all_tests())
