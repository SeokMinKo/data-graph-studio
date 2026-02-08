# PRD: DGS v0.21 — DataEngine 분리 + v2 기능 와이어링 + UX 개선 (v2)

## 1. 목표
DataEngine God Object를 책임별로 분리하고, v2 미완성 기능을 MainWindow에 와이어링하며, UX 품질을 전반적으로 개선한다.

## 2. 배경
- `data_engine.py` 2,808줄: 파일 로딩, 데이터 변환, 통계, 데이터셋 관리, 비교 분석이 한 클래스에 몰려있음
- v2 7대 기능(대시보드, 스트리밍, 컬럼 생성, 내보내기, 주석, 테마, 단축키) 코어는 구현됐지만 MainWindow 와이어링 미완
- 루트에 잡파일 산재, IPC 포트 하드코딩, autosave 복구 UX 문제

## 3. 조사 요약
### 검토한 대안
| 대안 | 장점 | 단점 | 채택 여부 |
|------|------|------|----------|
| DataEngine 전체 재작성 | 깔끔한 설계 | 기존 코드 전부 수정 필요, 회귀 위험 | ❌ |
| DataEngine 점진적 추출 | 호환성 유지, re-export로 기존 import 보존 | 일시적 중복 코드 | ✅ |
| v2 기능 새로 구현 | 최적 설계 | 이미 구현된 코어 낭비 | ❌ |
| v2 기능 기존 코어 와이어링 | 빠른 완성, 코어 재사용 | 코어 버그 있으면 전파 | ✅ |

## 4. 요구사항

### Phase A: DataEngine 분리

#### 4.1 기능 요구사항 (FR)

**A-1: FileLoader 추출**
- [ ] FR-A1.1: `core/file_loader.py` — `FileLoader` 클래스 생성
  - 파일 타입 감지 (`detect_file_type`, `detect_delimiter`)
  - CSV/TSV/TXT/Excel/Parquet/JSON/ETL 로딩
  - 인코딩 정규화, 진행 콜백, Parquet 변환
  - 윈도우/Lazy 로딩, 취소
  - 프로파일 생성, 메모리 최적화, 정밀도 모드
- [ ] FR-A1.2: `FileLoader`는 `DataEngine`에서 composition으로 사용
- [ ] FR-A1.3: 기존 public API 유지 (Facade 위임)

**A-2: DataQuery 추출** (조회/변환/통계만 — export 제외)
- [ ] FR-A2.1: `core/data_query.py` — `DataQuery` 클래스 생성
  - 필터 (`filter`), 정렬 (`sort`), 그룹 집계 (`group_aggregate`)
  - 통계 (`get_statistics`, `get_all_statistics`, `get_full_profile_summary`)
  - 카테고리 판별, 고유값, 샘플링, 슬라이스, 검색, 인덱스
- [ ] FR-A2.2: `DataQuery`는 stateless — `pl.DataFrame`을 인자로 받아 동작
- [ ] FR-A2.3: 기존 public API 유지 (Facade 위임)
- [ ] FR-A2.4: `filter()` 반환값 정책: 새 DataFrame을 반환. Facade는 반환값을 호출자에게 전달만 하고, `self._df`는 변경하지 않음. `_df` 변경은 `load_file`/`activate_dataset`에서만 발생

**A-3: DataExporter 추출** (A-2에서 분리)
- [ ] FR-A3.1: `core/data_exporter.py` — `DataExporter` 클래스 생성
  - `export_csv`, `export_excel`, `export_parquet`
- [ ] FR-A3.2: stateless — DataFrame을 인자로 받아 파일로 내보냄
- [ ] FR-A3.3: 기존 public API 유지

**A-4: DatasetManager 추출**
- [ ] FR-A4.1: `core/dataset_manager.py` — `DatasetManager` 클래스 생성
  - 데이터셋 CRUD, 메모리 관리, 메타데이터, 컬럼 유틸
