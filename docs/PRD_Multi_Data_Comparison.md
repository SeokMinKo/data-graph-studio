# Data Graph Studio - 멀티데이터 비교 기능 PRD

## 📋 개요

**기능명:** Multi-Data Comparison (멀티데이터 비교)

**한 줄 설명:** 여러 데이터셋을 동시에 로드하여 오버레이 또는 병렬 비교 분석을 수행하는 기능

**타겟 사용자:**
- 데이터 분석가: A/B 테스트 결과 비교, 기간별 데이터 비교
- 엔지니어: 버전별 성능 데이터 비교, 시스템 로그 비교
- 연구원: 실험군/대조군 데이터 비교, 다중 실험 결과 분석
- PM/기획자: 캠페인별 성과 비교, 지역별 매출 비교

**핵심 가치:**
> "여러 데이터를 한 화면에서 직관적으로 비교하여 인사이트 도출 시간 단축"

---

## 🎯 문제 정의

### 현재 한계

| 항목 | 현재 상태 | 문제점 |
|------|----------|--------|
| 데이터 로드 | 단일 파일만 가능 | 비교를 위해 별도 창 필요 |
| 그래프 | 하나의 데이터셋만 렌더링 | 오버레이 비교 불가 |
| 상태 관리 | 단일 AppState | 데이터셋별 독립 설정 불가 |
| 테이블 | 하나의 DataFrame 표시 | 다중 데이터 탐색 불가 |

### 사용자 페인 포인트

1. **번거로운 비교 작업**
   - 2개 파일 비교 시 2개의 프로그램 창 필요
   - 수동으로 화면 배치 필요
   - 동일 시점으로 정렬하기 어려움

2. **시간 낭비**
   - 각 파일을 순차적으로 열어 확인해야 함
   - 비교 결과를 수동으로 기록해야 함
   - 차이점 발견이 어려움

3. **분석 품질 저하**
   - 동시에 볼 수 없어 패턴 인식 어려움
   - 정량적 비교 도구 부재
   - 시각적 비교 한계

---

## 🎨 비교 모드 설계

### 모드 1: 오버레이 비교 (Overlay Mode)

하나의 차트에 여러 데이터셋을 겹쳐서 표시

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📊 OVERLAY COMPARISON                                                   │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                                                                  │    │
│  │     Dataset A ━━━━                                              │    │
│  │     Dataset B ─ ─ ─                                              │    │
│  │                    ━━━━                                          │    │
│  │            ━━━━━━━━    ━━━━                                      │    │
│  │       ━━━━━        ─ ─ ─ ─ ━━━━━━                               │    │
│  │   ━━━━        ─ ─ ─         ─ ─ ─ ─ ━━━                          │    │
│  │  ─ ─ ─ ─ ─ ─                        ━━━                          │    │
│  │                                                                  │    │
│  │  Legend:  ━ sales_2024.csv   ─ sales_2023.csv                   │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  📈 Comparison Stats:                                                    │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Metric         │  Dataset A   │  Dataset B   │  Diff (A-B)     │    │
│  │  ───────────────────────────────────────────────────────────────│    │
│  │  Mean           │  $1,234.56   │  $1,098.23   │  +$136.33 (+12%)│    │
│  │  Max            │  $5,678.90   │  $4,890.12   │  +$788.78 (+16%)│    │
│  │  Sum            │  $1.23M      │  $1.09M      │  +$140K   (+13%)│    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**적합한 사용 사례:**
- 시계열 추세 비교 (연도별, 월별)
- A/B 테스트 결과 비교
- 버전별 성능 데이터 비교
- 예측 vs 실제 데이터 비교

**특징:**
- 동일 X축 공유
- 데이터셋별 고유 색상/스타일
- 범례로 데이터셋 구분
- 통합 통계 패널

---

### 모드 2: 병렬 비교 (Side-by-Side Mode)

각 데이터셋을 독립된 패널에 표시

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📊 SIDE-BY-SIDE COMPARISON                                              │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─────────────────────────┐  ┌─────────────────────────┐               │
│  │  📂 sales_2024.csv      │  │  📂 sales_2023.csv      │               │
│  ├─────────────────────────┤  ├─────────────────────────┤               │
│  │  Summary                │  │  Summary                │               │
│  │  Rows: 50,000           │  │  Rows: 48,200           │               │
│  │  Mean: $1,234           │  │  Mean: $1,098           │               │
│  ├─────────────────────────┤  ├─────────────────────────┤               │
│  │       ╭─────╮           │  │       ╭───╮             │               │
│  │      ╱      ╲          │  │      ╱     ╲            │               │
│  │  ───╱        ╲───      │  │  ───╱       ╲───        │               │
│  │                         │  │                         │               │
│  ├─────────────────────────┤  ├─────────────────────────┤               │
│  │  Table View             │  │  Table View             │               │
│  │  ┌────┬────┬────┐      │  │  ┌────┬────┬────┐      │               │
│  │  │ A  │ B  │ C  │      │  │  │ A  │ B  │ C  │      │               │
│  │  └────┴────┴────┘      │  │  └────┴────┴────┘      │               │
│  └─────────────────────────┘  └─────────────────────────┘               │
│                                                                          │
│  🔗 Sync Options:  ☑ Sync Scroll  ☑ Sync Zoom  □ Sync Selection        │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**적합한 사용 사례:**
- 완전히 다른 구조의 데이터 비교
- 각 데이터셋에 다른 차트 타입 적용
- 독립적인 필터/그룹 설정 필요 시
- 상세 테이블 탐색 필요 시

