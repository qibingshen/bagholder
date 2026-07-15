"""以 DuckDB 保存任务、去重键和状态迁移，供桌面进程与后台工作进程协调使用。"""

from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import duckdb

from stock_agent.domain.task import InvalidTaskTransition, TaskRecord, TaskState


class TaskService:
    """管理单机任务状态；调用方必须以状态机而非直接更新数据库改变任务结果。"""

    _transitions: dict[TaskState, frozenset[TaskState]] = {
        TaskState.QUEUED: frozenset({TaskState.VALIDATING, TaskState.CANCEL_REQUESTED}),
        TaskState.VALIDATING: frozenset(
            {TaskState.RUNNING, TaskState.FAILED, TaskState.CANCEL_REQUESTED}
        ),
        TaskState.RUNNING: frozenset(
            {
                TaskState.STAGING,
                TaskState.RETRY_WAIT,
                TaskState.FAILED,
                TaskState.CANCEL_REQUESTED,
                TaskState.INTERRUPTED,
            }
        ),
        TaskState.STAGING: frozenset(
            {
                TaskState.VERIFYING,
                TaskState.FAILED,
                TaskState.CANCEL_REQUESTED,
                TaskState.INTERRUPTED,
            }
        ),
        TaskState.VERIFYING: frozenset(
            {
                TaskState.SUCCEEDED,
                TaskState.FAILED,
                TaskState.CANCEL_REQUESTED,
                TaskState.INTERRUPTED,
            }
        ),
        TaskState.RETRY_WAIT: frozenset(
            {TaskState.QUEUED, TaskState.FAILED, TaskState.CANCEL_REQUESTED}
        ),
        TaskState.CANCEL_REQUESTED: frozenset({TaskState.CANCELLED}),
        TaskState.INTERRUPTED: frozenset({TaskState.RETRY_WAIT, TaskState.FAILED}),
        TaskState.SUCCEEDED: frozenset(),
        TaskState.CANCELLED: frozenset(),
        TaskState.FAILED: frozenset(),
    }

    def __init__(self, database_path: Path) -> None:
        self._connection = duckdb.connect(str(database_path))
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                task_id VARCHAR PRIMARY KEY,
                task_type VARCHAR NOT NULL,
                deduplication_key VARCHAR UNIQUE NOT NULL,
                state VARCHAR NOT NULL,
                attempt_count INTEGER NOT NULL,
                created_at TIMESTAMPTZ NOT NULL,
                error_code VARCHAR,
                input_version VARCHAR,
                output_version VARCHAR,
                audit_correlation_id VARCHAR
            )
            """
        )

    def submit(
        self, task_type: str, deduplication_key: str, input_version: str | None = None
    ) -> TaskRecord:
        """创建或复用同一去重键的任务，防止重复写入或重复启动后台进程。"""

        if not task_type.strip() or not deduplication_key.strip():
            raise ValueError("任务类型和去重键不能为空")
        existing = self._connection.execute(
            "SELECT task_id FROM tasks WHERE deduplication_key = ?", [deduplication_key]
        ).fetchone()
        if existing:
            return self.get(UUID(existing[0]))
        task_id = uuid4()
        self._connection.execute(
            "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                str(task_id),
                task_type,
                deduplication_key,
                TaskState.QUEUED.value,
                0,
                datetime.now(UTC),
                None,
                input_version,
                None,
                None,
            ],
        )
        return self.get(task_id)

    def get(self, task_id: UUID) -> TaskRecord:
        """读取明确任务标识，不以“最新任务”代替，避免桌面显示错位状态。"""

        row = self._connection.execute(
            "SELECT task_id, task_type, deduplication_key, state, attempt_count, "
            "created_at, error_code FROM tasks WHERE task_id = ?",
            [str(task_id)],
        ).fetchone()
        if row is None:
            raise KeyError(str(task_id))
        return TaskRecord(UUID(row[0]), row[1], row[2], TaskState(row[3]), row[4], row[5], row[6])

    def transition(self, task_id: UUID, target: TaskState) -> TaskRecord:
        """在同一数据库中验证并写入状态迁移，防止调用方伪造成功状态。"""

        current = self.get(task_id)
        if target not in self._transitions[current.state]:
            raise InvalidTaskTransition(f"不允许从 {current.state} 迁移到 {target}")
        attempts = current.attempt_count + (1 if target is TaskState.RUNNING else 0)
        self._connection.execute(
            "UPDATE tasks SET state = ?, attempt_count = ? WHERE task_id = ?",
            [target.value, attempts, str(task_id)],
        )
        return self.get(task_id)

    def mark_retryable_failure(self, task_id: UUID, error_code: str) -> TaskRecord:
        """仅运行期可恢复错误可进入退避等待，完整性或权限错误必须改走失败路径。"""

        record = self.transition(task_id, TaskState.RETRY_WAIT)
        self._connection.execute(
            "UPDATE tasks SET error_code = ? WHERE task_id = ?", [error_code, str(task_id)]
        )
        return self.get(record.task_id)

    def fail(self, task_id: UUID, error_code: str) -> TaskRecord:
        """记录不可恢复的工作失败，禁止该任务继续提交暂存或覆盖已验证数据。"""

        record = self.transition(task_id, TaskState.FAILED)
        self._connection.execute(
            "UPDATE tasks SET error_code = ? WHERE task_id = ?", [error_code, str(task_id)]
        )
        return self.get(record.task_id)

    def succeed(self, task_id: UUID, output_version: str) -> TaskRecord:
        """仅在验证阶段完成后登记输出版本并标记成功。"""

        record = self.transition(task_id, TaskState.SUCCEEDED)
        self._connection.execute(
            "UPDATE tasks SET output_version = ? WHERE task_id = ?", [output_version, str(task_id)]
        )
        return self.get(record.task_id)

    def retry(self, task_id: UUID) -> TaskRecord:
        """将退避中的任务重新排队，保留已累计的尝试次数与错误证据。"""

        return self.transition(task_id, TaskState.QUEUED)

    def cancel(self, task_id: UUID) -> TaskRecord:
        """请求取消；工作进程必须确认后才能进入已取消状态。"""

        return self.transition(task_id, TaskState.CANCEL_REQUESTED)

    def confirm_cancelled(self, task_id: UUID) -> TaskRecord:
        """记录工作进程已停止并确认不会再提交暂存工件。"""

        return self.transition(task_id, TaskState.CANCELLED)

    def mark_interrupted(self, task_id: UUID) -> TaskRecord:
        """记录进程中断，恢复时再根据原子提交证据决定重试或失败。"""

        return self.transition(task_id, TaskState.INTERRUPTED)

    def recover_interrupted(self, task_id: UUID, has_valid_commit: bool) -> TaskRecord:
        """中断后只接受已验证的提交证据；无证据时终止，避免消费半成品数据。"""

        return self.transition(
            task_id, TaskState.RETRY_WAIT if has_valid_commit else TaskState.FAILED
        )
