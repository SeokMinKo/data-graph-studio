# Code Review: Project Explorer / Tree Navigation

**Date**: 2026-02-19  
**Scope**: 7 files — tree view, profile model, property panel, dataset manager panel, profile UI controller, dataset controller, profile domain model  
**Total LOC**: ~3,450

---

## Executive Summary

Project Explorer는 2-level tree (datasets → profiles)를 기반으로 한 탐색/관리 시스템. frozen dataclass + `dataclasses.replace` 패턴, incremental model updates, macOS accessibility crash workaround 등 좋은 설계 판단이 보임. 그러나 **God object 의존**, **중복 트리 구현**, **store 접근 방어 코드 과다**, **컨트롤러 간 결합** 등 구조적 문제가 존재.

---

## Architecture Overview

```
ProjectTreeView ──→ ProfileFilterProxy ──→ ProfileModel
       │                                      │
       │ (signals)                    store + state (duck-typed)
       ▼                                      │
ProfileUIController ──→ MainWindow ──→ ProfileController
       │                                      │
       ▼                                      ▼
DatasetController ──→ MainWindow ──→ DataEngine + AppState
       │
       ▼
DatasetManagerPanel (독립 트리 구현)
```

---

## P0 — Critical Issues

### 1. 두 개의 독립적 트리 구현 (Duplicated Tree)

**파일**: `dataset_manager_panel.py` (`_update_tree`) vs `project_tree_view.py` + `profile_model.py`

`DatasetManagerPanel._update_tree()`는 `QTreeWidget`으로 **자체 트리를 직접 구축**. 동시에 `ProjectTreeView` + `ProfileModel`이 `QAbstractItemModel` 기반으로 동일 데이터의 또 다른 트리를 관리.

**문제점**:
- 동일 데이터(datasets → profiles)를 두 곳에서 별도 렌더링
- 동기화 버그 위험 (한쪽만 업데이트되는 경우)
- context menu, rename, delete 로직 양쪽에 중복
- `DatasetManagerPanel`의 트리는 incremental update 없이 매번 `clear() + rebuild`

**수정안**:
```python
# DatasetManagerPanel이 ProjectTreeView/ProfileModel을 재사용하도록 리팩토링
# 또는 DatasetManagerPanel의 트리를 제거하고 ProjectTreeView를 embed
class DatasetManagerPanel(QWidget):
    def __init__(self, engine, state, profile_model: ProfileModel, parent=None):
        ...
        self.tree_view = ProjectTreeView(self)
        self.tree_view.set_model(profile_model)
```

### 2. ProfileUIController = God Object Proxy

**파일**: `profile_ui_controller.py` (624L)

`ProfileUIController`는 `self._w` (MainWindow)를 통해 **거의 모든 것에 접근**: `profile_store`, `profile_model`, `graph_panel`, `engine`, `state`, `_undo_stack`, `profile_controller`, `profile_comparison_controller`, `_file_controller`, `_floating_graph_manager`, `_compare_toolbar`, `statusbar`, `summary_panel`, `table_panel` 등.

**문제점**:
- MainWindow의 모든 internal을 알아야 함 → 변경 시 깨짐
- 테스트 불가능 (MainWindow mock이 거대)
- `_w.profile_controller` vs `ProfileUIController` 역할 경계 모호

**수정안**: 필요한 의존성만 생성자에서 주입
```python
class ProfileUIController:
    def __init__(
        self,
        profile_store: ProfileStore,
        profile_model: ProfileModel,
        profile_controller: ProfileController,
        state: AppState,
        statusbar: QStatusBar,
    ):
        ...
```

### 3. DatasetController도 동일한 God Object Proxy

**파일**: `dataset_controller.py` (768L)

`DatasetController`도 `self._w`를 통해 MainWindow 전체에 접근. 특히 `_on_dataset_loading_finished`에서 `w.engine`, `w.state`, `w.profile_model`, `w._pending_*` 등에 직접 접근.

**수정안**: 동일하게 DI 패턴 적용. `_pending_*` 상태는 controller 자체가 소유.

---

## P1 — Significant Issues

### 4. ProfileModel의 duck-typing 방어 코드 과다

