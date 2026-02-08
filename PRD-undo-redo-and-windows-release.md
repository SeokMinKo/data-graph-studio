# PRD — Undo/Redo 확대 + Windows 설치형 배포/자동 업데이트

- Project: **Data Graph Studio (DGS)**
- Target Release: **v0.22.x** (implemented: v0.22.0, v0.22.1)
- Owner: 고돌
- Date: 2026-02-09

## 0. Summary

본 PRD는 DGS에서 사용자 체감이 큰 **Undo/Redo 범위 확대**와, 개발자 입장에서 중요한 **Windows 설치형 배포 + 자동 업데이트**를 동시에 달성하기 위한 요구사항/설계/검증 기준을 정의한다.

핵심 목표는 아래 2가지다.

1) 사용자가 데이터 탐색/비교/시각화 과정에서 **실수했을 때 즉시 되돌릴 수 있게** 한다.
2) Windows 사용자에게 **설치형 배포**와 **릴리즈 기반 자동 업데이트 경로**를 제공한다.

---

## 1. Goals / Non-Goals

### Goals

#### G1. Undo/Redo (세션 내)
- 앱 실행 세션 내에서 Undo/Redo를 제공한다.
- 우선순위는 **B → A → C → E → D** 순으로 확대한다.
  - B: Filter/Sort 등 query state
  - A: Dataset add/remove/activate 중 “사용자 체감 큰 것” 우선
  - C: Chart settings / view settings
  - E: Compare mode/datasets selection
  - D: Computed Column (데이터 변형)
- 사용자는 **History Panel(타임라인)**에서 Undo 히스토리를 확인할 수 있다.

#### G2. Windows 설치형 배포
- 태그(v*) 푸시 시, GitHub Actions에서 Windows 설치형 인스톨러(`.exe`)를 만든다.
- 생성된 인스톨러는 GitHub Release에 자동 업로드한다.

#### G3. 자동 업데이트 (Windows)
- 앱은 GitHub Releases 최신 버전을 확인해 업데이트 가능 여부를 알린다.
- 업데이트 시 인스톨러를 다운로드해 실행하는 플로우를 제공한다.

### Non-Goals
- Undo/Redo의 프로젝트 저장/로드 간 **영속성 유지**는 하지 않는다(세션 내만).
- macOS codesign/notarize는 범위에서 제외.
- 델타 패치/백그라운드 무중단 업데이트(진짜 seamless updater)는 범위 밖.

---

## 2. User Stories

### Undo/Redo
- US1) 사용자는 필터를 잘못 걸었을 때 Ctrl+Z로 이전 상태로 돌아가고 싶다.
- US2) 사용자는 정렬을 바꿨다가 원복하고 싶다.
- US3) 사용자는 데이터셋을 비교하다가, 비교 모드/선택을 바꾸고 되돌리고 싶다.
- US4) 사용자는 데이터셋을 삭제했는데 다시 복원하고 싶다(세션 내).
- US5) 사용자는 차트 타입/스타일을 바꿨다가 되돌리고 싶다.
- US6) 사용자는 계산 컬럼을 추가했는데 Undo로 컬럼 추가 전 DF로 돌아가고 싶다.

### 배포/업데이트
- US7) 개발자는 태그만 푸시하면 Windows 설치 파일이 Release에 붙길 원한다.
- US8) 사용자는 앱에서 “업데이트 있음”을 보고 클릭 한 번으로 업데이트를 설치하고 싶다.

---

## 3. Functional Requirements

### 3.1 Undo/Redo Core
- FR-U1: Undo/Redo는 **세션 내**에서만 동작한다.
- FR-U2: Undo 스택은 선형 타임라인이며, 새 동작 push 시 redo 미래가 잘린다.
- FR-U3: Undo/Redo 실행 시 앱 상태가 실제로 변경되어야 한다(기존의 “pop만 하는 Undo” 금지).
- FR-U4: 최대 깊이를 초과하면 가장 오래된 항목이 제거된다.
- FR-U5: 복합 동작(compound)을 지원해 여러 sub-action을 1개의 undo로 묶을 수 있다.

### 3.2 Undo/Redo 범위
- FR-U6 (B): Filter add/remove/toggle/clear가 undoable 해야 한다.
- FR-U7 (B): Sort set/clear가 undoable 해야 한다.
- FR-U8 (C): Chart settings 업데이트(타입/옵션)가 undoable 해야 한다.
- FR-U9 (A): Dataset activate가 undoable 해야 한다.
- FR-U10 (A): Dataset remove가 undoable 해야 한다(세션 내 복원).
- FR-U11 (E): Comparison mode 변경이 undoable 해야 한다.
- FR-U12 (E): Comparison datasets selection 변경이 undoable 해야 한다.
- FR-U13 (D): Computed Column add가 undoable 해야 한다(DF를 이전/이후로 실제 스왑).

### 3.3 History Panel
- FR-H1: History Panel은 dock 패널로 제공된다.
- FR-H2: History Panel은 undo stack 변경 시 자동으로 갱신된다.
- FR-H3: View 메뉴에서 토글 가능해야 한다.

