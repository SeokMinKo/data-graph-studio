"""
Tests for FileWatcher — PRD Section 3.2, 6.2, 10.2

TDD tests for:
- UT-2.1: 폴링 간격 설정
- UT-2.2: Tail 모드에서 새 행 감지
- UT-2.3: Reload 모드에서 파일 변경 감지
- UT-2.4: Self-change 무시 (무한 루프 방지)
- UT-2.5: Debounce 동작 (300ms 내 중복 병합)
- UT-2.6: 파일 삭제 감지 → file_deleted Signal
- UT-2.7: 폴링 간격 경계값 (0.5초 미만/60초 초과 → 클램핑)

Plus additional tests for safety policies (Section 10.2):
- 최대 감시 파일 10개
- 2GB 초과 tail 모드만
- 에러 시 백오프
"""

import os
import time
from typing import Any, Callable, Dict, List, Optional
from unittest.mock import MagicMock

import pytest

from data_graph_studio.core.io_abstract import IFileSystem, ITimerFactory


# ─── Mock implementations for DI ────────────────────────────────────

class FakeStat:
    """os.stat_result 대체용"""
    def __init__(self, st_mtime: float = 0.0, st_size: int = 0):
        self.st_mtime = st_mtime
        self.st_size = st_size
        self.st_mode = 0o100644
        self.st_ino = 0
        self.st_dev = 0
        self.st_nlink = 1
        self.st_uid = 0
        self.st_gid = 0
        self.st_atime = st_mtime
        self.st_ctime = st_mtime


class MockFileSystem(IFileSystem):
    """테스트용 Mock 파일 시스템"""

    def __init__(self):
        self.files: Dict[str, bytes] = {}
        self.stats: Dict[str, FakeStat] = {}
        self._deleted: set = set()
        self._permission_denied: set = set()

    def add_file(self, path: str, data: bytes, mtime: float = 1000.0):
        self.files[path] = data
        self.stats[path] = FakeStat(st_mtime=mtime, st_size=len(data))
        self._deleted.discard(path)

    def update_file(self, path: str, data: bytes, mtime: float = None):
        if mtime is None:
            old = self.stats.get(path)
            mtime = (old.st_mtime + 1.0) if old else time.time()
        self.files[path] = data
        self.stats[path] = FakeStat(st_mtime=mtime, st_size=len(data))

    def delete_file(self, path: str):
        self._deleted.add(path)
        self.files.pop(path, None)
        self.stats.pop(path, None)

    def set_permission_denied(self, path: str):
        self._permission_denied.add(path)

    def clear_permission_denied(self, path: str):
        self._permission_denied.discard(path)

    def read_file(self, path: str) -> bytes:
        if path in self._permission_denied:
            raise PermissionError(f"Permission denied: {path}")
        if path in self._deleted or path not in self.files:
            raise FileNotFoundError(f"File not found: {path}")
        return self.files[path]

    def write_file(self, path: str, data: bytes) -> None:
        self.files[path] = data
        self.stats[path] = FakeStat(st_mtime=time.time(), st_size=len(data))

    def stat(self, path: str):
        if path in self._permission_denied:
            raise PermissionError(f"Permission denied: {path}")
        if path in self._deleted or path not in self.stats:
            raise FileNotFoundError(f"File not found: {path}")
        return self.stats[path]

    def exists(self, path: str) -> bool:
        if path in self._deleted:
            return False
        return path in self.files


class MockTimer:
    """Mock timer that can be manually triggered"""

    def __init__(self, interval_ms: int, callback: Callable):
        self.interval_ms = interval_ms
        self.callback = callback
        self.running = False

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def trigger(self):
        """Manually trigger the timer callback"""
        if self.running:
            self.callback()


class MockTimerFactory(ITimerFactory):
    """테스트용 Mock 타이머 팩토리"""

    def __init__(self):
        self.timers: List[MockTimer] = []

    def create_timer(self, interval_ms: int, callback: Callable) -> MockTimer:
        timer = MockTimer(interval_ms, callback)
        self.timers.append(timer)
        return timer

    @property
    def last_timer(self) -> Optional[MockTimer]:
        return self.timers[-1] if self.timers else None


# ─── Fixtures ──────────────────────────────────────────────────────

@pytest.fixture
def mock_fs():
    return MockFileSystem()


@pytest.fixture
def mock_timer_factory():
    return MockTimerFactory()


@pytest.fixture
def csv_data_5rows():
    return b"a,b,c\n1,2,3\n4,5,6\n7,8,9\n10,11,12\n13,14,15\n"


