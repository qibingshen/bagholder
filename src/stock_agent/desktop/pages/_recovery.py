"""校验页面恢复所需的本地事实，禁止普通状态字符串伪造恢复。"""

from __future__ import annotations

from datetime import UTC, datetime

from stock_agent.application.market_service import MarketStatus


def is_trusted_recovery_fact(market_status: MarketStatus | None) -> bool:
    """仅接受字段完整、已验证、带时区且未指向未来的本地市场事实。"""

    if not isinstance(market_status, MarketStatus) or not market_status.is_verified:
        return False

    try:
        source_id = market_status.source_id.strip()
        data_version = market_status.data_version.strip()
        market_time = market_status.market_time
        collected_at = market_status.collected_at
    except (AttributeError, TypeError):
        return False

    if (
        not source_id
        or not data_version
        or not _is_aware(market_time)
        or not _is_aware(collected_at)
    ):
        return False
    if market_time > collected_at:
        return False

    now = datetime.now(tz=UTC)
    return market_time.astimezone(UTC) <= now and collected_at.astimezone(UTC) <= now


def _is_aware(value: object) -> bool:
    """判断时间是否带有可审计的时区信息。"""

    return (
        isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None
    )