- [ ] FR-A4.2: `FileLoader`를 주입받아 로딩 위임
- [ ] FR-A4.3: 기존 public API 유지
- [ ] FR-A4.4: 데이터셋 삭제 시 `dataset_removing(dataset_id)` 이벤트 발행 (콜백/Signal). ComparisonEngine 등 소비자가 진행 중 작업 취소 가능

**A-5: ComparisonEngine 추출**
- [ ] FR-A5.1: `core/comparison_engine.py` — `ComparisonEngine` 클래스 생성
  - 정렬, 차이, 비교 통계, 병합, 통계 검정, 상관 분석, 기술 통계 비교, 정규성 검정
- [ ] FR-A5.2: `DatasetManager` 참조를 받아 데이터셋 접근
- [ ] FR-A5.3: 기존 public API 유지
- [ ] FR-A5.4: 비교 연산 시 datasets snapshot(ID→df 복사본) 사용. 연산 중 원본 변경/삭제에 안전

**A-6: DataEngine Facade 유지**
- [ ] FR-A6.1: `DataEngine`은 5개 모듈의 Facade로 남음 (기존 import 100% 호환)
- [ ] FR-A6.2: 모든 기존 public 메서드를 하위 모듈에 위임
- [ ] FR-A6.3: `from data_graph_studio.core.data_engine import DataEngine` 동작 유지

### 상태 소유권 다이어그램

```
DataEngine (Facade)
├── _loader: FileLoader
│   ├── _df: pl.DataFrame          ← 단일 파일 로딩 결과 (레거시 호환)
│   ├── _lazy_df: pl.LazyFrame     ← lazy 로딩 상태
│   ├── _progress: LoadingProgress
│   └── _cancel_flag: bool
├── _query: DataQuery              ← stateless, df를 인자로 받음
├── _exporter: DataExporter        ← stateless, df를 인자로 받음
├── _datasets: DatasetManager
│   ├── _datasets: Dict[str, DatasetInfo]  ← 멀티 데이터셋 상태
│   ├── _active_dataset_id: str
│   └── _loader: FileLoader (주입됨)
├── _comparison: ComparisonEngine
│   └── _datasets: DatasetManager (참조)
└── _cache: Dict[str, Any]         ← Facade 레벨 캐시 (LRU, maxsize=128)

프로퍼티 위임:
- DataEngine.df → self._loader._df (단일 파일) 또는 self._datasets.get_dataset_df(active_id)
- DataEngine.datasets → self._datasets.datasets
```

### 캐시 전략
- **소유권**: Facade(`DataEngine`)가 `_cache`를 소유
- **Eviction**: LRU, maxsize=128 항목
- **무효화**: `load_file()`, `activate_dataset()`, `remove_dataset()` 호출 시 `_cache.clear()`
- **DataQuery에 캐시 전달**: `DataQuery` 메서드에 optional `cache` 파라미터. 통계/프로파일 결과를 캐시 키로 저장

### 스레드 안전성 규칙
- **규칙 1**: `_df` 교체는 메인 스레드에서만 수행. async_load 완료 Signal → 메인 스레드에서 `_df = new_df`
- **규칙 2**: 스트리밍 데이터 갱신은 `QMetaObject.invokeMethod(Qt.QueuedConnection)`으로 메인 스레드 큐에 넣음
- **규칙 3**: ComparisonEngine은 연산 시작 시 필요한 df의 참조를 snapshot으로 확보. 연산 중 원본 변경 무관
- **규칙 4**: `DatasetManager.load_dataset(async_load=True)` 진행 중 같은 dataset_id의 df 접근 → `None` 반환 (로딩 중 플래그)

### 부분 실패 시 상태 일관성
- FileLoader 로딩 성공 후 DatasetManager 등록 실패 → FileLoader의 `_df`를 이전 상태로 복원 (로딩 전 `_prev_df` 백업)
- 상태 변경은 Facade를 통해서만 수행. 하위 모듈 직접 상태 변경 금지

### Phase B: v2 기능 MainWindow 와이어링

