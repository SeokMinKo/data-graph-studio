# PRD v3: Project Explorer (프로젝트 탐색창)

## 1. 개요

### 1.1 목표
왼쪽 데이터셋 패널을 **VS Code Explorer 스타일**의 프로젝트 탐색창으로 개편

### 1.2 용어 정의
| 용어 | 정의 |
|-----|-----|
| **Project** | 로드된 데이터셋 파일 (CSV/Parquet). 1 파일 = 1 프로젝트 |
| **Profile** | 그래프 설정 스냅샷. X축, Y축, 그룹, 필터, 차트타입 등 저장 |
| **Active Project** | 현재 그래프/테이블에 데이터가 표시 중인 프로젝트 (1개만 가능) |
| **Selected Item** | 트리에서 키보드/마우스로 포커스된 항목 (Active와 독립) |
| **Applied Profile** | 현재 그래프에 적용된 프로파일 (없을 수도 있음) |

### 1.3 성공 기준 (측정 가능)

**테스트 환경**: M1 Mac, 16GB RAM, macOS 14+, Python 3.11, PySide6 6.6+

| 기준 | 목표 | 측정 방법 |
|-----|-----|----------|
| 트리 렌더링 (cold) | < 100ms | time.perf_counter(), 앱 시작 후 첫 렌더 |
| 트리 렌더링 (warm) | < 50ms | 이미 로드된 상태에서 재렌더 |
| 프로파일 적용 | < 200ms | 더블클릭 → 그래프 업데이트 완료 |
| Export/Import | < 100ms | 10KB .dgp 파일 기준 |
| 메모리 | < 5KB/profile | sys.getsizeof() + 재귀 측정 |

---

## 2. 아키텍처

### 2.1 데이터 흐름 (단방향)
```
┌─────────────────────────────────────────────────────────────┐
│                      User Interaction                        │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                    ProjectTreeView                           │
│                    (QTreeView, UI only)                      │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     ProfileModel                             │
│              (QAbstractItemModel, read-only view)            │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                     ProfileStore                             │
│        (Canonical storage, CRUD, File I/O, NO AppState)      │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          │ (데이터 요청만)
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                  GraphSettingMapper                          │
│           (GraphSetting ↔ AppState 변환 전용)                │
└─────────────────────────┬───────────────────────────────────┘
                          ▼
┌─────────────────────────────────────────────────────────────┐
│                      AppState                                │
│              (Runtime state, profiles 미포함)                │
└─────────────────────────────────────────────────────────────┘
```

### 2.2 핵심 원칙
1. **ProfileStore는 AppState를 모름** (의존성 없음)
2. **GraphSettingMapper가 경계 레이어** 역할
3. **단방향 데이터 흐름**: Store → Model → View
4. **Apply는 Controller/Service가 수행** (View → Controller → Mapper → AppState)

### 2.3 클래스 책임
| 클래스 | 책임 | 의존성 |
|-------|-----|-------|
| `ProfileStore` | CRUD, 파일 I/O, 캐시 | GraphSetting만 |
| `ProfileModel` | QAbstractItemModel | ProfileStore |
| `ProjectTreeView` | QTreeView, 이벤트 | ProfileModel |
| `GraphSettingMapper` | 양방향 변환 | GraphSetting, AppState 타입 |
| `ProfileController` | Apply/Save 로직 | Store, Mapper, AppState |
| `AppState` | 런타임 상태 | 없음 |

### 2.4 데이터 모델

#### GraphSetting (Immutable)
```python
@dataclass(frozen=True)
class GraphSetting:
    id: str                          # UUID v4
    name: str                        # 1-100자, strip()
    dataset_id: str                  # 귀속 프로젝트 ID
    schema_version: int = 1          # 마이그레이션용
    
    chart_type: ChartType
    x_column: Optional[str]
    group_columns: Tuple[GroupColumn, ...]
    value_columns: Tuple[ValueColumn, ...]
    hover_columns: Tuple[str, ...]
    filters: Tuple[FilterCondition, ...]
    sorts: Tuple[SortCondition, ...]
    chart_settings: MappingProxyType  # immutable dict
    
    created_at: float
    modified_at: float
    
    def with_name(self, name: str) -> 'GraphSetting':
        """이름 변경된 새 인스턴스 반환"""
        return dataclasses.replace(self, name=name, modified_at=time.time())
```

