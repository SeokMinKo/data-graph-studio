"""
Integration UX Test Suite
CLI, Python API, REST API, Clipboard, Drag-Drop 통합 테스트
"""
import json
import socket
import time
import tempfile
import os
import sys
import subprocess
from pathlib import Path

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

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = 0
        self.failed = 0
        self.skipped = 0
    
    def ok(self, msg: str):
        self.passed += 1
        print(f"    [OK] {msg}")
    
    def fail(self, msg: str):
        self.failed += 1
        print(f"    [FAIL] {msg}")
    
    def skip(self, msg: str):
        self.skipped += 1
        print(f"    [SKIP] {msg}")
    
    def summary(self) -> str:
        total = self.passed + self.failed
        if self.failed == 0:
            return f"PASS ({self.passed}/{total})"
        return f"FAIL ({self.passed}/{total})"

def create_test_csv(name: str = "test_data") -> str:
    """테스트 CSV 파일 생성"""
    import polars as pl
    
    df = pl.DataFrame({
        'Time': list(range(1, 11)),
        'Value1': [10, 25, 15, 30, 20, 35, 25, 40, 30, 45],
        'Value2': [5, 15, 10, 20, 15, 25, 20, 30, 25, 35],
        'Category': ['A', 'B', 'A', 'B', 'A', 'B', 'A', 'B', 'A', 'B'],
    })
    
    temp_file = os.path.join(tempfile.gettempdir(), f'{name}.csv')
    df.write_csv(temp_file)
    return temp_file

# ==================== CLI Tests ====================

def test_cli_info():
    """CLI info 명령 테스트"""
    print("\n" + "="*60)
    print("TEST: CLI - info command")
    print("="*60)
    
    result = TestResult("CLI info")
    temp_file = create_test_csv("cli_info_test")
    
    try:
        # info 명령 실행
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "info", temp_file],
            capture_output=True, text=True, timeout=30
        )
        
        if proc.returncode == 0:
            result.ok("info command executed")
            
            # 출력 확인
            output = proc.stdout
            if "Rows: 10" in output:
                result.ok("Row count correct")
            else:
                result.fail(f"Row count wrong: {output}")
            
            if "Columns: 4" in output:
                result.ok("Column count correct")
            else:
                result.fail(f"Column count wrong")
            
            if "Time" in output and "Value1" in output:
                result.ok("Column names shown")
            else:
                result.fail("Column names missing")
        else:
            result.fail(f"Command failed: {proc.stderr}")
        
        # JSON 출력 테스트
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "info", temp_file, "--json"],
            capture_output=True, text=True, timeout=30
        )
        
        if proc.returncode == 0:
            try:
                info = json.loads(proc.stdout)
                if info.get('rows') == 10:
                    result.ok("JSON output valid")
                else:
                    result.fail("JSON output incorrect")
            except json.JSONDecodeError:
                result.fail("Invalid JSON output")
        
    except subprocess.TimeoutExpired:
        result.fail("Command timeout")
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

def test_cli_plot():
    """CLI plot 명령 테스트"""
    print("\n" + "="*60)
    print("TEST: CLI - plot command")
    print("="*60)
    
    result = TestResult("CLI plot")
    temp_file = create_test_csv("cli_plot_test")
    output_file = os.path.join(tempfile.gettempdir(), "cli_test_chart.png")
    
    try:
        # 기본 플롯
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "plot", temp_file,
             "-x", "Time", "-y", "Value1", "-o", output_file],
            capture_output=True, text=True, timeout=60
        )
        
        if proc.returncode == 0:
            result.ok("plot command executed")
            
            if os.path.exists(output_file):
                size = os.path.getsize(output_file)
                if size > 1000:  # 최소 1KB
                    result.ok(f"Output file created ({size} bytes)")
                else:
                    result.fail(f"Output file too small ({size} bytes)")
                os.remove(output_file)
            else:
                result.fail("Output file not created")
        else:
            result.fail(f"Command failed: {proc.stderr}")
        
        # 여러 Y 컬럼
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "plot", temp_file,
             "-x", "Time", "-y", "Value1,Value2", "--chart", "line", "-o", output_file],
            capture_output=True, text=True, timeout=60
        )
        
        if proc.returncode == 0 and os.path.exists(output_file):
            result.ok("Multiple Y columns work")
            os.remove(output_file)
        else:
            result.fail("Multiple Y columns failed")
        
        # Bar 차트
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "plot", temp_file,
             "-x", "Category", "-y", "Value1", "--chart", "bar", "-o", output_file],
            capture_output=True, text=True, timeout=60
        )
        
        if proc.returncode == 0 and os.path.exists(output_file):
            result.ok("Bar chart works")
            os.remove(output_file)
        else:
            result.fail("Bar chart failed")
        
        # 제목 추가
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "plot", temp_file,
             "-x", "Time", "-y", "Value1", "--title", "Test Chart", "-o", output_file],
            capture_output=True, text=True, timeout=60
        )
        
        if proc.returncode == 0:
            result.ok("Title option works")
            if os.path.exists(output_file):
                os.remove(output_file)
        
    except subprocess.TimeoutExpired:
        result.fail("Command timeout")
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(output_file):
            os.remove(output_file)
    
    return result

