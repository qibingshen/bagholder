"""隔离桌面实时行情刷新，避免网络访问阻塞 PySide6 界面。"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QThread, Signal


class LiveQuoteRefresh(QThread):
    """在后台线程执行调用方注入的本地事实刷新操作。"""

    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, operation: Callable[[], object]) -> None:
        super().__init__()
        self._operation = operation

    def run(self) -> None:
        """只把完成结果或脱敏失败消息发送回界面线程。"""

        try:
            self.succeeded.emit(self._operation())
        except Exception:
            self.failed.emit("实时行情刷新失败，界面仍可继续使用。")
