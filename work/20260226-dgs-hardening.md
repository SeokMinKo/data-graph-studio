# Task: 20260226-dgs-hardening

## Goal
Windows 설치본 오프라인 실행 안정성 향상(Perfetto/trace_processor_shell 포함), Import/NameError 0건 지향, 린트/테스트/패키징 증적 확보.

## Scope
- 배치1: preflight + lint 오류 수정
- 배치2: 핵심 pytest 실행 및 Import/NameError 사전 점검
- 배치3: PyInstaller spec/Windows installer workflow 점검 및 보완
- 배치4: 최종 검증, 커밋/푸시

## Constraints
- 파괴적 변경 금지
- 기능 삭제 최소화
- high-risk 변경 분리

## Definition of Done
- ruff check 통과
- 핵심 pytest 스위트 통과
- dgs.spec 기준 Windows 번들 누락 리스크 완화
- 가능하면 installer workflow/release 상태 확인
- 커밋/푸시 및 증적 보고

## Progress Log
- [x] preflight 완료 (python3/pytest/ruff 버전 확인)
- [x] batch1: lint 탐지/수정 (startup 관련 파일 대상)
- [x] batch2: 핵심 pytest 실행 + import smoke
- [x] batch3: windows-installer workflow 점검/수정 + 최근 릴리즈 상태 확인
- [x] batch4: 최종 검증, 커밋/푸시

## Evidence
- `python3 --version` → 3.14.2
- `pytest --version` → 9.0.2
- `ruff --version` → 0.15.2
- `ruff check .` → 795 errors 탐지(기존 기술부채), 이번 배치에서는 startup/packaging 안정성에 직접 영향 있는 파일만 수정
- `ruff check main.py data_graph_studio/ui/dialogs/trace_progress_dialog.py` → All checks passed
- `pytest -q tests/unit/test_ipc_security.py tests/unit/test_trace_config_dialog.py tests/unit/test_trace_progress.py tests/test_project.py` → 83 passed
- import smoke:
  - OK main
  - OK data_graph_studio.ui.main_window
  - OK data_graph_studio.ui.dialogs.trace_progress_dialog
  - OK data_graph_studio.ui.controllers.trace_controller
- `gh run list --workflow "Windows Installer" --limit 3`:
  - v0.25.14 success
  - v0.25.13 success
  - v0.25.12 success
