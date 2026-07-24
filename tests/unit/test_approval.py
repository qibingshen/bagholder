from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest


def _proposal_and_verdict():
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        OrderProposal,
        OrderSide,
        RiskVerdict,
    )

    now = datetime.now(UTC)
    proposal = OrderProposal(
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
    verdict = RiskVerdict(
        verdict_id=uuid4(),
        proposal_id=proposal.proposal_id,
        allowed=True,
        rule_version="risk-v1",
        blocked_reasons=[],
        checked_at=now,
    )
    return now, proposal, verdict


def test_自动审批要求账户和策略双开关() -> None:
    from bagholder.application.approval_service import ApprovalService, StrategyAuthorization

    now, proposal, verdict = _proposal_and_verdict()
    authorization = StrategyAuthorization(
        account_id="citic-main",
        strategy_id="agent-v1",
        starts_at=now - timedelta(minutes=1),
        expires_at=now + timedelta(hours=1),
    )

    with pytest.raises(PermissionError, match="账户实盘开关"):
        ApprovalService().approve_auto(
            proposal=proposal,
            verdict=verdict,
            strategy_id="agent-v1",
            account_live_enabled=False,
            authorization=authorization,
            now=now,
        )


def test_自动授权不能跨交易日() -> None:
    from bagholder.application.approval_service import ApprovalService, StrategyAuthorization

    now, proposal, verdict = _proposal_and_verdict()
    authorization = StrategyAuthorization(
        account_id="citic-main",
        strategy_id="agent-v1",
        starts_at=now,
        expires_at=now + timedelta(days=1),
    )

    with pytest.raises(ValueError, match="当日失效"):
        ApprovalService().approve_auto(
            proposal=proposal,
            verdict=verdict,
            strategy_id="agent-v1",
            account_live_enabled=True,
            authorization=authorization,
            now=now,
        )
