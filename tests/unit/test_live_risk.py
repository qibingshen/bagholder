from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest


def _proposal():
    from bagholder.contracts.live_trading import ExecutionMode, OrderProposal, OrderSide

    now = datetime.now(UTC)
    return OrderProposal(
        proposal_id=uuid4(),
        decision_id=uuid4(),
        account_id="citic-main",
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10"),
        mode=ExecutionMode.LIVE,
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )


def _context(**updates):
    from bagholder.domain.risk import LiveRiskContext

    values = {
        "quote_age_seconds": Decimal("1"),
        "reconciled": True,
        "halted": False,
        "security_tradable": True,
        "price_within_limit": True,
        "cash_available": Decimal("100000"),
        "available_to_sell": 1000,
        "net_asset": Decimal("1000000"),
        "current_total_exposure": Decimal("0.20"),
        "current_security_exposure": Decimal("0.01"),
        "current_industry_exposure": Decimal("0.05"),
        "daily_turnover": Decimal("0.01"),
        "daily_pnl": Decimal("0"),
        "peak_drawdown": Decimal("0"),
    }
    values.update(updates)
    return LiveRiskContext(**values)


@pytest.mark.parametrize(
    ("updates", "reason"),
    [
        ({"quote_age_seconds": Decimal("5.001")}, "STALE_QUOTE"),
        ({"reconciled": False}, "ACCOUNT_NOT_RECONCILED"),
        ({"halted": True}, "ACCOUNT_HALTED"),
        ({"security_tradable": False}, "SECURITY_NOT_TRADABLE"),
        ({"price_within_limit": False}, "PRICE_LIMIT_VIOLATION"),
    ],
)
def test_关键事实异常时拒绝真实订单(updates, reason) -> None:
    from bagholder.application.risk_service import LiveRiskService

    verdict = LiveRiskService().evaluate(_proposal(), _context(**updates))

    assert verdict.allowed is False
    assert reason in verdict.blocked_reasons
