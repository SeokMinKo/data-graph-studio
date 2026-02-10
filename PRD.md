# PRD: Android Perfetto Logging + Ftrace Parser 완성 (v2)

## 1. 목표
Android 기기에서 ftrace 블록 레이어 이벤트를 캡처하고, 텍스트 ftrace 로그를 regex로 파싱하여 DGS 데이터셋으로 로드하는 end-to-end 파이프라인 완성.

## 2. 배경
- AndroidLoggerWizard (5페이지) 존재하지만, 트레이스 실행 중 진행 상태 표시/중지 기능 없음
- `_start_blk_trace()`/`_stop_blk_trace()` — subprocess.Popen 직접 사용 → UI 블로킹
- `FtraceParser.parse_raw()` = NotImplementedError (스켈레톤)
- 현재 wizard는 perfetto binary를 생성 → traceconv 없이 파싱 불가

**타겟 사용자**: 스토리지/커널 엔지니어 — Android 기기의 블록 레이어 성능 분석 (주 2-5회 사용 예상)

## 3. 캡처 방식 전환

### 기존 perfetto 경로와의 공존
- **캡처 방식 선택 UI 추가**: TraceConfigPage에 "Capture Mode" 콤보박스
  - `Raw Ftrace (requires root)` — 텍스트 직접 출력, parse_raw()로 파싱 가능
  - `Perfetto (no root needed)` — 기존 바이너리 캡처 유지 (파싱은 향후 지원)
- 기존 perfetto 워크플로우 **제거하지 않음** (breaking change 방지)
- Page 3: PerfettoCheckPage 유지 + RootCheckPage 추가 → 캡처 모드에 따라 표시

### logger_config.json 마이그레이션
- `version` 필드 도입 (기본값 1)
- 기존 config (version 없음) → `capture_mode: "perfetto"` 자동 설정
- 새 config: `capture_mode: "raw_ftrace"` 추가
- 새 필드 기본값: `capture_mode: "perfetto"`, `sysfs_path: "/sys/kernel/tracing"`

## 4. 요구사항

### 4.1 기능 요구사항 (FR)
- [x] FR-1: `parse_raw()` — regex로 ftrace 텍스트 파싱 → polars DataFrame
  - 컬럼: timestamp(f64), cpu(i32), task(str), pid(i32), flags(str), event(str), details(str)
  - `#` 주석 라인 스킵 (settings.skip_comments)
  - 필터링은 **polars 벡터 연산**으로 수행 (Python 루프 아님)
- [x] FR-2: Wizard 캡처 모드 선택 (perfetto / raw_ftrace)
- [x] FR-3: RootCheckPage 추가 (raw_ftrace 모드 시만 표시)
- [x] FR-4: AdbTraceController — adb 명령 순차 실행 + sysfs 상태 관리 (SRP)
- [x] FR-5: TraceProgressDialog — AdbTraceController의 signal만 구독하여 UI 표시
  - 경과 시간 라벨, 로그 영역 (auto-scroll), Stop 버튼
  - Stop 더블클릭 방어 (버튼 disable)
  - Esc → Stop 확인, 최소 크기 480×320
- [x] FR-6: 트레이스 중지 후 자동 파싱 제안 (raw_ftrace 모드만)
- [x] FR-7: parse_raw()를 **QThread 워커**에서 실행 (메인스레드 블로킹 방지)
- [x] FR-8: sysfs 상태 복원 보장 — try/finally로 tracing_on=0 + events disable

### 4.2 비기능 요구사항 (NFR)
- [x] NFR-1: parse_raw() — 100만 라인 파싱 < 5초 (M1 16GB 기준)
- [x] NFR-2: UI — 트레이스 중 + 파싱 중 메인 윈도우 블로킹 없음
- [x] NFR-3: 에러 메시지 — 모든 실패 케이스에 복구 안내 포함
- [x] NFR-4: 메모리 — 입력 파일의 3배 이내 피크 메모리
- [x] NFR-5: 모든 신규 public 함수/클래스에 Google-style docstring + 타입 힌트 100%
- [x] NFR-6: adb 명령 조립 시 shlex.quote() 적용 (shell injection 방어)

