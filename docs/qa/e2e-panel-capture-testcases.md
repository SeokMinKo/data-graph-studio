# DGS 패널 캡처 기반 E2E 기능 평가 TC

목적: DGS의 `panel capture` 기능(`dgs_capture`)을 이용해, 기능별 UI 렌더링/상태 반영을 E2E로 검증한다.

---

## 0) 공통 실행 규칙

- 실행 방식
  - 실행 중 앱 연결: `python -m data_graph_studio.tools.dgs_capture --connect ...`
  - 헤드리스 실행: `python -m data_graph_studio.tools.dgs_capture --headless ...`
- 기본 출력 경로: `docs/qa/e2e-panel-captures/<tc-id>/`
- 캡처 대상 권장: `graph_panel`, `table_panel`, `summary_panel`, `window`
- 증적 필수:
  1. IPC/CLI 응답 로그
  2. 패널 캡처 이미지
  3. Pass/Fail 판정 근거(화면 관찰 포인트)

---

## 1) 테스트 데이터셋

- `01_sales_simple.csv` (기본 집계/카테고리)
- `02_stock_ohlc.csv` (시계열/가격)
- `03_sensors_timeseries.csv` (타임시리즈)
- `04_wide_table.csv` (컬럼 많은 테이블)
- `05_null_heavy.csv` (결측치 다수)

---

## 2) 기능별 E2E TC

## TC-PANEL-001: 기본 로드 후 주요 패널 렌더링
- 목적: 파일 로드 직후 핵심 패널이 정상 렌더링되는지 확인
- 사전조건: 앱 실행 가능, 데이터 파일 접근 가능
- 절차:
  1. 데이터 로드
  2. `graph_panel`, `table_panel`, `summary_panel` 캡처
- 기대결과:
  - graph_panel: 빈 화면이 아닌 데이터 플롯/축 노출
  - table_panel: 헤더 + 최소 1행 데이터 노출
  - summary_panel: row/column 등 요약 정보 노출
- 캡처 명령 예시:
  - `python -m data_graph_studio.tools.dgs_capture --connect --target graph_panel --output-dir docs/qa/e2e-panel-captures/TC-PANEL-001`

## TC-PANEL-002: 차트 타입 변경 반영
- 목적: 차트 타입 전환(예: line → bar → scatter)이 그래프에 반영되는지 검증
- 절차:
  1. 동일 데이터셋 로드
  2. 차트 타입 A/B/C 순으로 변경
  3. 각 단계마다 graph_panel 캡처
- 기대결과:
  - 각 이미지에서 시각 요소(선/막대/산점) 형태가 명확히 달라야 함
  - 크래시/빈 플롯 없음

## TC-PANEL-003: 필터 적용 전/후 상태 비교
- 목적: 필터링이 그래프/테이블에 일관되게 반영되는지 검증
- 절차:
  1. 필터 미적용 상태 캡처 (graph/table)
  2. 필터 1개 적용 후 캡처
  3. 필터 해제 후 재캡처
- 기대결과:
  - 적용 시 데이터 포인트/행 수 감소가 화면에서 확인 가능
  - 해제 시 원복됨

## TC-PANEL-004: 패널별 캡처 타겟 정확성
- 목적: target 지정(`graph_panel`, `table_panel`, `summary_panel`, `window`)이 정확히 동작하는지 확인
- 절차:
  1. 각 target으로 캡처 수행
  2. 파일명/이미지 내용을 target과 대조
- 기대결과:
  - 잘못된 패널이 저장되지 않아야 함
  - `window`는 전체 창, `panel`은 해당 영역만 포함

## TC-PANEL-005: 데이터셋 전환 시 활성 상태 반영
- 목적: 다중 데이터셋에서 활성 데이터셋 변경이 UI에 반영되는지 검증
- 절차:
  1. 데이터셋 2개 이상 로드
  2. 활성 데이터셋 변경 전/후 캡처
- 기대결과:
  - graph/table 표시 내용이 데이터셋에 맞게 바뀜
  - 요약 패널 수치도 함께 변경

## TC-PANEL-006: 대용량/와이드 테이블 렌더링 안정성
- 목적: 컬럼이 많은 데이터에서 table_panel 표시 안정성 검증
- 절차:
  1. wide_table 로드
  2. table_panel 캡처
- 기대결과:
  - 헤더 깨짐/중첩/완전 공백 현상 없음
  - 스크롤 가능한 상태 유지

## TC-PANEL-007: 결측치 데이터 렌더링 안정성
- 목적: 결측치 많은 데이터에서 그래프/테이블 오류 없이 렌더링되는지 확인
- 절차:
  1. null_heavy 데이터 로드
  2. graph/table/summary 캡처
- 기대결과:
  - 예외 팝업/크래시 없이 표시
  - 테이블에서 결측치 표시 규칙 일관

## TC-PANEL-008: 비교 모드(가능 시) 화면 검증
- 목적: 비교 관련 화면(overlay/side-by-side/stat panel)이 정상 노출되는지 확인
- 절차:
  1. 비교 모드 진입
  2. 관련 패널 캡처
- 기대결과:
  - 비교 대상 구분(색/레이블/패널 분리) 명확
  - 통계/차이 요약이 비정상 빈값으로만 표시되지 않음

## TC-PANEL-009: 캡처 파일 저장 규칙 검증
- 목적: 캡처 산출물 규칙(파일명, 포맷, 출력경로)이 일관적인지 확인
- 절차:
  1. `--format png` 고정으로 캡처 반복
  2. output-dir 별 파일 생성 확인
- 기대결과:
  - 파일 생성 누락 없음
  - 타임스탬프/패널명 기반 파일명 규칙 유지

## TC-PANEL-010: 회귀 스모크
- 목적: 릴리즈 전 최소 기능 회귀 확인
- 절차:
  1. TC-001,002,003,004 핵심만 1회 실행
- 기대결과:
  - 주요 플로우 4개 모두 PASS

---

## 3) 판정 템플릿 (각 TC 공통)

- TC ID:
- 결과: PASS / FAIL
- 실행 명령:
- 산출 이미지:
- 관찰 포인트:
- 실패 시 증상:
- 추정 원인:
- 후속 액션:

---

## 4) 운영 권장

- PR마다 최소 `TC-010` 수행
- UI/차트 로직 변경 PR은 `TC-001~004` + 영향받는 케이스 추가 수행
- 주 1회 야간 배치로 `TC-001~009` 전체 수행 후 리포트 아카이브
