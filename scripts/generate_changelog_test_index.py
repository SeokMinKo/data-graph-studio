#!/usr/bin/env python3
"""Generate CHANGELOG ↔ tests index markdown + manual mapping priority list.

Usage:
  python scripts/generate_changelog_test_index.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
OUT_INDEX = ROOT / "docs" / "changelog-test-index.md"
OUT_MANUAL = ROOT / "docs" / "changelog-manual-mapping-priority.md"

# Keyword-driven mapping (lightweight, maintainable)
RULES = [
    (
        re.compile(
            r"Open Project|프로젝트 열기|저장/로드|프로젝트 탐색창|데이터셋 표시|로드",
            re.I,
        ),
        [
            "tests/test_project.py",
            "tests/unit/test_main_graph_event_sequence.py",
        ],
    ),
    (
        re.compile(r"Perfetto|permission denied|one-shot|fallback", re.I),
        [
            "tests/unit/test_perfetto_oneshot_fallback.py",
            "tests/unit/test_trace_controller_perfetto_pipeline.py",
        ],
    ),
    (
        re.compile(r"Selection|Draw|mouseReleaseEvent|드래그|drawing", re.I),
        [
            "tests/unit/test_main_graph_event_sequence.py",
            "tests/test_drawing.py",
            "tests/unit/test_selection_sync.py",
        ],
    ),
    (
        re.compile(r"Undo|Redo", re.I),
        [
            "tests/test_project.py",
            "tests/test_bug_fixes.py",
        ],
    ),
    (
        re.compile(r"Windows|Program Files|권한", re.I),
        [
            "tests/test_updater_validation.py",
        ],
    ),
    (
        re.compile(r"autosave|세션 복원|프로파일", re.I),
        [
            "tests/test_project.py",
            "tests/unit/test_ipc_profile.py",
        ],
    ),
    (
        re.compile(r"multi-file|multiple files|멀티 데이터셋", re.I),
        [
            "tests/test_bug_fixes.py",
            "tests/test_multi_dataset.py",
        ],
    ),
]

# Function-level hints for quick triage
FUNCTION_RULES = [
    (
        re.compile(r"Open Project|저장/로드|복원|프로젝트", re.I),
        [
            "tests/test_project.py::TestProjectFileIO::test_load_project",
            "tests/test_project.py::TestProjectRegressionCoverage::test_legacy_data_source_migrates_to_data_sources",
        ],
    ),
    (
        re.compile(r"Selection|Draw|mouseReleaseEvent|드래그", re.I),
        [
            "tests/unit/test_main_graph_event_sequence.py::TestMainGraphMouseEventSequence::test_rect_select_press_move_release_selects_expected_points",
            "tests/unit/test_main_graph_event_sequence.py::TestMainGraphMouseEventSequence::test_mode_switch_during_rect_drag_cleans_stale_selection_state",
        ],
    ),
    (
        re.compile(r"Perfetto|permission denied|fallback", re.I),
        [
            "tests/unit/test_perfetto_oneshot_fallback.py::test_oneshot_fallback_command_used_when_config_mode_fails",
        ],
    ),
    (
        re.compile(r"multi-file|multiple files|멀티 데이터셋", re.I),
        [
            "tests/test_bug_fixes.py::TestFileLoadingControllerRegression::test_open_multiple_files_with_paths_enables_overlay_compare",
        ],
    ),
]

PRIORITY_KEYWORDS = [
    (re.compile(r"데이터.*로드|저장/로드|복원|file|project", re.I), 3),
    (re.compile(r"permission|권한|crash|fail|error", re.I), 3),
    (re.compile(r"selection|draw|drag|mouse", re.I), 2),
    (re.compile(r"theme|color|UI|가독성", re.I), 1),
]


def extract_bugfix_lines(changelog_text: str) -> list[tuple[str, str]]:
    current_version = "unknown"
    rows: list[tuple[str, str]] = []
    for line in changelog_text.splitlines():
        if line.startswith("## ["):
            current_version = line.strip()
            continue
        if line.strip().startswith("- ") and ("버그" in line or "fix" in line.lower()):
            rows.append((current_version, line.strip()))
    return rows


def dedupe(items: list[str]) -> list[str]:
    out: list[str] = []
    seen = set()
    for x in items:
        if x not in seen:
            seen.add(x)
            out.append(x)
    return out


def map_tests(bug_line: str) -> list[str]:
    mapped: list[str] = []
    for pattern, tests in RULES:
        if pattern.search(bug_line):
            mapped.extend(tests)
    return dedupe(mapped)


def map_test_functions(bug_line: str) -> list[str]:
    mapped: list[str] = []
    for pattern, funcs in FUNCTION_RULES:
        if pattern.search(bug_line):
            mapped.extend(funcs)
    return dedupe(mapped)


def score_priority(bug_line: str) -> int:
    score = 0
    for pattern, pts in PRIORITY_KEYWORDS:
        if pattern.search(bug_line):
            score += pts
    return score


def score_to_label(score: int) -> str:
    if score >= 4:
        return "P1"
    if score >= 2:
        return "P2"
    return "P3"


def generate_index(
    rows: list[tuple[str, str]],
) -> tuple[list[str], list[tuple[int, str, str]]]:
    lines = [
        "# CHANGELOG ↔ Test Index",
        "",
        "자동 생성 파일. 버그 수정 이력과 관련 테스트 파일/함수를 키워드 기반으로 매핑한다.",
        "",
        "| Version | Bugfix item | Related tests | Related test functions |",
        "|---|---|---|---|",
    ]

    manual_items: list[tuple[int, str, str]] = []

    for version, bug in rows:
        tests = map_tests(bug)
        funcs = map_test_functions(bug)
        if tests:
            test_cell = "<br>".join(f"`{t}`" for t in tests)
            func_cell = (
                "<br>".join(f"`{f}`" for f in funcs)
                if funcs
                else "(function mapping pending)"
            )
        else:
            test_cell = "(manual mapping needed)"
            func_cell = "(manual mapping needed)"
            manual_items.append((score_priority(bug), version, bug))
        lines.append(f"| {version} | {bug} | {test_cell} | {func_cell} |")

    return lines, manual_items


def generate_manual_priority(manual_items: list[tuple[int, str, str]]) -> list[str]:
    lines = [
        "# CHANGELOG Manual Mapping Priority",
        "",
        "자동 생성 파일. `manual mapping needed` 항목을 우선순위로 정렬한다.",
        "",
        "| Priority | Score | Version | Bugfix item |",
        "|---|---:|---|---|",
    ]

    for score, version, bug in sorted(
        manual_items, key=lambda x: (-x[0], x[1]), reverse=False
    ):
        lines.append(f"| {score_to_label(score)} | {score} | {version} | {bug} |")

    if not manual_items:
        lines.append("| P3 | 0 | - | manual mapping needed 항목 없음 |")

    return lines


def main() -> None:
    changelog_text = CHANGELOG.read_text(encoding="utf-8")
    rows = extract_bugfix_lines(changelog_text)

    index_lines, manual_items = generate_index(rows)
    manual_lines = generate_manual_priority(manual_items)

    OUT_INDEX.write_text("\n".join(index_lines) + "\n", encoding="utf-8")
    OUT_MANUAL.write_text("\n".join(manual_lines) + "\n", encoding="utf-8")

    print(f"Generated: {OUT_INDEX}")
    print(f"Generated: {OUT_MANUAL}")


if __name__ == "__main__":
    main()
