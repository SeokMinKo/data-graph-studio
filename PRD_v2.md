# PRD v2: Project Explorer (프로젝트 탐색창)

## 1. 개요

### 1.1 목표
왼쪽 데이터셋 패널을 **VS Code Explorer 스타일**의 프로젝트 탐색창으로 개편

### 1.2 용어 정의
| 용어 | 정의 |
|-----|-----|
| **Project** | 로드된 데이터셋 파일 (CSV/Parquet). 1 파일 = 1 프로젝트 |
| **Profile** | 그래프 설정 스냅샷. X축, Y축, 그룹, 필터, 차트타입 등 저장 |
| **Active Project** | 현재 그래프/테이블에 표시 중인 프로젝트 |
| **Selected Item** | 트리에서 포커스된 항목 (Active와 별개) |

### 1.3 성공 기준 (측정 가능)
- [ ] 트리 렌더링: 100 profiles, 10 projects 기준 **< 50ms**
- [ ] 프로파일 적용: 클릭 → 그래프 업데이트 **< 200ms**
- [ ] 파일 Import/Export: 10KB .dgp 파일 **< 100ms**
- [ ] 키보드로 모든 CRUD 작업 가능
- [ ] 기존 카드 UI 완전 제거

---

## 2. 아키텍처

### 2.1 컴포넌트 구조
```
┌─────────────────────────────────────────────────┐
│                   MainWindow                     │
│  ┌─────────────┐  ┌──────────────────────────┐  │
│  │ ProjectTree │  │      GraphPanel          │  │
│  │ (QTreeView) │  │                          │  │
│  └──────┬──────┘  └──────────────────────────┘  │
│         │                                        │
│  ┌──────▼──────┐                                │
│  │ProfileModel │ ◄─── QAbstractItemModel        │
│  └──────┬──────┘                                │
└─────────┼───────────────────────────────────────┘
          │
   ┌──────▼──────┐
   │ProfileStore │  ◄─── 서비스 레이어 (CRUD + 영속성)
   └──────┬──────┘
          │
   ┌──────▼──────┐
   │  AppState   │  ◄─── 런타임 상태 (profiles 제외)
   └─────────────┘
```

### 2.2 클래스 책임
| 클래스 | 책임 |
|-------|-----|
| `ProfileStore` | Profile CRUD, 파일 I/O, 버저닝 |
| `ProfileModel` | QAbstractItemModel 구현, 트리 데이터 |
| `ProjectTreeView` | QTreeView 서브클래스, 이벤트 처리 |
| `AppState` | 런타임 그래프 상태 (profiles 미포함) |

### 2.3 데이터 모델

#### GraphSetting (Immutable)
```python
@dataclass(frozen=True)
class GraphSetting:
    id: str                          # UUID v4
    name: str                        # 1-100자, 공백 trim
    dataset_id: str                  # 귀속 프로젝트
    schema_version: int = 1          # 마이그레이션용
    
    chart_type: ChartType
    x_column: Optional[str]
    group_columns: Tuple[GroupColumn, ...]   # immutable
    value_columns: Tuple[ValueColumn, ...]   # immutable
    hover_columns: Tuple[str, ...]
    filters: Tuple[FilterCondition, ...]
    sorts: Tuple[SortCondition, ...]
    chart_settings: FrozenDict
    
    created_at: float
    modified_at: float
```

#### 매핑 계약: AppState ↔ GraphSetting
| AppState 필드 | GraphSetting 필드 | 변환 |
|--------------|------------------|-----|
| `_chart_settings.chart_type` | `chart_type` | enum 동일 |
| `_x_column` | `x_column` | 직접 복사 |
| `_group_columns` | `group_columns` | List → Tuple |
| `_value_columns` | `value_columns` | List → Tuple |
| `_hover_columns` | `hover_columns` | List → Tuple |
| `_filters` | `filters` | List → Tuple |
| `_sorts` | `sorts` | List → Tuple |

---

## 3. 기능 요구사항

### 3.1 트리 UI

#### FR-1: 트리 구조
```
📊 sales_data.csv              [▼] [+]
   ├─ 📈 Monthly Trend
   ├─ 📊 Region Compare  ← selected
   └─ 🥧 Category Share

📊 stock_ohlc.csv              [▶] [+]
```

- 프로젝트 아이콘: 📊 (데이터 아이콘, 폴더 X)
- `[▼]` / `[▶]`: 펼침/접기 토글
- `[+]`: 새 프로파일 버튼 (트리 아이템 아님)

