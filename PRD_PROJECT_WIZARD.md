# PRD: 새 프로젝트 마법사 (New Project Wizard)

## 개요

### 목표
기존 데이터셋 탭 기반 UI를 제거하고, 프로젝트 익스플로러 + 새 프로젝트 마법사 방식으로 전환한다. 파일 로딩 시 마법사가 실행되어 파싱 설정과 기본 그래프 설정(프로파일)을 한 번에 처리한다.

### 배경
- 현재: 파일 열기 → 파싱 다이얼로그 → 데이터셋 탭에 추가 → 별도로 그래프 설정
- 변경: 파일 열기 → **새 프로젝트 마법사** → 바로 그래프 렌더링

### 범위
1. 새 프로젝트 마법사 (스텝 바이 스텝 위자드)
2. 데이터셋 탭/패널 제거 (Datasets 탭)
3. 기존 파싱 다이얼로그 기능을 마법사로 통합 후 제거
4. 기존 프로젝트 열 때는 마법사 스킵
5. Projects 탭 (ProjectTreeView) 메인으로 승격

---

## 기능 요구사항

### FR-1: 새 프로젝트 마법사 UI

#### FR-1.1: 마법사 트리거
- **기본**: 파일 열기 (File > Open, Ctrl+O, 드래그앤드롭) 시 마법사 실행
- **마법사 스킵 옵션**:
  - `File > Open Without Wizard` (Ctrl+Shift+O) → 기본 파싱 설정으로 바로 열기
  - 환경설정에서 "Always skip wizard" 옵션 제공
- 기존 `.dgs` 프로젝트 파일 열 때는 항상 마법사 스킵, 바로 로드

#### FR-1.2: 마법사 스텝 구조
```
┌─────────────────────────────────────────────────────────┐
│  ● ○ ○  Step 1/3: 파싱 설정                      [X]   │
├─────────────────────────────────────────────────────────┤
│                                                         │
│  [스텝 컨텐츠 영역]                                      │
│                                                         │
├─────────────────────────────────────────────────────────┤
│                          [< 이전]  [다음 >]  [취소]      │
└─────────────────────────────────────────────────────────┘
```

**Step 1: 파싱 설정**
- 파일 정보 표시 (파일명, 크기, 타입)
- 인코딩 선택 (UTF-8, CP949, EUC-KR, ...)
- 구분자 설정 (CSV: 쉼표/탭/세미콜론/커스텀, Regex 지원)
- 헤더 행 포함 여부
- 스킵할 행 수
- 주석 문자
- Excel/Parquet 시트 선택 (해당 시)
- **미리보기 테이블** (샘플 100행)
- 컬럼 제외 체크박스
- **로딩 프로그레스 바** (파싱 진행률)

**Step 2: 그래프 기본 설정**
- 차트 타입 선택 (Line, Bar, Scatter, ...)
- X축 컬럼 선택 (필수)
- Y축 컬럼(들) 선택 (필수, 최소 1개)
- Group 컬럼 선택 (선택사항)
- Hover 정보 컬럼(들) 선택 (선택사항)
- **미리보기 차트** (샘플 데이터 기반, 실시간 반영)
- **확대 보기 버튼** (미리보기 차트 확대)

**Step 3: 완료**
- 설정 요약 표시
- 프로젝트 이름 입력 (기본값: 파일명)
- [완료] 클릭 시:
  1. 프로젝트 생성
  2. 프로파일 생성 (기본 그래프 설정 저장)
  3. 메인 윈도우에 그래프 렌더링
  4. ProjectTreeView에 추가

#### FR-1.3: 마법사 동작
- 각 스텝 간 자유롭게 이동 가능 (이전/다음)
- **Step 간 설정 유지**: 뒤로 갔다가 앞으로 와도 입력값 보존
- 필수 설정 미완료 시 다음 스텝 비활성화:
  - Step 1: 파싱 성공 필수
  - Step 2: X축 1개 + Y축 최소 1개 필수
- ESC 또는 취소로 마법사 종료 → 모든 임시 데이터 정리
- **ETL 변환 중 취소**: 백그라운드 스레드 안전하게 종료

