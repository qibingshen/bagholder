"""任务中心页面状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

_任务状态说明 = {
    "LOADING": "正在加载本地任务状态。",
    "OFFLINE": "当前离线，不能启动新的后台任务。",
    "PARTIAL_SUCCESS": "任务部分完成，请查看降级影响。",
    "RECOVERABLE": "任务可从恢复点继续。",
    "READY": "任务中心可用。",
}


@dataclass(frozen=True, slots=True)
class TaskCenterPageState:
    """任务中心状态，控制恢复入口和警告展示。"""

    status: str
    user_message: str = field(init=False)
    show_warning: bool = field(init=False)
    show_resume_action: bool = field(init=False)

    def __post_init__(self) -> None:
        """部分成功显示警告，可恢复状态显示恢复入口。"""

        if self.status not in _任务状态说明:
            raise ValueError(f"不支持的任务中心状态：{self.status}")
        object.__setattr__(self, "user_message", _任务状态说明[self.status])
        object.__setattr__(self, "show_warning", self.status == "PARTIAL_SUCCESS")
        object.__setattr__(self, "show_resume_action", self.status == "RECOVERABLE")
