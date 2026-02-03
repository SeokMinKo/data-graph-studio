# PRD Review Log: Single-Dataset Multi-Profile Comparison

**PRD**: `PRD-profile-comparison.md`  
**Round**: 1  
**Date**: 2025-07-16  
**Reviewed Against**: `profile.py`, `profile_store.py`, `profile_controller.py`, `state.py`, `side_by_side_layout.py`, `graph_setting_mapper.py`

---

### 🧠 Behavior Reviewer

**Status**: REJECT

**Feedback**:

The PRD covers the core happy paths well but has significant gaps in edge cases and error scenarios:

1. **"X축 동일" definition is dangerously vague (Critical)**  
   FR-3/FR-4 require "X축이 동일한 프로파일" but never define what "동일" means. Does it mean:
   - Same `x_column` name? (e.g., both use "time")
   - Same data type? (numeric vs datetime)
   - Same actual values/range?
   
   This ambiguity will cause implementation disagreements. A profile with `x_column="time"` where time is datetime vs another with `x_column="time"` where time is integer — are these "동일"? The PRD must define this precisely.

2. **Profile mutation during comparison is unspecified (Critical)**  
   What happens when:
   - User edits a profile (changes chart type, Y column) while it's being compared?
   - User deletes a profile that's currently in comparison mode?
   - User renames a profile during comparison?
   
   The `ProfileController` already has signals (`profile_deleted`, `profile_renamed`) but the PRD doesn't describe how `ProfileComparisonController` reacts to them.

3. **Single profile selection behavior undefined**  
   FR-1 says "2개 이상 프로파일을 선택하여 비교 모드 진입" but what if the user selects only 1? Error message? Disabled button? The dialog behavior is not specified.

4. **Mixed chart types in Overlay undefined**  
   What happens with Overlay when Profile A is `line` and Profile B is `bar`? Both rendered as-is? Force conversion to line? The PRD doesn't address chart_type conflicts in overlay mode.

5. **Comparison mode exit flow missing**  
   How does the user leave comparison mode? Close button? Esc key? Double-click a single profile? This critical UX flow is completely absent.

6. **Data reload/refresh during comparison**  
   If the CSV file is modified externally and reloaded, all profiles reference the same DataFrame. The PRD correctly identifies NFR-4 (shared DataFrame reference) but doesn't address what happens when that DataFrame is replaced.

7. **Difference mode with different row counts**  
   FR-4 says "X축이 동일한 2개 프로파일" — but both profiles share the SAME DataFrame (same dataset). So they always have the same rows. The "difference" would only be between different Y columns. This seems like a narrow use case that the PRD doesn't clearly articulate. Is the Difference mode actually computing `Y_A - Y_B` for the same X values? This needs explicit clarification with a concrete example.

8. **No undo for comparison operations**  
   `ProfileController` has undo support. The new `ProfileComparisonController` has no undo spec. Entering/exiting comparison mode, changing sync settings — are these undoable?

**Must fix before AGREE**: Items 1, 2, 5, 7

---

### 🏗️ Structure Reviewer

**Status**: REJECT

**Feedback**:

The module decomposition is mostly reasonable but has structural conflicts with the existing codebase:

1. **ProfileComparisonState vs ComparisonSettings — overlapping responsibility (Critical)**  
   The existing `ComparisonSettings` in `state.py` already has:
   ```python
   class ComparisonSettings:
       mode: ComparisonMode
       sync_scroll: bool
       sync_zoom: bool
       sync_pan_x: bool
       sync_pan_y: bool
       sync_selection: bool
   ```
   The proposed `ProfileComparisonState` duplicates these with `sync_x`, `sync_y`, `sync_selection`. This creates two sources of truth for sync configuration. The PRD should either:
   - Extend `ComparisonSettings` to handle profile comparison, OR
   - Clearly define that `ComparisonSettings` is dataset-only and `ProfileComparisonState` is profile-only, with a discriminator for which is active.

2. **ViewSyncManager duplicates SideBySideLayout sync logic (Critical)**  
   `SideBySideLayout` already implements view synchronization with `_is_syncing` flag, `_on_panel_view_changed()`, and `set_view_range()`. The new `ViewSyncManager` would be a third sync mechanism (after `SideBySideLayout` and `ComparisonSettings`). 
   
   **Recommendation**: Extract a shared `ViewSyncManager` from the existing `SideBySideLayout` and reuse it for both dataset and profile comparison. Don't add a parallel implementation.