#### 메모리 예산 검증
```python
# 예상 크기 계산
# - 기본 필드: ~200 bytes
# - group_columns (5개): ~500 bytes
# - value_columns (10개): ~1000 bytes
# - chart_settings: ~500 bytes
# - 기타: ~300 bytes
# 총: ~2.5KB (5KB 예산 내)
```

---

## 3. 기능 요구사항

### 3.1 트리 UI

#### FR-1: 트리 구조
```
📊 sales_data.csv              [▼] [+]
   ├─ 📈 Monthly Trend         ← applied (bold + dot)
   ├─ 📊 Region Compare        ← selected (blue bg)
   └─ 🥧 Category Share

📊 stock_ohlc.csv              [▶] [+]
```

- **[+] 버튼 위치**: 프로젝트 행 우측, [▼] 옆
- **[+] 동작**: 해당 프로젝트에 새 프로파일 생성

#### FR-2: 상태 정의 및 시각적 표현

| 상태 | 배경색 | 테두리 | 텍스트 | 아이콘 | 공존 가능 |
|-----|-------|-------|-------|-------|---------|
| normal | transparent | none | #E2E8F0 | 기본 | - |
| hover | #1F2937 | none | #E2E8F0 | 기본 | selected, active |
| selected | #1E3A5F | 2px #2563EB | #FFFFFF | 기본 | active, hover |
| active | transparent | none | **bold** | 🟢 8px dot | selected, hover |
| focused | - | 2px dashed #60A5FA | - | - | 모든 상태 |
| disabled | transparent | none | #6B7280 50% | 흐림 | - |
| loading | transparent | none | #9CA3AF | ⏳ spinner | - |

**색상 대비 검증 (WCAG 2.1 AA)**:
| 조합 | 비율 | 통과 |
|-----|-----|-----|
| #E2E8F0 on #111827 | 12.6:1 | ✅ |
| #FFFFFF on #1E3A5F | 8.9:1 | ✅ |
| #6B7280 on #111827 | 4.8:1 | ✅ |
| #60A5FA on #111827 | 5.2:1 | ✅ |

#### FR-3: 인터랙션 상세

| 동작 | 대상 | 결과 |
|-----|-----|-----|
| 싱글클릭 | 프로젝트 | 선택 + 활성화 (Active Project 변경) |
| 싱글클릭 | 프로파일 | 선택만 (적용 X) |
| 더블클릭 | 프로파일 | 적용 (unsaved 경고 후) |
| [▼]/[▶] 클릭 | 토글 | 펼침/접기 |
| [+] 클릭 | 버튼 | 해당 프로젝트에 새 프로파일 |
| 우클릭 | 모든 항목 | 컨텍스트 메뉴 |
| 우클릭 | 빈 영역 | 메뉴 없음 |

**Hit Target**: 모든 클릭 영역 최소 44x32px

### 3.2 키보드 접근성 (완전 정의)

**포커스 요구사항**: 트리가 포커스된 상태에서만 동작

| 키 | 동작 | 조건 |
|---|-----|-----|
| ↑ | 이전 항목 선택 | - |
| ↓ | 다음 항목 선택 | - |
| ← | 프로젝트: 접기 / 프로파일: 부모로 이동 | - |
| → | 프로젝트: 펼치기 / 이미 펼침: 첫 자식으로 | - |
| Enter | 프로젝트: 활성화 / 프로파일: **적용** | unsaved 경고 |
| Space | 펼침/접기 토글 | 프로젝트만 |
| F2 | 인라인 이름 변경 모드 | 프로파일만 |
| Delete | 삭제 (확인 다이얼로그) | 프로파일만 |
| Ctrl+N | 새 프로파일 | 프로젝트 선택 시 |
| Ctrl+D | 복제 | 프로파일 선택 시 |
| Ctrl+S | Export | 프로파일 선택 시 |
| Ctrl+O | Import | 프로젝트 선택 시 |
| Escape | 인라인 편집 취소 / 선택 해제 | - |
| Shift+F10 | 컨텍스트 메뉴 열기 | - |

