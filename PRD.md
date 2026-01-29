# Data Graph Studio - PRD (Product Requirements Document)

## 📋 개요

**제품명:** Data Graph Studio (가칭: GraphForge / DataViz Pro)

**한 줄 설명:** 1000만 행 이상의 빅데이터도 부드럽게, 드래그 앤 드롭으로 강력한 시각화를 만드는 도구

**타겟 사용자:**
- 데이터 분석가 (대용량 로그/트랜잭션 분석)
- 엔지니어 (성능 데이터, 시스템 로그 분석)
- 연구원 (대규모 실험 데이터 시각화)
- PM/기획자 (리포트 작성)

**핵심 가치:**
> "Excel의 피벗 테이블 + Tableau의 시각화 + 빅데이터 성능"

**핵심 차별점:**
| 기존 도구 | 한계 | Data Graph Studio |
|----------|------|-------------------|
| Excel | 100만 행 제한, 느림 | 1000만+ 행 지원 |
| Tableau | 비쌈, 무거움 | 가볍고 빠름 |
| Python/R | 코딩 필요 | 노코드 드래그앤드롭 |
| 웹 기반 도구 | 브라우저 한계 | 네이티브 성능 |

---

## 🎯 핵심 컨셉

### 메인 레이아웃 (3단 구조)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                              DATA GRAPH STUDIO                          │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │                        📊 SUMMARY PANEL                           │  │ 10%
│  │  Count: 10,523 │ Mean: 1,234 │ Median: 1,100 │ Std: 456 │ ...    │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│  ═══════════════════════════════════ ↕ 드래그로 높이 조절 ═══════════  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌─────────────────────────────────────┐  ┌────────────┐ │
│  │  GRAPH   │  │  🔍 ✋ ▢ 〰️ ✕ 🔄 ⊡  ← Graph Toolbar │  │   STAT     │ │
│  │  OPTIONS │  ├─────────────────────────────────────┤  │   PANEL    │ │
│  │          │  │                                     │  │            │ │
│  │ X-Axis   │  │                                     │  │ Histogram  │ │ 45%
│  │ Y-Axis   │  │         📈 MAIN GRAPH               │  │ Box Plot   │ │
│  │ Type     │  │                                     │  │ Violin     │ │
│  │ Style    │  │                                     │  │ Pie Chart  │ │
│  │          │  │                                     │  │ Heatmap    │ │
│  └──────────┘  └─────────────────────────────────────┘  └────────────┘ │
│  ═══════════════════════════════════ ↕ 드래그로 높이 조절 ═══════════  │
├─────────────────────────────────────────────────────────────────────────┤
│  ┌──────────┐  ┌─────────────────────────────────────┐  ┌────────────┐ │
│  │  GROUP   │  │                                     │  │   VALUE    │ │
│  │  ZONE    │  │           📋 TABLE VIEW             │  │   ZONE     │ │
│  │          │  │                                     │  │            │ │
│  │ ┌──────┐ │  │  Col1  │  Col2  │  Col3  │  Col4   │  │ ┌────────┐ │ │ 45%
│  │ │Region│ │  │  ───── │  ───── │  ───── │  ─────  │  │ │ Sales  │ │ │
│  │ └──────┘ │  │  ...   │  ...   │  ...   │  ...    │  │ │ (SUM)  │ │ │
│  │ ┌──────┐ │  │  ...   │  ...   │  ...   │  ...    │  │ └────────┘ │ │
│  │ │ Date │ │  │                                     │  │ ┌────────┐ │ │
│  │ └──────┘ │  │   ☑ Row 1  │  ☑ Row 2  │ ...       │  │ │ Count  │ │ │
│  │          │  │   ← 테이블 행 선택 가능             │  │ │ (AVG)  │ │ │
│  └──────────┘  └─────────────────────────────────────┘  └────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### 레이아웃 구조

| 영역 | 기본 높이 | 설명 |
|------|----------|------|
| **SUMMARY** | 10% | 텍스트 기반 통계 요약 |
| **GRAPH** | 45% | 메인 그래프 + 옵션 + 통계 차트 |
| **TABLE** | 45% | 데이터 테이블 + 그룹/밸류 존 |

### 높이 조절
- 각 영역 사이에 **드래그 핸들** (splitter)
- 드래그로 자유롭게 높이 비율 조절
- 더블 클릭 시 기본 비율로 리셋
- 최소 높이 제한 (각 영역 50px 이상)

---

## 🔗 양방향 선택 연동 (Bidirectional Selection)

### 핵심 개념
그래프와 테이블의 선택이 **실시간으로 동기화**됨.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│   GRAPH에서 선택                    TABLE에서 선택                  │
│   ┌─────────────┐                  ┌─────────────────┐              │
│   │    ●        │                  │ ☑ Row 1        │              │
│   │   ╱ ╲       │  ◄──────────►   │ ☑ Row 2        │              │
│   │  ●   ● ←선택│   양방향 동기화  │ ☐ Row 3        │              │
│   │ ╱     ╲     │                  │ ☑ Row 4        │              │
│   │●       ●    │                  │ ☐ Row 5        │              │
│   └─────────────┘                  └─────────────────┘              │
│                                                                     │
│   ● 선택된 포인트는 테이블에서         테이블에서 선택한 행은        │
│     자동으로 필터/하이라이트           그래프에서 하이라이트         │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 선택 동작

#### 그래프 → 테이블
| 그래프 동작 | 테이블 반응 |
|------------|------------|
| 포인트 클릭 | 해당 행 하이라이트 + 스크롤 |
| 영역 선택 (Rect/Lasso) | 해당 행들 필터링 (나머지 숨김) |
| 범례 클릭 | 해당 그룹 행들만 필터 |
| 선택 해제 | 필터 해제, 전체 표시 |

#### 테이블 → 그래프
| 테이블 동작 | 그래프 반응 |
|------------|------------|
| 행 클릭 | 해당 포인트 하이라이트 |
| 다중 행 선택 (Ctrl+클릭) | 해당 포인트들 하이라이트 |
| 범위 선택 (Shift+클릭) | 해당 포인트들 하이라이트 |
| 선택 해제 | 전체 포인트 일반 스타일 |