## 5. 범위
### 포함
- parse_raw() regex 구현 (최적화: finditer + 컬럼별 리스트)
- AdbTraceController (프로세스 관리 분리)
- TraceProgressDialog (UI only)
- RootCheckPage + 캡처 모드 선택
- main_window.py 연결 교체
- QThread 워커로 파싱 실행

### 제외
- blocklayer converter
- perfetto binary parsing (향후)
- trace-cmd 지원
- 커스텀 settings UI 위젯

## 6. 기술 설계

### 아키텍처
```
AndroidLoggerWizard (6 pages)
  ├── AdbCheckPage (기존 유지)
  ├── DeviceConnectionPage (기존 유지)
  ├── PerfettoCheckPage (기존 유지, perfetto 모드 시)
  ├── RootCheckPage (신규, raw_ftrace 모드 시)
  ├── TraceConfigPage (수정: capture_mode 콤보박스 추가)
  └── SummaryPage (수정: Start → TraceProgressDialog 열기)

AdbTraceController(QObject) — 신규
  ├── signals: log_message(str), progress(str), finished(str), error(str)
  ├── start_trace(serial, config) → QProcess 순차 실행
  ├── stop_trace() → tracing_on=0 + pull text + disable events
  ├── _detect_sysfs_path() → /sys/kernel/tracing 또는 /sys/kernel/debug/tracing
  ├── _run_adb_cmd(args) → QProcess + shlex.quote
  └── cleanup() → try/finally sysfs 상태 복원

TraceProgressDialog(QDialog) — 신규
  ├── controller: AdbTraceController 참조
  ├── _elapsed_timer: QTimer (1초 간격)
  ├── _log_area: QTextEdit (readonly, auto-scroll)
  ├── _stop_btn: QPushButton (클릭 시 disable → controller.stop_trace)
  ├── closeEvent → controller.stop_trace() + waitForFinished(3000) + kill
  └── placeholder: "트레이스를 시작합니다..."

FtraceParser.parse_raw() — 구현
  ├── Path.read_text("utf-8") 또는 50MB+ → chunk 스트리밍
  ├── re.finditer(PATTERN, text) — splitlines 제거
  ├── 컬럼별 리스트 수집 (dict 생성 제거)
  ├── pl.DataFrame({"col": list}) 생성
  └── df.filter() 로 events/cpus 필터링 (벡터 연산)

ParseWorker(QThread) — 신규
  ├── run() → parse_raw() 실행
  ├── finished signal → 메인스레드에서 DataEngine.load_dataset_from_dataframe()
  └── error signal → 메인스레드에서 에러 다이얼로그
```

### 파일 변경 목록
| 파일 | 변경 유형 | 설명 |
|------|----------|------|
| `parsers/ftrace_parser.py` | 수정 | parse_raw() regex 구현 (finditer + 컬럼별 리스트) |
| `ui/dialogs/android_logger_wizard.py` | 수정 | RootCheckPage 추가, 캡처 모드 선택, config 마이그레이션 |
| `ui/dialogs/trace_progress_dialog.py` | 신규 | TraceProgressDialog + AdbTraceController |
| `ui/main_window.py` | 수정 | _start/_stop_blk_trace 교체, ParseWorker 연결 |
| `tests/unit/test_ftrace_parser.py` | 신규 | parse_raw() 단위 테스트 |
| `tests/unit/test_trace_progress.py` | 신규 | AdbTraceController + Dialog 테스트 |

