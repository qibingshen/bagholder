"""导出供应商无关的行情适配器协议和注册表。"""

from .base import MarketDataAdapter, NormalizedQuote, SourceCapability
from .registry import DuplicateSourceError, MarketDataRegistry, UnknownSourceError

__all__ = [
    "DuplicateSourceError",
    "MarketDataAdapter",
    "MarketDataRegistry",
    "NormalizedQuote",
    "SourceCapability",
    "UnknownSourceError",
]