def test_cli_convert():
    """CLI convert 명령 테스트"""
    print("\n" + "="*60)
    print("TEST: CLI - convert command")
    print("="*60)
    
    result = TestResult("CLI convert")
    temp_csv = create_test_csv("cli_convert_test")
    temp_parquet = os.path.join(tempfile.gettempdir(), "converted.parquet")
    temp_json = os.path.join(tempfile.gettempdir(), "converted.json")
    
    try:
        # CSV -> Parquet
        proc = subprocess.run(
            [sys.executable, "-m", "data_graph_studio.cli", "convert", temp_csv, "-o", temp_parquet],
            capture_output=True, text=True, timeout=30
        )
        
        if proc.returncode == 0 and os.path.exists(temp_parquet):
            result.ok("CSV -> Parquet conversion")
        else:
            result.fail(f"CSV -> Parquet failed: {proc.stderr}")
        
        # Parquet -> JSON
        if os.path.exists(temp_parquet):
            proc = subprocess.run(
                [sys.executable, "-m", "data_graph_studio.cli", "convert", temp_parquet, "-o", temp_json],
                capture_output=True, text=True, timeout=30
            )
            
            if proc.returncode == 0 and os.path.exists(temp_json):
                result.ok("Parquet -> JSON conversion")
            else:
                result.fail("Parquet -> JSON failed")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        for f in [temp_csv, temp_parquet, temp_json]:
            if os.path.exists(f):
                os.remove(f)
    
    return result

# ==================== Python API Tests ====================

def test_python_api_basic():
    """Python API 기본 테스트"""
    print("\n" + "="*60)
    print("TEST: Python API - Basic operations")
    print("="*60)
    
    result = TestResult("Python API Basic")
    temp_file = create_test_csv("api_basic_test")
    output_file = os.path.join(tempfile.gettempdir(), "api_test_chart.png")
    
    try:
        from data_graph_studio import DataGraphStudio
        
        # 로드 테스트
        dgs = DataGraphStudio()
        dgs.load(temp_file)
        
        if dgs.data is not None:
            result.ok("Data loaded")
        else:
            result.fail("Data not loaded")
        
        # shape 확인
        if dgs.shape == (10, 4):
            result.ok(f"Shape correct: {dgs.shape}")
        else:
            result.fail(f"Shape wrong: {dgs.shape}")
        
        # columns 확인
        if 'Time' in dgs.columns and 'Value1' in dgs.columns:
            result.ok("Columns accessible")
        else:
            result.fail("Columns not accessible")
        
        # info 확인
        info = dgs.info()
        if info.get('rows') == 10:
            result.ok("Info method works")
        else:
            result.fail("Info method failed")
        
        # 플롯 및 저장
        dgs.plot(x='Time', y=['Value1', 'Value2'], chart='line')
        dgs.set_title("API Test Chart")
        dgs.save(output_file)
        
        if os.path.exists(output_file):
            size = os.path.getsize(output_file)
            if size > 1000:
                result.ok(f"Chart saved ({size} bytes)")
            else:
                result.fail("Chart too small")
        else:
            result.fail("Chart not saved")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(output_file):
            os.remove(output_file)
    
    return result

def test_python_api_chaining():
    """Python API 체이닝 테스트"""
    print("\n" + "="*60)
    print("TEST: Python API - Method chaining")
    print("="*60)
    
    result = TestResult("Python API Chaining")
    temp_file = create_test_csv("api_chain_test")
    output_file = os.path.join(tempfile.gettempdir(), "api_chain_chart.png")
    
    try:
        from data_graph_studio import DataGraphStudio
        
        # 체이닝 테스트
        dgs = (DataGraphStudio()
               .load(temp_file)
               .plot(x='Time', y=['Value1'])
               .set_title("Chained Chart")
               .set_size(800, 600))
        
        if dgs.data is not None:
            result.ok("Chaining works")
        else:
            result.fail("Chaining failed")
        
        dgs.save(output_file)
        
        if os.path.exists(output_file):
            result.ok("Chained save works")
        else:
            result.fail("Chained save failed")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(output_file):
            os.remove(output_file)
    
    return result