#### FR-1.4: 에러 처리
- 파싱 실패 시: 에러 메시지 표시, Step 1에서 진행 불가
- 지원하지 않는 파일 형식: 명확한 에러 메시지
- 인코딩 오류: 다른 인코딩 제안

### FR-2: 데이터셋 탭 제거

#### FR-2.1: 제거 대상
- `dataset_manager_panel.py` 관련 UI
- 메인 윈도우의 Datasets 탭
- 관련 메뉴 항목 (Add Dataset 등)

#### FR-2.2: 대체 방안
- 데이터셋 관리는 ProjectTreeView (Projects 탭)에서 수행
- 좌측 사이드바 탭 구조에서 Datasets 탭 제거, Projects 탭만 유지

### FR-3: 기존 파싱 다이얼로그 제거

#### FR-3.1: 제거 대상
- `parsing_preview_dialog.py`
- 관련 메뉴/버튼에서 호출 제거

#### FR-3.2: 기능 이관
- `ParsingSettings` 데이터클래스 → `core/parsing.py`로 분리
- 파싱 미리보기 로직 → `core/parsing_utils.py` 공통 모듈
- ETL 변환 기능 유지 (마법사 내에서 처리)

### FR-4: 기존 프로젝트 열기

#### FR-4.1: .dgs 파일 열기
- 마법사 없이 바로 프로젝트 로드
- 저장된 프로파일대로 그래프 렌더링
- ProjectTreeView에 프로젝트 추가
- 멀티 데이터셋 프로젝트: 모든 데이터셋을 트리에 표시

---

## 비기능 요구사항

### NFR-1: 성능
- **파일 크기 제한**: 최대 500MB (초과 시 경고, 계속 진행 가능)
- **미리보기 응답 시간**: 설정 변경 후 500ms 이내 미리보기 갱신
- **샘플링**: 
  - Step 1 미리보기: 최대 100행
  - Step 2 차트 미리보기: 최대 10,000행 샘플링
- **메모리 관리**: 마법사 취소/완료 시 임시 데이터 즉시 해제
- **대용량 파일 (100MB+)**: 
  - 스트리밍 파싱 (전체 로드 X)
  - 프로그레스 바 표시
  - 백그라운드 스레드에서 처리

### NFR-2: 에러 처리
- 모든 에러는 사용자 친화적 메시지로 표시
- 로그 파일에 상세 에러 기록
- 복구 가능한 에러는 재시도 옵션 제공

### NFR-3: 접근성
- 전체 키보드 네비게이션 지원
- Tab 순서 논리적 배치
- 스크린 리더 호환 라벨

### NFR-4: UI 디바운싱
- 설정 변경 시 미리보기 갱신: 300ms 디바운스
- 연속 입력 시 마지막 값만 처리

---

## 기술 설계

### 기존 컴포넌트 (활용)
```
data_graph_studio/
├── core/
│   ├── profile.py              # GraphSetting 데이터클래스
│   ├── profile_store.py        # ProfileStore (프로파일 저장소)
│   ├── profile_controller.py   # ProfileController
│   ├── graph_setting_mapper.py # GraphSettingMapper
│   └── project.py              # Project, DataSourceRef
├── ui/
│   ├── models/
│   │   └── profile_model.py    # ProfileModel (QAbstractItemModel)
│   └── views/
│       └── project_tree_view.py # ProjectTreeView
```

### 새 파일 구조
```
data_graph_studio/
├── core/
│   ├── parsing.py              # ParsingSettings (기존에서 이관)
│   └── parsing_utils.py        # 파싱 유틸리티 (공통 로직)
├── ui/
│   ├── wizards/
│   │   ├── __init__.py
│   │   ├── new_project_wizard.py      # 메인 마법사 (QWizard)
│   │   ├── parsing_step.py            # Step 1 (QWizardPage)
│   │   ├── graph_setup_step.py        # Step 2 (QWizardPage)
│   │   └── finish_step.py             # Step 3 (QWizardPage)
```

### 제거할 파일
- `ui/dialogs/parsing_preview_dialog.py` (기능 이관 후)
- `ui/panels/dataset_manager_panel.py`

### 클래스 설계

