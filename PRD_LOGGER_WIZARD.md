# PRD: Logger 메뉴 통합 + Wizard 리디자인 (v2)

> Round 1 리뷰 반영: 7 AGREE / 5 REJECT → 피드백 반영 후 v2

## 1. 목표
Logger 메뉴의 중복 항목(Start Block Trace / Setup Android Logger)을 통합하고, Wizard를 Perfetto UI Record 화면 수준의 전문 도구 UI로 리디자인한다.

**주요 사용자**: Android 성능 분석을 하는 개발자/엔지니어. 블록 레이어 트레이스 수집 경험이 있는 중급 이상 사용자.

## 2. 배경
현재 Logger 메뉴에 "Start Block Layer Trace..."와 "Setup Android Logger..." 두 개가 있다. Setup 끝에서 Start를 누르면 트레이스가 시작되고, Start에서 config 없으면 Setup으로 보내는 구조라 실질적으로 중복.

## 3. 조사 요약
### 검토한 대안
| 대안 | 장점 | 단점 | 채택 여부 |
|------|------|------|----------|
| QWizard 유지 + 스타일 개선 | 최소 변경 | 커스텀 레이아웃 한계, 버튼 위치 고정 | ❌ |
| QDialog + QStackedWidget | 완전한 레이아웃 자유도 | 네비게이션 직접 구현 | ❌ |
| **QDialog + 좌측 카테고리 + 우측 설정 (Perfetto 스타일)** | 단일 페이지, 전문 도구 느낌, 직관적 | 구현량 多 | ✅ |

### Perfetto UI Record 화면 분석
- **단일 페이지** — 좌측 카테고리 사이드바 + 우측 설정 패널
- **상단**: 연결 상태 + Recording Settings
- **좌측**: 프로브 카테고리 리스트
- **우측**: 선택한 카테고리의 상세 설정
- **하단**: Start Recording 버튼 (항상 보임)

## 4. 요구사항
### 4.1 기능 요구사항 (FR)
- [ ] FR-1: Logger 메뉴를 `Start Trace...` + `Configure...` 두 개로 통합
- [ ] FR-2: `Start Trace...` — 설정 있으면 바로 트레이스 시작, 없으면 Configure 다이얼로그 열기
- [ ] FR-3: `Configure...` — 단일 페이지 다이얼로그 (Perfetto 스타일)
- [ ] FR-4: 좌측 카테고리 패널: Connection, Capture Mode, Events, Output
- [ ] FR-5: Connection 카테고리: ADB 상태 + 디바이스 선택 (하나의 화면에). ADB 스캔 중 spinner + "Scanning devices..." 표시
- [ ] FR-6: Capture Mode 카테고리: Perfetto/Raw Ftrace 선택 + 모드별 설명. 모드 변경 시 Perfetto/Root 체크 자동 실행, 체크 중 spinner 표시
- [ ] FR-7: Events 카테고리: ftrace 이벤트 체크박스 (기존과 동일). **최소 1개 이벤트 필수** (0개 선택 시 Start 차단 + 경고)
- [ ] FR-8: Output 카테고리: 버퍼 크기 (4~512MB, 기본 64MB) + 저장 경로
- [ ] FR-9: 하단 고정: "Start Recording" 버튼 (녹색, primary) + "Save Config" + "Close"
- [ ] FR-10: Start Recording 시 유효성 검사 실패 → 해당 카테고리로 자동 이동 + 경고
- [ ] FR-11: Perfetto 모드 시 trace_processor 자동 다운로드 (기존 로직 유지)
- [ ] FR-12: Raw Ftrace 모드 시 root 확인 (기존 로직 유지, 인라인으로)
- [ ] FR-13: 설정 저장/로드 (`~/.data_graph_studio/logger_config.json`, v0→v1 자동 마이그레이션)
- [ ] FR-14: **Start Recording 클릭 시 즉시 버튼 disabled** → accept 후 main_window에서 처리 (더블클릭 방지)
- [ ] FR-15: **Close 시 미저장 변경사항 있으면 "Save changes?" 확인 다이얼로그** (Save/Discard/Cancel)
- [ ] FR-16: **키보드만으로 전체 워크플로우 완료 가능** (Tab: 카테고리→우측패널→하단버튼, ↑↓: 카테고리 이동)

