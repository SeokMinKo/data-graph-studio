# PRD: DGS v0.16 — Major Enhancement Bundle

## 1. 목표
Data Graph Studio의 Compare 모드 완성, 고급 차트 지원, 데이터 필터링, 사용성 전반 개선을 통해 Spotfire/Tableau급 시각화 도구로 한 단계 도약한다.

## 2. 배경
v0.15.x에서 기본 Compare, 프로파일 관리, Drawing이 구현되었으나:
- Compare Selection 동기화 미흡
- Overlay/Diff 모드 기능 부족 (스타일 하드코딩, 단일 Y축)
- Box/Violin/Heatmap 차트 미동작
- 콤보 차트(듀얼 Y축) 미지원
- 피벗 차트 수준의 데이터 필터링 없음
- Stats 패널 정보 부족 및 사용성 이슈

## 3. 요구사항

### 3.1 기능 요구사항

#### Compare 모드 개선
- [ ] FR-1: **Compare Selection 동기화** — 한 그래프에서 rect drag selection 시 선택된 데이터 포인트(row indices)가 모든 Compare 패널에서 동일하게 하이라이트된다. X/Y Sync 설정과 무관하게 항상 동기화.
  - **빈 상태**: 선택 포인트 0개(빈 영역 드래그) → 모든 패널에서 하이라이트 해제 (정상 흐름)
  - **경계값**: row index가 해당 패널 데이터 범위 초과 → 해당 패널에서 초과 인덱스 무시, 유효 인덱스만 하이라이트
  - **해제**: Compare 모드 종료 시 하이라이트 자동 해제, Selection Signal disconnect
  - **중복 호출**: 빠른 연속 드래그 시 디바운스 100ms 적용, 마지막 selection만 동기화
  - **하이라이트 색상**: 테마 대응 — 다크 테마 `#FF6B6B`, 라이트 테마 `#DC2626` (테마 팔레트에서 참조, 하드코딩 금지)

- [ ] FR-2: **Overlay/Diff 듀얼 Y축** — Overlay/Diff 모드에서 좌/우 2개의 Y축 사용. 프로파일 A는 왼쪽 Y축, 프로파일 B는 오른쪽 Y축. X축이 다르면 경고 다이얼로그 표시 + 해당 모드 비활성화.
  - **경고 메시지**: "X-axis columns differ between profiles (A: '{col_a}', B: '{col_b}'). Overlay/Diff mode requires matching X-axis. Please align X-axis settings."
  - **실시간 변경 대응**: Overlay 모드 중 프로파일 X축 변경 시 → 변경 감지하여 경고 다이얼로그 재표시 + Overlay 자동 해제 → Side-by-Side로 폴백

- [ ] FR-3: **Overlay/Diff 프로파일 스타일 적용** — 현재 하드코딩된 색상/스타일 대신 각 프로파일의 GraphSetting에 저장된 chart_settings (line_width, color, marker 등) 그대로 반영.
  - **불변 객체 처리**: GraphSetting은 frozen dataclass이므로, Overlay 렌더러는 `chart_settings`를 읽기 전용으로 참조. 스타일 변경 시 새 GraphSetting 생성 후 교체.

#### 고급 차트 지원
- [ ] FR-4: **Box Plot / Violin / Heatmap 동작**
  - **Box Plot**: X축=Group 컬럼(카테고리), Y축=Value 컬럼(수치). 각 그룹별 박스(Q1, 중앙값, Q3, IQR, 이상치) 표시. Group 미설정 시 전체 데이터로 단일 박스 렌더링.
  - **Violin Plot**: Box Plot과 동일 X/Y 매핑에 커널 밀도 추정(KDE) 추가. Group 미설정 시 단일 바이올린.
  - **Heatmap**: X축=카테고리 컬럼, Y축=카테고리 컬럼, Value=수치 컬럼. Data 탭에서 X/Y/Value 3개 컬럼으로 설정. Value 미설정 시 빈도(count) 사용.
  - **빈 상태 안내**:
    - Box/Violin에 Group 컬럼 미설정 시: 차트 영역에 "Set Group column for Box/Violin plot (or renders single box)" 안내 표시 후 단일 박스 렌더링
    - Heatmap Value 미설정 시: "Value column not set — showing frequency count" 안내 후 count 기반 렌더링
    - 카테고리 0개(빈 Group 컬럼) → "No categories found in selected Group column" 표시