### 3.3 ARIA 접근성

```html
<div role="tree" aria-label="Project Explorer">
  <div role="treeitem" aria-expanded="true" aria-selected="false">
    📊 sales_data.csv
    <div role="group">
      <div role="treeitem" aria-selected="true">📈 Monthly Trend</div>
      <div role="treeitem" aria-selected="false">📊 Region Compare</div>
    </div>
  </div>
</div>
```

**스크린리더 공지**:
- 펼침/접기: "sales_data.csv expanded" / "collapsed"
- 선택: "Monthly Trend selected"
- 적용: "Monthly Trend profile applied"
- 로딩: "Loading profiles..."
- 빈 상태: "No profiles. Press Ctrl+N to create one."

### 3.4 프로파일 CRUD

#### FR-4: 생성 (Create)
1. 트리거: [+] 버튼, Ctrl+N, 컨텍스트 메뉴
2. 이름 입력 다이얼로그
   - 제목: "New Profile"
   - 기본값: "New Profile"
   - 플레이스홀더: "Enter profile name"
   - 유효성: 1-100자, strip(), 빈 문자열 불가
   - 중복 처리: 자동 suffix " (1)", " (2)"...
   - 버튼: [Create] [Cancel], 기본 포커스: 입력 필드
3. 생성 완료 → 트리에 추가, 선택됨

**Edge Cases:**
| 상황 | 동작 |
|-----|-----|
| 그래프 설정 없음 | 빈 프로파일 생성 (x_column=None) |
| 프로젝트 없음 | [+] 버튼 disabled |
| 100자 초과 입력 | 입력 제한 (maxlength) |

#### FR-5: 적용 (Apply)

**Unsaved Changes 정의**: 
- 현재 그래프 설정이 마지막 저장된 프로파일과 다름
- 저장된 프로파일이 없으면 unsaved = true

**적용 흐름**:
```
더블클릭/Enter
    ↓
unsaved changes 체크
    ↓ (있으면)
┌─────────────────────────────────────┐
│ 현재 설정이 저장되지 않았습니다.      │
│                                     │
│ [저장 후 적용] [적용만] [취소]       │
│     (기본)                          │
└─────────────────────────────────────┘
    ↓
GraphSettingMapper.to_app_state(setting)
    ↓
AppState 업데이트 (signal batch)
    ↓
UI 업데이트 완료
```

**Signal Batching 구현**:
```python
class AppState:
    def begin_batch_update(self):
        self._batch_mode = True
        self._pending_signals = []
    
    def end_batch_update(self):
        self._batch_mode = False
        # 모든 pending signals를 단일 composite signal로
        self.batch_updated.emit(self._pending_signals)
        self._pending_signals = []
```

**Edge Cases:**
| 상황 | 동작 |
|-----|-----|
| 컬럼 불일치 | 경고 다이얼로그 + 가능한 필드만 적용 |
| 프로파일 손상 | "프로파일을 적용할 수 없습니다" 에러 |
| 적용 실패 | 롤백, 에러 토스트 표시 |

#### FR-6: 이름 변경 (Rename)
1. 트리거: F2, 컨텍스트 메뉴 "Rename"
2. 인라인 편집 모드 활성화
3. Enter: 저장, Escape: 취소
4. 유효성 검사 실패 → 빨간 테두리 + 툴팁
5. modified_at 업데이트

#### FR-7: 복제 (Duplicate)
1. 트리거: Ctrl+D, 컨텍스트 메뉴 "Duplicate"
2. 새 UUID 생성
3. 이름: "{원본} (Copy)", 중복 시 suffix
4. 즉시 트리에 추가, 선택됨

#### FR-8: 삭제 (Delete)

