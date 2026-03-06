"""
Memory Monitor - 메모리 사용량 모니터링
"""

import psutil
from typing import Dict


class MemoryMonitor:
    """메모리 모니터"""

    @staticmethod
    def get_process_memory() -> Dict[str, float]:
        """현재 프로세스 메모리 사용량"""
        process = psutil.Process()
        mem_info = process.memory_info()

        return {
            "rss_mb": mem_info.rss / (1024 * 1024),  # Resident Set Size
            "vms_mb": mem_info.vms / (1024 * 1024),  # Virtual Memory Size
            "percent": process.memory_percent(),
        }

    @staticmethod
    def get_system_memory() -> Dict[str, float]:
        """시스템 메모리 정보"""
        mem = psutil.virtual_memory()

        return {
            "total_gb": mem.total / (1024**3),
            "available_gb": mem.available / (1024**3),
            "used_gb": mem.used / (1024**3),
            "percent": mem.percent,
        }

    @staticmethod
    def format_memory(mb: float) -> str:
        """메모리 크기 포맷팅"""
        if mb >= 1024:
            return f"{mb / 1024:.2f} GB"
        return f"{mb:.1f} MB"
