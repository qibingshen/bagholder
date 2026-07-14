"""集中定义跨市场行情新鲜度的纯分类规则。"""

from __future__ import annotations

from datetime import datetime

from stock_agent.contracts.common import FreshnessState
from stock_agent.domain.market import Market


class FreshnessClassificationError(ValueError):
    """表示无法安全计算行情新鲜度的时间错误。"""


def classify_freshness(
    market: Market,
    market_time: datetime,
    collected_at: datetime,
    is_open: bool,
) -> FreshnessState:
    """按市场时点、采集时点和开市状态返回兼容公共契约的新鲜度。"""

    if not is_open:
        return "CLOSED"

    _validate_times(market_time, collected_at)

    age_seconds = (collected_at - market_time).total_seconds()
    realtime_limit = 5 if market is Market.CN else 15
    if age_seconds <= realtime_limit:
        return "REALTIME"
    if age_seconds <= 60:
        return "NEAR_REALTIME"
    if age_seconds <= 900:
        return "DELAYED"
    return "STALE"


def _validate_times(market_time: datetime, collected_at: datetime) -> None:
    """拒绝无时区或市场时点晚于采集时点的时间组合。"""

    if not _is_aware(market_time) or not _is_aware(collected_at):
        raise FreshnessClassificationError("市场时间和采集时间必须包含时区")
    if market_time > collected_at:
        raise FreshnessClassificationError("市场时间不能晚于采集时间")


def _is_aware(value: datetime) -> bool:
    """返回时间是否带有可用 UTC 偏移。"""

    return value.tzinfo is not None and value.utcoffset() is not None