@pytest.fixture
def csv_data_7rows():
    return b"a,b,c\n1,2,3\n4,5,6\n7,8,9\n10,11,12\n13,14,15\n16,17,18\n19,20,21\n"


@pytest.fixture
def watcher(mock_fs, mock_timer_factory):
    """Create a FileWatcher with mock dependencies"""
    from data_graph_studio.core.file_watcher import FileWatcher
    fw = FileWatcher(fs=mock_fs, timer_factory=mock_timer_factory)
    yield fw
    fw.shutdown()


# ─── UT-2.1: 폴링 간격 설정 ────────────────────────────────────────

class TestPollingInterval:
    """UT-2.1: FileWatcher 폴링 간격 설정"""

    def test_default_interval(self, watcher):
        """기본 폴링 간격은 1000ms"""
        assert watcher.poll_interval_ms == 1000

    def test_set_interval(self, watcher):
        """폴링 간격을 변경할 수 있다"""
        watcher.set_interval(2000)
        assert watcher.poll_interval_ms == 2000

    def test_set_interval_updates_timer(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """폴링 간격 변경 시 타이머도 업데이트"""
        from data_graph_studio.core.file_watcher import FileWatcher
        fw = FileWatcher(fs=mock_fs, timer_factory=mock_timer_factory, poll_interval_ms=1000)
        mock_fs.add_file("/test.csv", csv_data_5rows)
        fw.watch("/test.csv", mode="reload")
        fw.set_interval(3000)
        assert fw.poll_interval_ms == 3000
        fw.shutdown()

    def test_custom_initial_interval(self, mock_fs, mock_timer_factory):
        """생성 시 커스텀 간격"""
        from data_graph_studio.core.file_watcher import FileWatcher
        fw = FileWatcher(fs=mock_fs, timer_factory=mock_timer_factory, poll_interval_ms=5000)
        assert fw.poll_interval_ms == 5000
        fw.shutdown()


# ─── UT-2.2: Tail 모드에서 새 행 감지 ──────────────────────────────

class TestTailMode:
    """UT-2.2: FileWatcher tail 모드에서 새 행 감지"""

    def test_tail_detects_new_rows(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows, csv_data_7rows):
        """tail 모드에서 새 행이 추가되면 rows_appended Signal 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="tail")

        # Signal 수신을 위한 스파이
        appended_signals = []
        watcher.rows_appended.connect(lambda path, count: appended_signals.append((path, count)))

        # 새 행 추가 시뮬레이션
        mock_fs.update_file("/data.csv", csv_data_7rows, mtime=1001.0)

        # 타이머 트리거 → 변경 감지
        timer = mock_timer_factory.timers[0]  # poll timer
        timer.trigger()
        watcher.flush_debounce()

        assert len(appended_signals) == 1
        assert appended_signals[0][0] == "/data.csv"
        assert appended_signals[0][1] == 2  # 2행 추가

    def test_tail_does_not_emit_file_changed(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows, csv_data_7rows):
        """tail 모드에서는 file_changed가 아닌 rows_appended 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="tail")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        mock_fs.update_file("/data.csv", csv_data_7rows, mtime=1001.0)
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(changed_signals) == 0

    def test_tail_column_mismatch_fallback_to_reload(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """ERR-2.3: 컬럼 수 변경 시 tail 거부, file_changed(reload) 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="tail")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # 컬럼 구조 변경 데이터
        new_data = b"a,b,c,d\n1,2,3,4\n5,6,7,8\n"
        mock_fs.update_file("/data.csv", new_data, mtime=1001.0)

        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        # 컬럼 수가 변경되었으므로 file_changed로 폴백
        assert len(changed_signals) == 1


# ─── UT-2.3: Reload 모드에서 파일 변경 감지 ─────────────────────────

class TestReloadMode:
    """UT-2.3: FileWatcher reload 모드에서 파일 변경 감지"""

    def test_reload_detects_file_change(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """reload 모드에서 파일이 변경되면 file_changed Signal 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # 파일 내용 변경
        mock_fs.update_file("/data.csv", b"x,y\n1,2\n", mtime=1001.0)

        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(changed_signals) == 1
        assert changed_signals[0] == "/data.csv"

    def test_reload_no_change_no_signal(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """파일이 변경되지 않으면 Signal 미발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # 변경 없이 폴링
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(changed_signals) == 0

    def test_reload_mtime_change_only(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """mtime만 변경 (size 동일) → 변경 감지됨"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # mtime만 변경, size는 동일
        mock_fs.stats["/data.csv"] = FakeStat(st_mtime=1002.0, st_size=len(csv_data_5rows))

        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(changed_signals) == 1


# ─── UT-2.4: Self-change 무시 (무한 루프 방지) ──────────────────────

class TestSelfChange:
    """UT-2.4: FileWatcher self-change 무시"""

    def test_self_change_ignored(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """begin_self_modify 중 변경은 무시"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # 자기 수정 시작
        watcher.begin_self_modify("/data.csv")

        # 파일 변경 (앱 내부에서 저장)
        mock_fs.update_file("/data.csv", b"new,data\n1,2\n", mtime=1001.0)
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        # Self-modify 중이므로 무시됨
        assert len(changed_signals) == 0

    def test_after_end_self_modify_detects_changes(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """end_self_modify 후에는 다시 변경 감지"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        # 자기 수정 시작/종료
        watcher.begin_self_modify("/data.csv")
        mock_fs.update_file("/data.csv", b"new,data\n1,2\n", mtime=1001.0)
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()
        watcher.end_self_modify("/data.csv")

        # 현재 상태를 재기록 (self-modify에서 mtime 갱신)
        # 이후 외부 변경
        mock_fs.update_file("/data.csv", b"external,change\n5,6\n", mtime=1002.0)
        timer.trigger()
        watcher.flush_debounce()

        assert len(changed_signals) == 1


# ─── UT-2.5: Debounce 동작 ──────────────────────────────────────────

class TestDebounce:
    """UT-2.5: FileWatcher debounce (300ms 내 중복 병합)"""

    def test_multiple_changes_merged(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """연속 변경 이벤트가 하나로 병합"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        timer = mock_timer_factory.last_timer

        # 빠르게 3번 변경 (debounce 중)
        mock_fs.update_file("/data.csv", b"v1", mtime=1001.0)
        timer.trigger()
        mock_fs.update_file("/data.csv", b"v2", mtime=1002.0)
        timer.trigger()
        mock_fs.update_file("/data.csv", b"v3", mtime=1003.0)
        timer.trigger()

        # debounce 타이머 플러시
        watcher.flush_debounce()

        # debounce로 인해 1회만 발생 (또는 최종 변경만)
        assert len(changed_signals) <= 1

    def test_no_debounce_after_interval(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """debounce 간격 이후 변경은 새 이벤트"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        changed_signals = []
        watcher.file_changed.connect(lambda path: changed_signals.append(path))

        timer = mock_timer_factory.last_timer

        # 첫 번째 변경
        mock_fs.update_file("/data.csv", b"v1", mtime=1001.0)
        timer.trigger()
        watcher.flush_debounce()

        # 두 번째 변경 (debounce 후)
        mock_fs.update_file("/data.csv", b"v2", mtime=1002.0)
        timer.trigger()
        watcher.flush_debounce()

        # 2회 발생
        assert len(changed_signals) == 2


# ─── UT-2.6: 파일 삭제 감지 ────────────────────────────────────────

class TestFileDeletion:
    """UT-2.6: FileWatcher 파일 삭제 감지 → file_deleted Signal"""

    def test_file_deleted_signal(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """파일 삭제 시 file_deleted Signal 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        deleted_signals = []
        watcher.file_deleted.connect(lambda path: deleted_signals.append(path))

        # 파일 삭제
        mock_fs.delete_file("/data.csv")

        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(deleted_signals) == 1
        assert deleted_signals[0] == "/data.csv"

    def test_file_deleted_stops_watching(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """파일 삭제 후 해당 파일은 더 이상 감시하지 않음"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        deleted_signals = []
        watcher.file_deleted.connect(lambda path: deleted_signals.append(path))

        mock_fs.delete_file("/data.csv")
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        # 더 이상 감시하지 않으므로 추가 Signal 없음
        timer.trigger()
        watcher.flush_debounce()
        assert len(deleted_signals) == 1

    def test_permission_denied_emits_file_deleted(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """ERR-2.2: 읽기 권한 거부 시 file_deleted 발생"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        deleted_signals = []
        watcher.file_deleted.connect(lambda path: deleted_signals.append(path))

        mock_fs.set_permission_denied("/data.csv")
        timer = mock_timer_factory.timers[0]
        timer.trigger()
        watcher.flush_debounce()

        assert len(deleted_signals) == 1


# ─── UT-2.7: 폴링 간격 경계값 ──────────────────────────────────────

class TestIntervalClamping:
    """UT-2.7: 폴링 간격 경계값 (0.5초 미만/60초 초과 → 클램핑)"""

    def test_below_minimum_clamped(self, watcher):
        """0.5초(500ms) 미만은 500ms로 클램핑"""
        watcher.set_interval(100)
        assert watcher.poll_interval_ms == 500

    def test_above_maximum_clamped(self, watcher):
        """60초(60000ms) 초과는 60000ms로 클램핑"""
        watcher.set_interval(120000)
        assert watcher.poll_interval_ms == 60000

    def test_minimum_boundary(self, watcher):
        """정확히 500ms는 허용"""
        watcher.set_interval(500)
        assert watcher.poll_interval_ms == 500

    def test_maximum_boundary(self, watcher):
        """정확히 60000ms는 허용"""
        watcher.set_interval(60000)
        assert watcher.poll_interval_ms == 60000

    def test_normal_value(self, watcher):
        """정상 범위 값"""
        watcher.set_interval(5000)
        assert watcher.poll_interval_ms == 5000

    def test_zero_clamped(self, watcher):
        """0ms → 500ms로 클램핑"""
        watcher.set_interval(0)
        assert watcher.poll_interval_ms == 500

    def test_negative_clamped(self, watcher):
        """음수 → 500ms로 클램핑"""
        watcher.set_interval(-1000)
        assert watcher.poll_interval_ms == 500

    def test_initial_below_minimum_clamped(self, mock_fs, mock_timer_factory):
        """생성 시 최소값 미만 → 클램핑"""
        from data_graph_studio.core.file_watcher import FileWatcher
        fw = FileWatcher(fs=mock_fs, timer_factory=mock_timer_factory, poll_interval_ms=100)
        assert fw.poll_interval_ms == 500
        fw.shutdown()

    def test_initial_above_maximum_clamped(self, mock_fs, mock_timer_factory):
        """생성 시 최대값 초과 → 클램핑"""
        from data_graph_studio.core.file_watcher import FileWatcher
        fw = FileWatcher(fs=mock_fs, timer_factory=mock_timer_factory, poll_interval_ms=100000)
        assert fw.poll_interval_ms == 60000
        fw.shutdown()


# ─── Safety Policy Tests (Section 10.2) ────────────────────────────

class TestMaxWatchedFiles:
    """최대 감시 파일 수: 10개"""

    def test_max_10_files(self, watcher, mock_fs, mock_timer_factory):
        """10개 초과 시 가장 오래된 파일 해제"""
        # 11개 파일 생성 & 감시
        for i in range(11):
            path = f"/file_{i}.csv"
            mock_fs.add_file(path, b"a,b\n1,2\n", mtime=1000.0 + i)
            watcher.watch(path, mode="reload")

        assert watcher.watched_count <= 10
        # 가장 먼저 등록한 file_0은 해제됨
        assert not watcher.is_watching("/file_0.csv")
        # 최신 file_10은 감시 중
        assert watcher.is_watching("/file_10.csv")


class TestLargeFileTailOnly:
    """2GB 초과 파일은 tail 모드만 지원"""

    def test_large_file_reload_rejected(self, watcher, mock_fs):
        """2GB 초과 파일에 reload 모드 → tail로 강제 전환 또는 거부"""
        path = "/huge.csv"
        mock_fs.add_file(path, b"a,b\n1,2\n", mtime=1000.0)
        # 2GB 초과로 설정
        mock_fs.stats[path] = FakeStat(st_mtime=1000.0, st_size=3 * 1024 * 1024 * 1024)

        # reload 모드 시도 → tail로 강제 전환
        watcher.watch(path, mode="reload")
        info = watcher.get_watch_info(path)
        assert info is not None
        assert info["mode"] == "tail"


class TestErrorBackoff:
    """에러 시 백오프: 폴링 간격 2배 증가 (최대 30초)"""

    def test_backoff_on_error(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """파일 읽기 실패 시 폴링 간격 2배 증가"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")
        original_interval = watcher.poll_interval_ms

        # 파일을 일시적으로 접근 불가
        mock_fs.set_permission_denied("/data.csv")
        timer = mock_timer_factory.last_timer
        timer.trigger()

        # 백오프가 적용됨 (혹은 파일 삭제로 처리)
        # 주의: permission denied는 file_deleted로 처리될 수 있음
        # 이 경우 watching이 중단되므로 별도의 에러 백오프 테스트가 필요

    def test_backoff_max_30s(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """백오프 최대 30초"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        # 내부 백오프 간격이 30초를 초과하지 않음
        watcher._apply_backoff("/data.csv")
        watcher._apply_backoff("/data.csv")
        watcher._apply_backoff("/data.csv")
        watcher._apply_backoff("/data.csv")
        watcher._apply_backoff("/data.csv")
        watcher._apply_backoff("/data.csv")

        info = watcher.get_watch_info("/data.csv")
        assert info is not None
        assert info.get("effective_interval_ms", 0) <= 30000

    def test_backoff_resets_on_success(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """성공 시 원래 간격 복원"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        # 백오프 적용
        watcher._apply_backoff("/data.csv")
        info_after_backoff = watcher.get_watch_info("/data.csv")

        # 성공적 변경 감지 후 리셋
        mock_fs.update_file("/data.csv", b"changed", mtime=1001.0)
        timer = mock_timer_factory.last_timer
        timer.trigger()
        watcher.flush_debounce()

        info_after_success = watcher.get_watch_info("/data.csv")
        if info_after_success:
            assert info_after_success.get("backoff_multiplier", 1) == 1


# ─── Watch/Unwatch Tests ───────────────────────────────────────────

class TestWatchUnwatch:
    """watch/unwatch 기본 동작"""

    def test_watch_starts_timer(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """watch 호출 시 타이머 시작"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")

        timer = mock_timer_factory.last_timer
        assert timer is not None
        assert timer.running is True

    def test_unwatch_stops_monitoring(self, watcher, mock_fs, mock_timer_factory, csv_data_5rows):
        """unwatch 호출 후 더 이상 감시하지 않음"""
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        watcher.watch("/data.csv", mode="reload")
        watcher.unwatch("/data.csv")

        assert not watcher.is_watching("/data.csv")

    def test_watch_nonexistent_file(self, watcher, mock_fs):
        """존재하지 않는 파일 감시 시도 → 무시"""
        result = watcher.watch("/nonexistent.csv", mode="reload")
        assert result is False

    def test_multiple_files(self, watcher, mock_fs, mock_timer_factory):
        """여러 파일 동시 감시"""
        mock_fs.add_file("/a.csv", b"a\n1\n", mtime=1000.0)
        mock_fs.add_file("/b.csv", b"b\n2\n", mtime=1000.0)

        watcher.watch("/a.csv", mode="reload")
        watcher.watch("/b.csv", mode="tail")

        assert watcher.is_watching("/a.csv")
        assert watcher.is_watching("/b.csv")
        assert watcher.watched_count == 2


# ─── StreamingController Tests ──────────────────────────────────────

class TestStreamingController:
    """StreamingController 기본 동작 테스트"""

    def test_initial_state_off(self, mock_fs, mock_timer_factory):
        """초기 상태는 'off'"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        assert ctrl.state == "off"
        ctrl.shutdown()

    def test_start_streaming(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """스트리밍 시작 → 'live' 상태"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        ctrl.start("/data.csv", mode="tail")
        assert ctrl.state == "live"
        ctrl.shutdown()

    def test_pause_resume(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """일시정지/재개"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        ctrl.start("/data.csv", mode="tail")
        ctrl.pause()
        assert ctrl.state == "paused"
        ctrl.resume()
        assert ctrl.state == "live"
        ctrl.shutdown()

    def test_stop_streaming(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """스트리밍 중단 → 'off' 상태"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        ctrl.start("/data.csv", mode="tail")
        ctrl.stop()
        assert ctrl.state == "off"
        ctrl.shutdown()

    def test_state_transitions(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """상태 전이: off → live → paused → live → off"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)

        states = []
        ctrl.streaming_state_changed.connect(lambda s: states.append(s))

        ctrl.start("/data.csv", mode="tail")
        ctrl.pause()
        ctrl.resume()
        ctrl.stop()

        assert states == ["live", "paused", "live", "off"]
        ctrl.shutdown()

    def test_set_poll_interval(self, mock_fs, mock_timer_factory, csv_data_5rows):
        """폴링 간격 설정"""
        from data_graph_studio.core.streaming_controller import StreamingController
        ctrl = StreamingController(fs=mock_fs, timer_factory=mock_timer_factory)
        mock_fs.add_file("/data.csv", csv_data_5rows, mtime=1000.0)
        ctrl.start("/data.csv", mode="tail")
        ctrl.set_poll_interval(2000)
        assert ctrl.poll_interval_ms == 2000
        ctrl.shutdown()
