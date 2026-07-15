"""MCP 只读研究工具目录和结果包装。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from stock_agent.contracts.common import Freshness, SourceProvenance
from stock_agent.mcp.contracts import (
    MCP_TOOL_VERSION,
    READONLY_RESEARCH_TOOLS,
    MCPPredictionToolResult,
    MCPToolRequest,
    MCPToolResult,
)

MCPToolCategory = Literal["market", "prediction", "backtest", "report", "task", "model"]

TOOL_CATEGORIES: dict[str, MCPToolCategory] = {
    "market.get_status": "market",
    "market.get_quotes": "market",
    "market.get_history": "market",
    "prediction.get": "prediction",
    "prediction.list_history": "prediction",
    "backtest.get": "backtest",
    "backtest.start_readonly": "backtest",
    "report.get": "report",
    "report.list": "report",
    "task.get": "task",
    "task.list": "task",
    "task.start_analysis": "task",
    "model.get": "model",
    "model.list": "model",
    "model.get_evaluation": "model",
}


@dataclass(frozen=True)
class MCPToolDescriptor:
    """描述一个 MCP 只读研究工具。"""

    name: str
    category: MCPToolCategory
    destructive: bool = False


@dataclass(frozen=True)
class MCPToolExecutionResult:
    """本地服务返回给 MCP 包装层的结构化结果。"""

    payload: dict[str, Any]
    data_as_of: datetime
    data_version: str
    freshness: Freshness
    provenance: list[SourceProvenance]
    prediction_version: str | None = None
    model_version: str | None = None


class MCPToolCatalog:
    """提供 MCP 工具发现和统一结果包装。"""

    def __init__(self, tools: dict[str, MCPToolDescriptor]) -> None:
        """使用显式工具描述符初始化目录。"""

        self._tools = tools

    @classmethod
    def default(cls) -> MCPToolCatalog:
        """构建首个阶段支持的市场、预测、回测、报告、任务和模型工具目录。"""

        tools = {
            name: MCPToolDescriptor(name=name, category=category)
            for name, category in TOOL_CATEGORIES.items()
            if name in READONLY_RESEARCH_TOOLS
        }
        return cls(tools=tools)

    @property
    def categories(self) -> set[str]:
        """返回目录中覆盖的业务类别。"""

        return {tool.category for tool in self._tools.values()}

    def get(self, tool_name: str) -> MCPToolDescriptor:
        """按名称获取工具描述符，未登记工具直接拒绝。"""

        return self._tools[tool_name]

    def invoke(
        self,
        request: MCPToolRequest,
        local_handler: Callable[[MCPToolRequest], MCPToolExecutionResult],
    ) -> MCPToolResult[dict[str, Any]]:
        """调用本地处理器，并把结果包装成可被大模型引用的 MCP 信封。"""

        descriptor = self.get(request.tool_name)
        local_result = local_handler(request)
        base_kwargs = {
            "contract_version": request.contract_version,
            "tool_name": descriptor.name,
            "tool_version": MCP_TOOL_VERSION,
            "parameter_digest": _digest_params(request.params),
            "result_id": uuid4(),
            "request_id": request.request_id,
            "called_at": datetime.now(UTC),
            "generated_at": datetime.now(UTC),
            "data_as_of": local_result.data_as_of,
            "data_version": local_result.data_version,
            "freshness": local_result.freshness,
            "provenance": local_result.provenance,
            "payload": local_result.payload,
        }
        if descriptor.name.startswith("prediction."):
            return MCPPredictionToolResult[dict[str, Any]](
                **base_kwargs,
                prediction_version=local_result.prediction_version or "",
                model_version=local_result.model_version or "",
            )
        return MCPToolResult[dict[str, Any]](**base_kwargs)


def _digest_params(params: dict[str, Any]) -> str:
    """生成可审计但不暴露证券明细或凭据的参数摘要。"""

    parts: list[str] = []
    for key in sorted(params):
        value = params[key]
        if key in {"symbol", "symbols", "token", "api_key", "password"}:
            value = "<redacted>"
        elif isinstance(value, list):
            value = ",".join(str(item) for item in value)
        parts.append(f"{key}={value}")
    return ";".join(parts)


__all__ = [
    "MCPToolCatalog",
    "MCPToolCategory",
    "MCPToolDescriptor",
    "MCPToolExecutionResult",
    "TOOL_CATEGORIES",
]
