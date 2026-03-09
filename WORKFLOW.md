---
agent:
  max_concurrent: 3
  model: gpt-5.4
  timeout_minutes: 30
hooks:
  before_run: |
    cd /Users/lov2fn/Projects/data-graph-studio
    source .venv/bin/activate 2>/dev/null || true
    pip install -e ".[dev]" -q 2>/dev/null || true
  after_run: |
    python -m pytest tests/ -x -q --tb=short 2>&1 | tail -20
---

# DGS Issue Fix Workflow

You are fixing an issue in Data Graph Studio, a PySide6-based data analysis application.

## Project Structure
- `data_graph_studio/` — main package (Python, PySide6)
- `tests/` — pytest test suite
- `pyproject.toml` — project config

## Rules
1. Use TDD: write/update test first, verify it fails, then implement fix
2. Follow existing code style (Black formatting, type hints)
3. Run `python -m pytest tests/ -x -q` before committing
4. Keep changes minimal and focused on the issue
5. Do not modify unrelated files