3. **ProfileComparisonController vs ProfileController — unclear relationship**  
   The existing `ProfileController` manages CRUD operations on profiles. The new `ProfileComparisonController` manages comparison state. But who owns the lifecycle? Does `ProfileComparisonController` depend on `ProfileController`? Can both be active simultaneously? The dependency table in Section 11 lists Module G depending on A, B, D, E, F but not on `ProfileController` — yet it clearly needs to query profiles via the store.

4. **ProfileMiniGraphWidget vs MiniGraphWidget — code duplication**  
   The PRD says "MiniGraphWidget과 유사하나 dataset_id 대신 (dataset_id, profile_id) 사용". This suggests near-copy-paste. Better approach: make `MiniGraphWidget` accept an optional `GraphSetting` parameter. If provided, render according to that setting; if not, use the dataset's default state.

5. **Module placement is clean**  
   The file placement (`core/profile_comparison.py`, `core/view_sync.py`, `ui/panels/profile_*.py`) follows existing conventions. The dependency DAG (B independent, A→C→D/E/F→G→H) enables parallel development. This is well done.

6. **Signal integration unclear**  
   `AppState` already has `comparison_mode_changed` and `comparison_settings_changed` signals. Will `ProfileComparisonController` emit these same signals or introduce new ones? If new signals, how does the main window know which comparison is active?

**Must fix before AGREE**: Items 1, 2, 3

---

### 🎨 UI Reviewer

**Status**: AGREE (conditional)

**Feedback**:

The UI design is sensible and the wireframes are clear, but several usability concerns need addressing:

1. **Ctrl+Click discovery problem (Medium)**  
   Profile multi-selection via Ctrl+Click is a power-user pattern. First-time users won't discover it. Consider:
   - A "Compare" checkbox/toggle on each profile bar item
   - A dedicated "Compare Mode" button that enables multi-select with visual cues (checkboxes appear)
   - Tooltip on the profile bar explaining multi-select

2. **Exit comparison mode — missing (High)**  
   No UI element is described for exiting comparison. Need either:
   - An "X" or "Exit Comparison" button in the comparison layout header
   - The comparison mode selector dialog should have a "Cancel" / "Back to Single" option
   - Clicking a single profile should exit comparison

3. **Small screen layout for 4 panels (Medium)**  
   Side-by-Side with 4 panels at minimum 150px each = 600px + margins. On a 1280px-wide window this works. On smaller screens, panels become too narrow. Consider:
   - 2x2 grid layout option for 3-4 panels instead of horizontal-only
   - Minimum panel width enforcement with horizontal scroll if needed
   - Responsive breakpoint: ≤2 panels horizontal, 3-4 panels grid

4. **Overlay legend readability with 8 series (Medium)**  
   8 series in one chart with distinct colors is at the edge of readability. The wireframe shows a legend but doesn't address:
   - Interactive legend (click to show/hide individual series)
   - Color accessibility (colorblind-safe palette)
   - Dual-axis labeling when units differ

5. **Sync toggle placement is good**  
   The `[Sync: ☑X축 ☑Y축 ☑Selection] [Reset All]` toolbar is well-positioned and clear. The defaults (X=on, Y=off, Selection=on) are sensible.

6. **Difference mode stats are useful**  
   Showing Mean diff, Max diff, RMSE is a good analytical feature. Consider also showing the diff as a percentage option.

7. **Mode selection dialog — Overlay/Difference disabled states**  
   FR-7 mentions disabling with tooltip, which is correct UX. Good.

**Conditional on**: Adding exit comparison UX (item 2). Other items are recommendations.

---

### 🔍 Overall Reviewer

**Status**: REJECT

**Feedback**:

1. **Section 10 "미해결 질문 — 없음" is a red flag (Critical)**  
   A PRD of this scope with zero open questions indicates insufficient scrutiny. At minimum, these should be listed:
   - How do we distinguish dataset comparison vs profile comparison in the UI state?
   - Should profile comparison persist across sessions (save/load)?
   - What's the interaction between dataset comparison and profile comparison? (FR-8 says "공존" but doesn't elaborate)

