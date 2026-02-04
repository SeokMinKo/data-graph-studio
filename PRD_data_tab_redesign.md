# PRD: Data Tab UI Redesign

## Overview
Chart Options > Data 탭의 UI를 리디자인한다. 체크박스 기반 UI를 **Search + ListBox** 패턴으로 교체하고, 섹션 순서를 변경한다.

## Current State
- 파일: `data_graph_studio/ui/panels/data_tab.py` (class `DataTab`)
- 현재 순서: X-Axis → Y-Axis → Group By (+ Agg1, Agg2) → Hover → Filter
- Y-Axis: 모든 숫자 컬럼을 체크박스로 나열, 체크하면 선택
- Group By: 모든 컬럼을 체크박스로 나열
- Hover: 모든 컬럼을 체크박스로 나열
- Filter: 컬럼 선택 콤보 → 값 체크박스 리스트

## Requirements

### 1. 섹션 순서 변경
**새 순서 (위→아래):**
1. Filter
2. Group By
3. X-Axis (축)
4. Y-Axis Values
5. Hover

각 섹션 사이에 구분선(separator) 유지.

### 2. Y-Axis / Group By / Hover — 체크박스 → Search + ListBox

**기존 방식 (제거):**
- 모든 컬럼을 체크박스 목록으로 나열
- 체크로 선택/해제

**새 방식:**
각 섹션에 동일한 패턴 적용:

```
┌─ Section Header (e.g. "Y-Axis (Values)")  [None] ─┐
│ 🔍 Search columns...                              │
│ ┌─────────────────────────────────────────────┐   │
│ │ price                                   [×] │   │
│ │ volume                                  [×] │   │
│ │ temperature                             [×] │   │
│ └─────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

동작:
- **Search columns** (QLineEdit): 타이핑하면 드롭다운/자동완성으로 컬럼 후보 표시
  - QComboBox(editable=True)를 사용. 타이핑하면 필터링되는 방식.
  - 컬럼을 선택(Enter 또는 클릭)하면 → 아래 ListBox에 추가
  - 이미 추가된 컬럼은 드롭다운에서 회색 처리 or 제외
- **ListBox**: 선택된 컬럼들이 표시됨
  - 각 항목 오른쪽에 **[×]** 버튼 → 클릭 시 해당 항목 제거
  - 빈 상태에서는 "(none)" 또는 빈 상태 표시
- **[None] 버튼**: 기존처럼 모든 항목 제거 (초기화)

**Y-Axis 특수사항:**
- 숫자 컬럼만 후보로 표시 (기존과 동일)
- 각 항목에 **f(y) 토글** 기존처럼 유지 (항목 클릭하면 수식 입력 펼침)

**Group By 특수사항:**
- 모든 컬럼 후보

**Hover 특수사항:**
- 모든 컬럼 후보

### 3. Group By에서 Aggregation 제거
- 현재 Data 탭의 Agg 1, Agg 2 콤보박스를 **제거**
- Aggregation은 데이터 테이블(하단 테이블 패널)에 이미 있는 Agg 컨트롤로 대체
- `_agg_combo`, `_agg_combo_2` 위젯 제거
- **주의**: `_on_global_agg_changed`, `_on_global_agg2_changed` 핸들러도 제거
- **주의**: `get_chart_options()`에서 agg 관련 반환값은 다른 곳(테이블 패널)에서 제공하므로, 그래프 패널에서 agg 값을 가져오는 기존 코드가 테이블 패널의 agg를 참조하도록 해야 함. 또는 Agg state가 AppState에 이미 있으면 그걸 사용.

### 4. Filter 섹션 리디자인

**기존 방식:**
- 컬럼 선택 콤보 → 해당 컬럼의 모든 unique 값을 체크박스로 나열

**새 방식:**
```
┌─ Filter  [Clear] ─────────────────────────────────┐
│ 🔍 Search columns...  (컬럼 선택)                  │
│ 🔍 Search values...   (값 검색, 선택하면 ListBox에)│
│ [All] [None]                                       │
│ ┌─────────────────────────────────────────────┐   │
│ │ category = "Electronics"                [×] │   │
│ │ category = "Food"                       [×] │   │
│ │ region = "Seoul"                        [×] │   │
│ └─────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────┘
```

동작:
- **Search columns** (QComboBox editable): 컬럼 선택
- **Search values** (QComboBox editable): 선택된 컬럼의 unique 값을 검색. 타이핑하면 필터링.
  - 값을 선택(Enter/클릭)하면 → 아래 ListBox에 `"column = value"` 형태로 추가
  - 이미 추가된 값은 드롭다운에서 제외 or 회색
- **ListBox**: 선택된 필터 항목들
  - 각 항목에 [×] 버튼 → 제거
  - 여러 컬럼의 값을 동시에 필터 가능 (multi-column filter)
- **[All] 버튼**: 현재 선택된 컬럼의 모든 값을 ListBox에 추가
- **[None] 버튼**: ListBox 전체 비움 (필터 해제)
- `filter_changed` 시그널: `{column: [selected_values]}` dict emit (기존과 동일한 인터페이스)

### 5. X-Axis
- 기존 QComboBox(editable, searchable) 유지 — 변경 없음

## Technical Notes

### 파일 수정 범위
- **주 파일**: `data_graph_studio/ui/panels/data_tab.py`
  - `DataTab._setup_ui()` 전면 재작성
  - `_YAxisItemWidget` — f(y) 토글 기능은 유지하되, ListBox 아이템 위젯으로 변경
  - 체크박스 관련 메서드 → ListBox 관련 메서드로 교체
  - Agg 관련 위젯/핸들러 제거
- **그래프 패널**: `data_graph_studio/ui/panels/graph_panel.py`
  - `OptionsPanel`이 `DataTab`을 사용하는 부분 — 인터페이스 변경 없으면 수정 불필요
  - Agg 값 참조 방식 확인 필요
- **테스트**: `tests/` — DataTab 관련 테스트 수정

### 위젯 설계

**`_ColumnListBox` (신규 위젯)**:
- QWidget with QVBoxLayout
- 각 항목: QHBoxLayout[QLabel(column_name), QPushButton("×")]
- 최대 높이 제한 (QScrollArea 내부)
- `item_added(str)`, `item_removed(str)` 시그널

**`_SearchableColumnPicker` (신규 위젯)**:
- QComboBox(editable=True, insertPolicy=NoInsert)
- setCompleter with QStringListModel for filtering
- 선택 시 `column_selected(str)` 시그널 emit
- 선택 후 텍스트 클리어

### AppState 인터페이스 (변경 없음)
- `state.add_value_column(name)` / `state.remove_value_column(index)`
- `state.add_group_column(name)` / `state.remove_group_column(name)`
- `state.add_hover_column(name)` / `state.remove_hover_column(name)`
- `state.set_x_column(name)`

### 시그널 인터페이스 (변경 없음)
- `DataTab.filter_changed` — `Dict[str, List[Any]]`
- `OptionsPanel.option_changed` — 기존 유지

## Constraints
- 기존 AppState 인터페이스 유지 (breaking change 없음)
- 기존 테스트 최대한 유지, 필요하면 수정
- Dark theme 호환 (기존 스타일시트 활용)
- 컬럼 수가 많을 때 (100+) 성능 고려 — Search/Completer 사용
