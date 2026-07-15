"""提供桌面与本机 MCP 共用的受控应用服务入口。"""

from typing import Protocol

from stock_agent.application.task_service import TaskService
from stock_agent.contracts.common import RequestExecutionOptions
from stock_agent.domain.task import TaskRecord


class PermissionDenied(PermissionError):
    """表示调用方不属于本机受控边界，不能创建或查询本地研究任务。"""


class AuditSink(Protocol):
    """最小审计边界；后续持久化审计服务可替换此接口而不扩大调用权限。"""

    def append(self, event_name: str, task: TaskRecord) -> None:
        """追加任务相关审计事件。"""


class InMemoryAuditSink:
    """仅供测试验证审计调用，生产环境必须使用追加式持久化审计服务。"""

    def __init__(self) -> None:
        self.events: list[dict[str, str]] = []

    def append(self, event_name: str, task: TaskRecord) -> None:
        """记录不含凭据的任务标识与类型。"""

        self.events.append(
            {"event_name": event_name, "task_id": str(task.task_id), "task_type": task.task_type}
        )


class LocalApplicationService:
    """统一验证本机权限、请求参数并协调任务持久化与审计。"""

    _allowed_scopes = frozenset({"local-desktop", "local-mcp"})

    def __init__(self, task_service: TaskService, audit_sink: AuditSink) -> None:
        self._task_service = task_service
        self._audit_sink = audit_sink

    def start_analysis(
        self,
        caller_scope: str,
        task_type: str,
        options: RequestExecutionOptions,
    ) -> TaskRecord:
        """创建可审计的非破坏性研究任务，拒绝远程调用和缺少幂等键的重复风险。"""

        if caller_scope not in self._allowed_scopes:
            raise PermissionDenied("仅允许本机桌面端或本机 MCP 调用本地应用服务")
        if options.idempotency_key is None:
            raise ValueError("启动任务必须提供幂等键")
        task = self._task_service.submit(task_type, options.idempotency_key)
        self._audit_sink.append("task_started", task)
        return task
