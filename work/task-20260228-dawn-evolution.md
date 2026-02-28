# Task: 20260228 dawn evolution

## Goal
Improve Data Graph Studio for Windows offline installer stability, runtime error prevention, and UX recovery guidance.

## Scope
- updater safety guards around installer asset metadata/download path
- update-check controller error handling UX
- tests for new validation behavior

## Constraints
- small batches
- run: ruff F821 + py_compile + pytest subset
- commit and push

## Definition of Done
- Code changes merged in master
- Required validations pass

## Batches
1. updater metadata/download validation + tests ✅
2. help controller runtime/UX error-path fix ✅
3. installer launch path guard + tests ✅

## Progress Log
- preflight complete: python3/pytest/ruff versions checked
- batch 1 complete: URL/filename guards in updater + 2 tests added
- batch 2 complete: fixed QMessageBox parent bug (`self` -> `self.w`) + actionable recovery guide on generic failures

## Evidence
- `ruff check --select F821 data_graph_studio/ui/controllers/help_controller.py data_graph_studio/core/updater.py tests/test_updater_validation.py`
- `python3 -m py_compile data_graph_studio/ui/controllers/help_controller.py data_graph_studio/core/updater.py`
- `pytest -q tests/test_updater_validation.py` (5 passed)

- batch 3 complete: added launch-time installer path validation (.exe + file exists + MZ header) and Windows launcher tests
