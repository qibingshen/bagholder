# 任务 1 复核包（HK 测试补齐）

## 提交
161ffa0 test: cover hk quote freshness boundary
d7b0a4c fix: validate quote freshness by market
f0415b7 fix: require quote freshness
525490b feat: add market data adapter registry

## 统计
 src/stock_agent/adapters/market_data/__init__.py |  13 ++
 src/stock_agent/adapters/market_data/base.py     |  69 ++++++++
 src/stock_agent/adapters/market_data/registry.py |  38 +++++
 tests/contract/test_market_data_contract.py      | 205 +++++++++++++++++++++++
 4 files changed, 325 insertions(+)

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
index 0000000..7cac505
--- /dev/null
+++ b/src/stock_agent/adapters/market_data/base.py
@@ -0,0 +1,69 @@
+"""定义与供应商无关的行情适配器协议。"""
+
+from __future__ import annotations
+
+from collections.abc import Sequence
+from datetime import datetime
+from typing import Protocol
+
+from pydantic import BaseModel, Field, field_validator, model_validator
+
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class SourceCapability(BaseModel):
+    """描述行情来源可提供的市场范围和运行能力。"""
+
+    source_id: str = Field(min_length=1)
+    markets: tuple[str, ...] = Field(min_length=1)
+    credential_required: bool
+    supports_realtime: bool
+
+
+class NormalizedQuote(BaseModel):
+    """承载已规范化且可追溯的单个证券行情。"""
+
+    security_id: InstrumentIdentity
+    price: float
+    source_id: str = Field(min_length=1)
+    market_time: datetime
+    collected_at: datetime
+    data_version: str = Field(min_length=1)
+    freshness: Freshness
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
+    @model_validator(mode="after")
+    def 验证实时行情年龄(self) -> NormalizedQuote:
+        """按证券所属市场限制实时行情的最大年龄。"""
+
+        if self.freshness.state != "REALTIME":
+            return self
+
+        maximum_age_seconds = {
+            Market.CN: 5,
+            Market.HK: 15,
+            Market.US: 15,
+        }[self.security_id.market]
+        if self.freshness.age_seconds > maximum_age_seconds:
+            raise ValueError(f"实时行情年龄不能超过 {maximum_age_seconds} 秒")
+        return self
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
index 0000000..e3fde3a
--- /dev/null
+++ b/tests/contract/test_market_data_contract.py
@@ -0,0 +1,205 @@
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
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+def 市场证券身份(market: Market) -> InstrumentIdentity:
+    """构造仅用于契约测试的完整证券身份。"""
+
+    exchange, currency = {
+        Market.CN: ("SSE", "CNY"),
+        Market.HK: ("HKEX", "HKD"),
+        Market.US: ("NASDAQ", "USD"),
+    }[market]
+    return InstrumentIdentity(
+        market=market,
+        exchange=exchange,
+        display_code="600000",
+        currency=currency,
+    )
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
+        "security_id": 市场证券身份(Market.CN),
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+        "freshness": Freshness(state="REALTIME", age_seconds=1),
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
+        "security_id": 市场证券身份(Market.CN),
+        "price": 10.25,
+        "source_id": "演示来源",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "data_version": "演示版本-1",
+        "freshness": Freshness(state="REALTIME", age_seconds=1),
+    }
+    quote[field] = datetime(2026, 7, 14, 9, 30)
+
+    with pytest.raises(ValidationError):
+        NormalizedQuote(**quote)
+
+
+def test_规范化行情拒绝缺少单条行情新鲜度() -> None:
+    """每条行情必须带有新鲜度，供核心服务在使用前执行时效性控制。"""
+
+    with pytest.raises(ValidationError, match="freshness"):
+        NormalizedQuote(
+            security_id=市场证券身份(Market.CN),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            data_version="演示版本-1",
+        )
+
+
+def test_规范化行情接受严格的新鲜度状态() -> None:
+    """行情新鲜度使用现有公共契约，避免各来源自定义不兼容状态。"""
+
+    quote = NormalizedQuote(
+        security_id=市场证券身份(Market.CN),
+        price=10.25,
+        source_id="演示来源",
+        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        data_version="演示版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=1),
+    )
+
+    assert quote.freshness.state == "REALTIME"
+
+
+def test_来源能力拒绝空市场范围() -> None:
+    """来源必须明确声明至少一个覆盖市场，避免注册不可用的适配器。"""
+
+    with pytest.raises(ValidationError, match="markets"):
+        SourceCapability(
+            source_id="演示来源",
+            markets=(),
+            credential_required=False,
+            supports_realtime=True,
+        )
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
+)
+def test_规范化行情拒绝超过市场实时年龄上限(market: Market, age_seconds: int) -> None:
+    """实时行情超过所属市场上限时，不能进入统一行情契约。"""
+
+    with pytest.raises(ValidationError, match="实时行情"):
+        NormalizedQuote(
+            security_id=市场证券身份(market),
+            price=10.25,
+            source_id="演示来源",
+            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            data_version="演示版本-1",
+            freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
+        )
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 5), (Market.HK, 15), (Market.US, 15)],
+)
+def test_规范化行情接受市场实时年龄上限内的行情(market: Market, age_seconds: int) -> None:
+    """实时行情等于所属市场上限时仍是合法可用的行情。"""
+
+    quote = NormalizedQuote(
+        security_id=市场证券身份(market),
+        price=10.25,
+        source_id="演示来源",
+        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        data_version="演示版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=age_seconds),
+    )
+
+    assert quote.freshness.age_seconds == age_seconds
