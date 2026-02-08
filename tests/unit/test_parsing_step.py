"""
ParsingStep UI 테스트
"""

from pathlib import Path

import pandas as pd
import pytest

from PySide6.QtWidgets import QApplication

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])

from data_graph_studio.ui.wizards.parsing_step import ParsingStep


def test_parsing_step_ui_rendering():
    """ParsingStep 기본 UI 렌더링"""
    file_path = Path(__file__).resolve().parents[2] / "test_data" / "test_comma.csv"
    step = ParsingStep(str(file_path))
    step.initializePage()

    assert step.preview_table.rowCount() > 0
    assert len(step._column_checkboxes) > 0
    assert step.progress_bar is not None


def test_parsing_step_get_settings():
    """파싱 설정 반환"""
    file_path = Path(__file__).resolve().parents[2] / "test_data" / "test_comma.csv"
    step = ParsingStep(str(file_path))
    step.initializePage()

    settings = step.get_parsing_settings()
    assert settings.file_path == str(file_path)
    assert settings.delimiter == ","


def test_parsing_step_get_preview_df():
    """미리보기 DataFrame 반환"""
    file_path = Path(__file__).resolve().parents[2] / "test_data" / "test_comma.csv"
    step = ParsingStep(str(file_path))
    step.initializePage()

    df = step.get_preview_df()
    assert isinstance(df, pd.DataFrame)
    assert "name" in df.columns
