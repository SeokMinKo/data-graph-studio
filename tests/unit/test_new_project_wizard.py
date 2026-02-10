from PySide6.QtWidgets import QApplication

# Ensure QApplication exists
app = QApplication.instance()
if not app:
    app = QApplication([])

from data_graph_studio.ui.wizards.new_project_wizard import NewProjectWizard


def test_wizard_initialization_adds_pages():
    wizard = NewProjectWizard("/tmp/sample.csv")

    page_ids = list(wizard.pageIds())
    assert len(page_ids) == 2
    assert wizard.page(page_ids[0]) is not None
    assert wizard.page(page_ids[1]) is not None


def test_wizard_cleanup_clears_preview_df():
    wizard = NewProjectWizard("/tmp/sample.csv")
    wizard._preview_df = object()

    wizard.cleanupPage(0)

    assert wizard._preview_df is None
