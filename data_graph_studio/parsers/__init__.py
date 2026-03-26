"""Parsers package - custom file parsers for DGS."""

from .base import BaseParser, ParserProfile, ParserProfileStore
from .ftrace_parser import FtraceParser
from .graph_preset import GraphPreset, BUILTIN_PRESETS, select_preset
from .perfetto_to_systrace import convert_perfetto_to_systrace

__all__ = [
    "BaseParser",
    "ParserProfile",
    "ParserProfileStore",
    "FtraceParser",
    "GraphPreset",
    "BUILTIN_PRESETS",
    "select_preset",
    "convert_perfetto_to_systrace",
]
