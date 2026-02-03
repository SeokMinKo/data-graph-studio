# PRD: Single-Dataset Multi-Profile Comparison (v2)

## 1. 목표
하나의 CSV(데이터셋) 내에서 여러 프로파일(GraphSetting)을 동시에 비교할 수 있는 기능 구현. Side-by-Side, Overlay, Difference 세 가지 비교 모드 지원.

## 2. 배경
현재 비교 기능은 **다른 CSV 파일(데이터셋) 간** 비교만 지원. 같은 CSV에서 다른 그래프 설정(예: X=time,Y=voltage vs X=time,Y=current)을 동시에 보는 기능이 없음. 기존 `ComparisonMode`, `SideBySideLayout` 인프라를 **확장**하여 프로파일 단위 비교 추가.

### 현재 구조
- `ComparisonMode`: SINGLE, OVERLAY, SIDE_BY_SIDE, DIFFERENCE
- `ComparisonSettings`: sync_scroll, sync_zoom, sync_pan_x, sync_pan_y, sync_selection
- `SideBySideLayout` → `MiniGraphWidget`: 데이터셋 단위, 내부에 뷰 동기화 로직 있음
- `ProfileStore` / `ProfileController`: 프로파일 CRUD, dataset_id에 종속
- `AppState`: comparison_mode_changed, comparison_settings_changed 시그널

## 3. 요구사항

### 3.1 기능 요구사항
- [ ] FR-1: 같은 데이터셋의 여러 프로파일을 선택하여 비교 모드 진입 (Profile Bar에서 Ctrl+Click 또는 Compare Mode 토글)
- [ ] FR-2: **Side-by-Side** — 어떤 프로파일 조합에서든 작동. 각 프로파일이 독립 패널로 표시
- [ ] FR-3: **Overlay** — X축이 동일한(= 같은 `x_column` 이름) 프로파일끼리만 가능. 하나의 차트에 여러 Y축 계열 겹침
- [ ] FR-4: **Difference** — X축이 동일한(= 같은 `x_column` 이름) 2개 프로파일만 가능. `Y_A - Y_B` 차이값 계산/표시 (같은 DataFrame이므로 행 인덱스 완벽 일치)
- [ ] FR-5: **Zoom/Move 동기화** — X축 동기화, Y축 동기화를 개별 토글 가능
- [ ] FR-6: **Selection 동기화** — 한 패널에서 데이터 포인트 선택 시 다른 패널에서도 같은 행 하이라이트
- [ ] FR-7: Overlay/Difference 시 X축 불일치 프로파일 선택하면 해당 모드 비활성화 + 툴팁 설명
- [ ] FR-8: **데이터셋 비교와 프로파일 비교는 상호 배타적**. 한 번에 하나만 활성. 프로파일 비교 진입 시 데이터셋 비교 자동 해제, 역도 동일
- [ ] FR-9: **비교 모드 종료** — 비교 레이아웃 헤더의 "✕ Exit" 버튼, Esc키, 또는 Profile Bar에서 단일 프로파일 클릭 시 단일 뷰로 복귀
- [ ] FR-10: **비교 중 프로파일 변경 대응**
  - 삭제: 해당 패널 제거, 1개만 남으면 자동으로 비교 모드 종료
  - 이름 변경: 패널 헤더 갱신
  - 설정 수정(차트 타입, 컬럼 변경): 해당 패널 리렌더. Overlay/Difference에서 X축이 달라지면 경고 후 Side-by-Side로 자동 전환
- [ ] FR-11: Overlay에서 chart_type이 다른 프로파일 혼합 시 모두 line으로 통일 렌더링 (경고 표시)