- [ ] FR-5: **콤보 차트 (듀얼 Y축)** — Y축 컬럼 선택에 따른 자동 모드 전환:
  - **Y축 0개**: 일반 빈 차트 (기존 동작 유지, "Select Y-axis column" 안내)
  - **Y축 1개**: 싱글 Y축 모드 (기존 동작 유지)
  - **Y축 2개**: 콤보 차트 자동 활성화. 좌Y=첫 번째 컬럼, 우Y=두 번째 컬럼 (`use_secondary_axis: bool`로 구분). 각 시리즈별로 차트 타입(Line/Bar/Scatter/Area)과 스타일(색상, 선 굵기, 마커)을 개별 설정 가능.
  - **Y축 3개 이상**: 최대 2개 제한. 3번째 이상 선택 시 경고 토스트 "Maximum 2 Y-axis columns supported. Additional columns ignored." 표시 후 무시.
  - **모드 해제**: Y축 2개→1개로 줄이면 콤보 해제 → 우측 ViewBox/AxisItem `deleteLater()` 정리, 시리즈별 설정 초기화
  - **렌더링 분리**: 콤보 차트 렌더러를 `graph/charts/combo_chart.py`로 분리, `graph_panel.py`에서는 위임만 수행

#### 데이터 필터링
- [ ] FR-6: **피벗 차트 스타일 Filter** — ChartOption > Data 탭에 Filter 섹션 추가. 컬럼 선택 → 해당 컬럼의 고유값(unique values) 목록 표시 → 다중 선택으로 필터링 → 필터링된 데이터만 그래프 렌더링. 엑셀 피벗차트의 Filter와 동일 동작.
  - **빈 상태**: 필터 결과 0행 → 그래프 영역에 "No data matches filters" 안내 + Stats 패널에 "N/A" 표시
  - **대규모 unique values**: unique값 1000개 이상 → 검색(QLineEdit) 필터 + 가상 스크롤(QListView with QStandardItemModel). 체크박스 위젯 직접 생성하지 않고 모델/뷰 패턴 사용.
  - **unique values 캐싱**: `@functools.lru_cache(maxsize=128)` (dataset_id, column_name 기준). 데이터 변경 시 캐시 무효화.
  - **빠른 연속 토글 대응**: 디바운스 300ms. 300ms 이내 연속 변경 → 마지막 상태만 반영.
  - **데이터셋 전환 시**: 필터 상태 프로파일별 저장. 다른 데이터셋 전환 → 해당 프로파일 필터 복원.
  - **필터 해제**: "Clear All" → FilterCondition 목록 비움 (별도 Undo 스택 불필요, 기존 프로파일 Undo와 통합).

#### Stats 패널 개선
- [ ] FR-7: **Stats Summary 높이 확장 + 스크롤** — Summary 영역의 최대 높이 제한 제거. 남은 공간 최대 활용. 내용 넘치면 Y 스크롤.
- [ ] FR-8: **Stats 그래프 hover 표시** — X Dist, Y Dist, GroupBy Ratio, Percentile 미니 그래프에 마우스 hover 시 해당 x, y 값 tooltip 표시. Tooltip은 QToolTip 사용 (별도 위젯 생성 없음, 메모리 안전).
- [ ] FR-9: **GroupBy Ratio 라벨 정상화** — 그룹 데이터가 있을 때 실제 그룹명 표시. Q1/Q2/Q3/Q4는 그룹 데이터가 없을 때의 fallback으로만 사용.

