# PRD: Data Graph Studio v2 — 7대 기능 확장

## 1. 목표
DGS를 단순 CSV 뷰어에서 **전문 데이터 분석 도구**로 도약시키는 7개 핵심 기능을 추가한다.

## 2. 배경
현재 DGS는 CSV/Parquet 로딩, 기본 차트, 멀티 데이터셋, 프로파일 비교 기능을 갖추고 있다. 그러나 실무 데이터 분석에 필수적인 대시보드, 실시간 모니터링, 데이터 변환, 내보내기, 주석, 테마 토글, 단축키 기능이 부재하여 사용성에 한계가 있다.

### 현재 아키텍처
```
main.py → MainWindow
├── core/
│   ├── state.py (AppState — 전역 상태)
│   ├── data_engine.py (DataEngine — Polars 기반 데이터 처리)
│   ├── profile_store.py (ProfileStore — 프로파일 CRUD)
│   ├── profile_controller.py (ProfileController — 오케스트레이션)
│   ├── profile_comparison_controller.py (비교 모드 컨트롤러)
│   └── view_sync.py (ViewSyncManager — 뷰 동기화)
├── ui/
│   ├── main_window.py (MainWindow — IPC 서버 포함)
│   ├── panels/ (graph_panel, table_panel, summary_panel, stats_panel 등)
│   ├── views/ (project_tree_view)
│   ├── models/ (profile_model)
│   └── theme.py (Tailwind 테마)
└── IPC 서버 (TCP:52849)
```

## 3. 요구사항

### Feature 1: 대시보드 모드 (Dashboard Mode)

#### 3.1.1 기능 요구사항
- [ ] FR-1.1: 사용자가 "Dashboard Mode"를 활성화하면, 메인 영역이 격자 레이아웃(1×1~3×3)으로 전환된다.
- [ ] FR-1.2: 각 격자 셀에 독립적인 차트 위젯을 배치할 수 있다. (드래그앤드롭 또는 셀 클릭 → 프로파일 선택)
- [ ] FR-1.3: 셀 크기를 드래그로 조절할 수 있다. (가로/세로 스팬 지원: 1셀이 2×1 또는 1×2로 확장 가능)
- [ ] FR-1.4: 대시보드 레이아웃을 저장/불러오기 할 수 있다. (JSON 형식, 프로파일 ID + 셀 위치 + 크기)
- [ ] FR-1.5: 각 셀의 차트는 독립적으로 줌/팬 가능하며, 선택적으로 X축/Y축 동기화가 가능하다.
- [ ] FR-1.6: 대시보드 모드에서 "Exit" 버튼 또는 Esc로 일반 모드로 복귀한다.
- [ ] FR-1.7: 대시보드에 빈 셀은 "Click to add chart" 플레이스홀더를 표시한다.
- [ ] FR-1.8: 대시보드 레이아웃 프리셋 제공: 1×1, 1×2, 2×1, 2×2, 1×3, 3×1, 2×3.
- [ ] FR-1.9: 대시보드 셀의 최소 크기는 **240×180px**로 제한한다. 셀이 최소 크기 이하로 줄어들 수 없으며, 창 크기가 모든 셀을 최소 크기로 표시할 수 없을 경우 스크롤바를 표시한다.
- [ ] FR-1.10: 대시보드 초기 렌더링 시 각 셀에 스피너(로딩 인디케이터)를 표시하고, 렌더링 완료 후 차트로 교체한다.

#### 3.1.2 비기능 요구사항
- [ ] NFR-1.1: 9개 셀(3×3) 동시 렌더링 시 메인 스레드 프레임 드롭 없음 (<16ms/frame)
- [ ] NFR-1.2: 레이아웃 전환(일반↔대시보드) 시 <500ms
- [ ] NFR-1.3: 저장된 대시보드 JSON < 10KB
- [ ] NFR-1.4: **다운샘플링 전략** — 각 셀의 데이터 포인트가 화면 픽셀 수의 4배를 초과하면 **LTTB(Largest Triangle Three Buckets)** 알고리즘으로 다운샘플링한다. 예: 셀 너비 400px → 최대 1600 포인트 렌더링. 줌인 시 원본 데이터에서 재샘플링한다.
- [ ] NFR-1.5: **반응형 정책** — 대시보드 최소 창 크기는 **800×600px**. 3×3 레이아웃에서 창이 최소 크기보다 작아지면 가장 오른쪽/아래 셀부터 오버플로우 스크롤. 각 셀 헤더(프로파일 이름)는 ellipsis(`…`)로 잘림 처리.

#### 3.1.3 에러/취소 시나리오
- [ ] ERR-1.1: 대시보드 셀에 할당된 프로파일이 삭제된 경우 → 해당 셀을 빈 상태(FR-1.7)로 복원하고 "Profile removed" 토스트 메시지 표시.
- [ ] ERR-1.2: 대시보드 레이아웃 JSON 로드 실패(파싱 오류, 스키마 불일치) → 기본 2×2 레이아웃으로 폴백, 에러 토스트 표시.
- [ ] ERR-1.3: 데이터셋이 없는 상태에서 대시보드 활성화 → "No datasets loaded. Open a file first." 안내 메시지와 함께 대시보드 진입 차단.
- [ ] ERR-1.4: 레이아웃 편집 중 Esc/취소 → 편집 이전 레이아웃 상태로 즉시 복귀 (Undo 스택에 push하지 않음).

### Feature 2: 실시간 데이터 스트리밍 (Live Data Streaming)

#### 3.2.1 기능 요구사항
- [ ] FR-2.1: 파일 워치 모드 — 로드된 CSV/Parquet 파일이 디스크에서 변경되면 자동 감지 후 리로드한다.
- [ ] FR-2.2: Tail 모드 — CSV 파일에 새 행이 추가되면, 전체 리로드 없이 새 행만 추가(append) 한다.
- [ ] FR-2.3: 스트리밍 활성화/비활성화 토글 UI (툴바 또는 메뉴).
- [ ] FR-2.4: 폴링 간격을 설정할 수 있다 (기본 1초, 범위 0.5초~60초).
- [ ] FR-2.5: 차트에서 "Follow tail" 옵션 — 새 데이터가 추가되면 자동으로 X축 끝으로 스크롤.
- [ ] FR-2.6: 스트리밍 상태를 상태바에 표시 (🟢 Live / ⏸ Paused / ⏹ Off).
- [ ] FR-2.7: 파일이 삭제되거나 접근 불가 시 자동으로 스트리밍을 중단하고 사용자에게 알림.
- [ ] FR-2.8: **FileWatcher 무한 루프 방지** — 자기 자신의 저장/리로드로 인한 파일 변경을 무시한다.
  - Self-change 무시: 앱 내부에서 파일을 수정하기 직전에 `_self_modifying` 플래그를 설정하고, 변경 감지 콜백에서 해당 플래그가 켜져 있으면 무시한다.
  - Debounce: 파일 변경 이벤트를 **300ms debounce**하여 연속 이벤트를 하나로 병합한다.
  - 변경 감지 기준: `mtime + file_size` 조합 비교. mtime만으로는 같은 초 내 변경을 놓칠 수 있음.

#### 3.2.2 비기능 요구사항
- [ ] NFR-2.1: Tail 추가 시 기존 데이터프레임을 복사하지 않음 (Polars concat/extend)
- [ ] NFR-2.2: 폴링이 메인 스레드를 블로킹하지 않음 (QThread/QTimer 기반)
- [ ] NFR-2.3: 100만 행 파일에 1000행 추가 시 차트 업데이트 <200ms
- [ ] NFR-2.4: **대용량 리로드(전체 파일 재로드) 시** — 500ms 이상 소요될 경우 상태바에 프로그레스 표시(파일 읽기 진행률). 리로드 중 기존 데이터를 유지하고, 완료 시 swap.

