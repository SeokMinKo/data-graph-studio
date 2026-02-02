from data_graph_studio.core.parsing import ParsingSettings
from data_graph_studio.core.parsing_utils import ParsingEngine
from data_graph_studio.core.data_engine import FileType, DelimiterType


def _write(tmp_path, name, content, encoding="utf-8"):
    path = tmp_path / name
    path.write_text(content, encoding=encoding)
    return path


def test_detect_encoding_utf8(tmp_path):
    path = _write(tmp_path, "sample.txt", "hello\nworld\n", encoding="utf-8")

    encoding = ParsingEngine.detect_encoding(str(path))

    assert encoding.startswith("utf")


def test_parse_preview_csv(tmp_path):
    path = _write(tmp_path, "sample.csv", "a,b\n1,2\n3,4\n")
    settings = ParsingSettings(
        file_path=str(path),
        file_type=FileType.CSV,
        encoding="utf-8",
        delimiter=",",
        delimiter_type=DelimiterType.COMMA,
        has_header=True,
    )

    df = ParsingEngine.parse_preview(settings, max_rows=100)

    assert list(df.columns) == ["a", "b"]
    assert df.shape == (2, 2)


def test_parse_preview_skip_comment(tmp_path):
    content = "skipme\n# comment\nh1,h2\nv1,v2\n"
    path = _write(tmp_path, "sample.csv", content)
    settings = ParsingSettings(
        file_path=str(path),
        file_type=FileType.CSV,
        encoding="utf-8",
        delimiter=",",
        delimiter_type=DelimiterType.COMMA,
        has_header=True,
        skip_rows=1,
        comment_char="#",
    )

    df = ParsingEngine.parse_preview(settings, max_rows=10)

    assert list(df.columns) == ["h1", "h2"]
    assert df.shape == (1, 2)
    assert df.iloc[0].tolist() == ["v1", "v2"]


def test_parse_full_excluded_columns(tmp_path):
    path = _write(tmp_path, "sample.csv", "a,b,c\n1,2,3\n4,5,6\n")
    settings = ParsingSettings(
        file_path=str(path),
        file_type=FileType.CSV,
        encoding="utf-8",
        delimiter=",",
        delimiter_type=DelimiterType.COMMA,
        has_header=True,
        excluded_columns=["b"],
    )

    df = ParsingEngine.parse_full(settings)

    assert list(df.columns) == ["a", "c"]
    assert df.shape == (2, 2)


def test_parse_preview_regex_delimiter(tmp_path):
    path = _write(tmp_path, "sample.txt", "a b c\n1 2 3\n")
    settings = ParsingSettings(
        file_path=str(path),
        file_type=FileType.TXT,
        encoding="utf-8",
        delimiter=" ",
        delimiter_type=DelimiterType.REGEX,
        regex_pattern=r"\s+",
        has_header=True,
    )

    df = ParsingEngine.parse_preview(settings, max_rows=5)

    assert list(df.columns) == ["a", "b", "c"]
    assert df.iloc[0].tolist() == ["1", "2", "3"]