#### UI/UX 개선
- [ ] FR-10: **ChartOption 체크 항목 상단 정렬** — Y-Axis, GroupBy, Hover 리스트에서 체크된 항목이 항상 최상단에 위치.
- [ ] FR-11: **Draw 선택 + 이동** — 그려진 도형을 마우스 클릭으로 선택, 드래그로 위치 이동 가능.
  - **모드**: 기존 DRAW 모드에서 도형 위 클릭 시 선택 모드 진입 (별도 SELECT_DRAW 모드 불필요)
  - **영역 밖 드래그**: 그래프 ViewBox 경계에서 클램핑 (밖으로 못 나감)
  - **Undo 지원**: 드래그 시작 시 `save_undo_state()`, Ctrl+Z → 원위치 복귀
  - **Cancel**: Esc 키 → 이동 취소, 원위치로 복귀
  - **잠긴 도형**: `locked=True` 도형은 이동 불가, 클릭 시 "Shape is locked" 상태바 메시지

- [ ] FR-12: **프로젝트 탐색창 우클릭 메뉴 개선** — 멀티 선택 시 X/Y/Zoom/Selection Sync 메뉴 제거, Remove 메뉴 추가.
- [ ] FR-13: **Toolbar 순서 재배치** — Open Project → Save Project → Save Profile → Load Profile 순서. 버튼 간 간격 축소.
- [ ] FR-14: **Fit 단축키 동작 확인** — "F" 키로 Auto Fit, "Home" 키로 Reset View 정상 동작. 현재 미동작 시 키 바인딩 재등록 + 포커스 위젯 확인.
- [ ] FR-15: **Compare Toolbar 영역 확장** — Compare Widget이 깨지지 않도록 최소 너비 확보 (최소 600px, QWidget.setMinimumWidth).

### 3.2 비기능 요구사항
- [ ] NFR-1: **성능** — 50만 행 데이터에서 Filter 적용 < 500ms
- [ ] NFR-2: **메모리** — 콤보 차트 듀얼 Y축 추가 시 메모리 증가 < 20%
- [ ] NFR-3: **호환성** — 기존 .dgp 프로파일 파일과 하위 호환 유지. 새 필드(`SeriesStyle`) 없는 구버전 파일 → `None` 기본값 폴백으로 전역 설정 적용.
- [ ] NFR-4: **안정성** — 모든 새 기능에서 예외 시 크래시 없이 graceful degradation

### 3.3 회귀 영향 분석
- **ValueColumn 확장**: `SeriesStyle` 필드 추가는 Optional이므로 기존 직렬화 호환. 기존 `color`, `use_secondary_axis` 필드 유지.
- **FilterCondition 확장**: `operator="in"` + `values` 필드 추가. 기존 `operator` ("==", "!=", ">", "<" 등) 동작 불변.
- **graph_panel.py**: 콤보 차트 렌더링을 `combo_chart.py`로 분리하여 기존 렌더링 코드 수정 최소화.
- **기존 테스트**: `ValueColumn` 관련 기존 테스트는 새 `style` 필드가 `None` 기본값이므로 영향 없음.

## 4. 범위

### 포함
- FR-1 ~ FR-15의 모든 기능
- 관련 단위 테스트, 통합 테스트

### 제외
- 3D 차트
- 웹 기반 리모트 뷰
- 실시간 스트리밍 데이터 (v2 범위)
- 차트 내 주석(annotation) 고급 기능
- 숫자 컬럼 범위 필터(range filter) — v0.17 범위

## 5. UI/UX 상세

### 5.1 콤보 차트 (FR-5)
```
┌──────────────────────────────────────────┐
│ Y1 Label                    Y2 Label  │
│ ┌──────────────────────────────────┐   │
│ │  ███ Bar (Y1)                    │   │
│ │  ─── Line (Y2)      ── Y2 axis  │   │
│ │  ███      ───────                │   │
│ │  ███  ───         ───           │   │
│ └──────────────────────────────────┘   │
│           X Axis                        │
└──────────────────────────────────────────┘
```
- Y축 2개 선택 시 자동 활성화 (3개 이상은 경고 후 무시)
- 각 시리즈 옆에 차트 타입 드롭다운 (📈/📊/⬤/▤)
- 색상 버튼으로 개별 색상 설정
- 렌더러: `graph/charts/combo_chart.py` 분리 모듈