**특징:**
- 독립된 그래프/테이블 패널
- 선택적 동기화 (스크롤, 줌, 선택)
- 데이터셋별 독립 설정
- 최대 4개 데이터셋 동시 표시

---

### 모드 3: 차이 분석 (Difference Mode)

두 데이터셋 간의 차이를 직접 시각화

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📊 DIFFERENCE ANALYSIS                                                  │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Comparing: sales_2024.csv (A) vs sales_2023.csv (B)                    │
│  Formula: A - B                                                          │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │         Positive Difference (A > B)                             │    │
│  │                    ▓▓▓▓                                          │    │
│  │              ▓▓▓▓▓▓▓▓▓▓▓▓                                       │    │
│  │         ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓                                   │    │
│  │  ─────────────────────────────────────────── baseline (0)       │    │
│  │         ░░░░░░                                                   │    │
│  │              ░░░░░░░░░░                                          │    │
│  │         Negative Difference (A < B)                             │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  📊 Difference Statistics:                                               │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  Total Difference:  +$136,330 (+12.4%)                          │    │
│  │  Positive Days:     215 (58.9%)                                 │    │
│  │  Negative Days:     150 (41.1%)                                 │    │
│  │  Max Increase:      +$2,500 (2024-06-15)                        │    │
│  │  Max Decrease:      -$1,200 (2024-02-03)                        │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**적합한 사용 사례:**
- 증감 분석 (전년 대비 증감)
- 편차 분석 (예측 vs 실제)
- 벤치마크 비교 (목표 vs 실적)

---

## 🏗️ 기술 아키텍처

### 1. 데이터 엔진 리팩토링

#### 현재 구조
```python
class DataEngine:
    _df: Optional[pl.DataFrame]        # 단일 DataFrame
    _source: Optional[DataSource]      # 단일 소스
    _profile: Optional[DataProfile]    # 단일 프로파일
```

#### 새로운 구조
```python
@dataclass
class DatasetInfo:
    """개별 데이터셋 정보"""
    id: str                           # 고유 식별자 (UUID)
    name: str                         # 표시 이름
    df: pl.DataFrame                  # 데이터프레임
    source: DataSource                # 데이터 소스 정보
    profile: DataProfile              # 프로파일링 정보
    color: str                        # 차트 색상
    metadata: Dict[str, Any]          # 추가 메타데이터
    created_at: datetime              # 로드 시간

class DataEngine:
    """멀티 데이터셋을 지원하는 데이터 엔진"""
    _datasets: Dict[str, DatasetInfo] = {}  # dataset_id -> DatasetInfo
    _active_dataset_id: Optional[str] = None
    _comparison_mode: ComparisonMode = ComparisonMode.SINGLE

    # 새로운 메서드
    def load_dataset(self, path: str, name: str = None) -> str:
        """데이터셋 로드 후 ID 반환"""
        pass

    def get_dataset(self, dataset_id: str) -> Optional[DatasetInfo]:
        """특정 데이터셋 조회"""
        pass

    def remove_dataset(self, dataset_id: str) -> bool:
        """데이터셋 제거"""
        pass

    def get_comparison_df(self, dataset_ids: List[str],
                          join_column: str = None) -> pl.DataFrame:
        """비교용 병합 DataFrame 생성"""
        pass

    def calculate_diff(self, dataset_a: str, dataset_b: str,
                       value_column: str, key_column: str = None) -> pl.DataFrame:
        """두 데이터셋 간 차이 계산"""
        pass

    @property
    def active_dataset(self) -> Optional[DatasetInfo]:
        """현재 활성 데이터셋"""
        return self._datasets.get(self._active_dataset_id)

    @property
    def dataset_count(self) -> int:
        """로드된 데이터셋 수"""
        return len(self._datasets)
```

