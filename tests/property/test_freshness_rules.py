"""验证跨市场行情新鲜度的纯规则边界。"""

from datetime import UTC, datetime, timedelta

import pytest

from stock_agent.domain.freshness import FreshnessClassificationError, classify_freshness
from stock_agent.domain.market import Market


@pytest.mark.parametrize(
    ("market", "realtime_limit"),
    [
        (Market.CN, 0),
        (Market.HK, 0),
        (Market.US, 0),
        (Market.CN, 5),
        (Market.HK, 15),
        (Market.US, 15),
    ],
)
def test_交易时段在各市场实时精确边界内为实时(market: Market, realtime_limit: int) -> None:
    """各市场年龄等于实时阈值时仍应判为实时行情。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    market_time = collected_at - timedelta(seconds=realtime_limit)

    assert classify_freshness(market, market_time, collected_at, is_open=True) == "REALTIME"


@pytest.mark.parametrize(
    ("market", "age_seconds"),
    [(Market.CN, 6), (Market.HK, 16), (Market.US, 16)],
)
def test_交易时段超过各市场实时边界为近实时(market: Market, age_seconds: int) -> None:
    """实时阈值之外且不超过一分钟的行情应降为近实时。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    market_time = collected_at - timedelta(seconds=age_seconds)

    assert classify_freshness(market, market_time, collected_at, is_open=True) == "NEAR_REALTIME"


@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [(60, "NEAR_REALTIME"), (61, "DELAYED"), (900, "DELAYED"), (901, "STALE")],
)
def test_交易时段通用时效边界(age_seconds: int, expected: str) -> None:
    """一分钟与十五分钟边界必须保持与公共新鲜度契约一致。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    market_time = collected_at - timedelta(seconds=age_seconds)

    assert classify_freshness(Market.CN, market_time, collected_at, is_open=True) == expected


def test_休市时忽略时间年龄并返回休市() -> None:
    """休市行情不能被标为可实时使用。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)

    assert (
        classify_freshness(Market.US, collected_at - timedelta(days=1), collected_at, is_open=False)
        == "CLOSED"
    )


def test_休市时即使市场时间异常也返回休市() -> None:
    """休市状态优先于时间年龄，避免下游把休市行情当成可用行情。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)

    assert (
        classify_freshness(
            Market.CN, collected_at + timedelta(seconds=1), collected_at, is_open=False
        )
        == "CLOSED"
    )


@pytest.mark.parametrize(
    ("market_time", "collected_at"),
    [
        (datetime(2026, 7, 14, 9, 30), datetime(2026, 7, 14, 9, 30, tzinfo=UTC)),
        (
            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            datetime(2026, 7, 14, 9, 30),
        ),
        (
            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        ),
    ],
)
def test_拒绝无时区或负年龄的时间(market_time: datetime, collected_at: datetime) -> None:
    """无时区和未来市场时间都不能伪装成新鲜行情。"""

    with pytest.raises(FreshnessClassificationError):
        classify_freshness(Market.CN, market_time, collected_at, is_open=True)