#### FR-2: 상태 정의
| 상태 | 시각적 표현 |
|-----|-----------|
| **normal** | 기본 배경 |
| **hover** | 밝은 배경 (#1F2937) |
| **selected** | 파란 테두리 |
| **active** | 볼드 텍스트 + 녹색 점 |
| **focused** | 점선 테두리 (키보드) |
| **disabled** | 회색 텍스트, 클릭 불가 |
| **loading** | 스피너 아이콘 |

#### FR-3: 인터랙션
| 동작 | 결과 |
|-----|-----|
| 프로젝트 클릭 | 해당 프로젝트 활성화 |
| 프로파일 싱글클릭 | **선택만** (적용 X) |
| 프로파일 더블클릭 | 프로파일 적용 |
| `[▼]`/`[▶]` 클릭 | 펼침/접기 |
| `[+]` 클릭 | 새 프로파일 생성 |
| 우클릭 | 컨텍스트 메뉴 |

### 3.2 프로파일 CRUD

#### FR-4: 생성 (Create)
1. `[+]` 버튼 또는 컨텍스트 메뉴 → "New Profile"
2. 이름 입력 다이얼로그
   - 기본값: "New Profile"
   - 유효성: 1-100자, 앞뒤 공백 trim
   - 중복 시: 자동 suffix "(1)", "(2)"...
3. 현재 그래프 설정으로 GraphSetting 생성
4. 새 UUID v4 할당
5. created_at, modified_at = now

**Edge Cases:**
- 그래프 설정 없음 → 빈 프로파일 생성 (x_column=None)
- 데이터셋 비어있음 → 정상 생성 (적용 시 경고)

#### FR-5: 적용 (Apply)
1. 더블클릭 또는 컨텍스트 메뉴 → "Apply"
2. **Unsaved changes 경고**: 현재 설정이 저장 안 됐으면 확인 다이얼로그
   - "현재 설정이 저장되지 않았습니다. 계속하시겠습니까?"
   - [저장 후 적용] [그냥 적용] [취소]
3. GraphSetting → AppState 복원 (매핑 계약 따름)
4. Signal batch로 UI 업데이트 (beginUpdate/endUpdate)

**Edge Cases:**
- 컬럼 불일치 → 경고 다이얼로그 + 부분 적용
- 프로파일 손상 → 에러 메시지, 적용 중단

#### FR-6: 이름 변경 (Rename)
1. 컨텍스트 메뉴 → "Rename" 또는 F2
2. 인라인 편집 모드
3. 유효성 검사 (1-100자)
4. 중복 시 자동 suffix
5. modified_at 업데이트

#### FR-7: 복제 (Duplicate)
1. 컨텍스트 메뉴 → "Duplicate"
2. 새 UUID 생성 (기존 ID 복제 X)
3. 이름: "{원본} (Copy)"
4. 중복 시 suffix
5. created_at = now

#### FR-8: 삭제 (Delete)
1. 컨텍스트 메뉴 → "Delete" 또는 Del 키
2. **확인 다이얼로그**: "'{name}' 프로파일을 삭제하시겠습니까?"
3. 삭제 후:
   - 활성 프로파일였다면 → 그래프 설정 유지, 활성 해제
   - 선택 이동: 다음 항목 또는 이전 항목
4. **Undo 지원**: Ctrl+Z로 복원 (5분 내)

### 3.3 파일 I/O

#### FR-9: Export
1. 컨텍스트 메뉴 → "Export..." 또는 툴바 버튼
2. OS 파일 저장 다이얼로그
3. 기본 파일명: `{profile_name}.dgp`
4. **단일 프로파일 export** (여러 개 X)

#### FR-10: Import
1. 컨텍스트 메뉴 → "Import..." 또는 툴바 버튼
2. OS 파일 열기 다이얼로그
3. **현재 활성 프로젝트에 추가**
4. 이름 충돌 시 suffix
5. 버전 체크 → 마이그레이션

**파일 포맷 (.dgp)**
```json
{
  "dgp_version": 1,
  "exported_at": "2026-02-02T22:00:00Z",
  "profile": {
    "id": "uuid",
    "name": "...",
    "schema_version": 1,
    ...
  }
}
```

**에러 처리:**
| 에러 | 동작 |
|-----|-----|
| 파일 없음 | "파일을 찾을 수 없습니다" |
| JSON 파싱 실패 | "잘못된 파일 형식입니다" |
| 버전 미지원 | "지원하지 않는 버전입니다 (v{n})" |
| 스키마 불일치 | 부분 import + 경고 |

### 3.4 툴바

| 버튼 | 동작 | 단축키 |
|-----|-----|-------|
| 💾 Save | 선택된 프로파일 Export | Ctrl+S |
| 📂 Open | 프로파일 Import | Ctrl+O |

- 선택 없으면 disabled
- 툴팁: "Save Profile (Ctrl+S)"

### 3.5 키보드 접근성

| 키 | 동작 |
|---|-----|
| ↑/↓ | 항목 이동 |
| ← | 접기 또는 부모로 이동 |
| → | 펼치기 또는 첫 자식으로 |
| Enter | 프로파일 적용 |
| Space | 펼침/접기 토글 |
| F2 | 이름 변경 |
| Del | 삭제 (확인 후) |
| Ctrl+N | 새 프로파일 |
| Ctrl+D | 복제 |
| Shift+F10 | 컨텍스트 메뉴 |

### 3.6 컨텍스트 메뉴

**프로젝트 우클릭:**
```
➕ New Profile       Ctrl+N
📂 Import...        Ctrl+O
─────────────────
❌ Remove Project
```

**프로파일 우클릭:**
```
▶️ Apply            Enter
✏️ Rename           F2
📋 Duplicate        Ctrl+D
─────────────────
💾 Export...        Ctrl+S
─────────────────
🗑️ Delete           Del
```

---

## 4. 비기능 요구사항

### 4.1 성능
- 트리 렌더링: **< 50ms** (100 profiles, 10 projects)
- 프로파일 적용: **< 200ms**
- Export/Import: **< 100ms** (10KB)
- Incremental update: 단일 노드 변경 시 전체 재구성 X

### 4.2 메모리
- 프로파일당 **< 5KB**
- 중복 저장 방지: ProfileStore가 canonical storage

### 4.3 접근성
- WCAG 2.1 AA 준수
- 색상 대비: 4.5:1 이상
- 스크린리더: ARIA tree/treeitem roles
- 키보드: 모든 작업 가능

### 4.4 스타일
- 다크 테마 기본
- 배경: #111827
- 텍스트: #E2E8F0
- 선택: #2563EB (border)
- 활성: #10B981 (dot)

---

## 5. 마이그레이션

### 5.1 기존 데이터
- 기존 graph settings → "Default" 프로파일로 자동 생성
- 카드 UI 상태 (색상 등) → 프로젝트 메타데이터로 보존

### 5.2 스키마 버저닝
```python
def migrate_profile(data: dict) -> GraphSetting:
    version = data.get("schema_version", 0)
    if version == 0:
        # v0 → v1: chart_settings 구조 변경
        data = migrate_v0_to_v1(data)
    return GraphSetting.from_dict(data)
```

---

## 6. 테스트 시나리오

### Unit Tests
- [ ] UT-1: GraphSetting immutable 검증
- [ ] UT-2: ProfileStore CRUD 정상 동작
- [ ] UT-3: 이름 충돌 시 suffix 생성
- [ ] UT-4: 스키마 마이그레이션
- [ ] UT-5: 매핑 계약 round-trip

### Integration Tests
- [ ] IT-1: 프로파일 생성 → 트리 업데이트 (incremental)
- [ ] IT-2: 프로파일 적용 → AppState 변경 → 그래프 업데이트
- [ ] IT-3: Export → Import → 동일 설정
- [ ] IT-4: Undo/Redo 동작

### E2E Tests
- [ ] E2E-1: 데이터 로드 → 그래프 설정 → 저장 → 다른 프로파일 적용 → 복원
- [ ] E2E-2: 키보드만으로 전체 CRUD 수행
- [ ] E2E-3: 대용량 테스트 (100 profiles, 10 projects)
- [ ] E2E-4: 컬럼 불일치 시 부분 적용 + 경고

---

## 7. 제외 항목 (Out of Scope)
- 비교 모드 프로파일 동작
- 클라우드 동기화
- 프로파일 폴더/그룹화
- 멀티 유저/권한
- 프로파일 검색/필터
- 태그/라벨
- 분석/텔레메트리
- 드래그앤드롭 정렬

---

## 8. 오픈 이슈
없음 - 모든 질문 해결됨
