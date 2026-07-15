"""定义本地量化事实在各进程之间传递时必须携带的公共契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar
from uuid import UUID

from pydantic import BaseModel, Field, model_validator

PayloadT = TypeVar("PayloadT")
FreshnessState = Literal["REALTIME", "NEAR_REALTIME", "DELAYED", "STALE", "CLOSED"]


class Freshness(BaseModel):
    """描述行情可用性，过期状态必须由上层阻断当前预测。"""

    state: FreshnessState
    age_seconds: int = Field(ge=0)


class SourceProvenance(BaseModel):
    """记录可回溯到本地工件的数据来源与时点。"""

    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    data_version: str = Field(min_length=1)
    artifact_hash: str = Field(min_length=64, max_length=128)


class PageRequest(BaseModel):
    """限制集合查询规模，防止 MCP 或界面触发无界本地扫描。"""

    page_size: int = Field(default=50, ge=1, le=200)
    page_cursor: str | None = None


class RequestExecutionOptions(BaseModel):
    """统一传递请求超时和幂等键，服务端仍可施加更严格的工具上限。"""

    timeout_ms: int = Field(default=5_000, ge=1, le=30_000)
    idempotency_key: str | None = Field(default=None, min_length=1, max_length=128)


class ErrorEnvelope(BaseModel):
    """仅传递可安全展示的错误信息，绝不包含堆栈或凭据。"""

    code: str = Field(min_length=1)
    message_zh: str = Field(min_length=1)
    retryable: bool
    correlation_id: UUID
    safe_recovery_action: str = Field(min_length=1)
    partial_result_id: UUID | None = None


class ResultEnvelope(BaseModel, Generic[PayloadT]):
    """承载可展示量化事实；缺失溯源时拒绝创建结果。"""

    contract_version: str = Field(min_length=1)
    result_id: UUID
    request_id: UUID
    generated_at: datetime
    data_as_of: datetime
    data_version: str = Field(min_length=1)
    freshness: Freshness
    provenance: list[SourceProvenance]
    warnings: list[str] = Field(default_factory=list)
    payload: PayloadT

    @model_validator(mode="after")
    def 验证溯源与版本(self) -> ResultEnvelope[PayloadT]:
        """防止缺少来源或跨版本来源的数字绕过本地事实链。"""

        if not self.provenance:
            raise ValueError("量化结果必须至少包含一条来源溯源记录")
        if any(item.data_version != self.data_version for item in self.provenance):
            raise ValueError("结果数据版本必须与全部溯源记录一致")
        return self