### 하이라이트 스타일
```
선택된 데이터:     강조 색상, 100% 불투명도, 크기 증가
선택되지 않은 데이터: 회색 처리, 30% 불투명도, 기본 크기
```

---

## 📊 Summary Panel

### 위치 및 역할
- 화면 **최상단**에 위치
- 현재 데이터의 **핵심 통계**를 한눈에 표시
- **동적 업데이트**: 선택/그룹화/필터 변경 시 자동 갱신

### 표시 정보

```
┌─────────────────────────────────────────────────────────────────────────┐
│  📊 SUMMARY                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                         │
│  📋 Data                     📈 Statistics (Value: Sales)              │
│  ─────────────────────       ─────────────────────────────────          │
│  Total Rows: 10,523          Sum:     $12,456,789                       │
│  Selected:   1,247 (11.8%)   Mean:    $1,184.25                         │
│  Filtered:   5,200           Median:  $980.00                           │
│  Groups:     15              Std Dev: $456.78                           │
│                              Min:     $10.00   Max: $15,000.00          │
│                              Q1:      $650.00  Q3:  $1,450.00           │
│                                                                         │
│  🏷️ Current Selection: Region=Asia, Category=Electronics (247 rows)    │
│                                                                         │
└─────────────────────────────────────────────────────────────────────────┘
```

### 업데이트 트리거

| 트리거 | Summary 반응 |
|--------|-------------|
| 데이터 로드 | 전체 데이터 통계 표시 |
| 필터 적용 | 필터된 데이터 통계로 업데이트 |
| 그래프/테이블 선택 | 선택된 데이터 통계로 업데이트 |
| Group Zone 변경 | 그룹별 통계 표시 |
| Value Zone 변경 | 해당 Value의 집계 통계 표시 |
| 선택 해제 | 전체 데이터 통계로 복귀 |

### Summary 컴포넌트

1. **Data Count**
   - Total Rows (전체)
   - Selected (선택된 행)
   - Filtered (필터 후)
   - Groups (그룹 수)

2. **Value Statistics** (Value Zone에 등록된 컬럼)
   - Sum, Mean, Median
   - Std Dev, Variance
   - Min, Max, Range
   - Q1, Q3, IQR
   - Percentiles

3. **Selection Context**
   - 현재 선택된 그룹/필터 조건 표시
   - 빠른 클리어 버튼

---

## 🛠️ Graph Toolbar (그래프 툴바)

### 위치
메인 그래프 **상단**에 아이콘 버튼 배치

### 툴바 구성

```
┌─────────────────────────────────────────────────────────────────────────┐
│  🔍   ✋   ▢   〰️   ✕   🔄   ⊡   │   💾   📋   ⚙️                      │
│  Zoom Move Rect Lasso Desel Reset Fit │  Save Copy Settings            │
│  ──────── Selection Tools ────────   │  ──── Actions ────              │
└─────────────────────────────────────────────────────────────────────────┘
```

### 버튼 상세

| 아이콘 | 이름 | 기능 | 단축키 |
|--------|------|------|--------|
| 🔍 | **Zoom** | 드래그로 영역 확대 | `Z` |
| ✋ | **Move/Pan** | 드래그로 그래프 이동 | `H` |
| ▢ | **Rect Select** | 사각형 드래그로 데이터 선택 | `R` |
| 〰️ | **Lasso Select** | 자유 곡선으로 데이터 선택 | `L` |
| ✕ | **Deselect** | 현재 선택 해제 | `Escape` |
| 🔄 | **Reset** | 줌/팬 초기화 (선택 유지) | `Home` |
| ⊡ | **Autofit** | 모든 데이터가 보이게 자동 맞춤 | `F` |

### 보조 버튼

| 아이콘 | 이름 | 기능 |
|--------|------|------|
| 💾 | **Save** | 그래프 이미지 저장 |
| 📋 | **Copy** | 클립보드에 복사 |
| ⚙️ | **Settings** | 그래프 설정 패널 토글 |

### 툴 동작 상세

#### 🔍 Zoom Tool
```
동작: 드래그로 확대할 영역 선택
      스크롤 휠로 확대/축소
      더블클릭으로 해당 지점 중심 확대

옵션: □ X축만   □ Y축만   ☑ 양방향
```

#### ✋ Move/Pan Tool
```
동작: 드래그로 그래프 영역 이동
      확대된 상태에서 탐색용

옵션: □ X축만   □ Y축만   ☑ 자유 이동
```

#### ▢ Rect Select Tool
```
동작: 드래그로 사각형 영역 그리기
      영역 내 모든 데이터 포인트 선택
      Shift+드래그: 기존 선택에 추가
      Ctrl+드래그: 기존 선택에서 제외
```

#### 〰️ Lasso Select Tool
```
동작: 자유롭게 곡선을 그려 영역 선택
      복잡한 형태의 데이터 군집 선택에 유용
      Shift/Ctrl 수정자 동일하게 적용
```

#### ✕ Deselect
```
동작: 모든 선택 해제
      테이블 필터도 함께 해제
      Summary는 전체 데이터 통계로 복귀
```

#### 🔄 Reset View
```
동작: 줌/팬을 초기 상태로 복원
      선택된 데이터는 유지
      X/Y축 범위 자동 계산
```

#### ⊡ Autofit
```
동작: 모든 데이터 포인트가 화면에 보이도록 자동 조정
      여백 10% 추가
      종횡비 유지 옵션
```

### 툴바 상태 표시
```
현재 활성 툴:  [🔍 Zoom] ← 선택된 툴 하이라이트
선택된 포인트: 247 / 10,523 (2.3%)
줌 레벨:      150%
```

---

## 🔧 기능 상세

### 1. 데이터 입력 (Data Input)

#### 1.1 지원 포맷
| 포맷 | 설명 |
|------|------|
| CSV | 구분자 자동 감지 (comma, tab, semicolon, pipe) |
| Excel | .xlsx, .xls (다중 시트 지원) |
| JSON | Array of objects, nested 구조 flatten 옵션 |
| Clipboard | 직접 붙여넣기 (테이블 형태 자동 인식) |
| Parquet | 대용량 데이터 지원 |
| SQLite | 로컬 DB 파일 직접 쿼리 |

