# 조사 결과 — DGS Logger Wizard 리팩토링

> 작성일: 2026-02-12

---

## 1. Perfetto UI Record Trace 분석

### 레이아웃 구조
Perfetto UI의 Record Trace 페이지는 **단일 페이지 + 좌측 카테고리 사이드바** 패턴:

```
┌──────────────────────────────────────────────┐
│  Top Bar (Navigation)                        │
├────────────┬─────────────────────────────────┤
│            │                                 │
│  Category  │   Settings Content Area         │
│  Sidebar   │                                 │
│            │   - Recording Settings          │
│  ☐ Target  │     (Mode, Buffer, Duration)    │
│  ☐ Probes  │                                 │
│    CPU     │   - Probe-specific options       │
│    GPU     │     (checkboxes, dropdowns)     │
│    Memory  │                                 │
│    Android │                                 │
│    Chrome  │                                 │
│  ☐ Advanced│                                 │
│            │   [▶ Start Recording]           │
│            │                                 │
├────────────┴─────────────────────────────────┤
│  Status Bar / Connection Info                │
└──────────────────────────────────────────────┘
```

### 설정 흐름
- **위자드가 아님** — 단일 페이지에서 모든 설정을 한 번에 볼 수 있음
- 좌측 사이드바에서 카테고리를 클릭하면 우측 콘텐츠가 전환됨
- 상단에 Recording Settings (모드, 버퍼, 시간), 하단에 Probes 탭별 옵션
- "Start Recording" 버튼은 항상 보임 (스크롤 없이)
- 연결 상태(Device connection)는 상단에 인라인으로 표시

### 디자인 특징
- **다크/라이트 테마** 지원, 기본 다크
- 색상: 배경 `#1a1a2e` 계열, 강조 `#03DAC5` (teal), 버튼 `#4CAF50` (green)
- 폰트: Roboto / system sans-serif, 14px 기본
- 간격: 카테고리 항목 간 8px, 섹션 간 16px, 패딩 24px
- 프로브 섹션은 **토글 가능한 카드** 형태 (아코디언이 아닌 체크박스+확장)
- 최소한의 장식, 정보 밀도 높음

---

## 2. 유사 도구 패턴

| 도구 | 설정 방식 | 장점 | 단점 |
|------|-----------|------|------|
| **Perfetto UI** | 단일 페이지 + 카테고리 사이드바 | 전체 설정 한눈에 파악, 비순차적 접근 가능 | 옵션 많으면 콘텐츠 영역 복잡해짐 |
| **Android Studio Profiler** | 모달 다이얼로그 + 탭 | 간결, 빠른 시작 가능 | 고급 설정 숨겨져 있음 |
| **Wireshark Capture Options** | 단일 다이얼로그 + 탭 바 | 모든 옵션 한 화면, 인터페이스 목록 명확 | 탭이 많아지면 발견성 떨어짐 |
| **Chrome DevTools Performance** | 팝오버 설정 + 원클릭 시작 | 극도로 간단 | 고급 옵션 접근 어려움 |
| **Instruments (macOS)** | 위자드(템플릿 선택) → 설정 패널 | 템플릿으로 빠른 시작 | 커스텀 설정이 번거로움 |

### 패턴 정리
전문 도구들의 공통점:
1. **위자드보다 단일 페이지 선호** — Next/Back 클릭 없이 설정 전체를 조망
2. **카테고리 사이드바** 또는 **탭 바**로 섹션 전환
3. **시작 버튼은 항상 접근 가능** (하단 고정 또는 상단 고정)
4. **연결 상태는 인라인** — 별도 페이지가 아닌 상단 배너/섹션

---

## 3. PySide6 구현 방안

| 방안 | 장점 | 단점 | 추천 |
|------|------|------|------|
| **A. QWizard 커스텀 스타일링** | 기존 코드 최소 변경, QWizardPage 재사용 | 사이드바/자유 네비게이션 불가, 페이지 순서 강제, 스타일 제한 심함 | ❌ |
| **B. QDialog + QListWidget(사이드바) + QStackedWidget** | Perfetto 스타일 완벽 구현 가능, 비순차 탐색, 자유도 높음 | 직접 구현 필요량 많음 (네비게이션, 유효성 검증) | ✅ **추천** |
| **C. QDialog + QTabWidget** | 간단, Qt 기본 위젯으로 충분 | 탭 많으면 지저분, Perfetto 느낌 안 남 | △ 차선 |
| **D. QMainWindow 서브클래스 (독립 창)** | 메뉴바, 툴바, 상태바 활용 가능 | 다이얼로그 모달 흐름에 안 맞음 | ❌ |

### 추천: 방안 B 상세 설계

```python
class LoggerSetupDialog(QDialog):
    """Perfetto-style single-page logger configuration dialog."""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(800, 560)
        
        main_layout = QHBoxLayout(self)
        
        # 좌측: 카테고리 사이드바
        self._sidebar = QListWidget()
        self._sidebar.setFixedWidth(180)
        self._sidebar.setStyleSheet("""
            QListWidget { background: #2b2b3d; border: none; }
            QListWidget::item { padding: 10px 16px; color: #ccc; }
            QListWidget::item:selected { background: #3d3d5c; color: #fff; }
        """)
        
        # 우측: 콘텐츠 스택
        self._stack = QStackedWidget()
        
        main_layout.addWidget(self._sidebar)
        main_layout.addWidget(self._stack, stretch=1)
        
        # 카테고리 등록
        self._add_page("🔌 Connection", ConnectionPanel())
        self._add_page("⚙️ Recording", RecordingSettingsPanel())
        self._add_page("📡 Probes", ProbeSelectionPanel())
        self._add_page("📋 Summary", SummaryPanel())
        
        # 하단 고정 버튼 바 (우측 콘텐츠 아래)
        # [Start Recording] [Save Config] [Cancel]
```

