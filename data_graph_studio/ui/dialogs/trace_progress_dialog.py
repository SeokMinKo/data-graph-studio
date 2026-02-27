"""ADB Trace Controller and Progress Dialog.

Raw ftrace / Perfetto 캡처를 위한 ADB 명령 컨트롤러와 진행 상황 다이얼로그.
"""

from __future__ import annotations

import logging
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

from PySide6.QtCore import QObject, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QTextEdit,
    QVBoxLayout,
)

logger = logging.getLogger(__name__)


class AdbTraceController(QObject):
    """ADB를 통한 ftrace 캡처 컨트롤러.

    Attributes:
        _serial: 대상 기기 시리얼.
        _sysfs_path: ftrace sysfs 경로.
        _enabled_events: 활성화된 이벤트 목록.
        _tracing: 트레이싱 진행 중 여부.
    """

    log_message = Signal(str)
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._sysfs_path: str = ""
        self._enabled_events: list[str] = []
        self._tracing: bool = False

    def _run_adb_cmd(self, serial: str, shell_cmd: str) -> subprocess.CompletedProcess[str]:
        """ADB shell su 명령을 실행한다.

        Args:
            serial: 기기 시리얼 번호.
            shell_cmd: 실행할 셸 명령.

        Returns:
            CompletedProcess 결과.
        """
        quoted = shlex.quote(shell_cmd)
        cmd = ["adb", "-s", serial, "shell", "su", "-c", quoted]
        self.log_message.emit(f"$ {' '.join(cmd)}")
        logger.debug("[AdbTrace] exec: %s", " ".join(cmd))
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            logger.warning(
                "[AdbTrace] cmd failed (rc=%d): %s\nstdout=%s\nstderr=%s",
                result.returncode, shell_cmd,
                result.stdout[:500], result.stderr[:500],
            )
        else:
            logger.debug("[AdbTrace] cmd ok: %s (stdout=%d bytes)", shell_cmd, len(result.stdout))
        return result

    def _detect_sysfs_path(self, serial: str) -> str:
        """ftrace sysfs 경로를 탐지한다.

        Args:
            serial: 기기 시리얼 번호.

        Returns:
            발견된 sysfs 경로.

        Raises:
            RuntimeError: 두 경로 모두 접근 불가 시.
        """
        for path in ["/sys/kernel/tracing", "/sys/kernel/debug/tracing"]:
            logger.debug("[AdbTrace] probing sysfs: %s", path)
            result = self._run_adb_cmd(serial, f"ls {path}/trace")
            if result.returncode == 0:
                logger.info("[AdbTrace] sysfs path found: %s", path)
                return path
        logger.error("[AdbTrace] no sysfs path found on device %s", serial)
        raise RuntimeError("ftrace sysfs path not found on device")

    def start_trace(self, serial: str, config: dict[str, Any]) -> None:
        """트레이스를 시작한다.

        Args:
            serial: 기기 시리얼 번호.
            config: 트레이스 설정 (buffer_size_mb, events, save_path).
        """
        logger.info("[AdbTrace] start_trace: serial=%s, config=%s", serial, {
            k: v for k, v in config.items() if k != "save_path"
        })
        self._serial = serial
        self._sysfs_path = self._detect_sysfs_path(serial)
        sysfs = self._sysfs_path

        self.progress.emit("Clearing buffer...")
        self._run_adb_cmd(serial, f"echo > {sysfs}/trace")

        kb = config.get("buffer_size_mb", 64) * 1024
        self.progress.emit(f"Setting buffer size to {kb} KB...")
        self._run_adb_cmd(serial, f"echo {kb} > {sysfs}/buffer_size_kb")

        events = config.get("events", [])
        self._enabled_events = list(events)
        for event in events:
            self.progress.emit(f"Enabling event: {event}")
            self._run_adb_cmd(serial, f"echo 1 > {sysfs}/events/{event}/enable")

        self.progress.emit("Starting trace...")
        self._run_adb_cmd(serial, f"echo 1 > {sysfs}/tracing_on")
        self._tracing = True
        logger.info("[AdbTrace] tracing started: %d events enabled", len(events))
        self.log_message.emit("Tracing started.")

    def stop_trace(self, save_path: str) -> None:
        """트레이스를 중지하고 결과를 저장한다.

        Args:
            save_path: 트레이스 파일 저장 경로.
        """
        try:
            logger.info("[AdbTrace] stop_trace: save_path=%s", save_path)
            self.progress.emit("Stopping trace...")
            self._run_adb_cmd(self._serial, f"echo 0 > {self._sysfs_path}/tracing_on")
            self._tracing = False

            self.progress.emit("Pulling trace data...")
            result = self._run_adb_cmd(
                self._serial, f"cat {self._sysfs_path}/trace"
            )
            trace_size = len(result.stdout)
            logger.info("[AdbTrace] trace data pulled: %d bytes, stderr=%s",
                        trace_size, result.stderr[:200] if result.stderr else "")
            Path(save_path).parent.mkdir(parents=True, exist_ok=True)
            Path(save_path).write_text(result.stdout, encoding="utf-8")
            logger.info("[AdbTrace] trace saved: %s (%d bytes)", save_path, trace_size)
            self.log_message.emit(f"Trace saved to {save_path}")

            self._disable_events()
            self.finished.emit(save_path)
        except Exception as e:
            logger.error("[AdbTrace] stop_trace failed: %s", e, exc_info=True)
            self.error.emit(str(e))
        finally:
            self.cleanup()

    def _disable_events(self) -> None:
        """활성화된 이벤트를 비활성화한다."""
        for event in self._enabled_events:
            try:
                self._run_adb_cmd(
                    self._serial,
                    f"echo 0 > {self._sysfs_path}/events/{event}/enable",
                )
            except Exception as e:
                logger.warning("[AdbTrace] failed to disable event %s: %s", event, e)

    def cleanup(self) -> None:
        """트레이싱 상태를 정리한다 (idempotent)."""
        if not self._serial or not self._sysfs_path:
            logger.debug("[AdbTrace] cleanup: nothing to clean (no serial/sysfs)")
            return
        logger.debug("[AdbTrace] cleanup: tracing=%s, serial=%s", self._tracing, self._serial)
        try:
            if self._tracing:
                self._run_adb_cmd(
                    self._serial,
                    f"echo 0 > {self._sysfs_path}/tracing_on",
                )
                self._tracing = False
                logger.info("[AdbTrace] cleanup: tracing stopped")
        except Exception as e:
            logger.warning("[AdbTrace] cleanup: failed to stop tracing: %s", e)
        self._disable_events()


