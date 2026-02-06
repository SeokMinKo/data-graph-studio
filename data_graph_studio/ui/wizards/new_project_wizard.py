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
    from .wpr_convert_step import WprConvertStep, is_wpr_file
except Exception:  # pragma: no cover

    def is_wpr_file(_: str) -> bool:
        return False

    class WprConvertStep(QWizardPage):
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
        self.current_file_path = file_path
        self._parsing_settings = None
        self._graph_setting = None
        self._preview_df = None

        self.setWindowTitle("New Project Wizard")
        self.resize(1500, 800)
        self.setMinimumSize(1200, 600)

        if is_wpr_file(file_path):
            self.addPage(WprConvertStep(file_path))

        self._parsing_step = ParsingStep(file_path)
        self._graph_step = GraphSetupStep()
        self._finish_step = FinishStep()
        self.addPage(self._parsing_step)
        self.addPage(self._graph_step)
        self.addPage(self._finish_step)

    def cleanupPage(self, page_id: int) -> None:
        """마법사 취소 시 cleanup"""
        self._preview_df = None
        super().cleanupPage(page_id)

    def set_current_file_path(self, file_path: str) -> None:
        self.current_file_path = file_path
        if hasattr(self, "_parsing_step"):
            self._parsing_step.update_file_path(file_path)
    
    def accept(self) -> None:
        """마법사 완료 (Finish 버튼)"""
        # 각 단계에서 설정 수집
        parsing_page = self._parsing_step
        graph_page = self._graph_step
        finish_page = self._finish_step
        
        parsing_settings = None
        graph_setting = None
        preview_df = None
        project_name = None
        
        if parsing_page and hasattr(parsing_page, "get_parsing_settings"):
            parsing_settings = parsing_page.get_parsing_settings()
        
        if parsing_page and hasattr(parsing_page, "get_preview_df"):
            preview_df = parsing_page.get_preview_df()
        
        if graph_page and hasattr(graph_page, "get_graph_setting"):
            graph_setting = graph_page.get_graph_setting()
        
        if finish_page and hasattr(finish_page, "get_project_name"):
            project_name = finish_page.get_project_name()
        
        # 시그널 발생
        result = {
            'parsing_settings': parsing_settings,
            'graph_setting': graph_setting,
            'preview_df': preview_df,
            'project_name': project_name,
        }
        self.project_created.emit(result)
        
        super().accept()
