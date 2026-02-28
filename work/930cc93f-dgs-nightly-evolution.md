# Task: DGS nightly evolution (cron 930cc93f)

## Goal
Improve data-graph-studio daily on functionality/stability/design with focus on Windows offline install stability, runtime error prevention, and UX recovery guidance.

## Scope
- Update validation path for Windows updater payloads.
- Improve update failure recovery UX message.
- Add regression tests for offline/mismatched checksum cases.

## Constraints
- Small batches.
- Mandatory checks: preflight (python3/pytest/ruff versions), ruff F821, related py_compile, focused pytest subset.
- Commit and push changes.

## Definition of Done
- Updater rejects malformed checksum payload and mismatched filename checksum.
- Update dialog shows actionable recovery steps and correct parent widget usage.
- Required validation commands pass.
- Commit pushed to origin/master.

## Batches
1. Updater checksum validation hardening + tests.
2. Update error UX improvement in HelpController.
3. Validation + commit/push.

## Progress Log
- [x] Preflight versions checked.
- [x] Batch 1 implemented.
- [x] Batch 2 implemented.
- [x] Batch 3 validation + commit/push.

## Evidence
- python3 --version / pytest --version / ruff --version
- ruff check data_graph_studio tests --select F821
- python3 -m py_compile ...
- pytest tests/test_updater_validation.py