#### 1.2 데이터 소스 연결 (Pro Feature)
- **URL Fetch:** REST API, CSV URL
- **Database:** PostgreSQL, MySQL, SQLite
- **Cloud:** Google Sheets, Notion DB
- **실시간:** WebSocket 스트리밍 데이터

#### 1.3 스마트 파싱
- 날짜/시간 포맷 자동 감지
- 숫자 포맷 자동 감지 (천단위 구분자, 소수점)
- 데이터 타입 추론 (문자열, 숫자, 날짜, 불리언)
- 헤더 행 자동 감지

---

### 2. 테이블 뷰 (Table View)

#### 2.1 기본 기능
| 기능 | 설명 | 단축키 |
|------|------|--------|
| **Search** | 전체 테이블 또는 특정 컬럼 검색 | `Ctrl+F` |
| **Filter** | 컬럼별 조건 필터 (다중 조건) | 컬럼 헤더 클릭 |
| **Sort** | 단일/다중 컬럼 정렬 | 컬럼 헤더 클릭 |
| **Reorder** | 드래그 앤 드롭으로 컬럼 순서 변경 | 드래그 |
| **Resize** | 컬럼 너비 조절 | 드래그 |
| **Hide/Show** | 컬럼 숨기기/보이기 | 우클릭 메뉴 |
| **Freeze** | 컬럼 고정 (스크롤 시 유지) | 우클릭 메뉴 |

#### 2.2 필터 조건
```
문자열: contains, equals, starts with, ends with, regex, is empty
숫자: =, ≠, >, <, ≥, ≤, between, is null
날짜: before, after, between, last N days/weeks/months
불리언: is true, is false
```

#### 2.3 계산 필드 (Calculated Fields)
사용자가 수식으로 새로운 컬럼 생성:
```javascript
// 예시
Price * Quantity                    // 기본 연산
CONCAT(FirstName, " ", LastName)    // 문자열 결합
DATE_DIFF(EndDate, StartDate)       // 날짜 차이
IF(Sales > 1000, "High", "Low")     // 조건부
ROUND(Value, 2)                     // 반올림
EXTRACT(Timestamp, "hour")          // 시간 추출
```

#### 2.4 데이터 변환
- **타입 변환:** 문자열 ↔ 숫자, 문자열 → 날짜
- **텍스트:** UPPER, LOWER, TRIM, SPLIT
- **날짜:** 포맷 변경, 시간대 변환
- **숫자:** 반올림, 천단위 포맷
- **One-Hot Encoding:** 카테고리 → 0/1 컬럼들
- **Binning:** 연속 값을 구간으로 분류

---

### 3. 그룹 존 (Group Zone) - 왼쪽 패널

#### 3.1 동작 방식
1. 테이블에서 컬럼을 **드래그**하여 Group Zone에 **드롭**
2. 여러 컬럼 드롭 시 **계층적 그룹화** (순서 중요)
3. 그룹은 그래프에서 **Legend Item**이 됨

#### 3.2 그룹 옵션
```
┌─────────────────────────┐
│  GROUP ZONE             │
├─────────────────────────┤
│  ┌───────────────────┐  │
│  │ 📁 Region      ⋮  │  │  ← 드래그로 순서 변경
│  │    ├─ Asia        │  │
│  │    ├─ Europe      │  │
│  │    └─ America     │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ 📁 Category    ⋮  │  │
│  │    ├─ Electronics │  │
│  │    └─ Clothing    │  │
│  └───────────────────┘  │
│                         │
│  [+ Add Group]          │
└─────────────────────────┘
```

#### 3.3 그룹 필터
- 체크박스로 특정 그룹 값만 선택
- 검색으로 그룹 필터링
- "Top N" 또는 "Others" 그룹화

---

### 4. 밸류 존 (Value Zone) - 오른쪽 패널

#### 4.1 동작 방식
1. 숫자 컬럼을 **드래그**하여 Value Zone에 **드롭**
2. 각 Value에 **집계 함수** 선택
3. 여러 Value 드롭 시 **다중 Y축** 또는 **스택**

#### 4.2 집계 함수
| 함수 | 설명 |
|------|------|
| SUM | 합계 |
| AVG | 평균 |
| MEDIAN | 중앙값 |
| COUNT | 개수 |
| COUNT DISTINCT | 고유 값 개수 |
| MIN | 최솟값 |
| MAX | 최댓값 |
| STDEV | 표준편차 |
| VAR | 분산 |
| FIRST | 첫 번째 값 |
| LAST | 마지막 값 |
| PERCENTILE(N) | N 백분위수 |

#### 4.3 밸류 옵션
```
┌─────────────────────────┐
│  VALUE ZONE             │
├─────────────────────────┤
│  ┌───────────────────┐  │
│  │ 💰 Sales       ⋮  │  │
│  │    Agg: [SUM ▼]   │  │
│  │    Format: $#,##0 │  │
│  │    Color: 🔵      │  │
│  └───────────────────┘  │
│  ┌───────────────────┐  │
│  │ 📊 Profit      ⋮  │  │
│  │    Agg: [AVG ▼]   │  │
│  │    Format: $#,##0 │  │
│  │    Color: 🟢      │  │
│  │    Axis: [Secondary]│ │
│  └───────────────────┘  │
│                         │
│  [+ Add Value]          │
└─────────────────────────┘
```

---

### 5. 메인 그래프 (Main Graph)

#### 5.1 그래프 타입

**기본 차트:**
| 타입 | 용도 |
|------|------|
| Line | 시계열, 추세 |
| Area | 누적 추세, 비율 변화 |
| Bar (Vertical) | 범주 비교 |
| Bar (Horizontal) | 긴 레이블, 순위 |
| Scatter | 상관관계, 분포 |
| Bubble | 3차원 비교 (x, y, size) |

