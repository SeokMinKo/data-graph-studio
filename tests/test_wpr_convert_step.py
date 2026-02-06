from data_graph_studio.ui.wizards.wpr_convert_step import is_wpr_file, build_wpr_output_path


def test_is_wpr_file() -> None:
    assert is_wpr_file("/tmp/test.etl") is True
    assert is_wpr_file("/tmp/test.wpr") is True
    assert is_wpr_file("/tmp/test.csv") is False


def test_build_wpr_output_path() -> None:
    out = build_wpr_output_path("/tmp/sample.etl")
    assert out.endswith("sample_wpr.parquet")
