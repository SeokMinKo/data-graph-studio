#!/usr/bin/env python3
"""Generate CHANGELOG ↔ tests index markdown.

Usage:
  python scripts/generate_changelog_test_index.py
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHANGELOG = ROOT / "CHANGELOG.md"
OUT = ROOT / "docs" / "changelog-test-index.md"

# Keyword-driven mapping (lightweight, maintainable)
RULES = [
    (re.compile(r"Open Project|프로젝트 열기|로드", re.I), [
        "tests/test_project.py",
        "tests/unit/test_main_graph_event_sequence.py",
    ]),
    (re.compile(r"Perfetto|permission denied|one-shot|fallback", re.I), [
        "tests/unit/test_perfetto_oneshot_fallback.py",
        "tests/unit/test_trace_controller_perfetto_pipeline.py",
    ]),
    (re.compile(r"Selection|Draw|mouseReleaseEvent|드래그", re.I), [
        "tests/unit/test_main_graph_event_sequence.py",
        "tests/test_drawing.py",
        "tests/unit/test_selection_sync.py",
    ]),
    (re.compile(r"Undo|Redo", re.I), [
        "tests/test_project.py",
        "tests/test_bug_fixes.py",
    ]),
    (re.compile(r"Windows|Program Files|권한", re.I), [
        "tests/test_updater_validation.py",
    ]),
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


def map_tests(bug_line: str) -> list[str]:
    mapped: list[str] = []
    for pattern, tests in RULES:
        if pattern.search(bug_line):
            mapped.extend(tests)
    # dedupe while preserving order
    out = []
    seen = set()
    for t in mapped:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def main() -> None:
    changelog_text = CHANGELOG.read_text(encoding="utf-8")
    rows = extract_bugfix_lines(changelog_text)

    lines = [
        "# CHANGELOG ↔ Test Index",
        "",
        "자동 생성 파일. 버그 수정 이력과 관련 테스트 파일을 키워드 기반으로 매핑한다.",
        "",
        "| Version | Bugfix item | Related tests |",
        "|---|---|---|",
    ]

    for version, bug in rows:
        tests = map_tests(bug)
        test_cell = "<br>".join(f"`{t}`" for t in tests) if tests else "(manual mapping needed)"
        lines.append(f"| {version} | {bug} | {test_cell} |")

    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Generated: {OUT}")


if __name__ == "__main__":
    main()