### 4.2 비기능 요구사항 (NFR)
- [ ] NFR-1: 다이얼로그 최소 700x500, 최대 제한 없음
- [ ] NFR-2: 좌측 카테고리 폭 180px 고정, 우측 stretch
- [ ] NFR-3: 카테고리 선택 시 우측 패널 전환 50ms 이내
- [ ] NFR-4: ADB 디바이스 스캔 QProcess 비동기, 5초 타임아웃
- [ ] NFR-5: Perfetto/Root 체크는 Capture Mode 변경 시 자동 실행
- [ ] NFR-6: **스타일: 시스템 테마 기본 따르기** + Start Recording 버튼만 녹색 강조 + 좌측 사이드바 약간의 배경색 차이. 앱 전체와 일관성 유지.
- [ ] NFR-7: **다이얼로그 closeEvent() 시 진행 중인 QProcess.kill() + 타이머 정리 보장**
- [ ] NFR-8: **ADB 의존 테스트는 반드시 mock 사용** (CI flaky 방지)

## 5. 범위
### 포함
- `android_logger_wizard.py` → `trace_config_dialog.py` 전면 재작성 (QWizard → QDialog)
- `main_window.py` Logger 메뉴 + 핸들러 수정
- 기존 테스트 업데이트 + 신규 테스트 추가
- CHANGELOG 항목 추가

### 제외
- `trace_progress_dialog.py` 내부 로직
- FtraceParser 로직
- 새로운 트레이스 기능 추가

## 6. 기술 설계
### 아키텍처

```
TraceConfigDialog (QDialog)
├── QHBoxLayout (메인)
│   ├── QListWidget (좌측 카테고리, 180px 고정)
│   │   ├── "🔌 Connection"
│   │   ├── "📡 Capture Mode"
│   │   ├── "📋 Events"
│   │   └── "💾 Output"
│   └── QStackedWidget (우측 패널, stretch)
│       ├── ConnectionPanel (ADB체크 + 디바이스 선택 + spinner)
│       ├── CaptureModePanel (Perfetto/Ftrace + root/perfetto 체크 + spinner)
│       ├── EventsPanel (ftrace 이벤트 체크박스)
│       └── OutputPanel (버퍼 크기 SpinBox 4-512MB + 저장 경로)
├── QFrame (구분선)
└── QHBoxLayout (하단 버튼)
    ├── QPushButton "Start Recording" (녹색, primary)
    ├── QPushButton "Save Config"
    └── QPushButton "Close"
```

### Public API
```python
class TraceConfigDialog(QDialog):
    def __init__(self, parent=None) -> None: ...
    def get_config(self) -> dict[str, Any]: ...      # 현재 설정 수집
    def set_config(self, config: dict) -> None: ...   # 패널에 값 설정
    def is_dirty(self) -> bool: ...                   # 미저장 변경 여부
    
    # Panels (read-only access)
    connection_panel: ConnectionPanel
    capture_panel: CaptureModePanel
    events_panel: EventsPanel
    output_panel: OutputPanel
```

### Config Schema
```json
// v0 (기존, version 키 없음)
{
  "device_serial": "ABC123",
  "buffer_size_mb": 64,
  "events": ["block/block_rq_issue", "block/block_rq_complete"],
  "save_path": "/tmp/trace.txt"
}

// v1 (현재)
{
  "version": 1,
  "device_serial": "ABC123",
  "capture_mode": "perfetto",       // 신규: "perfetto" | "raw_ftrace"
  "sysfs_path": "/sys/kernel/tracing",  // 신규
  "buffer_size_mb": 64,
  "events": ["block/block_rq_issue", "block/block_rq_complete"],
  "save_path": "/tmp/trace.csv"
}

// 마이그레이션 v0→v1: capture_mode="perfetto", sysfs_path="/sys/kernel/tracing" 추가, version=1 설정
```