#### ComparisonMode Enum
```python
class ComparisonMode(Enum):
    SINGLE = "single"           # 단일 데이터셋 (기존 모드)
    OVERLAY = "overlay"         # 오버레이 비교
    SIDE_BY_SIDE = "side_by_side"  # 병렬 비교
    DIFFERENCE = "difference"   # 차이 분석
```

---

### 2. 상태 관리 리팩토링

#### 현재 구조
```python
class AppState:
    _x_column: Optional[str]
    _group_columns: List[GroupColumn]
    _value_columns: List[ValueColumn]
    _filters: List[FilterCondition]
```

#### 새로운 구조
```python
@dataclass
class DatasetState:
    """개별 데이터셋의 상태"""
    dataset_id: str
    x_column: Optional[str] = None
    group_columns: List[GroupColumn] = field(default_factory=list)
    value_columns: List[ValueColumn] = field(default_factory=list)
    hover_columns: List[str] = field(default_factory=list)
    filters: List[FilterCondition] = field(default_factory=list)
    sorts: List[SortCondition] = field(default_factory=list)
    selection: SelectionState = field(default_factory=SelectionState)
    chart_settings: ChartSettings = field(default_factory=ChartSettings)

class AppState(QObject):
    """멀티 데이터셋을 지원하는 앱 상태"""

    # 시그널 추가
    dataset_added = Signal(str)           # dataset_id
    dataset_removed = Signal(str)         # dataset_id
    dataset_activated = Signal(str)       # dataset_id
    comparison_mode_changed = Signal(str) # mode
    datasets_compared = Signal(list)      # [dataset_ids]

    # 상태 저장소
    _dataset_states: Dict[str, DatasetState] = {}
    _active_dataset_id: Optional[str] = None
    _comparison_datasets: List[str] = []   # 비교 중인 데이터셋 목록
    _comparison_mode: ComparisonMode = ComparisonMode.SINGLE

    # 동기화 설정
    _sync_scroll: bool = True
    _sync_zoom: bool = True
    _sync_selection: bool = False

    def get_state(self, dataset_id: str = None) -> DatasetState:
        """데이터셋 상태 조회 (None이면 활성 데이터셋)"""
        pass

    def add_dataset_state(self, dataset_id: str) -> DatasetState:
        """새 데이터셋 상태 추가"""
        pass

    def set_comparison_datasets(self, dataset_ids: List[str]):
        """비교할 데이터셋 설정"""
        pass

    def apply_to_all_datasets(self, action: Callable[[DatasetState], None]):
        """모든 데이터셋에 동일 설정 적용"""
        pass
```

---

### 3. UI 컴포넌트 설계

#### 3.1 데이터셋 매니저 패널 (새로 추가)

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📂 DATASET MANAGER                                              [−][×] │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Loaded Datasets (3/4):                                                  │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  ● sales_2024.csv                              [Active]    [×]  │    │
│  │    📊 50,000 rows × 12 cols  │  💾 4.2 MB  │  📅 2 min ago      │    │
│  │    Color: 🔵  │  ☑ Compare                                      │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  ○ sales_2023.csv                                          [×]  │    │
│  │    📊 48,200 rows × 12 cols  │  💾 3.9 MB  │  📅 5 min ago      │    │
│  │    Color: 🟠  │  ☑ Compare                                      │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  ○ budget_2024.csv                                         [×]  │    │
│  │    📊 12,000 rows × 8 cols   │  💾 1.1 MB  │  📅 10 min ago     │    │
│  │    Color: 🟢  │  □ Compare                                      │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  [+ Add Dataset]  [Compare Selected]                                     │
│                                                                          │
│  ─────────────────────────────────────────────────────────────────────  │
│  Comparison Mode:                                                        │
│  ○ Single    ● Overlay    ○ Side-by-Side    ○ Difference               │
│                                                                          │
│  Join Settings (for Overlay/Difference):                                 │
│  Key Column: [Date             ▼]                                        │
│  ☑ Auto-align by key                                                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

**DatasetManagerPanel 클래스:**
```python
class DatasetManagerPanel(QWidget):
    """데이터셋 관리 패널"""

    # 시그널
    dataset_selected = Signal(str)        # dataset_id
    dataset_removed = Signal(str)         # dataset_id
    compare_requested = Signal(list)      # [dataset_ids]
    mode_changed = Signal(str)            # mode

    def __init__(self, engine: DataEngine, state: AppState):
        pass

    def add_dataset_item(self, dataset_info: DatasetInfo):
        """데이터셋 아이템 추가"""
        pass

    def refresh_dataset_list(self):
        """데이터셋 목록 새로고침"""
        pass

    def get_selected_for_comparison(self) -> List[str]:
        """비교용 선택된 데이터셋 ID 목록"""
        pass
```

---

#### 3.2 비교 그래프 패널 (ComparisonGraphPanel)

