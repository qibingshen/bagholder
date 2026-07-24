from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError


def test_研究决策必须携带证据和版本() -> None:
    from bagholder.contracts.live_trading import ResearchDecision

    with pytest.raises(ValidationError):
        ResearchDecision(
            decision_id=uuid4(),
            security_key="CN:600000.SH",
            as_of=datetime.now(UTC),
            action="BUY",
            confidence=Decimal("0.8"),
            evidence_ids=[],
            data_version="",
            model_version="ta-astock",
        )


def test_实盘订单提案必须包含有效期() -> None:
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        OrderProposal,
        OrderSide,
    )

    now = datetime.now(UTC)
    proposal = OrderProposal(
        proposal_id=uuid4(),
        decision_id=uuid4(),
        account_id="citic-main",
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10.20"),
        mode=ExecutionMode.LIVE,
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )

    assert proposal.quantity == 100


def test_过期时间不能早于创建时间() -> None:
    from bagholder.contracts.live_trading import ExecutionMode, OrderProposal, OrderSide

    now = datetime.now(UTC)
    with pytest.raises(ValidationError, match="有效期"):
        OrderProposal(
            proposal_id=uuid4(),
            decision_id=uuid4(),
            account_id="citic-main",
            security_key="CN:600000.SH",
            side=OrderSide.BUY,
            quantity=100,
            limit_price=Decimal("10.20"),
            mode=ExecutionMode.LIVE,
            created_at=now,
            expires_at=now - timedelta(seconds=1),
        )
