"""验证后台工作失败不会崩溃桌面调用方或污染已验证数据。"""

from errno import ENOSPC


def test_工作失败被隔离为结构化事件且桌面可继续使用(tmp_path) -> None:
    """磁盘不足等后台异常只能使任务失败并产生事件，不能向桌面调用方传播。"""

    from stock_agent.application.task_service import TaskService
    from stock_agent.contracts.worker_events import WorkerEventKind
    from stock_agent.domain.task import TaskState
    from stock_agent.workers.runner import WorkerRunner

    service = TaskService(tmp_path / "tasks.duckdb")
    task = service.submit("市场更新", "worker-disk-full")
    service.transition(task.task_id, TaskState.VALIDATING)
    service.transition(task.task_id, TaskState.RUNNING)

    outcome = WorkerRunner(service).execute(
        task.task_id, lambda: (_ for _ in ()).throw(OSError(ENOSPC, "磁盘空间不足"))
    )

    assert outcome.event.kind is WorkerEventKind.FAILED
    assert outcome.desktop_message == "后台任务失败，桌面应用仍可继续使用。"
    assert service.get(task.task_id).state is TaskState.FAILED


def test_取消请求由工作进程确认而非让桌面线程阻塞(tmp_path) -> None:
    """取消请求必须通过结构化事件确认，避免界面等待后台线程而失去响应。"""

    from stock_agent.application.task_service import TaskService
    from stock_agent.contracts.worker_events import WorkerEventKind
    from stock_agent.domain.task import TaskState
    from stock_agent.workers.runner import WorkerRunner

    service = TaskService(tmp_path / "tasks.duckdb")
    task = service.submit("市场更新", "worker-cancel")
    service.cancel(task.task_id)

    outcome = WorkerRunner(service).confirm_cancellation(task.task_id)

    assert outcome.event.kind is WorkerEventKind.CANCELLED
    assert service.get(task.task_id).state is TaskState.CANCELLED


def test_只有已验证的暂存提交可以使后台任务成功(tmp_path) -> None:
    """工作单元返回的版本证据未经验证时，任务绝不能被标记为成功。"""

    from stock_agent.application.task_service import TaskService
    from stock_agent.contracts.worker_events import WorkerEventKind
    from stock_agent.domain.task import TaskState
    from stock_agent.workers.runner import StagedCommit, WorkerRunner

    service = TaskService(tmp_path / "tasks.duckdb")
    task = service.submit("市场更新", "worker-commit")
    service.transition(task.task_id, TaskState.VALIDATING)
    service.transition(task.task_id, TaskState.RUNNING)

    outcome = WorkerRunner(service).execute(
        task.task_id, lambda: StagedCommit("daily-cn-v1", is_valid=True)
    )

    assert outcome.event.kind is WorkerEventKind.SUCCEEDED
    assert service.get(task.task_id).state is TaskState.SUCCEEDED