### 5.2 Filter (FR-6)
```
┌─ Data Tab ────────────────────┐
│ X-Axis: [column_combo     ▼] │
│ Y-Axis: [✓ col_a] [✓ col_b]  │
│ GroupBy: [column_combo    ▼]  │
│ Hover:  [✓ col_c]            │
│                               │
│ Filter:                       │
│ ┌─────────────────────────┐  │
│ │ Column: [status      ▼] │  │
│ │ 🔍 [search...        ]  │  │  ← unique값 1000+ 시 표시
│ │ ☑ Active               │  │
│ │ ☑ Pending              │  │
│ │ ☐ Closed               │  │
│ │ [Select All] [Clear]   │  │
│ └─────────────────────────┘  │
│ [+ Add Filter]               │
└───────────────────────────────┘
```
- 다중 필터 컬럼 지원 (AND 조합)
- Select All / Clear All 버튼
- 필터 적용 시 상태바에 "Filtered: X of Y rows" 표시
- unique값 1000+ → 검색 필터 + QListView 가상 스크롤
- 필터 결과 0행 → 그래프에 "No data matches filters" 표시

### 5.3 Compare Selection 동기화 (FR-1)
```
┌─ Graph A ─────────┐ ┌─ Graph B ─────────┐
│     ● ●           │ │     ●             │
│   ●[███]●         │ │   ●[███]●         │
│  ● [███] ●        │ │  ● [███] ●        │
│    [███]           │ │    [███]           │
│ (selection box)    │ │ (synced highlight) │
└────────────────────┘ └────────────────────┘
```
- Graph A에서 드래그 선택 → 선택된 row indices 계산
- 같은 row indices가 Graph B에서 하이라이트 (테마별 색상)
- 항상 동기화 (Sync 설정 무관)
- 빈 선택 → 하이라이트 해제

### 5.4 Overlay 듀얼 Y축 (FR-2)
```
┌──────────────────────────────────┐
│ Y1(Profile A)     Y2(Profile B) │
│ ┌────────────────────────────┐  │
│ │ ─── Profile A (left Y)     │  │
│ │ ─── Profile B (right Y)    │  │
│ └────────────────────────────┘  │
│           X Axis                 │
└──────────────────────────────────┘
```

### 5.5 Box Plot / Violin / Heatmap (FR-4)
```
┌─ Box Plot ─────────────┐  ┌─ Heatmap ──────────────┐
│   ┌─┐                  │  │     C1   C2   C3       │
│   │ │  ┌─┐   ┌─┐      │  │ R1 [██] [░░] [▒▒]      │
│ ──┤ ├──┤ ├── ┤ ├──     │  │ R2 [░░] [██] [░░]      │
│   │ │  │ │   │ │       │  │ R3 [▒▒] [░░] [██]      │
│   └─┘  └─┘   └─┘      │  │                         │
│   G1   G2    G3        │  │ X=카테고리, Y=카테고리   │
│ X=Group, Y=Value       │  │ Value=수치(or count)    │
└────────────────────────┘  └─────────────────────────┘
```

## 6. 데이터 구조

### 6.1 SeriesStyle (콤보 차트용, 신규)
```python
@dataclass
class SeriesStyle:
    """시리즈별 개별 스타일 설정. ValueColumn에서 Optional로 참조."""
    chart_type: Optional[str] = None      # "line" | "bar" | "scatter" | "area" (None=전역 설정)
    line_width: Optional[int] = None      # 개별 선 굵기 (None=전역 설정)
    marker: Optional[str] = None          # 마커 타입 (None=전역 설정)
```