**통계 차트:**
| 타입 | 용도 |
|------|------|
| Box Plot | 분포, 이상치 |
| Violin | 밀도 분포 |
| Histogram | 빈도 분포 |
| Density | 확률 밀도 |
| Error Bar | 불확실성 |

**비율 차트:**
| 타입 | 용도 |
|------|------|
| Pie | 비율 (항목 ≤7) |
| Donut | 비율 + 중앙 정보 |
| Treemap | 계층적 비율 |
| Sunburst | 계층적 비율 (방사형) |
| Sankey | 흐름, 전환 |

**특수 차트:**
| 타입 | 용도 |
|------|------|
| Heatmap | 2차원 밀도, 상관관계 |
| Radar | 다차원 비교 |
| Candlestick | 주가, OHLC |
| Waterfall | 누적 변화 |
| Funnel | 전환율 |
| Gauge | 단일 KPI |

#### 5.2 그래프 옵션 패널 (왼쪽)

```
┌─────────────────────────┐
│  GRAPH OPTIONS          │
├─────────────────────────┤
│  📊 Chart Type          │
│  [Line Chart      ▼]    │
│                         │
│  📏 X-Axis              │
│  Column: [Date    ▼]    │
│  Scale: [Linear   ▼]    │
│  Label Rotation: 45°    │
│                         │
│  📐 Y-Axis              │
│  Scale: [Linear   ▼]    │
│  Range: [Auto ▼]        │
│  □ Secondary Y-Axis     │
│                         │
│  🎨 Style               │
│  Line Width: ━━━ [2]    │
│  Marker Size: ● [6]     │
│  Marker Shape: [●▼]     │
│  Fill Opacity: ▓░ [0.3] │
│  Curve: [Smooth   ▼]    │
│                         │
│  📍 Data Labels         │
│  □ Show Values          │
│  Position: [Top   ▼]    │
│                         │
│  🏷️ Legend              │
│  Position: [Right  ▼]   │
│  □ Interactive          │
│                         │
│  🎯 Interactions        │
│  ☑ Tooltip              │
│  ☑ Zoom/Pan             │
│  □ Crosshair            │
│  ☑ Brush Selection      │
└─────────────────────────┘
```

#### 5.3 그래프 타입별 특수 옵션

**Line Chart:**
- Interpolation: Linear / Smooth / Step
- Show Points: Always / Hover / Never
- Connect Nulls: Yes / No

**Bar Chart:**
- Orientation: Vertical / Horizontal
- Stacked: None / Stacked / 100% Stacked
- Bar Width: 0.1 ~ 1.0
- Gap: 0 ~ 1.0

**Scatter:**
- Bubble Mode: Size encoding
- Trendline: None / Linear / Polynomial / Exponential
- Jitter: Add noise for overlapping points

**Heatmap:**
- Color Scale: Sequential / Diverging
- Cell Labels: Show / Hide
- Cluster: Row / Column / Both

---

### 6. 통계 패널 (Stat Panel) - 그래프 오른쪽

메인 그래프의 데이터를 다양한 관점으로 보여주는 보조 차트들.

#### 6.1 패널 구성

```
┌─────────────────────────┐
│  STAT PANEL             │
├─────────────────────────┤
│  ┌───────────────────┐  │
│  │  X-Axis Dist.     │  │
│  │  ┌─────────────┐  │  │
│  │  │ ▓▓▓▓▓▓░░░░░ │  │  │  ← X축 값 분포 (Histogram)
│  │  └─────────────┘  │  │
│  │  [Histogram ▼]    │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │  Y-Axis Dist.     │  │
│  │  ┌─────────────┐  │  │
│  │  │   ┃━━━┃     │  │  │  ← Y축 값 분포 (Box Plot)
│  │  │   ┃   ┃     │  │  │
│  │  └─────────────┘  │  │
│  │  [Box Plot  ▼]    │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │  Composition      │  │
│  │     ╭───╮         │  │
│  │    ╱     ╲        │  │  ← 구성비 (Pie/Donut)
│  │   ╲  35%  ╱       │  │
│  │    ╲     ╱        │  │
│  │     ╰───╯         │  │
│  │  [Pie Chart ▼]    │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │  Correlation      │  │
│  │  ┌─────────────┐  │  │
│  │  │ ░▒▓█▓▒░     │  │  │  ← 상관관계 (Heatmap)
│  │  │ ▒▓█▓▒░░     │  │  │
│  │  └─────────────┘  │  │
│  │  [Heatmap   ▼]    │  │
│  └───────────────────┘  │
│                         │
│  ┌───────────────────┐  │
│  │  Summary Stats    │  │
│  │  ───────────────  │  │
│  │  Mean:    1,234   │  │
│  │  Median:  1,100   │  │
│  │  Std Dev:   456   │  │
│  │  Min:       100   │  │
│  │  Max:     5,000   │  │
│  │  Q1:        800   │  │
│  │  Q3:      1,500   │  │
│  └───────────────────┘  │
└─────────────────────────┘
```

#### 6.2 Stat Panel 차트 옵션
- **X-Axis Distribution:** Histogram, Density, Rug Plot
- **Y-Axis Distribution:** Histogram, Box Plot, Violin, Strip
- **Composition:** Pie, Donut, Waffle
- **Correlation:** Heatmap, Scatter Matrix
- **Summary:** Statistics Card, Sparkline

#### 6.3 연동 기능
- 메인 그래프에서 **브러시 선택** → Stat Panel 자동 업데이트
- Stat Panel 클릭 → 메인 그래프 **하이라이트**
- 양방향 필터링

---

### 7. 인터랙션 & UX

#### 7.1 드래그 앤 드롭

```
┌─────────────────────────────────────────┐
│  Table Column Header                    │
│  ┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐       │
│  │ A   │ │ B   │ │ C   │ │ D   │       │
│  └──┬──┘ └─────┘ └─────┘ └─────┘       │
│     │                                   │
│     │ 드래그                            │
│     ▼                                   │
│  ┌─────────┐          ┌─────────┐      │
│  │ GROUP   │    OR    │  VALUE  │      │
│  │  ZONE   │          │  ZONE   │      │
│  │         │          │         │      │
│  │ [Drop!] │          │ [Drop!] │      │
│  └─────────┘          └─────────┘      │
└─────────────────────────────────────────┘
```

