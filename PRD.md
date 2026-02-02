# PRD: Project Explorer (프로젝트 탐색창)

## 1. 목표
왼쪽 데이터셋 패널을 IDE 스타일의 **프로젝트 탐색창**으로 개편하여, 데이터셋(프로젝트)과 그래프 프로파일을 트리 구조로 관리한다.

## 2. 배경
- 현재: 데이터셋 목록이 개별 카드 형태로 표시됨
- 문제: 그래프 설정을 저장/재사용하기 어려움
- 목표: VS Code, PyCharm 등의 프로젝트 탐색창처럼 직관적인 트리 구조 제공

## 3. 요구사항

### 3.1 기능 요구사항 (Functional Requirements)

#### FR-1: 트리 구조 UI
- [ ] FR-1.1: 데이터셋을 최상위 항목(프로젝트)으로 표시
- [ ] FR-1.2: 프로젝트명 우측에 ▶/▼ 토글 표시
- [ ] FR-1.3: 토글 클릭 시 프로파일 목록 펼침/접음
- [ ] FR-1.4: 활성 프로젝트 시각적 강조 (배경색 또는 볼드)

#### FR-2: 프로파일 표시
- [ ] FR-2.1: 프로파일 항목에 차트 타입 아이콘 표시
- [ ] FR-2.2: 프로파일 이름 표시
- [ ] FR-2.3: 형식: `📈 Line | Profile Name` 또는 `📊 Bar | Profile Name`
- [ ] FR-2.4: 프로파일 클릭 시 즉시 그래프 설정 적용

#### FR-3: 프로파일 생성
- [ ] FR-3.1: 펼쳐진 프로파일 목록 상단에 `+ 새 프로파일` 버튼
- [ ] FR-3.2: 버튼 클릭 시 현재 그래프 설정을 새 프로파일로 저장
- [ ] FR-3.3: 프로파일 이름 입력 다이얼로그
- [ ] FR-3.4: 프로파일은 해당 데이터셋에 귀속

#### FR-4: 프로파일 관리
- [ ] FR-4.1: 프로파일 우클릭 컨텍스트 메뉴
- [ ] FR-4.2: 이름 변경 (Rename)
- [ ] FR-4.3: 삭제 (Delete) - 확인 다이얼로그 필수
- [ ] FR-4.4: 복제 (Duplicate)

#### FR-5: 파일 저장/불러오기
- [ ] FR-5.1: 프로파일을 `.dgp` 파일로 내보내기 (Export)
- [ ] FR-5.2: `.dgp` 파일에서 프로파일 가져오기 (Import)
- [ ] FR-5.3: 상단 툴바에 💾 Save Profile 버튼
- [ ] FR-5.4: 상단 툴바에 📂 Load Profile 버튼

#### FR-6: 기존 UI 제거
- [ ] FR-6.1: 기존 DatasetItemWidget 카드 UI 제거
- [ ] FR-6.2: 트리 UI로 완전 대체

### 3.2 비기능 요구사항 (Non-Functional Requirements)

- [ ] NFR-1: 트리 펼침/접음 애니메이션 부드럽게 (100ms 이하)
- [ ] NFR-2: 100개 프로파일까지 렌더링 성능 저하 없음
- [ ] NFR-3: 다크 테마와 일관된 스타일링

## 4. 범위

### 포함
- 트리 UI 구현
- 프로파일 CRUD (Create, Read, Update, Delete)
- 파일 Import/Export
- 툴바 버튼

### 제외 (이번 버전)
- 비교 모드에서의 프로파일 동작
- 클라우드 동기화
- 프로파일 폴더/그룹화

## 5. UI/UX 상세

### 5.1 트리 구조
```
📁 sales_data.csv          ▼
   ├─ + 새 프로파일
   ├─ 📈 Line | Monthly Trend
   ├─ 📊 Bar  | Region Compare
   └─ 🥧 Pie  | Category Share

📁 stock_ohlc.csv          ▶
```

### 5.2 차트 타입 아이콘
| 차트 타입 | 아이콘 |
|----------|--------|
| line | 📈 |
| bar | 📊 |
| scatter | ⚬ |
| pie | 🥧 |
| area | 📉 |
| candlestick | 🕯️ |

### 5.3 컨텍스트 메뉴 (프로파일 우클릭)
```
┌──────────────────┐
│ ▶️ Apply         │
│ ✏️ Rename        │
│ 📋 Duplicate     │
│ ───────────────  │
│ 💾 Export...     │
│ ───────────────  │
│ 🗑️ Delete        │
└──────────────────┘
```

### 5.4 컨텍스트 메뉴 (프로젝트 우클릭)
```
┌──────────────────┐
│ ➕ New Profile   │
│ 📂 Import...     │
│ ───────────────  │
│ ❌ Remove Dataset│
└──────────────────┘
```

### 5.5 툴바 버튼
- 💾 **Save Profile**: 현재 설정을 활성 데이터셋에 프로파일로 저장
- 📂 **Load Profile**: `.dgp` 파일에서 프로파일 불러오기

## 6. 데이터 구조

### 6.1 GraphSetting (기존 구조 활용)
```python
@dataclass
class GraphSetting:
    id: str
    name: str
    chart_type: str  # line, bar, scatter, pie, area, candlestick
    x_column: Optional[str]
    group_columns: List[Dict]
    value_columns: List[Dict]
    hover_columns: List[str]
    chart_settings: Dict
    filters: List[Dict]
    sorts: List[Dict]
    created_at: float
    modified_at: float
```

### 6.2 DatasetState 확장
```python
@dataclass
class DatasetState:
    # ... 기존 필드들 ...
    profiles: List[GraphSetting] = field(default_factory=list)
```

### 6.3 파일 포맷 (.dgp)
JSON 기반, 기존 Profile 클래스 포맷 유지

## 7. 테스트 시나리오

### Unit Tests
- [ ] UT-1: GraphSetting 생성/직렬화/역직렬화
- [ ] UT-2: DatasetState.profiles 추가/삭제/수정
- [ ] UT-3: 차트 타입별 아이콘 매핑

### Integration Tests
- [ ] IT-1: 프로파일 저장 → 트리 UI 업데이트
- [ ] IT-2: 프로파일 클릭 → AppState 그래프 설정 적용
- [ ] IT-3: Export → Import → 동일 설정 복원

### E2E Tests
- [ ] E2E-1: 데이터 로드 → 그래프 설정 → 프로파일 저장 → 다른 프로파일 적용 → 원래 프로파일 복원
- [ ] E2E-2: 프로파일 Export → 앱 재시작 → Import → 설정 적용
- [ ] E2E-3: 프로파일 복제 → 이름 변경 → 삭제

## 8. 성공 기준
- [ ] 트리 UI가 IDE 프로젝트 탐색창처럼 동작
- [ ] 프로파일 저장/로드/삭제/이름변경/복제 모두 동작
- [ ] 파일 Export/Import 정상 동작
- [ ] 기존 카드 UI 완전 제거
- [ ] 모든 테스트 통과

## 9. 미해결 질문
- 없음 (모든 질문 해결됨)
