"""
Parsing settings for file import.
"""

from dataclasses import dataclass, field
from typing import Optional, List

from .data_engine import FileType, DelimiterType


@dataclass
class ParsingSettings:
    """파싱 설정"""

    file_path: str
    file_type: FileType
    encoding: str = "utf-8"
    delimiter: str = ","
    delimiter_type: DelimiterType = DelimiterType.COMMA
    regex_pattern: str = ""
    has_header: bool = True
    skip_rows: int = 0
    comment_char: str = ""
    sheet_name: Optional[str] = None
    excluded_columns: List[str] = None  # 제외할 컬럼 목록
    # ETL specific settings
    etl_converted_path: Optional[str] = None  # Path to converted CSV from ETL
    etl_selected_processes: List[str] = field(default_factory=list)  # Selected processes

    def __post_init__(self):
        if self.excluded_columns is None:
            self.excluded_columns = []
        if self.etl_selected_processes is None:
            self.etl_selected_processes = []