#### 7.2 단축키

| 키 | 동작 |
|----|------|
| `Ctrl+O` | 파일 열기 |
| `Ctrl+V` | 클립보드 붙여넣기 |
| `Ctrl+S` | 프로젝트 저장 |
| `Ctrl+E` | 그래프 내보내기 |
| `Ctrl+Z/Y` | Undo / Redo |
| `Ctrl+F` | 검색 |
| `Ctrl+G` | 그래프 뷰로 전환 |
| `Ctrl+T` | 테이블 뷰로 전환 |
| `Ctrl+1~9` | 그래프 타입 전환 |
| `Space` | 그래프 줌 리셋 |
| `Escape` | 선택 해제 |

#### 7.3 컨텍스트 메뉴 (우클릭)

**테이블 헤더:**
- Sort Ascending / Descending
- Filter...
- Hide Column
- Freeze Column
- Create Calculated Field...
- Change Data Type
- Rename

**테이블 셀:**
- Copy
- Filter by this value
- Highlight matching
- Drill down

**그래프:**
- Export as PNG / SVG / PDF
- Copy to clipboard
- Reset zoom
- Show data table
- Annotate...

#### 7.4 툴팁

```
┌──────────────────────┐
│  📍 Data Point       │
│  ────────────────    │
│  Region: Asia        │
│  Date: 2024-01-15    │
│  Sales: $12,500      │
│  Growth: +15.3%      │
│  ────────────────    │
│  Click to drill down │
└──────────────────────┘
```

---

## ⚡ 빅데이터 처리 (Big Data Performance)

> **핵심 목표:** 1000만 행 이상의 데이터도 부드럽게 처리

### 성능 목표

| 데이터 크기 | 로딩 시간 | 그래프 렌더링 | 필터/정렬 | 메모리 사용 |
|------------|----------|--------------|----------|------------|
| 10만 행 | < 1초 | < 0.5초 | < 0.3초 | < 200MB |
| 100만 행 | < 5초 | < 1초 | < 1초 | < 1GB |
| 1000만 행 | < 30초 | < 2초 | < 3초 | < 4GB |
| 1억 행 | 스트리밍 | 샘플링 | 인덱스 | 디스크 기반 |

---

### 8. 데이터 로딩 전략

#### 8.1 청크 기반 로딩 (Chunked Loading)
```
┌─────────────────────────────────────────────────────────────┐
│  📂 Loading: sales_data.csv (2.5GB)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Strategy: Chunked Loading (1M rows per chunk)              │
│                                                             │
│  [████████████░░░░░░░░░░░░░░░░░] 42%                        │
│                                                             │
│  Chunk 5/12 loading...                                      │
│  Rows loaded: 4,200,000 / 10,000,000                        │
│  Memory: 1.2GB / 8GB available                              │
│  ETA: 15 seconds                                            │
│                                                             │
│  ☑ Start analyzing while loading (progressive)              │
│  □ Load entire file before processing                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 8.2 프로그레시브 로딩
- 첫 N개 행 즉시 표시 (프리뷰)
- 백그라운드에서 나머지 로딩
- 로딩 중에도 탐색/필터 가능 (로딩된 범위 내)
- 진행률 표시 + 취소 가능

#### 8.3 지연 로딩 (Lazy Loading)
- 필요한 컬럼만 메모리에 로드
- 사용하지 않는 컬럼은 디스크에 유지
- 접근 시 자동으로 로드

---

### 9. 메모리 최적화

#### 9.1 데이터 타입 최적화
```python
# 자동 타입 다운캐스팅
Original:  int64  (8 bytes) → Optimized: int16 (2 bytes)  # 75% 절감
Original: float64 (8 bytes) → Optimized: float32 (4 bytes) # 50% 절감
Original:  object (variable) → Optimized: category (index)  # 90%+ 절감

# 예시: 1000만 행 × 20 컬럼
Before optimization: 3.2GB
After optimization:  0.4GB (87% 절감)
```

#### 9.2 메모리 관리 전략
| 전략 | 설명 |
|------|------|
| **Type Inference** | 로드 시 최적 타입 자동 감지 |
| **Categorical Encoding** | 반복 문자열을 정수 인덱스로 |
| **Sparse Storage** | NULL/0이 많은 컬럼 희소 저장 |
| **Memory Mapping** | 대용량 파일 mmap으로 가상 메모리 사용 |
| **LRU Cache** | 최근 사용 데이터 캐시, 오래된 것 해제 |
| **Garbage Collection** | 미사용 데이터 주기적 해제 |

#### 9.3 메모리 모니터
```
┌─────────────────────────────────────┐
│  💾 Memory Usage                    │
├─────────────────────────────────────┤
│  ████████████░░░░░ 2.1GB / 8GB      │
│                                     │
│  Data:      1.8GB (85%)             │
│  Cache:     0.2GB (10%)             │
│  UI:        0.1GB (5%)              │
│                                     │
│  ⚠️ High memory usage               │
│  [Optimize] [Clear Cache]           │
└─────────────────────────────────────┘
```

---

### 10. 렌더링 최적화

#### 10.1 가상 스크롤 (Virtual Scrolling)
```
┌─────────────────────────────────────────────────────────────┐
│  실제 렌더링되는 영역 (Viewport)                            │
│  ─────────────────────────────────────────────────────────  │
│                                                             │
│  ┌─ 버퍼 (위) ─┐                                            │
│  │  Row 995    │  ← 화면 밖이지만 미리 렌더링              │
│  │  Row 996    │                                           │
│  ├─────────────┼─────────────────────────────────────────  │
│  │  Row 997    │  ← ┐                                      │
│  │  Row 998    │    │                                      │
│  │  Row 999    │    │ 화면에 보이는 행만 DOM에 존재        │
│  │  Row 1000   │    │ (예: 20개 행)                        │
│  │  Row 1001   │    │                                      │
│  │  Row 1002   │  ← ┘                                      │
│  ├─────────────┼─────────────────────────────────────────  │
│  │  Row 1003   │  ← 버퍼 (아래)                            │
│  │  Row 1004   │                                           │
│  └─────────────┘                                            │
│                                                             │
│  전체: 10,000,000 행  │  렌더링: ~30 행  │  스크롤: 부드러움│
└─────────────────────────────────────────────────────────────┘
```

#### 10.2 그래프 샘플링 (Graph Sampling)
```
┌─────────────────────────────────────────────────────────────┐
│  📊 Rendering Strategy                                      │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Data points: 5,000,000                                     │
│  Visible area can show: ~2,000 points effectively          │
│                                                             │
│  ☑ Smart Sampling (recommended)                             │
│     → Show 10,000 representative points                     │
│     → Preserve outliers and distribution                    │
│     → Full data used for calculations                       │
│                                                             │
│  □ Aggregation                                              │
│     → Bin data into 1,000 buckets                          │
│     → Show min/max/avg per bucket                          │
│                                                             │
│  □ Progressive Rendering                                    │
│     → Start with 1,000 points                              │
│     → Add detail on zoom                                   │
│                                                             │
│  ⚠️ Showing all points may cause performance issues         │
│  □ Force render all (not recommended)                       │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 10.3 샘플링 알고리즘