기존 GraphPanel을 확장하여 멀티 데이터셋 렌더링 지원

```python
class ComparisonGraphPanel(GraphPanel):
    """멀티 데이터셋 비교 그래프 패널"""

    def __init__(self, engine: DataEngine, state: AppState):
        super().__init__(engine, state)
        self._dataset_plots: Dict[str, List[PlotItem]] = {}
        self._dataset_colors: Dict[str, str] = {}

    def render_overlay(self, dataset_ids: List[str]):
        """오버레이 모드 렌더링"""
        self.clear_all_plots()

        for i, dataset_id in enumerate(dataset_ids):
            dataset = self.engine.get_dataset(dataset_id)
            state = self.state.get_state(dataset_id)
            color = self._get_dataset_color(dataset_id, i)

            # 데이터 준비
            df = self._prepare_chart_data(dataset.df, state)

            # 샘플링
            if len(df) > MAX_POINTS:
                df = self._sample_data(df, MAX_POINTS)

            # 플롯 생성
            plot_items = self._create_plots(df, state, color, dataset.name)
            self._dataset_plots[dataset_id] = plot_items

        self._update_legend()
        self._update_comparison_stats()

    def render_difference(self, dataset_a: str, dataset_b: str,
                          value_column: str, key_column: str = None):
        """차이 모드 렌더링"""
        diff_df = self.engine.calculate_diff(
            dataset_a, dataset_b, value_column, key_column
        )

        # 양수/음수 별도 색상으로 바 차트 렌더링
        self._render_difference_chart(diff_df)
        self._update_difference_stats(diff_df)

    def _update_comparison_stats(self):
        """비교 통계 패널 업데이트"""
        pass

    def _update_legend(self):
        """데이터셋별 범례 업데이트"""
        pass
```

---

#### 3.3 병렬 비교 레이아웃 (SideBySideLayout)

```python
class SideBySideLayout(QWidget):
    """병렬 비교 레이아웃"""

    def __init__(self, engine: DataEngine, state: AppState, max_panels: int = 4):
        super().__init__()
        self._panels: Dict[str, DatasetPanel] = {}
        self._max_panels = max_panels

        # 메인 레이아웃
        self._splitter = QSplitter(Qt.Horizontal)

    def add_dataset_panel(self, dataset_id: str):
        """데이터셋 패널 추가"""
        if len(self._panels) >= self._max_panels:
            raise ValueError(f"최대 {self._max_panels}개까지만 추가 가능")

        panel = DatasetPanel(self.engine, self.state, dataset_id)
        self._panels[dataset_id] = panel
        self._splitter.addWidget(panel)

        # 동기화 연결
        self._connect_sync(panel)

    def _connect_sync(self, panel: DatasetPanel):
        """패널 간 동기화 연결"""
        if self.state.sync_scroll:
            panel.scroll_changed.connect(self._sync_scroll)
        if self.state.sync_zoom:
            panel.zoom_changed.connect(self._sync_zoom)
        if self.state.sync_selection:
            panel.selection_changed.connect(self._sync_selection)


class DatasetPanel(QWidget):
    """개별 데이터셋 뷰 패널"""

    # 시그널
    scroll_changed = Signal(float, float)  # x, y
    zoom_changed = Signal(float, float, float, float)  # x_min, x_max, y_min, y_max
    selection_changed = Signal(set)  # row_indices

    def __init__(self, engine: DataEngine, state: AppState, dataset_id: str):
        super().__init__()
        self.dataset_id = dataset_id

        # 각 패널은 독립적인 Summary, Graph, Table 보유
        self._summary = SummaryPanel(engine, state, dataset_id)
        self._graph = GraphPanel(engine, state, dataset_id)
        self._table = TablePanel(engine, state, dataset_id)
```

---

### 4. 데이터 정렬 및 병합 전략

#### 4.1 키 컬럼 기반 정렬