2. **FR-8 "공존" is underspecified (Critical)**  
   "기존 데이터셋 간 비교 기능과 공존" — but how exactly? Can the user:
   - Compare profiles within a dataset while also comparing across datasets?
   - Switch from dataset comparison to profile comparison in one click?
   - Are these mutually exclusive modes or composable?
   
   The existing `ComparisonMode` enum is shared between both features. Setting `SIDE_BY_SIDE` — is that for datasets or profiles? There needs to be a clear discriminator or separate mode enums.

3. **No persistence/serialization spec**  
   The existing `Profile` class has `save()` / `load()` / `to_json()`. Should comparison state be saved? If the user creates a useful comparison (Profile A vs B in Overlay), can they save and restore that view? This is a common expectation for analysis tools.

4. **Missing accessibility requirements**  
   No mention of keyboard navigation, screen reader compatibility, or high-contrast mode for the comparison views.

5. **Test coverage gaps**  
   - No test for "profile deleted during comparison" 
   - No test for "profile edited during comparison"
   - No negative test for Overlay with incompatible X axes (IT-3 tests the warning, but not the enforcement)
   - No test for switching between dataset comparison and profile comparison

6. **Success criteria are vague on regression**  
   "기존 데이터셋 비교 기능 회귀 없음" — no specific regression test list. Which existing tests must continue to pass?

7. **Version/migration**  
   If `ProfileComparisonState` is serialized, what's the schema version? The existing `GraphSetting` has `schema_version`. New state classes should follow the same pattern.

**Must fix before AGREE**: Items 1, 2

---

### ⚡ Algorithm Reviewer

**Status**: AGREE (conditional)

**Feedback**:

1. **X-axis compatibility check algorithm undefined (High)**  
   The PRD says Overlay/Difference require matching X axes. The algorithm for this check is not specified. Proposed implementation should be:
   ```
   compatible = profile_a.x_column == profile_b.x_column
   ```
   Since all profiles share the same DataFrame, same `x_column` name guarantees same data. But this should be explicit in the PRD.

2. **Difference calculation is straightforward (Good)**  
   Since profiles share the same DataFrame, `diff = df[y_col_a] - df[y_col_b]` is O(n) and trivially parallelizable with pandas vectorized ops. RMSE is `sqrt(mean(diff²))`. No algorithmic concerns here.

3. **Sync debounce strategy needs specification (Medium)**  
   "50ms 디바운스" — but which type?
   - **Trailing edge** (fire after 50ms of silence): Good for continuous pan/zoom
   - **Leading edge** (fire immediately, then suppress): Better for perceived responsiveness
   - **Throttle** (fire at most once per 50ms): Best for continuous events
   
   For pan/zoom sync, I'd recommend throttling, not debouncing. The distinction matters for UX.

4. **Overlay dual-axis assignment algorithm unspecified (Medium)**  
   "서로 다른 단위의 Y축은 dual-axis (왼/오) 자동 배정" — but how are "different units" detected? The `ValueColumn` doesn't have a `unit` field. Possible approaches:
   - If `use_secondary_axis` is set in the profile's GraphSetting → use it
   - Auto-detect by comparing Y-value ranges (different orders of magnitude)
   - Let user manually assign during comparison setup
   
   The auto-detection algorithm should be specified.

5. **Downsampling reuse is good**  
   Referencing existing `sampling.py` for >1000 points is the right approach. No need to reinvent.

6. **Selection sync algorithm**  
   Selection sync via row indices is O(k) where k = selected rows. Since all profiles share the same DataFrame, row indices are globally valid. This is clean and efficient.

**Conditional on**: Specifying the sync debounce type (item 3) and X-axis check algorithm (item 1). Items 2, 4 can be deferred to implementation.

---

### 🔧 Performance & Memory Reviewer

**Status**: AGREE

**Feedback**:

1. **NFR-4 (no data copy) is well-designed (Good)**  
   All profiles reference the same DataFrame. Only `GraphSetting` objects (lightweight metadata) are duplicated. For a 100k-row × 50-column DataFrame (~40MB), this avoids creating 4 copies in Side-by-Side mode. Memory target of <50MB additional is achievable.