def test_python_api_dict_load():
    """Python API 딕셔너리 로드 테스트"""
    print("\n" + "="*60)
    print("TEST: Python API - Dict/DataFrame load")
    print("="*60)
    
    result = TestResult("Python API Dict Load")
    output_file = os.path.join(tempfile.gettempdir(), "api_dict_chart.png")
    
    try:
        from data_graph_studio import DataGraphStudio
        import polars as pl
        
        # 딕셔너리 로드
        data = {
            'x': [1, 2, 3, 4, 5],
            'y': [10, 20, 15, 25, 30],
        }
        
        dgs = DataGraphStudio()
        dgs.load_dict(data)
        
        if dgs.shape == (5, 2):
            result.ok("Dict load works")
        else:
            result.fail(f"Dict load failed: {dgs.shape}")
        
        # Polars DataFrame 로드
        df = pl.DataFrame({
            'a': [1, 2, 3],
            'b': [4, 5, 6],
        })
        
        dgs2 = DataGraphStudio()
        dgs2.load_polars(df)
        
        if dgs2.shape == (3, 2):
            result.ok("Polars load works")
        else:
            result.fail("Polars load failed")
        
        # from_config 테스트
        config = {
            'data': {'x': [1, 2, 3], 'y': [10, 20, 30]},
            'x': 'x',
            'y': ['y'],
            'chart': 'line',
            'title': 'Config Test',
        }
        
        dgs3 = DataGraphStudio.from_config(config)
        if dgs3.data is not None:
            result.ok("from_config works")
        else:
            result.fail("from_config failed")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(output_file):
            os.remove(output_file)
    
    return result

def test_python_api_quick_plot():
    """Python API quick_plot 테스트"""
    print("\n" + "="*60)
    print("TEST: Python API - Quick plot function")
    print("="*60)
    
    result = TestResult("Python API Quick Plot")
    temp_file = create_test_csv("api_quick_test")
    output_file = os.path.join(tempfile.gettempdir(), "api_quick_chart.png")
    
    try:
        from data_graph_studio import plot
        
        # quick plot
        dgs = plot(temp_file, x='Time', y='Value1', output=output_file)
        
        if os.path.exists(output_file):
            result.ok("Quick plot works")
        else:
            result.fail("Quick plot failed")
        
        # dict로 quick plot
        data = {'x': [1, 2, 3], 'y': [10, 20, 15]}
        output2 = os.path.join(tempfile.gettempdir(), "api_quick_dict.png")
        
        plot(data, x='x', y='y', output=output2)
        
        if os.path.exists(output2):
            result.ok("Quick plot with dict works")
            os.remove(output2)
        else:
            result.fail("Quick plot with dict failed")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
        if os.path.exists(output_file):
            os.remove(output_file)
    
    return result

# ==================== Clipboard Tests ====================

def test_clipboard_manager():
    """ClipboardManager 테스트"""
    print("\n" + "="*60)
    print("TEST: Clipboard Manager")
    print("="*60)
    
    result = TestResult("Clipboard Manager")
    
    try:
        from data_graph_studio.core.clipboard_manager import ClipboardManager, DragDropHandler
        
        # DragDropHandler 테스트
        if '.csv' in DragDropHandler.SUPPORTED_EXTENSIONS:
            result.ok("CSV in supported extensions")
        else:
            result.fail("CSV not supported")
        
        if '.xlsx' in DragDropHandler.SUPPORTED_EXTENSIONS:
            result.ok("Excel in supported extensions")
        else:
            result.fail("Excel not supported")
        
        # is_supported_file 테스트
        if DragDropHandler.is_supported_file("test.csv"):
            result.ok("is_supported_file works for CSV")
        else:
            result.fail("is_supported_file failed for CSV")
        
        if not DragDropHandler.is_supported_file("test.exe"):
            result.ok("is_supported_file rejects EXE")
        else:
            result.fail("is_supported_file accepts EXE")
        
        # get_file_type 테스트
        if DragDropHandler.get_file_type("test.csv") == "data":
            result.ok("get_file_type works for CSV")
        else:
            result.fail("get_file_type failed")
        
        if DragDropHandler.get_file_type("test.xlsx") == "excel":
            result.ok("get_file_type works for Excel")
        else:
            result.fail("get_file_type for Excel failed")
        
    except ImportError as e:
        result.skip(f"Import error: {e}")
    except Exception as e:
        result.fail(f"Error: {e}")
    
    return result

