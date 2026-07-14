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


@pytest.mark.parametrize(
    ("market", "realtime_limit"),
    [(Market.CN, 5), (Market.HK, 15), (Market.US, 15)],
)
@pytest.mark.parametrize(
    ("age_seconds", "expected"),
    [
        (0, "REALTIME"),
        ("realtime_limit", "REALTIME"),
        ("realtime_limit_plus_one", "NEAR_REALTIME"),
        (60, "NEAR_REALTIME"),
        (61, "DELAYED"),
        (900, "DELAYED"),
        (901, "STALE"),
    ],
)
def test_三市场完整新鲜度边界严格转换(
    market: Market, realtime_limit: int, age_seconds: int | str, expected: str
) -> None:
    """三市场在全部公共阈值和各自实时阈值处必须精确分级。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    resolved_age_seconds = {
        "realtime_limit": realtime_limit,
        "realtime_limit_plus_one": realtime_limit + 1,
    }.get(age_seconds, age_seconds)
    assert isinstance(resolved_age_seconds, int)

    market_time = collected_at - timedelta(seconds=resolved_age_seconds)

    assert classify_freshness(market, market_time, collected_at, is_open=True) == expected


@pytest.mark.parametrize(
    ("market", "age_seconds", "expected"),
    [
        (Market.CN, 4.000001, "REALTIME"),
        (Market.CN, 5.000001, "NEAR_REALTIME"),
        (Market.CN, 60.000001, "DELAYED"),
        (Market.CN, 900.000001, "STALE"),
        (Market.HK, 14.000001, "REALTIME"),
        (Market.HK, 15.000001, "NEAR_REALTIME"),
        (Market.HK, 60.000001, "DELAYED"),
        (Market.HK, 900.000001, "STALE"),
        (Market.US, 14.000001, "REALTIME"),
        (Market.US, 15.000001, "NEAR_REALTIME"),
        (Market.US, 60.000001, "DELAYED"),
        (Market.US, 900.000001, "STALE"),
    ],
)
def test_带微秒年龄向上取整后不得跨越新鲜度阈值(
    market: Market, age_seconds: float, expected: str
) -> None:
    """超过任一秒级阈值的微秒部分必须向上取整，不能被截断为更高新鲜度。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    market_time = collected_at - timedelta(seconds=age_seconds)

    assert classify_freshness(market, market_time, collected_at, is_open=True) == expected


def test_休市时忽略时间年龄并返回休市() -> None:
    """休市行情不能被标为可实时使用。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)

    assert (
        classify_freshness(Market.US, collected_at - timedelta(days=1), collected_at, is_open=False)
        == "CLOSED"
    )


def test_休市时未来市场时间仍被拒绝() -> None:
    """未来市场时间无论开闭市都不能绕过时间一致性校验。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)

    with pytest.raises(FreshnessClassificationError):
        classify_freshness(
            Market.CN, collected_at + timedelta(seconds=1), collected_at, is_open=False
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


@pytest.mark.parametrize(
    ("market", "age_seconds"),
    [(Market.CN, 0), (Market.HK, 86_400), (Market.US, 900)],
)
def test_交易日历关闭时有效时间无论年龄均为休市(
    market: Market, age_seconds: int
) -> None:
    """交易日历关闭优先于有效年龄的任何新鲜度分级。"""

    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
    market_time = collected_at - timedelta(seconds=age_seconds)

    assert classify_freshness(market, market_time, collected_at, is_open=False) == "CLOSED"


@pytest.mark.parametrize(
    ("market", "market_time", "collected_at"),
    [
        (
            Market.CN,
            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        ),
        (
            Market.HK,
            datetime(2026, 7, 14, 9, 30),
            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
        ),
        (
            Market.US,
            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
            datetime(2026, 7, 14, 9, 30),
        ),
    ],
)
def test_交易日历关闭时仍拒绝未来无时区或负年龄时间(
    market: Market, market_time: datetime, collected_at: datetime
) -> None:
    """休市状态不能绕过未来时间、无时区和负年龄的基本时间校验。"""

    with pytest.raises(FreshnessClassificationError):
        classify_freshness(market, market_time, collected_at, is_open=False)


@pytest.mark.parametrize(
    ("state", "expected"),
    [
        ("REALTIME", True),
        ("NEAR_REALTIME", True),
        ("DELAYED", False),
        ("STALE", False),
        ("CLOSED", False),
    ],
)
def test_仅有效实时或近实时行情可用于当前预测(state: str, expected: bool) -> None:
    """延迟、过期和休市行情不得进入面向当前预测的研究输入。"""

    from stock_agent.domain import freshness

    assert freshness.is_usable_for_current_prediction(state) is expected
