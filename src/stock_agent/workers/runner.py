"""将后台工作结果转换为任务状态与结构化事件，不依赖 PySide6 界面对象。"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from errno import ENOSPC
from uuid import UUID

from stock_agent.application.task_service import TaskService
from stock_agent.contracts.worker_events import WorkerEvent, WorkerEventKind
from stock_agent.domain.task import TaskState


@dataclass(frozen=True, slots=True)
class WorkerOutcome:
    """表示后台结果对桌面端的安全影响，失败消息不含内部异常细节。"""

    event: WorkerEvent
    desktop_message: str


@dataclass(frozen=True, slots=True)
class StagedCommit:
    """工作进程返回的暂存提交证据；版本有效性必须在成功状态前明确确认。"""

    output_version: str
    is_valid: bool


class WorkerRunner:
    """运行由独立工作进程调用的工作单元，并确保异常只影响对应任务。"""

    def __init__(self, task_service: TaskService) -> None:
        self._task_service = task_service

    def execute(self, task_id: UUID, operation: Callable[[], StagedCommit]) -> WorkerOutcome:
        """捕获工作异常，写入失败状态并返回事件；调用方无需捕获后台异常。"""

        try:
            staged_commit = operation()
        except OSError as error:
            error_code = "DISK_FULL" if error.errno == ENOSPC else "WORKER_OS_ERROR"
            self._task_service.fail(task_id, error_code)
            return self._failed(task_id, error_code)
        except Exception:
            self._task_service.fail(task_id, "WORKER_CRASHED")
            return self._failed(task_id, "WORKER_CRASHED")
        if not staged_commit.output_version or not staged_commit.is_valid:
            self._task_service.fail(task_id, "STAGING_VALIDATION_FAILED")
            return self._failed(task_id, "STAGING_VALIDATION_FAILED")
        self._task_service.transition(task_id, TaskState.STAGING)
        self._task_service.transition(task_id, TaskState.VERIFYING)
        self._task_service.succeed(task_id, staged_commit.output_version)
        return WorkerOutcome(
            WorkerEvent(WorkerEventKind.SUCCEEDED, task_id, datetime.now(UTC)),
            "后台任务已完成，结果可供桌面应用读取。",
        )

    def confirm_cancellation(self, task_id: UUID) -> WorkerOutcome:
        """由工作端确认已停止后更新为取消状态，避免桌面线程等待或强制终止。"""

        self._task_service.confirm_cancelled(task_id)
        return WorkerOutcome(
            WorkerEvent(WorkerEventKind.CANCELLED, task_id, datetime.now(UTC)),
            "后台任务已取消，桌面应用仍可继续使用。",
        )

    @staticmethod
    def _failed(task_id: UUID, error_code: str) -> WorkerOutcome:
        return WorkerOutcome(
            WorkerEvent(WorkerEventKind.FAILED, task_id, datetime.now(UTC), error_code),
            "后台任务失败，桌面应用仍可继续使用。",
        )
