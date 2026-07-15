"""任务中心视图模型。"""

from __future__ import annotations

from dataclasses import dataclass, field

_终态 = frozenset({"success", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class TaskItemViewModel:
    """桌面任务列表中的单个任务状态。"""

    task_id: str
    status: str
    retryable: bool
    cancellable: bool
    resume_from: str | None
    notification_level: str
    safe_message_zh: str
    can_retry: bool = field(init=False)
    can_cancel: bool = field(init=False)
    can_resume: bool = field(init=False)

    def __post_init__(self) -> None:
        """终态任务只允许查看结果，不允许重复触发后台任务。"""

        is_terminal = self.status in _终态
        object.__setattr__(self, "can_retry", self.retryable and not is_terminal)
        object.__setattr__(self, "can_cancel", self.cancellable and not is_terminal)
        object.__setattr__(self, "can_resume", self.resume_from is not None and not is_terminal)