### PySide6 Modern UI 베스트 프랙티스
- **QSS(Qt Style Sheets)** 로 다크 테마 적용 — 앱 전체 또는 다이얼로그 단위
- **QPropertyAnimation** 으로 사이드바 전환 시 페이드/슬라이드 효과 (선택)
- **아이콘**: Material Design Icons 또는 emoji로 카테고리 구분
- **상태 표시**: QLabel + 컬러 인디케이터 (● 녹색=연결됨, ● 빨간=미연결)
- **반응형**: QSplitter 사용 시 사이드바 리사이즈 가능

---

## 4. 기존 코드 재사용 가능

- **`AdbCheckPage._check_adb()`**: ADB 검색 로직 → `ConnectionPanel`에 그대로 이식
- **`AdbCheckPage._refresh_devices()`**: 디바이스 목록 갱신 → `ConnectionPanel`에 이식
- **`PerfettoCheckPage._check_perfetto()`**: Perfetto 존재 확인 → `ConnectionPanel` 하단에 자동 체크로 통합
- **`RootCheckPage._check_root()`**: Root 확인 → `ConnectionPanel`에서 캡처 모드 선택 시 조건부 표시
- **`TraceConfigPage` 전체**: 캡처 모드, 버퍼, 이벤트, 출력 경로 → `RecordingSettingsPanel` + `ProbeSelectionPanel`로 분할
- **`SummaryPage._build_config()`**: 설정 직렬화 → 그대로 재사용
- **`load_logger_config()` / `save_logger_config()`**: 설정 영속화 → 변경 없이 재사용
- **`migrate_config()`**: 마이그레이션 → 변경 없이 재사용
- **`DEFAULT_EVENTS`**: 이벤트 목록 → 변경 없이 재사용
- **`main_window.py`의 `_on_start_trace()` (line 1938~2050)**: 트레이스 시작 로직 → 인터페이스만 `wizard.start_requested` → `dialog.start_requested`로 변경

---

## 5. 직접 구현 필요

- **카테고리 사이드바 위젯**: QWizard에는 없는 개념. QListWidget 기반으로 새로 구현
- **비순차 유효성 검증 시스템**: QWizard는 순차 isComplete()로 관리하지만, 단일 페이지에서는 각 패널의 상태를 종합해서 Start 버튼 활성화 판단 필요
- **인라인 상태 표시**: ADB/디바이스/Perfetto/Root 상태를 사이드바 아이콘 색상으로 반영 (✅/❌)
- **하단 고정 액션 바**: 스크롤과 무관하게 Start Recording 버튼 항상 접근 가능
- **다크 테마 QSS**: 현재 위자드는 시스템 테마 의존. Perfetto 스타일은 전용 다크 QSS 필요

---

## 6. 핵심 인사이트

1. **위자드 → 단일 페이지 전환이 핵심 개선**: 현재 5단계 위자드의 가장 큰 문제는 "설정 확인하려면 Back을 여러 번 눌러야 함". Perfetto처럼 사이드바+단일 페이지로 바꾸면 UX가 극적으로 개선됨.

2. **ADB+Device+Perfetto/Root 체크를 "Connection" 하나로 통합**: 현재 3개 페이지(AdbCheck, PerfettoCheck, RootCheck)가 하는 일은 본질적으로 "연결 가능한가?" 하나. 연결 패널에서 자동으로 순차 체크하고 상태만 표시하면 됨.

3. **기존 비즈니스 로직의 80%는 재사용 가능**: ADB 체크, 디바이스 열거, Perfetto 확인, root 확인, 설정 저장/로드 — 이 모든 로직은 UI 레이어만 교체하면 됨. 핵심 변경은 **레이아웃 구조**뿐.

4. **페이지 수 감소**: 5개 위자드 페이지 → 3~4개 사이드바 패널 (Connection, Recording Settings, Probes, Summary). Summary도 선택적 — Start 버튼이 항상 보이면 별도 요약 불필요.

5. **점진적 마이그레이션 가능**: 기존 `QWizardPage` 내부 위젯들을 `QWidget` 패널로 옮기는 것이므로, 각 패널을 하나씩 마이그레이션 가능.

---

## 7. 제안 파일 구조

```
data_graph_studio/ui/dialogs/
├── android_logger_wizard.py      # (기존, deprecated 예정)
├── logger_setup_dialog.py        # 새 메인 다이얼로그
├── logger_panels/
│   ├── __init__.py
│   ├── connection_panel.py       # ADB + Device + Perfetto/Root 통합
│   ├── recording_panel.py        # 캡처 모드, 버퍼, 시간 제한
│   ├── probe_panel.py            # Ftrace 이벤트 선택, 출력 경로
│   └── summary_panel.py          # (선택) 최종 확인
└── trace_progress_dialog.py      # (기존, 변경 없음)
```

---

## 8. 예상 작업량

| 항목 | 예상 시간 | 난이도 |
|------|-----------|--------|
| LoggerSetupDialog 프레임 (사이드바 + 스택) | 2h | ★★☆ |
| ConnectionPanel (기존 로직 이식 + 통합) | 3h | ★★★ |
| RecordingPanel (기존 TraceConfigPage 분할) | 1.5h | ★★☆ |
| ProbePanel (이벤트 체크박스 + 출력 경로) | 1.5h | ★★☆ |
| 다크 테마 QSS | 2h | ★★☆ |
| 유효성 검증 시스템 | 1.5h | ★★★ |
| main_window.py 통합 | 1h | ★☆☆ |
| 테스트 및 폴리싱 | 2h | ★★☆ |
| **합계** | **~14.5h** | |