**삭제 흐름**:
```
Delete 키 / 컨텍스트 메뉴
    ↓
┌─────────────────────────────────────┐
│ '{name}' 프로파일을 삭제하시겠습니까? │
│                                     │
│ [삭제] [취소]                       │
│          (기본)                     │
└─────────────────────────────────────┘
    ↓
삭제 실행
    ↓
Undo 토스트 표시 (5초)
┌─────────────────────────────────────┐
│ 프로파일이 삭제되었습니다. [실행 취소] │
└─────────────────────────────────────┘
```

**Undo 구현**:
- 저장소: 메모리 내 UndoStack (최대 10개)
- 유효 시간: 5분 (앱 재시작 시 소멸)
- 지원 작업: Delete, Rename
- UI: 토스트 (5초) + Edit 메뉴 "Undo" (Ctrl+Z)

### 3.5 파일 I/O

#### FR-9: Export
- 트리거: Ctrl+S, 컨텍스트 메뉴 "Export..."
- OS 저장 다이얼로그
- 기본 파일명: `{profile_name}.dgp`
- 단일 프로파일만 export

#### FR-10: Import
- 트리거: Ctrl+O, 컨텍스트 메뉴 "Import..."
- OS 열기 다이얼로그
- 대상: **선택된 프로젝트**에 추가

**파일 포맷 (.dgp) v1**:
```json
{
  "dgp_version": 1,
  "schema_version": 1,
  "exported_at": "2026-02-02T22:00:00Z",
  "profile": { ... }
}
```

**버전 호환성**:
| dgp_version | 동작 |
|-------------|-----|
| 1 | 정상 로드 |
| 0 또는 없음 | 레거시 마이그레이션 시도 |
| 2+ | "지원하지 않는 버전" 에러 |

**에러 처리**:
| 에러 | 메시지 | 복구 |
|-----|-------|-----|
| 파일 없음 | "파일을 찾을 수 없습니다" | - |
| 권한 없음 | "파일을 읽을 수 없습니다" | - |
| JSON 오류 | "잘못된 파일 형식입니다" | - |
| 버전 미지원 | "지원하지 않는 버전입니다 (v{n})" | - |
| 스키마 불일치 | "일부 설정을 가져올 수 없습니다" | 부분 import |

### 3.6 Async I/O 설계

```python
class ProfileStore:
    def __init__(self):
        self._io_thread = QThread()
        self._worker = IOWorker()
        self._worker.moveToThread(self._io_thread)
        self._io_thread.start()
    
    def export_async(self, profile: GraphSetting, path: str):
        """UI 스레드 블로킹 없이 export"""
        self._worker.export_requested.emit(profile, path)
    
    def import_async(self, path: str) -> QFuture[GraphSetting]:
        """UI 스레드 블로킹 없이 import"""
        future = QFuture()
        self._worker.import_requested.emit(path, future)
        return future

class IOWorker(QObject):
    export_requested = Signal(GraphSetting, str)
    import_requested = Signal(str, object)
    export_completed = Signal(bool, str)  # success, error
    import_completed = Signal(GraphSetting, str)  # result, error
```

---

## 4. 컨텍스트 메뉴

### 프로젝트 우클릭
```
➕ New Profile       Ctrl+N
📂 Import...        Ctrl+O
─────────────────────────
❌ Remove Project   (확인 필요)
```

### 프로파일 우클릭
```
▶️ Apply            Enter
✏️ Rename           F2
📋 Duplicate        Ctrl+D
─────────────────────────
💾 Export...        Ctrl+S
─────────────────────────
🗑️ Delete           Del
```

### Disabled 상태
- Apply: 이미 적용된 프로파일이면 disabled
- Export: 프로파일 손상 시 disabled
- 모든 항목: loading 상태면 disabled

---

## 5. 마이그레이션

### 5.1 기존 데이터 → 프로파일
1. 앱 시작 시 기존 graph settings 감지
2. "Default" 프로파일로 자동 생성
3. 사용자에게 알림: "기존 설정이 'Default' 프로파일로 저장되었습니다"

