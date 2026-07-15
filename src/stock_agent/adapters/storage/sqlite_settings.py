"""仅保存窗口和偏好等可重建桌面状态。"""

import sqlite3
from pathlib import Path


class QuantitativeFactForbiddenError(ValueError):
    """阻止将行情、预测等量化事实写入 SQLite。"""


class DesktopSettingsStore:
    """隔离桌面偏好，避免其成为量化事实来源。"""

    def __init__(self, path: Path) -> None:
        self._connection = sqlite3.connect(path)
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )

    def set(self, key: str, value: str) -> None:
        """保存可重建设置，拒绝事实域键。"""
        if key.split(".", 1)[0] in {"quote", "market", "prediction", "backtest", "report", "model"}:
            raise QuantitativeFactForbiddenError("SQLite 不得保存量化事实")
        self._connection.execute("INSERT OR REPLACE INTO settings VALUES (?, ?)", (key, value))
        self._connection.commit()

    def get(self, key: str) -> str | None:
        """读取桌面设置。"""
        row = self._connection.execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row[0])