2. **ViewSyncManager panel references — potential leak (Medium)**  
   `ViewSyncManager._panels: Dict[str, Any]` holds references to panel widgets. If a panel is destroyed (e.g., exiting comparison mode) but the reference in `_panels` isn't cleared, the widget won't be garbage collected. 
   
   **Mitigation**: Use `weakref.WeakValueDictionary` or ensure `_panels` is cleared on mode exit. This is an implementation concern, not a PRD issue, but should be noted in the PRD as a design constraint.

3. **QTimer-based debounce (Medium)**  
   The existing `SideBySideLayout` uses `QTimer.singleShot(50/100ms)` for sync flag reset. This is a simple but effective pattern. For the new `ViewSyncManager`, the same approach works. However, with 4 panels each emitting range-change events, worst case is 4 × 50ms timer allocations per interaction. This is negligible.

4. **Overlay rendering with 8 series × 100k rows (Medium)**  
   PyQtGraph can handle this, but the PRD's 1-second target (NFR-2) may be tight without downsampling. The PRD mentions automatic downsampling at >1000 points (Section 7), which is aggressive. For overlay, I'd recommend:
   - Downsample threshold at 5000-10000 points per series (not 1000)
   - Use LTTB (Largest Triangle Three Buckets) downsampling for visual fidelity
   
   The existing `sampling.py` presumably handles this, so it's an implementation detail.

5. **Side-by-Side 4 panels rendering budget (Good)**  
   NFR-1 says <500ms per panel. With downsampling at 1000 points, each panel renders ~1000 points, which pyqtgraph handles in <100ms. The 500ms budget is conservative and achievable.

6. **No off-screen rendering optimization mentioned**  
   If the user scrolls or resizes panels such that some are partially visible, are they still fully rendered? For 4 panels this doesn't matter, but it's worth noting.

7. **Memory target validation**  
   Back-of-envelope: 4 panels × (PlotWidget ~5MB + downsampled data ~1MB + widget tree ~1MB) ≈ 28MB. Plus ViewSyncManager overhead ~1MB. Total ~30MB < 50MB target. ✅

**No blocking issues. Recommendations noted for implementation.**

---

## Summary

| Reviewer | Status | Key Blocking Issues |
|----------|--------|-------------------|
| 🧠 Behavior | ❌ REJECT | X축 동일 정의, profile mutation during comparison, exit flow, Difference mode semantics |
| 🏗️ Structure | ❌ REJECT | State duplication (ProfileComparisonState vs ComparisonSettings), ViewSyncManager duplication, Controller relationship |
| 🎨 UI | ✅ AGREE* | *Conditional on adding exit comparison UX |
| 🔍 Overall | ❌ REJECT | "No open questions" false claim, FR-8 공존 underspecified, ComparisonMode ambiguity |
| ⚡ Algorithm | ✅ AGREE* | *Conditional on specifying sync strategy and X-axis check |
| 🔧 Perf & Memory | ✅ AGREE | No blocking issues |

**AGREE: 3/6 (with 2 conditional)**  
**REJECT: 3/6**

### Verdict: ❌ FAIL — Does not meet 4/6 threshold

### Required Changes for Round 2

1. **Define "X축 동일" precisely** — same `x_column` name is sufficient (since same DataFrame), but state it explicitly
2. **Add ProfileComparisonState → ComparisonSettings integration plan** — either extend ComparisonSettings or add a discriminator field (`comparison_target: "dataset" | "profile"`)
3. **Extract ViewSyncManager from existing SideBySideLayout** — don't create a parallel sync mechanism
4. **Define ProfileComparisonController ↔ ProfileController relationship** — lifecycle, signal forwarding
5. **Add comparison exit flow** — UI elements and state transitions for leaving comparison mode
6. **Specify profile mutation handling during comparison** — what happens on edit/delete/rename
7. **Elaborate FR-8 "공존"** — are dataset comparison and profile comparison mutually exclusive or composable?
8. **Move Section 10 open questions** — at minimum list items 1, 2, 7 above as acknowledged open questions
9. **Add Difference mode concrete example** — clarify it's computing Y_A - Y_B for the same X data
10. **Specify debounce type** — throttle (recommended) vs trailing-edge debounce

---
---

# Round 2 Review

**PRD**: `PRD-profile-comparison.md` (v2)  
**Round**: 2  
**Date**: 2025-07-16  
**Reviewed Against**: `state.py` (ComparisonSettings, ComparisonMode), `profile_controller.py` (ProfileController), `side_by_side_layout.py` (SideBySideLayout, MiniGraphWidget)