class PerfettoTraceController(QObject):
    """Perfetto 기반 캡처 + trace_processor_shell CSV 변환 컨트롤러.

    Flow:
        1. perfetto config push → perfetto 실행 (adb shell)
        2. Stop 시 SIGINT → pull .perfetto-trace
        3. trace_processor_shell로 CSV 변환
        4. CSV 경로 emit

    Signals:
        log_message: 로그 메시지.
        progress: 현재 단계.
        finished: 완료 시 CSV 파일 경로.
        error: 에러 메시지.
    """

    log_message = Signal(str)
    progress = Signal(str)
    finished = Signal(str)
    error = Signal(str)

    # ftrace_event 테이블 쿼리 — ts(나노초), cpu, event name, args
    FTRACE_QUERY = (
        "SELECT fe.ts, c.cpu, fe.name, t.name AS task, t.tid AS pid, "
        "group_concat(a.key || '=' || a.display_value, ' ') AS details "
        "FROM ftrace_event fe "
        "LEFT JOIN cpu c ON fe.ucpu = c.id "
        "LEFT JOIN thread t ON fe.utid = t.id "
        "LEFT JOIN args a ON fe.arg_set_id = a.arg_set_id "
        "GROUP BY fe.id "
        "ORDER BY fe.ts"
    )

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._serial: str = ""
        self._process: subprocess.Popen | None = None
        self._tracing: bool = False
        self._trace_device_path = "/data/local/tmp/dgs_trace.perfetto-trace"
        self._tp_shell: str = ""
        self._used_oneshot: bool = False

    @staticmethod
    def _platform_bin_dir() -> str:
        """Return platform subdirectory name for bundled binaries."""
        import platform as _platform
        s = sys.platform
        m = _platform.machine().lower()
        if s == "darwin":
            return "darwin-arm64" if m == "arm64" else "darwin-amd64"
        elif s == "linux":
            return "linux-arm64" if m == "aarch64" else "linux-amd64"
        elif s == "win32":
            return "win-amd64"
        return ""

    @staticmethod
    def find_trace_processor() -> str:
        """trace_processor_shell 또는 래퍼 스크립트 경로를 찾는다.

        탐색 순서:
        1. ~/.data_graph_studio/bin/ (사용자 로컬 캐시)
        2. 프로젝트 assets/bin/ (개발 모드)
        3. PATH에서 trace_processor_shell / trace_processor
        4. 자동 다운로드 → ~/.data_graph_studio/bin/

        Returns:
            실행 파일 경로.

        Raises:
            FileNotFoundError: 다운로드도 실패했을 때.
        """
        names = ["trace_processor_shell", "trace_processor"]
        if sys.platform == "win32":
            names.extend(["trace_processor_shell.exe", "trace_processor.exe"])

        # 1. 사용자 로컬 캐시
        user_bin = Path.home() / ".data_graph_studio" / "bin"
        for name in names:
            cached = user_bin / name
            if cached.exists():
                logger.debug("[trace_processor] found user cache: %s", cached)
                return str(cached)

        # 2. 패키지/실행 경로 기반 assets — 플랫폼별 바이너리
        plat_dir = PerfettoTraceController._platform_bin_dir()
        exe_name = "trace_processor_shell.exe" if sys.platform == "win32" else "trace_processor_shell"

        candidate_roots = [
            Path(__file__).resolve().parent.parent.parent,  # .../data_graph_studio
            Path(__file__).resolve().parent.parent.parent.parent,  # project root (dev)
            Path(sys.executable).resolve().parent,  # frozen exe dir
            Path(sys.executable).resolve().parent / "_internal",  # PyInstaller onedir
            Path(getattr(sys, "_MEIPASS", "")) if getattr(sys, "_MEIPASS", "") else None,
        ]

        for root in [p for p in candidate_roots if p]:
            for rel in [
                Path("assets") / "bin" / plat_dir / exe_name,
                Path("data_graph_studio") / "assets" / "bin" / plat_dir / exe_name,
            ]:
                bundled = root / rel
                if bundled.exists():
                    logger.debug("[trace_processor] found bundled: %s", bundled)
                    return str(bundled)

        # 3. PATH 탐색
        for name in ["trace_processor_shell", "trace_processor_shell.exe",
                      "trace_processor"]:
            path = shutil.which(name)
            if path:
                return path

        # 4. 자동 다운로드
        return PerfettoTraceController._download_trace_processor(user_bin)

    @staticmethod
    def _download_trace_processor(dest_dir: Path) -> str:
        """Perfetto trace_processor를 자동 다운로드한다.

        https://get.perfetto.dev/trace_processor 래퍼 스크립트를 받아서
        실행 권한을 부여한다. GitHub raw mirror를 fallback으로 사용.

        Returns:
            다운로드된 파일 경로.

        Raises:
            FileNotFoundError: 다운로드 실패 시.
        """
        import ssl
        import urllib.request

        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / "trace_processor"

        urls = [
            "https://get.perfetto.dev/trace_processor",
            "https://raw.githubusercontent.com/nicmcd/trace_processor_shell/master/trace_processor",
        ]

        headers = {"User-Agent": "DataGraphStudio/1.0"}
        last_error: Exception | None = None

        for url in urls:
            logger.info("Downloading trace_processor from %s ...", url)
            try:
                req = urllib.request.Request(url, headers=headers)
                # Allow up to 30s connection timeout
                ctx = ssl.create_default_context()
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    data = resp.read()
                dest.write_bytes(data)
                # chmod on non-Windows; on Windows just ensure file exists
                try:
                    dest.chmod(0o755)
                except OSError:
                    pass
                logger.info("Downloaded trace_processor to %s (%d bytes)", dest, len(data))
                return str(dest)
            except Exception as e:
                logger.warning("Failed to download from %s: %s", url, e)
                last_error = e
                dest.unlink(missing_ok=True)
                continue

        raise FileNotFoundError(
            "trace_processor_shell not found and auto-download failed.\n\n"
            f"Error: {last_error}\n\n"
            "Manual install:\n"
            "  curl -LO https://get.perfetto.dev/trace_processor\n"
            "  chmod +x trace_processor\n"
            f"  mv trace_processor {dest_dir}/"
        ) from last_error

    def _push_perfetto_config(self, adb: list[str], local_config_path: str) -> str:
        """Push perfetto config to device and ensure readable permission.

        우선 /data/local/tmp 경로를 사용하고, 실패 시 /sdcard/Download로 fallback 한다.
        Returns:
            Device config path used.
        Raises:
            RuntimeError: 모든 경로에서 push 실패 시.
        """
        candidates = [
            "/data/local/tmp/dgs_perfetto.pbtxt",
            "/sdcard/Download/dgs_perfetto.pbtxt",
        ]
        last_error = ""

        for device_config in candidates:
            try:
                push_result = subprocess.run(
                    adb + ["push", local_config_path, device_config],
                    capture_output=True,
                    text=True,
                    timeout=15,
                    check=True,
                )
                logger.debug("[Perfetto] config pushed to %s: %s", device_config, push_result.stdout.strip())

                # shell user가 소유한 파일이면 root 없이 chmod 가능
                chmod_result = subprocess.run(
                    adb + ["shell", "chmod", "644", device_config],
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                if chmod_result.returncode != 0:
                    logger.warning(
                        "[Perfetto] chmod failed for %s (non-fatal): %s",
                        device_config,
                        chmod_result.stderr.strip(),
                    )
                else:
                    logger.debug("[Perfetto] chmod 644 applied: %s", device_config)

                return device_config
            except subprocess.CalledProcessError as e:
                last_error = e.stderr or str(e)
                logger.warning(
                    "[Perfetto] config push failed for %s: rc=%s stderr=%s",
                    device_config,
                    e.returncode,
                    (e.stderr or "").strip(),
                )

        raise RuntimeError(f"Failed to push perfetto config to device paths: {last_error}")

    def start_trace(self, serial: str, config: dict[str, Any]) -> None:
        """Perfetto 트레이스를 시작한다.

        Args:
            serial: 기기 시리얼 번호.
            config: 트레이스 설정 (buffer_size_mb, events).
        """
        logger.info("[Perfetto] start_trace: serial=%s, buffer=%dMB, events=%s",
                    serial, config.get("buffer_size_mb", 64), config.get("events", []))
        self._serial = serial
        self._tp_shell = self.find_trace_processor()
        logger.debug("[Perfetto] trace_processor: %s", self._tp_shell)

        buffer_mb = int(config.get("buffer_size_mb", 64))
        buffer_kb = buffer_mb * 1024
        events = config.get("events", [
            "block/block_rq_issue",
            "block/block_rq_complete",
            "ufs/ufshcd_command",
        ])
        duration_s = int(config.get("duration_s", 10))

        events_str = "\n".join(f'            ftrace_events: "{e}"' for e in events)
        perfetto_config = (
            f"buffers: {{\n"
            f"    size_kb: {buffer_kb}\n"
            f"    fill_policy: RING_BUFFER\n"
            f"}}\n"
            f"data_sources: {{\n"
            f"    config {{\n"
            f'        name: "linux.ftrace"\n'
            f"        ftrace_config {{\n"
            f"{events_str}\n"
            f"            buffer_size_kb: {buffer_kb // 2}\n"
            f"        }}\n"
            f"    }}\n"
            f"}}\n"
            f"duration_ms: 0\n"
        )

        # Push config
        self.progress.emit("Pushing perfetto config...")
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".pbtxt", delete=False
        ) as f:
            f.write(perfetto_config)
            config_path = f.name

        adb = ["adb", "-s", serial]
        try:
            device_config = self._push_perfetto_config(adb, config_path)
        finally:
            Path(config_path).unlink(missing_ok=True)

        # Start perfetto (--txt for text-format config)
        # NOTE: non-root Android builds can deny direct -c /path reads due to SELinux.
        # Use stdin piping with -c - for broader compatibility.
        self.progress.emit("Starting perfetto...")
        self._used_oneshot = False
        self._trace_device_path = "/data/local/tmp/dgs_trace.perfetto-trace"
        shell_cmd = (
            f"cat {shlex.quote(device_config)} | "
            f"perfetto --txt -c - -o {shlex.quote(self._trace_device_path)}"
        )
        perfetto_cmd = adb + ["shell", shell_cmd]
        self.log_message.emit(
            f"$ adb -s {serial} shell '{shell_cmd}'"
        )
        self._process = subprocess.Popen(
            perfetto_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        # Give perfetto a moment to start (or fail)
        import time
        time.sleep(1)
        if self._process.poll() is not None:
            # Exited immediately — read stderr for error
            _, stderr = self._process.communicate(timeout=5)
            err_msg = stderr.decode(errors="replace").strip() if stderr else "unknown error"
            logger.warning("[Perfetto] config mode failed, trying oneshot fallback: rc=%s, stderr=%s",
                           self._process.returncode, err_msg)
            self._process = None

            # Fallback: known-working command path/format from field validation
            self._used_oneshot = True
            self._trace_device_path = "/data/misc/perfetto-traces/blocktrace.pftrace"
            oneshot_cmd = adb + [
                "shell", "perfetto",
                "--time", f"{duration_s}s",
                "--buffer", f"{buffer_mb}mb",
                *events,
                "-o", self._trace_device_path,
            ]
            self.log_message.emit(
                f"$ adb -s {serial} shell perfetto --time {duration_s}s --buffer {buffer_mb}mb "
                f"{' '.join(events)} -o {self._trace_device_path}"
            )
            self._process = subprocess.Popen(
                oneshot_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            time.sleep(1)
            if self._process.poll() is not None:
                _, stderr2 = self._process.communicate(timeout=5)
                err_msg2 = stderr2.decode(errors="replace").strip() if stderr2 else "unknown error"
                logger.error("[Perfetto] oneshot fallback failed: rc=%s, stderr=%s",
                             self._process.returncode, err_msg2)
                self._process = None
                raise RuntimeError(f"Perfetto failed to start: {err_msg2}")

        self._tracing = True
        logger.info("[Perfetto] tracing started (pid=%s, oneshot=%s)", self._process.pid, self._used_oneshot)
        self.log_message.emit("Perfetto tracing started.")

    def stop_trace(self, save_path: str) -> None:
        """트레이스 중지 → pull → trace_processor_shell CSV 변환.

        Args:
            save_path: 최종 CSV 파일 저장 경로.
        """
        adb = ["adb", "-s", self._serial]
        trace_local = str(Path(save_path).with_suffix(".perfetto-trace"))
        logger.info("[Perfetto] stop_trace: save_path=%s, trace_local=%s", save_path, trace_local)

        try:
            # 1. Stop perfetto (SIGINT) or wait for oneshot completion
            self.progress.emit("Stopping perfetto...")
            if self._used_oneshot:
                logger.debug("[Perfetto] oneshot mode: waiting for perfetto to finish")
                if self._process:
                    try:
                        rc = self._process.wait(timeout=30)
                        logger.debug("[Perfetto] oneshot process exited: rc=%s", rc)
                    except subprocess.TimeoutExpired:
                        logger.warning("[Perfetto] oneshot timeout, killing")
                        self._process.kill()
            else:
                pid_result = subprocess.run(
                    adb + ["shell", "pidof", "perfetto"],
                    capture_output=True, text=True, timeout=5,
                )
                perfetto_pid = pid_result.stdout.strip()
                if perfetto_pid:
                    logger.debug("[Perfetto] sending SIGINT to pid %s", perfetto_pid)
                    kill_result = subprocess.run(
                        adb + ["shell", "kill", "-SIGINT", perfetto_pid],
                        capture_output=True, text=True, timeout=5,
                    )
                    logger.debug("[Perfetto] kill result: rc=%d, stderr=%s",
                                 kill_result.returncode, kill_result.stderr.strip())
                else:
                    logger.warning("[Perfetto] perfetto process not found on device")
                if self._process:
                    try:
                        rc = self._process.wait(timeout=20)
                        logger.debug("[Perfetto] local process exited: rc=%s", rc)
                    except subprocess.TimeoutExpired:
                        logger.warning("[Perfetto] local process timeout, killing")
                        self._process.kill()
            self._tracing = False

            # 2. Wait for trace file to be flushed, then pull
            self.progress.emit("Waiting for trace file...")
            import time
            for attempt in range(5):
                check = subprocess.run(
                    adb + ["shell", "ls", "-l", self._trace_device_path],
                    capture_output=True, text=True, timeout=5,
                )
                if check.returncode == 0 and self._trace_device_path in check.stdout:
                    logger.debug("[Perfetto] trace file exists (attempt %d): %s",
                                 attempt, check.stdout.strip())
                    break
                logger.debug("[Perfetto] trace file not ready (attempt %d), waiting 2s...", attempt)
                time.sleep(2)
            else:
                logger.warning("[Perfetto] trace file not found after 5 attempts")

            self.progress.emit("Pulling trace file...")
            logger.debug("[Perfetto] pulling %s → %s", self._trace_device_path, trace_local)
            result = subprocess.run(
                adb + ["pull", self._trace_device_path, trace_local],
                capture_output=True, text=True, timeout=120,
            )
            if result.returncode != 0:
                logger.error("[Perfetto] pull failed: rc=%d, stderr=%s",
                             result.returncode, result.stderr.strip())
                raise RuntimeError(
                    f"Failed to pull trace: {result.stderr.strip()}"
                )
            trace_size = Path(trace_local).stat().st_size if Path(trace_local).exists() else 0
            logger.info("[Perfetto] binary trace pulled: %s (%d bytes)", trace_local, trace_size)
            self.log_message.emit(f"Binary trace: {trace_local}")

            # 3. Convert to CSV via trace_processor_shell
            self.progress.emit("Converting to CSV...")
            csv_path = str(Path(save_path).with_suffix(".csv"))
            logger.debug("[Perfetto] converting: %s → %s (query=%d chars)",
                         trace_local, csv_path, len(self.FTRACE_QUERY))
            self.log_message.emit(
                f"$ {self._tp_shell} -Q '...' {trace_local}"
            )
            tp_result = subprocess.run(
                [
                    self._tp_shell,
                    "-Q", self.FTRACE_QUERY,
                    trace_local,
                ],
                capture_output=True, text=True, timeout=120,
            )
            if tp_result.returncode != 0:
                logger.error("[Perfetto] trace_processor failed: rc=%d\nstderr=%s",
                             tp_result.returncode, tp_result.stderr[:1000])
                raise RuntimeError(
                    f"trace_processor_shell failed: {tp_result.stderr.strip()}"
                )

            csv_size = len(tp_result.stdout)
            csv_lines = tp_result.stdout.count("\n")
            Path(csv_path).write_text(tp_result.stdout, encoding="utf-8")
            logger.info("[Perfetto] CSV saved: %s (%d bytes, ~%d rows)", csv_path, csv_size, csv_lines)
            self.log_message.emit(f"CSV saved: {csv_path}")
            self.finished.emit(csv_path)

        except Exception as e:
            logger.error("[Perfetto] stop_trace failed: %s", e, exc_info=True)
            self.error.emit(str(e))
        finally:
            self._process = None
            self._used_oneshot = False

    def cleanup(self) -> None:
        """Perfetto 프로세스를 정리한다 (idempotent)."""
        logger.debug("[Perfetto] cleanup: process=%s, tracing=%s", self._process is not None, self._tracing)
        if self._process:
            try:
                self._process.kill()
                logger.debug("[Perfetto] cleanup: local process killed")
            except Exception as e:
                logger.warning("[Perfetto] cleanup: kill failed: %s", e)
            self._process = None
        if self._tracing and self._serial:
            try:
                pid_result = subprocess.run(
                    ["adb", "-s", self._serial, "shell", "pidof", "perfetto"],
                    capture_output=True, text=True, timeout=5,
                )
                pid = pid_result.stdout.strip()
                if pid:
                    subprocess.run(
                        ["adb", "-s", self._serial, "shell",
                         "kill", "-9", pid],
                        capture_output=True, text=True, timeout=5,
                    )
            except Exception:
                pass
            self._tracing = False


class _StopWorker(QThread):
    """stop_trace를 백그라운드에서 실행하는 워커 스레드."""

    def __init__(
        self, controller: AdbTraceController, save_path: str, parent: QObject | None = None
    ) -> None:
        super().__init__(parent)
        self._controller = controller
        self._save_path = save_path

    def run(self) -> None:
        """스레드에서 stop_trace를 실행한다."""
        self._controller.stop_trace(self._save_path)


class TraceProgressDialog(QDialog):
    """트레이스 진행 상황을 표시하는 다이얼로그.

    Attributes:
        _controller: AdbTraceController 참조.
        _start_time: 트레이스 시작 시간.
    """

    def __init__(
        self,
        controller: AdbTraceController,
        save_path: str = "",
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Trace Progress")
        self.setMinimumSize(480, 320)

        self._controller = controller
        self._save_path = save_path
        self._start_time = time.time()
        self._worker: _StopWorker | None = None

        layout = QVBoxLayout(self)

        self._elapsed_label = QLabel("Elapsed: 0s")
        layout.addWidget(self._elapsed_label)

        self._log_text = QTextEdit()
        self._log_text.setReadOnly(True)
        self._log_text.setPlaceholderText("트레이스를 시작합니다...")
        layout.addWidget(self._log_text)

        self._stop_btn = QPushButton("Stop")
        self._stop_btn.clicked.connect(self._on_stop)
        layout.addWidget(self._stop_btn)

        # Connect signals
        controller.log_message.connect(self._append_log)
        controller.progress.connect(self._append_log)
        controller.finished.connect(self._on_finished)
        controller.error.connect(self._on_error)

        # Timer for elapsed time
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_elapsed)
        self._timer.start(1000)

    def _append_log(self, msg: str) -> None:
        """로그 메시지를 추가한다."""
        self._log_text.append(msg)
        scrollbar = self._log_text.verticalScrollBar()
        if scrollbar:
            scrollbar.setValue(scrollbar.maximum())

    def _update_elapsed(self) -> None:
        """경과 시간을 업데이트한다."""
        elapsed = int(time.time() - self._start_time)
        self._elapsed_label.setText(f"Elapsed: {elapsed}s")

    def _on_stop(self) -> None:
        """Stop 버튼 클릭 핸들러."""
        self._stop_btn.setEnabled(False)
        self._worker = _StopWorker(self._controller, self._save_path, self)
        self._worker.start()

    def _on_finished(self, path: str) -> None:
        """트레이스 완료 핸들러."""
        self._timer.stop()
        self.accept()

    def _on_error(self, msg: str) -> None:
        """에러 핸들러."""
        self._timer.stop()
        QMessageBox.critical(self, "Trace Error", msg)
        self.reject()

    def closeEvent(self, event: Any) -> None:
        """닫기 이벤트: 트레이스 중이면 확인 요청."""
        if self._controller._tracing:
            reply = QMessageBox.question(
                self,
                "Confirm",
                "트레이스가 진행 중입니다. 중지하시겠습니까?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.No:
                event.ignore()
                return
            self._controller.cleanup()
        super().closeEvent(event)