**파일**: `profile_model.py` — `_get_dataset_ids()`, `_get_profiles()`, `_get_dataset_name()`

```python
def _get_profiles(self, dataset_id):
    if hasattr(self._store, "get_by_dataset"):
        ...
    elif hasattr(self._store, "get_profiles"):
        ...
    elif hasattr(self._store, "get_settings"):
        ...
    elif isinstance(self._store, dict):
        ...
    elif hasattr(self._store, "profiles_by_dataset"):
        ...
```

5개의 `hasattr` 분기 = store 인터페이스가 정의되지 않았다는 증거.

**수정안**: Protocol 또는 ABC 정의
```python
from typing import Protocol

class ProfileStoreProtocol(Protocol):
    def get_by_dataset(self, dataset_id: str) -> List[GraphSetting]: ...
    def get(self, profile_id: str) -> Optional[GraphSetting]: ...
    def add(self, setting: GraphSetting) -> None: ...
    def update(self, setting: GraphSetting) -> None: ...
    def reorder(self, dataset_id: str, ids: List[str]) -> None: ...
```

### 5. DatasetManagerPanel 내 하드코딩된 스타일시트

**파일**: `dataset_manager_panel.py`

```python
title.setStyleSheet("font-size: 14px; font-weight: bold; color: #F2F4F8;")
self.tree.setStyleSheet("""
    QTreeWidget { background: #111827; color: #E2E8F0; ... }
""")
self.add_btn.setStyleSheet("""
    QPushButton { background-color: #4CAF50; color: white; ... }
""")
```

다크 테마 색상이 하드코딩 → 라이트 테마에서 깨짐. 앱에 `_theme_manager`가 있는데 이 패널은 무시.

**수정안**: QSS 파일 또는 `apply_theme(is_light)` 메서드 추가, objectName 기반 스타일링.

### 6. remove_profile_incremental의 O(n²) 탐색

**파일**: `profile_model.py` L215-240

```python
for i, node in enumerate(self._nodes):
    if (...):
        for n in self._nodes:  # 내부 루프 다시 전체 순회
            if n.dataset_id == dataset_id and n.setting is not None:
                if n.setting.id == profile_id:
                    row = row_count
                    break
                row_count += 1
```

이중 루프로 노드 리스트 전체를 2번 순회. 프로파일 수가 많으면 성능 저하.

**수정안**: 단일 패스로 row 계산
```python
def remove_profile_incremental(self, dataset_id, profile_id):
    row = 0
    target_idx = -1
    for i, node in enumerate(self._nodes):
        if node.dataset_id == dataset_id and node.setting is not None:
            if node.setting.id == profile_id:
                target_idx = i
                break
            row += 1
    if target_idx < 0:
        self.refresh()
        return
    # ... beginRemoveRows with row
```

### 7. _on_dataset_loading_finished 내 pending state가 MainWindow에 분산

**파일**: `dataset_controller.py` L141-143

```python
w._pending_dataset_id = dataset_id
w._pending_dataset_name = name
w._pending_dataset_path = file_path
```

loading 상태가 MainWindow attribute로 저장 → 동시 로딩 시 덮어쓰기 위험, 코드 추적 어려움.

**수정안**: `@dataclass` 로 `_PendingLoad` 캡슐화, DatasetController 내부 관리
```python
@dataclass
class _PendingLoad:
    dataset_id: str
    name: str
    file_path: str

class DatasetController:
    def __init__(self, ...):
        self._pending: Optional[_PendingLoad] = None
```

### 8. _save_project_to의 중복 프로파일 수집 로직

**파일**: `profile_ui_controller.py` L489-502 & L445-458

프로파일 수집 + 중복 제거 코드가 `_on_save_profile_bundle_as`와 `_save_project_to`에서 **거의 동일하게** 반복.

**수정안**: 헬퍼 메서드 추출
```python
def _collect_all_profiles(self) -> List[dict]:
    """모든 프로파일을 중복 없이 수집"""
    ...
```

### 9. PropertyPanel이 Qt와 분리되어 있지만 쓸모 제한적

**파일**: `property_panel.py`