### 6.2 ValueColumn 확장
```python
@dataclass
class ValueColumn:
    name: str
    aggregation: AggregationType = AggregationType.NONE
    color: Optional[str] = None           # 기존 필드 유지
    use_secondary_axis: bool = False      # 기존 필드 유지 (좌/우 Y축 구분)
    order: Optional[int] = None           # 기존 필드 유지
    formula: Optional[str] = None         # 기존 필드 유지
    style: Optional[SeriesStyle] = None   # 신규: 콤보 차트 시리즈별 스타일
    # style이 None이면 전역 GraphSetting의 chart_settings 사용
```
- **기존 필드 유지**: `color`, `use_secondary_axis` 그대로 사용 (중복 필드 없음)
- **SeriesStyle 분리**: 시각적 표현 정보는 `SeriesStyle`로 분리하여 단일 책임 원칙 준수
- **하위 호환**: `style` 필드는 Optional, 구버전 .dgp 파일에 없으면 `None` → 전역 설정 사용

### 6.3 FilterCondition 확장 (기존 모델 확장, 신규 모델 불필요)
```python
@dataclass
class FilterCondition:
    column: str
    operator: str             # 기존: "==", "!=", ">", "<", ">=", "<="
                              # 신규 추가: "in" (값 목록 필터)
    value: Optional[Any] = None       # 기존: 단일 값 비교용
    values: Optional[List[Any]] = None  # 신규: operator="in"일 때 다중 값 목록
    enabled: bool = True              # 기존 필드 유지
    
    # 사용 예: FilterCondition(column="status", operator="in", values=["Active", "Pending"])
    # v0.17 확장: operator="range", value={"min": 0, "max": 100}
```
- **기존 FilterCondition 확장**: 새 FilterSetting 모델 만들지 않음
- **values 필드**: `operator="in"`일 때만 사용, 기존 operator에선 무시
- **v0.17 확장 포인트**: `operator="range"` 추가 시 `value` 필드에 dict 사용 가능

### 6.4 State 확장
```python
class AppState:
    # 기존...
    filter_changed = Signal()  # 기존 Signal 재사용
    # FilterCondition 목록은 GraphSetting 내에 저장 (프로파일별 관리)
```

## 7. Signal 생명주기

### 7.1 Compare Selection 동기화
```
Compare 모드 진입 (_on_profile_comparison_started):
  → selection_changed Signal을 모든 패널에 connect
  → _compare_selection_connections: List[Connection] 에 저장

Compare 모드 해제 (_on_profile_comparison_ended):
  → _compare_selection_connections 순회하며 disconnect
  → 모든 패널 하이라이트 해제
  → _compare_selection_connections.clear()
```

### 7.2 Filter Signal
```
DataTab 초기화:
  → filter_changed Signal 정의 (DataTab 소속)
  
DataTab에서 필터 변경:
  → 디바운스 300ms → filter_changed.emit(filter_conditions)
  
GraphPanel.refresh():
  → filter_changed 수신 → 필터 적용 후 렌더링
  
DataTab 소멸 (데이터셋 변경, 탭 닫기):
  → QObject 소멸자에서 자동 Signal 해제 (Qt 기본 동작)
```

### 7.3 연쇄 업데이트 배치 전략
```
Filter 변경 → 디바운스 300ms → batch 실행:
  1. Polars lazy eval로 필터 적용 (데이터 변환)
  2. 그래프 리렌더링 (중간 렌더링 억제, final만)
  3. Stats 패널 업데이트
  
4패널 Compare Selection 동시 업데이트:
  → QTimer.singleShot(0) 으로 이벤트 루프 한 사이클에 배치
  → 각 패널 blockSignals(True) → 업데이트 → blockSignals(False)
```

## 8. 메인 스레드 전략

### 8.1 Filter 실행 스레드 분기
```
행 수 < 50만:
  → 메인 스레드에서 Polars lazy eval 실행 (예상 < 100ms, UI 블로킹 허용)
  
행 수 >= 50만:
  → QThread 워커에서 필터 실행
  → 메인 스레드에 프로그레스 인디케이터 표시 (QProgressBar indeterminate)
  → 완료 시 Signal로 결과 전달 → 메인 스레드에서 렌더링
```

### 8.2 Box/Violin 통계 계산
```
행 수 < 50만: 메인 스레드 (Polars 네이티브 quantile/std 충분히 빠름)
행 수 >= 50만: QThread 워커 (Box/Violin은 정렬 필요 → O(n log n))
```

