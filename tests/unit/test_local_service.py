"""验证本地应用服务不接受远程调用，并在启动任务时写入审计。"""

import pytest


def test_本地服务校验权限和幂等键并审计任务启动(tmp_path) -> None:
    """任务入口必须阻断远程调用和无幂等键请求，合法请求可被追溯。"""

    from stock_agent.application.local_service import (
        InMemoryAuditSink,
        LocalApplicationService,
        PermissionDenied,
    )
    from stock_agent.application.task_service import TaskService
    from stock_agent.contracts.common import RequestExecutionOptions

    audit = InMemoryAuditSink()
    service = LocalApplicationService(TaskService(tmp_path / "tasks.duckdb"), audit)

    with pytest.raises(PermissionDenied):
        service.start_analysis(
            "remote", "市场更新", RequestExecutionOptions(idempotency_key="key-1")
        )
    with pytest.raises(ValueError):
        service.start_analysis("local-desktop", "市场更新", RequestExecutionOptions())

    task = service.start_analysis(
        "local-desktop", "市场更新", RequestExecutionOptions(idempotency_key="key-1")
    )

    assert task.deduplication_key == "key-1"
    assert audit.events == [
        {"event_name": "task_started", "task_id": str(task.task_id), "task_type": "市场更新"}
    ]
