# PRD: MainWindow & GraphPanel God Object 리팩토링

## 목표
`main_window.py` (5,248줄, 216 메서드)와 `graph_panel.py` (5,019줄, 150 메서드)를 책임별로 분리하여 유지보수성을 높인다.

## 범위
- **기능 변경 없음** — 순수 리팩토링
- **기존 테스트 100% 통과** 유지
- **공개 API(시그널, 메서드명) 유지** — 외부에서 호출하는 인터페이스 변경 최소화

---

## Phase 1: MainWindow 분리 (main_window.py → 6개 모듈)

### 1.1 MenuBarController (`ui/controllers/menubar_controller.py`)
- `_setup_menubar()` (284~671행, ~388줄)
- 메뉴 액션 핸들러: `_on_open_file`, `_on_export`, `_show_about`, `_show_shortcuts`, `_on_theme_changed`, `_on_toggle_*` 등
- 최근 파일 관리: `_update_recent_files_menu`, `_get_recent_files`, `_add_to_recent_files`, `_clear_recent_files`
- 예상: ~800줄

### 1.2 FileLoadingController (`ui/controllers/file_loading_controller.py`)
- `DataLoaderThread`, `DataLoaderThreadWithSettings` 클래스
- 파일 로딩: `_on_open_file`, `_load_file`, `_load_file_with_settings`, `_on_loading_progress`, `_on_loading_finished`
- 파싱 프리뷰: `_show_parsing_preview`, `_check_large_file_warning`
- 다중 파일: `_on_open_multiple_files`
- 프로젝트 로딩: `_load_project_file`, `_show_new_project_wizard`
- 드래그앤드롭: `dragEnterEvent`, `dropEvent`, `_handle_dropped_files`
- 클립보드 임포트: `_on_import_from_clipboard`, `_paste_from_clipboard`
- 예상: ~600줄

### 1.3 IPCController (`ui/controllers/ipc_controller.py`)
- `_setup_ipc_server()` + 모든 `_ipc_*` 메서드 (1354~1810행, ~456줄)
- IPC 서버 설정 및 핸들러 등록
- 예상: ~500줄

### 1.4 DatasetController (`ui/controllers/dataset_controller.py`)
- 데이터셋 관리: `_on_add_dataset`, `_add_dataset_from_file`, `_load_dataset`, `_on_dataset_*`
- 비교 모드: `_set_comparison_mode`, `_on_comparison_*`, `_start_*_comparison`, `_show_comparison_view`
- 비교 리포트: `_on_export_comparison_report`
- 예상: ~700줄

### 1.5 ProfileUIController (`ui/controllers/profile_ui_controller.py`)
- 프로필 메뉴/UI: `_on_new_profile_menu`, `_on_load_profile_menu`, `_on_save_profile_menu`
- 프로필 CRUD: `_on_profile_*_requested` 메서드들
- 프로필 비교: `_on_profile_comparison_started`, `_on_profile_comparison_ended`
- 프로필 자동저장: `_schedule_profile_autosave`, `_autosave_active_profile`
- 예상: ~500줄

### 1.6 MainWindow (리팩토링 후)
- `__init__`, `_setup_window`, `_setup_main_layout`, `_setup_statusbar`
- 컨트롤러 초기화 및 연결
- `_connect_signals`, `closeEvent`, `keyPressEvent`
- 레이아웃/패널 관리: `_reset_layout`, `_toggle_panel_visibility`
- 오토리커버리: `_setup_autorecovery`, `_autosave_session`
- 예상: ~800줄

---

## Phase 2: GraphPanel 분리 (graph_panel.py → 4개 모듈)

### 현재 구조
- `GraphOptionsPanel` (42~1016행, ~975줄) — 옵션 UI
- `LegendSettingsPanel` (1017~1209행, ~193줄) — 범례 설정
- `StatPanel` (1210~1616행, ~407줄) — 통계 패널
- `MainGraph` (1617~2935행, ~1,319줄) — pyqtgraph PlotWidget
- `GraphPanel` (2936~5019행, ~2,084줄) — 메인 통합 패널

### 분리 계획
- `GraphOptionsPanel` → `ui/panels/graph_options_panel.py` (독립 파일)
- `LegendSettingsPanel` → `ui/panels/legend_settings_panel.py` (독립 파일)
- `StatPanel` → `ui/panels/stat_panel.py` (독립 파일)
- `MainGraph` → `ui/panels/main_graph.py` (독립 파일)
- `GraphPanel` → 기존 파일에 남되, 위 4개를 import (~2,100줄)

---

## 구현 전략

### 컨트롤러 패턴
```python
class MenuBarController:
    def __init__(self, window: 'MainWindow'):
        self._window = window
        self._setup_menubar()
    
    # MainWindow의 속성에 접근할 때는 self._window.xxx
```

- 각 컨트롤러는 MainWindow 참조를 받아 필요한 위젯/상태에 접근
- MainWindow는 컨트롤러를 초기화하고 public 인터페이스 위임
- 기존 시그널/슬롯 연결은 유지

### 마이그레이션 순서
1. Phase 2 (GraphPanel) 먼저 — 클래스 단위 분리라 안전
2. Phase 1 (MainWindow) — 메서드 단위 분리라 더 섬세한 작업 필요

### 테스트 전략
- 각 Phase 후 전체 테스트 실행
- 기존 테스트가 모두 통과해야 다음 Phase 진행
- 새 컨트롤러에 대한 단위 테스트 추가 (import 가능성 확인 수준)

---

## 완료 기준
- [ ] `main_window.py` 800줄 이하
- [ ] `graph_panel.py` 2,500줄 이하
- [ ] 기존 테스트 100% 통과
- [ ] 새 모듈별 import 테스트
- [ ] `git diff --stat`으로 변경 확인
