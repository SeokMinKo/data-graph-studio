# DGS 품질 업그레이드 설계

**날짜:** 2026-02-22
**프로젝트:** Data Graph Studio
**목표:** 코드 품질, 테스트, 성능, 안정성, UI/UX 전방위 개선

---

## 접근법: C (리뷰 → 우선순위 → Ralph Loop 구현)

### Phase 1: 병렬 리뷰

5개 에이전트가 동시에 각 도메인 분석 후 리포트 작성.

| 에이전트 | 담당 도메인 | 산출물 |
|---|---|---|
| Architecture | God objects, 모듈 결합도, SOLID 원칙, PRD-refactor-god-objects 이행 상태 | `docs/plans/review-architecture.md` |
| Tests | 커버리지 갭, 취약 케이스, 테스트 구조, edge case 누락 | `docs/plans/review-tests.md` |
| Performance | 샘플링 알고리즘, 렌더링 파이프라인, 메모리 관리 패턴 | `docs/plans/review-performance.md` |
| Stability | 에러 핸들링, 엣지케이스, PRD에 기록된 알려진 버그 | `docs/plans/review-stability.md` |
| UI/UX | PySide6 패턴, 사용자 흐름, 테마 일관성, 접근성 | `docs/plans/review-uiux.md` |

### Phase 2: 우선순위 결정

- 5개 리포트 합산
- 심각도(Critical / High / Medium / Low) + 임팩트 기준으로 그룹핑
- 사용자와 함께 구현 순서 결정

### Phase 3: Ralph Loop 구현

각 우선순위 항목마다:

```
/ralph-loop "<항목 설명>" --completion-promise "DONE" --max-iterations 15
```

- 자기교정하며 반복 구현
- 각 항목 완료 후 테스트 통과 확인

---

## 리뷰 범위

### Architecture 에이전트

- `data_graph_studio/core/state.py` (1640줄) — AppState god object 분석
- `data_graph_studio/ui/main_window.py` (2023줄) — MainWindow 결합도
- `data_graph_studio/ui/panels/` — Panel 간 의존성
- PRD-refactor-god-objects.md 이행 상태 확인

### Tests 에이전트

- `tests/` 전체 (40+ 파일)
- 커버리지 리포트 생성 및 분석
- 각 도메인별 edge case 매핑

### Performance 에이전트

- `data_graph_studio/graph/sampling.py` — LTTB/Min-Max/Random
- `data_graph_studio/ui/panels/graph_panel.py` (2381줄) — 렌더링 루프
- `data_graph_studio/core/cache.py` — L1/L2/L3 캐시 효율성

### Stability 에이전트

- 모든 PRD.md, REVIEW_LOG*.md, CHANGELOG.md의 버그/이슈 항목
- try/except 패턴 전수 조사
- None/edge case 처리 누락

### UI/UX 에이전트

- `data_graph_studio/ui/theme.py` (2259줄)
- `data_graph_studio/ui/panels/` 전체 — 일관성 검토
- 사용자 흐름 분석 (drag & drop, selection, filtering)

---

## 성공 기준

- 각 도메인 리뷰 리포트 완성
- 우선순위 목록 사용자 승인
- 각 Ralph Loop 구현 후 `pytest` 그린
