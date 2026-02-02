"""New project wizard."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWizard, QWizardPage

try:
    from .parsing_step import ParsingStep
except Exception:  # pragma: no cover - placeholder until implemented

    class ParsingStep(QWizardPage):
        def __init__(self, file_path: str, parent=None):
            super().__init__(parent)
            self.file_path = file_path


try:
    from .graph_setup_step import GraphSetupStep
except Exception:  # pragma: no cover - placeholder until implemented

    class GraphSetupStep(QWizardPage):
        def __init__(self, parent=None):
            super().__init__(parent)


try:
    from .finish_step import FinishStep
except Exception:  # pragma: no cover - placeholder until implemented

    class FinishStep(QWizardPage):
        def __init__(self, parent=None):
            super().__init__(parent)


class NewProjectWizard(QWizard):
    """새 프로젝트 마법사"""

    project_created = Signal(object)

    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        self.file_path = file_path
        self._parsing_settings = None
        self._graph_setting = None
        self._preview_df = None

        self.addPage(ParsingStep(file_path))
        self.addPage(GraphSetupStep())
        self.addPage(FinishStep())

    def cleanupPage(self, page_id: int) -> None:
        """마법사 취소 시 cleanup"""
        self._preview_df = None
        super().cleanupPage(page_id)
