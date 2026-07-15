"""验证训练、回测和预测仅使用预测时点已可获得的数据。"""

from datetime import UTC, datetime, timedelta

import pytest


def test_特征晚于预测时点必须拒绝() -> None:
    """未来特征进入训练或预测即构成不可接受的数据泄漏。"""

    from stock_agent.domain.market_rules import PointInTimeViolation, ensure_available_at

    prediction_time = datetime(2026, 7, 14, tzinfo=UTC)
    with pytest.raises(PointInTimeViolation):
        ensure_available_at(prediction_time, prediction_time + timedelta(seconds=1), "特征")


def test_不同币种缺失同一时点汇率必须不可比较() -> None:
    """跨市场比较缺失对应版本汇率时只能降级为不可比较。"""

    from stock_agent.domain.market_rules import NotComparableError, compare_currency_at

    with pytest.raises(NotComparableError):
        compare_currency_at(100.0, "CNY", 10.0, "USD", exchange_rate=None)


def test_非交易日和晚生效公司行动不得用于历史计算() -> None:
    """日历和公司行动均须使用分析时点已经生效的版本。"""
    from stock_agent.domain.market_rules import (
        CompanyAction,
        PointInTimeViolation,
        TradingCalendar,
        effective_actions,
    )

    at = datetime(2026, 7, 14, tzinfo=UTC)
    calendar = TradingCalendar(
        market="CN",
        version_id="calendar-cn-20260714-v1",
        trading_days={datetime(2026, 7, 14).date()},
    )
    assert not calendar.is_trading_day(datetime(2026, 7, 15).date())
    with pytest.raises(PointInTimeViolation):
        effective_actions(
            [
                CompanyAction(
                    action_id="split-000001-20260715",
                    action_type="split",
                    effective_at=at + timedelta(days=1),
                    version_id="action-cn-20260715-v1",
                    source_id="authorized-source",
                )
            ],
            at,
        )


def test_交易日历和公司行动必须携带可追溯版本() -> None:
    """历史分析必须能还原当时采用的市场规则与公司行动版本。"""

    from stock_agent.domain.market_rules import CompanyAction, TradingCalendar

    calendar = TradingCalendar(
        market="CN",
        version_id="calendar-cn-20260714-v1",
        trading_days={datetime(2026, 7, 14).date()},
    )
    action = CompanyAction(
        action_id="split-000001-20260714",
        action_type="split",
        effective_at=datetime(2026, 7, 14, tzinfo=UTC),
        version_id="action-cn-20260714-v2",
        source_id="authorized-source",
    )

    assert calendar.version_id == "calendar-cn-20260714-v1"
    assert action.version_id == "action-cn-20260714-v2"


def test_汇率晚于分析时点可得时必须阻止跨币种比较() -> None:
    """汇率虽然带有市场时间，但晚到数据仍会造成未来数据泄漏。"""

    from stock_agent.domain.market_rules import (
        ExchangeRateQuote,
        PointInTimeViolation,
        compare_currency_at,
    )

    analysis_time = datetime(2026, 7, 14, 8, tzinfo=UTC)
    quote = ExchangeRateQuote(
        base_currency="USD",
        quote_currency="CNY",
        rate=7.2,
        market_time=analysis_time,
        available_at=analysis_time + timedelta(minutes=1),
        version_id="fx-usd-cny-20260714-v1",
    )

    with pytest.raises(PointInTimeViolation):
        compare_currency_at(100.0, "CNY", 10.0, "USD", quote, analysis_time)
