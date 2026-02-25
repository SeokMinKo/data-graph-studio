import polars as pl

from data_graph_studio.ui.panels._table_column_mixin import _TableColumnMixin


def test_build_split_dataframe_uses_python_regex_behavior():
    df = pl.DataFrame({"raw": ["id=101", "id=202", "nomatch"]})

    # Python re supports lookbehind; this should match first two rows.
    pattern = r"(?<=id=)(\d+)"
    result = _TableColumnMixin._build_split_dataframe(object(), df, "raw", pattern, {1: "id"})

    assert result.columns == ["raw", "id"]
    assert result["id"].to_list() == ["101", "202", None]