| 알고리즘 | 설명 | 용도 |
|---------|------|------|
| **LTTB** | Largest Triangle Three Buckets | 시계열, 추세 유지 |
| **Random** | 무작위 샘플링 | 분포 분석 |
| **Stratified** | 그룹별 비율 유지 샘플링 | 범주형 데이터 |
| **Reservoir** | 스트리밍 데이터 샘플링 | 실시간 데이터 |
| **Min-Max** | 구간별 최소/최대 유지 | 이상치 보존 |

#### 10.4 WebGL 렌더링
- Canvas 2D 한계: ~10,000 포인트
- WebGL 사용: ~1,000,000+ 포인트
- GPU 가속으로 부드러운 인터랙션
- Scatter, Heatmap에 특히 효과적

---

### 11. 연산 최적화

#### 11.1 증분 계산 (Incremental Computation)
```
필터 변경 시:
─────────────────────────────────────────────────────
❌ 나쁜 방식: 전체 데이터 재계산
   → 1000만 행 × 20 컬럼 = 매번 수 초

✅ 좋은 방식: 변경된 부분만 계산
   → 추가된 행만 통계에 반영
   → 제거된 행만 통계에서 차감
   → 밀리초 단위 응답
─────────────────────────────────────────────────────
```

#### 11.2 백그라운드 처리 (Web Workers / Threading)
```
┌──────────────────┐     ┌──────────────────┐
│    Main Thread   │     │  Worker Thread   │
│    (UI 담당)     │     │  (연산 담당)     │
├──────────────────┤     ├──────────────────┤
│                  │     │                  │
│  사용자 인터랙션 │ ──► │  필터/정렬/집계  │
│  그래프 렌더링   │ ◄── │  통계 계산       │
│  애니메이션     │     │  데이터 변환     │
│                  │     │                  │
│  ✅ 항상 반응    │     │  ⏳ 무거운 작업  │
└──────────────────┘     └──────────────────┘

UI는 절대 멈추지 않음!
```

#### 11.3 캐싱 전략

| 캐시 레벨 | 대상 | 무효화 조건 |
|----------|------|------------|
| **L1** | 현재 뷰 통계 | 필터/선택 변경 |
| **L2** | 컬럼별 통계 | 데이터 변경 |
| **L3** | 정렬 인덱스 | 데이터 추가/삭제 |
| **L4** | 렌더링 결과 | 줌/팬/리사이즈 |

#### 11.4 인덱싱
```
대용량 데이터 필터/검색 최적화:

┌─────────────────────────────────────────────────────────┐
│  Column: "Region" (1000만 행)                           │
├─────────────────────────────────────────────────────────┤
│  Without Index:  Full scan → 2.5초                      │
│  With Index:     Hash lookup → 0.01초                   │
├─────────────────────────────────────────────────────────┤
│  자동 인덱스 생성:                                       │
│  ☑ Group Zone 컬럼                                       │
│  ☑ 자주 필터되는 컬럼                                    │
│  ☑ 정렬 기준 컬럼                                        │
└─────────────────────────────────────────────────────────┘
```

---

### 12. 데이터 엔진 선택

#### 12.1 권장 기술 스택

| 컴포넌트 | 기술 | 이유 |
|---------|------|------|
| **Data Engine** | Polars / DuckDB | Pandas 대비 10-100x 빠름 |
| **File Format** | Parquet / Arrow | 컬럼 기반, 압축, 빠른 로딩 |
| **In-Memory** | Apache Arrow | 제로카피 데이터 공유 |
| **Query** | SQL (DuckDB) | 익숙한 문법, 최적화된 실행 |
| **Streaming** | Polars Lazy | 필요한 것만 처리 |

#### 12.2 Polars vs Pandas 비교

```
작업: 1000만 행 CSV 로드 + 그룹별 집계

┌────────────────┬──────────┬──────────┬───────────┐
│ 작업           │ Pandas   │ Polars   │ 개선율    │
├────────────────┼──────────┼──────────┼───────────┤
│ CSV 로드       │ 45초     │ 3초      │ 15x       │
│ 필터           │ 2.1초    │ 0.08초   │ 26x       │
│ 그룹 집계      │ 8.5초    │ 0.3초    │ 28x       │
│ 정렬           │ 12초     │ 0.8초    │ 15x       │
│ 메모리 사용    │ 4.2GB    │ 1.1GB    │ 4x 절감   │
└────────────────┴──────────┴──────────┴───────────┘
```