```python
# core/parsing.py
@dataclass
class ParsingSettings:
    """파싱 설정 - 기존 parsing_preview_dialog.py에서 이관"""
    file_path: str
    file_type: FileType
    encoding: str = "utf-8"
    delimiter: str = ","
    has_header: bool = True
    skip_rows: int = 0
    comment_char: str = ""
    sheet_name: Optional[str] = None
    excluded_columns: List[str] = field(default_factory=list)

# core/parsing_utils.py
class ParsingEngine:
    """파싱 유틸리티 - 공통 로직"""
    @staticmethod
    def detect_encoding(file_path: str) -> str: ...
    @staticmethod
    def parse_preview(settings: ParsingSettings, max_rows: int = 100) -> pd.DataFrame: ...
    @staticmethod
    def parse_full(settings: ParsingSettings) -> pd.DataFrame: ...

# ui/wizards/new_project_wizard.py
class NewProjectWizard(QWizard):
    """새 프로젝트 마법사"""
    project_created = Signal(object)  # Project 객체 전달
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._parsing_settings: Optional[ParsingSettings] = None
        self._graph_setting: Optional[GraphSetting] = None
        self._preview_df: Optional[pd.DataFrame] = None
        
        self.addPage(ParsingStep(file_path))
        self.addPage(GraphSetupStep())
        self.addPage(FinishStep())
        
    def cleanupPage(self, id: int):
        """마법사 취소 시 cleanup"""
        self._preview_df = None  # 메모리 해제

# ui/wizards/parsing_step.py  
class ParsingStep(QWizardPage):
    """Step 1: 파싱 설정"""
    parsing_complete = Signal(object)  # ParsingSettings
    
    def __init__(self, file_path: str):
        super().__init__()
        self.file_path = file_path
        self._settings = ParsingSettings(file_path=file_path, ...)
        self._update_timer = QTimer()  # 디바운스용
        self._update_timer.setSingleShot(True)
        self._update_timer.setInterval(300)
        
    def initializePage(self):
        """페이지 진입 시 초기화"""
        self._load_preview()
        
    def validatePage(self) -> bool:
        """다음 스텝 진행 가능 여부"""
        return self._parsing_success
        
    def get_parsing_settings(self) -> ParsingSettings:
        return self._settings
        
    def get_preview_df(self) -> pd.DataFrame:
        return self._preview_df

# ui/wizards/graph_setup_step.py
class GraphSetupStep(QWizardPage):
    """Step 2: 그래프 기본 설정"""
    
    def __init__(self):
        super().__init__()
        self._columns: List[str] = []
        self._graph_setting: Optional[GraphSetting] = None
        
    def initializePage(self):
        """이전 스텝에서 컬럼 목록 받아오기"""
        wizard = self.wizard()
        parsing_step = wizard.page(0)
        df = parsing_step.get_preview_df()
        self._columns = list(df.columns)
        self._populate_column_combos()
        
    def validatePage(self) -> bool:
        """X축 + Y축 최소 1개 필수"""
        return self._x_column is not None and len(self._y_columns) >= 1
        
    def get_graph_setting(self) -> GraphSetting:
        return GraphSetting.create_new(
            name="Default",
            chart_type=self._chart_type,
            x_column=self._x_column,
            value_columns=self._y_columns,
            ...
        )

# ui/wizards/finish_step.py
class FinishStep(QWizardPage):
    """Step 3: 완료"""
    
    def initializePage(self):
        """설정 요약 표시"""
        wizard = self.wizard()
        parsing = wizard.page(0).get_parsing_settings()
        graph = wizard.page(1).get_graph_setting()
        self._show_summary(parsing, graph)
```

### Step 간 데이터 전달
- **방식**: QWizard의 `page(id)` 메서드로 이전 페이지 참조
- **데이터 흐름**:
  1. Step 1 → `ParsingSettings` + `preview_df`
  2. Step 2 → `GraphSetting` (컬럼 목록은 Step 1에서 참조)
  3. Step 3 → 요약 표시 (Step 1, 2 모두 참조)