```python
class DataAligner:
    """여러 데이터셋을 키 컬럼 기준으로 정렬"""

    @staticmethod
    def align_by_key(datasets: Dict[str, pl.DataFrame],
                     key_column: str,
                     fill_strategy: str = "null") -> Dict[str, pl.DataFrame]:
        """
        키 컬럼 기준으로 데이터셋 정렬

        Args:
            datasets: {dataset_id: DataFrame} 매핑
            key_column: 정렬 기준 컬럼 (예: "date", "id")
            fill_strategy: 누락값 처리 ("null", "forward", "backward", "interpolate")

        Returns:
            정렬된 데이터셋 매핑
        """
        # 모든 키 값의 합집합 구하기
        all_keys = set()
        for df in datasets.values():
            all_keys.update(df[key_column].unique().to_list())

        # 각 데이터셋을 전체 키에 맞춰 확장
        aligned = {}
        for dataset_id, df in datasets.items():
            aligned_df = df.join(
                pl.DataFrame({key_column: list(all_keys)}),
                on=key_column,
                how="right"
            ).sort(key_column)

            if fill_strategy == "forward":
                aligned_df = aligned_df.fill_null(strategy="forward")
            elif fill_strategy == "backward":
                aligned_df = aligned_df.fill_null(strategy="backward")
            elif fill_strategy == "interpolate":
                aligned_df = aligned_df.interpolate()

            aligned[dataset_id] = aligned_df

        return aligned

    @staticmethod
    def create_comparison_view(datasets: Dict[str, pl.DataFrame],
                               key_column: str,
                               value_columns: List[str]) -> pl.DataFrame:
        """
        비교용 통합 뷰 생성

        Returns:
            key | dataset_a_col1 | dataset_b_col1 | dataset_a_col2 | ...
        """
        aligned = DataAligner.align_by_key(datasets, key_column)

        result = pl.DataFrame({key_column: aligned[list(datasets.keys())[0]][key_column]})

        for dataset_id, df in aligned.items():
            for col in value_columns:
                result = result.with_columns(
                    df[col].alias(f"{dataset_id}_{col}")
                )

        return result
```

---

### 5. 비교 통계 엔진

```python
@dataclass
class ComparisonStatistics:
    """두 데이터셋 간 비교 통계"""
    dataset_a_id: str
    dataset_b_id: str
    column: str

    # 기본 통계
    a_mean: float
    b_mean: float
    a_std: float
    b_std: float
    a_sum: float
    b_sum: float

    # 차이 통계
    diff_mean: float
    diff_percent: float
    correlation: float

    # 통계 검정 결과
    t_statistic: Optional[float] = None
    p_value: Optional[float] = None
    is_significant: Optional[bool] = None

class ComparisonEngine:
    """비교 분석 엔진"""

    @staticmethod
    def compare_columns(df_a: pl.DataFrame, df_b: pl.DataFrame,
                        column: str, alpha: float = 0.05) -> ComparisonStatistics:
        """두 데이터셋의 특정 컬럼 비교"""

        a_values = df_a[column].drop_nulls().to_numpy()
        b_values = df_b[column].drop_nulls().to_numpy()

        # 기본 통계
        a_mean, b_mean = a_values.mean(), b_values.mean()
        a_std, b_std = a_values.std(), b_values.std()
        a_sum, b_sum = a_values.sum(), b_values.sum()

        # 차이 통계
        diff_mean = a_mean - b_mean
        diff_percent = (diff_mean / b_mean * 100) if b_mean != 0 else float('inf')

        # 상관관계 (길이가 같은 경우)
        correlation = None
        if len(a_values) == len(b_values):
            correlation = np.corrcoef(a_values, b_values)[0, 1]

        # t-검정
        from scipy import stats
        t_stat, p_value = stats.ttest_ind(a_values, b_values)
        is_significant = p_value < alpha

        return ComparisonStatistics(
            dataset_a_id=df_a.name if hasattr(df_a, 'name') else 'A',
            dataset_b_id=df_b.name if hasattr(df_b, 'name') else 'B',
            column=column,
            a_mean=a_mean, b_mean=b_mean,
            a_std=a_std, b_std=b_std,
            a_sum=a_sum, b_sum=b_sum,
            diff_mean=diff_mean,
            diff_percent=diff_percent,
            correlation=correlation,
            t_statistic=t_stat,
            p_value=p_value,
            is_significant=is_significant
        )

    @staticmethod
    def generate_comparison_report(datasets: Dict[str, pl.DataFrame],
                                   value_columns: List[str]) -> pd.DataFrame:
        """전체 비교 리포트 생성"""
        pass
```

---

## 📐 UI/UX 상세 설계

### 1. 데이터셋 추가 워크플로우

