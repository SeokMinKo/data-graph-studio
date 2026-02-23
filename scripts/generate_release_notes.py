#!/usr/bin/env python3
"""
릴리즈 노트 자동 생성기

커밋 로그를 파싱하여 Conventional Commits 기반 릴리즈 노트를 생성한다.

사용법:
  # 최신 태그의 릴리즈 노트
  python scripts/generate_release_notes.py

  # 특정 버전
  python scripts/generate_release_notes.py v0.13.0

  # 전체 CHANGELOG.md 생성
  python scripts/generate_release_notes.py --full

  # GitHub Release body용 (마크다운)
  python scripts/generate_release_notes.py v0.13.0 --format github
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional


# ── 설정 ──────────────────────────────────────────────────

COMMIT_TYPES = {
    "feat": "✨ Features",
    "fix": "🐛 Bug Fixes",
    "perf": "⚡ Performance",
    "refactor": "♻️ Refactor",
    "docs": "📝 Documentation",
    "style": "🎨 Style",
    "test": "🧪 Tests",
    "build": "📦 Build",
    "ci": "🔧 CI",
    "chore": "🔨 Chores",
}

# feat, fix 등이 아닌 커밋은 여기로
FALLBACK_SECTION = "📌 Other Changes"

# Conventional Commit 패턴: type(scope): description
CC_PATTERN = re.compile(
    r"^(?P<type>[a-z]+)"       # type
    r"(?:\((?P<scope>[^)]+)\))?"  # optional (scope)
    r"(?P<breaking>!)?"        # optional breaking change marker
    r":\s*"                    # colon + space
    r"(?P<desc>.+)$"           # description
)

KST = timezone(timedelta(hours=9))


# ── 데이터 ────────────────────────────────────────────────

@dataclass
class Commit:
    hash: str
    type: str
    scope: Optional[str]
    description: str
    breaking: bool
    raw: str


@dataclass
class VersionNotes:
    tag: str
    date: str
    commits: list[Commit] = field(default_factory=list)
    breaking_changes: list[Commit] = field(default_factory=list)


# ── Git 헬퍼 ─────────────────────────────────────────────

def git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        capture_output=True, text=True, check=True,
    )
    return result.stdout.strip()


def get_sorted_tags() -> list[str]:
    """시맨틱 버전 순으로 정렬된 태그 목록"""
    raw = git("tag", "-l", "--sort=version:refname")
    if not raw:
        return []
    return [t for t in raw.splitlines() if t.startswith("v")]


def get_tag_date(tag: str) -> str:
    """태그의 날짜 (YYYY-MM-DD KST)"""
    try:
        iso = git("log", "-1", "--format=%aI", tag)
        dt = datetime.fromisoformat(iso).astimezone(KST)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(KST).strftime("%Y-%m-%d")


def get_commits_between(from_ref: Optional[str], to_ref: str) -> list[str]:
    """두 ref 사이의 커밋 (hash + message)"""
    if from_ref:
        range_spec = f"{from_ref}..{to_ref}"
    else:
        range_spec = to_ref
    raw = git("log", range_spec, "--oneline", "--no-merges")
    if not raw:
        return []
    return raw.splitlines()


# ── 파싱 ─────────────────────────────────────────────────

def parse_commit(line: str) -> Commit:
    parts = line.split(" ", 1)
    hash_ = parts[0]
    msg = parts[1] if len(parts) > 1 else ""

    m = CC_PATTERN.match(msg)
    if m:
        return Commit(
            hash=hash_,
            type=m.group("type"),
            scope=m.group("scope"),
            description=m.group("desc"),
            breaking=bool(m.group("breaking")),
            raw=msg,
        )
    # Conventional Commit 형식이 아닌 경우
    return Commit(
        hash=hash_,
        type="other",
        scope=None,
        description=msg,
        breaking=False,
        raw=msg,
    )


def build_version_notes(tag: str, prev_tag: Optional[str]) -> VersionNotes:
    lines = get_commits_between(prev_tag, tag)
    commits = [parse_commit(line) for line in lines]
    breaking = [c for c in commits if c.breaking]

    return VersionNotes(
        tag=tag,
        date=get_tag_date(tag),
        commits=commits,
        breaking_changes=breaking,
    )


# ── 렌더링 ────────────────────────────────────────────────

def render_commit(c: Commit, include_hash: bool = True) -> str:
    scope_part = f"**{c.scope}:** " if c.scope else ""
    hash_part = f" ([`{c.hash[:7]}`](../../commit/{c.hash}))" if include_hash else ""
    breaking_mark = " ⚠️ **BREAKING**" if c.breaking else ""
    return f"- {scope_part}{c.description}{hash_part}{breaking_mark}"


def render_version(notes: VersionNotes, fmt: str = "changelog") -> str:
    if not notes.commits:
        return ""

    lines: list[str] = []

    # 헤더
    if fmt == "changelog":
        lines.append(f"## [{notes.tag}] — {notes.date}")
    else:
        # GitHub Release: 태그 이름은 제목에 있으므로 날짜만
        lines.append(f"*Released: {notes.date}*")

    lines.append("")

    # Breaking Changes
    if notes.breaking_changes:
        lines.append("### ⚠️ Breaking Changes")
        lines.append("")
        for c in notes.breaking_changes:
            lines.append(render_commit(c, include_hash=(fmt == "changelog")))
        lines.append("")

    # 타입별 그룹
    grouped: dict[str, list[Commit]] = {}
    for c in notes.commits:
        key = c.type if c.type in COMMIT_TYPES else "other"
        grouped.setdefault(key, []).append(c)

    # feat, fix 우선 → 나머지 알파벳순
    type_order = list(COMMIT_TYPES.keys()) + ["other"]
    for type_key in type_order:
        commits = grouped.get(type_key, [])
        if not commits:
            continue
        section_name = COMMIT_TYPES.get(type_key, FALLBACK_SECTION)
        lines.append(f"### {section_name}")
        lines.append("")
        for c in commits:
            lines.append(render_commit(c, include_hash=(fmt == "changelog")))
        lines.append("")

    return "\n".join(lines)


def render_full_changelog(tags: list[str]) -> str:
    lines = [
        "# Changelog",
        "",
        "All notable changes to Data Graph Studio.",
        "",
        "Format: [Conventional Commits](https://www.conventionalcommits.org/)",
        "",
    ]

    # 최신 → 과거 순
    for i in range(len(tags) - 1, -1, -1):
        prev = tags[i - 1] if i > 0 else None
        notes = build_version_notes(tags[i], prev)
        rendered = render_version(notes)
        if rendered:
            lines.append(rendered)

    return "\n".join(lines)


# ── CLI ───────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="릴리즈 노트 자동 생성")
    parser.add_argument("tag", nargs="?", help="대상 태그 (기본: 최신)")
    parser.add_argument("--full", action="store_true", help="전체 CHANGELOG.md 생성")
    parser.add_argument("--format", choices=["changelog", "github"], default="changelog",
                        help="출력 형식")
    parser.add_argument("--output", "-o", help="출력 파일 (기본: stdout)")
    args = parser.parse_args()

    tags = get_sorted_tags()
    if not tags:
        print("태그가 없습니다.", file=sys.stderr)
        sys.exit(1)

    if args.full:
        result = render_full_changelog(tags)
    else:
        target = args.tag or tags[-1]
        if target not in tags:
            print(f"태그 '{target}'을 찾을 수 없습니다.", file=sys.stderr)
            sys.exit(1)
        idx = tags.index(target)
        prev = tags[idx - 1] if idx > 0 else None
        notes = build_version_notes(target, prev)
        result = render_version(notes, fmt=args.format)

    if args.output:
        Path(args.output).write_text(result, encoding="utf-8")
        print(f"✅ {args.output} 생성 완료")
    else:
        print(result)


if __name__ == "__main__":
    main()