### 3.2 비기능 요구사항
- [ ] NFR-1: Side-by-Side 최대 4개 프로파일 동시 표시, 각 패널 렌더링 < 500ms
- [ ] NFR-2: Overlay 최대 8개 계열, 100k 행 기준 렌더링 < 1초 (다운샘플링 적용)
- [ ] NFR-3: 동기화 이벤트 지연 < 50ms (throttle 방식: 최대 50ms 간격 1회 fire)
- [ ] NFR-4: 추가 메모리 사용량: 프로파일당 데이터 복사 없음 (동일 DataFrame 참조). 4프로파일 비교 시 추가 < 50MB
- [ ] NFR-5: 기존 단일 데이터셋/데이터셋 간 비교 기능 회귀 없음 (기존 test_multi_dataset.py, test_integration.py 전체 통과)

## 4. 범위

### 포함
- `ComparisonSettings` 확장 (`comparison_target` 필드 추가)
- `ViewSyncManager` — 기존 `SideBySideLayout`의 동기화 로직을 **추출**하여 공용 매니저로 분리. 기존 데이터셋 비교와 새 프로파일 비교 모두 이 매니저 사용
- `MiniGraphWidget` 확장 — optional `GraphSetting` 파라미터 추가. 있으면 해당 설정으로 렌더, 없으면 기존 동작
- `ProfileSideBySideLayout` — `SideBySideLayout` 상속/확장, 프로파일 ID 기반 패널 생성
- `ProfileOverlayRenderer` — 프로파일 기반 오버레이
- `ProfileDifferenceRenderer` — 프로파일 기반 차이 분석
- `ProfileComparisonController` — `ProfileController`와 협력 (ProfileController의 시그널 구독)
- UI: 프로파일 비교 진입/종료 UX

### 제외
- 다른 데이터셋의 프로파일 간 교차 비교
- 3D 차트 비교
- 비교 상태 저장/복원 (향후 기능)
- 프로파일 비교 undo/redo

## 5. UI/UX 상세

### 5.1 비교 진입
1. Profile Bar에서 2개 이상 프로파일 선택 (Ctrl+Click)
   - Compare Mode 토글 버튼으로 "선택 모드" 진입하면 체크박스 표시
2. 선택 후 → 비교 모드 선택 다이얼로그:
   - Side-by-Side: 항상 활성
   - Overlay: X축 동일 조건 충족 시만 활성. 미충족 시 비활성 + 툴팁 "All profiles must share the same X column"
   - Difference: X축 동일 + 정확히 2개 선택 시만 활성. 미충족 시 비활성 + 툴팁
3. 1개만 선택된 상태에서 비교 시도 → 버튼 비활성화, 툴팁 "Select 2+ profiles to compare"

### 5.2 비교 종료
- 비교 레이아웃 헤더 우측 "✕ Exit Comparison" 버튼
- Esc 키
- Profile Bar에서 단일 프로파일 더블클릭
- 데이터셋 비교 모드 진입 시 자동 종료
→ 모두 `ComparisonMode.SINGLE`로 전환 + 이전 활성 프로파일 적용

### 5.3 Side-by-Side 레이아웃
```
┌──────────────────────────────────────────────────────┐
│ Profile Comparison (Side-by-Side)           [✕ Exit] │
│ [Sync: ☑X축  ☐Y축  ☑Selection]          [Reset All] │
├─────────────────────┬────────────────────────────────┤
│  Profile A (blue)   │  Profile B (orange)            │
│  Line / time→volt   │  Bar / time→current            │
│  ┌───────────────┐  │  ┌───────────────┐             │
│  │   chart_A     │  │  │   chart_B     │             │
│  └───────────────┘  │  └───────────────┘             │
│  μ:3.2 σ:0.8       │  μ:12.5 σ:2.1                  │
└─────────────────────┴────────────────────────────────┘
```
- 3~4 패널 시 수평 스플리터. 화면 폭이 좁으면 (패널 < 200px) 2×2 그리드로 자동 전환