### parse_raw() 상세 설계
```python
import re
from pathlib import Path
import polars as pl
import logging

logger = logging.getLogger(__name__)

# Ftrace 라인 포맷 참조:
# https://docs.kernel.org/trace/ftrace.html#the-file-system
# 형태: <task>-<pid> [<cpu>] <flags> <timestamp>: <event>: <details>
# tgid 변형: <task>-<pid> (<tgid>) [<cpu>] ...
FTRACE_LINE_RE = re.compile(
    r"^\s*(?P<task>.+?)-(?P<pid>\d+)"       # task-pid
    r"\s+(?:\([\s\d-]+\)\s+)?"              # optional tgid (ignored)
    r"\[(?P<cpu>\d+)\]"                      # [cpu]
    r"\s+(?P<flags>[a-zA-Z.]{4,5})"         # flags (d..1, dNh2, etc)
    r"\s+(?P<timestamp>\d+\.\d+):"          # timestamp:
    r"\s+(?P<event>[\w:]+):"                # event:
    r"\s+(?P<details>.*?)$",                # details
    re.MULTILINE
)

STREAMING_THRESHOLD = 50 * 1024 * 1024  # 50MB

def parse_raw(self, file_path: str, settings: Dict[str, Any]) -> pl.DataFrame:
    """Parse raw ftrace text into structured event DataFrame.

    Args:
        file_path: Path to ftrace log file.
        settings: Parser settings dict.

    Returns:
        polars DataFrame with columns:
        timestamp(f64), cpu(i32), task(str), pid(i32),
        flags(str), event(str), details(str)

    Raises:
        ValueError: If no valid events found.
        FileNotFoundError: If file doesn't exist.
        UnicodeDecodeError: If file isn't valid UTF-8.
    """
    path = Path(file_path)
    text = path.read_text("utf-8")
    skip_comments = settings.get("skip_comments", True)

    # 컬럼별 리스트 수집 (dict 오버헤드 제거)
    timestamps: list[float] = []
    cpus: list[int] = []
    tasks: list[str] = []
    pids: list[int] = []
    flags_list: list[str] = []
    events: list[str] = []
    details_list: list[str] = []
    skipped = 0

    for m in FTRACE_LINE_RE.finditer(text):
        # skip_comments: finditer with MULTILINE skips non-matching lines
        # but we should check if the line starts with #
        line_start = text.rfind('\n', 0, m.start()) + 1
        if skip_comments and text[line_start:line_start+1] == '#':
            continue

        timestamps.append(float(m.group("timestamp")))
        cpus.append(int(m.group("cpu")))
        tasks.append(m.group("task").strip())
        pids.append(int(m.group("pid")))
        flags_list.append(m.group("flags"))
        events.append(m.group("event"))
        details_list.append(m.group("details").strip())

    if not timestamps:
        logger.warning(f"No valid ftrace events found in {file_path}")

    df = pl.DataFrame({
        "timestamp": pl.Series("timestamp", timestamps, dtype=pl.Float64),
        "cpu": pl.Series("cpu", cpus, dtype=pl.Int32),
        "task": pl.Series("task", tasks, dtype=pl.Utf8),
        "pid": pl.Series("pid", pids, dtype=pl.Int32),
        "flags": pl.Series("flags", flags_list, dtype=pl.Utf8),
        "event": pl.Series("event", events, dtype=pl.Utf8),
        "details": pl.Series("details", details_list, dtype=pl.Utf8),
    })

    # Polars 벡터 필터링
    event_filter = settings.get("events", [])
    cpu_filter = settings.get("cpus", [])
    if event_filter:
        df = df.filter(pl.col("event").is_in(event_filter))
    if cpu_filter:
        df = df.filter(pl.col("cpu").is_in(cpu_filter))

    return df
```

### AdbTraceController 상세 설계
```python
class AdbTraceController(QObject):
    """adb를 통한 ftrace 캡처 제어.

    모든 adb 명령은 QProcess로 비동기 실행.
    sysfs 상태 복원은 try/finally로 보장.

    Signals:
        log_message(str): 로그 메시지
        progress(str): 현재 단계 ("enabling events", "tracing", "pulling")
        finished(str): 완료 시 파일 경로
        error(str): 에러 메시지
    """

    SYSFS_PATHS = ["/sys/kernel/tracing", "/sys/kernel/debug/tracing"]

    def _detect_sysfs_path(self, serial: str) -> str:
        """두 경로를 시도하여 사용 가능한 sysfs 경로 반환."""
        for path in self.SYSFS_PATHS:
            # adb shell su -c "cat {path}/tracing_on"
            ...

    def _run_adb_cmd(self, serial: str, shell_cmd: str) -> subprocess.CompletedProcess:
        """adb shell su -c 명령 실행. shlex.quote 적용."""
        import shlex
        # shlex.quote로 shell_cmd 래핑
        ...

    def start_trace(self, serial: str, config: dict) -> None:
        """트레이스 시작. 비동기."""
        # 1. detect sysfs path
        # 2. clear buffer
        # 3. set buffer size
        # 4. enable events (try/finally로 cleanup 보장)
        # 5. tracing_on = 1
        # 6. emit progress("tracing")

    def stop_trace(self, serial: str, save_path: str) -> None:
        """트레이스 중지 + pull + cleanup."""
        try:
            # 1. tracing_on = 0
            # 2. cat trace > save_path
            # 3. emit finished(save_path)
        finally:
            # 4. disable all events
            # 5. emit progress("cleanup done")

    def cleanup(self) -> None:
        """강제 정리 (앱 종료/크래시 시)."""
        # tracing_on = 0, events disable
```

