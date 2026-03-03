# CHANGELOG ↔ Test Index

자동 생성 파일. 버그 수정 이력과 관련 테스트 파일을 키워드 기반으로 매핑한다.

| Version | Bugfix item | Related tests |
|---|---|---|
| ## [v0.23.11] — 2026-02-09 | - **프로젝트 열기(Open Project)가 데이터를 로드하지 않던 버그 수정** — Ctrl+Alt+P로 .dgs 프로젝트를 열 때 프로파일만 복원되고 데이터소스가 로드되지 않던 문제 해결. `file_loading_controller._load_project_file`로 통합하여 데이터 + 프로파일 모두 정상 로드 | `tests/test_project.py`<br>`tests/unit/test_main_graph_event_sequence.py`<br>`tests/unit/test_ipc_profile.py` |
| ## [v0.18.3] — 2026-02-05 | - **프로젝트 저장/로드 버그 수정** — 저장 시 데이터 소스 경로 포함, 로드 시 자동 복원 ([`b05e65f`](../../commit/b05e65f)) | `tests/test_project.py`<br>`tests/unit/test_main_graph_event_sequence.py` |
| ## [v0.15.7] — 2026-02-04 | - Selection/Draw 마우스 드래그 버그 수정 — `mouseReleaseEvent` 중복 정의로 selection/draw 완료 처리가 무시되던 문제 해결 ([`9568bfa`](../../commit/9568bfa)) | `tests/unit/test_main_graph_event_sequence.py`<br>`tests/test_drawing.py`<br>`tests/unit/test_selection_sync.py` |
| ## [v0.15.1] — 2026-02-04 | - 세션 복원 시 프로파일이 프로젝트 탐색창에 표시되지 않는 버그 수정 — autosave에 프로파일 데이터 저장/복원 추가 ([`autosave-profiles`](../../commit/HEAD)) | `tests/test_project.py`<br>`tests/unit/test_main_graph_event_sequence.py`<br>`tests/unit/test_ipc_profile.py` |
| ## [v0.13.1] — 2026-02-04 | - 프로파일 독립성 버그 수정 + 트리 expand 상태 보존 ([`5d424bb`](../../commit/5d424bb)) | `tests/test_project.py`<br>`tests/unit/test_ipc_profile.py` |
| ## [v0.12.9] — 2026-02-03 | - GroupBy multi-select checkboxes, search filters, dual aggregation, fix input heights ([`43d54e0`](../../commit/43d54e0)) | (manual mapping needed) |
| ## [v0.11.7] — 2026-02-03 | - 프로젝트 탐색창 3가지 버그 수정 ([`76a2db9`](../../commit/76a2db9)) | `tests/test_project.py`<br>`tests/unit/test_main_graph_event_sequence.py` |
| ## [v0.10.1] — 2026-02-03 | - 파일 로딩 후 프로젝트 탐색창에 데이터셋 표시되지 않던 버그 수정 ([`e00aeff`](../../commit/e00aeff)) | `tests/test_project.py`<br>`tests/unit/test_main_graph_event_sequence.py` |
| ## [v0.9.8] — 2026-02-03 | - Fix Zone chip layout alignment and sizing ([`1db1628`](../../commit/1db1628)) | (manual mapping needed) |
| ## [v0.9.4] — 2026-02-03 | - Comprehensive theme color fixes ([`1060fac`](../../commit/1060fac)) | (manual mapping needed) |
| ## [v0.9.0] — 2026-02-03 | - Light theme + bug fixes ([`3567bd4`](../../commit/3567bd4)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix: Improve drag-and-drop from table header and clean up context menu ([`d96d6d6`](../../commit/d96d6d6)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix readability: change light backgrounds to dark theme colors ([`75415c7`](../../commit/75415c7)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix text readability: change dark text colors to light (#E6E9EF, #C2C8D1) ([`337980f`](../../commit/337980f)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix: Enable X/Y-Axis Navigator checkboxes by default ([`cfdeca5`](../../commit/cfdeca5)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix: Change Chart Options and Legend header color to white (#E6E9EF) ([`64bcbe1`](../../commit/64bcbe1)) | (manual mapping needed) |
| ## [v0.8.0] — 2026-02-03 | - Fix: reorder setup calls - main_layout before toolbar ([`4981c20`](../../commit/4981c20)) | (manual mapping needed) |
| ## [v0.7.0] — 2026-02-02 | - Fix QA issues: mapper dataset_id, model icon, controller unsaved, view delete ([`71bd5d2`](../../commit/71bd5d2)) | (manual mapping needed) |
| ## [v0.4.8] — 2026-02-02 | - Fix sliding window toggles ([`387c64b`](../../commit/387c64b)) | (manual mapping needed) |
| ## [v0.4.6] — 2026-02-02 | - Fix chart options (log/reverse/smooth/labels/points) ([`36a950d`](../../commit/36a950d)) | (manual mapping needed) |
| ## [v0.4.5] — 2026-02-02 | - Fix Y sliding window orientation mapping ([`8a62d38`](../../commit/8a62d38)) | (manual mapping needed) |
| ## [v0.4.4] — 2026-02-02 | - Fix column selection checkbox contrast ([`9b1d323`](../../commit/9b1d323)) | `tests/unit/test_main_graph_event_sequence.py`<br>`tests/test_drawing.py`<br>`tests/unit/test_selection_sync.py` |
| ## [v0.4.3] — 2026-02-02 | - Fix menu hover contrast and drawing visibility/pen width ([`627c5f8`](../../commit/627c5f8)) | `tests/unit/test_main_graph_event_sequence.py`<br>`tests/test_drawing.py`<br>`tests/unit/test_selection_sync.py` |
| ## [v0.3.8] — 2026-02-02 | - Fix table context menu contrast and persist dataset state ([`5d7b2d4`](../../commit/5d7b2d4)) | (manual mapping needed) |
| ## [v0.3.6] — 2026-02-02 | - Fix missing Any import ([`36ebe29`](../../commit/36ebe29)) | (manual mapping needed) |
| ## [v0.3.4] — 2026-02-02 | - Fix toolbar clear and chart type sync ([`0331dc2`](../../commit/0331dc2)) | (manual mapping needed) |
| ## [v0.2.7] — 2026-02-02 | - Fix windowed index length and add multi-file dataset load ([`557bea2`](../../commit/557bea2)) | (manual mapping needed) |
| ## [v0.2.6] — 2026-02-02 | - Fix stats pie chart, aggregation sync, floating actions, drawing UX ([`b99cc23`](../../commit/b99cc23)) | `tests/unit/test_main_graph_event_sequence.py`<br>`tests/test_drawing.py`<br>`tests/unit/test_selection_sync.py` |
| ## [v0.2.4] — 2026-02-02 | - Fix Overview card background for dark theme ([`7c28076`](../../commit/7c28076)) | (manual mapping needed) |
| ## [v0.2.1] — 2026-02-02 | - Apply minimal modern grayscale theme and fix table text contrast ([`e77c36f`](../../commit/e77c36f)) | (manual mapping needed) |
| ## [v0.2.0] — 2026-02-02 | - Move legend to Chart Options tab, add hover data zone, fix legend options ([`008d052`](../../commit/008d052)) | (manual mapping needed) |
| ## [v0.2.0] — 2026-02-02 | - Fix import paths in test files and type hints in report generators ([`c24201c`](../../commit/c24201c)) | (manual mapping needed) |
| ## [v0.2.0] — 2026-02-02 | - Multiple UI improvements and bug fixes ([`f56ac35`](../../commit/f56ac35)) | (manual mapping needed) |
| ## [v0.2.0] — 2026-02-02 | - Fix deprecation warnings: pl.count->pl.len, how=outer->full, stepMode=True->center ([`f5f9d9a`](../../commit/f5f9d9a)) | (manual mapping needed) |