### 5.4 Overlay 레이아웃
```
┌──────────────────────────────────────────────────────┐
│ Profile Comparison (Overlay)  X: time       [✕ Exit] │
├──────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────┐    │
│  │   voltage (left Y, blue)                     │    │
│  │   current (right Y, orange)                  │    │
│  │        ← combined chart →                    │    │
│  └──────────────────────────────────────────────┘    │
│  Legend: ● Profile A - voltage  ● Profile B - current│
│  (click legend to show/hide individual series)       │
└──────────────────────────────────────────────────────┘
```
- Y축 단위가 다르면 (값 범위 10배 이상 차이) 자동 dual-axis (left/right)
- chart_type 혼합 시 모두 line으로 렌더 + "Mixed chart types → rendered as line" 경고

### 5.5 Difference 레이아웃
```
┌──────────────────────────────────────────────────────┐
│ Profile Comparison (Difference)  X: time    [✕ Exit] │
│ Profile A: voltage vs Profile B: current             │
├──────────────────────────────────────────────────────┤
│  ┌──────────────────────────────────────────────┐    │
│  │  ── A (blue)  ── B (orange)                  │    │
│  │  ░░ Diff shaded area (gray)                  │    │
│  └──────────────────────────────────────────────┘    │
│  Mean Diff: 9.3  Max Diff: 15.2  RMSE: 10.1         │
│  (Diff = A - B, computed per-row)                    │
└──────────────────────────────────────────────────────┘
```
- Difference = `df[Y_col_A] - df[Y_col_B]` (같은 DataFrame, 같은 행)
- 예시: Profile A가 Y=voltage, Profile B가 Y=current → diff = voltage - current per row

### 5.6 동기화 동작 (Side-by-Side)
- **X축 동기화 (기본 ON)**: pan/zoom 시 다른 패널 X축 범위 동일하게
- **Y축 동기화 (기본 OFF)**: zoom 시 다른 패널 Y축 범위 동일하게
- **Selection 동기화 (기본 ON)**: 데이터 포인트/영역 선택 시 같은 행 인덱스를 다른 패널 하이라이트
- 동기화 방식: **throttle** (50ms 간격 최대 1회 fire, leading edge)
- 각각 독립 토글 (체크박스)

## 6. 데이터 구조

### 6.1 ComparisonSettings 확장 (기존 클래스 수정)
```python
@dataclass
class ComparisonSettings:
    mode: ComparisonMode = ComparisonMode.SINGLE
    # 기존 필드 유지
    sync_scroll: bool = True
    sync_zoom: bool = True
    sync_pan_x: bool = True
    sync_pan_y: bool = False
    sync_selection: bool = True
    comparison_datasets: List[str] = field(default_factory=list)
    
    # 신규 필드
    comparison_target: str = "dataset"  # "dataset" | "profile"
    comparison_profile_ids: List[str] = field(default_factory=list)  # 프로파일 비교 시 대상 ID
    comparison_dataset_id: str = ""  # 프로파일 비교 시 대상 데이터셋 ID
```

### 6.2 ViewSyncManager (기존 SideBySideLayout에서 추출)
```python
class ViewSyncManager(QObject):
    """뷰 동기화 매니저 — 데이터셋/프로파일 비교 공용"""
    view_range_synced = Signal(str, list, list)  # source_id, x_range, y_range
    selection_synced = Signal(str, list)  # source_id, selected_indices
    
    def __init__(self):
        self._sync_x: bool = True
        self._sync_y: bool = False
        self._sync_selection: bool = True
        self._panels: weakref.WeakValueDictionary = weakref.WeakValueDictionary()
        self._throttle_timer: QTimer  # 50ms throttle
        self._pending_sync: Optional[tuple] = None
    
    def register_panel(self, panel_id: str, panel: QWidget): ...
    def unregister_panel(self, panel_id: str): ...
    def on_source_range_changed(self, source_id: str, x_range, y_range): ...
    def on_source_selection_changed(self, source_id: str, indices: list): ...
```
- `weakref.WeakValueDictionary` 사용하여 패널 파괴 시 자동 정리 (메모리 누수 방지)
- 기존 `SideBySideLayout`의 `_on_panel_view_changed`, `set_view_range` 로직을 여기로 이전