### 8.3 Compare Selection 계산
```
numpy vectorized: O(n) boolean indexing
10만 포인트 → < 10ms (항상 메인 스레드)
100만 포인트 → < 100ms (메인 스레드 허용, 디바운스 100ms로 연속 호출 방지)
```

## 9. 성능 & 메모리 요구사항
- Filter 적용: 50만 행 기준 < 500ms (Polars lazy eval 활용)
- 콤보 차트 렌더링: 기존 차트 대비 렌더링 시간 < 2x
- Compare Selection 동기화: < 100ms (numpy vectorized)
- 듀얼 Y축: ViewBox 추가로 메모리 < 5MB 증가 (PlotDataItem, 축 라벨, 범례 포함)
- Filter unique values 캐싱: `@functools.lru_cache(maxsize=128)`, dataset_id+column 기준

## 10. 테스트 시나리오

### Unit Tests
- [ ] UT-1: FilterCondition `operator="in"` 직렬화/역직렬화 라운드트립
- [ ] UT-2: ValueColumn `style: Optional[SeriesStyle]` 기본값 호환성 (None 폴백)
- [ ] UT-3: 콤보 차트 듀얼 Y축 데이터 분리 로직 (`use_secondary_axis` 기준)
- [ ] UT-4: Compare Selection indices 계산 (rect 범위 내 포인트 매칭)
- [ ] UT-5: Overlay 듀얼 Y축 스케일링 독립성
- [ ] UT-6: Filter AND 조합 로직 (빈 필터, 단일 필터, 동일 컬럼 중복, 전체 선택)
- [ ] UT-7: Box/Violin/Heatmap 차트 데이터 변환 (Group 있음/없음, Value 있음/없음)
- [ ] UT-8: ChartOption 체크 항목 정렬 로직 (체크/해제/재정렬/전체 토글)
- [ ] UT-9: Drawing move(dx, dy) 좌표 업데이트 + 클램핑 + locked 도형 거부
- [ ] UT-10: GroupBy Ratio 라벨 생성 (그룹 데이터 있음 → 그룹명, 없음 → Q1~Q4 fallback)
- [ ] UT-11: SeriesStyle 직렬화/역직렬화 라운드트립
- [ ] UT-12: 콤보 차트 Y축 모드 전환 (0개→1개→2개→1개) 상태 정리
- [ ] UT-13: FilterCondition `operator="in"` + `values` 빈 리스트/None 처리
- [ ] UT-14: Selection 동기화 인덱스 범위 초과 시 무시 (경계값)
- [ ] UT-15: Heatmap count 기반 렌더링 (Value 미설정)

### Integration Tests
- [ ] IT-1: Filter 적용 → 그래프 리프레시 → Stats 업데이트 연쇄 (배치 검증)
- [ ] IT-2: 콤보 차트 → 프로파일 저장 → 로드 → SeriesStyle 설정 복원
- [ ] IT-3: Compare Selection → 다른 패널 하이라이트 → 해제 → Signal disconnect 확인
- [ ] IT-4: Overlay 모드 → 프로파일 스타일 → 듀얼 Y축 렌더링
- [ ] IT-5: 여러 필터 + 그룹 + 콤보 차트 동시 적용
- [ ] IT-6: Overlay 모드 중 X축 변경 → 경고 → Side-by-Side 폴백
- [ ] IT-7: .dgp 구버전 파일 로드 → SeriesStyle None 폴백 → 정상 렌더링

### E2E Tests
- [ ] E2E-1: 파일 로드 → Y 2개 선택 → 콤보 차트 → 각 시리즈 스타일 변경 → 저장 → 재로드 → 설정 유지
- [ ] E2E-2: 파일 로드 → Filter 설정 → 그래프 업데이트 확인 → Filter 변경 → 해제
- [ ] E2E-3: 프로파일 2개 → Compare Side-by-Side → Selection → 동기화 확인 → Exit
- [ ] E2E-4: 프로파일 2개 → Compare Overlay → 듀얼 Y축 → 스타일 확인
- [ ] E2E-5: Box Plot / Violin / Heatmap 각각 렌더링 확인 (Group 유무 모두)