#### 3.2.3 에러/취소 시나리오
- [ ] ERR-2.1: 파일 삭제/이동 시 → 스트리밍 자동 중단, "File not found: {path}" 경고 다이얼로그. 사용자가 "Locate File" 또는 "Stop Watching"을 선택.
- [ ] ERR-2.2: 파일 헤더(컬럼 구조) 변경 시 → 스트리밍 중단, "File schema changed. Reload required." 알림. 기존 데이터 유지, 사용자가 수동 리로드 선택.
- [ ] ERR-2.3: 파일 읽기 권한 오류 시 → "Permission denied: {path}" 에러, 3회 재시도 후 스트리밍 중단.
- [ ] ERR-2.4: 스트리밍 토글 OFF 시 → FileWatcher 즉시 해제, 타이머 중단. 현재 로드된 데이터는 유지.

### Feature 3: 데이터 변환 파이프라인 (Computed Columns)

#### 3.3.1 기능 요구사항
- [ ] FR-3.1: "Add Computed Column" 다이얼로그에서 수식을 입력하여 새 컬럼을 생성한다.
  - 지원 연산: 사칙연산(+,-,*,/), 비교(>, <, ==), 논리(and, or, not)
  - 컬럼 참조: `{column_name}` 형식 (예: `{voltage} * {current}`)
  - 내장 함수: `abs()`, `round()`, `log()`, `sqrt()`, `pow()`, `clip(min, max)`
- [ ] FR-3.2: 이동 평균(Moving Average) — 윈도우 크기를 지정하여 rolling mean 컬럼을 생성한다.
- [ ] FR-3.3: 미분(Difference) — 인접 행 간의 차이값 컬럼을 생성한다. (1차, 2차 미분)
- [ ] FR-3.4: 누적합(Cumulative Sum) — 컬럼의 누적합 컬럼을 생성한다.
- [ ] FR-3.5: 정규화(Normalize) — min-max 또는 z-score 정규화 컬럼을 생성한다.
- [ ] FR-3.6: 생성된 컬럼은 원본 데이터와 동일하게 차트 Y축, 필터, 통계에서 사용 가능하다.
- [ ] FR-3.7: 생성된 컬럼은 프로파일에 포함되어 저장/복원된다.
- [ ] FR-3.8: 생성된 컬럼 목록을 관리 패널에서 편집/삭제할 수 있다.
- [ ] FR-3.9: 수식 오류 시 사용자 친화적 에러 메시지 (어디가 잘못되었는지 하이라이트).
- [ ] FR-3.10: **순환 참조 방지** — 생성 컬럼이 다른 생성 컬럼을 참조할 때, DAG(Directed Acyclic Graph) 검증을 수행한다.
  - 새 컬럼 생성/편집 시 의존성 그래프에 대해 **토폴로지 정렬**을 실행한다.
  - 순환이 감지되면 컬럼 생성을 차단하고 에러 메시지 표시: `"Circular reference detected: {col_A} → {col_B} → {col_A}. Remove the cycle to proceed."`
  - 의존성 그래프는 `Dict[str, Set[str]]` (컬럼명 → 참조하는 컬럼명 집합)으로 관리한다.
  - 컬럼 삭제 시, 해당 컬럼에 의존하는 다른 생성 컬럼이 있으면 경고: `"Column '{name}' is referenced by: {dependents}. Delete anyway?"`. 확인 시 의존 컬럼도 함께 삭제(cascade) 또는 에러 상태로 전환.
- [ ] FR-3.11: **수식 화이트리스트** — 허용된 Polars 함수/연산자만 사용 가능하며, 비허용 함수 호출 시 차단한다.
  - 허용 연산자: `+`, `-`, `*`, `/`, `//`, `%`, `**`, `>`, `<`, `>=`, `<=`, `==`, `!=`, `&`, `|`, `~`
  - 허용 Polars 함수:
    - 수학: `abs`, `sqrt`, `log`, `log10`, `exp`, `pow`, `round`, `floor`, `ceil`, `clip`
    - 통계: `mean`, `std`, `var`, `min`, `max`, `sum`, `median`, `quantile`
    - 윈도우: `rolling_mean`, `rolling_std`, `rolling_min`, `rolling_max`, `rolling_sum`
    - 변환: `cast`, `fill_null`, `fill_nan`, `shift`, `diff`, `cum_sum`, `cum_max`, `cum_min`
    - 조건: `when`, `then`, `otherwise`
    - 문자열: (없음 — 수치 컬럼 전용)
  - **차단 정책**: 수식 파서가 AST를 순회하며 화이트리스트에 없는 함수 호출을 발견하면 즉시 차단. 에러 메시지: `"Function '{func_name}' is not allowed. Allowed functions: {list}"`
  - `eval()`, `exec()`, `import`, `__` 접두사 식별자는 무조건 차단 (Python 인젝션 방지).

#### 3.3.2 비기능 요구사항
- [ ] NFR-3.1: 수식 평가는 Polars Expressions 기반 (Python eval 사용 금지 — 보안)
- [ ] NFR-3.2: 100만 행에 대한 컬럼 생성 <500ms. **500ms 이상 소요 시 워커 스레드(QThread)에서 실행**하고, 다이얼로그에 프로그레스 바와 "Cancel" 버튼을 표시한다. 워커 완료 시 `Signal`로 메인 스레드에 결과를 전달한다.
- [ ] NFR-3.3: 생성 컬럼은 레이지 평가 (실제 사용 시점에 계산)

#### 3.3.3 에러/취소 시나리오
- [ ] ERR-3.1: 수식에서 존재하지 않는 컬럼 참조 → `"Column '{name}' not found. Available columns: {list}"` 에러.
- [ ] ERR-3.2: 0으로 나누기 → 해당 행을 `null`로 처리하고, 결과 프리뷰에 `"Warning: {N} rows resulted in null (division by zero)"` 표시.
- [ ] ERR-3.3: 타입 불일치 (문자열 컬럼에 수학 연산) → `"Type error: column '{name}' is {type}, expected numeric."` 에러.
- [ ] ERR-3.4: 워커 스레드에서 컬럼 생성 중 사용자가 Cancel 클릭 → 워커 즉시 중단, 부분 결과 폐기, 데이터 상태 변경 없음.
- [ ] ERR-3.5: 순환 참조 감지 → FR-3.10의 에러 메시지 표시, 컬럼 생성 차단.

### Feature 4: 내보내기 강화 (Export Enhancement)

#### 3.4.1 기능 요구사항
- [ ] FR-4.1: 차트를 PNG로 내보내기 (현재 화면 해상도, 또는 지정 해상도: 1920×1080, 3840×2160).
- [ ] FR-4.2: 차트를 SVG로 내보내기 (벡터 형식, 편집 가능).
- [ ] FR-4.3: 차트를 PDF로 내보내기 (A4/Letter 크기, 차트 + 통계 요약 포함).
- [ ] FR-4.4: 현재 뷰의 데이터를 CSV/Parquet/Excel로 내보내기 (필터/정렬/생성 컬럼 포함).
- [ ] FR-4.5: 대시보드 전체를 하나의 PDF/PNG로 내보내기.
- [ ] FR-4.6: 내보내기 설정 다이얼로그: 파일 형식, 크기, DPI, 배경색(투명/흰색/다크), 범례 포함 여부.
- [ ] FR-4.7: 클립보드에 복사 (Cmd+C로 차트 이미지, Cmd+Shift+C로 데이터 테이블).
- [ ] FR-4.8: IPC 커맨드 `export_chart`, `export_data`, `export_dashboard`.
- [ ] FR-4.9: **내보내기 프로그레스** — 모든 내보내기 작업에 프로그레스 다이얼로그를 표시한다.
  - 프로그레스 바 + 취소 버튼
  - 단계 표시: "Rendering chart..." → "Writing file..." → "Complete"
  - 대시보드 PDF 내보내기 시 셀 단위 진행률: "Exporting cell 3/9..."

#### 3.4.2 비기능 요구사항
- [ ] NFR-4.1: PNG 내보내기 <1초 (풀HD), SVG <2초
- [ ] NFR-4.2: PDF 생성 시 외부 의존성 최소화 (reportlab 또는 Qt 내장 PDF)
- [ ] NFR-4.3: 내보내기 중 UI 블로킹 없음 (워커 스레드)

