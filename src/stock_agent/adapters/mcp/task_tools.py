"""MCP 非破坏性任务启动工具适配器。"""

from __future__ import annotations

from uuid import UUID

from stock_agent.mcp.runtime import MCPRuntime, MCPRuntimeTaskResult


class MCPTaskToolAdapter:
    """把 MCP 启动类工具请求转交给受控运行时。"""

    def __init__(self, runtime: MCPRuntime) -> None:
        """注入运行时，便于桌面端和测试使用相同边界。"""

        self._runtime = runtime

    def start_analysis(
        self,
        request_id: UUID,
        idempotency_key: str,
        params: dict[str, object],
    ) -> MCPRuntimeTaskResult:
        """启动每日分析等非破坏性研究任务。"""

        return self._runtime.start_task(
            tool_name="task.start_analysis",
            request_id=request_id,
            idempotency_key=idempotency_key,
            params=params,
        )
