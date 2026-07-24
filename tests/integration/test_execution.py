from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4


def _request():
    from bagholder.contracts.live_trading import (
        ExecutionMode,
        ExecutionRequest,
        OrderApproval,
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
    return ExecutionRequest(
        request_id=uuid4(),
        idempotency_key="idem-0123456789abcdef",
        proposal=proposal,
        risk_verdict=RiskVerdict(
            verdict_id=uuid4(),
            proposal_id=proposal.proposal_id,
            allowed=True,
            rule_version="risk-v1",
            blocked_reasons=[],
            checked_at=now,
        ),
        approval=OrderApproval(
            approval_id=uuid4(),
            proposal_id=proposal.proposal_id,
            approver="LOCAL_USER",
            approved=True,
            approved_at=now,
            expires_at=now + timedelta(minutes=1),
        ),
        correlation_id=uuid4(),
    )


def test_重复幂等键只调用一次券商网关() -> None:
    from bagholder.application.execution_service import LiveExecutionService
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository
    from bagholder.testing.fake_gateway import FakeBrokerGateway

    gateway = FakeBrokerGateway()
    service = LiveExecutionService(InMemoryTradingRepository(), gateway)
    request = _request()

    first = service.submit(request, datetime.now(UTC))
    second = service.submit(request, datetime.now(UTC))

    assert first == second
    assert gateway.submit_call_count == 1


def test_未经批准的请求不会调用网关() -> None:
    from bagholder.application.execution_service import LiveExecutionService
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository
    from bagholder.testing.fake_gateway import FakeBrokerGateway

    gateway = FakeBrokerGateway()
    service = LiveExecutionService(InMemoryTradingRepository(), gateway)
    request = _request()
    request = request.model_copy(
        update={"approval": request.approval.model_copy(update={"approved": False})}
    )

    try:
        service.submit(request, datetime.now(UTC))
    except PermissionError:
        pass
    else:
        raise AssertionError("未经批准的真实订单必须被拒绝")

    assert gateway.submit_call_count == 0


def test_真实执行回执可按券商订单号查询(tmp_path: Path) -> None:
    from bagholder.application.execution_service import LiveExecutionService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore
    from bagholder.testing.fake_gateway import FakeBrokerGateway

    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    service = LiveExecutionService(store, FakeBrokerGateway())

    receipt = service.submit(_request(), datetime.now(UTC))
    order = store.get_order(receipt.broker_order_id)

    assert order["broker_order_id"] == receipt.broker_order_id
    assert order["mode"] == "LIVE"
    assert order["status"] == "SUBMITTED"