### 6.3 MiniGraphWidget 확장 (기존 클래스 수정)
```python
class MiniGraphWidget(QWidget):
    def __init__(self, dataset_id: str, engine, state, 
                 graph_setting: Optional[GraphSetting] = None,  # 신규
                 parent=None):
        self.graph_setting = graph_setting  # 있으면 이 설정으로 렌더
        # graph_setting이 있으면 chart_type, x_column, value_columns를 이것에서 읽음
        # 없으면 기존 동작 (state에서 읽음)
```

### 6.4 ProfileComparisonController (신규)
```python
class ProfileComparisonController(QObject):
    comparison_started = Signal(list)  # profile_ids
    comparison_ended = Signal()
    panel_removed = Signal(str)  # profile_id
    
    def __init__(self, store: ProfileStore, controller: ProfileController, state: AppState):
        # ProfileController 시그널 구독
        controller.profile_deleted.connect(self._on_profile_deleted)
        controller.profile_renamed.connect(self._on_profile_renamed)
        controller.profile_applied.connect(self._on_profile_applied)
```

## 7. 성능 & 메모리 요구사항
- **데이터 복사 없음**: 모든 프로파일이 같은 DataFrame 참조. 프로파일은 뷰(설정)만 다름
- **렌더링 최적화**: 5000개 이상 포인트 시 자동 다운샘플링 (기존 sampling.py의 LTTB 활용)
- **동기화 throttle**: QTimer 50ms, leading edge fire. 연속 이벤트 시 최대 20fps 동기화
- **Overlay dual-axis 결정**: Y축 값 범위 비교, max/min 비율 > 10배면 dual-axis. 그 외 single-axis
- **패널 weakref**: ViewSyncManager가 WeakValueDictionary 사용. 패널 파괴 시 자동 참조 해제
- 목표: 100k 행 × 4 프로파일 Side-by-Side = 추가 메모리 < 50MB

## 8. 테스트 시나리오

### Unit Tests
- [ ] UT-1: ComparisonSettings.comparison_target 필드 동작 ("dataset" | "profile")
- [ ] UT-2: ViewSyncManager X축 throttle 동기화 on/off
- [ ] UT-3: ViewSyncManager Y축 throttle 동기화 on/off
- [ ] UT-4: ViewSyncManager Selection 동기화
- [ ] UT-5: ViewSyncManager weakref 패널 정리 (패널 파괴 후 참조 없음)
- [ ] UT-6: X축 일치 여부 검증: `profile_a.x_column == profile_b.x_column`
- [ ] UT-7: Difference 계산: `df[Y_A] - df[Y_B]`, Mean, Max, RMSE
- [ ] UT-8: MiniGraphWidget에 GraphSetting 전달 시 해당 설정으로 렌더 검증
- [ ] UT-9: Dual-axis 판정: 값 범위 비율 > 10 → dual, ≤ 10 → single
- [ ] UT-10: Mixed chart_type → line 통일 변환

### Integration Tests
- [ ] IT-1: ProfileStore에서 2개 프로파일 → ProfileComparisonController → Side-by-Side 시작
- [ ] IT-2: Side-by-Side에서 ViewSyncManager 동기화 동작
- [ ] IT-3: Overlay에서 X축 불일치 시 모드 비활성화 (warning, Side-by-Side만 가능)
- [ ] IT-4: 데이터셋 비교 → 프로파일 비교 전환 시 이전 비교 자동 해제
- [ ] IT-5: 프로파일 비교 → 데이터셋 비교 전환 시 이전 비교 자동 해제
- [ ] IT-6: 비교 중 프로파일 삭제 → 패널 제거, 1개 남으면 비교 종료
- [ ] IT-7: 비교 중 프로파일 수정 (Y컬럼 변경) → 패널 리렌더
- [ ] IT-8: 비교 중 프로파일 X축 변경 → Overlay면 경고 후 Side-by-Side 전환