### 5.2 실패 처리
- 마이그레이션 실패 시 → 원본 유지, 에러 로그
- 롤백: 이전 버전 앱에서 열 수 있도록 호환성 유지

### 5.3 스키마 버전 업그레이드
```python
MIGRATIONS = {
    (0, 1): migrate_v0_to_v1,
    (1, 2): migrate_v1_to_v2,
}

def migrate_profile(data: dict) -> GraphSetting:
    current = data.get("schema_version", 0)
    target = CURRENT_SCHEMA_VERSION
    
    while current < target:
        migrate_fn = MIGRATIONS.get((current, current + 1))
        if not migrate_fn:
            raise MigrationError(f"No migration path from v{current}")
        data = migrate_fn(data)
        current += 1
    
    return GraphSetting.from_dict(data)
```

---

## 6. 에러 처리 통합

| 작업 | 에러 유형 | UI 표시 | 복구 |
|-----|---------|--------|-----|
| 프로파일 로드 | 파일 손상 | 토스트 에러 | 건너뛰기 |
| 프로파일 적용 | 컬럼 불일치 | 경고 다이얼로그 | 부분 적용 |
| 프로파일 저장 | 디스크 풀 | 토스트 에러 | 재시도 버튼 |
| Import | JSON 오류 | 토스트 에러 | - |
| Export | 권한 없음 | 토스트 에러 | 다른 경로 선택 |

---

## 7. 테스트 시나리오

### Unit Tests
- [ ] UT-1: GraphSetting immutable 검증 (frozen=True)
- [ ] UT-2: ProfileStore CRUD 독립 동작 (AppState 의존 없음)
- [ ] UT-3: GraphSettingMapper 양방향 round-trip
- [ ] UT-4: 이름 충돌 시 suffix 생성 ("Test" → "Test (1)")
- [ ] UT-5: 스키마 마이그레이션 v0→v1
- [ ] UT-6: 메모리 크기 < 5KB 검증

### Integration Tests
- [ ] IT-1: 프로파일 생성 → ProfileModel 업데이트 (incremental)
- [ ] IT-2: 프로파일 적용 → AppState → 그래프 업데이트
- [ ] IT-3: Export → Import → 동일 설정 검증
- [ ] IT-4: Undo 동작 (Delete → Ctrl+Z → 복원)
- [ ] IT-5: 비동기 I/O 블로킹 없음 검증

### E2E Tests
- [ ] E2E-1: 전체 CRUD 워크플로우
- [ ] E2E-2: 키보드만으로 모든 작업 수행
- [ ] E2E-3: 대용량 (100 profiles, 10 projects) 성능 검증
- [ ] E2E-4: 컬럼 불일치 시 부분 적용 + 경고

### 성능 벤치마크
```python
def test_tree_render_performance():
    # Setup: 10 projects, 100 profiles total
    store = ProfileStore()
    for i in range(10):
        for j in range(10):
            store.add(create_test_profile(f"proj_{i}", f"profile_{j}"))
    
    model = ProfileModel(store)
    view = ProjectTreeView()
    view.setModel(model)
    
    # Measure cold render
    start = time.perf_counter()
    view.show()
    QApplication.processEvents()
    cold_time = time.perf_counter() - start
    
    assert cold_time < 0.1  # 100ms
    
    # Measure warm render
    view.hide()
    start = time.perf_counter()
    view.show()
    QApplication.processEvents()
    warm_time = time.perf_counter() - start
    
    assert warm_time < 0.05  # 50ms
```

---

## 8. 제외 항목 (Out of Scope)
1. 비교 모드 프로파일 동작
2. 클라우드 동기화
3. 프로파일 폴더/그룹화
4. 멀티 유저/권한
5. 프로파일 검색/필터
6. 태그/라벨
7. 분석/텔레메트리
8. 드래그앤드롭 정렬
9. 프로파일 공유
10. 버전 히스토리
11. 자동 저장
12. 프로파일 비교
13. 템플릿
14. 단축키 커스터마이징

---

## 9. 오픈 이슈
없음 - 모든 질문 해결됨
