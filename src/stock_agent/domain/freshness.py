"""集中定义跨市场行情新鲜度的纯分类规则。"""

from __future__ import annotations

import math
from datetime import datetime
from typing import TypedDict

from stock_agent.contracts.common import FreshnessState
from stock_agent.domain.market import Market


class FreshnessClassificationError(ValueError):
    """表示无法安全计算行情新鲜度的时间错误。"""


class CurrentPredictionFreshnessFact(TypedDict):
    """当前预测判断所需的行情状态与可验证时点。"""

    state: FreshnessState
    market_time: datetime
    collected_at: datetime
    time_is_verifiable: bool


def is_usable_for_current_prediction(fact: CurrentPredictionFreshnessFact) -> bool:
    """仅允许时点可验证的实时或近实时行情进入当前预测。"""

    if fact.get("time_is_verifiable") is not True:
        return False

    state = fact.get("state")
    if state not in {"REALTIME", "NEAR_REALTIME"}:
        return False

    market_time = fact.get("market_time")
    collected_at = fact.get("collected_at")
    if not isinstance(market_time, datetime) or not isinstance(collected_at, datetime):
        raise FreshnessClassificationError("当前预测新鲜度事实必须包含有效的市场时间和采集时间")

    calculate_age_seconds(market_time, collected_at)
    return True


def require_usable_for_current_prediction(fact: CurrentPredictionFreshnessFact) -> None:
    """强制校验行情能否用于当前预测，并给出不可用的领域原因。"""

    if fact.get("time_is_verifiable") is not True:
        raise FreshnessClassificationError("市场时间不可验证，当前预测不可用")

    market_time = fact.get("market_time")
    collected_at = fact.get("collected_at")
    if not isinstance(market_time, datetime) or not isinstance(collected_at, datetime):
        raise FreshnessClassificationError("当前预测新鲜度事实必须包含有效的市场时间和采集时间")
    calculate_age_seconds(market_time, collected_at)

    state = fact.get("state")
    if state in {"DELAYED", "STALE"}:
        raise FreshnessClassificationError("市场行情过期，当前预测不可用")
    if state == "CLOSED":
        raise FreshnessClassificationError("市场休市，当前预测不可用")
    if state not in {"REALTIME", "NEAR_REALTIME"}:
        raise FreshnessClassificationError("市场行情状态不可用，当前预测不可用")


def classify_freshness(
    market: Market,
    market_time: datetime,
    collected_at: datetime,
    is_open: bool,
) -> FreshnessState:
    """按市场时点、采集时点和开市状态返回兼容公共契约的新鲜度。"""

    _validate_times(market_time, collected_at)

    if not is_open:
        return "CLOSED"

    age_seconds = calculate_age_seconds(market_time, collected_at)
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


def calculate_age_seconds(market_time: datetime, collected_at: datetime) -> int:
    """按真实时点差向上取整为秒，统一各行情路径的年龄口径。"""

    _validate_times(market_time, collected_at)
    return math.ceil((collected_at - market_time).total_seconds())


def _is_aware(value: datetime) -> bool:
    """返回时间是否带有可用 UTC 偏移。"""

    return value.tzinfo is not None and value.utcoffset() is not None
