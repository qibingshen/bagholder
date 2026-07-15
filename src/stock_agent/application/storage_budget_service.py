"""本地容量预算、预警和分钟线保存限制。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class StorageBudgetDecision:
    """容量预算评估结果。"""

    status: str


class StorageBudgetService:
    """按总容量和预警比例评估本地数据占用。"""

    def __init__(self, max_bytes: int, warning_ratio: float) -> None:
        """设置最大容量和预警比例。"""

        self._max_bytes = max_bytes
        self._warning_bytes = int(max_bytes * warning_ratio)

    def evaluate(self, used_bytes: int) -> StorageBudgetDecision:
        """返回 OK、WARNING 或 BLOCKED。"""

        if used_bytes > self._max_bytes:
            return StorageBudgetDecision(status="BLOCKED")
        if used_bytes >= self._warning_bytes:
            return StorageBudgetDecision(status="WARNING")
        return StorageBudgetDecision(status="OK")


@dataclass(frozen=True)
class RetentionDecision:
    """分钟线保存范围校验结果。"""

    allowed: bool


class MinuteRetentionPolicy:
    """限制分钟线证券数量和保留天数。"""

    def __init__(self, max_symbols: int, max_days: int) -> None:
        """设置分钟线选择上限。"""

        self._max_symbols = max_symbols
        self._max_days = max_days

    def validate(self, symbol_count: int, retention_days: int) -> RetentionDecision:
        """检查分钟线保存计划是否在预算范围内。"""

        return RetentionDecision(
            allowed=symbol_count <= self._max_symbols and retention_days <= self._max_days
        )


class PlatformDataDirectory:
    """集中封装三平台数据目录差异。"""

    @staticmethod
    def for_platform(platform: str, username: str) -> Path:
        """返回指定平台的默认数据目录。"""

        if platform == "Windows":
            return Path("C:/Users") / username / "AppData" / "Local" / "Bagholder"
        if platform == "Darwin":
            return Path("/Users") / username / "Library" / "Application Support" / "Bagholder"
        return Path("/home") / username / ".local" / "share" / "bagholder"