#### 3.4.3 에러/취소 시나리오
- [ ] ERR-4.1: 디스크 공간 부족 → `"Not enough disk space. Required: {size}, Available: {avail}"`. 내보내기 중단, 부분 파일 삭제.
- [ ] ERR-4.2: 파일 쓰기 권한 오류 → `"Permission denied: {path}. Choose a different location."` 파일 선택 다이얼로그 재표시.
- [ ] ERR-4.3: 내보내기 중 Cancel 클릭 → 워커 스레드 중단, 부분 생성된 파일 삭제, 롤백 완료 토스트 표시.
- [ ] ERR-4.4: PDF 렌더링 실패 (메모리 부족) → `"Export failed: insufficient memory for {cols}×{rows} dashboard."` 해상도를 낮추도록 안내.

### Feature 5: 북마크 & 데이터 주석 (Bookmarks & Annotations)

#### 3.5.1 기능 요구사항
- [ ] FR-5.1: 차트 위 데이터 포인트를 클릭하여 주석(Annotation)을 추가할 수 있다.
  - 텍스트 입력 (최대 200자)
  - 아이콘/색상 선택 (🔴🟡🟢🔵 + 경고⚠️, 체크✅, 별⭐)
- [ ] FR-5.2: 주석은 데이터 좌표(x, y)에 앵커되어, 줌/팬 시 따라 이동한다.
- [ ] FR-5.3: X축 범위를 드래그하여 "구간 북마크"를 생성할 수 있다 (하이라이트 + 라벨).
- [ ] FR-5.4: 북마크/주석 목록 패널에서 전체 주석을 리스트로 보고, 클릭하면 해당 위치로 이동.
- [ ] FR-5.5: 주석은 프로파일에 포함되어 저장/복원된다.
- [ ] FR-5.6: 주석을 편집/삭제할 수 있다 (우클릭 컨텍스트 메뉴).
- [ ] FR-5.7: 주석 표시/숨기기 토글.
- [ ] FR-5.8: **주석 인터랙션 모드 전환** — 차트는 기본적으로 **탐색 모드**(줌/팬)이며, 주석 추가/구간 북마크 생성을 위해 **주석 모드**로 전환해야 한다.
  - **진입 방법 (3가지 지원)**:
    1. 툴바의 📌 "Annotate" 토글 버튼 클릭 (활성 시 버튼 강조 표시)
    2. 단축키 `Cmd+Shift+A` (주석 모드 토글)
    3. 주석 패널이 열려 있는 상태에서 차트 위 `Shift+클릭` (일시적 주석 추가 — 모드 전환 없이)
  - **모드별 커서 변경**: 탐색 모드 = 🖐️ grab cursor, 주석 모드 = ✚ crosshair cursor
  - **모드 표시**: 차트 우측 상단에 현재 모드 뱃지 표시 ("📌 Annotate" / 표시 없음)
  - **자동 퇴장**: 주석 추가 완료(다이얼로그 OK) 후 자동으로 탐색 모드로 복귀. 연속 주석 추가를 원하면 `Shift` 키를 누른 채 OK 클릭 시 주석 모드 유지.
  - **주석 모드에서의 클릭 동작**:
    - 데이터 포인트 근처 클릭(±5px snap) → 포인트 주석 추가 다이얼로그
    - 빈 영역 클릭 → 해당 좌표에 자유 주석 추가 다이얼로그
    - 드래그 → 구간 북마크 생성 (X축 범위 선택)
  - **탐색 모드에서의 주석 상호작용**:
    - 기존 주석 마커 호버 → 텍스트 팝업 표시
    - 기존 주석 마커 클릭 → 주석 편집 다이얼로그 (모드 전환 불필요)
    - 기존 주석 마커 우클릭 → 컨텍스트 메뉴 (편집/삭제/색상 변경)
  - **대시보드 모드 연동**: 주석 모드는 현재 포커스된 셀에만 적용. 셀 포커스 변경 시 주석 모드 자동 해제.

#### 3.5.2 비기능 요구사항
- [ ] NFR-5.1: 주석 1000개까지 성능 저하 없음
- [ ] NFR-5.2: 주석 데이터 < 100KB (1000개 기준)

#### 3.5.3 에러/취소 시나리오
- [ ] ERR-5.1: 주석 텍스트가 200자를 초과하면 → 입력 필드에서 201자부터 입력 차단, 남은 글자 수 표시.
- [ ] ERR-5.2: 주석 추가 중 다이얼로그에서 Cancel → 주석 생성 취소, 데이터 변경 없음.
- [ ] ERR-5.3: 주석이 참조하는 데이터셋이 삭제된 경우 → 해당 주석을 "orphaned" 상태로 표시(회색), 주석 패널에서 일괄 정리 가능.

### Feature 6: 다크/라이트 테마 토글 (Theme Toggle)

#### 3.6.1 기능 요구사항
- [ ] FR-6.1: 메뉴바 또는 툴바에 테마 토글 버튼 (🌙/☀️ 아이콘).
- [ ] FR-6.2: 클릭 시 즉시 라이트↔다크 전환 (기존 Tailwind 테마 활용).
- [ ] FR-6.3: 테마 선호가 앱 종료 후에도 유지된다 (QSettings 또는 설정 파일).
- [ ] FR-6.4: "System" 옵션 — macOS 다크모드 설정을 따른다.
- [ ] FR-6.5: 차트(pyqtgraph) 배경/전경색도 테마에 맞게 변경된다.
- [ ] FR-6.6: 테마 전환 시 깜빡임(flash) 없이 부드러운 전환.
- [ ] FR-6.7: IPC 커맨드 `set_theme dark|light|system`, `get_theme`.

#### 3.6.2 비기능 요구사항
- [ ] NFR-6.1: 테마 전환 <100ms (모든 위젯 스타일시트 업데이트 포함)
- [ ] NFR-6.2: 테마 전환 시 차트 데이터 리로드 없음

#### 3.6.3 에러/취소 시나리오
- [ ] ERR-6.1: 테마 설정 파일 손상 시 → 기본 테마(Light)로 폴백, 설정 파일 재생성.
- [ ] ERR-6.2: 테마 토글 연타 시 → 마지막 토글 결과만 적용 (debounce 100ms). 중간 상태가 렌더링되지 않음.

### Feature 7: 키보드 단축키 패널 (Keyboard Shortcuts)

#### 3.7.1 기능 요구사항
- [ ] FR-7.1: 전역 단축키 매핑:
  | 단축키 | 동작 | 비고 |
  |--------|------|------|
  | `Cmd+O` | 파일 열기 | |
  | `Cmd+S` | 프로파일 저장 | |
  | `Cmd+Shift+S` | 다른 이름으로 프로파일 저장 | |
  | `Cmd+E` | 내보내기 다이얼로그 | |
  | `Cmd+Shift+D` | 대시보드 모드 토글 | ~~Cmd+D~~ macOS Dock 충돌 회피 |
  | `Cmd+Shift+L` | 실시간 스트리밍 토글 | ~~Cmd+L~~ macOS 주소바 충돌 회피 |
  | `Cmd+T` | 테마 토글 | |
  | `Cmd+K` | 컬럼 생성 다이얼로그 | |
  | `Cmd+Shift+A` | 주석 모드 토글 | 차트 인터랙션 모드 전환 (탐색↔주석) |
  | `Cmd+Shift+B` | 주석 패널 토글 | ~~Cmd+B~~ 볼드체 충돌 회피 |
  | `Cmd+1~9` | 대시보드 셀 포커스 | |
  | `Cmd+/` | 단축키 도움말 표시 | |
  | `Cmd+Z` | Undo | |
  | `Cmd+Shift+Z` | Redo | |
  | `Space` | 차트에서 팬 모드 토글 | 텍스트 입력 중 비활성화 |
  | `F11` | 전체 화면 토글 | |
