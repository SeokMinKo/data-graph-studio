# Graph Profiles Feature - PRD

## 개요

**기능명:** Graph Profiles (그래프 프로파일)

**한 줄 설명:** 데이터별로 자주 사용하는 그래프 설정들을 프로파일로 저장하고, 버튼 클릭만으로 빠르게 전환하며, Floating 창으로 여러 그래프를 동시에 비교 분석

**목표:**
- 반복적인 그래프 설정 작업 제거
- 동일 데이터에 대한 다양한 시각화 빠른 전환
- 여러 그래프를 동시에 비교 분석 가능

---

## 핵심 개념

### 용어 정의

| 용어 | 설명 |
|------|------|
| **Graph Setting** | 단일 그래프의 설정 (차트 타입, X/Y축, 필터, 집계 등) |
| **Profile** | 여러 Graph Setting의 묶음 (데이터 유형별로 저장) |
| **Profile Bar** | 그래프 패널 상단에 표시되는 설정 버튼 목록 |
| **Floating Graph** | 메인 윈도우와 독립적으로 열리는 그래프 창 |

### 사용자 시나리오

#### 시나리오 1: 프로파일 생성 및 저장
```
1. 사용자가 데이터 로드 후 원하는 그래프 설정 완료
2. "현재 설정 저장" 버튼 클릭
3. 설정 이름 입력 (예: "일별 매출 추이")
4. 현재 설정이 프로파일에 저장됨
5. 추가 설정들도 같은 방식으로 저장
6. 프로파일 저장 → 모든 설정을 하나의 프로파일 파일로 저장
```

#### 시나리오 2: 프로파일 불러오기 및 전환
```
1. 동일 구조의 데이터 파일 로드
2. 기존 프로파일 불러오기
3. Profile Bar에 저장된 설정들이 버튼으로 표시됨
4. "월별 카테고리 비교" 버튼 클릭
5. 즉시 해당 설정의 그래프가 표시됨
6. "지역별 매출 파이차트" 버튼 클릭
7. 즉시 해당 설정으로 전환됨
```

#### 시나리오 3: 여러 그래프 비교
```
1. 데이터 로드 및 프로파일 활성화 상태
2. "일별 매출 추이" 설정 활성화
3. "Floating으로 열기" 버튼 클릭 또는 버튼 더블클릭
4. 새 창에 해당 그래프가 표시됨
5. 메인 창에서 "카테고리별 비중" 선택
6. 두 그래프를 나란히 비교 분석
7. 추가로 더 많은 Floating 창 생성 가능
```

---

## UI/UX 설계

### 1. Profile Bar (프로파일 바)

**위치:** Summary Panel 아래, Graph Panel 상단

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         📊 SUMMARY PANEL                                │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │  📁 Profile: [sales_analysis.dgp ▼]  [📂] [💾] [➕]               │  │
│  │                                                                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌─────┐     │  │
│  │  │ 📈 일별  │ │ 📊 월별  │ │ 🥧 카테  │ │ 📉 지역  │ │  +  │     │  │
│  │  │   매출   │ │  카테고리│ │  고리별  │ │   비교   │ │     │     │  │
│  │  │  추이    │ │   비교   │ │   비중   │ │         │ │     │     │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘ └─────┘     │  │
│  │      ↑                                                            │  │
│  │   현재 활성                                                        │  │
│  └───────────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────────┤
│                          📈 GRAPH PANEL                                 │
```

### 2. Profile Bar 상세

#### 2.1 프로파일 선택 영역
```
┌─────────────────────────────────────────────────────────────────────┐
│  📁 Profile: [sales_analysis.dgp ▼]  [📂 Load] [💾 Save] [➕ New]   │
└─────────────────────────────────────────────────────────────────────┘
```

| 요소 | 동작 |
|------|------|
| 드롭다운 | 최근 사용 프로파일 목록 표시 |
| 📂 Load | 프로파일 파일 (.dgp) 불러오기 |
| 💾 Save | 현재 프로파일 저장 |
| ➕ New | 새 프로파일 생성 |

#### 2.2 설정 버튼 영역
```
┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
│ 📈 일별  │ │ 📊 월별  │ │ 🥧 카테  │ │ 📉 지역  │   ← 저장된 설정들
│   매출   │ │  카테고리│ │  고리별  │ │   비교   │
│  추이    │ │   비교   │ │   비중   │ │         │
│  [🔲][⊡] │ │  [🔲][⊡] │ │  [🔲][⊡] │ │  [🔲][⊡] │   ← 액션 버튼
└──────────┘ └──────────┘ └──────────┘ └──────────┘
    ↑ 활성 상태 (강조 표시)