`PropertyPanel` 클래스는 순수 Python (Qt 불필요), `PropertyPanelWidget`은 Qt 위젯. 그러나:
- `PropertyPanelWidget`이 `_model._groups`에 직접 접근 (캡슐화 위반)
- `PropertyType.NUMBER/INTEGER` 등에 대한 에디터 위젯이 미구현 (text 폴백만)
- `_on_item_changed`에서 타입 변환 없음 (문자열 그대로 저장)

**수정안**: 
- `PropertyPanel.groups` property 추가 (읽기 전용)
- 타입별 에디터 위젯 팩토리 구현
- `_on_item_changed`에서 타입 캐스팅

### 10. GraphSetting.chart_settings의 MappingProxyType 비일관성

**파일**: `profile.py`

`__post_init__`에서 `MappingProxyType`으로 래핑하지만, `to_dict()`에서 `dict()`로 풀고, `from_dict()`에서 plain dict를 전달 → `__post_init__`에서 다시 래핑. 작동은 하지만:
- `normalized_chart_settings()`가 매번 새 dict 생성
- nested dict (chart_settings 안의 dict)는 여전히 mutable

**수정안**: deep freeze 유틸리티 또는 plain dict + `__eq__` override로 단순화.

---

## P2 — Minor / Enhancement

### 11. ProfileManager가 사용되지 않는 것으로 보임

**파일**: `profile.py` L280-444

`ProfileManager` 클래스는 `ProfileStore`와 역할 중복. 7개 파일 내에서 참조 없음. Dead code일 가능성 높음.

**수정안**: 사용처 확인 후 제거 또는 `ProfileStore`와 통합.

### 12. ProjectTreeView의 signal 과다

**파일**: `project_tree_view.py` — 12개 signal 선언

`profile_activated`, `profile_selected`, `project_activated`, `new_profile_requested`, `rename_requested`, `delete_requested`, `duplicate_requested`, `export_requested`, `import_requested`, `compare_requested`, `copy_to_dataset_requested`, `favorite_toggled`

View가 12개 signal을 방출 → 연결 코드가 MainWindow 어딘가에 12줄 이상.

**수정안**: Command 패턴으로 묶기
```python
class TreeAction(Enum):
    APPLY = "apply"
    RENAME = "rename"
    DELETE = "delete"
    ...

# Signal: action_requested = Signal(TreeAction, str)  # action, target_id
```

### 13. DatasetItemWidget.mouseDoubleClickEvent가 state를 직접 변경

**파일**: `dataset_manager_panel.py` L175-181

더블클릭으로 이름 변경 시 `self.name_label.setText(new_name)`만 호출하고 **state/engine에 반영하지 않음**. UI만 바뀌고 실제 데이터는 그대로.

**수정안**: `renamed` signal 추가 → 컨트롤러에서 `state.rename_dataset()` 호출

### 14. _chart_type_icon 매핑이 ProfileModel에 존재

**파일**: `profile_model.py` L286-294

아이콘 매핑이 모델 레이어에 있음 → 표현 로직이 데이터 모델에 침투.

**수정안**: `_ChartIconDelegate` 또는 별도 유틸리티로 이동

### 15. Profile.check_compatibility의 group_columns 접근 방식

**파일**: `profile.py` L367-370

```python
for gc in setting.group_columns:
    if 'name' in gc:  # dict 가정
```

`group_columns`가 dict일 때만 작동. string일 수도 있는데 (코드 다른 곳에서 혼용) 처리 없음.

**수정안**: 타입 체크 추가
```python
name = gc['name'] if isinstance(gc, dict) else str(gc)
```

### 16. DatasetController._on_dataset_remove_requested의 과도한 복잡도

**파일**: `dataset_controller.py` L215-300

85줄짜리 메서드. undo 캡처, 메모리 판단, snapshot, restore 로직이 한 메서드에 집중.

**수정안**: `_capture_dataset_snapshot()`, `_restore_dataset()` 헬퍼로 분리

### 17. 테마 판정 코드 반복

**파일**: `dataset_controller.py` — 4회 반복