- [ ] FR-7.2: "Keyboard Shortcuts" 다이얼로그 (Cmd+/ 또는 메뉴) — 모든 단축키 목록 표시.
- [ ] FR-7.3: 단축키 커스터마이징 — 사용자가 원하는 키 조합으로 변경 가능.
- [ ] FR-7.4: 단축키 충돌 감지 — 같은 키 조합에 2개 동작 할당 시 경고.
- [ ] FR-7.5: 단축키 설정은 앱 종료 후에도 유지된다.
- [ ] FR-7.6: **macOS 시스템 단축키 충돌 방지** — 기본 매핑에서 macOS 시스템 단축키(Cmd+H, Cmd+M, Cmd+Q, Cmd+W, Cmd+D 등)와 겹치는 조합을 사용하지 않는다. 사용자가 커스터마이징 시 시스템 단축키와 충돌하면 경고: `"'{key}' conflicts with macOS system shortcut. Use anyway?"`

#### 3.7.2 비기능 요구사항
- [ ] NFR-7.1: 단축키 입력 → 동작 실행 <50ms
- [ ] NFR-7.2: 텍스트 입력 필드에 포커스 있을 때 단축키 비활성화

#### 3.7.3 에러/취소 시나리오
- [ ] ERR-7.1: 단축키 설정 파일 손상 시 → 기본 단축키로 복원, `"Shortcut settings reset to defaults."` 토스트 표시.
- [ ] ERR-7.2: 커스터마이징에서 충돌 감지 → `"'{key}' is already assigned to '{action}'. Replace?"` 확인 다이얼로그. Cancel 시 변경 취소.

## 4. 범위

### 포함
- 7개 기능 전체 (대시보드, 스트리밍, 변환, 내보내기, 주석, 테마, 단축키)
- IPC 확장 (각 기능별 IPC 커맨드)
- 유닛/통합/E2E 테스트

### 제외
- SQL 쿼리 에디터 (향후)
- 플러그인 시스템 (향후)
- 웹 대시보드 퍼블리싱 (향후)
- 멀티 윈도우 (현재 단일 윈도우)
- 네트워크 데이터 소스 (REST API, WebSocket 등)

## 5. UI/UX 상세

### 5.1 대시보드 모드 UI
```
┌─────────────────────────────────────────────┐
│ [Dashboard Mode]  Layout: [2×2 ▼]  [⚙] [✕] │
├──────────────────┬──────────────────────────┤
│  Voltage (line)  │  Current (line)          │
│  ~~~~~~~~~~~~~~~│  ~~~~~~~~~~~~~~~~~~~~~~  │
│                  │                          │
├──────────────────┼──────────────────────────┤
│  Temperature     │  Power (scatter)         │
│  ~~~~~~~~~~~~~~~│  · · · · · ·            │
│                  │                          │
└──────────────────┴──────────────────────────┘
```
- 헤더바: 모드 라벨, 레이아웃 프리셋 드롭다운, 설정 기어, 닫기 버튼
- 각 셀: 프로파일 기반 미니 차트 + 헤더 (이름, 행수)
- 빈 셀: "+" 아이콘 + "Click to add chart" 텍스트
- **최소 셀 크기 240×180px**, 창 축소 시 스크롤바 표시

### 5.2 스트리밍 UI
```
상태바: [...] 🟢 Live (1.0s) | 500,234 rows | 245.3 MB
```
- 툴바에 ▶/⏸ 토글 버튼 (초기 상태: ⏹ Off)
- 설정: 폴링 간격 스피너 (0.5~60초)
- "Follow tail" 체크박스 (차트 오른쪽 하단)

### 5.3 컬럼 생성 다이얼로그
```
┌────────────────────────────────────────┐
│ Add Computed Column                    │
├────────────────────────────────────────┤
│ Name: [power_calc          ]           │
│                                        │
│ Type: ○ Formula  ○ Moving Avg          │
│       ○ Difference  ○ Cumsum           │
│       ○ Normalize                      │
│                                        │
│ Formula: [{voltage} * {current}    ]   │
│                                        │
│ Preview:                               │
│ ┌──────────────────────────────┐       │
│ │ 48.60, 47.78, 45.67, ...    │       │
│ └──────────────────────────────┘       │
│                                        │
│ [━━━━━━━━━━━░░░░] 67% (워커 실행 중)  │
│                                        │
│        [Cancel] [Create]               │
└────────────────────────────────────────┘
```
- 500ms 이상 소요 시 프로그레스 바 표시
- Cancel로 워커 스레드 중단 가능

### 5.4 주석 UI
- **모드 전환**: 툴바에 📌 "Annotate" 토글 버튼. 활성 시 주황색 강조 + 차트 우측 상단 "📌 Annotate" 뱃지
- **커서**: 탐색 모드 = 🖐️ grab, 주석 모드 = ✚ crosshair
- 차트 위 마커: 작은 원(●) + 호버 시 텍스트 팝업 (탐색/주석 모드 모두에서 표시)
- 구간 북마크: 반투명 색상 오버레이 + 상단 라벨 (주석 모드에서 드래그로 생성)
- 사이드 패널 (토글): 주석 리스트, 클릭 시 해당 위치로 이동
```
┌─────────────────────────────────────┐
│ [📌 Annotate]  (툴바 토글 버튼)      │
├─────────────────────────────────────┤
│                      📌 Annotate    │ ← 모드 뱃지 (활성 시)
│     ·                               │
│    / \    ● "Peak"                  │ ← 기존 주석 (호버/클릭 가능)
│   /   \       ✚ ← crosshair 커서   │
│  /     \___/                        │
│ ████████████ ← 구간 북마크 (드래그)  │
└─────────────────────────────────────┘
```

### 5.5 테마 토글
- 툴바: 🌙 (다크) / ☀️ (라이트) 아이콘 버튼
- 메뉴: View → Theme → Light / Dark / System

### 5.6 단축키 도움말 다이얼로그
```
┌──────────────────────────────────┐
│ Keyboard Shortcuts       [✕]     │
├──────────────────────────────────┤
│ File                             │
│   Cmd+O          Open file       │
│   Cmd+S          Save profile    │
│   Cmd+E          Export          │
│                                  │
│ View                             │
│   Cmd+Shift+D    Dashboard mode  │
│   Cmd+T          Toggle theme    │
│   Cmd+Shift+A    Annotate mode     │
│   Cmd+Shift+B    Annotations     │
│   F11            Fullscreen      │
│                                  │
│ Data                             │
│   Cmd+K          Computed column │
│   Cmd+Shift+L    Live streaming  │
│   Cmd+Z          Undo           │
│   Cmd+Shift+Z    Redo           │
│   Cmd+/          This dialog     │
└──────────────────────────────────┘
```

### 5.7 로딩/프로그레스 UI 정책
500ms 이상 소요되는 모든 작업에 로딩 표시를 적용한다:

| 작업 | 표시 위치 | 형태 |
|------|----------|------|
| 대시보드 초기 렌더링 | 각 셀 내부 | 스피너 (셀별 독립) |
| 컬럼 생성 | 다이얼로그 내 | 프로그레스 바 + Cancel |
| 내보내기 (PNG/SVG/PDF) | 모달 다이얼로그 | 프로그레스 바 + 단계 텍스트 + Cancel |
| 대용량 파일 리로드 | 상태바 | 프로그레스 바 + 파일명 |
| 대시보드 PDF 내보내기 | 모달 다이얼로그 | 프로그레스 바 + "Cell N/M" |

- 500ms 미만 작업에는 로딩 표시를 하지 않음 (깜빡임 방지)
- 로딩 시작 후 500ms 경과 시점에 로딩 UI를 표시 (즉시 표시하지 않음)

## 6. 데이터 구조

### 6.1 DashboardLayout
```python
@dataclass
class DashboardCell:
    row: int          # 격자 행 (0-based)
    col: int          # 격자 열 (0-based)
    row_span: int     # 세로 스팬 (기본 1)
    col_span: int     # 가로 스팬 (기본 1)
    profile_id: str   # 프로파일 ID (빈 셀이면 "")
    
@dataclass
class DashboardLayout:
    name: str
    rows: int         # 격자 행 수 (1~3)
    cols: int         # 격자 열 수 (1~3)
    cells: List[DashboardCell]
    sync_x: bool = False
    sync_y: bool = False
```

