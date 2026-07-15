"""验证后台任务状态迁移、去重和崩溃恢复边界。"""

import pytest


def test_重复提交复用同一持久化任务且拒绝非法迁移(tmp_path) -> None:
    """同一去重键不得启动两个写任务，非法跳转也不能篡改持久化状态。"""

    from stock_agent.application.task_service import TaskService
    from stock_agent.domain.task import InvalidTaskTransition, TaskState

    service = TaskService(tmp_path / "tasks.duckdb")
    first = service.submit("市场更新", "daily-cn-20260714")
    duplicate = service.submit("市场更新", "daily-cn-20260714")

    assert duplicate.task_id == first.task_id
    with pytest.raises(InvalidTaskTransition):
        service.transition(first.task_id, TaskState.SUCCEEDED)
    assert service.get(first.task_id).state is TaskState.QUEUED


def test_任务可取消可重试并在重启中断后按提交证据恢复(tmp_path) -> None:
    """只有可恢复故障可重试；中断任务必须依据原子提交证据决定后续状态。"""

    from stock_agent.application.task_service import TaskService
    from stock_agent.domain.task import TaskState

    service = TaskService(tmp_path / "tasks.duckdb")
    retryable = service.submit("市场更新", "daily-cn-20260714-retry")
    service.transition(retryable.task_id, TaskState.VALIDATING)
    service.transition(retryable.task_id, TaskState.RUNNING)
    service.mark_retryable_failure(retryable.task_id, "RATE_LIMITED")
    assert service.get(retryable.task_id).state is TaskState.RETRY_WAIT
    service.retry(retryable.task_id)
    service.cancel(retryable.task_id)
    service.confirm_cancelled(retryable.task_id)
    assert service.get(retryable.task_id).state is TaskState.CANCELLED

    no_commit = service.submit("市场更新", "daily-cn-20260714-no-commit")
    service.transition(no_commit.task_id, TaskState.VALIDATING)
    service.transition(no_commit.task_id, TaskState.RUNNING)
    service.mark_interrupted(no_commit.task_id)
    assert (
        service.recover_interrupted(no_commit.task_id, has_valid_commit=False).state
        is TaskState.FAILED
    )

    committed = service.submit("市场更新", "daily-cn-20260714-committed")
    service.transition(committed.task_id, TaskState.VALIDATING)
    service.transition(committed.task_id, TaskState.RUNNING)
    service.mark_interrupted(committed.task_id)
    assert (
        service.recover_interrupted(committed.task_id, has_valid_commit=True).state
        is TaskState.RETRY_WAIT
    )