### 데이터 흐름
1. 다이얼로그 열기 → `load_logger_config()` → `set_config()` → 각 패널에 값 설정
2. 사용자 설정 변경 → 패널 내부 상태만 업데이트 (dirty flag 설정)
3. "Save Config" → `get_config()` → `save_logger_config()` → dirty flag 리셋
4. "Start Recording" → 유효성 검사 → config 저장 → 버튼 disabled → `dialog.accept()`
5. "Close" → dirty check → 미저장 시 확인 다이얼로그 → reject/accept
6. **closeEvent()** → 진행 중 QProcess kill + 타이머 정리

### main_window.py 변경
- `_on_start_trace()`: config 존재하고 유효 → 바로 트레이스, 아니면 → Configure 다이얼로그
- `_on_configure_trace()`: 항상 다이얼로그 열기 (설정만)
- 기존 `_on_setup_android_logger()`, `_on_start_blk_trace()` 제거

## 7. 엣지 케이스 & 에러 처리
- EC-1: ADB 미설치 → Connection 패널에 설치 안내 링크, Start 비활성화
- EC-2: 디바이스 미연결 → Connection 패널에 안내, Start 시 Connection으로 이동
- EC-3: Perfetto 모드인데 디바이스에 perfetto 없음 → Capture Mode 패널에 경고, Start 차단
- EC-4: Raw Ftrace 모드인데 root 없음 → Capture Mode 패널에 경고, Start 차단
- EC-5: 저장 경로가 빈 문자열 → Start 시 파일 다이얼로그 자동 열기
- EC-6: 설정 파일 손상(JSON 파싱 실패) → `load_logger_config()` 기본값 반환, warning 로깅
- EC-7: ADB 스캔 중 타임아웃 → "Scan timed out" 메시지, Refresh 버튼 활성화, warning 로깅
- EC-8: **Events 0개 선택 + Start → "Select at least one event" 경고, Events 카테고리로 이동**
- EC-9: **Start Recording 더블클릭 → 첫 클릭에서 버튼 즉시 disabled (FR-14)**
- EC-10: **Close 시 미저장 변경 → "Save changes?" 다이얼로그 (FR-15)**
- EC-11: **다이얼로그 close 시 ADB 스캔 진행 중 → QProcess.kill() 자동 정리 (NFR-7)**

## 8. 알려진 리스크 (Pre-mortem)
| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| QWizard 기반 기존 테스트 깨짐 | 높음 | 중 | 테스트를 새 클래스명/구조에 맞춰 업데이트 |
| 시스템 테마에서 녹색 버튼이 부자연스러움 | 중 | 낮 | QPalette 기반 accent color 사용, QSS 최소화 |
| 단일 페이지로 바꾸면 초보자가 어디서 시작할지 모름 | 낮 | 중 | Connection이 기본 선택, 미완료 항목에 ⚠️ 표시 |

## 9. 성능 목표
- 다이얼로그 열기: < 200ms
- 카테고리 전환: < 50ms
- ADB 디바이스 스캔: < 5s (타임아웃)
- 메모리: 다이얼로그 < 10MB

## 10. 테스트 시나리오

### FR ↔ 테스트 매핑

| FR | 테스트 | 설명 |
|----|--------|------|
| FR-1 | E2E-1 | 메뉴 구조 확인 |
| FR-2 | E2E-1 | Start Trace 동작 |
| FR-3 | UT-1 | 다이얼로그 구조 |
| FR-4 | UT-1 | 4개 카테고리 |
| FR-5 | UT-4, UT-12 | ADB 체크/스캔 |
| FR-6 | UT-6, UT-8, UT-9 | 모드 전환/체크 |
| FR-7 | UT-13 | 이벤트 0개 차단 |
| FR-8 | UT-3 | 버퍼/경로 저장 |
| FR-9 | UT-1 | 버튼 존재 |
| FR-10 | UT-5 | 유효성→카테고리 이동 |
| FR-11 | UT-8 | Perfetto 체크 |
| FR-12 | UT-9 | Root 체크 |
| FR-13 | UT-3, UT-7, UT-11 | config 저장/로드/마이그레이션/손상 |
| FR-14 | UT-14 | 더블클릭 방지 |
| FR-15 | UT-15 | 미저장 경고 |
| FR-16 | UT-16 | 키보드 접근성 |

