from data_graph_studio.core.parsing import ParsingSettings
from data_graph_studio.core.data_engine import FileType, DelimiterType


def test_parsing_settings_defaults():
    settings = ParsingSettings(
        file_path="sample.csv",
        file_type=FileType.CSV,
        excluded_columns=None,
        etl_selected_processes=None,
    )

    assert settings.encoding == "utf-8"
    assert settings.delimiter == ","
    assert settings.delimiter_type == DelimiterType.COMMA
    assert settings.has_header is True
    assert settings.skip_rows == 0
    assert settings.comment_char == ""
    assert settings.excluded_columns == []
    assert settings.etl_selected_processes == []
