import hashlib
import sys
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

SECRET = b"0123456789abcdef0123456789abcdef"


def _plugin_sha256() -> str:
    root = Path(__file__).parents[2]
    plugin_path = root / "integrations" / "vnpy" / "bagholder_vnpy_fake.py"
    return hashlib.sha256(plugin_path.read_bytes()).hexdigest()


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


def _transport(tmp_path: Path, *, plugin_sha256: str | None = None):
    from bagholder.integrations.vnpy_client import SubprocessVnpyTransport

    root = Path(__file__).parents[2]
    return SubprocessVnpyTransport(
        python_executable=sys.executable,
        server_path=root / "integrations" / "vnpy" / "server.py",
        gateway_plugin="bagholder_vnpy_fake:create_gateway",
        gateway_plugin_sha256=plugin_sha256 or _plugin_sha256(),
        nonce_store_path=tmp_path / "vnpy-nonces.sqlite3",
        secret=SECRET,
        timeout_seconds=5,
    )


def _gateway(tmp_path: Path):
    from bagholder.adapters.broker.vnpy_gateway import VnpyBrokerGateway
    from bagholder.integrations.vnpy_client import VnpyClient

    return VnpyBrokerGateway(
        VnpyClient(secret=SECRET, transport=_transport(tmp_path))
    )


def test_签名子进程协议能够提交真实模式委托(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)

    receipt = gateway.submit(_request())

    assert receipt.accepted is True
    assert receipt.status == "SUBMITTED"
    assert receipt.broker_order_id.startswith("FAKE-LIVE-")


def test_vnpy_gateway_资金查询转换为_decimal(tmp_path: Path) -> None:
    gateway = _gateway(tmp_path)

    funds = gateway.query_funds("citic-main")

    assert funds["cash_available"] == Decimal("1000000.00")


def test_fake_gateway_暴露完整身份和能力(tmp_path: Path) -> None:
    health = _gateway(tmp_path).health()

    assert health["broker_code"] == "CITIC"
    assert health["account_ids"] == ["citic-main"]
    assert set(health["capabilities"]) == {
        "live_orders",
        "cancel",
        "funds_query",
        "positions_query",
        "orders_query",
        "trades_query",
        "market_data",
    }
    assert health["test_plugin"] is True


def test_受信插件摘要不匹配时拒绝加载(tmp_path: Path) -> None:
    from bagholder.integrations.vnpy_client import VnpyClient, VnpyNodeError

    client = VnpyClient(
        secret=SECRET,
        transport=_transport(tmp_path, plugin_sha256="0" * 64),
    )

    with pytest.raises(VnpyNodeError) as captured:
        client.request("HEALTH", {})

    assert captured.value.error_code == "GATEWAY_PLUGIN_HASH_MISMATCH"


def test_nonce_在不同交易节点进程间也不能重放(tmp_path: Path) -> None:
    from bagholder.integrations.vnpy_protocol import AuthenticatedProtocol

    transport = _transport(tmp_path)
    message = AuthenticatedProtocol(secret=SECRET).sign(
        command="HEALTH",
        payload={},
        nonce="cross-process-replay-nonce",
        now=datetime.now(UTC),
    )

    first = transport.send(message)
    second = transport.send(message)

    assert first["ok"] is True
    assert second == {"ok": False, "error_code": "REPLAY_DETECTED"}
