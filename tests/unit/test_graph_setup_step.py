import polars as pl
import pytest

from PySide6.QtWidgets import QApplication, QWizard, QWizardPage
from PySide6.QtCore import Qt

from data_graph_studio.ui.wizards.graph_setup_step import GraphSetupStep


# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])


class DummyParsingStep(QWizardPage):
    def __init__(self, df):
        super().__init__()
        self._df = df

    def get_preview_df(self):
        return self._df


@pytest.fixture
def sample_df():
    return pl.DataFrame({
        "date": [1, 2, 3],
        "sales": [10, 20, 30],
        "profit": [3, 6, 9],
    })


def _create_wizard_with_step(graph_step: GraphSetupStep, df):
    wizard = QWizard()
    parsing_step = DummyParsingStep(df)
    wizard.addPage(parsing_step)
    wizard.addPage(graph_step)
    wizard.dataset_id = "ds-1"
    return wizard


def test_initialize_page_populates_columns(sample_df):
    step = GraphSetupStep()
    _create_wizard_with_step(step, sample_df)

    step.initializePage()

    assert step.x_column_combo.count() == len(sample_df.columns) + 1
    assert step.y_columns_list.count() == len(sample_df.columns)
    assert step.hover_columns_list.count() == len(sample_df.columns)
    assert step.group_column_combo.count() == len(sample_df.columns) + 1


def test_validate_page_requires_x_and_y(sample_df):
    step = GraphSetupStep()
    _create_wizard_with_step(step, sample_df)

    step.initializePage()
    assert step.validatePage() is False

    step.x_column_combo.setCurrentIndex(1)
    item = step.y_columns_list.item(0)
    item.setCheckState(Qt.Checked)

    assert step.validatePage() is True


def test_get_graph_setting(sample_df):
    step = GraphSetupStep()
    _create_wizard_with_step(step, sample_df)

    step.initializePage()
    step.chart_type_combo.setCurrentText("Line")
    step.x_column_combo.setCurrentIndex(1)

    step.y_columns_list.item(1).setCheckState(Qt.Checked)
    step.group_column_combo.setCurrentIndex(2)
    step.hover_columns_list.item(0).setCheckState(Qt.Checked)

    setting = step.get_graph_setting()

    assert setting.dataset_id == "ds-1"
    assert setting.chart_type == "Line"
    assert setting.x_column == sample_df.columns[0]
    assert setting.value_columns == (sample_df.columns[1],)
    assert setting.group_columns == (sample_df.columns[1],)
    assert setting.hover_columns == (sample_df.columns[0],)