### 6.2 FileWatcher
```python
class FileWatcher(QObject):
    file_changed = Signal(str)       # file_path
    file_deleted = Signal(str)
    rows_appended = Signal(str, int) # file_path, new_row_count
    
    def __init__(self, poll_interval_ms: int = 1000): ...
    def watch(self, file_path: str, mode: str = "reload"): ...  # "reload" | "tail"
    def unwatch(self, file_path: str): ...
    def set_interval(self, ms: int): ...
    
    # M3: 무한 루프 방지
    _self_modifying: bool = False    # 자기 수정 플래그
    _debounce_timer: QTimer          # 300ms debounce
    _last_mtime: float               # 마지막 확인 mtime
    _last_size: int                  # 마지막 확인 파일 크기
    
    def begin_self_modify(self): ...  # _self_modifying = True
    def end_self_modify(self): ...    # _self_modifying = False (타이머로 300ms 후)
```

### 6.3 ComputedColumn
```python
@dataclass
class ComputedColumn:
    name: str
    kind: str          # "formula" | "moving_avg" | "difference" | "cumsum" | "normalize"
    expression: str    # Polars expression string or formula
    params: dict       # {"window": 10} for moving_avg, {"order": 1} for difference, etc.
    dataset_id: str
    depends_on: List[str] = field(default_factory=list)  # 참조하는 다른 생성 컬럼명 (DAG 추적)
```

### 6.4 Annotation
```python
@dataclass
class Annotation:
    id: str
    kind: str          # "point" | "range"
    x: float           # X 좌표 (point) 또는 x_start (range)
    x_end: float       # range 전용
    y: Optional[float] # point 전용
    text: str
    color: str         # hex
    icon: str          # emoji
    dataset_id: str
    profile_id: str    # 어떤 프로파일에 속하는지
```

### 6.5 ShortcutConfig
```python
@dataclass
class ShortcutEntry:
    action_id: str      # "file.open", "view.dashboard", etc.
    key_sequence: str    # "Ctrl+O", "Ctrl+D"
    description: str
    category: str        # "File", "View", "Data"
```

### 6.6 UndoAction
```python
from enum import Enum
from typing import Any

class UndoActionType(Enum):
    ANNOTATION_ADD = "annotation_add"
    ANNOTATION_DELETE = "annotation_delete"
    ANNOTATION_EDIT = "annotation_edit"
    COLUMN_ADD = "column_add"
    COLUMN_DELETE = "column_delete"
    COLUMN_EDIT = "column_edit"
    DASHBOARD_LAYOUT_CHANGE = "dashboard_layout_change"
    DASHBOARD_CELL_ASSIGN = "dashboard_cell_assign"
    DASHBOARD_CELL_REMOVE = "dashboard_cell_remove"

@dataclass
class UndoAction:
    action_type: UndoActionType
    timestamp: float               # time.time()
    description: str               # 사용자 표시용 (예: "Add annotation 'Peak voltage'")
    before_state: Any              # 변경 전 상태 스냅샷 (직렬화 가능)
    after_state: Any               # 변경 후 상태 스냅샷 (직렬화 가능)
    dataset_id: Optional[str]      # 관련 데이터셋
    profile_id: Optional[str]      # 관련 프로파일

@dataclass
class UndoStack:
    undo_stack: List[UndoAction] = field(default_factory=list)
    redo_stack: List[UndoAction] = field(default_factory=list)
    max_depth: int = 50            # 최대 50개 동작 기억
    
    def push(self, action: UndoAction): ...   # undo_stack에 추가, redo_stack 초기화
    def undo(self) -> Optional[UndoAction]: ...  # undo_stack에서 pop → redo_stack에 push
    def redo(self) -> Optional[UndoAction]: ...  # redo_stack에서 pop → undo_stack에 push
    def clear(self): ...                          # 파일/프로젝트 전환 시 전체 초기화
```

### 6.7 ColumnDependencyGraph
```python
class ColumnDependencyGraph:
    """생성 컬럼 간 의존성 DAG 관리"""
    _edges: Dict[str, Set[str]]  # column_name → {referenced_column_names}
    
    def add_column(self, name: str, depends_on: Set[str]) -> None: ...
    def remove_column(self, name: str) -> Set[str]: ...  # 반환: cascade 삭제 대상
    def has_cycle(self, name: str, depends_on: Set[str]) -> Optional[List[str]]: ...
        # 순환 경로 반환 (없으면 None). 토폴로지 정렬 기반.
    def topological_order(self) -> List[str]: ...  # 평가 순서 반환
    def dependents_of(self, name: str) -> Set[str]: ...  # name에 의존하는 컬럼들
```

## 7. Undo 시스템 설계

### 7.1 Undo 가능 동작 목록

| 동작 | Undo 가능 | Redo 가능 | 비고 |
|------|-----------|-----------|------|
| 주석 추가 | ✅ | ✅ | 주석 데이터 복원 |
| 주석 삭제 | ✅ | ✅ | 삭제된 주석 복원 |
| 주석 편집 | ✅ | ✅ | 이전 텍스트/색상 복원 |
| 생성 컬럼 추가 | ✅ | ✅ | 컬럼 정의 + 의존성 복원 |
| 생성 컬럼 삭제 | ✅ | ✅ | 컬럼 정의 + 데이터 복원 |
| 생성 컬럼 편집 | ✅ | ✅ | 이전 수식/파라미터 복원 |
| 대시보드 레이아웃 변경 | ✅ | ✅ | 이전 레이아웃 스냅샷 복원 |
| 대시보드 셀 프로파일 할당/해제 | ✅ | ✅ | 이전 셀 상태 복원 |
| **테마 전환** | ❌ | ❌ | 설정 변경, Undo 대상 아님 |
| **단축키 변경** | ❌ | ❌ | 설정 변경, Undo 대상 아님 |
| **파일 열기/닫기** | ❌ | ❌ | Undo 스택 초기화 트리거 |
| **프로파일 저장** | ❌ | ❌ | 영속화, Undo 대상 아님 |
| **내보내기** | ❌ | ❌ | 외부 파일 생성, Undo 대상 아님 |
| **스트리밍 ON/OFF** | ❌ | ❌ | 모드 전환, Undo 대상 아님 |

### 7.2 Undo 스택 정책
- **스택 깊이**: 최대 **50개** 동작. 초과 시 가장 오래된 동작부터 제거 (FIFO).
- **스택 초기화 시점**: 파일 열기, 파일 닫기, 프로젝트 전환 시 Undo/Redo 스택 전체 초기화.
- **Redo 스택 초기화**: 새로운 동작 수행 시 Redo 스택 전체 초기화 (standard behavior).
- **복합 동작**: 생성 컬럼 삭제 시 cascade 삭제가 발생하면, 모든 삭제를 하나의 UndoAction으로 묶어 한 번의 Undo로 전체 복원.
- **메모리 관리**: UndoAction의 `before_state`/`after_state`는 경량 스냅샷 (데이터 전체 복사 금지). 주석은 Annotation 객체 사본, 컬럼은 ComputedColumn 정의 사본(데이터 제외 — 레이지 재평가), 대시보드는 DashboardLayout 사본.

### 7.3 Undo/Redo UI
- **Cmd+Z**: Undo 실행. 상태바에 `"Undo: {description}"` 토스트 표시 (2초 후 소멸).
- **Cmd+Shift+Z**: Redo 실행. 상태바에 `"Redo: {description}"` 토스트 표시.
- Undo/Redo 스택이 비어있을 때 단축키 입력 → 아무 동작 없음 (경고 없음).
- Edit 메뉴에 "Undo {description}" / "Redo {description}" 항목 (스택 top의 description 표시).

## 8. 기능 간 상호작용 매트릭스

7개 기능이 동시에 활성화될 수 있는 주요 조합별 동작을 정의한다.

### 8.1 상호작용 매트릭스

