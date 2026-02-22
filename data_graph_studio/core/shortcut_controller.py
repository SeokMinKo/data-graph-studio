"""
ShortcutController — Feature 7: 키보드 단축키

기존 ShortcutManager를 래핑/확장하여:
- 단축키 커스터마이징 + 영속화 (JSON)
- 충돌 감지
- macOS 시스템 단축키 충돌 검토
- PRD FR-7.1 ~ FR-7.6 구현
"""

import json
import os
import logging
from typing import Dict, List, Optional, Callable, Union

from PySide6.QtGui import QKeySequence

from ..ui.shortcuts import ShortcutManager, Shortcut, ShortcutCategory

logger = logging.getLogger(__name__)

# macOS 시스템 단축키 목록 (Cmd = Meta in Qt)
# 이 키 조합들은 macOS가 시스템 레벨에서 가로채므로 앱에서 사용하면 안 됨
MACOS_SYSTEM_SHORTCUTS = {
    "Meta+H",       # Hide app
    "Meta+M",       # Minimize window
    "Meta+Q",       # Quit app
    "Meta+W",       # Close window
    "Meta+D",       # Dock / Show Desktop
    "Meta+L",       # Go to address bar (Finder/Safari)
    "Meta+Tab",     # App switcher
    "Meta+Space",   # Spotlight
    "Meta+,",       # Preferences
    "Meta+N",       # New window (some apps)
    "Meta+`",       # Cycle windows
    "Ctrl+H",       # Also mapped for Cmd+H on macOS
    "Ctrl+M",
    "Ctrl+Q",
    "Ctrl+W",
    "Ctrl+D",
    "Ctrl+L",
    "Ctrl+Tab",
    "Ctrl+Space",
    "Ctrl+,",
}

# 위 목록을 정규화해서 빠른 조회를 위한 세트
_NORMALIZED_SYSTEM_SHORTCUTS = set()


def _normalize_key_string(key_str: str) -> str:
    """키 문자열을 정규화 (대소문자, 순서 통일)"""
    if not key_str:
        return ""
    # QKeySequence를 통해 정규화
    try:
        seq = QKeySequence(key_str)
        return seq.toString()
    except Exception:
        return key_str


def _init_system_shortcuts():
    """시스템 단축키 목록 초기화 (정규화)"""
    global _NORMALIZED_SYSTEM_SHORTCUTS
    if _NORMALIZED_SYSTEM_SHORTCUTS:
        return
    for shortcut_str in MACOS_SYSTEM_SHORTCUTS:
        normalized = _normalize_key_string(shortcut_str)
        if normalized:
            _NORMALIZED_SYSTEM_SHORTCUTS.add(normalized)
        # 원본도 추가 (정규화 실패 대비)
        _NORMALIZED_SYSTEM_SHORTCUTS.add(shortcut_str)