```
┌─────────────────────────────────────────────────────────────────────────┐
│  Step 1: 파일 선택                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  💡 Tip: Ctrl+클릭으로 여러 파일 선택 가능                               │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  📁 Documents/Data/                                              │    │
│  │                                                                  │    │
│  │  ☑ sales_2024.csv                     4.2 MB    2024-01-15     │    │
│  │  ☑ sales_2023.csv                     3.9 MB    2023-01-10     │    │
│  │  □  sales_2022.csv                     3.5 MB    2022-01-08     │    │
│  │  □  customers.xlsx                     1.2 MB    2024-01-20     │    │
│  │                                                                  │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Selected: 2 files (8.1 MB total)                                        │
│                                                                          │
│                                    [Cancel]  [Open Selected]             │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────────┐
│  Step 2: 파싱 미리보기 및 설정                                           │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌─ sales_2024.csv ─────────────────────────────────────────────────┐   │
│  │  Encoding: UTF-8 ▼   Delimiter: , ▼   Header: Row 1 ▼           │   │
│  │  ┌────────────────────────────────────────────────────────────┐ │   │
│  │  │  date       │  region  │  sales   │  qty    │  category   │ │   │
│  │  │  2024-01-01 │  Asia    │  1234.56 │  10     │  Electronics│ │   │
│  │  │  2024-01-02 │  Europe  │  2345.67 │  15     │  Clothing   │ │   │
│  │  └────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ┌─ sales_2023.csv ─────────────────────────────────────────────────┐   │
│  │  Encoding: UTF-8 ▼   Delimiter: , ▼   Header: Row 1 ▼           │   │
│  │  ┌────────────────────────────────────────────────────────────┐ │   │
│  │  │  date       │  region  │  sales   │  qty    │  category   │ │   │
│  │  │  2023-01-01 │  Asia    │  1100.00 │  8      │  Electronics│ │   │
│  │  │  2023-01-02 │  Europe  │  2100.50 │  12     │  Clothing   │ │   │
│  │  └────────────────────────────────────────────────────────────┘ │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
│  ☑ Same settings for all files                                          │
│                                                                          │
│                                    [Back]  [Load All]                    │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

                                    ↓

┌─────────────────────────────────────────────────────────────────────────┐
│  Step 3: 비교 설정                                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  How would you like to compare these datasets?                           │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │  ● Overlay Mode                                                  │    │
│  │    Show all datasets on a single chart                          │    │
│  │    Best for: time series comparison, trend analysis              │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  ○ Side-by-Side Mode                                            │    │
│  │    Show each dataset in a separate panel                        │    │
│  │    Best for: different structures, independent exploration       │    │
│  ├─────────────────────────────────────────────────────────────────┤    │
│  │  ○ Difference Mode                                              │    │
│  │    Show the difference between two datasets                      │    │
│  │    Best for: variance analysis, before/after comparison          │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│                                                                          │
│  Key Column for Alignment: [date           ▼]  (auto-detected)          │
│                                                                          │
│                                    [Skip]  [Start Comparison]            │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

### 2. 단축키

| 동작 | 단축키 | 설명 |
|------|--------|------|
| 데이터셋 추가 | `Ctrl+Shift+O` | 새 데이터셋 추가 로드 |
| 다음 데이터셋 | `Ctrl+Tab` | 다음 데이터셋으로 전환 |
| 이전 데이터셋 | `Ctrl+Shift+Tab` | 이전 데이터셋으로 전환 |
| 비교 시작 | `Ctrl+K` | 선택된 데이터셋 비교 |
| 단일 모드 | `Ctrl+1` | 단일 데이터셋 모드 |
| 오버레이 모드 | `Ctrl+2` | 오버레이 비교 모드 |
| 병렬 모드 | `Ctrl+3` | 병렬 비교 모드 |
| 차이 모드 | `Ctrl+4` | 차이 분석 모드 |
| 데이터셋 닫기 | `Ctrl+W` | 현재 데이터셋 닫기 |
| 모두 닫기 | `Ctrl+Shift+W` | 모든 데이터셋 닫기 |

---

### 3. 데이터셋 색상 팔레트

```python
DEFAULT_DATASET_COLORS = [
    "#1f77b4",  # 파랑
    "#ff7f0e",  # 주황
    "#2ca02c",  # 초록
    "#d62728",  # 빨강
    "#9467bd",  # 보라
    "#8c564b",  # 갈색
    "#e377c2",  # 분홍
    "#7f7f7f",  # 회색
    "#bcbd22",  # 올리브
    "#17becf",  # 청록
]