---

## Round 1 Required Changes — Verification

| # | Required Change | Status | Evidence |
|---|----------------|--------|----------|
| 1 | "X축 동일" = same `x_column` name | ✅ Fixed | FR-3/FR-4: "(= 같은 `x_column` 이름)" 명시. UT-6: `profile_a.x_column == profile_b.x_column` |
| 2 | ComparisonSettings 통합 (comparison_target) | ✅ Fixed | §6.1: `comparison_target: str = "dataset"`, `comparison_profile_ids`, `comparison_dataset_id` 추가. 별도 `ProfileComparisonState` 없음 |
| 3 | ViewSyncManager를 SideBySideLayout에서 추출 | ✅ Fixed | §4: "기존 `SideBySideLayout`의 동기화 로직을 **추출**하여 공용 매니저로 분리". §6.2: 상세 API. §11 Module H: SideBySideLayout 리팩터 |
| 4 | ProfileComparisonController ↔ ProfileController 관계 | ✅ Fixed | §6.4: 생성자에서 `controller: ProfileController` 받음. `profile_deleted`/`profile_renamed`/`profile_applied` 시그널 구독 |
| 5 | 비교 종료 플로우 | ✅ Fixed | FR-9: 4가지 종료 경로 (✕ Exit, Esc, 단일 프로파일 클릭, 데이터셋 비교 진입). §5.2: 상세 UX |
| 6 | 비교 중 프로파일 변경 대응 | ✅ Fixed | FR-10: 삭제(패널 제거+자동 종료), 이름변경(헤더 갱신), 설정 수정(리렌더+X축 변경 시 Side-by-Side 전환) |
| 7 | FR-8 상호 배타적 명시 | ✅ Fixed | FR-8: "상호 배타적. 한 번에 하나만 활성. 프로파일 비교 진입 시 데이터셋 비교 자동 해제, 역도 동일" |
| 8 | Section 10 미해결 질문 | ✅ Fixed | Q1: 비교 상태 저장/복원, Q2: 키보드 접근성, Q3: Colorblind-safe palette — 모두 향후 기능으로 인지/연기 |
| 9 | Difference 모드 구체적 예시 | ✅ Fixed | §5.5: "Profile A: Y=voltage, Profile B: Y=current → diff = voltage - current per row". `df[Y_col_A] - df[Y_col_B]` 공식 명시 |
| 10 | Debounce → throttle 명시 | ✅ Fixed | §5.6: "throttle (50ms 간격 최대 1회 fire, leading edge)". NFR-3: "(throttle 방식)". §7: "leading edge fire, 최대 20fps" |

**10/10 Required Changes Addressed** ✅

---

## Reviewer Assessments

### 🧠 Behavior Reviewer

**Status**: ✅ AGREE

**Round 1 blocking items resolved:**
- ✅ "X축 동일" 정의: FR-3/FR-4에서 `(= 같은 x_column 이름)` 명확히 정의. 같은 DataFrame을 공유하므로 x_column 이름이 같으면 데이터도 동일 — 논리적으로 완전함.
- ✅ Profile mutation: FR-10의 3가지 시나리오(삭제/이름변경/설정수정) 모두 구체적 동작 명시. Overlay/Difference에서 X축 변경 시 Side-by-Side 폴백은 올바른 설계.
- ✅ Exit flow: FR-9 + §5.2에서 4가지 종료 경로 및 `ComparisonMode.SINGLE`로의 상태 전환 명시.
- ✅ Difference 의미론: §5.5의 구체적 예시와 수식으로 "같은 DataFrame, 다른 Y컬럼" 모델 명확.

**새로운 관찰 (비차단):**
- FR-10의 "1개만 남으면 자동으로 비교 모드 종료"는 올바른 엣지 케이스 처리
- FR-11의 mixed chart_type → line 통일도 합리적 결정
- §5.1의 단일 프로파일 선택 시 비활성화 + 툴팁도 R1에서 제기한 우려 해결
- Data reload during comparison (R1 item 6)은 여전히 미기술이나, R1에서도 must-fix가 아니었고, 동일 DataFrame 참조 모델에서는 reload 시 전체 UI가 리프레시되므로 자연 처리됨