**B-1: 대시보드 모드 완성**
- [ ] FR-B1.1: 메뉴/툴바의 Dashboard Mode 토글이 `DashboardPanel`을 메인 영역에 표시
- [ ] FR-B1.2: 프로파일을 셀 클릭→프로파일 선택 다이얼로그로 배치. 키보드: Arrow Key 셀 이동, Enter로 프로파일 할당, Tab으로 셀 순회
- [ ] FR-B1.3: 레이아웃 프리셋 (1×1, 1×2, 2×1, 2×2) 선택 UI
- [ ] FR-B1.4: 대시보드 레이아웃 저장/불러오기 (JSON, 프로젝트 파일에 포함)
- [ ] FR-B1.5: Esc로 일반 모드 복귀. **셀 배치 상태는 유지됨** (재진입 시 복원)
- [ ] FR-B1.6: 빈 셀에 "Click to add chart" 플레이스홀더
- [ ] FR-B1.7: `DashboardPanel`은 lazy 생성 (최초 진입 시 1회). 모드 전환 시 visibility만 토글. 재생성 안 함
- [ ] FR-B1.8: 대시보드 모드 토글 연속 클릭 방어 — `_dashboard_toggling` guard flag, 전환 완료 전 추가 클릭 무시

**B-2: 스트리밍 UI 완성**
- [ ] FR-B2.1: 스트리밍 다이얼로그에서 파일 경로 + 간격 설정 후 시작
- [ ] FR-B2.2: 스트리밍 툴바의 Play/Pause/Stop이 실제 파일 워치 시작/중단
- [ ] FR-B2.3: 새 데이터 감지 시 그래프 자동 업데이트. 데이터 갱신은 `QMetaObject.invokeMethod`로 메인 스레드에서 수행
- [ ] FR-B2.4: 상태바에 스트리밍 상태 표시 (감시 중/일시정지/정지)
- [ ] FR-B2.5: 데이터 미로드 상태에서 스트리밍 시작 시도 → "No data loaded" 토스트 + 시작 차단
- [ ] FR-B2.6: Play 연속 클릭 방어 — 이미 재생 중이면 무시
- [ ] FR-B2.7: Stop 시 **현재 데이터 유지** (원본 복원 안 함). 사용자가 원하면 Undo로 복원

**B-3: Computed Column UI 완성**
- [ ] FR-B3.1: Data 메뉴 → Add Calculated Field가 `ComputedColumnDialog` 표시
- [ ] FR-B3.2: 표현식 입력 → 미리보기 → 확인 시 테이블/그래프에 새 컬럼 추가
- [ ] FR-B3.3: expressions.py의 기존 Expression 엔진 활용
- [ ] FR-B3.4: 에러 표현식 입력 시 인라인 에러 메시지 + 빨간 하이라이트. 에러 종류: `SyntaxError` → "표현식 문법 오류: {위치}", `ColumnNotFoundError` → "컬럼 '{name}' 없음", `TypeError` → "타입 불일치: {상세}", `DivisionByZeroError` → "0으로 나누기"
- [ ] FR-B3.5: 데이터 미로드 시 → "데이터를 먼저 로드하세요" 메시지, 다이얼로그 진입 차단
- [ ] FR-B3.6: 대용량 미리보기 시 최대 100행 샘플링, 프로그레스 표시

**B-4: 내보내기 완성**
- [ ] FR-B4.1: 그래프 → PNG/SVG 내보내기 (File → Export → Image)
- [ ] FR-B4.2: 데이터 → CSV/Excel/Parquet 내보내기 (메뉴 연결 확인)
- [ ] FR-B4.3: 리포트 → HTML/PPTX 내보내기 (메뉴 연결 확인)
- [ ] FR-B4.4: ExportDialog에서 형식 선택 + 옵션 설정 + 파일 저장 다이얼로그

