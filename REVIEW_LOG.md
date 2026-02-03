# PRD Review Log

## Feature: Data Table Enhancement (Sorting & Searching)
PRD File: `PRD_TABLE_ENHANCEMENT.md`

---

## Round 1
Date: 2026-02-03 08:55 KST

### 🧠 Behavior Reviewer
**Status**: ✅ AGREE
**Feedback**:
- FR-3.6 컬럼 선택 UI 상세 필요 (단일? 다중?)
- 기존 헤더 메뉴에 정렬 초기화 항목 추가 방식 명시 필요
- 핵심 동작은 모두 정의됨

### 🏗️ Structure Reviewer
**Status**: ❌ REJECT
**Feedback**:
- `SortState` 저장 위치 불명확 → Model 내부 저장 권장
- `original_indices: List[int]`는 대용량에서 메모리 비효율
- `pl.Series` 또는 `np.ndarray`로 변경 필요

### 🎨 UI Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 정렬 아이콘 색상: `#59B8E3` 사용 권장
- 로딩 인디케이터: 검색 입력창 내 작은 스피너 권장
- 기본 UI 구조 적절

### 🔍 Overall Reviewer
**Status**: ✅ AGREE
**Feedback**:
- IT-2, IT-3, IT-4 조합 테스트 상세화 필요
- Phase 3 포함 여부 명확히 해야 함
- 전체적으로 일관성 있음

### ⚡ Algorithm Reviewer
**Status**: ❌ REJECT
**Feedback**:
- 캐시 무효화 조건 명시 필요
- 검색 + 정렬 순서 명시 필요 (검색 → 정렬)
- stable sort 필요 여부 결정 필요

### 🔧 Performance & Memory Reviewer
**Status**: ❌ REJECT
**Feedback**:
- `_sorted_df` 캐싱은 메모리 2배 → 인덱스만 저장
- QThread 사용 기준 명시: 100,000행 이상
- 정렬 인덱스는 `pl.Int32` 사용 (메모리 50% 절감)

### Summary
- **AGREE**: 3/6 (Behavior, UI, Overall)
- **통과 여부**: ❌ FAIL (4명 이상 필요)

### Actions Taken
1. `SortState` 저장 위치 명시: PolarsTableModel 내부
2. `original_indices` → `sort_indices: pl.Series(dtype=pl.Int32)` 변경
3. 캐시 무효화 조건 추가
4. 검색 + 정렬 순서 명시 (필터 → 검색 → 정렬)
5. QThread 사용 기준 명시 (100k행 이상)
6. `_sorted_df` 캐싱 제거, 인덱스 기반 접근으로 변경
7. 메모리 증가 제한 20% → 10%로 강화

---

## Round 2
Date: 2026-02-03 08:58 KST

### 🧠 Behavior Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 이전 피드백 유지, 핵심 동작 정의 충분

### 🏗️ Structure Reviewer
**Status**: ✅ AGREE
**Feedback**:
- `SortState`가 Model 내부 저장으로 명시됨 ✓
- `sort_indices: pl.Series` 사용으로 메모리 효율화 ✓
- 캐시 무효화 조건 명시됨 ✓

### 🎨 UI Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 이전 피드백 유지

### 🔍 Overall Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 검색 + 정렬 순서가 6.3절에 명시됨 ✓
- 전체 흐름 일관성 유지

### ⚡ Algorithm Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 캐시 무효화 조건 명시됨 ✓
- 검색 → 정렬 순서 명시됨 ✓
- unstable sort 기본, stable 필요 시 옵션 사용으로 명시됨 ✓

### 🔧 Performance & Memory Reviewer
**Status**: ✅ AGREE
**Feedback**:
- 인덱스 기반 접근으로 변경됨 ✓
- QThread 기준 100k행 명시됨 ✓
- `pl.Int32` 사용 명시됨 ✓
- 메모리 증가 10% 이하로 강화됨 ✓

### Summary
- **AGREE**: 6/6
- **통과 여부**: ✅ PASS

### Next Steps
1. 구현 단계 진행
2. TDD 기반 테스트 작성
3. 병렬 구현 에이전트 활용 가능
