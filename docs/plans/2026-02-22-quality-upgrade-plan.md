# DGS 품질 업그레이드 구현 플랜

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Data Graph Studio 코드 품질, 테스트, 성능, 안정성, UI/UX 전방위 개선

**Architecture:** 병렬 리뷰 에이전트 5개 → 우선순위 합산 → Ralph Loop 반복 구현

**Tech Stack:** Python 3.9+, PySide6, Polars, PyQtGraph, pytest

---

## Phase 1: 병렬 리뷰 (모든 에이전트 동시 dispatch)

**중요:** Task 1~5는 동시에 실행한다. 각 에이전트는 코드를 수정하지 않고 리포트만 작성한다.

---

### Task 1: Architecture 리뷰 에이전트

**산출물:** `docs/plans/review-architecture.md`

**분석 대상:**
- `data_graph_studio/core/state.py` — AppState god object (1640줄)
- `data_graph_studio/ui/main_window.py` — MainWindow (2023줄)
- `data_graph_studio/ui/panels/graph_panel.py` — GraphPanel (2381줄)
- `data_graph_studio/ui/panels/table_panel.py` — TablePanel (2892줄)
- `PRD-refactor-god-objects.md` — 이행 상태 확인

**검토 항목:**
1. **God Objects**: 2000줄+ 파일의 단일책임원칙(SRP) 위반 현황
2. **순환 의존성**: core ↔ ui 간 양방향 import 여부
3. **결합도 점수**: 각 모듈의 직접 의존 수
4. **PRD-refactor-god-objects.md 이행률**: 이미 분리된 항목 vs 미이행 항목
5. **Signal/Slot 남용**: 과도한 시그널 체인, 디버깅 어려운 패턴
6. **전역 상태 노출**: AppState의 필드가 직접 외부에서 변경되는 패턴

**리포트 형식:**
```markdown
# Architecture Review

## Critical Issues
- [파일:라인] 문제 설명

## High Issues
- ...

## Medium / Low Issues
- ...

## PRD-refactor-god-objects 이행 상태
- 완료: ...
- 미이행: ...

## 권장 리팩터링 순서
1. ...
```

**명령:**
```bash
cd /Users/lov2fn/Projects/data-graph-studio
wc -l data_graph_studio/core/state.py data_graph_studio/ui/main_window.py data_graph_studio/ui/panels/*.py
python -c "import ast, os; ..."  # import graph 분석
```

---

### Task 2: 테스트 품질 리뷰 에이전트

**산출물:** `docs/plans/review-tests.md`

**분석 대상:**
- `tests/` 전체 (40+ 파일)
- `data_graph_studio/core/` 전체

**검토 항목:**
1. **커버리지 갭**: 테스트가 없거나 약한 모듈 식별
2. **테스트 품질**: assert 하나짜리, 너무 광범위한 통합 테스트, mock 남용
3. **누락된 edge case 카테고리:**
   - 빈 데이터프레임 (0행, 0컬럼)
   - NaN/Inf/None 값 포함 데이터
   - 10M+ 행 성능 경계
   - 동시 파일 로딩
   - 잘못된 파일 형식
4. **테스트 격리**: 전역 상태 오염 여부
5. **느린 테스트**: 5초+ 걸리는 테스트, 최적화 가능한 것
6. **중복 테스트**: 같은 동작을 여러 파일에서 테스트하는 것

**명령:**
```bash
cd /Users/lov2fn/Projects/data-graph-studio
pytest --co -q 2>/dev/null | wc -l
pytest --cov=data_graph_studio --cov-report=term-missing -q 2>/dev/null | tail -50
```

**리포트 형식:**
```markdown
# Test Quality Review

## Coverage Gaps (커버리지 0% 또는 <50%)
- `module.py`: 커버리지 X%, 누락 케이스

## Missing Edge Cases
- DataEngine: 빈 데이터프레임 처리 테스트 없음
- ...

## Poor Quality Tests
- `tests/test_X.py:line` — 이유

## Slow Tests
- `tests/test_X.py::test_name` — Xs

## Recommended New Tests (우선순위순)
1. ...
```

---

### Task 3: 성능 리뷰 에이전트

**산출물:** `docs/plans/review-performance.md`

**분석 대상:**
- `data_graph_studio/graph/sampling.py`
- `data_graph_studio/ui/panels/graph_panel.py` (2381줄)
- `data_graph_studio/ui/panels/main_graph.py` (2158줄)
- `data_graph_studio/core/cache.py`
- `data_graph_studio/core/data_query.py`
- `data_graph_studio/core/data_engine.py`

**검토 항목:**
1. **샘플링 알고리즘**: LTTB/Min-Max/Random의 정확도 vs 속도 trade-off
2. **렌더링 루프**: 불필요한 redraw 트리거, paint event 중복
3. **Polars 쿼리 효율성**: lazy eval 미활용, 불필요한 collect(), 컬럼 전체 로드
4. **캐시 히트율**: L1/L2/L3 캐시 무효화 조건이 너무 공격적인가
5. **Qt 이벤트 루프 블로킹**: 긴 작업의 메인 스레드 실행 여부
6. **메모리 누수 패턴**: 큰 데이터프레임의 참조 순환, 미해제 Qt 위젯

**리포트 형식:**
```markdown
# Performance Review

## Critical Bottlenecks
- [파일:라인] 문제 + 예상 임팩트

## Memory Issues
- ...

## Cache Inefficiencies
- ...

## Quick Wins (코드 몇 줄로 해결 가능)
- ...

## Recommended Profiling Points
- `python -m cProfile -s cumtime main.py data.csv`
```

