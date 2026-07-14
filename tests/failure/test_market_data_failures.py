"""验证新浪代码规则拒绝不安全或不受支持的身份。"""

import pytest

from stock_agent.adapters.market_data.sina_codes import (
    UnsupportedSinaCodeError,
    normalize_sina_code,
)
from stock_agent.domain.market import InstrumentIdentity, Market


@pytest.mark.parametrize(
    ("exchange", "display_code", "expected"),
    [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
)
def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
    """新浪 A 股请求代码必须携带正确交易所前缀。"""

    identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")

    assert normalize_sina_code(identity) == expected


@pytest.mark.parametrize(
    "identity",
    [
        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
        InstrumentIdentity(Market.CN, "BSE", "830000", "CNY"),
        InstrumentIdentity(Market.CN, "SSE", "60000", "CNY"),
        InstrumentIdentity(Market.CN, "SZSE", "0000A1", "CNY"),
        InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
    ],
)
def test_新浪代码规范化拒绝跨市场交易所和非法代码(
    identity: InstrumentIdentity,
) -> None:
    """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""

    with pytest.raises(UnsupportedSinaCodeError):
        normalize_sina_code(identity)