```

#### 2.3 설정 버튼 상호작용

| 동작 | 결과 |
|------|------|
| **클릭** | 해당 설정을 메인 그래프에 적용 |
| **더블클릭** | 새 Floating 창에 해당 그래프 열기 |
| **우클릭** | 컨텍스트 메뉴 (편집, 복제, 삭제, 이름 변경) |
| **드래그** | 버튼 순서 재정렬 |
| **[🔲] 버튼** | Floating 창으로 열기 |
| **[⊡] 버튼** | Dashboard에 추가 (향후 기능) |

#### 2.4 설정 추가 버튼
```
┌─────┐
│  +  │  ← 현재 그래프 설정을 새 설정으로 저장
└─────┘
```

클릭 시 다이얼로그:
```
┌─────────────────────────────────────┐
│  💾 Save Current Graph Setting      │
├─────────────────────────────────────┤
│                                     │
│  Name:  [일별 매출 추이          ]  │
│                                     │
│  Icon:  [📈 ▼]  (선택 가능)         │
│                                     │
│  Description: (optional)            │
│  [                               ]  │
│  [                               ]  │
│                                     │
│        [Cancel]  [Save]             │
└─────────────────────────────────────┘
```

### 3. Floating Graph Window (플로팅 그래프 창)

```
┌──────────────────────────────────────────────────────┐
│  📈 일별 매출 추이                    [─] [□] [✕]   │
├──────────────────────────────────────────────────────┤
│  ┌────────────────────────────────────────────────┐  │
│  │                                                │  │
│  │                                                │  │
│  │            Interactive Graph                   │  │
│  │            (메인 창과 동일한 기능)              │  │
│  │                                                │  │
│  │                                                │  │
│  └────────────────────────────────────────────────┘  │
├──────────────────────────────────────────────────────┤
│  🔗 Sync Selection  │  📋 Copy  │  💾 Export        │
└──────────────────────────────────────────────────────┘
```

#### 3.1 Floating Window 특징

| 기능 | 설명 |
|------|------|
| **독립 창** | 메인 윈도우와 별도로 이동/크기 조절 가능 |
| **동일 데이터** | 메인 창과 동일한 데이터를 공유 |
| **Selection Sync** | 선택 동기화 On/Off (한 창에서 선택 → 다른 창에 반영) |
| **독립 설정** | 각 창마다 개별 그래프 설정 유지 |
| **멀티 모니터** | 다른 모니터로 이동 가능 |

#### 3.2 Selection Sync 동작

```
┌─────────────────┐         ┌─────────────────┐
│   Main Window   │◄───────►│ Floating Window │
│                 │  Sync   │                 │
│   ● ● ● ● ●    │   ON    │   ▓ ▓ ▓ ▓ ▓    │
│   선택 시       │         │   같이 하이라이트│
└─────────────────┘         └─────────────────┘

