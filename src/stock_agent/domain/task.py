"""定义后台任务的持久化状态机，禁止跳过校验或验证阶段直接完成。"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TaskState(StrEnum):
    """任务的可持久化状态；成功只能在版本验证后产生。"""

    QUEUED = "QUEUED"
    VALIDATING = "VALIDATING"
    RUNNING = "RUNNING"
    STAGING = "STAGING"
    VERIFYING = "VERIFYING"
    SUCCEEDED = "SUCCEEDED"
    RETRY_WAIT = "RETRY_WAIT"
    CANCEL_REQUESTED = "CANCEL_REQUESTED"
    CANCELLED = "CANCELLED"
    INTERRUPTED = "INTERRUPTED"
    FAILED = "FAILED"


class InvalidTaskTransition(ValueError):
    """表示请求绕过任务安全状态机，调用方必须停止当前工作流。"""


@dataclass(frozen=True, slots=True)
class TaskRecord:
    """任务的可审计最小记录，不包含凭据或可直接覆盖的量化事实。"""

    task_id: UUID
    task_type: str
    deduplication_key: str
    state: TaskState
    attempt_count: int
    created_at: datetime
    error_code: str | None = None
