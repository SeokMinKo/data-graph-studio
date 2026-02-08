# Changelog

## [v0.23.0] — 2026-02-09

### 🔐 Security / Updates

- **Windows 업데이트 무결성 검증** — Release에 `.sha256` 체크섬 파일을 함께 업로드하고, 업데이트 다운로드 후 SHA256 검증 통과 시에만 installer 실행
- **Frozen 빌드 버전 안정화** — CI에서 `data_graph_studio/_build_version.py`에 버전 주입 (PyInstaller 환경에서도 정확한 버전 판별)

### 🧹 Undo/Redo

- **UndoAction 완전 제거** — Undo 시스템을 `UndoCommand(do/undo)`로 통일, 테스트/레거시 정리
- **대형 데이터셋 삭제 Undo 메모리 보호** — 대형 데이터셋 삭제는 DF 스냅샷 대신 파일 경로 기반 reload로 복구

### 🧰 CI

- **Windows installer smoke 강화** — installer 체크섬 생성/업로드 포함

---

All notable changes to Data Graph Studio.

Format: [Conventional Commits](https://www.conventionalcommits.org/)

## [v0.22.1] — 2026-02-09

### 🐛 Bug Fixes

- **Computed Column Undo/Redo 복구** — 계산 컬럼 추가 후 Undo/Redo 시 DataFrame이 실제로 되돌아가도록 수정

---

## [v0.22.0] — 2026-02-09

### ✨ Features

- **Undo/Redo 확대 (세션 내)** — Filter/Sort/Chart Settings, Dataset Activate/Remove, Compare mode/datasets까지 되돌리기 지원
- **History Panel** — Undo 타임라인을 Dock 패널로 제공 (View 메뉴에서 토글)
- **Windows 자동 업데이트 (설치형)** — GitHub Releases 최신 버전 확인 후 installer 다운로드/실행

### 🧰 Build/Release

- **Windows 설치형 배포 파이프라인** — GitHub Actions에서 PyInstaller + Inno Setup으로 `DataGraphStudio-Setup-vX.Y.Z.exe` 생성 후 Release에 업로드

---

## [v0.21.0] — 2026-02-08

### 🔧 Refactor

- **DataEngine God Object 분리** — Facade 패턴으로 5개 모듈 추출:
  - `FileLoader` — 파일 로딩, 인코딩 감지, lazy loading
  - `DataQuery` — stateless 필터/정렬/통계
  - `DataExporter` — CSV/Excel/Parquet 내보내기
  - `DatasetManager` — 멀티 데이터셋 CRUD
  - `ComparisonEngine` — 비교 분석, 통계 검정

### ✨ Features

- **IPC 동적 포트** — 기본 52849, 사용 중이면 자동 +1 (최대 100회). `~/.dgs/ipc_port`에 pid:port 기록. `dgs_client.py` 자동 디스커버리
- **Autosave 복구 개선** — "Don't show again" 체크박스, 복구 실패 시 .bak 백업 + 에러 토스트
- **글로벌 크래시 로그** — `sys.excepthook`으로 `~/.dgs/crash.log`에 타임스탬프 + traceback 기록
- **v2 기능 MainWindow 와이어링** — 대시보드, 스트리밍, 계산 컬럼, 내보내기, 주석, 테마, 단축키

### 🧹 Chores

- **루트 정리** — 잡파일 삭제 (screenshot*.png, test_*.py, *.html 리포트, ad-hoc 스크립트)
- **.gitignore 강화** — 루트 *.png, *.html, *.csv, autosave.json, .dgs/ 등 추가
- **README 업데이트** — 아키텍처 다이어그램, v2 기능 사용 가이드 추가

---

## [v0.20.1] — 2026-02-08

### 🔧 Refactor

- **MainWindow God Object 분리** — 5,248줄 → 3,375줄, 4개 컨트롤러 추출 (IPC, FileLoading, Dataset, ProfileUI)
- **GraphPanel God Object 분리** — 5,019줄 → 2,133줄, 4개 모듈 추출 (GraphOptionsPanel, LegendSettingsPanel, StatPanel, MainGraph)

---

## [v0.20.0] — 2026-02-06

### ✨ Features

- **WPR Import Wizard 단계별 ETL 로딩** — WPAExporter 변환 단계 추가 + Parquet 변환/미리보기 흐름

---

## [v0.19.0] — 2026-02-05

### ✨ Features

- **Grid View (Facet Grid)** — 데이터를 카테고리별로 분할하여 여러 그래프로 표시 ([`92837ea`](../../commit/92837ea))
  - Chart 탭에 "Enable Grid View" 체크박스
  - Split by: Filter에서 선택된 열 기준으로 분할
  - Direction: Row / Column / Wrap 선택
  - 축 동기화 (zoom/pan 연동)

---

## [v0.18.3] — 2026-02-05

### 🐛 Bug Fixes

- **프로젝트 저장/로드 버그 수정** — 저장 시 데이터 소스 경로 포함, 로드 시 자동 복원 ([`b05e65f`](../../commit/b05e65f))

### ✨ Features

- **툴바 2줄 구성** — 1줄: 파일/선택도구/그리기/차트타입, 2줄: 스트리밍/비교 ([`b05e65f`](../../commit/b05e65f))

---

## [v0.18.0] — 2026-02-05

### ✨ Features

- **Help 메뉴 + Command Palette** — Ctrl+Shift+P / F1으로 VS Code 스타일 기능 검색, 모든 메뉴 액션 인덱싱 ([`f27dd60`](../../commit/f27dd60))
- **스트리밍 UI 연결** — 툴바 ▶Start/⏸Pause/⏹Stop 버튼, View 메뉴 Start/Stop Streaming, StreamingController 연동 ([`b5dda69`](../../commit/b5dda69))
- **Combination 모드 컬럼별 차트타입** — 각 value column별로 Line/Bar/Scatter/Area 개별 선택 가능 ([`0feb59b`](../../commit/0feb59b))

### 🐛 Bug Fixes

- **단축키 텍스트 입력 충돌 방지** — QLineEdit/QSpinBox 등에 포커스 시 단독키(1~6, F, Home, Delete) 단축키 무시 ([`47e1cd8`](../../commit/47e1cd8))
- **Combination 차트 Bar 렌더링 개선** — 바 너비 0.8x, outline pen 추가 ([`bb7fa95`](../../commit/bb7fa95))

---

## [v0.17.0] — 2026-02-04

### ✨ Features

- **Combination 차트 자동 전환** — Y축에 value column 2개 이상 추가 시 자동으로 🔀 Combination으로 전환, 1개로 줄이면 원래 차트 타입 복원 ([`691f005`](../../commit/691f005), [`e676d8c`](../../commit/e676d8c))
- **검색 가능 콤보박스** — 모든 Search columns/values 필드에 contains 매칭 검색 + 드롭다운 기능 통합 ([`5aae78f`](../../commit/5aae78f))
- **마커 테두리 옵션** — Style > Marker 섹션에 Border 체크박스 추가, Line/Scatter/Combo 차트 전부 적용 ([`cc7ba12`](../../commit/cc7ba12))

### 🐛 Bug Fixes

- **Compare 모드 샘플링** — 하드코딩(1K/5K) 제거, 프로파일의 sampling 설정(show_all_data/max_points) 그대로 사용 ([`e59533b`](../../commit/e59533b))

---

## [v0.15.7] — 2026-02-04

### 🐛 Bug Fixes

- Selection/Draw 마우스 드래그 버그 수정 — `mouseReleaseEvent` 중복 정의로 selection/draw 완료 처리가 무시되던 문제 해결 ([`9568bfa`](../../commit/9568bfa))
- `_on_mouse_clicked` scene signal과 `mousePressEvent` 충돌 제거 — press→drag→release 모델만 사용

### ✨ Features

- 툴바에 Draw 색상 선택 버튼 추가 — 클릭하면 색상 다이얼로그, 기본색 빨간색 ([`9568bfa`](../../commit/9568bfa))

---

## [v0.15.6] — 2026-02-04

### 🔧 Refactor

- 미사용 QComboBox import 제거, 프로파일/프로젝트 last-path 추적 추가, save-project 스텁 제거 ([`71c3c88`](../../commit/71c3c88))

---

## [v0.15.1] — 2026-02-04

### 🐛 Bug Fixes

- 세션 복원 시 프로파일이 프로젝트 탐색창에 표시되지 않는 버그 수정 — autosave에 프로파일 데이터 저장/복원 추가 ([`autosave-profiles`](../../commit/HEAD))

---

## [v0.15.0] — 2026-02-04

### ✨ Features

- Compare 전용 툴바 — Grid Layout(Row/Column/2×2) + Sync 토글(X/Y/Zoom/Selection) ([`8a79db8`](../../commit/8a79db8))
- Side-by-Side 비교 시 프로파일 그래프 설정 반영 — scatter, bar, line + group_by + 전체 value_columns ([`8a79db8`](../../commit/8a79db8))
- View 메뉴에서 Compare Toolbar 토글 가능, Compare 모드 진입/종료 시 자동 show/hide ([`8a79db8`](../../commit/8a79db8))

---

## [v0.14.4] — 2026-02-04

### 🐛 Bug Fixes

- 프로파일 이름 변경 시 access violation 크래시 수정 — 재진입 방지 가드 + 시그널 블로킹 ([`e651eb7`](../../commit/e651eb7))
- project_tree_view 시그널 disconnect RuntimeWarning 제거 ([`23867af`](../../commit/23867af))

---

## [v0.14.3] — 2026-02-04

### 🐛 Bug Fixes

- 존재하지 않는 그룹/값 컬럼 참조 시 ColumnNotFoundError 크래시 수정 ([`6c2cce4`](../../commit/6c2cce4))

---

## [v0.13.1] — 2026-02-04

### ✨ Features

- 릴리즈 노트 자동 생성 스크립트 + GitHub Actions 워크플로우 ([`8fa28cc`](../../commit/8fa28cc))

### 🐛 Bug Fixes

- 프로파일 독립성 버그 수정 + 트리 expand 상태 보존 ([`5d424bb`](../../commit/5d424bb))
- clean up unused imports and variables (bug hunt) ([`dd8253e`](../../commit/dd8253e))

## [v0.13.0] — 2026-02-04

### ✨ Features

- add tooltips to all UI buttons and interactive widgets ([`201f83d`](../../commit/201f83d))
- v2 7대 기능 구현 — 대시보드, 스트리밍, 컬럼 생성, 내보내기, 주석, 테마, 단축키 ([`7791174`](../../commit/7791174))
- single-dataset multi-profile comparison + IPC + Tailwind themes ([`a38ebf4`](../../commit/a38ebf4))

### 🐛 Bug Fixes

- accessibility crash + autosave dialog blocking ([`1be044d`](../../commit/1be044d))

## [v0.12.9] — 2026-02-03

### ✨ Features

- GroupBy multi-select checkboxes, search filters, dual aggregation, fix input heights ([`43d54e0`](../../commit/43d54e0))

## [v0.12.8] — 2026-02-03

### 🐛 Bug Fixes

- add missing agg_changed signal to _YAxisItemWidget ([`3f9ae35`](../../commit/3f9ae35))

## [v0.12.7] — 2026-02-03

### 🐛 Bug Fixes

- project tree profiles not rendering due to QPalette enum API change ([`2febb30`](../../commit/2febb30))
- show all percentile points with markers in Stats Pctl chart ([`bf9e9a3`](../../commit/bf9e9a3))
- GroupBy Ratio bar chart X-axis shows group names instead of numbers ([`06e2960`](../../commit/06e2960))

## [v0.12.6] — 2026-02-03

### ✨ Features

- Group By를 콤보박스로 변경 (X-Axis와 동일한 UX) ([`fcb0fcb`](../../commit/fcb0fcb))

## [v0.12.5] — 2026-02-03

### 🐛 Bug Fixes

- PE_PanelItemViewItem → QStyle.PE_PanelItemViewItem ([`525048f`](../../commit/525048f))

## [v0.12.4] — 2026-02-03

### ✨ Features

- Aggregation을 Group By로 이동 + Y-Axis 간소화 ([`69429b4`](../../commit/69429b4))

## [v0.12.3] — 2026-02-03

### ✨ Features

- Data 탭 [All] 버튼 제거 + 각 섹션 검색 필드 추가 ([`b0542bf`](../../commit/b0542bf))

## [v0.12.2] — 2026-02-03

### 🐛 Bug Fixes

- 테이블 높이 확대 + Summary 텍스트 선택/스크롤 지원 ([`74d43c5`](../../commit/74d43c5))

## [v0.12.1] — 2026-02-03

### 🐛 Bug Fixes

- Chart Options 탭 바 간격 축소 - 5개 탭 모두 표시 ([`ca4ba9b`](../../commit/ca4ba9b))

## [v0.12.0] — 2026-02-03

### ✨ Features

- Zone을 Chart Options Data 탭으로 이전 (v0.12.0) ([`5ae05a3`](../../commit/5ae05a3))

## [v0.11.8] — 2026-02-03

### 🐛 Bug Fixes

- Y range slider 반전 + Chip 레이아웃 + Zoom Undo/Redo ([`7102363`](../../commit/7102363))

## [v0.11.7] — 2026-02-03

### 🐛 Bug Fixes

- 프로젝트 탐색창 3가지 버그 수정 ([`76a2db9`](../../commit/76a2db9))

## [v0.11.6] — 2026-02-03

### 🐛 Bug Fixes

- ProfileModel internalPointer GC 크래시 수정 (PySide6) ([`eb27504`](../../commit/eb27504))

## [v0.11.5] — 2026-02-03

### 📌 Other Changes

- 위자드 완료 후 크래시 디버깅 로그 추가 ([`4d426ec`](../../commit/4d426ec))

## [v0.11.4] — 2026-02-03

### 🐛 Bug Fixes

- 마법사 완료 후 그래프 그리기 크래시 수정 ([`de85ece`](../../commit/de85ece))

## [v0.11.3] — 2026-02-03

### ⚡ Performance

- 파싱 프리뷰 속도 대폭 개선 ([`ebdb2c0`](../../commit/ebdb2c0))

## [v0.11.2] — 2026-02-03

### 🐛 Bug Fixes

- table_panel.py QMessageBox import 누락 수정 ([`628b15d`](../../commit/628b15d))

## [v0.11.1] — 2026-02-03

### 🐛 Bug Fixes

- parsing_step.py QApplication import 누락 수정 ([`0806c25`](../../commit/0806c25))

## [v0.11.0] — 2026-02-03

### 🐛 Bug Fixes

- AttributeError 전수 점검 - 22개 문제 수정 ([`1908ebf`](../../commit/1908ebf))

## [v0.10.9] — 2026-02-03

### 🐛 Bug Fixes

- AppState.begin/end_batch_update 추가 + ProfileModel stale pointer 방어 ([`6cd0dfd`](../../commit/6cd0dfd))

## [v0.10.8] — 2026-02-03

### 🐛 Bug Fixes

- 파싱 프로그래스바 10% 정지 문제 수정 ([`b58a8e3`](../../commit/b58a8e3))

## [v0.10.7] — 2026-02-03

### 🐛 Bug Fixes

- 마법사 프리뷰에서 컬럼 Exclude 시 크래시 수정 ([`b11d258`](../../commit/b11d258))

## [v0.10.6] — 2026-02-03

### 🐛 Bug Fixes

- 파싱 프리뷰에서 데이터 행이 헤더보다 컬럼 많을 때 크래시 수정 ([`e7ffcb8`](../../commit/e7ffcb8))

## [v0.10.5] — 2026-02-03

### 🐛 Bug Fixes

- 마법사 완료 시 apply_setting → apply_profile 수정 ([`0f49e79`](../../commit/0f49e79))

## [v0.10.4] — 2026-02-03

### ✨ Features

- 테이블 헤더 Ctrl+드래그로 Zone에 컬럼 배치 ([`10f6700`](../../commit/10f6700))

## [v0.10.3] — 2026-02-03

### 🐛 Bug Fixes

- drag&drop 시 _open_file AttributeError 수정 ([`525f904`](../../commit/525f904))

## [v0.10.2] — 2026-02-03

### 🐛 Bug Fixes

- 마법사 첫 프로파일 이름을 Profile_1로 저장 ([`fb387b1`](../../commit/fb387b1))

## [v0.10.1] — 2026-02-03

### 🐛 Bug Fixes

- 파일 로딩 후 프로젝트 탐색창에 데이터셋 표시되지 않던 버그 수정 ([`e00aeff`](../../commit/e00aeff))

## [v0.10.0] — 2026-02-03

### ✨ Features

- ETL 바이너리 파일 네이티브 파싱 지원 (etl-parser) ([`2de2a21`](../../commit/2de2a21))

## [v0.9.9] — 2026-02-03

### 🐛 Bug Fixes

- Zone chip layout - wider zones, remove maxWidth limits ([`874398f`](../../commit/874398f))

## [v0.9.8] — 2026-02-03

### 🎨 Style

- Fix Zone chip layout alignment and sizing ([`1db1628`](../../commit/1db1628))

## [v0.9.7] — 2026-02-03

### 🐛 Bug Fixes

- ProfileStore.add_setting -> add() method call ([`d10dbe8`](../../commit/d10dbe8))

## [v0.9.6] — 2026-02-03

### 🐛 Bug Fixes

- Wizard preview chart not rendering ([`629b4a4`](../../commit/629b4a4))

## [v0.9.5] — 2026-02-03

### 🎨 Style

- Wizard window width 3x larger (1500px) ([`2a5f838`](../../commit/2a5f838))

## [v0.9.4] — 2026-02-03

### 🐛 Bug Fixes

- Comprehensive theme color fixes ([`1060fac`](../../commit/1060fac))

## [v0.9.3] — 2026-02-03

### 🐛 Bug Fixes

- Align X-Axis/Group Zone with Chart Options panel ([`e1ab099`](../../commit/e1ab099))

## [v0.9.2] — 2026-02-03

### 🐛 Bug Fixes

- Wizard Finish button not triggering project creation ([`e55057d`](../../commit/e55057d))

## [v0.9.1] — 2026-02-03

### 🐛 Bug Fixes

- Wizard project creation async bug ([`7772028`](../../commit/7772028))

## [v0.9.0] — 2026-02-03

### ✨ Features

- Light theme + bug fixes ([`3567bd4`](../../commit/3567bd4))

## [v0.8.0] — 2026-02-03

### ✨ Features

- Data Table Enhancement - Sorting & Searching ([`818f824`](../../commit/818f824))
- 새 프로젝트 마법사 구현 (New Project Wizard) ([`29bb0d2`](../../commit/29bb0d2))

### 📌 Other Changes

- Fix: Improve drag-and-drop from table header and clean up context menu ([`d96d6d6`](../../commit/d96d6d6))
- Refactor: Extract helper classes to graph_widgets.py ([`9418419`](../../commit/9418419))
- Refactor: Extract SlidingWindowWidget to separate file ([`2b432d3`](../../commit/2b432d3))
- Fix readability: change light backgrounds to dark theme colors ([`75415c7`](../../commit/75415c7))
- Fix text readability: change dark text colors to light (#E6E9EF, #C2C8D1) ([`337980f`](../../commit/337980f))
- Fix: Enable X/Y-Axis Navigator checkboxes by default ([`cfdeca5`](../../commit/cfdeca5))
- Unify panel margins to 4px for aligned edges (Chart Options, Legend, Table zones) ([`d6fb078`](../../commit/d6fb078))
- Fix: Change Chart Options and Legend header color to white (#E6E9EF) ([`64bcbe1`](../../commit/64bcbe1))
- UI improvements: narrower sidebar, unified splitter widths, larger Stats font ([`b5c9c91`](../../commit/b5c9c91))
- Unify splitter handle width to 1px for consistent spacing ([`4dcf05d`](../../commit/4dcf05d))
- Fix: reorder setup calls - main_layout before toolbar ([`4981c20`](../../commit/4981c20))
- Remove Overview and Profile tabs from top area ([`9eac5df`](../../commit/9eac5df))

## [v0.7.0] — 2026-02-02

### 📌 Other Changes

- Integrate Project Explorer into MainWindow sidebar ([`7a94246`](../../commit/7a94246))
- Fix QA issues: mapper dataset_id, model icon, controller unsaved, view delete ([`71bd5d2`](../../commit/71bd5d2))
- Add profile controller with undo and tests ([`5a1e0a5`](../../commit/5a1e0a5))
- Add project tree view with context menus and shortcuts ([`367d698`](../../commit/367d698))
- Add GraphSettingMapper and tests ([`6664487`](../../commit/6664487))
- Add ProfileStore and freeze GraphSetting ([`16d3959`](../../commit/16d3959))
- Add profile tree model ([`25d6810`](../../commit/25d6810))

## [v0.6.0] — 2026-02-02

### 📌 Other Changes

- Add project explorer with profiles tree and save/load ([`1ff40a0`](../../commit/1ff40a0))

## [v0.5.2] — 2026-02-02

### 📌 Other Changes

- Allow header reorder and drag-to-zone together ([`c3ed5f5`](../../commit/c3ed5f5))

## [v0.5.1] — 2026-02-02

### 📌 Other Changes

- Add X/Y pan sync options for comparison ([`cd7917d`](../../commit/cd7917d))

## [v0.5.0] — 2026-02-02

### 📌 Other Changes

- Add missing column_action signal ([`c3dcfa9`](../../commit/c3dcfa9))

## [v0.4.9] — 2026-02-02

### 📌 Other Changes

- Enable drag on value chips ([`fda451b`](../../commit/fda451b))

## [v0.4.8] — 2026-02-02

### 📌 Other Changes

- Fix sliding window toggles ([`387c64b`](../../commit/387c64b))

## [v0.4.7] — 2026-02-02

### 📌 Other Changes

- Add format placeholders and scatter data labels ([`f5e7c71`](../../commit/f5e7c71))
- Unify axis/group/value/hover zones with draggable chips ([`ed652b2`](../../commit/ed652b2))

## [v0.4.6] — 2026-02-02

### 📌 Other Changes

- Fix chart options (log/reverse/smooth/labels/points) ([`36a950d`](../../commit/36a950d))

## [v0.4.5] — 2026-02-02

### 📌 Other Changes

- Fix Y sliding window orientation mapping ([`8a62d38`](../../commit/8a62d38))

## [v0.4.4] — 2026-02-02

### 📌 Other Changes

- Fix column selection checkbox contrast ([`9b1d323`](../../commit/9b1d323))

## [v0.4.3] — 2026-02-02

### 📌 Other Changes

- Fix menu hover contrast and drawing visibility/pen width ([`627c5f8`](../../commit/627c5f8))

## [v0.4.2] — 2026-02-02

### 📌 Other Changes

- Allow header reorder; require Shift for drag-to-zones ([`6336a62`](../../commit/6336a62))

## [v0.4.1] — 2026-02-02

### 📌 Other Changes

- Make Exclude column drop data and clean state ([`45f1924`](../../commit/45f1924))

## [v0.4.0] — 2026-02-02

### 📌 Other Changes

- Enable header drag reorder and persist column order ([`c3fa682`](../../commit/c3fa682))

## [v0.3.9] — 2026-02-02

### 📌 Other Changes

- Add header context menu actions for set-as and exclude ([`3742475`](../../commit/3742475))

## [v0.3.8] — 2026-02-02

### 📌 Other Changes

- Fix table context menu contrast and persist dataset state ([`5d7b2d4`](../../commit/5d7b2d4))

## [v0.3.7] — 2026-02-02

### 📌 Other Changes

- Improve parsing preview table/checkbox contrast ([`4aeafa5`](../../commit/4aeafa5))

## [v0.3.6] — 2026-02-02

### 📌 Other Changes

- Fix missing Any import ([`36ebe29`](../../commit/36ebe29))

## [v0.3.5] — 2026-02-02

### 📌 Other Changes

- Add autosave recovery with restore prompt ([`d450fc8`](../../commit/d450fc8))

## [v0.3.4] — 2026-02-02

### 📌 Other Changes

- Fix toolbar clear and chart type sync ([`0331dc2`](../../commit/0331dc2))

## [v0.3.3] — 2026-02-02

### 📌 Other Changes

- Enhance stats percentiles, groupby summary, overview height, draw toolbar ([`8059e60`](../../commit/8059e60))

## [v0.3.2] — 2026-02-02

### 📌 Other Changes

- Register datasets on load and add ([`e36b597`](../../commit/e36b597))

## [v0.3.1] — 2026-02-02

### 📌 Other Changes

- Align sliding window distribution with plotted data ([`a40c0d6`](../../commit/a40c0d6))

## [v0.3.0] — 2026-02-02

### 📌 Other Changes

- Guard drawing menu actions before graph panel init ([`0a54a6d`](../../commit/0a54a6d))

## [v0.2.9] — 2026-02-02

### 📌 Other Changes

- Use margin on fit/reset auto-range ([`372a744`](../../commit/372a744))

## [v0.2.8] — 2026-02-02

### 📌 Other Changes

- Auto-fit graph with min/max margin ([`2522cc0`](../../commit/2522cc0))

## [v0.2.7] — 2026-02-02

### 📌 Other Changes

- Fix windowed index length and add multi-file dataset load ([`557bea2`](../../commit/557bea2))

## [v0.2.6] — 2026-02-02

### 📌 Other Changes

- Fix stats pie chart, aggregation sync, floating actions, drawing UX ([`b99cc23`](../../commit/b99cc23))

## [v0.2.5] — 2026-02-02

### 📌 Other Changes

- Apply dark style to parsing preview dialog ([`05cf5ea`](../../commit/05cf5ea))

## [v0.2.4] — 2026-02-02

### 📌 Other Changes

- Fix Overview card background for dark theme ([`7c28076`](../../commit/7c28076))

## [v0.2.3] — 2026-02-02

### 📌 Other Changes

- Use polars-friendly encodings in parsing dialog ([`73af7d7`](../../commit/73af7d7))

## [v0.2.2] — 2026-02-02

### 📌 Other Changes

- Normalize encoding names for polars CSV ([`8886d03`](../../commit/8886d03))

## [v0.2.1] — 2026-02-02

### 📌 Other Changes

- Default to midnight theme for readability ([`1e3c0f2`](../../commit/1e3c0f2))
- Add setuptools_scm for versioning ([`0c65f70`](../../commit/0c65f70))
- Improve contrast in overview and dataset sidebar ([`ec9c486`](../../commit/ec9c486))
- Reduce spacing between chart options and graph ([`ba454cc`](../../commit/ba454cc))
- Adopt dark blue theme palette and align chart option grids ([`bebbe6f`](../../commit/bebbe6f))
- Update accent to light blue #7EB6FF with improved contrast ([`e61d1f2`](../../commit/e61d1f2))
- Combine overview and profile into tabs ([`ce890ef`](../../commit/ce890ef))
- Lighten parsing preview dialog to match minimal theme ([`fb8c98b`](../../commit/fb8c98b))
- Apply minimal modern grayscale theme and fix table text contrast ([`e77c36f`](../../commit/e77c36f))
- Expose summary via IPC and update on IPC load ([`117cc4c`](../../commit/117cc4c))
- Debounce window slider, add window size UI, full-data summary ([`25d23be`](../../commit/25d23be))
- Add window UI controls and full-dataset stats ([`287cc4a`](../../commit/287cc4a))
- Add window setter for lazy windowed datasets ([`e8287a7`](../../commit/e8287a7))
- Add windowed loading and parquet conversion for large CSVs ([`7ec51a6`](../../commit/7ec51a6))
- Reduce memory peak with streaming lazy collects ([`f9f3d9e`](../../commit/f9f3d9e))
- Handle Windows absolute paths and coerce datetime X for plotting ([`e3b8dde`](../../commit/e3b8dde))

## [v0.2.0] — 2026-02-02

### ✨ Features

- Add Lasso Select and Limit to Marking features ([`165af5a`](../../commit/165af5a))
- Add comprehensive Help menu and improve tooltips ([`50e23da`](../../commit/50e23da))
- Implement CLI, Python API, and REST API Server ([`0943a23`](../../commit/0943a23))
- Add clipboard and drag-drop support ([`fa01852`](../../commit/fa01852))
- Add feature-based UX test suite ([`e915e07`](../../commit/e915e07))
- Add comprehensive UX test suite ([`db3d507`](../../commit/db3d507))
- Add IPC server for external process control ([`68cd359`](../../commit/68cd359))
- Add comprehensive report generation feature ([`4d6e08a`](../../commit/4d6e08a))
- Complete multi-data comparison feature implementation ([`d488034`](../../commit/d488034))
- Implement Multi-Data Comparison feature ([`7359dc7`](../../commit/7359dc7))
- Implement Graph Profiles feature for saving and loading graph configurations ([`6d41976`](../../commit/6d41976))
- Comprehensive performance, memory, and UX improvements ([`8ccee1f`](../../commit/8ccee1f))
- Add Y-axis formula support and categorical axis display ([`2b6b4a5`](../../commit/2b6b4a5))
- Add Views toggle, Excel-style format, preset save/load, and ETL parsing ([`eac7e22`](../../commit/eac7e22))
- Add sliding window navigation for graph X and Y axes ([`b647f22`](../../commit/b647f22))
- Add sampling rate control with algorithm selection and OpenGL acceleration ([`e2e4915`](../../commit/e2e4915))
- Move legend to Chart Options tab, add hover data zone, fix legend options ([`008d052`](../../commit/008d052))
- Implement Spotfire-level graph analysis capabilities (Phase 1-7) ([`88d4572`](../../commit/88d4572))
- Add file info to Overview and optimize table performance ([`0001f57`](../../commit/0001f57))
- Add float functionality and reorder MainGraph sections ([`444c16b`](../../commit/444c16b))
- Enhanced UI with parsing preview, chart options, X Zone, and filter system ([`35d0870`](../../commit/35d0870))
- 다양한 파일 형식 및 구분자 지원 확장 ([`73ed7b6`](../../commit/73ed7b6))

### 🐛 Bug Fixes

- IPC column selection, add live UX test scripts ([`cc7c89a`](../../commit/cc7c89a))
- All 759 tests passing ([`87450b3`](../../commit/87450b3))
- Update tests to match implementation changes ([`eac04e2`](../../commit/eac04e2))
- Fix import paths in test files and type hints in report generators ([`c24201c`](../../commit/c24201c))
- Use RGB tuples for PyQtGraph mkBrush and mkPen instead of hex strings ([`4b52748`](../../commit/4b52748))
- Resolve multiple ultrathink UI bugs ([`3c85015`](../../commit/3c85015))
- Improve ETL binary file detection to prevent corrupted loading ([`3d33c2e`](../../commit/3d33c2e))
- DirectWrite font error on Windows ([`0c8a42f`](../../commit/0c8a42f))
- Distribution table display and hidden column bugs ([`1526bc0`](../../commit/1526bc0))
- Multiple UI improvements and bug fixes ([`f56ac35`](../../commit/f56ac35))
- X-Axis 드롭다운 및 축 제목 수정 ([`b747325`](../../commit/b747325))
- setup.py에 py_modules 추가 (main.py entry point 수정) ([`454d446`](../../commit/454d446))

### ⚡ Performance

- GroupedTableModel 최적화 (Polars groupby 사용) ([`283b82b`](../../commit/283b82b))
- 대용량 데이터 샘플링 적용 (최대 10,000 포인트) ([`2f3030c`](../../commit/2f3030c))

### ♻️ Refactor

- src -> data_graph_studio 패키지 구조 변경 ([`046458c`](../../commit/046458c))

### 📝 Documentation

- Add PRD for External Integration & Interoperability ([`e51b1cd`](../../commit/e51b1cd))
- Add PRD for Multi-Data Comparison feature ([`b46f4ca`](../../commit/b46f4ca))
- Add PRD for Graph Profiles feature ([`305fdb9`](../../commit/305fdb9))
- Add Spotfire-level graph analysis upgrade PRD ([`e61156a`](../../commit/e61156a))
- Add comprehensive CLAUDE.md for AI assistant guidance ([`12f5364`](../../commit/12f5364))

### 🧪 Tests

- Add integration UX tests for CLI, API, Clipboard ([`011244f`](../../commit/011244f))
- Add automated feature test script ([`e020444`](../../commit/e020444))
- 파일 형식 및 구분자 지원 테스트 추가 ([`5af8e09`](../../commit/5af8e09))

### 🔨 Chores

- Add .gitignore for Python project ([`528c967`](../../commit/528c967))

### 📌 Other Changes

- Add setuptools_scm for versioning ([`3247054`](../../commit/3247054))
- Fix deprecation warnings: pl.count->pl.len, how=outer->full, stepMode=True->center ([`f5f9d9a`](../../commit/f5f9d9a))
- Major update: Menu restructure, UI cleanup, Statistics panel, Report features ([`1016869`](../../commit/1016869))
- Initial commit: Data Graph Studio ([`1189926`](../../commit/1189926))