| 조합 | 동작 정의 |
|------|-----------|
| **대시보드 + 스트리밍** | ✅ 공존 가능. 스트리밍 업데이트 시 활성 셀의 차트만 업데이트. 비활성(최소화/숨김) 셀은 포커스 획득 시 갱신. 9셀 동시 업데이트는 순차적으로 처리 (셀 인덱스 순, 각 셀 <50ms). |
| **대시보드 + 주석** | ✅ 공존 가능. 주석 추가/편집은 **현재 포커스된 셀**의 차트에만 적용. 셀 포커스 표시: 파란색 테두리 2px. 주석 패널은 전체 주석 리스트를 표시하되, 현재 셀 주석을 상단에 강조. |
| **대시보드 + 컬럼 생성** | ✅ 공존 가능. 컬럼 생성 다이얼로그에서 대상 데이터셋을 명시적으로 선택해야 함 (드롭다운). 생성 완료 후, 해당 데이터셋을 사용하는 모든 셀의 Y축 목록 갱신. |
| **대시보드 + 내보내기** | ✅ 공존 가능. "Export Dashboard" 시 모든 셀을 하나의 PDF/PNG로 렌더링. 개별 셀 우클릭 → "Export this cell" 가능. |
| **스트리밍 + 컬럼 생성** | ✅ 공존 가능. 스트리밍으로 새 행 추가 시, 생성 컬럼을 **자동 재평가**한다. 단, rolling/cumsum 등은 새 행에 대해서만 증분 계산 (전체 재계산 아님). formula 타입은 새 행에 대해서만 평가. |
| **스트리밍 + 주석** | ✅ 공존 가능. 기존 주석은 데이터 좌표 기준이므로 새 행 추가에 영향 없음. "Follow tail" 활성화 시 주석이 화면 밖으로 스크롤될 수 있으나, 주석 패널 클릭으로 복귀 가능. |
| **스트리밍 + 내보내기** | ⚠️ 조건부. 내보내기 실행 시 **스트리밍을 일시 정지**하고, 현재 스냅샷으로 내보내기 수행. 완료 후 자동 재개. 사용자에게 `"Streaming paused during export"` 토스트 표시. |
| **주석 + 컬럼 생성** | ✅ 독립적. 주석은 원본 데이터 좌표에 앵커, 생성 컬럼은 새 데이터 시리즈. 상호 영향 없음. |
| **프로파일 비교 모드 + 대시보드** | ❌ 배타적. 대시보드 활성화 시 프로파일 비교 모드 자동 해제. 비교 모드 진입 시 대시보드 자동 해제. 전환 시 `"Exiting {current_mode} to enter {new_mode}"` 토스트 표시. |
| **테마 + 모든 기능** | ✅ 독립적. 테마 전환은 모든 활성 기능의 시각적 스타일만 업데이트. 데이터/상태 변경 없음. |
| **단축키 + 모든 기능** | ✅ 독립적. 현재 활성 모드에 따라 단축키 컨텍스트 자동 전환. 대시보드 모드일 때 `Cmd+1~9` 활성화, 일반 모드일 때 비활성화. |

### 8.2 동시 활성화 제약

- **최대 동시 활성화**: 대시보드 + 스트리밍 + 주석 + 테마 + 단축키 (5개)
- **배타적 모드**: 대시보드 ↔ 프로파일 비교 모드
- **일시 정지 조합**: 스트리밍 + 내보내기 (내보내기 동안 스트리밍 일시 정지)

## 9. 모듈 배치 및 아키텍처

### 9.1 파일 구조 (신규 모듈)

```
core/
├── state.py                        # AppState 확장 (아래 9.3 참조)
├── data_engine.py                  # DataEngine 확장 (ComputedColumn 평가)
├── dashboard_controller.py         # [NEW] DashboardController
├── streaming_controller.py         # [NEW] StreamingController
├── export_controller.py            # [NEW] ExportController
├── annotation_controller.py        # [NEW] AnnotationController
├── shortcut_controller.py          # [NEW] ShortcutController
├── undo_manager.py                 # [NEW] UndoManager (UndoStack 관리)
├── column_dependency_graph.py      # [NEW] ColumnDependencyGraph (DAG)
├── formula_parser.py               # [NEW] FormulaParser (수식 → Polars Expr 변환)
├── file_watcher.py                 # [NEW] FileWatcher (QObject, 폴링 기반)
├── io_abstract.py                  # [NEW] I/O 추상화 인터페이스 (DI용)
│
ui/
├── panels/
│   ├── dashboard_panel.py          # [NEW] DashboardPanel (격자 레이아웃)
│   ├── annotation_panel.py         # [NEW] AnnotationPanel (주석 목록)
│   └── mini_graph_widget.py        # [NEW] MiniGraphWidget (대시보드 셀 차트)
├── dialogs/
│   ├── computed_column_dialog.py   # [NEW] ComputedColumnDialog
│   ├── export_dialog.py            # [NEW] ExportDialog
│   ├── shortcut_help_dialog.py     # [NEW] ShortcutHelpDialog
│   └── shortcut_edit_dialog.py     # [NEW] ShortcutEditDialog
├── theme.py                        # 기존 확장 (토글 로직)
└── main_window.py                  # 기존 확장 (컨트롤러 연결만, 로직 위임)
```

### 9.2 컨트롤러 계층

기존 패턴(`ProfileController`, `ProfileComparisonController`)을 따라 각 기능별 컨트롤러를 `core/`에 배치한다. 컨트롤러는 비즈니스 로직을 담당하고, UI 패널/다이얼로그는 표시만 담당한다.

```
MainWindow
├── ProfileController (기존)
├── ProfileComparisonController (기존)
├── DashboardController (NEW)
│   ├── DashboardLayout 관리
│   ├── DashboardPanel ↔ 데이터 바인딩
│   └── 셀 프로파일 할당/해제
├── StreamingController (NEW)
│   ├── FileWatcher 생성/관리
│   ├── 폴링 간격 설정
│   └── DataEngine과 데이터 동기화
├── ExportController (NEW)
│   ├── 워커 스레드 관리
│   ├── 내보내기 형식별 렌더링 위임
│   └── 프로그레스 Signal 발행
├── AnnotationController (NEW)
│   ├── Annotation CRUD
│   ├── 프로파일 연동 (저장/복원)
│   └── 좌표 변환 관리
├── ShortcutController (NEW)
│   ├── QShortcut 등록/해제
│   ├── 충돌 감지
│   └── 설정 영속화
└── UndoManager (NEW)
    ├── UndoStack 관리
    ├── 각 컨트롤러에서 push 호출
    └── Undo/Redo 실행 시 해당 컨트롤러에 복원 위임
```

### 9.3 상태 관리 전략

**기존 AppState 확장** 방식을 채택한다. 각 기능의 상태를 별도 dataclass로 정의하고, AppState에 속성으로 추가한다.

```python
# core/state.py 확장

@dataclass
class DashboardState:
    active: bool = False
    layout: Optional[DashboardLayout] = None
    focused_cell: Optional[int] = None  # 포커스된 셀 인덱스

@dataclass
class StreamingState:
    active: bool = False
    mode: str = "off"          # "off" | "live" | "paused"
    poll_interval_ms: int = 1000
    follow_tail: bool = False

@dataclass
class AnnotationState:
    panel_visible: bool = False
    annotations: Dict[str, List[Annotation]] = field(default_factory=dict)  # profile_id → annotations

@dataclass  
class ThemeState:
    current: str = "system"    # "light" | "dark" | "system"

class AppState:
    # ... 기존 속성 ...
    dashboard: DashboardState = field(default_factory=DashboardState)
    streaming: StreamingState = field(default_factory=StreamingState)
    annotations: AnnotationState = field(default_factory=AnnotationState)
    theme: ThemeState = field(default_factory=ThemeState)
```

**상태 변경 흐름**: 
1. UI 이벤트 또는 IPC 커맨드 → 해당 컨트롤러 메서드 호출
2. 컨트롤러가 AppState 업데이트 + UndoManager.push() (해당 시)
3. 컨트롤러가 Signal 발행 → UI 갱신

### 9.4 의존성 주입(DI) 포인트

테스트 용이성을 위해 외부 I/O에 대한 추상화 레이어를 도입한다:

