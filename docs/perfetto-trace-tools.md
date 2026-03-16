# Perfetto merge / systrace tools

## GitHub summary

This repo now includes a complete Perfetto trace utility flow:

1. Merge multiple `.ptftrace` / `.pftrace` / `.perfetto-trace` files into one CSV via `trace_processor_shell`
2. Convert that merged CSV back into systrace/ftrace-style `.txt`
3. Run the whole pipeline in one command
4. Export Perfetto CSV to systrace text from the DGS UI

## Key commits

- `e75c7eb` Add Perfetto trace merge CSV script
- `a4d90af` Add merged Perfetto CSV to systrace converter
- `47e2e10` Add systrace export flow for merged Perfetto traces
- `31eec5e` Add standalone Perfetto merge and systrace tools

## Main entry points

### Visible wrapper commands
- `scripts/perfetto/merge_perfetto_ptftrace_to_csv.py`
- `scripts/perfetto/convert_merged_perfetto_csv_to_systrace_txt.py`
- `scripts/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py`

### Canonical standalone implementations
- `tools/perfetto/merge_perfetto_ptftrace_to_csv.py`
- `tools/perfetto/convert_merged_perfetto_csv_to_systrace_txt.py`
- `tools/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py`

## Example

```bash
python scripts/perfetto/merge_perfetto_ptftrace_to_systrace_txt.py \
  "traces/*.ptftrace" \
  --csv-output merged.csv \
  --txt-output merged_systrace.txt
```