### 3.4 Windows 설치형 배포
- FR-W1: 태그(v*) 푸시 시 Windows CI가 실행된다.
- FR-W2: PyInstaller `dgs.spec` 기반 onedir 빌드를 수행한다.
- FR-W3: Inno Setup으로 `DataGraphStudio-Setup-v{version}.exe`를 생성한다.
- FR-W4: 생성된 exe를 GitHub Release에 업로드한다.

### 3.5 자동 업데이트 (Windows)
- FR-AU1: 앱은 GitHub Release 최신 버전을 조회한다.
- FR-AU2: Release 자산 중 `DataGraphStudio-Setup-*.exe`를 찾아 다운로드 URL을 얻는다.
- FR-AU3: 버전이 더 최신이면 사용자에게 업데이트 여부를 물어본다.
- FR-AU4: 동의 시 인스톨러를 다운로드 후 실행한다.

---

## 4. UX Requirements

- UX1: Ctrl+Z / Ctrl+Shift+Z(또는 StandardKey Redo)로 Undo/Redo가 동작한다.
- UX2: History Panel은 적용된 항목(✓)과 미적용(미래) 항목을 구분해 보여준다.
- UX3: 업데이트는 Windows에서만 보장하며, 타 OS에서는 조용히 no-op.

---

## 5. Technical Design

### 5.1 Undo 모델

기존 `UndoAction(before_state/after_state)`의 한계를 보완하기 위해 **실행 가능한 커맨드 기반**으로 변경한다.

- `UndoCommand { description, do(), undo() }`
- `UndoStack`: 선형 타임라인 + cursor(index)
- 호환성: 기존 테스트/코드가 `UndoAction`을 push하는 경우를 위해 no-op 커맨드로 래핑(이행기)

AppState 내부 변경은 “이미 mutation이 일어난 뒤”인 경우가 많으므로 `push()`가 아니라 `record()`로 기록한다.

### 5.2 적용 전략 (B/A/C/E)
- Filter/Sort/ChartSettings는 `copy.deepcopy` snapshot 방식으로 되돌린다.
- Dataset remove는 엔진의 dataset_info + state snapshot을 저장하여 세션 내 복구한다.
- Compare 설정은 이전 설정 목록을 snapshot으로 저장하여 복원한다.

### 5.3 Computed Column (D)
- Computed column 생성 시 `before_df`/`after_df`를 확보하고, undo 시 이전 DF로 스왑한다.
- UI는 table/graph/options columns를 동기화한다.

### 5.4 Windows 설치형 배포
- GitHub Actions windows-latest:
  - requirements 설치
  - pyinstaller 실행
  - choco로 Inno Setup 설치
  - `.iss` 컴파일 (버전은 태그에서 파생)
  - release 자산 업로드

### 5.5 자동 업데이트
- `https://api.github.com/repos/{owner}/{repo}/releases/latest` 조회
- 설치 파일 asset을 찾아 temp에 다운로드 후 실행

---

## 6. Risks / Edge Cases

- R1: Undo 적용 중 signal 재진입으로 다시 undo 기록이 쌓이는 루프 → `pause()` 가드 필요
- R2: Dataset remove 복원이 메모리를 크게 잡아먹을 수 있음(대형 DF 유지) → 세션 내만, max_depth 제한
- R3: PyInstaller hiddenimports 누락으로 Windows 빌드 실패 가능 → spec 유지보수 필요
- R4: GitHub latest 릴리즈에 installer asset이 없으면 업데이트 불가 → UI 메시지 필요
- R5: 설치 중 앱이 파일 잠금으로 깨질 수 있음 → 설치 실행 후 앱 종료

---

## 7. Acceptance Criteria

- AC1: `pytest` 전체 통과
- AC2: 필터/정렬/차트설정/비교 설정 변경 후 Undo/Redo로 상태가 실제로 되돌아간다.
- AC3: 계산 컬럼 추가 후 Undo하면 DF가 컬럼 추가 전으로 되돌아간다.
- AC4: History Panel에서 타임라인이 보이고, Undo/Redo 시 갱신된다.
- AC5: 태그 push 시 Release에 Windows installer exe가 업로드된다.
- AC6: Windows에서 최신 릴리즈가 더 높으면 업데이트 프롬프트가 뜬다.

---

## 8. Implementation Notes (현재 구현 상태)

- Implemented:
  - Undo/Redo core: `data_graph_studio/core/undo_manager.py`
  - History Panel: `data_graph_studio/ui/panels/history_panel.py`
  - State integration: `data_graph_studio/core/state.py`, dataset controller
  - Windows installer CI: `.github/workflows/windows-installer.yml`
  - Updater: `data_graph_studio/core/updater.py`
  - Computed column undo fix: `MainWindow._on_computed_column_created`

- Releases:
  - v0.22.0: undo 확대 + windows installer + updater
  - v0.22.1: computed column undo/redo DF revert fix
