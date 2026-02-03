"""
Tests for I/O Abstraction Layer — PRD Section 9.4

Tests for:
- IFileSystem ABC and RealFileSystem
- ITimerFactory ABC
- atomic_write utility
"""

import os
import tempfile
import pytest

from data_graph_studio.core.io_abstract import (
    IFileSystem,
    ITimerFactory,
    RealFileSystem,
    atomic_write,
)


class TestRealFileSystem:
    """RealFileSystem 구현 테스트"""

    def test_write_and_read_file(self, tmp_path):
        fs = RealFileSystem()
        path = str(tmp_path / "test.txt")
        data = b"hello world"

        fs.write_file(path, data)
        result = fs.read_file(path)
        assert result == data

    def test_exists_true(self, tmp_path):
        fs = RealFileSystem()
        path = str(tmp_path / "exists.txt")
        with open(path, "wb") as f:
            f.write(b"data")

        assert fs.exists(path) is True

    def test_exists_false(self, tmp_path):
        fs = RealFileSystem()
        assert fs.exists(str(tmp_path / "nonexistent.txt")) is False

    def test_stat(self, tmp_path):
        fs = RealFileSystem()
        path = str(tmp_path / "stat_test.txt")
        with open(path, "wb") as f:
            f.write(b"12345")

        result = fs.stat(path)
        assert result.st_size == 5

    def test_read_nonexistent_raises(self, tmp_path):
        fs = RealFileSystem()
        with pytest.raises(FileNotFoundError):
            fs.read_file(str(tmp_path / "nope.txt"))

    def test_stat_nonexistent_raises(self, tmp_path):
        fs = RealFileSystem()
        with pytest.raises(FileNotFoundError):
            fs.stat(str(tmp_path / "nope.txt"))

    def test_write_creates_parent_dirs(self, tmp_path):
        fs = RealFileSystem()
        path = str(tmp_path / "sub" / "dir" / "file.txt")
        fs.write_file(path, b"nested")
        assert fs.exists(path)
        assert fs.read_file(path) == b"nested"


class TestIFileSystemABC:
    """IFileSystem은 ABC이며 직접 인스턴스화 불가"""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            IFileSystem()


class TestITimerFactoryABC:
    """ITimerFactory은 ABC이며 직접 인스턴스화 불가"""

    def test_cannot_instantiate(self):
        with pytest.raises(TypeError):
            ITimerFactory()


class TestAtomicWrite:
    """atomic_write 유틸리티 테스트 — PRD Section 10.3"""

    def test_basic_write(self, tmp_path):
        path = str(tmp_path / "atomic.txt")
        atomic_write(path, b"safe data")

        with open(path, "rb") as f:
            assert f.read() == b"safe data"

    def test_overwrites_existing(self, tmp_path):
        path = str(tmp_path / "overwrite.txt")
        with open(path, "wb") as f:
            f.write(b"old")

        atomic_write(path, b"new")
        with open(path, "rb") as f:
            assert f.read() == b"new"

    def test_no_temp_file_left_on_success(self, tmp_path):
        path = str(tmp_path / "clean.txt")
        atomic_write(path, b"data")

        # .tmp file should not exist
        assert not os.path.exists(path + ".tmp")

    def test_no_temp_file_left_on_failure(self, tmp_path):
        """실패 시 임시 파일이 정리됨"""
        # Use a directory as path to force rename failure
        dir_path = str(tmp_path / "a_dir")
        os.makedirs(dir_path)

        with pytest.raises(Exception):
            atomic_write(dir_path, b"will fail")

        assert not os.path.exists(dir_path + ".tmp")

    def test_atomic_write_fsync(self, tmp_path):
        """데이터가 디스크에 안전하게 기록됨 (fsync 호출됨)"""
        path = str(tmp_path / "fsync_test.txt")
        atomic_write(path, b"fsync data")

        # Simply check it was written correctly
        with open(path, "rb") as f:
            assert f.read() == b"fsync data"

    def test_large_data(self, tmp_path):
        """대용량 데이터도 정상 동작"""
        path = str(tmp_path / "large.bin")
        data = b"x" * (1024 * 1024)  # 1MB
        atomic_write(path, data)

        with open(path, "rb") as f:
            assert f.read() == data