### Unit Tests
- [ ] UT-1: TraceConfigDialog 생성 시 4개 카테고리 + 3개 하단 버튼 표시
- [ ] UT-2: 카테고리 클릭 시 우측 패널 전환
- [ ] UT-3: config 로드/저장 라운드트립 (모든 필드)
- [ ] UT-4: ADB 미설치 시 Connection 패널 경고 표시 (mock shutil.which)
- [ ] UT-5: Start Recording 시 디바이스 미선택 → Connection으로 이동
- [ ] UT-6: Capture mode 변경 시 관련 체크 자동 실행
- [ ] UT-7: 기존 config 마이그레이션 v0→v1 (version 키 없는 dict → version=1)
- [ ] UT-8: Perfetto 미설치 디바이스 → Capture Mode 패널 경고 + Start 차단 (mock subprocess)
- [ ] UT-9: Root 없는 디바이스 + Raw Ftrace → 경고 + Start 차단 (mock subprocess)
- [ ] UT-10: 빈 저장 경로 + Start → 파일 다이얼로그 호출 (mock QFileDialog)
- [ ] UT-11: 손상된 config JSON → 기본값 로드 (tmpfile에 invalid JSON)
- [ ] UT-12: ADB 스캔 타임아웃 → 메시지 + Refresh 활성화 (mock QProcess timeout)
- [ ] UT-13: Events 0개 선택 + Start → 경고 + Events 카테고리 이동
- [ ] UT-14: Start Recording 클릭 → 버튼 즉시 disabled
- [ ] UT-15: 설정 변경 후 Close → "Save changes?" 다이얼로그 표시 (mock QMessageBox)
- [ ] UT-16: Tab/방향키로 카테고리→패널→버튼 이동 가능

### E2E Tests
- [ ] E2E-1: 메뉴 → Start Trace (설정 없음) → Configure 다이얼로그 열림
- [ ] E2E-2: 메뉴 → Configure → 설정 변경 → Save → 다시 열면 값 유지
- [ ] E2E-3: Configure → 설정 완료 → Start Recording → dialog accepted (config 저장됨)

### 테스트 전략
- **모든 외부 의존성(ADB, subprocess, QFileDialog) mock 필수** (NFR-8)
- 테스트 이름: `test_{시나리오}_{기대결과}`
- config fixture: `tmp_path`에 임시 config 파일 생성

## 11. 성공 기준
- [ ] Logger 메뉴가 Start Trace + Configure 두 개로 정리됨
- [ ] 다이얼로그가 좌측 180px 카테고리 + 우측 설정 패널 + 하단 고정 버튼 구조
- [ ] 기존 기능 100% 유지 (Perfetto/Raw Ftrace 캡처, config 저장/로드)
- [ ] 설정→트레이스 시작까지 클릭 수 3회 이내 (Configure 열기 → 설정 → Start)
- [ ] 16개 UT + 3개 E2E 전체 통과

## 12. 미해결 질문
- (없음)

---

## 실행 계획

### 구현 순서
1. `trace_config_dialog.py` 전면 작성 (TraceConfigDialog + 4개 Panel + config 유틸)
2. `main_window.py` Logger 메뉴 + 핸들러 수정
3. `android_logger_wizard.py` deprecated 처리 (import 호환 유지)
4. 테스트 작성 (16 UT + 3 E2E)

### 병렬 가능 그룹
- Group 1: trace_config_dialog.py (독립)
- Group 2 (순차, Group 1 완료 후): main_window.py → 테스트

### 예상 파일 변경
- 신규: `data_graph_studio/ui/dialogs/trace_config_dialog.py`
- 수정: `data_graph_studio/ui/main_window.py`
- 수정: `tests/unit/test_trace_progress.py` → `tests/unit/test_trace_config_dialog.py`
- 유지: `android_logger_wizard.py` (deprecated, import 호환)