### MainWindow 수정사항
```python
# main_window.py 변경점

def __init__(self):
    # 좌측 사이드바에서 Datasets 탭 제거
    # Projects 탭만 유지
    self._setup_sidebar()  # ProjectTreeView만 포함

def _open_file(self, file_path: str):
    if file_path.endswith('.dgs'):
        # 기존 프로젝트 - 바로 로드
        self._load_project(file_path)
    else:
        # 새 데이터 파일 - 마법사 실행
        wizard = NewProjectWizard(file_path, self)
        wizard.project_created.connect(self._on_project_created)
        if wizard.exec() == QWizard.Rejected:
            return  # 취소됨, cleanup은 wizard에서 처리

def _open_file_without_wizard(self, file_path: str):
    """Ctrl+Shift+O - 마법사 없이 기본 설정으로 열기"""
    # 기본 파싱 설정 적용
    # 기본 그래프 설정 (첫 번째 숫자 컬럼을 Y축으로)
    ...

def _on_project_created(self, project: Project):
    # ProfileStore에 추가
    self._profile_store.add_dataset(project.dataset_id, project.profiles)
    # ProfileModel 갱신
    self._profile_model.refresh()
    # 그래프 렌더링
    self._render_graph(project)
```

---

## UI/UX 상세

### 마법사 크기
- 기본 크기: 900 x 650 px
- 최소 크기: 700 x 500 px
- 모달 다이얼로그

### Step Progress Indicator
```
● ○ ○  Step 1: 파싱 설정
○ ● ○  Step 2: 그래프 설정  
○ ○ ●  Step 3: 완료
```

### Step 1 레이아웃
```
┌─────────────────────────────────────────────────────────┐
│  📁 파일: sales_data.csv (125 KB)                       │
├─────────────────────────────────────────────────────────┤
│  ┌───────────────────┐  ┌─────────────────────────────┐ │
│  │ 파싱 옵션          │  │ 미리보기                    │ │
│  │                   │  │ ┌─────┬─────┬─────┬─────┐  │ │
│  │ 인코딩: [UTF-8 ▼] │  │ │ col1│ col2│ col3│ col4│  │ │
│  │ 구분자: [쉼표  ▼] │  │ ├─────┼─────┼─────┼─────┤  │ │
│  │ 헤더행: [✓]       │  │ │ ...                   │  │ │
│  │ 스킵행: [0    ]   │  │ └─────┴─────┴─────┴─────┘  │ │
│  │ 주석:   [       ] │  │                            │ │
│  │                   │  │ [컬럼 제외 체크박스들]       │ │
│  └───────────────────┘  └─────────────────────────────┘ │
│  [████████████░░░░░░░░] 파싱 중... 45%                  │
└─────────────────────────────────────────────────────────┘
```

### Step 2 레이아웃
```
┌─────────────────────────────────────────────────────────┐
│  ┌───────────────────┐  ┌─────────────────────────────┐ │
│  │ 그래프 설정        │  │ 미리보기 차트         [🔍]  │ │
│  │                   │  │                            │ │
│  │ 차트: [Line   ▼]  │  │    📈 [실시간 그래프]        │ │
│  │                   │  │                            │ │
│  │ X축:  [date   ▼]* │  │                            │ │
│  │                   │  │                            │ │
│  │ Y축:  [☑ sales]*  │  │                            │ │
│  │       [☑ profit]  │  │                            │ │
│  │       [☐ cost]    │  │                            │ │
│  │                   │  │                            │ │
│  │ Group: [region▼]  │  │                            │ │
│  │ Hover: [name  ▼]  │  │                            │ │
│  │                   │  │                            │ │
│  │ * 필수 항목        │  │                            │ │
│  └───────────────────┘  └─────────────────────────────┘ │
└─────────────────────────────────────────────────────────┘
```

### Step 3 레이아웃
```
┌─────────────────────────────────────────────────────────┐
│  ✅ 설정 완료!                                          │
│                                                         │
│  프로젝트 이름: [sales_data           ]                 │
│                                                         │
│  ┌─────────────────────────────────────────────────┐   │
│  │ 📋 설정 요약                                     │   │
│  │                                                 │   │
│  │ 📁 파일: sales_data.csv                         │   │
│  │ 📊 인코딩: UTF-8, 구분자: 쉼표, 헤더: 있음        │   │
│  │ 📈 컬럼: 10개 (2개 제외)                         │   │
│  │                                                 │   │
│  │ 🎨 차트 타입: Line                               │   │
│  │ ➡️ X축: date                                    │   │
│  │ ⬆️ Y축: sales, profit                           │   │
│  │ 🏷️ Group: region                                │   │
│  │ 💬 Hover: name, id                              │   │
│  └─────────────────────────────────────────────────┘   │
│                                                         │
│  [완료] 클릭 시 그래프가 바로 표시됩니다.                 │
└─────────────────────────────────────────────────────────┘
```