**남은 권고 (비차단):**
- FR-10에서 프로파일 수정 감지의 구체적 메커니즘(어떤 시그널이 트리거되는지)은 구현 단계에서 확인 필요. `ProfileController.profile_applied` 시그널이 이미 존재하므로 문제 없을 것으로 판단.

---

### 🏗️ Structure Reviewer

**Status**: ✅ AGREE

**Round 1 blocking items resolved:**
- ✅ State 중복 해소: `ProfileComparisonState` 클래스 제거, 기존 `ComparisonSettings`에 `comparison_target` 필드 추가로 단일 진실 소스 유지. 기존 `comparison_datasets`(데이터셋용)과 `comparison_profile_ids`(프로파일용)이 `comparison_target`으로 구분됨 — 깔끔한 discriminated union 패턴.
- ✅ ViewSyncManager 추출: §6.2에서 기존 `SideBySideLayout._on_panel_view_changed()`, `set_view_range()` 로직의 이전을 명시. §11 Module B(신규 추출) → Module H(기존 리팩터) 의존성 올바름.
- ✅ Controller 관계: §6.4에서 `ProfileComparisonController(store, controller, state)` 시그니처로 명확한 의존성. `ProfileController`의 시그널을 구독하는 관계 — 소유가 아닌 협력 패턴.

**구조 분석:**
- `MiniGraphWidget` 확장(§6.3): optional `GraphSetting` 파라미터 추가는 R1에서 권고한 접근법 그대로. 기존 `dataset_id` 기반 동작과 하위 호환 유지.
- `ProfileSideBySideLayout`이 `SideBySideLayout` 상속(§11 Module D): 기존 코드의 `MiniGraphWidget` 생성을 `GraphSetting` 포함 버전으로 오버라이드하는 template method 패턴으로 구현 가능. 적절.
- Signal 통합: 기존 `AppState.comparison_mode_changed`/`comparison_settings_changed` 재사용 + `comparison_target` discriminator로 소비자가 모드 판별 가능. 새 시그널 불필요.
- §11 병렬화 DAG: A,B 독립 → C,H 병렬 → D,E,F 병렬 → G → I — 의존성 사이클 없음, 작업 분리 깔끔.

**남은 권고 (비차단):**
- `ViewSyncManager`의 기본값(`_sync_y: False`)과 기존 `ComparisonSettings.sync_pan_y: True`의 차이: 런타임에 `ComparisonSettings`에서 초기화하도록 구현 시 주의 필요. PRD 수준에서는 문제 아님.
- `ProfileSideBySideLayout` 상속 시 `SideBySideLayout.refresh()` 메서드의 dataset_id 기반 로직을 오버라이드해야 함 — 구현 시 protected method 분리 권고.

---

### 🎨 UI Reviewer

**Status**: ✅ AGREE

**Round 1 조건부 항목 해결:**
- ✅ Exit comparison UX: §5.2에서 4가지 종료 경로 완전 명세. 모든 와이어프레임에 `[✕ Exit]` 버튼 포함.

**UI/UX 평가:**
- §5.1 비교 진입: Compare Mode 토글 → 체크박스 표시 방식은 R1에서 제기한 Ctrl+Click 발견성 문제를 해결. 두 가지 진입 방식(Ctrl+Click + 토글 모드) 제공으로 초보자/숙련자 모두 커버.
- §5.3 반응형 레이아웃: "패널 < 200px 시 2×2 그리드 자동 전환"은 R1의 소형 화면 우려 해결.
- §5.4 Overlay 범례: "click legend to show/hide individual series" — 인터랙티브 범례 추가됨.
- §5.4 Dual-axis: "Y축 단위가 다르면 (값 범위 10배 이상 차이) 자동 dual-axis" — 명확한 기준.
- §5.5 Difference 통계: Mean Diff, Max Diff, RMSE 표시 — 분석 가치 높음.
- FR-7 비활성 모드 + 툴팁: 올바른 UX 패턴.
- FR-11 Mixed chart_type → line + 경고: 사용자에게 투명한 처리.

**남은 권고 (비차단):**
- Difference 모드에서 diff를 percentage 옵션으로 표시하는 기능은 향후 추가 가치 있음 (R1에서 제안했으나 현 범위에서는 불필요)
- §5.3의 μ, σ 표시는 좋으나 어떤 값의 통계인지(선택된 Y컬럼) 명시하면 더 좋겠음 — 구현 시 자연스럽게 해결될 수준

