"""验证 A 股、港股、美股多市场行情适配器契约。"""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from stock_agent.domain.market import Market


def test_三市场适配器声明代码时区币种和授权边界() -> None:
    """适配器目录必须分别声明三大市场的来源、时区、币种和凭据要求。"""

    from stock_agent.adapters.market_data.multi_market import MultiMarketAdapterCatalog

    catalog = MultiMarketAdapterCatalog.default()

    cn = catalog.primary_for(Market.CN)
    hk = catalog.primary_for(Market.HK)
    us = catalog.primary_for(Market.US)

    assert cn.source_id == "sina"
    assert cn.requires_credentials is False
    assert cn.timezone == "Asia/Shanghai"
    assert cn.currency == "CNY"
    assert hk.timezone == "Asia/Hong_Kong"
    assert hk.currency == "HKD"
    assert us.source_id == "finnhub"
    assert us.requires_credentials is True
    assert us.currency == "USD"


def test_无凭据美股适配器必须降级且不得伪装实时() -> None:
    """Finnhub 未授权时只能返回受限降级状态，不能产生行情数字。"""

    from stock_agent.adapters.market_data.multi_market import MultiMarketAdapterCatalog

    catalog = MultiMarketAdapterCatalog.default()
    decision = catalog.availability_for(Market.US, authorized_sources=frozenset())

    assert decision.available is False
    assert decision.freshness_state == "STALE"
    assert decision.reason_code == "CREDENTIAL_REQUIRED"
    assert "Finnhub" in decision.message_zh


def test_来源冲突必须拒绝自动合并行情数字() -> None:
    """同一市场存在多个候选来源时，必须显式报冲突，禁止自动挑选数字。"""

    from stock_agent.adapters.market_data.multi_market import (
        AdapterDescriptor,
        SourceConflictError,
        SourceConflictResolver,
    )

    resolver = SourceConflictResolver()

    with pytest.raises(SourceConflictError, match="来源冲突"):
        resolver.select_primary(
            Market.CN,
            (
                AdapterDescriptor.sina_cn(),
                AdapterDescriptor(
                    source_id="cn-backup",
                    market=Market.CN,
                    timezone="Asia/Shanghai",
                    currency="CNY",
                    requires_credentials=False,
                    max_requests_per_minute=60,
                ),
            ),
        )


def test_限频触发时返回可审计降级而不是部分行情() -> None:
    """适配器超过请求频率时必须拒绝本批次，避免返回不完整行情。"""

    from stock_agent.adapters.market_data.multi_market import RateLimiter, RateLimitExceededError

    limiter = RateLimiter(max_requests_per_minute=2)
    now = datetime(2026, 7, 16, 10, 0, tzinfo=ZoneInfo("Asia/Shanghai"))

    limiter.record("sina", now)
    limiter.record("sina", now)

    with pytest.raises(RateLimitExceededError, match="限频"):
        limiter.record("sina", now)