**B-5: 주석 시스템 완성**
- [ ] FR-B5.1: View 메뉴 → Annotation Panel 토글이 사이드 패널 표시
- [ ] FR-B5.2: 그래프 위 우클릭 → "Add Annotation" 메뉴. 키보드: Ctrl+Shift+N으로도 추가 가능
- [ ] FR-B5.3: 텍스트 주석 생성/편집/삭제
- [ ] FR-B5.4: 주석 목록에서 클릭 시 해당 데이터 포인트로 네비게이트
- [ ] FR-B5.5: 주석이 프로파일과 함께 저장/로드
- [ ] FR-B5.6: 그래프 미로드 시 주석 추가 시도 → "그래프를 먼저 표시하세요" 토스트

**B-6: 테마 토글 완성**
- [ ] FR-B6.1: View 메뉴 → Theme에서 다크/라이트/미드나이트 전환
- [ ] FR-B6.2: 전환 시 모든 패널(그래프, 테이블, 트리, 상태바) 일괄 반영
- [ ] FR-B6.3: 설정에 테마 선택 저장 (앱 재시작 시 복원)

**B-7: 키보드 단축키 완성**
- [ ] FR-B7.1: shortcuts.py의 모든 단축키가 MainWindow에서 동작
- [ ] FR-B7.2: Help → Keyboard Shortcuts로 단축키 목록 표시
- [ ] FR-B7.3: 텍스트 입력 중일 때 단일 키 단축키 비활성 (검증)
- [ ] FR-B7.4: 단축키 커스터마이즈 다이얼로그 (ShortcutEditDialog 활용)
- [ ] FR-B7.5: 단축키 등록 시 충돌 감지 — `ShortcutController.register()` 호출 시 기존 바인딩과 중복이면 경고 로그 + 이전 바인딩 해제

### Undo 범위 정의

| 동작 | Undoable | 비고 |
|------|----------|------|
| Computed Column 추가 | ✅ | UndoStack에 push, Undo 시 컬럼 제거 |
| Computed Column 삭제 | ✅ | UndoStack에 push, Undo 시 컬럼 복원 |
| 주석 생성/편집/삭제 | ✅ | 각 동작을 UndoStack에 push |
| 대시보드 셀 배치 변경 | ✅ | 레이아웃 변경을 UndoStack에 push |
| 대시보드 모드 토글 | ❌ | 모드 전환은 Undo 대상 아님 |
| 스트리밍 시작/정지 | ❌ | 상태 전환은 Undo 대상 아님 |
| 테마 변경 | ❌ | 설정 변경은 Undo 대상 아님 |
| 데이터셋 추가/삭제 | ❌ | 파일 I/O 작업은 Undo 대상 아님 |
| 필터/정렬 적용 | ✅ | 기존 Undo 동작 유지 |

### 빈 상태(데이터/그래프 없음) 동작 정의

| 기능 | 데이터 미로드 시 | 그래프 없음 시 | 프로파일 없음 시 |
|------|-----------------|--------------|----------------|
| 대시보드 | "No datasets loaded" 메시지, 진입 차단 | 빈 셀 플레이스홀더 | "Click to add chart" |
| 스트리밍 | "No data loaded" 토스트, 시작 차단 | N/A (데이터 기반) | N/A |
| Computed Column | "데이터를 먼저 로드하세요", 진입 차단 | N/A | N/A |
| 주석 | "그래프를 먼저 표시하세요" 토스트 | 추가 버튼 비활성 | N/A |
| 내보내기 (이미지) | 메뉴 비활성 | 메뉴 비활성 | N/A |
| 내보내기 (데이터) | 메뉴 비활성 | N/A | N/A |

### Signal/Slot 해제 규칙
- **규칙 1**: 대시보드 모드는 hide/show만 하므로 Signal 재연결 불필요 (최초 생성 시 1회 연결)
- **규칙 2**: 스트리밍 Stop 시 `FileWatcher`의 Signal 모두 `disconnect()`. 재시작 시 `connect()`
- **규칙 3**: 주석 패널 hide 시 Signal 유지 (visible 상태와 무관하게 프로파일 저장 시 주석 포함)
- **규칙 4**: 위젯 삭제(`deleteLater`) 전 해당 위젯의 모든 Signal `disconnect()`