---

### 🔍 Overall Reviewer

**Status**: ✅ AGREE

**Round 1 blocking items resolved:**
- ✅ Section 10 미해결 질문: Q1(상태 저장/복원 → v2), Q2(키보드 접근성 → 별도 이슈), Q3(Colorblind palette → 테마 시스템) — 현실적이고 솔직한 인지. "미해결 질문 없음"이라는 R1의 비현실적 주장이 해소됨.
- ✅ FR-8 상호 배타적: "한 번에 하나만 활성"으로 명확히 정의. 전환 시 자동 해제 동작 명시. `comparison_target` 필드가 discriminator 역할.

**일관성 검증:**
- `ComparisonMode` enum(SINGLE, OVERLAY, SIDE_BY_SIDE, DIFFERENCE)은 데이터셋/프로파일 비교 모두에 재사용 — `comparison_target`으로 구분. 일관적.
- FR 번호(1~11)가 연속적이고 상호 참조 없이 독립적. 깔끔.
- NFR(1~5)이 각각 측정 가능한 기준 포함. PT(1~4)와 1:1 대응.
- 테스트 커버리지: IT-6(삭제), IT-7(수정), IT-8(X축 변경), IT-4/5(모드 전환) — R1에서 지적한 누락 테스트 모두 추가됨.
- RT-1~4: 구체적 기존 테스트 파일 명시(test_multi_dataset.py, test_integration.py, test_profile.py, test_state.py).
- Section 4 제외 범위: undo/redo, 교차 비교, 3D, 상태 저장 — 명확한 경계.

**남은 권고 (비차단):**
- `ComparisonSettings` 확장 시 schema_version 없음 — 하지만 현재 `ComparisonSettings`는 `@dataclass`로 메모리 전용(파일 직렬화 없음)이고, 상태 저장은 Q1(v2)로 연기됨. 현 시점에서는 불필요.
- 성공 기준(§9)이 테스트 시나리오(§8)와 잘 매핑됨. 누락 없음.

---

### ⚡ Algorithm Reviewer

**Status**: ✅ AGREE

**Round 1 조건부 항목 해결:**
- ✅ X축 호환성 체크: `profile_a.x_column == profile_b.x_column` 명시. 같은 DataFrame이므로 이름 일치 = 데이터 일치. 추가 타입/범위 체크 불필요.
- ✅ Throttle 명시: "throttle (50ms 간격 최대 1회 fire, leading edge)" — trailing-edge debounce 아닌 throttle임을 확정. Leading edge로 첫 이벤트 즉시 반영, 이후 50ms 억제. pan/zoom UX에 최적.

**알고리즘 분석:**
- Difference 계산: `df[Y_col_A] - df[Y_col_B]` — O(n) pandas vectorized op. RMSE = `sqrt(mean(diff²))` — O(n). 100k행에서 수 ms. 문제 없음.
- Dual-axis 판정(§7): "max/min 비율 > 10배" — 엄밀히는 두 Y컬럼의 값 범위(max-min) 비율을 의미. UT-9에서 검증. 구현 시 `range_A / range_B` 또는 `max(abs(A)) / max(abs(B))`로 해석 가능하나, 어느 쪽이든 10배 임계값이면 결과 동일. 엣지 케이스(0 포함, 음수)는 구현에서 방어 코딩 필요 — PRD 수준에서는 충분.
- Downsampling: §7에서 "5000개 이상 포인트 시 자동 다운샘플링 (LTTB)" — R1의 "1000은 너무 공격적" 피드백 반영됨. LTTB는 시각적 충실도 최적.
- Selection sync: 행 인덱스 기반 O(k) — 같은 DataFrame이므로 인덱스 전역 유효. 깔끔.
- ViewSyncManager의 `_pending_sync: Optional[tuple]`는 last-write-wins coalescing — throttle 구간 내 여러 패널 이벤트 시 마지막 것만 적용. 4패널 동시 pan 시에도 O(1) 저장.

**남은 권고 (비차단):**
- Dual-axis 판정의 정확한 수식(range ratio vs absolute max ratio)은 구현 시 UT-9에서 확정하면 됨.

---