```python
is_light = bool(getattr(getattr(w, '_theme_manager', None), 'current_theme', None).is_light()) if hasattr(getattr(w, '_theme_manager', None), 'current_theme') else False
```

동일한 한 줄이 4번 반복. 읽기 어렵고 에러 프론.

**수정안**: MainWindow에 `is_light_theme` property 추가
```python
@property
def is_light_theme(self) -> bool:
    tm = getattr(self, '_theme_manager', None)
    if tm and hasattr(tm, 'current_theme'):
        return tm.current_theme.is_light()
    return False
```

---

## Test Coverage Recommendations

| 파일 | 현재 | 권장 |
|------|------|------|
| `profile.py` (GraphSetting/Profile) | `test_profile_model.py` 존재 | ✅ migration, from_dict round-trip, check_compatibility edge cases |
| `profile_model.py` (ProfileModel) | 부분 | ⚠️ incremental add/remove/update, stale pointer, empty model |
| `project_tree_view.py` | 없음 | ❌ keyPressEvent, context menu, filter proxy |
| `property_panel.py` | 없음 | ❌ CRUD, reset_to_defaults, type conversion |
| `dataset_manager_panel.py` | 없음 | ❌ widget lifecycle, tree sync |
| `profile_ui_controller.py` | 없음 | ❌ 최소한 signal routing 테스트 |
| `dataset_controller.py` | 없음 | ❌ undo/redo, loading flow |

**우선 테스트 대상**:
1. `ProfileModel` incremental ops (add/remove/update) — 트리 상태 보존 검증
2. `GraphSetting` round-trip (to_dict ↔ from_dict) + MappingProxyType 무결성
3. `DatasetController._on_dataset_remove_requested` undo/redo 흐름

---

## Summary Table

| # | Priority | Issue | File(s) | Effort |
|---|----------|-------|---------|--------|
| 1 | **P0** | 중복 트리 구현 | dataset_manager_panel + project_tree_view | L |
| 2 | **P0** | ProfileUIController God object proxy | profile_ui_controller | L |
| 3 | **P0** | DatasetController God object proxy | dataset_controller | L |
| 4 | P1 | Store duck-typing 방어 코드 과다 | profile_model | M |
| 5 | P1 | 하드코딩 스타일시트 | dataset_manager_panel | M |
| 6 | P1 | remove_profile_incremental O(n²) | profile_model | S |
| 7 | P1 | pending state 분산 | dataset_controller | S |
| 8 | P1 | 프로파일 수집 중복 | profile_ui_controller | S |
| 9 | P1 | PropertyPanel 타입 에디터 미구현 | property_panel | M |
| 10 | P1 | MappingProxyType 비일관성 | profile.py | S |
| 11 | P2 | ProfileManager dead code 의심 | profile.py | S |
| 12 | P2 | Signal 과다 (12개) | project_tree_view | M |
| 13 | P2 | mouseDoubleClick state 미반영 | dataset_manager_panel | S |
| 14 | P2 | 아이콘 매핑 위치 | profile_model | S |
| 15 | P2 | check_compatibility 타입 혼용 | profile.py | S |
| 16 | P2 | remove 메서드 과도한 복잡도 | dataset_controller | M |
| 17 | P2 | 테마 판정 코드 반복 | dataset_controller | S |

**Effort**: S = < 1h, M = 1-4h, L = 4h+

---

## Positive Patterns Worth Keeping

1. **`_SafeAccessibleTreeView`** — macOS accessibility crash를 깔끔하게 우회
2. **frozen dataclass + `dataclasses.replace`** — 불변성 보장, 실수 방지
3. **incremental model updates** (`add_profile_incremental`, `remove_profile_incremental`, `update_profile_data`) — 트리 expand 상태 보존
4. **`_find_node` 캐시** — PySide6 GC로 인한 dangling pointer 방지
5. **`ProfileFilterProxy.setRecursiveFilteringEnabled(True)`** — 자식 매치 시 부모도 표시
6. **GraphSetting.`_migrate()` 패턴** — forward-compatible 스키마 마이그레이션
7. **Undo 가능한 dataset 제거** — 대용량 데이터셋은 reload-based undo로 메모리 절약