### 중복 호출 방어 정책
- **대시보드 토글**: `_dashboard_toggling` bool guard. 전환 완료 후 False
- **스트리밍 Play**: 이미 `StreamingState.PLAYING`이면 무시
- **파일 로딩**: `_loading_in_progress` guard. 로딩 중 추가 로딩 요청 → 토스트 "이미 로딩 중"
- **Computed Column 미리보기**: debounce 300ms (입력 후 300ms 대기 후 실행)

### Phase C: UX 품질 개선

**C-1: 루트 정리**
- [ ] FR-C1.1: 루트의 test_*.py → tests/ 이동 또는 삭제
- [ ] FR-C1.2: screenshot*.png, test_data.csv, sensor_data.csv → test_data/ 이동 또는 삭제
- [ ] FR-C1.3: *.html 리포트 파일 → 삭제 (재생성 가능)
- [ ] FR-C1.4: .gitignore 업데이트 (생성물 제외)

**C-2: IPC 동적 포트**
- [ ] FR-C2.1: IPC 서버가 사용 가능한 포트를 자동 선택 (기본값 52849, 사용 중이면 +1씩 최대 100회 시도)
- [ ] FR-C2.2: 선택된 포트를 파일(`~/.dgs/ipc_port`)에 PID와 함께 기록. stale 파일(해당 PID 프로세스 없음) 감지 후 덮어씀
- [ ] FR-C2.3: `dgs_client.py`가 포트 파일을 읽어 자동 연결
- [ ] FR-C2.4: 100회 시도 후 실패 → IPC 비활성화 + 경고 로그 (앱은 정상 동작)

**C-3: Autosave 복구 개선**
- [ ] FR-C3.1: 복구 다이얼로그가 앱 초기화를 블로킹하지 않도록 `QTimer.singleShot(500ms)` 지연
- [ ] FR-C3.2: "Don't show again" 체크박스 (설정에 저장)
- [ ] FR-C3.3: 복구 실패 시 autosave.json → autosave.json.bak 백업 후 삭제, 에러 토스트

**C-4: 에러 핸들링 강화**
- [ ] FR-C4.1: 대용량 파일 로딩 시 프로그레스바 + 취소 버튼 (동작 검증)
- [ ] FR-C4.2: 파일 로딩 실패 시 사용자 친화적 에러 메시지 (파일 크기, 인코딩, 형식 힌트)
- [ ] FR-C4.3: 글로벌 에러 핸들러 — `sys.excepthook` 설정, 크래시 방지, `~/.dgs/crash.log`에 기록

**C-5: README 업데이트**
- [ ] FR-C5.1: 새 아키텍처 다이어그램 (DataEngine Facade → 5 모듈)
- [ ] FR-C5.2: v2 기능 사용 가이드 (대시보드, 스트리밍, Computed Column 등)

**C-6: CHANGELOG 업데이트**
- [ ] FR-C6.1: v0.21 변경사항 기록 — DataEngine 분리, v2 기능 와이어링, UX 개선

**C-7: Docstring 기준**
- [ ] FR-C7.1: FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine의 모든 public 메서드에 Google-style docstring (Args/Returns/Raises) 필수
- [ ] FR-C7.2: TODO/FIXME에 `# TODO(@담당자, YYYY-MM): 설명` 포맷 적용

### closeEvent 정리 순서
앱 종료 시 반드시 아래 순서대로 정리:
1. 스트리밍 Stop (FileWatcher 중단, Signal disconnect)
2. Autosave 저장 (최종 상태)
3. Autosave 타이머 Stop
4. Memory 모니터 타이머 Stop
5. IPC 서버 Shutdown
6. Loader 스레드 Join (타임아웃 3초)
7. 리소스 해제 (gc.collect)

### 4.2 비기능 요구사항 (NFR)
- [ ] NFR-1: DataEngine 분리 후 기존 테스트 100% 통과
- [ ] NFR-2: `DataEngine` import 호환성 100% (re-export)
- [ ] NFR-3: 각 분리 모듈 파일 크기 ≤ 800줄
- [ ] NFR-4: 대시보드 3×3 렌더링 시 메인 스레드 <16ms/frame
- [ ] NFR-5: IPC 포트 충돌 시 앱 크래시 없음
- [ ] NFR-6: 핵심 연산 성능: `filter/sort` < 100ms (100만 행), `get_statistics` < 500ms (100만 행)
- [ ] NFR-7: 대시보드 셀 업데이트 배치: `QTimer.singleShot(0)` 통합으로 1프레임당 최대 1회 repaint

