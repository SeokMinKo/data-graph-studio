"""
New Project Wizard - 새 프로젝트 마법사
"""

from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QWizard, QWizardPage
from PySide6.QtCore import Signal

from ...core.parsing import ParsingSettings
from ...core.profile import GraphSetting

# Step 페이지 import (아직 없으면 fallback)
try:
    from .parsing_step import ParsingStep
except ImportError:
    ParsingStep = None

try:
    from .graph_setup_step import GraphSetupStep
except ImportError:
    GraphSetupStep = None

try:
    from .finish_step import FinishStep
except ImportError:
    FinishStep = None


class NewProjectWizard(QWizard):
    """
    새 프로젝트 마법사
    
    Step 1: 파싱 설정
    Step 2: 그래프 기본 설정
    Step 3: 완료 (요약 + 프로젝트 이름)
    """
    
    # 프로젝트 생성 완료 시그널
    # dict: {'parsing_settings': ParsingSettings, 'graph_setting': GraphSetting, 
    #        'project_name': str, 'preview_df': DataFrame}
    project_created = Signal(object)
    
    def __init__(self, file_path: str, parent=None):
        super().__init__(parent)
        
        self.file_path = file_path
        self.file_name = Path(file_path).stem
        
        # 내부 상태
        self._parsing_settings: Optional[ParsingSettings] = None
        self._graph_setting: Optional[GraphSetting] = None
        self._preview_df = None
        
        self._setup_ui()
        self._setup_pages()
    
    def _setup_ui(self):
        """UI 설정"""
        self.setWindowTitle(f"New Project - {Path(self.file_path).name}")
        self.setWizardStyle(QWizard.ModernStyle)
        self.setMinimumSize(900, 650)
        self.resize(900, 650)
        
        # 버튼 텍스트
        self.setButtonText(QWizard.BackButton, "< Back")
        self.setButtonText(QWizard.NextButton, "Next >")
        self.setButtonText(QWizard.FinishButton, "Finish")
        self.setButtonText(QWizard.CancelButton, "Cancel")
        
        # 옵션
        self.setOption(QWizard.NoBackButtonOnStartPage, True)
    
    def _setup_pages(self):
        """페이지 설정"""
        # Step 1: 파싱 설정
        if ParsingStep is not None:
            self._parsing_page = ParsingStep(self.file_path)
            self.addPage(self._parsing_page)
        else:
            # Fallback: 빈 페이지
            self._parsing_page = QWizardPage()
            self._parsing_page.setTitle("Step 1: Parsing Settings")
            self._parsing_page.setSubTitle("(ParsingStep not available)")
            self.addPage(self._parsing_page)
        
        # Step 2: 그래프 설정
        if GraphSetupStep is not None:
            self._graph_page = GraphSetupStep()
            self.addPage(self._graph_page)
        else:
            # Fallback: 빈 페이지
            self._graph_page = QWizardPage()
            self._graph_page.setTitle("Step 2: Graph Settings")
            self._graph_page.setSubTitle("(GraphSetupStep not available)")
            self.addPage(self._graph_page)
        
        # Step 3: 완료
        if FinishStep is not None:
            self._finish_page = FinishStep()
            self.addPage(self._finish_page)
        else:
            # Fallback: 빈 페이지
            self._finish_page = QWizardPage()
            self._finish_page.setTitle("Step 3: Finish")
            self._finish_page.setSubTitle("(FinishStep not available)")
            self.addPage(self._finish_page)
    
    def cleanupPage(self, id: int):
        """페이지 cleanup - 메모리 해제"""
        super().cleanupPage(id)
        # 마법사 취소 시 미리보기 데이터 해제
        if id == 0:  # 파싱 페이지
            self._preview_df = None
    
    def accept(self):
        """마법사 완료 (Finish 버튼 클릭)"""
        # 각 페이지에서 데이터 수집
        result = {}
        
        # Step 1: 파싱 설정
        if hasattr(self._parsing_page, 'get_parsing_settings'):
            result['parsing_settings'] = self._parsing_page.get_parsing_settings()
        if hasattr(self._parsing_page, 'get_preview_df'):
            result['preview_df'] = self._parsing_page.get_preview_df()
        
        # Step 2: 그래프 설정
        if hasattr(self._graph_page, 'get_graph_setting'):
            result['graph_setting'] = self._graph_page.get_graph_setting()
        
        # Step 3: 프로젝트 이름
        if hasattr(self._finish_page, 'get_project_name'):
            result['project_name'] = self._finish_page.get_project_name()
        else:
            result['project_name'] = self.file_name
        
        # 시그널 emit
        self.project_created.emit(result)
        
        super().accept()
    
    def reject(self):
        """마법사 취소"""
        # 메모리 해제
        self._preview_df = None
        self._parsing_settings = None
        self._graph_setting = None
        
        super().reject()
