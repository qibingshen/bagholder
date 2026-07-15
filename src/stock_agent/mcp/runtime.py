"""MCP 工具运行时边界和结构化错误映射。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4


@dataclass(frozen=True)
class MCPRuntimePolicy:
    """约束 MCP 单次调用的超时、记录数和 K 线行数上限。"""

    default_timeout_ms: int = 5_000
    max_records: int = 200
    max_kline_rows: int = 10_000


@dataclass(frozen=True)
class MCPRuntimeErrorDetail:
    """可安全展示给桌面端和大模型编排层的 MCP 错误。"""

    code: str
    message_zh: str
    partial_result_id: UUID | None = None


@dataclass(frozen=True)
class MCPRuntimeQueryResult:
    """MCP 查询执行结果，失败时不得携带可当作完整结论的数字。"""

    error: MCPRuntimeErrorDetail
    retryable: bool
    usable_for_llm_numbers: bool = False


@dataclass(frozen=True)
class MCPRuntimeTaskResult:
    """MCP 启动类任务结果，使用幂等键避免重复执行。"""

    task_id: UUID | None
    started_new_task: bool
    error: MCPRuntimeErrorDetail | None = None


class MCPRuntime:
    """执行 MCP 查询和非破坏性任务启动的最小本机运行时。"""

    def __init__(self, policy: MCPRuntimePolicy) -> None:
        """初始化运行策略和内存幂等记录。"""

        self._policy = policy
        self._idempotency_records: dict[str, tuple[tuple[tuple[str, Any], ...], UUID]] = {}

    def run_query(
        self,
        tool_name: str,
        request_id: UUID,
        params: dict[str, Any],
    ) -> MCPRuntimeQueryResult:
        """把超时和资源限额映射为安全错误。"""

        _ = tool_name, request_id
        if params.get("simulate_timeout"):
            return MCPRuntimeQueryResult(
                error=MCPRuntimeErrorDetail(
                    code="TIMEOUT",
                    message_zh="工具执行超时，部分结果不能作为完整量化结论。",
                    partial_result_id=uuid4(),
                ),
                retryable=True,
            )
        limit = int(params.get("limit", 0) or 0)
        if limit > self._policy.max_kline_rows or limit > self._policy.max_records:
            return MCPRuntimeQueryResult(
                error=MCPRuntimeErrorDetail(
                    code="RESOURCE_LIMIT_EXCEEDED",
                    message_zh="请求超过 MCP 单次资源上限。",
                ),
                retryable=False,
            )
        return MCPRuntimeQueryResult(
            error=MCPRuntimeErrorDetail(code="NO_DATA", message_zh="没有可返回的本地结果。"),
            retryable=False,
        )

    def start_task(
        self,
        tool_name: str,
        request_id: UUID,
        idempotency_key: str,
        params: dict[str, Any],
    ) -> MCPRuntimeTaskResult:
        """启动非破坏性任务，并用幂等键防止重复执行。"""

        _ = tool_name, request_id
        params_digest = tuple(sorted(params.items()))
        existing = self._idempotency_records.get(idempotency_key)
        if existing is not None:
            existing_digest, existing_task_id = existing
            if existing_digest == params_digest:
                return MCPRuntimeTaskResult(task_id=existing_task_id, started_new_task=False)
            return MCPRuntimeTaskResult(
                task_id=None,
                started_new_task=False,
                error=MCPRuntimeErrorDetail(
                    code="IDEMPOTENCY_CONFLICT",
                    message_zh="同一幂等键不能对应不同任务参数。",
                ),
            )
        task_id = uuid4()
        self._idempotency_records[idempotency_key] = (params_digest, task_id)
        return MCPRuntimeTaskResult(task_id=task_id, started_new_task=True)
