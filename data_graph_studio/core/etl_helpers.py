"""
ETL 바이너리 파싱 헬퍼.

Windows ETW (Event Tracing for Windows) .etl 바이너리 파일을
etl-parser 라이브러리를 사용해 Polars DataFrame으로 변환한다.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import polars as pl

logger = logging.getLogger(__name__)

try:
    from etl.etl import IEtlFileObserver, build_from_stream
    from etl.system import System

    HAS_ETL_PARSER = True
except ImportError:
    HAS_ETL_PARSER = False


def is_binary_etl(path: str) -> bool:
    """ETL 파일이 바이너리인지 확인한다.

    Args:
        path: 파일 경로.

    Returns:
        바이너리이면 True.
    """
    try:
        with open(path, "rb") as f:
            header = f.read(512)
    except Exception:
        return False
    if not header:
        return False
    null_count = header.count(b"\x00")
    non_printable_count = sum(1 for b in header if b < 32 and b not in (9, 10, 13))
    is_text = null_count == 0 and (
        non_printable_count / len(header) < 0.05 if len(header) > 0 else True
    )
    return not is_text


def parse_etl_binary(path: str) -> pl.DataFrame:
    """etl-parser로 바이너리 ETL 파일을 파싱한다.

    Args:
        path: ETL 파일 경로.

    Returns:
        파싱된 DataFrame.

    Raises:
        ImportError: etl-parser 미설치.
        ValueError: 파싱 실패 또는 빈 결과.
    """
    if not HAS_ETL_PARSER:
        raise ImportError("etl-parser 라이브러리가 설치되지 않았습니다.")

    FILETIME_EPOCH = datetime(1601, 1, 1)

    class _EtlEventCollector(IEtlFileObserver):
        def __init__(self):
            self.events: List[Dict[str, Any]] = []
            self.etw_events: List[Dict[str, Any]] = []
            self._error_count = 0

        def _filetime_to_datetime(self, filetime_val) -> Optional[datetime]:
            try:
                if filetime_val is None or filetime_val <= 0:
                    return None
                return FILETIME_EPOCH + timedelta(microseconds=filetime_val // 10)
            except (OverflowError, OSError, ValueError):
                return None

        def on_system_trace(self, event):
            try:
                system = System(event)
                mof = system.get_mof()
                event_def = mof.get_event_definition()
                record = {
                    "Timestamp": self._filetime_to_datetime(
                        getattr(event, "timestamp", None)
                    ),
                    "EventType": str(event_def) if event_def else "Unknown",
                    "ProcessID": getattr(event, "process_id", None),
                    "ThreadID": getattr(event, "thread_id", None),
                    "DiskNumber": getattr(mof.source, "DiskNumber", None),
                    "TransferSize": getattr(mof.source, "TransferSize", None),
                    "ByteOffset": getattr(mof.source, "ByteOffset", None),
                    "IrpFlags": getattr(mof.source, "IrpFlags", None),
                    "HighResResponseTime": getattr(
                        mof.source,
                        "HighResResponseTime",
                        getattr(mof.source, "HighResponseTime", None),
                    ),
                    "IssuingThreadId": getattr(mof.source, "IssuingThreadId", None),
                    "Source": "SystemTrace",
                }
                self.events.append(record)
            except Exception:
                self._error_count += 1

        def on_event_record(self, event):
            try:
                try:
                    msg = event.parse_etw()
                except Exception:
                    try:
                        msg = event.parse_tracelogging()
                    except Exception:
                        return
                if msg is None:
                    return
                record = {
                    "Timestamp": self._filetime_to_datetime(
                        getattr(event, "timestamp", None)
                    ),
                    "EventType": str(
                        getattr(msg, "name", getattr(msg, "opcode_name", "ETW"))
                    ),
                    "ProcessID": getattr(event, "process_id", None),
                    "ThreadID": getattr(event, "thread_id", None),
                    "DiskNumber": None,
                    "TransferSize": None,
                    "ByteOffset": None,
                    "IrpFlags": None,
                    "HighResResponseTime": None,
                    "IssuingThreadId": None,
                    "Source": "ETW",
                }
                if hasattr(msg, "properties"):
                    for key, val in msg.properties.items():
                        if key not in record:
                            record[key] = str(val) if val is not None else None
                self.etw_events.append(record)
            except Exception:
                self._error_count += 1

        def on_perfinfo_trace(self, event):
            pass

        def on_trace_record(self, event):
            pass

        def on_win_trace(self, event):
            pass

    try:
        with open(path, "rb") as f:
            raw_data = f.read()
    except Exception as e:
        raise ValueError(f"ETL 파일 읽기 실패: {e}")

    if not raw_data:
        raise ValueError("ETL 파일이 비어 있습니다.")

    collector = _EtlEventCollector()
    try:
        reader = build_from_stream(raw_data)
        reader.parse(collector)
    except Exception as e:
        raise ValueError(f"ETL 바이너리 파싱 실패: {e}")

    all_events = collector.events + collector.etw_events
    if not all_events:
        raise ValueError("ETL 파일에서 파싱 가능한 이벤트를 찾지 못했습니다.")

    base_columns = [
        "Timestamp",
        "EventType",
        "ProcessID",
        "ThreadID",
        "DiskNumber",
        "TransferSize",
        "ByteOffset",
        "IrpFlags",
        "HighResResponseTime",
        "IssuingThreadId",
        "Source",
    ]
    extra_columns: set = set()
    for evt in all_events:
        for key in evt:
            if key not in base_columns:
                extra_columns.add(key)

    all_columns = base_columns + sorted(extra_columns)
    df_dict: Dict[str, list] = {col: [] for col in all_columns}
    for evt in all_events:
        for col in all_columns:
            df_dict[col].append(evt.get(col, None))

    df = pl.DataFrame(df_dict)

    if "Timestamp" in df.columns:
        try:
            df = df.with_columns(pl.col("Timestamp").cast(pl.Datetime("us")))
        except Exception:
            pass

    numeric_cols = [
        "ProcessID",
        "ThreadID",
        "DiskNumber",
        "TransferSize",
        "ByteOffset",
        "IrpFlags",
        "HighResResponseTime",
        "IssuingThreadId",
    ]
    for col in numeric_cols:
        if col in df.columns:
            try:
                df = df.with_columns(pl.col(col).cast(pl.Int64))
            except Exception:
                pass

    non_null_cols = [col for col in df.columns if df[col].null_count() < len(df)]
    if non_null_cols:
        df = df.select(non_null_cols)

    return df