# 차이 모드 색상
DIFF_POSITIVE_COLOR = "#2ca02c"  # 초록 (증가)
DIFF_NEGATIVE_COLOR = "#d62728"  # 빨강 (감소)
DIFF_NEUTRAL_COLOR = "#7f7f7f"   # 회색 (변화없음)
```

---

## 📅 구현 로드맵

### Phase 1: 핵심 인프라 (2주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| DataEngine 멀티 데이터셋 지원 | Critical | 3일 |
| AppState DatasetState 분리 | Critical | 2일 |
| DatasetInfo, ComparisonMode 데이터 클래스 | High | 1일 |
| 기존 단일 데이터셋 호환성 유지 | Critical | 2일 |
| 단위 테스트 작성 | High | 2일 |

**Phase 1 완료 기준:**
- 여러 파일을 순차적으로 로드 가능
- 데이터셋 간 전환 가능
- 기존 기능 100% 정상 동작

---

### Phase 2: UI 컴포넌트 (2주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| DatasetManagerPanel 구현 | Critical | 3일 |
| 다중 파일 선택 다이얼로그 | High | 1일 |
| 데이터셋 색상 선택기 | Medium | 1일 |
| MainWindow 레이아웃 수정 | High | 2일 |
| 단축키 추가 | Medium | 1일 |
| UI 테스트 작성 | High | 2일 |

**Phase 2 완료 기준:**
- 데이터셋 매니저 패널 정상 동작
- 데이터셋 추가/제거/전환 UI 완성
- 기본 비교 모드 선택 가능

---

### Phase 3: 오버레이 비교 (2주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| ComparisonGraphPanel 구현 | Critical | 4일 |
| 멀티 데이터셋 렌더링 로직 | Critical | 2일 |
| 데이터 정렬 (DataAligner) | High | 2일 |
| 비교 통계 패널 | High | 2일 |
| 통합 범례 | Medium | 1일 |
| 성능 최적화 | High | 2일 |

**Phase 3 완료 기준:**
- 오버레이 모드로 2개 이상 데이터셋 시각화
- 키 컬럼 기준 자동 정렬
- 비교 통계 표시

---

### Phase 4: 병렬 비교 (1.5주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| SideBySideLayout 구현 | High | 3일 |
| DatasetPanel 컴포넌트 | High | 2일 |
| 동기화 로직 (스크롤, 줌) | Medium | 2일 |
| 선택 동기화 옵션 | Low | 1일 |

**Phase 4 완료 기준:**
- 최대 4개 데이터셋 병렬 표시
- 스크롤/줌 동기화 동작
- 독립적인 설정 적용 가능

---

### Phase 5: 차이 분석 (1.5주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| ComparisonEngine 구현 | High | 2일 |
| 차이 차트 렌더링 | High | 2일 |
| 통계 검정 기능 | Medium | 2일 |
| 차이 리포트 내보내기 | Low | 1일 |

**Phase 5 완료 기준:**
- 두 데이터셋 간 차이 시각화
- 통계적 유의성 검정
- 리포트 내보내기

---

### Phase 6: 고급 기능 및 최적화 (1주)

| 작업 | 우선순위 | 예상 일수 |
|------|---------|----------|
| 프로젝트 파일 (.dgs) 멀티 데이터셋 지원 | High | 2일 |
| 메모리 최적화 (대용량 데이터셋) | High | 2일 |
| 사용자 매뉴얼/튜토리얼 | Medium | 1일 |
| 통합 테스트 | High | 2일 |

---

## ⚡ 성능 고려사항

### 메모리 관리

```python
class MemoryManager:
    """멀티 데이터셋 메모리 관리"""

    MAX_TOTAL_MEMORY = 4 * 1024 * 1024 * 1024  # 4GB
    WARNING_THRESHOLD = 0.7  # 70%
    CRITICAL_THRESHOLD = 0.9  # 90%

    def __init__(self, engine: DataEngine):
        self.engine = engine

    def get_total_memory_usage(self) -> int:
        """전체 데이터셋 메모리 사용량"""
        total = 0
        for dataset in self.engine._datasets.values():
            total += dataset.df.estimated_size()
        return total

    def can_load_dataset(self, estimated_size: int) -> tuple[bool, str]:
        """데이터셋 로드 가능 여부 확인"""
        current = self.get_total_memory_usage()
        projected = current + estimated_size

        if projected > self.MAX_TOTAL_MEMORY:
            return False, f"메모리 한도 초과. 현재: {current/1e9:.1f}GB, 필요: {estimated_size/1e9:.1f}GB"

        if projected > self.MAX_TOTAL_MEMORY * self.CRITICAL_THRESHOLD:
            return True, "⚠️ 메모리 사용량이 높습니다. 일부 데이터셋 제거를 권장합니다."

        return True, None

    def suggest_datasets_to_remove(self, required_memory: int) -> List[str]:
        """메모리 확보를 위해 제거 추천 데이터셋"""
        pass
```

### 렌더링 최적화

```python
# 멀티 데이터셋 샘플링 전략
def sample_for_comparison(datasets: Dict[str, pl.DataFrame],
                          max_total_points: int = 20000) -> Dict[str, pl.DataFrame]:
    """
    전체 포인트 수 제한을 위한 샘플링

    각 데이터셋에 비례 배분:
    - Dataset A: 10,000 rows → 6,667 samples
    - Dataset B: 5,000 rows → 3,333 samples
    """
    total_rows = sum(len(df) for df in datasets.values())

    if total_rows <= max_total_points:
        return datasets

    sampled = {}
    for dataset_id, df in datasets.items():
        ratio = len(df) / total_rows
        sample_size = int(max_total_points * ratio)
        sampled[dataset_id] = lttb_sample(df, sample_size)

    return sampled