#### 12.3 Lazy Evaluation (지연 평가)
```python
# Eager (즉시 실행) - 메모리 많이 사용
df = pl.read_csv("huge.csv")           # 전체 로드
df = df.filter(col("year") > 2020)     # 필터 실행
df = df.group_by("region").agg(...)    # 집계 실행
result = df.select(...)                 # 선택 실행

# Lazy (지연 실행) - 최적화됨
result = (
    pl.scan_csv("huge.csv")            # 쿼리 계획만
    .filter(col("year") > 2020)        # 쿼리 계획 추가
    .group_by("region").agg(...)       # 쿼리 계획 추가
    .select(...)                        # 쿼리 계획 추가
    .collect()                          # 최적화 후 한번에 실행!
)

# Lazy가 더 빠른 이유:
# 1. 필요한 컬럼만 로드
# 2. 필터를 먼저 적용 (데이터 감소)
# 3. 연산 순서 최적화
# 4. 병렬 처리 자동 적용
```

---

### 13. 대용량 파일 처리 UI/UX

#### 13.1 로딩 경험
```
┌─────────────────────────────────────────────────────────────┐
│  📂 Large File Detected                                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  File: transactions_2024.csv                                │
│  Size: 4.2 GB (~50,000,000 rows estimated)                 │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  ⚡ Recommended: Smart Loading                       │   │
│  │     • Load first 100,000 rows for preview           │   │
│  │     • Index key columns in background               │   │
│  │     • Query remaining data on-demand                │   │
│  │     [Start Smart Loading]                           │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  □ Load entire file (may take several minutes)             │
│  □ Sample 1% of data (500,000 rows)                        │
│  □ Connect as database (keep on disk)                      │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

#### 13.2 성능 경고
```
⚠️ Performance Warning
───────────────────────────────────────
Showing all 5,000,000 points on graph
may cause slow interactions.

Recommendations:
• Enable sampling (show 10,000 points)
• Use aggregation view
• Filter data first