## 5. 범위
### 포함
- DataEngine 5모듈 분리 + Facade (FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine)
- v2 7개 기능 MainWindow 와이어링
- 루트 정리, IPC 동적 포트, autosave 개선, 에러 핸들링
- README, CHANGELOG, docstring 업데이트

### 제외
- 새로운 v2 기능 코어 구현 (이미 존재하는 코어만 와이어링)
- 성능 최적화 (LTTB 다운샘플링 등은 후속)
- 대시보드 드래그앤드롭 리사이즈 (MVP는 프리셋 레이아웃만)
- 새 차트 타입 추가
- 이모지→SVG 아이콘 마이그레이션 (후속 작업으로 별도 PRD)

## 6. 기술 설계

### 아키텍처 (분리 후)
```
core/
├── data_engine.py        (~350줄, Facade + 캐시)
├── file_loader.py        (~700줄, 파일 I/O + 로딩)
├── data_query.py         (~400줄, 조회/변환/통계)
├── data_exporter.py      (~100줄, CSV/Excel/Parquet 내보내기)
├── dataset_manager.py    (~400줄, 멀티 데이터셋)
├── comparison_engine.py  (~700줄, 비교 분석)
├── state.py              (기존 유지)
├── statistics.py         (기존 유지)
├── expressions.py        (기존 유지)
└── ...
```

### DataEngine Facade 패턴
```python
class DataEngine:
    def __init__(self, precision_mode=PrecisionMode.AUTO):
        self._loader = FileLoader(precision_mode)
        self._query = DataQuery()
        self._exporter = DataExporter()
        self._datasets = DatasetManager(self._loader)
        self._comparison = ComparisonEngine(self._datasets)
        self._cache: LRUCache = LRUCache(maxsize=128)

    @property
    def df(self) -> Optional[pl.DataFrame]:
        """활성 데이터셋의 DataFrame. 없으면 FileLoader의 단일 df."""
        if self._datasets.active_dataset_id:
            return self._datasets.get_dataset_df(self._datasets.active_dataset_id)
        return self._loader._df

    def load_file(self, *args, **kwargs):
        self._cache.clear()
        return self._loader.load_file(*args, **kwargs)
    
    def filter(self, *args, **kwargs):
        return self._query.filter(self.df, *args, **kwargs)  # 새 df 반환, self._df 미변경
    
    def export_csv(self, *args, **kwargs):
        return self._exporter.export_csv(self.df, *args, **kwargs)
```

### 의존성 방향
```
ComparisonEngine → DatasetManager → FileLoader
DataEngine (Facade) → FileLoader, DataQuery, DataExporter, DatasetManager, ComparisonEngine
MainWindow → DataEngine (Facade, 변경 없음)
```

### 단축키 매트릭스 (충돌 감사)

| 단축키 | 기존 용도 | 새 용도 | 충돌 |
|--------|----------|---------|------|
| Ctrl+D | (미사용) | 대시보드 모드 토글 | ✅ 안전 |
| Ctrl+Shift+A | (미사용) | 주석 패널 토글 | ✅ 안전 |
| Ctrl+Shift+N | (미사용) | 주석 추가 | ✅ 안전 |
| Ctrl+E | 내보내기 | 내보내기 (유지) | ✅ 유지 |
| Ctrl+T | (미사용) | 테마 전환 | ✅ 안전 |
| Ctrl+/ | (미사용) | 단축키 도움말 | ✅ 안전 |
| F11 | 전체화면 | 전체화면 (유지) | ✅ 유지 |

