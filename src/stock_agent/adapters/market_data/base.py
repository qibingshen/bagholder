"""定义与供应商无关的行情适配器协议。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field, field_validator


class SourceCapability(BaseModel):
    """描述行情来源可提供的市场范围和运行能力。"""

    source_id: str = Field(min_length=1)
    markets: tuple[str, ...]
    credential_required: bool
    supports_realtime: bool


class NormalizedQuote(BaseModel):
    """承载已规范化且可追溯的单个证券行情。"""

    security_id: str = Field(min_length=1)
    price: float
    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    data_version: str = Field(min_length=1)

    @field_validator("market_time", "collected_at")
    @classmethod
    def 验证时间包含时区(cls, value: datetime) -> datetime:
        """拒绝无时区时间，防止跨市场数据按错误时点比较。"""

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("行情时间必须包含时区")
        return value


class MarketDataAdapter(Protocol):
    """定义核心服务获取行情时依赖的最小供应商无关接口。"""

    capability: SourceCapability

    def fetch_quotes(
        self, codes: Sequence[str], collected_at: datetime
    ) -> Sequence[NormalizedQuote]:
        """按证券代码获取已规范化行情，不暴露供应商原始字段。"""
