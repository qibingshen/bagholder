"""验证行情适配器协议与注册表不依赖具体供应商。"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from stock_agent.adapters.market_data.base import (
    MarketDataAdapter,
    NormalizedQuote,
    SourceCapability,
)
from stock_agent.adapters.market_data.registry import (
    DuplicateSourceError,
    MarketDataRegistry,
    UnknownSourceError,
)
from stock_agent.contracts.common import Freshness


class 演示行情适配器:
    """用于验证注册表的最小适配器，不连接任何外部服务。"""

    capability = SourceCapability(
        source_id="演示来源",
        markets=("CN",),
        credential_required=False,
        supports_realtime=True,
    )

    def fetch_quotes(self, codes: list[str], collected_at: datetime) -> list[NormalizedQuote]:
        """返回空结果，避免测试引入供应商实现。"""

        return []


def test_注册表可以注册并按来源标识获取适配器() -> None:
    """核心服务只通过通用协议和来源标识访问行情适配器。"""

    registry = MarketDataRegistry()
    adapter: MarketDataAdapter = 演示行情适配器()

    registry.register(adapter)

    assert registry.get("演示来源") is adapter


def test_注册表拒绝重复来源标识() -> None:
    """同一来源只能注册一次，避免运行时覆盖已选定的行情来源。"""

    registry = MarketDataRegistry()
    registry.register(演示行情适配器())

    with pytest.raises(DuplicateSourceError, match="演示来源"):
        registry.register(演示行情适配器())


def test_注册表拒绝未知来源标识() -> None:
    """请求未知来源时返回明确领域错误，而不是泄漏字典实现细节。"""

    with pytest.raises(UnknownSourceError, match="未知来源"):
        MarketDataRegistry().get("未知来源")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("market_time", None),
        ("collected_at", None),
        ("data_version", ""),
    ],
)
def test_规范化行情拒绝缺少关键时间或数据版本(field: str, value: datetime | str | None) -> None:
    """缺少市场时间、采集时间或版本的供应商数据不能构造成统一行情。"""

    quote = {
        "security_id": "CN:600000",
        "price": 10.25,
        "source_id": "演示来源",
        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        "data_version": "演示版本-1",
        "freshness": Freshness(state="REALTIME", age_seconds=1),
    }
    quote[field] = value

    with pytest.raises(ValidationError):
        NormalizedQuote(**quote)


@pytest.mark.parametrize("field", ["market_time", "collected_at"])
def test_规范化行情拒绝不带时区的时间(field: str) -> None:
    """行情时间必须含时区，避免跨市场比较时把本地时间误认为同一时点。"""

    quote = {
        "security_id": "CN:600000",
        "price": 10.25,
        "source_id": "演示来源",
        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        "data_version": "演示版本-1",
        "freshness": Freshness(state="REALTIME", age_seconds=1),
    }
    quote[field] = datetime(2026, 7, 14, 9, 30)

    with pytest.raises(ValidationError):
        NormalizedQuote(**quote)


def test_规范化行情拒绝缺少单条行情新鲜度() -> None:
    """每条行情必须带有新鲜度，供核心服务在使用前执行时效性控制。"""

    with pytest.raises(ValidationError, match="freshness"):
        NormalizedQuote(
            security_id="CN:600000",
            price=10.25,
            source_id="演示来源",
            market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
            data_version="演示版本-1",
        )


def test_规范化行情接受严格的新鲜度状态() -> None:
    """行情新鲜度使用现有公共契约，避免各来源自定义不兼容状态。"""

    quote = NormalizedQuote(
        security_id="CN:600000",
        price=10.25,
        source_id="演示来源",
        market_time=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        collected_at=datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
        data_version="演示版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=1),
    )

    assert quote.freshness.state == "REALTIME"


def test_来源能力拒绝空市场范围() -> None:
    """来源必须明确声明至少一个覆盖市场，避免注册不可用的适配器。"""

    with pytest.raises(ValidationError, match="markets"):
        SourceCapability(
            source_id="演示来源",
            markets=(),
            credential_required=False,
            supports_realtime=True,
        )
