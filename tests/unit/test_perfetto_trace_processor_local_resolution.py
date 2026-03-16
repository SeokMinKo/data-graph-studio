from __future__ import annotations

import importlib.util
from pathlib import Path

MODULE_PATH = Path(__file__).resolve().parents[2] / "tools" / "perfetto" / "merge_perfetto_ptftrace_to_csv.py"
spec = importlib.util.spec_from_file_location("perfetto_merge_tool", MODULE_PATH)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
spec.loader.exec_module(module)


def test_resolve_trace_processor_prefers_local_exe(monkeypatch, tmp_path: Path) -> None:
    fake_script = tmp_path / "merge_perfetto_ptftrace_to_csv.py"
    fake_script.write_text("# stub", encoding="utf-8")
    fake_exe = tmp_path / "trace_processor_shell.exe"
    fake_exe.write_text("stub", encoding="utf-8")

    class FakeResolvedPath(type(Path())):
        pass

    monkeypatch.setattr(module, "__file__", str(fake_script))
    monkeypatch.setattr(module.shutil, "which", lambda name: None)

    resolved = module.resolve_trace_processor(None)
    assert resolved == str(fake_exe)