### 시퀀스 다이어그램
```
SummaryPage
  │ click "Start Trace"
  ├─► TraceProgressDialog(serial, config)
  │     │ show() + controller.start_trace()
  │     │
  │     │ controller.log_message ──► _log_area.append()
  │     │ controller.progress ────► _status_label.setText()
  │     │ _elapsed_timer.timeout ─► _update_elapsed()
  │     │
  │     │ [user clicks Stop]
  │     │ _stop_btn.setEnabled(False)
  │     │ controller.stop_trace(save_path)
  │     │
  │     │ controller.finished(file_path) ──► accept()
  │     │ controller.error(msg) ───────────► QMessageBox + reject()
  │     │
  │     │ [closeEvent]
  │     │ controller.stop_trace() + controller.cleanup()
  │     ▼
  │ dialog.result() == Accepted
  │ file_path = dialog.trace_file_path
  │
  ├─► QMessageBox.question("Open with Ftrace Parser?")
  │     │ Yes
  │     ├─► ParseWorker(FtraceParser, file_path, settings)
  │     │     │ worker.finished(df) → DataEngine.load_dataset_from_dataframe(df)
  │     │     │ worker.error(msg) → QMessageBox.critical()
  │     │     ▼
  │     │   _on_data_loaded()
  │     │
  │     │ No → done
  ▼
```

## 7. 엣지 케이스 & 에러 처리
- EC-1: 빈 trace (이벤트 0건) → 빈 DataFrame 반환 + QMessageBox "No events captured"
- EC-2: root/su 불가 → RootCheckPage에서 차단 + "기기에 root 접근이 필요합니다. Magisk/SuperSU 설치 확인" 메시지
- EC-3: ADB 연결 중 기기 분리 → QProcess.errorOccurred → "기기 연결이 끊어졌습니다. USB 케이블 확인" 다이얼로그
- EC-4: 대용량 trace (50MB+) → STREAMING_THRESHOLD 초과 시 chunk 파싱 (향후, v1은 전체 로드)
- EC-5: 비표준 ftrace 라인 → skip + 파싱 완료 후 "N lines skipped (not matching ftrace format)" statusbar
- EC-6: Stop 버튼 더블클릭 → 첫 클릭 시 setEnabled(False), controller.stop_trace()는 idempotent
- EC-7: 트레이스 중 다이얼로그 닫기 (X/Esc) → closeEvent에서 "트레이스가 진행 중입니다. 중지하시겠습니까?" 확인
- EC-8: adb shell su 타임아웃 → QProcess 10초 타임아웃 + "기기 응답 없음. 연결 확인" 메시지
- EC-9: sysfs 경로 없음 (커널 비지원) → "이 기기에서는 ftrace를 사용할 수 없습니다" + perfetto 모드 안내
- EC-10: 이전 세션 tracing_on 잔류 → start_trace 시작 시 tracing_on 상태 확인, 켜져있으면 먼저 끄기
- EC-11: 캡처 성공 → pull 실패 → "트레이스 캡처는 완료되었으나 파일 다운로드 실패. 재시도?" + 임시 파일 정리
- EC-12: timestamp 오버플로 (부팅 수백일) → f64 범위 내 (최대 ~1e15초), 문제 없음

## 8. 알려진 리스크
| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| sysfs 경로 차이 | 중 | 중 | _detect_sysfs_path()로 두 경로 시도 |
| su 명령 차이 (su -c vs su 0) | 중 | 중 | RootCheckPage에서 `su -c id` 시도, 실패 시 `su 0 id` 시도 |
| 대용량 pull 타임아웃 | 저 | 중 | QProcess 타임아웃 60초, 실패 시 재시도 안내 |
| ftrace 비활성화 커널 | 저 | 고 | sysfs 탐색 실패 → perfetto 모드 권장 |
| 앱 크래시 시 tracing_on 잔류 | 저 | 중 | 다음 start 시 guard check, atexit 등록은 과도 |

