"""验证三市场身份、时区和币种比较的基础规则。"""

import pytest


def test_证券代码必须与市场共同构成身份() -> None:
    """相同显示代码在不同市场不能被静默视为同一证券。"""

    from stock_agent.domain.market import InstrumentIdentity, Market

    cn = InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="600000", currency="CNY")
    hk = InstrumentIdentity(
        market=Market.HK, exchange="HKEX", display_code="600000", currency="HKD"
    )

    assert cn != hk
    assert cn.market_timezone == "Asia/Shanghai"
    assert hk.market_timezone == "Asia/Hong_Kong"


def test_跨币种比较没有同一时点汇率时必须拒绝() -> None:
    """缺少可用汇率时不得输出伪精确的跨市场比较数字。"""

    from stock_agent.domain.market import CurrencyComparison, MarketRuleError

    with pytest.raises(MarketRuleError, match="汇率"):
        CurrencyComparison.compare(100.0, "CNY", 10.0, "USD", exchange_rate=None)


@pytest.mark.parametrize("display_code", ["00001", "600000"])
def test_港股目录接受五位或六位_ascii_数字代码(display_code: str) -> None:
    """港交所本地目录兼容六位编码，同时保留五位标准显示格式。"""

    from stock_agent.domain.market import InstrumentIdentity, Market

    identity = InstrumentIdentity(Market.HK, "HKEX", display_code, "HKD")

    assert identity.display_code == display_code


@pytest.mark.parametrize("display_code", ["0000", "0000000", "0000A", "００００１"])
def test_港股目录拒绝非五或六位_ascii_数字代码(display_code: str) -> None:
    """港股目录代码不能因兼容性要求而放宽长度或 ASCII 边界。"""

    from stock_agent.domain.market import InstrumentIdentityInput, Market, MarketRuleError

    with pytest.raises(MarketRuleError):
        InstrumentIdentityInput(Market.HK, "HKEX", display_code, "HKD").to_identity()


@pytest.mark.parametrize(
    ("market", "exchange", "display_code", "currency"),
    [
        ("CN", "SSE", "00001", "CNY"),
        ("US", "NASDAQ", "600000", "USD"),
    ],
)
def test_港股目录兼容不放宽其他市场代码规则(
    market: str, exchange: str, display_code: str, currency: str
) -> None:
    """仅港股目录可兼容六位数字，A 股和美股规则必须保持原有边界。"""

    from stock_agent.domain.market import InstrumentIdentityInput, Market, MarketRuleError

    actual_market = Market[market]
    with pytest.raises(MarketRuleError):
        InstrumentIdentityInput(actual_market, exchange, display_code, currency).to_identity()
