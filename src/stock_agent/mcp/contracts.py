"""定义本机 MCP 工具必须遵守的结构化契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from stock_agent.contracts.common import Freshness, ResultEnvelope, SourceProvenance

PayloadT = TypeVar("PayloadT")
MCP_CONTRACT_VERSION = "1.0"
MCP_TOOL_VERSION = "1.0.0"

ReadonlyToolName = Literal[
    "market.get_status",
    "market.get_quotes",
    "market.get_history",
    "sector.list",
    "sector.get_metrics",
    "sector.get_rotation",
    "custom_sector.get",
    "custom_sector.get_members_at",
    "prediction.get",
    "prediction.list_history",
    "backtest.get",
    "backtest.start_readonly",
    "report.get",
    "report.list",
    "task.get",
    "task.list",
    "task.start_analysis",
    "model.get",
    "model.list",
    "model.get_evaluation",
]

READONLY_RESEARCH_TOOLS: frozenset[str] = frozenset(
    {
        "market.get_status",
        "market.get_quotes",
        "market.get_history",
        "sector.list",
        "sector.get_metrics",
        "sector.get_rotation",
        "custom_sector.get",
        "custom_sector.get_members_at",
        "prediction.get",
        "prediction.list_history",
        "backtest.get",
        "backtest.start_readonly",
        "report.get",
        "report.list",
        "task.get",
        "task.list",
        "task.start_analysis",
        "model.get",
        "model.list",
        "model.get_evaluation",
    }
)

START_TOOL_NAMES: frozenset[str] = frozenset({"task.start_analysis", "backtest.start_readonly"})
FORBIDDEN_PARAM_KEYS: frozenset[str] = frozenset(
    {
        "sql",
        "query",
        "file",
        "file_path",
        "path",
        "url",
        "uri",
        "credential",
        "credentials",
        "api_key",
        "token",
        "password",
        "broker",
        "broker_id",
    }
)


class MCPToolRegistry(BaseModel):
    """登记首个阶段允许暴露给大模型编排层的本机研究工具。"""

    tool_names: frozenset[str]

    @classmethod
    def default(cls) -> MCPToolRegistry:
        """返回宪法允许的默认只读研究工具集合。"""

        return cls(tool_names=READONLY_RESEARCH_TOOLS)

    def contains(self, tool_name: str) -> bool:
        """判断工具是否属于当前白名单。"""

        return tool_name in self.tool_names


class MCPPageRequest(BaseModel):
    """限制 MCP 集合查询规模，避免无界扫描本地数据。"""

    model_config = ConfigDict(extra="forbid")

    page_size: int = Field(default=50, ge=1, le=200)
    page_cursor: str | None = None


class MCPExecutionOptions(BaseModel):
    """声明 MCP 调用超时和启动类任务幂等键。"""

    model_config = ConfigDict(extra="forbid")

    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class MCPToolRequest(BaseModel):
    """所有 MCP 工具输入必须是严格版本化对象。"""

    model_config = ConfigDict(extra="forbid")

    contract_version: str = Field(pattern=r"^1\.0$")
    request_id: UUID
    tool_name: str = Field(min_length=1)
    params: dict[str, Any] = Field(default_factory=dict)
    page: MCPPageRequest | None = None
    options: MCPExecutionOptions = Field(default_factory=MCPExecutionOptions)

    @model_validator(mode="after")
    def 验证工具请求边界(self) -> MCPToolRequest:
        """拒绝越权参数，并要求启动类工具携带幂等键。"""

        forbidden = FORBIDDEN_PARAM_KEYS.intersection(self.params)
        if forbidden:
            raise ValueError(f"MCP 工具参数包含越权字段：{sorted(forbidden)}")
        if self.tool_name in START_TOOL_NAMES and not self.options.idempotency_key:
            raise ValueError("启动类 MCP 工具必须携带 idempotency_key")
        return self


class MCPToolResult(ResultEnvelope[PayloadT], Generic[PayloadT]):
    """承载 MCP 工具成功结果，数字必须保留工具元数据和本地溯源。"""

    tool_name: str = Field(min_length=1)
    tool_version: str = Field(min_length=1)
    parameter_digest: str = Field(min_length=1)
    called_at: datetime

    @model_validator(mode="after")
    def 验证工具元数据(self) -> MCPToolResult[PayloadT]:
        """确保 MCP 工具结果来自已登记工具并带有版本元数据。"""

        if self.tool_name not in READONLY_RESEARCH_TOOLS:
            raise ValueError("MCP 工具结果必须来自已登记的只读研究工具")
        if not self.tool_version.strip() or not self.parameter_digest.strip():
            raise ValueError("MCP 工具结果必须包含工具版本和参数摘要")
        return self


class MCPPredictionToolResult(MCPToolResult[PayloadT], Generic[PayloadT]):
    """预测工具结果必须额外绑定预测版本和模型版本。"""

    prediction_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def 验证预测工具版本(self) -> MCPPredictionToolResult[PayloadT]:
        """防止缺少模型或预测版本的概率数字进入解释层。"""

        if not self.tool_name.startswith("prediction."):
            raise ValueError("预测 MCP 结果只能用于 prediction.* 工具")
        return self


__all__ = [
    "FORBIDDEN_PARAM_KEYS",
    "MCP_CONTRACT_VERSION",
    "MCP_TOOL_VERSION",
    "MCPExecutionOptions",
    "MCPPageRequest",
    "MCPPredictionToolResult",
    "MCPToolRegistry",
    "MCPToolRequest",
    "MCPToolResult",
    "READONLY_RESEARCH_TOOLS",
    "ReadonlyToolName",
    "START_TOOL_NAMES",
    "Freshness",
    "SourceProvenance",
]