---

### Task 4: 안정성 리뷰 에이전트

**산출물:** `docs/plans/review-stability.md`

**분석 대상:**
- `CHANGELOG.md`, `REVIEW_LOG*.md`, `PRD*.md` — 기록된 버그/이슈
- `data_graph_studio/core/` 전체 — try/except 패턴
- `data_graph_studio/ui/` 전체 — None/edge case 처리

**검토 항목:**
1. **알려진 미해결 버그**: REVIEW_LOG와 CHANGELOG에서 TODO/FIXME 추출
2. **에러 스월링**: `except: pass`, `except Exception as e: logger.warning(e)` 후 계속 실행
3. **None 처리 누락**: `state.current_df`가 None일 때 체크 없이 접근
4. **경쟁 조건**: 파일 로딩 중 UI 조작, 스트리밍 중 데이터 변경
5. **미검증 사용자 입력**: 수식 파서, 파일 경로, 커스텀 축 포맷
6. **리소스 미해제**: 파일 핸들, Qt 타이머, 스레드

**명령:**
```bash
cd /Users/lov2fn/Projects/data-graph-studio
grep -rn "except.*pass\|except.*continue" data_graph_studio/ | head -30
grep -rn "TODO\|FIXME\|HACK\|XXX" data_graph_studio/ | head -30
grep -rn "\.current_df\." data_graph_studio/ui/ | head -20
```

**리포트 형식:**
```markdown
# Stability Review

## Known Unfixed Bugs (PRD/CHANGELOG에서 추출)
- Issue: ... | Location: ... | Severity: Critical/High/Medium

## Silent Failures
- [파일:라인] 문제 설명

## Null Safety Issues
- ...

## Race Conditions
- ...

## Unvalidated Inputs
- ...
```

---

### Task 5: UI/UX 리뷰 에이전트

**산출물:** `docs/plans/review-uiux.md`

**분석 대상:**
- `data_graph_studio/ui/theme.py` (2259줄)
- `data_graph_studio/ui/panels/` 전체
- `data_graph_studio/ui/widgets/` 전체
- `data_graph_studio/ui/main_window.py`
- `DASHBOARD.md`, `PRD_data_tab_redesign.md`

**검토 항목:**
1. **테마 일관성**: 하드코딩된 색상/폰트 vs 테마 시스템 사용
2. **레이아웃 일관성**: 패딩/마진/스페이싱 통일성
3. **사용자 흐름 단절**: 직관적이지 않은 인터랙션, 숨겨진 기능
4. **에러 피드백**: 실패 시 명확한 메시지 vs 조용히 실패
5. **로딩 상태**: 긴 작업 중 progress indicator 유무
6. **접근성**: 키보드 네비게이션, 툴팁, 스크린리더 고려
7. **반응성**: 큰 데이터 로딩 중 UI 응답성
8. **PRD_data_tab_redesign 이행 상태**: 구현된 것 vs 미구현

**리포트 형식:**
```markdown
# UI/UX Review

## Critical UX Issues
- [위치] 문제 + 사용자 영향

## Theme Inconsistencies
- [파일:라인] 하드코딩된 값 — 사용해야 할 테마 토큰

## Missing User Feedback
- ...

## Flow Issues
- ...

## Quick Wins
- ...
```

---

## Phase 2: 우선순위 합산 (에이전트 작업 완료 후)

**Step 1:** 5개 리포트 읽기
**Step 2:** 전체 이슈를 하나의 우선순위 목록으로 합산

| 우선순위 | 기준 |
|---|---|
| P0 Critical | 데이터 손실, 크래시, 보안 |
| P1 High | 명확한 버그, 심각한 성능 저하 |
| P2 Medium | 코드 품질, 테스트 갭, UX 불편함 |
| P3 Low | 개선 사항, 일관성 |

**Step 3:** 사용자와 함께 P0/P1 목록 확인 후 Ralph Loop 순서 결정

---

## Phase 3: Ralph Loop 구현 (우선순위별)

각 항목마다:

**Step 1: Ralph Loop 시작**
```bash
# DGS 프로젝트 세션에서:
/ralph-loop "<구체적 수정 사항>" --completion-promise "DONE" --max-iterations 15
```

**Step 2: 완료 확인**
```bash
cd /Users/lov2fn/Projects/data-graph-studio
pytest -q  # 전체 테스트 통과 확인
```

**Step 3: 커밋**
```bash
git add -p
git commit -m "fix: <항목>"
```

> P3 항목 예시 Ralph Loop 프롬프트:
> ```
> /ralph-loop "Fix all hardcoded color values in data_graph_studio/ui/panels/
> that bypass the theme system. Each color should use self.palette() or
> theme constants from theme.py. Run pytest after each file.
> Output <promise>DONE</promise> when all files are clean."
> --completion-promise "DONE" --max-iterations 20
> ```

---

## 실행 체크리스트

- [ ] Task 1-5: 병렬 리뷰 에이전트 dispatch (동시)
- [ ] 5개 리포트 수집 완료
- [ ] Phase 2: 우선순위 목록 작성 및 사용자 승인
- [ ] Phase 3: P0 항목 Ralph Loop 구현
- [ ] Phase 3: P1 항목 Ralph Loop 구현
- [ ] Phase 3: P2 항목 Ralph Loop 구현 (시간 허락 시)
- [ ] 전체 pytest 그린 확인
- [ ] 최종 커밋 및 태그
