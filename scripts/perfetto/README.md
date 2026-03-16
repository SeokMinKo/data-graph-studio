# Perfetto trace utilities

권장 진입점이다. standalone 도구는 `tools/perfetto/`에 있고,
이 디렉터리는 더 눈에 띄는 실행 경로를 제공한다.

## Commands

```bash
python scripts/perfetto/merge_perfetto_ptftrace_to_csv.py "traces/*.ptftrace" --output merged.csv
python scripts/perfetto/convert_merged_perfetto_csv_to_systrace_txt.py merged.csv --output merged_systrace.txt --include-source-comments
python scripts/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py "traces/*.ptftrace" --csv-output merged.csv --txt-output merged_systrace.txt
```

## Canonical implementation

- `tools/perfetto/merge_perfetto_ptftrace_to_csv.py`
- `tools/perfetto/convert_merged_perfetto_csv_to_systrace_txt.py`
- `tools/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py`

Windows에서는 `trace_processor_shell.exe`를 `tools/perfetto/` 폴더에 같이 두면 자동 인식한다.