[ Enable Sampling ] [ Aggregate ] [ Ignore ]
```

#### 13.3 진행률 & 취소
- 모든 장시간 작업에 진행률 표시
- 언제든 취소 가능
- 백그라운드 작업 상태 표시

---

### 14. 내보내기 & 공유

#### 8.1 그래프 내보내기
| 포맷 | 용도 |
|------|------|
| PNG | 일반 이미지 (고해상도 옵션) |
| SVG | 벡터 (편집 가능) |
| PDF | 인쇄용 |
| HTML | 인터랙티브 (Plotly 기반) |
| JSON | 그래프 설정 (재사용) |

#### 8.2 데이터 내보내기
- **CSV:** 필터/가공된 데이터
- **Excel:** 스타일 포함
- **JSON:** 구조화된 데이터
- **SQL:** INSERT 문 생성

#### 8.3 프로젝트 저장
`.dgs` (Data Graph Studio) 파일:
- 원본 데이터 (또는 데이터 소스 연결 정보)
- 모든 변환/필터 설정
- 그래프 설정
- 레이아웃

#### 8.4 템플릿
- 자주 쓰는 그래프 설정을 템플릿으로 저장
- 커뮤니티 템플릿 공유 (Pro)

---

### 9. 추가 기능 (클로 아이디어 💡)

#### 9.1 🤖 AI 추천 (Smart Suggestions)
```
┌─────────────────────────────────────┐
│  💡 AI Suggestions                  │
├─────────────────────────────────────┤
│  Based on your data, we recommend: │
│                                     │
│  📊 "Sales by Region" looks best   │
│     as a Bar Chart                  │
│     [Apply]                         │
│                                     │
│  ⚠️ Outlier detected in "Sales"    │
│     Row 45: $999,999 (3σ away)     │
│     [Investigate] [Exclude]         │
│                                     │
│  📈 Strong correlation found        │
│     between "Ads" and "Sales"       │
│     (r = 0.87)                      │
│     [Show Scatter Plot]             │
└─────────────────────────────────────┘
```

#### 9.2 📊 대시보드 모드
- 여러 그래프를 한 캔버스에 배치
- 그리드 레이아웃
- 공유 필터 (하나 필터 변경 → 전체 업데이트)
- 슬라이드쇼 모드 (발표용)

#### 9.3 🔄 데이터 새로고침
- 연결된 데이터 소스 자동 새로고침
- 스케줄링 (매 시간, 매일)
- 변경 감지 알림

#### 9.4 📝 주석 & 마크업
- 그래프에 텍스트 박스 추가
- 화살표, 원, 사각형 그리기
- 특정 데이터 포인트 하이라이트
- 프레젠테이션 모드

#### 9.5 🔍 데이터 프로파일링
파일 로드 시 자동 생성:
```
┌─────────────────────────────────────┐
│  📋 Data Profile                    │
├─────────────────────────────────────┤
│  Rows: 10,523  │  Columns: 15       │
│                                     │
│  Column        Type     Missing    │
│  ─────────────────────────────────  │
│  ID            int      0 (0%)     │
│  Name          string   12 (0.1%)  │
│  Date          datetime 0 (0%)     │
│  Sales         float    45 (0.4%)  │
│  Region        category 0 (0%)     │
│  ⚠️ Revenue   string   0 (0%)     │
│     → Detected as number, convert? │
└─────────────────────────────────────┘
```

#### 9.6 ⏱️ 시계열 특화 기능
- 기간 선택 슬라이더
- 이동 평균 오버레이
- 시즌성 분해 (Decomposition)
- 비교: 전년 대비, 전월 대비

#### 9.7 🎨 테마 & 브랜딩
- 다크 모드 / 라이트 모드
- 컬러 팔레트 커스터마이즈
- 회사 로고 삽입
- 커스텀 폰트

#### 9.8 ⚡ 성능 최적화
- 대용량 데이터 (100만+ 행) 샘플링 렌더링
- 가상 스크롤 테이블
- WebGL 기반 그래프 (대량 포인트)
- 백그라운드 연산 (Web Worker)

---

## 🏗️ 기술 스택 (제안)

### Option A: Desktop App (권장 ⭐)
```
┌─────────────────────────────────────────────────────────────┐
│  🖥️ Desktop App - 빅데이터 최적화                          │
├─────────────────────────────────────────────────────────────┤
│  Framework:   Python 3.11+ + PySide6 (Qt 6)                 │
│  Data Engine: Polars (primary) + DuckDB (SQL queries)       │
│  Charts:      PyQtGraph (real-time) + Plotly (export)       │
│  Table:       QTableView + Virtual Scrolling                │
│  Threading:   QThread + concurrent.futures                  │
│  Package:     PyInstaller / Nuitka → 단일 exe               │
├─────────────────────────────────────────────────────────────┤
│  ✅ 장점:                                                    │
│  • 네이티브 성능 (메모리 직접 제어)                          │
│  • 멀티코어 활용 (Python GIL 우회 가능)                      │
│  • 대용량 파일 mmap 지원                                     │
│  • 오프라인 사용 가능                                        │
└─────────────────────────────────────────────────────────────┘
```

### Option B: Web App (Tauri 기반)
```
┌─────────────────────────────────────────────────────────────┐
│  🌐 Web App with Native Backend                             │
├─────────────────────────────────────────────────────────────┤
│  Frontend:    React + TypeScript + Vite                     │
│  Backend:     Rust (Tauri) or Python (PyO3)                 │
│  Data:        DuckDB-WASM (light) / Polars (heavy)          │
│  Charts:      Apache ECharts (WebGL) / Plotly.js            │
│  Table:       TanStack Virtual + AG Grid                    │
│  State:       Zustand + React Query                         │
├─────────────────────────────────────────────────────────────┤
│  ✅ 장점:                                                    │
│  • 크로스 플랫폼 (Win/Mac/Linux)                            │
│  • 현대적 UI/UX                                              │
│  • Rust 백엔드로 빠른 연산                                   │
└─────────────────────────────────────────────────────────────┘
```

### 빅데이터 처리 핵심 라이브러리

| 역할 | 라이브러리 | 선택 이유 |
|------|-----------|----------|
| **Data Engine** | Polars | Pandas 대비 10-100x 빠름, Rust 기반 |
| **SQL Query** | DuckDB | 메모리 효율적, 분석 특화 |
| **File I/O** | Apache Arrow | 제로카피, 컬럼 기반 |
| **Large CSV** | Polars scan_csv | 지연 평가, 스트리밍 |
| **Parquet** | PyArrow | 압축, 빠른 로딩 |
| **Visualization** | PyQtGraph | 100만+ 포인트 실시간 |
| **WebGL Charts** | regl-scatterplot | 1000만+ 포인트 |

---

## 📅 개발 로드맵

### Phase 1: Core + Big Data Foundation (5주)
- [ ] **데이터 엔진 구축**
  - [ ] Polars 기반 데이터 로더
  - [ ] 청크 로딩 + 프로그레시브 UI
  - [ ] 타입 자동 감지 + 최적화
- [ ] **테이블 뷰**
  - [ ] 가상 스크롤 (100만 행 대응)
  - [ ] 검색, 필터, 정렬 (인덱스 활용)
  - [ ] 컬럼 드래그 재정렬
- [ ] **기본 구조**
  - [ ] 3단 레이아웃 (Summary/Graph/Table)
  - [ ] Group Zone / Value Zone 드래그 앤 드롭
  - [ ] 영역 리사이즈 (드래그 핸들)

### Phase 2: Visualization + Interaction (4주)
- [ ] **그래프 엔진**
  - [ ] 샘플링 렌더링 (LTTB 알고리즘)
  - [ ] 기본 차트 6종 (Line, Bar, Scatter, Area, Pie, Heatmap)
  - [ ] WebGL 가속 (대량 포인트)
- [ ] **그래프 툴바**
  - [ ] Zoom, Pan, Rect Select, Lasso Select
  - [ ] Deselect, Reset, Autofit
- [ ] **양방향 연동**
  - [ ] 그래프 선택 ↔ 테이블 필터
  - [ ] Summary 동적 업데이트
- [ ] **Stat Panel**
  - [ ] Histogram, Box Plot, Violin
  - [ ] Summary Statistics 카드

### Phase 3: Advanced Features (4주)
- [ ] **고급 테이블**
  - [ ] 계산 필드 (수식 엔진)
  - [ ] 피벗 테이블 모드
- [ ] **고급 그래프**
  - [ ] 다중 Y축
  - [ ] Candlestick, Waterfall, Funnel
  - [ ] Trendline, 이동평균
- [ ] **성능 최적화**
  - [ ] 백그라운드 워커 (연산 분리)
  - [ ] 캐싱 레이어 (L1-L4)
  - [ ] 증분 계산
- [ ] **저장/내보내기**
  - [ ] 프로젝트 파일 (.dgs)
  - [ ] PNG/SVG/PDF/HTML 내보내기

### Phase 4: Pro + Polish (3주)
- [ ] 대시보드 모드 (다중 그래프)
- [ ] 데이터 소스 연결 (DB, URL)
- [ ] 다크 모드 / 테마
- [ ] 단축키 전체 구현
- [ ] 튜토리얼 / 온보딩
- [ ] 성능 벤치마크 + 최적화

**총 예상 기간: 16주 (4개월)**

---

## 🎯 성공 지표

1. **효율성:** Excel에서 동일 작업 대비 50% 시간 단축
2. **학습 곡선:** 5분 내 첫 그래프 생성 가능
3. **유연성:** 어떤 테이블 데이터든 5번의 클릭/드래그로 시각화
4. **성능:** 10만 행 데이터 1초 내 로드, 그래프 렌더링 0.5초 이내

---

## 💡 네이밍 후보

| 이름 | 느낌 |
|------|------|
| **GraphForge** | 강력함, 제작 |
| **DataViz Studio** | 명확함, 전문성 |
| **ChartCraft** | 장인정신, 창작 |
| **Tabular** | 테이블 중심 |
| **PlotPilot** | 가벼움, 조종 |
| **DataLens** | 분석, 관찰 |
| **InsightForge** | 인사이트 도출 |

---

## 📎 참고 자료

- Tableau: 드래그 앤 드롭 UX 참고
- Observable Plot: 문법 간결함
- Grafana: 대시보드 레이아웃
- Superset: 오픈소스 BI 참고
- RAWGraphs: 특수 차트 참고

---

*최초 작성: 2026-01-29*
*작성자: 클로 + 고돌*