```

---

## 🧪 테스트 전략

### 단위 테스트

```python
# tests/test_multi_dataset.py

class TestDataEngineMultiDataset:

    def test_load_multiple_datasets(self, engine):
        """여러 데이터셋 로드 테스트"""
        id1 = engine.load_dataset("data1.csv", "Dataset 1")
        id2 = engine.load_dataset("data2.csv", "Dataset 2")

        assert engine.dataset_count == 2
        assert engine.get_dataset(id1).name == "Dataset 1"
        assert engine.get_dataset(id2).name == "Dataset 2"

    def test_remove_dataset(self, engine):
        """데이터셋 제거 테스트"""
        id1 = engine.load_dataset("data1.csv")
        engine.remove_dataset(id1)

        assert engine.dataset_count == 0
        assert engine.get_dataset(id1) is None

    def test_dataset_alignment(self, engine):
        """데이터셋 정렬 테스트"""
        # 날짜가 다른 두 데이터셋
        df1 = pl.DataFrame({"date": ["2024-01-01", "2024-01-03"], "value": [100, 300]})
        df2 = pl.DataFrame({"date": ["2024-01-02", "2024-01-03"], "value": [200, 350]})

        aligned = DataAligner.align_by_key(
            {"a": df1, "b": df2},
            key_column="date"
        )

        # 모든 날짜가 포함되어야 함
        assert len(aligned["a"]) == 3
        assert len(aligned["b"]) == 3


class TestComparisonEngine:

    def test_compare_columns(self):
        """컬럼 비교 통계 테스트"""
        df_a = pl.DataFrame({"value": [100, 200, 300]})
        df_b = pl.DataFrame({"value": [90, 180, 270]})

        stats = ComparisonEngine.compare_columns(df_a, df_b, "value")

        assert stats.a_mean == 200
        assert stats.b_mean == 180
        assert stats.diff_mean == 20
        assert abs(stats.diff_percent - 11.11) < 0.1
```

### 통합 테스트

```python
# tests/test_multi_dataset_integration.py

class TestMultiDatasetIntegration:

    @pytest.fixture
    def app_with_two_datasets(self, qtbot):
        """두 데이터셋이 로드된 앱"""
        app = MainWindow()
        qtbot.addWidget(app)

        app.engine.load_dataset("test_data/sales_2024.csv", "2024 Sales")
        app.engine.load_dataset("test_data/sales_2023.csv", "2023 Sales")

        return app

    def test_overlay_mode_rendering(self, app_with_two_datasets, qtbot):
        """오버레이 모드 렌더링 테스트"""
        app = app_with_two_datasets

        # 오버레이 모드 전환
        app.state.set_comparison_mode(ComparisonMode.OVERLAY)
        app.state.set_comparison_datasets(list(app.engine._datasets.keys()))

        # 그래프 렌더링 확인
        qtbot.waitUntil(lambda: app.graph_panel.plot_count == 2)

        assert app.graph_panel.legend_items == ["2024 Sales", "2023 Sales"]

    def test_side_by_side_sync(self, app_with_two_datasets, qtbot):
        """병렬 모드 동기화 테스트"""
        app = app_with_two_datasets

        app.state.set_comparison_mode(ComparisonMode.SIDE_BY_SIDE)
        app.state.sync_zoom = True

        # 첫 번째 패널 줌
        first_panel = app.side_by_side_layout.panels[0]
        first_panel.zoom(x_range=(0, 100))

        # 두 번째 패널도 동기화되어야 함
        second_panel = app.side_by_side_layout.panels[1]
        assert second_panel.x_range == (0, 100)
```

---

## 📊 성공 지표

| 지표 | 목표값 | 측정 방법 |
|------|--------|----------|
| 데이터셋 로드 시간 | 추가 데이터셋당 < 2초 오버헤드 | 벤치마크 테스트 |
| 오버레이 렌더링 시간 | 2개 데이터셋 × 100만 행 < 3초 | 벤치마크 테스트 |
| 메모리 효율 | 단일 모드 대비 < 20% 추가 | 메모리 프로파일링 |
| 사용자 작업 시간 | 기존 대비 50% 단축 | 사용자 테스트 |
| 학습 곡선 | 5분 내 비교 기능 사용 | 사용자 테스트 |

---

## 🔗 관련 문서

- [PRD.md](../PRD.md) - 메인 제품 요구사항
- [PRD_SPOTFIRE_UPGRADE.md](../PRD_SPOTFIRE_UPGRADE.md) - Spotfire 수준 업그레이드
- [PRD_Graph_Profiles.md](PRD_Graph_Profiles.md) - 그래프 프로필 기능
- [CLAUDE.md](../CLAUDE.md) - 개발 가이드

---

*작성일: 2026-01-30*
*작성자: Claude Code*