## 7. 엣지 케이스 & 에러 처리
- EC-1: DataEngine 분리 중 import 경로 변경 → re-export로 100% 호환
- EC-2: 대시보드 모드에서 프로파일이 0개 → 빈 셀 플레이스홀더 표시
- EC-3: 스트리밍 중 파일 삭제 → 감시 중단 + "파일이 삭제됨" 토스트
- EC-4: Computed Column 표현식 구문 오류 → 에러 종류별 인라인 메시지
- EC-5: IPC 포트 100회 시도 후 실패 → IPC 비활성화 + 경고 로그
- EC-6: autosave.json 파싱 실패 → .bak 백업 후 삭제, 앱 정상 시작
- EC-7: 대시보드 셀에 할당된 프로파일이 삭제됨 → 해당 셀 빈 상태 복원
- EC-8: 테마 전환 중 그래프 렌더링 → 전환 완료 후 일괄 repaint
- EC-9: ComparisonEngine 비교 중 데이터셋 삭제 → snapshot 사용으로 영향 없음, 결과는 stale 표시
- EC-10: FileLoader 로딩 성공 후 DatasetManager 등록 실패 → 이전 상태 복원
- EC-11: 스트리밍 + 대시보드 동시 사용 → 데이터 갱신 시 대시보드 셀 배치 repaint (singleShot 배치)

## 8. 알려진 리스크 (Pre-mortem)
| 리스크 | 확률 | 영향 | 대응 |
|--------|------|------|------|
| DataEngine 분리 시 내부 상태 공유 문제 | 중 | 높음 | 상태 소유권 다이어그램 명시, Facade가 유일한 상태 변경점 |
| v2 기능 코어에 숨은 버그 | 높음 | 중 | 각 기능 와이어링 후 수동 검증 + 통합 테스트 |
| 기존 테스트가 DataEngine 내부에 의존 | 중 | 중 | Facade API 불변, 기존 테스트 기준선 기록 후 비교 |
| 스트리밍 동시 접근 race condition | 중 | 높음 | 메인 스레드 전용 df 교체, QueuedConnection |
| 캐시 무효화 누락 | 중 | 중 | load_file/activate/remove에서 일괄 clear |
| 대시보드 위젯 메모리 누수 | 낮음 | 중 | lazy 생성 1회, hide/show만 토글 |

## 9. 성능 목표
- DataEngine 분리 후 100MB CSV 로딩 성능 차이 < 5%
- `filter/sort` < 100ms (100만 행)
- `get_statistics` < 500ms (100만 행)
- 대시보드 2×2 초기 렌더링 < 1초
- IPC 포트 자동 선택 < 100ms

## 10. 테스트 시나리오

### 테스트 전략
- **테스트 픽스처**: `tests/fixtures/` 디렉토리에 소형 샘플 파일 (CSV 10행, Parquet, JSON, TSV)
- **대용량 모킹**: `conftest.py`에 `create_large_df(n_rows)` 팩토리
- **네이밍 규칙**: `test_{모듈}_{시나리오}_{기대결과}` (예: `test_fileloader_csv_로딩성공`)
- **기존 테스트 기준선**: 분리 전 `pytest --co -q` 결과를 `tests/baseline.txt`에 기록

### Unit Tests
- [ ] UT-1: FileLoader — CSV, TSV, TXT, Parquet, JSON, Excel 각각 로딩 성공
- [ ] UT-2: FileLoader — 존재하지 않는 파일 → FileNotFoundError
- [ ] UT-3: FileLoader — 취소 시 로딩 중단, _df 미변경
- [ ] UT-4: FileLoader — windowed loading 시작/이동/범위초과
- [ ] UT-5: FileLoader — ETL 바이너리/텍스트 분기 (etl-parser 유무)
- [ ] UT-6: DataQuery.filter() — 조건 일치/불일치/빈 결과
- [ ] UT-7: DataQuery.sort() — 단일/복수 컬럼, 오름/내림차순
- [ ] UT-8: DataQuery.get_statistics() — 수치/문자/혼합 컬럼
- [ ] UT-9: DataExporter — CSV/Excel/Parquet 내보내기 + 선택 행만 내보내기
- [ ] UT-10: DatasetManager — 추가/삭제/활성화/메모리 한도 초과
- [ ] UT-11: DatasetManager — 삭제 시 dataset_removing 이벤트 발행 확인
- [ ] UT-12: ComparisonEngine — correlation 계산, 통계 검정
- [ ] UT-13: ComparisonEngine — 비교 중 원본 변경 시 snapshot으로 안전
- [ ] UT-14: DataEngine Facade — 기존 API 호출이 하위 모듈로 위임 확인
- [ ] UT-15: DataEngine Facade — load_file 후 캐시 clear 확인

