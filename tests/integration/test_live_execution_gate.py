from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

NOW = datetime(2026, 7, 25, 2, tzinfo=UTC)


class RecordingExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, request, now):
        from bagholder.domain.broker import BrokerOrderReceipt

        self.calls += 1
        return BrokerOrderReceipt(
            account_id=request.proposal.account_id,
            broker_order_id=f"ORDER-{self.calls}",
            accepted=True,
            status="SUBMITTED",
        )


def _request():
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        ExecutionRequest,
        OrderApproval,
        OrderProposal,
        OrderSide,
        RiskVerdict,
    )

    proposal = OrderProposal(
        proposal_id=uuid4(),
        decision_id=uuid4(),
        account_id="citic-main",
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal("10"),
        mode=ExecutionMode.LIVE,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
    )
    return ExecutionRequest(
        request_id=uuid4(),
        idempotency_key="live-0123456789abcdef",
        proposal=proposal,
        risk_verdict=RiskVerdict(
            verdict_id=uuid4(),
            proposal_id=proposal.proposal_id,
            allowed=True,
            rule_version="risk-v1",
            blocked_reasons=[],
            checked_at=NOW,
        ),
        approval=OrderApproval(
            approval_id=uuid4(),
            proposal_id=proposal.proposal_id,
            approver="LOCAL_USER",
            approved=True,
            approved_at=NOW,
            expires_at=NOW + timedelta(minutes=1),
        ),
        correlation_id=uuid4(),
    )


def test_live_不可用时绝不调用模拟执行器() -> None:
    from bagholder.application.execution_service import (
        ExecutionRouter,
        LiveBlockedError,
        LiveGateContext,
    )
    from bagholder.domain.broker import BrokerApiState

    paper = RecordingExecutor()
    live = RecordingExecutor()
    router = ExecutionRouter(paper=paper, live=live)

    with pytest.raises(LiveBlockedError) as captured:
        router.execute(
            request=_request(),
            now=NOW,
            live_context=LiveGateContext(
                system_live_enabled=True,
                account_live_enabled=True,
                broker_api_state=BrokerApiState.API_UNAVAILABLE,
                supports_live_orders=False,
                reconciled=True,
                interactive_confirmation=True,
            ),
        )

    assert captured.value.error_code == "BROKER_API_UNAVAILABLE"
    assert paper.calls == 0
    assert live.calls == 0


def test_live_全部安全门通过后只调用真实执行器() -> None:
    from bagholder.application.execution_service import (
        ExecutionRouter,
        LiveGateContext,
    )
    from bagholder.domain.broker import BrokerApiState

    paper = RecordingExecutor()
    live = RecordingExecutor()
    router = ExecutionRouter(paper=paper, live=live)

    receipt = router.execute(
        request=_request(),
        now=NOW,
        live_context=LiveGateContext(
            system_live_enabled=True,
            account_live_enabled=True,
            broker_api_state=BrokerApiState.READY,
            supports_live_orders=True,
            reconciled=True,
            interactive_confirmation=True,
        ),
    )

    assert receipt.status == "SUBMITTED"
    assert paper.calls == 0
    assert live.calls == 1


def test_本地人工审批必须匹配已通过风控() -> None:
    from bagholder.application.approval_service import ApprovalService

    request = _request()
    approval = ApprovalService().approve_local(
        proposal=request.proposal,
        verdict=request.risk_verdict,
        approved=True,
        now=NOW,
    )

    assert approval.approver == "LOCAL_USER"
    assert approval.approved is True