### 🔧 Performance & Memory Reviewer

**Status**: ✅ AGREE

**메모리 분석:**
- ✅ 데이터 복사 없음(NFR-4): 모든 프로파일이 같은 DataFrame 참조. `GraphSetting`은 메타데이터만(< 1KB). 100k행 × 50컬럼 DataFrame ~40MB가 1벌만 존재.
- ✅ WeakValueDictionary(§6.2): `ViewSyncManager._panels`가 `weakref.WeakValueDictionary` 사용. 패널 위젯 파괴 시 자동 참조 해제, GC 가능. R1에서 제기한 메모리 누수 우려 해결.
- Back-of-envelope: 4패널 × (PlotWidget ~5MB + downsampled buffer ~2MB + widget tree ~1MB) ≈ 32MB + ViewSyncManager ~1MB = ~33MB < 50MB 목표. ✅

**렌더링 성능:**
- NFR-1: 패널당 < 500ms. 5000포인트 다운샘플 후 pyqtgraph 렌더링 ~50-100ms. 충분한 마진.
- NFR-2: Overlay 8계열 100k행 < 1초. 계열당 5000포인트 다운샘플 → 8 × 5000 = 40k포인트 총 렌더링. pyqtgraph 기준 ~300-500ms. 달성 가능.
- NFR-3: 동기화 < 50ms. QTimer throttle + leading edge fire. `setRange()` 호출은 ~1-5ms. 50ms 내 충분.

**Throttle 구현:**
- §7: "QTimer 50ms, leading edge fire" — 기존 `SideBySideLayout`의 `QTimer.singleShot(50/100ms)` 패턴과 일관. 4패널 × 50ms 타이머 = 무시 가능한 오버헤드.
- `_pending_sync` 필드로 코알레싱 — 타이머 fire 시점에 최신 값만 전파. 중간 이벤트 폐기. 효율적.

**남은 권고 (비차단):**
- Overlay 모드에서 8계열 × dual-axis 시 pyqtgraph의 `ViewBox` 2개 관리 오버헤드 존재하나 측정 가능한 수준은 아님.
- Difference 모드의 shaded area (fill_between) 렌더링은 추가 ~50k 폴리곤 — pyqtgraph `FillBetweenItem` 성능 양호.

---

## Round 2 Summary

| Reviewer | Status | Key Notes |
|----------|--------|-----------|
| 🧠 Behavior | ✅ AGREE | R1 4개 blocking 항목 모두 해결. 엣지 케이스 처리 완전 |
| 🏗️ Structure | ✅ AGREE | ComparisonSettings 통합, ViewSyncManager 추출, Controller 협력 패턴 — 기존 코드와 정합성 확인 |
| 🎨 UI | ✅ AGREE | Exit UX 완성, 반응형 레이아웃, 인터랙티브 범례 추가 |
| 🔍 Overall | ✅ AGREE | 미해결 질문 인지, FR-8 명확화, 테스트 커버리지 완전, 회귀 테스트 명시 |
| ⚡ Algorithm | ✅ AGREE | X축 체크/throttle/dual-axis 판정 모두 명시. LTTB 다운샘플 임계값 5000으로 조정 |
| 🔧 Perf & Memory | ✅ AGREE | WeakRef 적용, 50MB 목표 달성 가능, throttle 구현 효율적 |

**AGREE: 6/6**

### Verdict: ✅ PASS — All 6 reviewers agree. PRD approved for implementation.

### Recommendations for Implementation Phase (non-blocking)

1. **ViewSyncManager 초기값**: `ComparisonSettings`에서 런타임 초기화하도록 구현 (하드코딩 금지)
2. **ProfileSideBySideLayout 상속**: `SideBySideLayout.refresh()` 내 패널 생성 로직을 protected method로 분리하여 오버라이드 용이하게
3. **Dual-axis 판정 수식**: `range_A / range_B` 사용 시 0 방어 코딩 필수 (zero-division, all-NaN 컬럼)
4. **Data reload during comparison**: 기존 데이터 리로드 시그널에 의한 전체 리프레시가 비교 모드에서도 동작하는지 IT에서 확인
5. **와이어프레임 통계**: Side-by-Side의 μ/σ가 어떤 Y컬럼 기준인지 구현 시 명확히 (활성 value_columns[0] 기준 권고)