### Integration Tests
- [ ] IT-1: DataEngine으로 파일 로딩 → 필터 → 통계 → 내보내기 전체 흐름
- [ ] IT-2: 대시보드 모드 진입 → 프로파일 배치 → 레이아웃 저장/불러오기
- [ ] IT-3: 스트리밍 시작 → 파일 변경 → 그래프 업데이트 (이벤트 기반 대기, 타임아웃 5초)
- [ ] IT-4: 주석 CRUD — 생성 → 편집 → 네비게이트 → 삭제
- [ ] IT-5: 테마 전환 → 모든 패널 스타일 변경 확인 → 앱 재시작 후 복원
- [ ] IT-6: 단축키 동작 — Ctrl+D(대시보드), Ctrl+Shift+A(주석), Ctrl+E(내보내기)
- [ ] IT-7: Computed Column 추가 → 테이블 반영 → Undo → 컬럼 제거 확인
- [ ] IT-8: 내보내기 전체 흐름 — PNG, CSV, HTML 각 형식

### E2E Tests
- [ ] E2E-1: CSV 로딩 → 대시보드 2×2 → 각 셀에 프로파일 배치
- [ ] E2E-2: IPC 포트 충돌 상황에서 앱 정상 시작 확인
- [ ] E2E-3: closeEvent 정리 순서 — 스트리밍 중 앱 종료 시 리소스 누수 없음

### flaky 방지
- IT-3: `polling timeout + retry` 대신 `Signal` 수신 대기 + `QTest.qWaitFor(condition, 5000)`
- E2E 스크린샷 비교 → DOM/위젯 상태 검증으로 대체

## 11. 성공 기준
- [ ] DataEngine 분리 후 data_engine.py ≤ 400줄
- [ ] 기존 테스트 100% 통과 (baseline 대비)
- [ ] v2 7개 기능 모두 메뉴/툴바에서 접근 가능 + 빈 상태 정상 처리
- [ ] 루트 디렉토리 잡파일 0개
- [ ] IPC 포트 충돌 시 앱 정상 동작
- [ ] 새 모듈 public 메서드 docstring 100%

## 12. 미해결 질문
없음.

## 13. 실행 계획

### 구현 순서 & 병렬 그룹

**Group 1 (병렬, 의존성 없음):**
- Agent 1: Phase A — DataEngine 분리 (file_loader, data_query, data_exporter, dataset_manager, comparison_engine, facade)
- Agent 2: Phase C — UX 개선 (루트 정리, IPC 동적 포트, autosave 개선, 에러 핸들링, README, CHANGELOG, docstring)

**Group 2 (순차, Group 1 완료 후):**
- Agent 3: Phase B-1~B-3 — 대시보드, 스트리밍, Computed Column 와이어링
- Agent 4: Phase B-4~B-7 — 내보내기, 주석, 테마, 단축키 와이어링

### 예상 파일 변경
- 신규: `core/file_loader.py`, `core/data_query.py`, `core/data_exporter.py`, `core/dataset_manager.py`, `core/comparison_engine.py`, `tests/fixtures/`, `tests/baseline.txt`
- 수정: `core/data_engine.py` (Facade로 축소), `ui/main_window.py` (와이어링 추가+closeEvent 정리), `core/__init__.py`, `.gitignore`, `README.md`, `CHANGELOG.md`
- 이동: 루트 test_*.py → tests/
- 삭제: screenshot*.png, test_data.csv (루트), *.html 리포트