### UI Behavior Tests
- [ ] UB-1: FR-12 우클릭 메뉴 — 단일 선택 시 전체 메뉴, 멀티 선택 시 Sync 메뉴 제거 + Remove 표시
- [ ] UB-2: FR-13 Toolbar 순서 — 버튼 순서 검증 (Open → Save → Save Profile → Load Profile)
- [ ] UB-3: FR-14 Fit 단축키 — "F" 키 Auto Fit + "Home" 키 Reset View 동작 검증
- [ ] UB-4: FR-15 Compare Toolbar — 최소 너비 600px 이하로 줄어들지 않음 검증
- [ ] UB-5: FR-11 Draw 이동 — Undo (Ctrl+Z) 복귀 + Esc 취소 동작 검증
- [ ] UB-6: FR-10 체크 항목 정렬 — 동적 체크/해제 후 재정렬 검증

### Performance Tests
- [ ] PT-1: 50만 행 × 20컬럼 데이터에서 Filter 적용/해제 < 500ms (`@pytest.mark.performance`, CI에서 3x 여유 = 1500ms)
- [ ] PT-2: 50만 행 콤보 차트 렌더링 < 3초 (`@pytest.mark.performance`, CI에서 3x 여유 = 9초)
- [ ] PT-3: Compare Selection 동기화 (10만 포인트) < 100ms (`@pytest.mark.performance`, CI에서 3x 여유 = 300ms)
- [ ] PT-4: Overlay 듀얼 Y축 렌더링 < 2초 (`@pytest.mark.performance`, CI에서 3x 여유 = 6초)

## 11. 성공 기준
- [ ] 15개 FR 전부 구현 및 동작 확인
- [ ] 기존 테스트 회귀 0건
- [ ] 새 테스트 커버리지 > 80%
- [ ] 50만 행 데이터에서 주요 기능 성능 기준 충족
- [ ] .dgp 프로파일 하위 호환성 유지

## 12. 미해결 질문
- ~~Q1: 콤보 차트에서 Y축 3개 이상 선택 시~~ → **해결**: 최대 2개 제한. 3번째 이상은 경고 토스트 후 무시.
- Q2: Filter에서 숫자 컬럼의 범위 필터(range filter)도 지원할 것인가? → v0.16에서는 값 목록 필터만, 범위는 v0.17. FilterCondition의 `operator` 확장 포인트로 대비.
- ~~Q3: Box Plot에서 X축은 Group 컬럼, Y축은 Value 컬럼으로 자동 매핑할 것인가?~~ → **해결**: X축=Group(카테고리), Y축=Value(수치). Group 미설정 시 전체 데이터 단일 박스.
- ~~Q4: Heatmap에서 X/Y/Value 3개 컬럼이 필요한데, 현재 UI로 충분한가?~~ → **해결**: Data탭의 X/Y/Value 3개 설정으로 충분. Value 미설정 시 빈도(count) 사용.

## 13. 구현 우선순위 (의존성 순)

### Phase A: 기반 (의존성 없음, 병렬 가능)
1. FR-7: Stats Summary height
2. FR-8: Stats hover
3. FR-9: GroupBy Ratio 라벨
4. FR-10: ChartOption 체크 정렬
5. FR-12: 탐색창 메뉴
6. FR-13: Toolbar 순서
7. FR-14: Fit 단축키
8. FR-15: Compare Toolbar 너비

### Phase B: 중간 (Phase A 불필요)
9. FR-4: Box/Violin/Heatmap 수정
10. FR-11: Draw 이동
11. FR-1: Compare Selection 동기화

### Phase C: 큰 기능 (State 확장 필요)
12. FR-6: Filter
13. FR-5: 콤보 차트

### Phase D: Compare 고급 (Phase B 후)
14. FR-2: Overlay 듀얼 Y축
15. FR-3: Overlay 스타일