[🔗 Sync ON]  → 선택이 모든 창에 동기화
[🔗 Sync OFF] → 각 창 독립적으로 선택
```

### 4. 컨텍스트 메뉴

#### 4.1 설정 버튼 우클릭 메뉴
```
┌─────────────────────┐
│ ✏️  Edit Setting   │  → 설정 편집 다이얼로그
│ 📋  Duplicate      │  → 복제하여 새 설정 생성
│ ✏️  Rename         │  → 이름 변경
│ ──────────────────  │
│ 🔲  Open Floating  │  → Floating 창으로 열기
│ ⊡  Add to Dashboard│  → 대시보드에 추가
│ ──────────────────  │
│ 🔼  Move Left      │  → 왼쪽으로 이동
│ 🔽  Move Right     │  → 오른쪽으로 이동
│ ──────────────────  │
│ 🗑️  Delete        │  → 설정 삭제
└─────────────────────┘
```

#### 4.2 Profile Bar 영역 우클릭 메뉴
```
┌─────────────────────────┐
│ ➕  New Setting         │  → 현재 설정 저장
│ 📂  Load Profile        │  → 프로파일 불러오기
│ 💾  Save Profile        │  → 프로파일 저장
│ 💾  Save Profile As...  │  → 다른 이름으로 저장
│ ──────────────────────  │
│ 📊  Manage Profiles...  │  → 프로파일 관리자
│ ⚙️  Profile Bar Settings│  → 표시 설정
└─────────────────────────┘
```

---

## 데이터 구조

### 1. GraphSetting (단일 그래프 설정)

```python
@dataclass
class GraphSetting:
    """단일 그래프 설정"""
    id: str                          # 고유 ID (UUID)
    name: str                        # 표시 이름
    icon: str = "📊"                 # 아이콘 (이모지)
    description: str = ""            # 설명
    created_at: float                # 생성 시간
    modified_at: float               # 수정 시간

    # 차트 설정
    chart_type: str                  # ChartType enum value
    x_column: Optional[str]          # X축 컬럼

    # Group Zone 설정
    group_columns: List[Dict]        # GroupColumn 목록

    # Value Zone 설정
    value_columns: List[Dict]        # ValueColumn 목록

    # 차트 스타일
    chart_settings: Dict             # ChartSettings 전체

    # 필터 (선택적)
    filters: List[Dict] = None       # 설정에 포함할 필터
    include_filters: bool = False    # 필터 포함 여부

    # 정렬 (선택적)
    sorts: List[Dict] = None         # 설정에 포함할 정렬
    include_sorts: bool = False      # 정렬 포함 여부
```

### 2. Profile (프로파일)

```python
@dataclass
class Profile:
    """그래프 프로파일"""
    id: str                          # 고유 ID
    name: str                        # 프로파일 이름
    description: str = ""            # 설명
    created_at: float                # 생성 시간
    modified_at: float               # 수정 시간

    # 데이터 스키마 정보 (호환성 체크용)
    data_schema: Dict = None         # 컬럼 이름과 타입

    # 그래프 설정 목록
    settings: List[GraphSetting]     # 저장된 설정들

    # 기본 설정 (프로파일 로드 시 자동 적용)
    default_setting_id: Optional[str] = None

    # 메타데이터
    tags: List[str] = None           # 태그
    author: str = ""                 # 작성자
```

### 3. 파일 형식 (.dgp - Data Graph Profile)

```json
{
  "format_version": "1.0",
  "profile": {
    "id": "uuid-1234-5678",
    "name": "Sales Analysis Profile",
    "description": "월간 매출 데이터 분석용 프로파일",
    "created_at": 1706500000.0,
    "modified_at": 1706500000.0,
    "data_schema": {
      "columns": {
        "date": "datetime",
        "region": "string",
        "category": "string",
        "sales": "float",
        "quantity": "int"
      }
    },
    "default_setting_id": "setting-uuid-1",
    "settings": [
      {
        "id": "setting-uuid-1",
        "name": "일별 매출 추이",
        "icon": "📈",
        "chart_type": "line",
        "x_column": "date",
        "group_columns": [
          {"name": "region", "selected_values": []}
        ],
        "value_columns": [
          {"name": "sales", "aggregation": "sum", "color": "#1f77b4"}
        ],
        "chart_settings": {
          "line_width": 2,
          "marker_size": 6
        }
      },
      {
        "id": "setting-uuid-2",
        "name": "카테고리별 비중",
        "icon": "🥧",
        "chart_type": "pie",
        "group_columns": [
          {"name": "category"}
        ],
        "value_columns": [
          {"name": "sales", "aggregation": "sum"}
        ]
      }
    ]
  }
}
```

---

## 기능 상세

### 1. 프로파일 호환성 검사

데이터 로드 시 프로파일과의 호환성을 검사합니다.

```
┌─────────────────────────────────────────────────────────────┐
│  ⚠️ Profile Compatibility Warning                           │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Profile "Sales Analysis" references columns that           │
│  don't exist in the current data:                          │
│                                                             │
│  ❌ Missing columns:                                        │
│     • "region" (used in 3 settings)                        │
│     • "profit" (used in 1 setting)                         │
│                                                             │
│  ⚠️ Type mismatch:                                          │
│     • "date" - Profile: datetime, Data: string             │
│                                                             │
│  Options:                                                   │
│  [ ] Skip incompatible settings                            │
│  [ ] Try to auto-map columns                               │
│  [ ] Edit profile to fix                                   │
│                                                             │
│              [Cancel]  [Load Anyway]  [Edit Mapping]        │
└─────────────────────────────────────────────────────────────┘
```

### 2. 컬럼 자동 매핑

유사한 이름의 컬럼을 자동으로 매핑합니다.

```
┌─────────────────────────────────────────────────────────────┐
│  🔄 Column Mapping                                          │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Profile Column    →    Data Column                        │
│  ─────────────────────────────────────────────              │
│  "region"          →    [Region         ▼]  ✓ Auto-matched │
│  "sales"           →    [total_sales    ▼]  ⚠️ Suggested   │
│  "date"            →    [order_date     ▼]  ⚠️ Suggested   │
│  "profit"          →    [───────────    ▼]  ❌ Not found   │
│                                                             │
│                    [Auto-Map All]  [Apply]                  │
└─────────────────────────────────────────────────────────────┘
```

### 3. 설정 간 빠른 전환

단축키로 설정 간 빠른 전환을 지원합니다.

| 단축키 | 동작 |
|--------|------|
| `Ctrl+1~9` | 해당 번호의 설정으로 전환 |
| `Ctrl+[` | 이전 설정으로 전환 |
| `Ctrl+]` | 다음 설정으로 전환 |
| `Ctrl+Shift+F` | 현재 설정을 Floating으로 열기 |
| `Ctrl+Shift+S` | 현재 설정 저장 |

### 4. Floating Window 관리

여러 Floating 창을 효율적으로 관리합니다.

```
메뉴: Window
├── 🔲 New Floating Graph          Ctrl+Shift+F
├── ─────────────────
├── 📐 Arrange Windows
│   ├── Tile Horizontally
│   ├── Tile Vertically
│   ├── Cascade
│   └── Snap to Grid
├── ─────────────────
├── 🔗 Sync All Selections         Ctrl+Shift+L
├── 🔗 Unsync All Selections
├── ─────────────────
├── ✕ Close All Floating Windows
└── ─────────────────
    ☑ Floating 1: 일별 매출 추이
    ☑ Floating 2: 월별 카테고리
    ☐ Floating 3: 지역별 비교