class ShortcutController:
    """
    단축키 컨트롤러

    기존 ShortcutManager를 래핑하여 추가 기능 제공:
    - 설정 영속화 (JSON 파일)
    - 충돌 감지 (앱 내 + macOS 시스템)
    - 단축키 커스터마이징 + 유효성 검증
    """

    def __init__(self, config_path: Optional[str] = None):
        self._manager = ShortcutManager()
        self._config_path = config_path or self._default_config_path()
        _init_system_shortcuts()

    @staticmethod
    def _default_config_path() -> str:
        """기본 설정 파일 경로"""
        return os.path.join(
            os.path.expanduser("~"),
            ".data_graph_studio",
            "shortcuts.json"
        )

    @property
    def manager(self) -> ShortcutManager:
        """내부 ShortcutManager 접근"""
        return self._manager

    # ==================== 단축키 등록 (PRD FR-7.1) ====================

    def register_defaults(self):
        """PRD FR-7.1 기본 단축키 등록"""
        m = self._manager

        # File
        m.register("file.open", "Open File", "Ctrl+O", ShortcutCategory.FILE,
                    description="파일 열기")
        m.register("file.save", "Save Profile", "Ctrl+S", ShortcutCategory.FILE,
                    description="프로파일 저장")
        m.register("file.save_as", "Save As", "Ctrl+Shift+S", ShortcutCategory.FILE,
                    description="다른 이름으로 저장")
        m.register("file.export", "Export", "Ctrl+E", ShortcutCategory.FILE,
                    description="내보내기 다이얼로그")

        # Edit
        m.register("edit.undo", "Undo", "Ctrl+Z", ShortcutCategory.EDIT,
                    description="실행 취소")
        m.register("edit.redo", "Redo", "Ctrl+Shift+Z", ShortcutCategory.EDIT,
                    description="다시 실행")
        m.register("edit.annotation_mode", "Annotation Mode", "Ctrl+Shift+A",
                    ShortcutCategory.EDIT,
                    description="주석 모드 토글")

        # View
        m.register("view.dashboard_toggle", "Dashboard Mode", "Ctrl+Shift+D",
                    ShortcutCategory.VIEW,
                    description="대시보드 모드 토글 (macOS Dock 충돌 회피)")
        m.register("view.streaming_toggle", "Live Streaming", "Ctrl+Shift+L",
                    ShortcutCategory.VIEW,
                    description="실시간 스트리밍 토글 (macOS 주소바 충돌 회피)")
        m.register("view.theme_toggle", "Toggle Theme", "Ctrl+T",
                    ShortcutCategory.VIEW,
                    description="테마 토글")
        m.register("view.annotation_panel", "Annotation Panel", "Ctrl+Shift+B",
                    ShortcutCategory.VIEW,
                    description="주석 패널 토글")
        m.register("view.fullscreen", "Fullscreen", "F11",
                    ShortcutCategory.VIEW,
                    description="전체 화면 토글")

        # Graph
        m.register("graph.pan_space", "Pan Mode (Space)", "Space",
                    ShortcutCategory.GRAPH,
                    description="차트 팬 모드 (텍스트 입력 중 비활성화)")

        # Data
        m.register("data.column_create", "Create Column", "Ctrl+K",
                    ShortcutCategory.DATA,
                    description="컬럼 생성 다이얼로그")

        # Dashboard (Cmd+1~9)
        for i in range(1, 10):
            m.register(
                f"dashboard.cell_{i}",
                f"Focus Cell {i}",
                f"Ctrl+{i}",
                ShortcutCategory.VIEW,
                description=f"대시보드 셀 {i} 포커스"
            )

        # Help
        m.register("help.shortcuts", "Keyboard Shortcuts", "Ctrl+/",
                    ShortcutCategory.HELP,
                    description="단축키 도움말 표시")

    # ==================== 조회 ====================

    def get_shortcut(self, shortcut_id: str) -> Optional[Shortcut]:
        """단축키 조회"""
        return self._manager.get(shortcut_id)

    def list_all(self) -> List[Shortcut]:
        """전체 단축키 목록"""
        return self._manager.list_all()

    def get_shortcuts_by_category(self) -> Dict[str, List[Shortcut]]:
        """카테고리별 단축키 그룹핑"""
        result = {}
        for category in ShortcutCategory:
            shortcuts = self._manager.list_by_category(category)
            if shortcuts:
                result[category.value] = shortcuts
        return result

    def get_cheatsheet(self) -> Dict[str, List[Dict]]:
        """치트시트 생성 (위임)"""
        return self._manager.get_cheatsheet()

    def get_customized(self) -> Dict[str, str]:
        """커스터마이징된 단축키 목록"""
        return self._manager._customized.copy()

    # ==================== 콜백 연결 ====================

    def connect(self, shortcut_id: str, callback: Callable):
        """콜백 연결"""
        self._manager.connect(shortcut_id, callback)

    def disconnect(self, shortcut_id: str):
        """콜백 연결 해제"""
        self._manager.disconnect(shortcut_id)

    def trigger(self, shortcut_id: str):
        """단축키 트리거"""
        self._manager.trigger(shortcut_id)

    # ==================== 커스터마이징 (FR-7.3) ====================

    def set_custom_keys(
        self, shortcut_id: str, keys: str, force: bool = False
    ) -> bool:
        """
        단축키 키 조합 변경

        Args:
            shortcut_id: 단축키 ID
            keys: 새 키 조합 문자열
            force: 충돌 무시

        Returns:
            True: 성공, False: 실패 (잘못된 키 조합)
        """
        if not keys or not keys.strip():
            return False

        # QKeySequence 유효성 확인
        seq = QKeySequence(keys)
        if seq.isEmpty():
            return False

        shortcut = self._manager.get(shortcut_id)
        if shortcut is None:
            return False

        self._manager.set_keys(shortcut_id, keys)
        return True

    def reset_shortcut(self, shortcut_id: str):
        """단일 단축키 초기화"""
        self._manager.reset(shortcut_id)

    def reset_all(self):
        """전체 단축키 초기화"""
        self._manager.reset_all()

    # ==================== 충돌 감지 (FR-7.4) ====================

    def check_conflict(self, keys: Union[str, QKeySequence]) -> Optional[Shortcut]:
        """
        키 조합 충돌 확인

        Returns:
            충돌하는 Shortcut 또는 None
        """
        return self._manager.check_conflict(keys)

    def check_conflict_for(
        self, shortcut_id: str, keys: Union[str, QKeySequence]
    ) -> Optional[Shortcut]:
        """
        특정 단축키의 키 변경 시 충돌 확인 (자기 자신 제외)

        Returns:
            충돌하는 Shortcut 또는 None
        """
        if isinstance(keys, str):
            keys_seq = QKeySequence(keys)
        else:
            keys_seq = keys

        keys_str = keys_seq.toString()

        for shortcut in self._manager.list_all():
            if shortcut.id == shortcut_id:
                continue
            if shortcut.keys.toString() == keys_str:
                return shortcut

        return None

    # ==================== macOS 시스템 충돌 (FR-7.6) ====================

    def is_macos_system_shortcut(self, keys: Union[str, QKeySequence]) -> bool:
        """
        macOS 시스템 단축키인지 확인

        Qt에서 Cmd는 Meta (macOS) 또는 Ctrl (크로스플랫폼) 키로 매핑됨.
        두 경우 모두 확인.
        """
        if isinstance(keys, QKeySequence):
            keys_str = keys.toString()
        else:
            keys_str = keys

        normalized = _normalize_key_string(keys_str)

        # 직접 매칭
        if normalized in _NORMALIZED_SYSTEM_SHORTCUTS:
            return True
        if keys_str in _NORMALIZED_SYSTEM_SHORTCUTS:
            return True

        # Meta ↔ Ctrl 변환 체크 (macOS에서 Cmd = Meta)
        if "Meta+" in keys_str:
            ctrl_variant = keys_str.replace("Meta+", "Ctrl+")
            ctrl_normalized = _normalize_key_string(ctrl_variant)
            if ctrl_normalized in _NORMALIZED_SYSTEM_SHORTCUTS:
                return True
            if ctrl_variant in _NORMALIZED_SYSTEM_SHORTCUTS:
                return True

        if "Ctrl+" in keys_str:
            meta_variant = keys_str.replace("Ctrl+", "Meta+")
            meta_normalized = _normalize_key_string(meta_variant)
            if meta_normalized in _NORMALIZED_SYSTEM_SHORTCUTS:
                return True
            if meta_variant in _NORMALIZED_SYSTEM_SHORTCUTS:
                return True

        return False

    def get_conflict_warnings(
        self, shortcut_id: str, keys: str
    ) -> List[str]:
        """
        키 변경 시 모든 경고 목록 반환

        Returns:
            경고 메시지 리스트 (빈 리스트 = 경고 없음)
        """
        warnings = []

        # macOS 시스템 충돌 확인
        if self.is_macos_system_shortcut(keys):
            warnings.append(
                f"'{keys}' conflicts with macOS system shortcut. Use anyway?"
            )

        # 앱 내 충돌 확인
        conflict = self.check_conflict_for(shortcut_id, keys)
        if conflict:
            warnings.append(
                f"'{keys}' is already assigned to '{conflict.name}'. Replace?"
            )

        return warnings

    # ==================== 영속화 (FR-7.5) ====================

    def save_config(self) -> bool:
        """
        커스터마이즈된 단축키 설정을 JSON 파일로 저장

        원자적 저장 (temp → rename) 패턴 적용 (PRD §10.3)

        Returns:
            True: 성공, False: 실패
        """
        try:
            data = {
                "version": 1,
                "customized": self._manager._customized.copy()
            }

            # 디렉토리 생성
            config_dir = os.path.dirname(self._config_path)
            if config_dir:
                os.makedirs(config_dir, exist_ok=True)

            # 원자적 저장
            tmp_path = self._config_path + ".tmp"
            try:
                with open(tmp_path, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                    f.flush()
                    os.fsync(f.fileno())
                os.replace(tmp_path, self._config_path)
            except Exception:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)
                raise

            return True
        except Exception as e:
            logger.error("shortcut_controller.save_config_failed", extra={"error": e})
            return False

    def load_config(self) -> bool:
        """
        JSON 파일에서 커스터마이즈된 단축키 설정 로드

        ERR-7.2: 손상된 파일 → 기본값 복원

        Returns:
            True: 성공, False: 실패 (기본값으로 폴백)
        """
        if not os.path.exists(self._config_path):
            return True  # 파일이 없으면 기본값 사용 (성공으로 간주)

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            if not isinstance(data, dict):
                raise ValueError("Invalid config format")

            # 커스터마이즈된 단축키 복원
            customized = data.get("customized", {})
            if isinstance(customized, dict):
                self._manager.from_dict({"customized": customized})

            return True
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            logger.warning("shortcut_controller.config_corrupted", extra={"error": e})
            # ERR-7.2: 기본값으로 복원
            self._manager.reset_all()
            return False
        except Exception as e:
            logger.error("shortcut_controller.load_config_failed", extra={"error": e})
            self._manager.reset_all()
            return False