```python
# core/io_abstract.py

from abc import ABC, abstractmethod

class IFileSystem(ABC):
    """파일 시스템 추상화 — FileWatcher, DataEngine에서 사용"""
    @abstractmethod
    def read_file(self, path: str) -> bytes: ...
    @abstractmethod
    def write_file(self, path: str, data: bytes) -> None: ...
    @abstractmethod
    def stat(self, path: str) -> os.stat_result: ...
    @abstractmethod
    def exists(self, path: str) -> bool: ...

class ITimerFactory(ABC):
    """타이머 추상화 — FileWatcher, 테스트에서 Mock 가능"""
    @abstractmethod
    def create_timer(self, interval_ms: int, callback: Callable) -> Any: ...

class RealFileSystem(IFileSystem):
    """실제 파일 시스템 구현"""
    ...

class MockFileSystem(IFileSystem):
    """테스트용 Mock 파일 시스템"""
    ...
```

**DI 적용 대상:**
- `FileWatcher(fs: IFileSystem, timer_factory: ITimerFactory)` — 파일 I/O와 타이머를 주입
- `DataEngine(fs: IFileSystem)` — 파일 읽기/쓰기를 주입
- `ExportController(fs: IFileSystem)` — 내보내기 파일 쓰기를 주입

## 10. 안정성 및 안전 정책

### 10.1 Signal/Slot 해제 정책

모든 Signal/Slot 연결은 다음 규칙을 따른다:

| 상황 | 해제 정책 |
|------|-----------|
| 대시보드 모드 종료 | `DashboardPanel.cleanup()` 호출 → 모든 MiniGraphWidget의 Signal 해제 → `deleteLater()` |
| 스트리밍 OFF | `StreamingController.stop()` → FileWatcher의 모든 Signal disconnect → FileWatcher `deleteLater()` |
| 파일 닫기 | 해당 파일의 모든 컨트롤러에 `on_file_closed(path)` 전파 → 관련 Signal 해제 |
| 앱 종료 | `MainWindow.closeEvent()` → 모든 컨트롤러의 `shutdown()` 순차 호출 |

**위젯 수명주기 관리:**
- 대시보드 셀 위젯: 모드 종료 시 `deleteLater()` 호출. 모드 재진입 시 새로 생성.
- 주석 마커 위젯: `hide()` + 리스트에서 제거 후 `deleteLater()`.
- **규칙**: 위젯 삭제 시 반드시 `deleteLater()` 사용 (즉시 `del` 금지). 삭제 전 모든 Signal disconnect.

### 10.2 FileWatcher 안전 정책

FR-2.8에서 정의한 무한 루프 방지 외 추가 정책:

- **최대 감시 파일 수**: 10개. 초과 시 가장 오래 감시한 파일부터 해제.
- **감시 대상 파일 크기 제한**: 2GB 초과 파일은 tail 모드만 지원, reload 모드 차단.
- **에러 시 백오프**: 파일 읽기 실패 시 폴링 간격을 2배로 증가 (최대 30초). 성공 시 원래 간격 복원.

### 10.3 원자적 저장 (Atomic Write)

데이터 손실 방지를 위해 모든 파일 저장에 **temp → rename** 패턴을 적용한다:

```python
def atomic_write(path: str, data: bytes) -> None:
    """원자적 파일 저장"""
    tmp_path = path + ".tmp"
    try:
        with open(tmp_path, 'wb') as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.rename(tmp_path, path)  # POSIX에서 원자적
    except Exception:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
```

**적용 대상:**
- 대시보드 레이아웃 JSON 저장
- 프로파일 저장 (주석 + 생성 컬럼 포함)
- 단축키 설정 파일 저장
- 테마 설정 저장
- 내보내기(CSV/Parquet/Excel) — 임시 파일 → 최종 경로 rename

### 10.4 IPC + UI 동시 접근 안전 정책

IPC 서버(TCP:52849)는 별도 스레드에서 실행되므로, UI 상태 변경은 반드시 **메인 스레드로 마샬링**한다:

```python
# IPC 핸들러에서 UI 조작 시
class IPCHandler:
    def handle_set_theme(self, theme: str):
        # 직접 호출 금지: self.theme_controller.set_theme(theme)
        # 메인 스레드로 마샬링:
        QMetaObject.invokeMethod(
            self.theme_controller, "set_theme",
            Qt.QueuedConnection,
            Q_ARG(str, theme)
        )
```

**규칙:**
- 모든 IPC 커맨드 핸들러에서 UI 관련 상태 변경은 `QMetaObject.invokeMethod(..., Qt.QueuedConnection)` 사용.
- IPC에서 읽기 전용 쿼리(`get_theme`, `get_status`)는 직접 반환 가능 (AppState는 읽기 스레드 안전).
- 동시 IPC 커맨드: 큐에 순차 처리, 동시 실행 금지.

### 10.5 워커 스레드 정책

500ms 이상 소요되는 작업은 워커 스레드에서 실행한다:

| 작업 | 스레드 | 취소 지원 | 결과 전달 |
|------|--------|-----------|-----------|
| 컬럼 생성 (100만 행) | QThread | ✅ `_cancelled` 플래그 | `Signal(pl.Series)` |
| 내보내기 (PNG/SVG/PDF) | QThread | ✅ | `Signal(str)` (파일 경로) |
| 대시보드 PDF 내보내기 | QThread | ✅ | `Signal(str)` |
| 대용량 파일 리로드 | QThread | ❌ | `Signal(pl.DataFrame)` |

**워커 스레드 규칙:**
- 워커에서 UI 직접 조작 금지 — Signal로만 메인 스레드에 전달.
- 워커 완료/취소 후 `deleteLater()` 호출.
- 동일 종류의 워커는 동시에 1개만 실행. 중복 요청 시 이전 워커 취소 후 새 워커 시작.

### 10.6 타이머/스레드 정리 순서

리소스 해제 시 다음 순서를 엄격히 준수한다:

**앱 종료 (`closeEvent`) 순서:**
1. 스트리밍 중단: `StreamingController.shutdown()` → FileWatcher 타이머 중단, Signal 해제
2. 워커 스레드 중단: 모든 활성 워커에 cancel 요청 → `wait(3000ms)` → 강제 `terminate()`
3. Undo 스택 초기화: `UndoManager.clear()`
4. 대시보드 정리: `DashboardController.shutdown()` → 셀 위젯 `deleteLater()`
5. 설정 저장: 테마, 단축키, 창 크기 → QSettings
6. IPC 서버 종료: 소켓 닫기

**파일 닫기 순서:**
1. 해당 파일의 스트리밍 중단
2. 해당 파일의 생성 컬럼 캐시 해제
3. 해당 파일의 주석 메모리 해제
4. Undo 스택 초기화

**대시보드 모드 종료 순서:**
1. 모든 셀의 차트 Signal disconnect
2. 셀 위젯 `deleteLater()`
3. DashboardState 초기화

## 11. 성능 & 메모리 요구사항

| 시나리오 | 목표 응답 시간 | 메모리 |
|----------|--------------|--------|
| 대시보드 9셀 렌더링 (50만 행, LTTB 다운샘플링 적용) | <1초 | 기존 대비 +200MB 이하 |
| Tail 추가 1000행 (100만 행 기존) | <200ms | 추가 복사 없음 |
| 컬럼 생성 (100만 행) | <500ms (워커 스레드) | 원본 대비 +1컬럼 메모리 |
| PNG 내보내기 (1920×1080) | <1초 | 임시 버퍼만 |
| 테마 전환 | <100ms | 추가 메모리 없음 |
| 주석 1000개 렌더링 | <50ms | <100KB |

## 12. 테스트 시나리오

### Unit Tests (45개)

**Dashboard (8개)**
- [ ] UT-1.1: DashboardLayout 생성/직렬화/역직렬화
- [ ] UT-1.2: DashboardLayout 셀 스팬 유효성 검증 (겹침 방지)
- [ ] UT-1.3: DashboardLayout 셀 추가/제거
- [ ] UT-1.4: DashboardLayout 셀 리사이즈 (스팬 변경)
- [ ] UT-1.5: DashboardLayout 최소 셀 크기 검증 (240×180 하한)
- [ ] UT-1.6: DashboardLayout JSON 스키마 검증 실패 → 기본 레이아웃 폴백
- [ ] UT-1.7: 축 동기화 (sync_x=True → 모든 셀 X축 범위 일치)
- [ ] UT-1.8: 빈 데이터셋에서 대시보드 활성화 차단