# ==================== IPC/App Integration Tests ====================

def test_app_clipboard_methods():
    """앱 클립보드 메서드 테스트"""
    print("\n" + "="*60)
    print("TEST: App Clipboard Methods")
    print("="*60)
    
    result = TestResult("App Clipboard Methods")
    
    # 앱 연결 확인
    r = send_cmd('ping')
    if r.get('result') != 'pong':
        result.skip("App not running")
        return result
    
    try:
        # acceptDrops 확인
        r = send_cmd('execute', code='window.acceptDrops()')
        if r.get('result') == True:
            result.ok("Drag-drop enabled")
        else:
            result.fail("Drag-drop not enabled")
        
        # paste 메서드 존재 확인 (메서드 호출하지 않고 존재만 확인)
        r = send_cmd('execute', code='callable(getattr(window, "_paste_from_clipboard", None))')
        if r.get('status') == 'ok':
            result.ok("Paste method exists")
        else:
            result.skip("Cannot check paste method")
        
        # copy graph 메서드 확인
        r = send_cmd('execute', code='callable(getattr(window, "_copy_graph_to_clipboard", None))')
        if r.get('status') == 'ok':
            result.ok("Copy graph method exists")
        else:
            result.skip("Cannot check copy method")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    
    return result

def test_app_integration_workflow():
    """앱 통합 워크플로우 테스트"""
    print("\n" + "="*60)
    print("TEST: App Integration Workflow")
    print("="*60)
    
    result = TestResult("App Integration Workflow")
    temp_file = create_test_csv("app_workflow_test")
    
    # 앱 연결 확인
    r = send_cmd('ping')
    if r.get('result') != 'pong':
        result.skip("App not running")
        if os.path.exists(temp_file):
            os.remove(temp_file)
        return result
    
    try:
        # 1. 파일 로드
        r = send_cmd('load_file', path=temp_file)
        if r.get('status') == 'ok':
            result.ok("File loaded via IPC")
        else:
            result.fail(f"File load failed: {r.get('error')}")
            return result
        
        time.sleep(0.5)
        
        # 2. 상태 확인
        state = send_cmd('get_state')['result']
        if state.get('data_loaded'):
            result.ok(f"Data loaded: {state.get('row_count')} rows")
        else:
            result.fail("Data not in state")
        
        # 3. 차트 타입 변경
        for chart in ['LINE', 'BAR', 'SCATTER']:
            r = send_cmd('set_chart_type', chart_type=chart)
            time.sleep(0.2)
            if r.get('status') == 'ok':
                pass
            else:
                result.fail(f"Chart type {chart} failed")
                break
        else:
            result.ok("All chart types work via IPC")
        
        # 4. 컬럼 설정
        r = send_cmd('set_columns', x='Time', y=['Value1', 'Value2'])
        if r.get('status') == 'ok':
            result.ok("Columns set via IPC")
        else:
            result.fail("Column setting failed")
        
        # 5. 패널 확인
        panels = send_cmd('get_panels')['result']
        if panels.get('table_panel', {}).get('visible'):
            result.ok("Table panel visible")
        if panels.get('graph_panel', {}).get('visible'):
            result.ok("Graph panel visible")
        
    except Exception as e:
        result.fail(f"Error: {e}")
    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)
    
    return result

# ==================== Main ====================

def run_all_tests():
    """모든 통합 테스트 실행"""
    print("\n" + "="*60)
    print("  DATA GRAPH STUDIO - INTEGRATION UX TEST")
    print("="*60)
    print(f"  Time: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("  Testing: CLI, Python API, Clipboard, App Integration")
    
    results = []
    
    tests = [
        # CLI Tests
        test_cli_info,
        test_cli_plot,
        test_cli_convert,
        # Python API Tests
        test_python_api_basic,
        test_python_api_chaining,
        test_python_api_dict_load,
        test_python_api_quick_plot,
        # Clipboard Tests
        test_clipboard_manager,
        # App Integration Tests
        test_app_clipboard_methods,
        test_app_integration_workflow,
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
        status = "PASS" if r.failed == 0 else "FAIL"
        skip_info = f" ({r.skipped} skipped)" if r.skipped > 0 else ""
        print(f"  [{status}] {r.name}: {r.summary()}{skip_info}")
    
    print(f"\n  Total: {total_passed} passed, {total_failed} failed, {total_skipped} skipped")
    
    if total_failed == 0:
        print("\n  [SUCCESS] All integration tests passed!")
        return 0
    else:
        print(f"\n  [WARNING] {total_failed} failures detected")
        return 1

if __name__ == '__main__':
    sys.exit(run_all_tests())
