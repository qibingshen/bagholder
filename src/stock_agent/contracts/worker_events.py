"""定义工作进程向本地服务报告的结构化事件，事件不包含凭据或原始异常堆栈。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class WorkerEventKind(StrEnum):
    """工作进程完成、失败或确认取消时允许发送的事件类型。"""

    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class WorkerEvent:
    """用于安全驱动桌面状态更新的事件，不把工作异常直接抛入界面线程。"""

    kind: WorkerEventKind
    task_id: UUID
    occurred_at: datetime
    error_code: str | None = None