### 에러 상태 UI
```
┌─────────────────────────────────────────────────────────┐
│  ⚠️ 파싱 오류                                           │
│                                                         │
│  파일을 읽을 수 없습니다.                                │
│  인코딩이 올바른지 확인해주세요.                          │
│                                                         │
│  추천 인코딩: CP949, EUC-KR                             │
│                                                         │
│  [다시 시도]  [다른 인코딩 선택]                         │
└─────────────────────────────────────────────────────────┘
```

---

## 테스트 케이스

### TC-1: 새 프로젝트 마법사 기본 플로우
1. CSV 파일 열기 → 마법사 실행 확인
2. Step 1: 파싱 설정 → 미리보기 정상 표시
3. Step 2: 그래프 설정 → 미리보기 차트 표시
4. Step 3: 완료 → 그래프 렌더링, ProjectTreeView에 추가

### TC-2: 다양한 파일 형식
- CSV (다양한 인코딩, 구분자)
- Excel (.xlsx, .xls)
- Parquet
- JSON
- ETL (Windows)

### TC-3: 기존 프로젝트 열기
1. .dgs 파일 열기 → 마법사 없이 바로 로드
2. 저장된 그래프 설정대로 렌더링

### TC-4: 마법사 취소
1. 마법사 중간에 취소/ESC → 아무 변경 없음, 메모리 정리 확인

### TC-5: 마법사 없이 열기
1. Ctrl+Shift+O로 파일 열기 → 마법사 없이 기본 설정으로 로드

### TC-6: 데이터셋 탭 제거 확인
- 메인 윈도우에서 Datasets 탭 없음
- Projects 탭만 존재

### TC-7: Step 간 이동
1. Step 2에서 Step 1로 이동 → 설정 유지
2. 다시 Step 2로 이동 → 이전 설정 그대로

### TC-8: 필수값 검증
1. Step 1: 파싱 실패 상태에서 다음 클릭 → 비활성화
2. Step 2: Y축 미선택 상태에서 다음 클릭 → 비활성화

### TC-9: 대용량 파일
1. 200MB CSV 파일 열기 → 프로그레스 바 표시
2. 미리보기 100행만 표시
3. 차트 미리보기 샘플링 확인

### TC-10: 에러 처리
1. 잘못된 인코딩 → 에러 메시지 + 추천
2. 손상된 파일 → 명확한 에러 메시지

---

## 마이그레이션 계획

### Phase 1: 공통 모듈 분리
1. `core/parsing.py` - ParsingSettings 이관
2. `core/parsing_utils.py` - 파싱 유틸리티 분리

### Phase 2: 마법사 구현
1. `wizards/` 폴더 및 기본 구조 생성
2. `NewProjectWizard` 클래스 구현
3. `ParsingStep` 구현 (기존 로직 활용)
4. `GraphSetupStep` 구현
5. `FinishStep` 구현

### Phase 3: MainWindow 통합
1. 파일 열기 로직 수정 (마법사 호출)
2. Ctrl+Shift+O 단축키 추가
3. Datasets 탭 제거, Projects 탭만 유지
4. 프로젝트 생성 후 그래프 렌더링 연결

### Phase 4: 레거시 제거
1. `parsing_preview_dialog.py` 제거
2. `dataset_manager_panel.py` 제거
3. 관련 import/호출 정리

### Phase 5: 테스트 및 검증
1. 전체 테스트 케이스 실행
2. 기존 .dgs 프로젝트 호환성 확인

---

## 확정 사항

1. **멀티 파일 지원**: 여러 파일 열 때 각각 마법사 실행 (마법사 없이 열기 옵션: Ctrl+Shift+O)
2. **프로젝트 익스플로러**: 기존 `ProjectTreeView` (ui/views/project_tree_view.py) 활용
3. **프로파일 편집**: 마법사 완료 후 그래프 설정 수정은 기존 프로파일 UI 사용

---

*작성: 맥클로 | 날짜: 2026-02-02 | 버전: 1.1*