```

### 5. Profile Manager (프로파일 관리자)

```
┌──────────────────────────────────────────────────────────────────────┐
│  📊 Profile Manager                                      [─] [□] [✕] │
├──────────────────────────────────────────────────────────────────────┤
│  ┌──────────────────┐  ┌───────────────────────────────────────────┐ │
│  │  📁 Profiles      │  │  Settings in "Sales Analysis"            │ │
│  │  ───────────────  │  │  ─────────────────────────────────────── │ │
│  │  📊 Sales Analysis│  │  ┌─────────────────────────────────────┐ │ │
│  │  📈 Marketing     │  │  │ 📈 일별 매출 추이        [⭐][✏️][🗑️]│ │ │
│  │  📉 Operations    │  │  │   Line, X: date, Y: sales (sum)     │ │ │
│  │  🏭 Manufacturing │  │  └─────────────────────────────────────┘ │ │
│  │                   │  │  ┌─────────────────────────────────────┐ │ │
│  │  [➕ New Profile] │  │  │ 📊 월별 카테고리         [  ][✏️][🗑️]│ │ │
│  │                   │  │  │   Bar, X: month, Y: sales by cat    │ │ │
│  └──────────────────┘  │  └─────────────────────────────────────┘ │ │
│                        │  ┌─────────────────────────────────────┐ │ │
│                        │  │ 🥧 카테고리별 비중       [  ][✏️][🗑️]│ │ │
│                        │  │   Pie, Group: category, Y: sales     │ │ │
│                        │  └─────────────────────────────────────┘ │ │
│                        │                                          │ │
│                        │  [➕ Add Current Setting]                 │ │
│                        └───────────────────────────────────────────┘ │
├──────────────────────────────────────────────────────────────────────┤
│  [Import...]  [Export...]           [Close]                          │
└──────────────────────────────────────────────────────────────────────┘
```

---

## 기술적 요구사항

### 1. 새로운 클래스

| 클래스 | 위치 | 역할 |
|--------|------|------|
| `GraphSetting` | `core/profile.py` | 단일 그래프 설정 |
| `Profile` | `core/profile.py` | 프로파일 (설정 묶음) |
| `ProfileManager` | `core/profile.py` | 프로파일 관리 |
| `ProfileBar` | `ui/panels/profile_bar.py` | Profile Bar UI |
| `SettingButton` | `ui/panels/profile_bar.py` | 설정 버튼 위젯 |
| `FloatingGraphWindow` | `ui/floating_graph.py` | Floating 그래프 창 |
| `ProfileManagerDialog` | `ui/dialogs/profile_manager.py` | 프로파일 관리 다이얼로그 |
| `SaveSettingDialog` | `ui/dialogs/save_setting.py` | 설정 저장 다이얼로그 |

### 2. AppState 확장

```python
class AppState:
    # 기존 signals...

    # 새로운 signals
    profile_loaded = Signal(object)      # Profile
    profile_saved = Signal()
    setting_changed = Signal(str)        # setting_id
    floating_window_opened = Signal(str) # setting_id
    floating_window_closed = Signal(str) # window_id

    # 새로운 속성
    _current_profile: Optional[Profile]
    _current_setting_id: Optional[str]
    _floating_windows: Dict[str, FloatingGraphWindow]
