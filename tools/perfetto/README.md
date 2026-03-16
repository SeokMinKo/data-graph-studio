# Perfetto standalone tools

DGS UI와 무관하게 CLI 단독 실행 가능한 스크립트 묶음이다.

## Files

- `merge_perfetto_ptftrace_to_csv.py`
- `convert_merged_perfetto_csv_to_systrace_txt.py`
- `merge_perfetto_ptftrace_to_systrace_txt.py`

## Examples

```bash
python tools/perfetto/merge_perfetto_ptftrace_to_csv.py "traces/*.ptftrace" --output merged.csv
python tools/perfetto/convert_merged_perfetto_csv_to_systrace_txt.py merged.csv --output merged_systrace.txt --include-source-comments
python tools/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py "traces/*.ptftrace" --csv-output merged.csv --txt-output merged_systrace.txt
```
