# 任务 1 复核包

## 提交
525490b feat: add market data adapter registry

## 统计
 src/stock_agent/adapters/market_data/__init__.py |  13 +++
 src/stock_agent/adapters/market_data/base.py     |  49 +++++++++++
 src/stock_agent/adapters/market_data/registry.py |  38 +++++++++
 tests/contract/test_market_data_contract.py      | 104 +++++++++++++++++++++++
 4 files changed, 204 insertions(+)

## 差异
diff --git a/src/stock_agent/adapters/market_data/__init__.py b/src/stock_agent/adapters/market_data/__init__.py
new file mode 100644
index 0000000..d0fbd33
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/__init__.py
@@ -0,0 +1,13 @@
+"""导出供应商无关的行情适配器协议和注册表。"""
+
+from .base import MarketDataAdapter, NormalizedQuote, SourceCapability
+from .registry import DuplicateSourceError, MarketDataRegistry, UnknownSourceError
+
+__all__ = [
+    "DuplicateSourceError",
+    "MarketDataAdapter",
+    "MarketDataRegistry",
+    "NormalizedQuote",
+    "SourceCapability",
+    "UnknownSourceError",
+]
diff --git a/src/stock_agent/adapters/market_data/base.py b/src/stock_agent/adapters/market_data/base.py
new file mode 100644
index 0000000..d8fde20
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/base.py
@@ -0,0 +1,49 @@
+"""定义与供应商无关的行情适配器协议。"""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from datetime import datetime
+from typing import Protocol
+
+from pydantic import BaseModel, Field, field_validator
+
+
+class SourceCapability(BaseModel):
+    """描述行情来源可提供的市场范围和运行能力。"""
+
+    source_id: str = Field(min_length=1)
+    markets: tuple[str, ...]
+    credential_required: bool
+    supports_realtime: bool
+
+
+class NormalizedQuote(BaseModel):
+    """承载已规范化且可追溯的单个证券行情。"""
+
+    security_id: str = Field(min_length=1)
+    price: float
+    source_id: str = Field(min_length=1)
+    market_time: datetime
+    collected_at: datetime
+    data_version: str = Field(min_length=1)
+
+    @field_validator("market_time", "collected_at")
+    @classmethod
+    def 验证时间包含时区(cls, value: datetime) -> datetime:
+        """拒绝无时区时间，防止跨市场数据按错误时点比较。"""
+
+        if value.tzinfo is None or value.utcoffset() is None:
+            raise ValueError("行情时间必须包含时区")
+        return value
+
+
+class MarketDataAdapter(Protocol):
+    """定义核心服务获取行情时依赖的最小供应商无关接口。"""
+
+    capability: SourceCapability
+
+    def fetch_quotes(
+        self, codes: Sequence[str], collected_at: datetime
+    ) -> Sequence[NormalizedQuote]:
+        """按证券代码获取已规范化行情，不暴露供应商原始字段。"""
diff --git a/src/stock_agent/adapters/market_data/registry.py b/src/stock_agent/adapters/market_data/registry.py
new file mode 100644
index 0000000..3b72f91
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/registry.py
@@ -0,0 +1,38 @@
+"""提供行情适配器的显式注册和查找。"""
+
+from __future__ import annotations
+
+from .base import MarketDataAdapter
+
+
+class DuplicateSourceError(ValueError):
+    """表示尝试重复注册同一行情来源。"""
+
+
+class UnknownSourceError(LookupError):
+    """表示请求的行情来源尚未注册。"""
+
+
+class MarketDataRegistry:
+    """保存来源标识到行情适配器的受控映射。"""
+
+    def __init__(self) -> None:
+        """初始化空的适配器注册表。"""
+
+        self._adapters: dict[str, MarketDataAdapter] = {}
+
+    def register(self, adapter: MarketDataAdapter) -> None:
+        """注册适配器；同一来源标识重复注册时明确拒绝。"""
+
+        source_id = adapter.capability.source_id
+        if source_id in self._adapters:
+            raise DuplicateSourceError(f"行情来源已注册：{source_id}")
+        self._adapters[source_id] = adapter
+
+    def get(self, source_id: str) -> MarketDataAdapter:
+        """返回已注册适配器；未知来源时抛出明确领域错误。"""
+
+        try:
+            return self._adapters[source_id]
+        except KeyError as error:
+            raise UnknownSourceError(f"未知行情来源：{source_id}") from error
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
new file mode 100644
index 0000000..9f5aead
--- /dev/null
+++ b/tests/contract/test_market_data_contract.py
@@ -0,0 +1,104 @@
+"""验证行情适配器协议与注册表不依赖具体供应商。"""
+
+from datetime import UTC, datetime
+
+import pytest
+from pydantic import ValidationError
+
+from stock_agent.adapters.market_data.base import (
+    MarketDataAdapter,
+    NormalizedQuote,
+    SourceCapability,
+)
+from stock_agent.adapters.market_data.registry import (
+    DuplicateSourceError,
+    MarketDataRegistry,
+    UnknownSourceError,
+)
+
+
+class 演示行情适配器:
+    """用于验证注册表的最小适配器，不连接任何外部服务。"""
+
+    capability = SourceCapability(
+        source_id="演示来源",
+        markets=("CN",),
+        credential_required=False,
+        supports_realtime=True,
+    )
+
+    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
+        """返回空结果，避免测试引入供应商实现。"""
+
+        return []
+
+
+def test_注册表可以注册并按来源标识获取适配器() -> None:
+    """核心服务只通过通用协议和来源标识访问行情适配器。"""
+
+    registry = MarketDataRegistry()
+    adapter: MarketDataAdapter = 演示行情适配器()
+
+    registry.register(adapter)
+
+    assert registry.get("演示来源") is adapter
+
+
+def test_注册表拒绝重复来源标识() -> None:
+    """同一来源只能注册一次，避免运行时覆盖已选定的行情来源。"""
+
+    registry = MarketDataRegistry()
+    registry.register(演示行情适配器())
+
+    with pytest.raises(DuplicateSourceError, match="演示来源"):
+        registry.register(演示行情适配器())
+
+
+def test_注册表拒绝未知来源标识() -> None:
+    """请求未知来源时返回明确领域错误，而不是泄漏字典实现细节。"""
+
+    with pytest.raises(UnknownSourceError, match="未知来源"):
+        MarketDataRegistry().get("未知来源")
+
+
+@pytest.mark.parametrize(
+    ("field", "value"),
+    [
+        ("market_time", None),
+        ("collected_at", None),
+        ("data_version", ""),
+    ],
+)
+def test_规范化行情拒绝缺少关键时间或数据版本(field: str, value: datetime | str | None) -> None:
+    """缺少市场时间、采集时间或版本的供应商数据不能构造成统一行情。"""
+
+    quote = {
+        "security_id": "CN:600000",
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+    }
+    quote[field] = value
+
+    with pytest.raises(ValidationError):
+        NormalizedQuote(**quote)
+
+
+@pytest.mark.parametrize("field", ["market_time", "collected_at"])
+def test_规范化行情拒绝不带时区的时间(field: str) -> None:
+    """行情时间必须含时区，避免跨市场比较时把本地时间误认为同一时点。"""
+
+    quote = {
+        "security_id": "CN:600000",
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+    }
+    quote[field] = datetime(2026, 7, 14, 9, 30)
+
+    with pytest.raises(ValidationError):
+        NormalizedQuote(**quote)
