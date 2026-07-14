"""提供行情适配器的显式注册和查找。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

from stock_agent.adapters.market_data.base import NormalizedQuote
from stock_agent.domain.market import Market

from .base import MarketDataAdapter


class DuplicateSourceError(ValueError):
    """表示尝试重复注册同一行情来源。"""


class UnknownSourceError(LookupError):
    """表示请求的行情来源尚未注册。"""


class SourceCapabilityViolationError(ValueError):
    """表示适配器声明能力与实际返回行情不一致。"""


class MarketDataRegistry:
    """保存来源标识到行情适配器的受控映射。"""

    def __init__(self) -> None:
        """初始化空的适配器注册表。"""

        self._adapters: dict[str, MarketDataAdapter] = {}

    def register(self, adapter: MarketDataAdapter) -> None:
        """注册适配器；同一来源标识重复注册时明确拒绝。"""

        source_id = adapter.capability.source_id
        if source_id in self._adapters:
            raise DuplicateSourceError(f"行情来源已注册：{source_id}")
        self._adapters[source_id] = adapter

    def get(self, source_id: str) -> MarketDataAdapter:
        """返回已注册适配器；未知来源时抛出明确领域错误。"""

        try:
            return self._adapters[source_id]
        except KeyError as error:
            raise UnknownSourceError(f"未知行情来源：{source_id}") from error

    def fetch_quotes(
        self, source_id: str, codes: Sequence[str], collected_at: datetime, market: Market
    ) -> Sequence[NormalizedQuote]:
        """只返回与选定来源及市场能力完全一致的一整批行情。"""

        adapter = self.get(source_id)
        if market.value not in adapter.capability.markets:
            raise SourceCapabilityViolationError(f"行情来源不支持市场：{market.value}")
        quotes = adapter.fetch_quotes(codes, collected_at)
        if any(
            quote.source_id != source_id or quote.security_id.market is not market
            for quote in quotes
        ):
            raise SourceCapabilityViolationError("适配器返回了与来源或市场能力不一致的行情")
        return quotes
