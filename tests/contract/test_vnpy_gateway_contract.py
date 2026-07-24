import sys
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
        limit_price=Decimal("10.20"),
        mode=ExecutionMode.LIVE,
        created_at=now,
        expires_at=now + timedelta(minutes=2),
    )
    return ExecutionRequest(
        request_id=uuid4(),
        idempotency_key="vnpy-0123456789abcdef",
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


def _gateway():
    from bagholder.adapters.broker.vnpy_gateway import VnpyBrokerGateway
    from bagholder.integrations.vnpy_client import SubprocessVnpyTransport, VnpyClient

    root = Path(__file__).parents[2]
    secret = b"0123456789abcdef0123456789abcdef"
    transport = SubprocessVnpyTransport(
        python_executable=sys.executable,
        server_path=root / "integrations" / "vnpy" / "server.py",
        gateway_plugin="bagholder_vnpy_fake:create_gateway",
        secret=secret,
        timeout_seconds=5,
    )
    return VnpyBrokerGateway(VnpyClient(secret=secret, transport=transport))


def test_签名子进程协议能够提交真实模式委托() -> None:
    gateway = _gateway()

    receipt = gateway.submit(_request())

    assert receipt.accepted is True
    assert receipt.status == "SUBMITTED"
    assert receipt.broker_order_id.startswith("FAKE-LIVE-")


def test_vnpy_gateway_资金查询转换为_decimal() -> None:
    gateway = _gateway()

    funds = gateway.query_funds("citic-main")

    assert funds["cash_available"] == Decimal("1000000.00")
