"""定义与供应商无关的行情适配器协议。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, field_validator, model_validator

from stock_agent.contracts.common import Freshness
from stock_agent.domain.market import InstrumentIdentity, Market


class SourceCapability(BaseModel):
    """描述行情来源可提供的市场范围和运行能力。"""

    source_id: str = Field(min_length=1)
    markets: tuple[str, ...] = Field(min_length=1)
    credential_required: bool
    supports_realtime: bool


class NormalizedQuote(BaseModel):
    """承载已规范化且可追溯的单个证券行情。"""

    security_id: InstrumentIdentity
    price: float
    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    data_version: str = Field(min_length=1)
    freshness: Freshness

    @field_validator("market_time", "collected_at")
    @classmethod
    def 验证时间包含时区(cls, value: datetime) -> datetime:
        """拒绝无时区时间，防止跨市场数据按错误时点比较。"""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("行情时间必须包含时区")
        return value

    @model_validator(mode="after")
    def 验证实时行情年龄(self) -> NormalizedQuote:
        """按证券所属市场限制实时行情的最大年龄。"""

        if self.freshness.state != "REALTIME":
            return self

        maximum_age_seconds = {
            Market.CN: 5,
            Market.HK: 15,
            Market.US: 15,
        }[self.security_id.market]
        if self.freshness.age_seconds > maximum_age_seconds:
            raise ValueError(f"实时行情年龄不能超过 {maximum_age_seconds} 秒")
        return self


class MarketDataAdapter(Protocol):
    """定义核心服务获取行情时依赖的最小供应商无关接口。"""

    capability: SourceCapability

    def fetch_quotes(
        self, codes: Sequence[str], collected_at: datetime
    ) -> Sequence[NormalizedQuote]:
        """按证券代码获取已规范化行情，不暴露供应商原始字段。"""
