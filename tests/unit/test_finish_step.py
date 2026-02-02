from types import SimpleNamespace

import pytest
from PySide6.QtWidgets import QWizard, QWizardPage

from data_graph_studio.core.profile import GraphSetting
from data_graph_studio.ui.wizards.finish_step import FinishStep


class DummyPreview:
    def __init__(self, columns):
        self.columns = columns


class DummyParsingPage(QWizardPage):
    def __init__(self, settings, preview):
        super().__init__()
        self._settings = settings
        self._preview = preview

    def get_parsing_settings(self):
        return self._settings

    def get_preview_df(self):
        return self._preview


class DummyGraphPage(QWizardPage):
    def __init__(self, setting):
        super().__init__()
        self._setting = setting

    def get_graph_setting(self):
        return self._setting


@pytest.mark.parametrize("has_header", [True])
def test_finish_step_renders_summary(qtbot, tmp_path, has_header):
    file_path = tmp_path / "sales_data.csv"
    file_path.write_text("a,b,c,d\n1,2,3,4\n", encoding="utf-8")
    size_bytes = file_path.stat().st_size

    parsing_settings = SimpleNamespace(
        file_path=str(file_path),
        encoding="utf-8",
        delimiter=",",
        has_header=has_header,
        excluded_columns=["b", "d"],
    )

    preview = DummyPreview(["a", "b", "c", "d"])

    graph_setting = GraphSetting(
        id="setting-1",
        name="Default",
        dataset_id="dataset-1",
        chart_type="line",
        x_column="date",
        value_columns=("sales", "profit"),
        group_columns=("region",),
        hover_columns=("name", "id"),
    )

    wizard = QWizard()
    wizard.addPage(DummyParsingPage(parsing_settings, preview))
    wizard.addPage(DummyGraphPage(graph_setting))

    finish_step = FinishStep()
    wizard.addPage(finish_step)

    qtbot.addWidget(wizard)

    finish_step.initializePage()

    assert finish_step.get_project_name() == "sales_data"
    assert "sales_data.csv" in finish_step._file_info_label.text()
    assert f"{size_bytes} B" in finish_step._file_info_label.text()

    parsing_text = finish_step._parsing_info_label.text()
    assert "utf-8" in parsing_text
    assert "," in parsing_text
    assert "헤더: 있음" in parsing_text

    assert finish_step._columns_info_label.text() == "4개 (2개 제외)"
    assert finish_step._chart_type_label.text() == "line"
    assert finish_step._x_axis_label.text() == "date"
    assert finish_step._y_axis_label.text() == "sales, profit"
    assert finish_step._group_label.text() == "region"
    assert finish_step._hover_label.text() == "name, id"


def test_finish_step_keeps_existing_project_name(qtbot, tmp_path):
    file_path = tmp_path / "sample.csv"
    file_path.write_text("a,b\n", encoding="utf-8")

    parsing_settings = SimpleNamespace(
        file_path=str(file_path),
        encoding="utf-8",
        delimiter=",",
        has_header=True,
        excluded_columns=[],
    )
    preview = DummyPreview(["a", "b"])

    graph_setting = GraphSetting(
        id="setting-2",
        name="Default",
        dataset_id="dataset-1",
        chart_type="bar",
        x_column="a",
        value_columns=("b",),
    )

    wizard = QWizard()
    wizard.addPage(DummyParsingPage(parsing_settings, preview))
    wizard.addPage(DummyGraphPage(graph_setting))

    finish_step = FinishStep()
    wizard.addPage(finish_step)

    qtbot.addWidget(wizard)

    finish_step._project_name_input.setText("Custom")
    finish_step.initializePage()

    assert finish_step.get_project_name() == "Custom"