### E2E Tests
- [ ] E2E-1: CSV 로드 → 프로파일 2개 생성 → Side-by-Side 비교 → X축 zoom 동기화 확인
- [ ] E2E-2: CSV 로드 → 같은 X축 프로파일 2개 → Overlay 비교 → 범례 클릭 show/hide
- [ ] E2E-3: CSV 로드 → 같은 X축 프로파일 2개 → Difference → RMSE 표시 확인
- [ ] E2E-4: 4개 프로파일 Side-by-Side → Selection 동기화 확인
- [ ] E2E-5: 비교 모드에서 Esc키 → 단일 뷰 복귀 확인
- [ ] E2E-6: 프로파일 비교 중 데이터셋 비교 진입 → 프로파일 비교 자동 해제 확인

### Regression Tests
- [ ] RT-1: 기존 test_multi_dataset.py 전체 통과
- [ ] RT-2: 기존 test_integration.py 전체 통과
- [ ] RT-3: 기존 test_profile.py 전체 통과
- [ ] RT-4: 기존 test_state.py 전체 통과

### Performance Tests
- [ ] PT-1: 100k행 4프로파일 Side-by-Side 렌더링 < 2초
- [ ] PT-2: Overlay 8계열 100k행 렌더링 < 1초
- [ ] PT-3: 동기화 이벤트 전파 지연 < 50ms
- [ ] PT-4: 메모리 증가 < 50MB (100k행 4프로파일)

## 9. 성공 기준
- [ ] 같은 CSV에서 2~4개 프로파일 Side-by-Side 비교 가능
- [ ] X축 동일 프로파일 간 Overlay/Difference 비교 가능
- [ ] Zoom/Pan X,Y 동기화 개별 토글 동작 (throttle 50ms)
- [ ] Selection 동기화 동작
- [ ] 비교 진입/종료 UX 완성
- [ ] 데이터셋 비교와 상호 배타적 전환 동작
- [ ] 비교 중 프로파일 변경 대응 완벽
- [ ] 기존 기능 회귀 없음 (RT-1~4 통과)
- [ ] 전체 테스트 통과

## 10. 미해결 질문 (인지됨, 향후 기능으로 연기)
- Q1: 비교 상태(어떤 프로파일을 어떤 모드로 비교 중)의 저장/복원 → v2에서 처리
- Q2: 키보드 접근성 (Tab으로 패널 간 이동, Enter로 선택) → 별도 접근성 이슈로
- Q3: Colorblind-safe 팔레트 자동 적용 → 테마 시스템 확장 시 함께

## 11. 구현 모듈 분리 (병렬화 계획)

| Module | Files | Dependencies | 비고 |
|--------|-------|-------------|------|
| A. ComparisonSettings 확장 | `core/state.py` 수정 | 없음 | comparison_target 필드 추가 |
| B. ViewSyncManager 추출 | `core/view_sync.py` 신규 | 없음 (독립) | SideBySideLayout에서 로직 이전 |
| C. MiniGraphWidget 확장 | `ui/panels/side_by_side_layout.py` 수정 | A | GraphSetting 파라미터 추가 |
| D. ProfileSideBySideLayout | `ui/panels/profile_side_by_side.py` 신규 | A, B, C | SideBySideLayout 상속 |
| E. ProfileOverlayRenderer | `ui/panels/profile_overlay.py` 신규 | A, data_engine | X축 체크 + overlay 렌더 |
| F. ProfileDifferenceRenderer | `ui/panels/profile_difference.py` 신규 | A, data_engine | diff 계산 + 렌더 |
| G. ProfileComparisonController | `core/profile_comparison_controller.py` 신규 | A, ProfileController | 시그널 구독, 상태 관리 |
| H. SideBySideLayout 리팩터 | `ui/panels/side_by_side_layout.py` 수정 | B | ViewSyncManager 사용하도록 |
| I. UI Integration | `ui/main_window.py`, `ui/panels/profile_bar.py` 수정 | D, E, F, G | 진입/종료 UX |

병렬 가능: A, B 독립 → C, H 병렬 → D, E, F 병렬 → G → I