**FileWatcher (7개)**
- [ ] UT-2.1: FileWatcher 폴링 간격 설정
- [ ] UT-2.2: FileWatcher tail 모드에서 새 행 감지
- [ ] UT-2.3: FileWatcher reload 모드에서 파일 변경 감지
- [ ] UT-2.4: FileWatcher self-change 무시 (무한 루프 방지)
- [ ] UT-2.5: FileWatcher debounce 동작 (300ms 내 중복 이벤트 병합)
- [ ] UT-2.6: FileWatcher 파일 삭제 감지 → file_deleted Signal
- [ ] UT-2.7: FileWatcher 폴링 간격 경계값 (0.5초 미만, 60초 초과 → 클램핑)

**ComputedColumn (11개)**
- [ ] UT-3.1: ComputedColumn 수식 파싱 (정상)
- [ ] UT-3.2: ComputedColumn 수식 파싱 (오류: 존재하지 않는 컬럼)
- [ ] UT-3.3: 이동평균 계산 정확성
- [ ] UT-3.4: 정규화 (min-max, z-score) 정확성
- [ ] UT-3.5: 순환 참조 감지 (A→B→A → 에러)
- [ ] UT-3.6: DAG 토폴로지 정렬 순서 검증
- [ ] UT-3.7: 화이트리스트 허용 함수 → 성공
- [ ] UT-3.8: 화이트리스트 비허용 함수 → 차단 에러
- [ ] UT-3.9: 0으로 나누기 → null 처리
- [ ] UT-3.10: 타입 불일치 에러 (문자열 컬럼 + 수학 연산)
- [ ] UT-3.11: 이동평균 경계값 (window=0, window=행수+1)

**Export (5개)**
- [ ] UT-4.1: PNG 내보내기 파일 생성
- [ ] UT-4.2: SVG 내보내기 파일 생성
- [ ] UT-4.3: PDF 내보내기 파일 생성
- [ ] UT-4.4: 내보내기 원자적 저장 (temp → rename)
- [ ] UT-4.5: 내보내기 취소 시 부분 파일 삭제

**Annotation (5개)**
- [ ] UT-5.1: Annotation 생성/직렬화
- [ ] UT-5.2: Annotation 좌표 변환 (줌/팬 시)
- [ ] UT-5.3: Annotation 편집/삭제
- [ ] UT-5.4: Annotation 텍스트 200자 초과 → 차단
- [ ] UT-5.5: Orphaned annotation 감지 (데이터셋 삭제 후)

**Theme (3개)**
- [ ] UT-6.1: 테마 전환 (light→dark→system)
- [ ] UT-6.2: 테마 설정 영속화
- [ ] UT-6.3: 테마 설정 파일 손상 → 기본 테마 폴백

**Shortcuts (4개)**
- [ ] UT-7.1: ShortcutConfig 로드/저장
- [ ] UT-7.2: 단축키 충돌 감지
- [ ] UT-7.3: 단축키 커스터마이징 (키 변경)
- [ ] UT-7.4: macOS 시스템 단축키 충돌 경고

**Undo (4개)**
- [ ] UT-8.1: UndoStack push/undo/redo 기본 동작
- [ ] UT-8.2: UndoStack 최대 깊이(50) 초과 → 가장 오래된 항목 제거
- [ ] UT-8.3: 새 동작 push → Redo 스택 초기화
- [ ] UT-8.4: 복합 동작 (cascade 삭제) → 하나의 Undo로 전체 복원

### Integration Tests (7개)
- [ ] IT-1.1: 대시보드 모드 전환 → 9셀 렌더링 → 복귀
- [ ] IT-2.1: 파일 변경 → 자동 리로드 → 차트 업데이트
- [ ] IT-3.1: 컬럼 생성 → Y축에 표시 → 프로파일 저장/복원
- [ ] IT-4.1: 차트 내보내기 → 파일 검증
- [ ] IT-5.1: 주석 추가 → 줌/팬 → 주석 위치 유지
- [ ] IT-6.1: 테마 전환 → 차트 색상 변경 → 앱 재시작 → 테마 유지
- [ ] IT-7.1: 단축키 → 해당 동작 실행

### E2E Tests (7개)
- [ ] E2E-1: 사용자가 sensor_data.csv를 열고 → 4개 프로파일 생성 → 2×2 대시보드 구성 → PDF 내보내기
- [ ] E2E-2: 사용자가 파일 열고 → 실시간 스트리밍 ON → 외부에서 행 추가 → 차트 자동 업데이트 확인
- [ ] E2E-3: 사용자가 이동평균 컬럼 생성 → 원본과 오버레이 비교 → 주석 추가 → 프로파일 저장
- [ ] E2E-4: **대시보드 + 스트리밍 동시 사용** — 2×2 대시보드 활성화 → 스트리밍 ON → 외부 행 추가 → 4개 셀 모두 업데이트 확인
- [ ] E2E-5: **Undo/Redo 전체 흐름** — 주석 추가 → 컬럼 생성 → Undo 2회 (컬럼 제거 → 주석 제거) → Redo 1회 (주석 복원) → 상태 일관성 검증
- [ ] E2E-6: **내보내기 + 테마 조합** — 다크 테마 전환 → 차트 PNG 내보내기 → 내보낸 이미지 배경색이 다크인지 검증 → 라이트 전환 → 재내보내기 → 배경색 변경 확인
- [ ] E2E-7: **컬럼 의존 체인** — 생성 컬럼 A 생성 → A를 참조하는 컬럼 B 생성 → A 삭제 시 B cascade 경고 → 확인 → 둘 다 삭제 확인 → Undo → 둘 다 복원 확인

### Performance Tests
- [ ] PT-1: 50만 행 × 9셀 대시보드 렌더링 <1초 (LTTB 다운샘플링 적용)
- [ ] PT-2: 100만 행 tail 추가(1000행) 후 차트 업데이트 <200ms
- [ ] PT-3: 100만 행 이동평균(window=100) 컬럼 생성 <500ms

## 13. 성공 기준
- [ ] 7개 기능 전체 구현 완료
- [ ] 단위 테스트 커버리지 80% 이상 (최소 45개 단위 테스트)
- [ ] E2E 테스트 7개 전체 통과
- [ ] 성능 테스트 3개 전체 통과
- [ ] 기존 183개 프로파일 비교 테스트 + 132개 회귀 테스트 깨지지 않음

## 14. 미해결 질문
- Q1: ~~대시보드 셀에 차트 외의 위젯(통계 카드, 테이블 등)도 넣을 수 있게 할지?~~ → v2에서는 차트만. 향후 확장.
- Q2: ~~스트리밍에서 Parquet 파일도 tail 모드를 지원할지?~~ → CSV만 tail 지원. Parquet는 전체 리로드.
- Q3: ~~컬럼 생성 수식에서 다른 생성 컬럼을 참조할 수 있게 할지?~~ → Yes, 의존성 순서대로 평가. **DAG 검증 + 토폴로지 정렬로 순환 참조 방지 (FR-3.10, 섹션 6.7).**

## 15. 구현 순서 (의존성 기반)

```
Phase A (독립, 병렬 가능):
  ├── Feature 6: 테마 토글 (가장 단순, 기존 코드 활용)
  ├── Feature 7: 키보드 단축키 (독립적)
  ├── Feature 5: 북마크/주석 (차트 레이어 추가)
  └── 공통: UndoManager, I/O 추상화, 원자적 저장 유틸리티

Phase B (Phase A 이후):
  ├── Feature 3: 컬럼 생성 (DataEngine 확장 + FormulaParser + DAG)
  └── Feature 2: 실시간 스트리밍 (FileWatcher + DataEngine)

Phase C (Phase A+B 이후):
  ├── Feature 1: 대시보드 (MiniGraphWidget 재사용 + LTTB 다운샘플링)
  └── Feature 4: 내보내기 (차트 렌더링 + PDF + 프로그레스)
```