## 9. 성능 목표
- parse_raw(): 100만 라인 < 5초 (Apple M1, 16GB 기준)
- 메모리: 입력 파일의 3배 이내 피크 (100MB 파일 → 피크 300MB)
- UI: 트레이스 중 + 파싱 중 메인 윈도우 반응성 유지 (0 블로킹)
- trace pull: 50MB 이내 < 30초

## 10. 테스트 시나리오
### Unit Tests
- [x] UT-1: parse_raw() — 정상 ftrace 텍스트 → 올바른 DataFrame (컬럼 타입/값 검증)
- [x] UT-2: parse_raw() — 주석 라인 (#) 스킵
- [x] UT-3: parse_raw() — events 필터 적용 (polars filter)
- [x] UT-4: parse_raw() — cpus 필터 적용 (polars filter)
- [x] UT-5: parse_raw() — events + cpus 동시 필터 조합
- [x] UT-6: parse_raw() — 빈 파일 → 빈 DataFrame (에러 없이)
- [x] UT-7: parse_raw() — 헤더만 있는 파일 (이벤트 0건)
- [x] UT-8: parse_raw() — 비표준 라인 스킵 (에러 없이, 경고 로그)
- [x] UT-9: parse_raw() — tgid 포맷 `(  123)` 지원
- [x] UT-10: parse_raw() — FileNotFoundError 발생
- [x] UT-11: AdbTraceController — _detect_sysfs_path (mock adb, 두 경로)
- [x] UT-12: AdbTraceController — start/stop 시퀀스 (mock QProcess)
- [x] UT-13: AdbTraceController — cleanup 보장 (에러 시에도)
- [x] UT-14: AdbTraceController — shlex.quote 적용 확인
- [x] UT-15: TraceProgressDialog — 생성/표시/Stop 버튼 disable
- [x] UT-16: RootCheckPage — root 확인 성공/실패 (mock adb)
- [x] UT-17: logger_config.json 마이그레이션 (version 없음 → v1)

### Integration Tests
- [x] IT-1: Wizard → Start Trace → Stop → 파일 생성 (mock adb)
- [x] IT-2: parse_raw() → DataEngine.load_dataset_from_dataframe() → 데이터셋 로드

## 11. 성공 기준
- [x] 텍스트 ftrace 파일을 열면 파싱되어 테이블에 표시
- [x] Wizard에서 캡처 모드 선택 가능 (perfetto / raw_ftrace)
- [x] raw_ftrace 모드: Start → 진행 표시 → Stop → 파일 저장 → 파싱 제안
- [x] root 없는 기기에서 명확한 안내 + perfetto 모드 권장
- [x] 100만 라인 파싱 5초 이내 (M1 16GB)
- [x] 트레이스/파싱 중 UI 프리즈 없음
- [x] sysfs 상태 복원 보장

## 12. 미해결 질문
- (없음)

## 13. 실행 계획

### 구현 순서
1. `parsers/ftrace_parser.py` — parse_raw() 구현 (독립, 의존성 없음)
2. `ui/dialogs/trace_progress_dialog.py` — AdbTraceController + TraceProgressDialog (독립)
3. `ui/dialogs/android_logger_wizard.py` — RootCheckPage 추가, 캡처 모드, config 마이그레이션
4. `ui/main_window.py` — 연결 교체, ParseWorker
5. `tests/` — 전체 테스트

### 병렬 가능 그룹
- Group 1 (병렬): 모듈 1 (parser) + 모듈 2 (dialog/controller)
- Group 2 (순차): 모듈 3 (wizard) → 모듈 4 (main_window)
- Group 3: 모듈 5 (tests) — 모두 완료 후

### 예상 파일 변경
- 신규: trace_progress_dialog.py, test_ftrace_parser.py, test_trace_progress.py
- 수정: ftrace_parser.py, android_logger_wizard.py, main_window.py

### CHANGELOG
- Added: FtraceParser.parse_raw() — regex-based ftrace text parser
- Added: AdbTraceController — non-blocking adb trace management
- Added: TraceProgressDialog — progress display with stop capability
- Added: RootCheckPage in Android Logger Wizard
- Added: Capture mode selection (Perfetto / Raw Ftrace)
- Changed: Block layer trace uses QThread worker for parsing