```

### 3. 파일 형식

| 형식 | 확장자 | 용도 |
|------|--------|------|
| Profile | `.dgp` | 프로파일 저장 (JSON) |
| Project | `.dgs` | 프로젝트 저장 (기존, 프로파일 포함 가능) |

### 4. 저장 위치

```
~/.data-graph-studio/
├── profiles/              # 사용자 프로파일
│   ├── sales_analysis.dgp
│   └── marketing.dgp
├── recent_profiles.json   # 최근 프로파일 목록
└── autosave/             # 자동 저장
```

---

## 구현 로드맵

### Phase 1: 핵심 기능 (2주)

- [ ] **데이터 구조**
  - [ ] GraphSetting dataclass
  - [ ] Profile dataclass
  - [ ] ProfileManager 기본 구현
  - [ ] 파일 저장/로드 (.dgp)

- [ ] **Profile Bar UI**
  - [ ] ProfileBar 위젯 구현
  - [ ] SettingButton 위젯 구현
  - [ ] MainWindow 레이아웃 수정
  - [ ] 설정 클릭 → 그래프 적용

- [ ] **기본 동작**
  - [ ] 현재 설정 저장
  - [ ] 설정 불러오기
  - [ ] 프로파일 저장/로드

### Phase 2: Floating Window (1주)

- [ ] **Floating Graph Window**
  - [ ] FloatingGraphWindow 클래스
  - [ ] Graph Panel 재사용
  - [ ] 창 관리 (열기/닫기)

- [ ] **Selection Sync**
  - [ ] 동기화 토글
  - [ ] 선택 상태 공유

### Phase 3: 고급 기능 (1주)

- [ ] **프로파일 관리**
  - [ ] ProfileManagerDialog
  - [ ] 설정 편집/복제/삭제
  - [ ] 프로파일 내보내기/가져오기

- [ ] **호환성 검사**
  - [ ] 컬럼 유효성 검사
  - [ ] 컬럼 자동 매핑
  - [ ] 경고 다이얼로그

### Phase 4: 마무리 (0.5주)

- [ ] **UX 개선**
  - [ ] 단축키 구현
  - [ ] 드래그 앤 드롭 재정렬
  - [ ] 컨텍스트 메뉴

- [ ] **테스트 및 문서화**
  - [ ] 단위 테스트
  - [ ] 통합 테스트
  - [ ] 사용자 가이드

---

## 참고사항

### 기존 시스템과의 통합

1. **Project 파일 (.dgs)**
   - 프로젝트에 활성 프로파일 참조 저장 가능
   - 프로파일 파일 경로 또는 임베드 선택

2. **기존 상태 관리 (AppState)**
   - 프로파일 관련 상태 추가
   - 기존 signal/slot 패턴 활용

3. **테마 시스템**
   - Profile Bar, Floating Window에 테마 적용
   - Light/Dark 모드 지원

### 성능 고려사항

1. **설정 전환 속도**
   - 그래프 설정 변경 시 최소 재계산
   - 캐시된 데이터 활용

2. **Floating Window 메모리**
   - 데이터 공유 (복사 X)
   - 창 닫을 때 리소스 해제

3. **프로파일 파일 크기**
   - JSON 압축 옵션
   - 대용량 필터 제외 옵션

---

*작성일: 2026-01-30*
*작성자: Claude Code*
