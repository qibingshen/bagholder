import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

NOW = datetime(2026, 7, 25, 5, tzinfo=UTC)


class RecordingGateway:
    def __init__(self, prefix: str) -> None:
        self.prefix = prefix
        self.calls = 0

    def submit(self, request):
        from bagholder.domain.broker import BrokerOrderReceipt

        self.calls += 1
        return BrokerOrderReceipt(
            account_id=request.proposal.account_id,
            broker_order_id=f"{self.prefix}-{self.calls}",
            accepted=True,
            status="SUBMITTED",
        )


def _request(account_id: str):
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
        account_id=account_id,
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
        idempotency_key=f"route-{account_id}-0123456789",
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


def test_live_订单只调用提案账户_gateway() -> None:
    from bagholder.adapters.broker.broker_config import BrokerAccountConfig
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeBinding,
        BrokerRuntimeRegistry,
    )
    from bagholder.application.execution_service import (
        AccountRoutedLiveExecutionService,
    )
    from bagholder.domain.broker import BrokerApiState, BrokerCode
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository

    citic = RecordingGateway("CITIC")
    guotai = RecordingGateway("GUOTAI")

    def binding(account_id, broker, gateway):
        config = BrokerAccountConfig(
            account_id,
            broker,
            broker.value,
            "CNY",
            f"BAGHOLDER_{broker.value}",
            frozenset({"live_orders"}),
        )
        return BrokerRuntimeBinding(
            config,
            True,
            gateway,
            BrokerApiState.READY,
            {"live_orders": True},
            None,
        )

    registry = BrokerRuntimeRegistry(
        (
            binding("citic-main", BrokerCode.CITIC, citic),
            binding(
                "guotai-haitong-main",
                BrokerCode.GUOTAI_HAITONG,
                guotai,
            ),
        ),
        (),
    )
    service = AccountRoutedLiveExecutionService(
        InMemoryTradingRepository(),
        registry,
    )

    receipt = service.submit(_request("guotai-haitong-main"), NOW)

    assert receipt.broker_order_id == "GUOTAI-1"
    assert citic.calls == 0
    assert guotai.calls == 1


def test_未知账户不调用任何_gateway() -> None:
    import pytest

    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeRegistry,
    )
    from bagholder.application.execution_service import (
        AccountRoutedLiveExecutionService,
        LiveBlockedError,
    )
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository

    service = AccountRoutedLiveExecutionService(
        InMemoryTradingRepository(),
        BrokerRuntimeRegistry((), ()),
    )

    with pytest.raises(LiveBlockedError) as captured:
        service.submit(_request("missing-account"), NOW)

    assert captured.value.error_code == "BROKER_ACCOUNT_NOT_FOUND"


def test_不可用账户不尝试其他_gateway() -> None:
    import pytest

    from bagholder.adapters.broker.broker_config import BrokerAccountConfig
    from bagholder.adapters.broker.broker_runtime_registry import (
        BrokerRuntimeBinding,
        BrokerRuntimeRegistry,
    )
    from bagholder.application.execution_service import (
        AccountRoutedLiveExecutionService,
        LiveBlockedError,
    )
    from bagholder.domain.broker import BrokerApiState, BrokerCode
    from bagholder.infrastructure.in_memory import InMemoryTradingRepository

    other = RecordingGateway("OTHER")
    unavailable = BrokerRuntimeBinding(
        BrokerAccountConfig(
            "citic-main",
            BrokerCode.CITIC,
            "中信证券",
            "CNY",
            "BAGHOLDER_CITIC_MAIN",
            frozenset({"live_orders"}),
        ),
        True,
        None,
        BrokerApiState.API_UNAVAILABLE,
        {},
        "GATEWAY_CONFIG_INCOMPLETE",
    )
    available_other = BrokerRuntimeBinding(
        BrokerAccountConfig(
            "guotai-haitong-main",
            BrokerCode.GUOTAI_HAITONG,
            "国泰海通证券",
            "CNY",
            "BAGHOLDER_GUOTAI_HAITONG_MAIN",
            frozenset({"live_orders"}),
        ),
        True,
        other,
        BrokerApiState.READY,
        {"live_orders": True},
        None,
    )
    service = AccountRoutedLiveExecutionService(
        InMemoryTradingRepository(),
        BrokerRuntimeRegistry((unavailable, available_other), ()),
    )

    with pytest.raises(LiveBlockedError) as captured:
        service.submit(_request("citic-main"), NOW)

    assert captured.value.error_code == "BROKER_API_UNAVAILABLE"
    assert other.calls == 0


def test_runtime_按账户配置生成独立实盘门(
    tmp_path: Path,
    monkeypatch,
) -> None:
    from bagholder.domain.broker import BrokerApiState, BrokerCode
    from bagholder.runtime import build_runtime

    config_dir = tmp_path / "brokers"
    config_dir.mkdir()
    (config_dir / "citic.json").write_text(
        json.dumps(
            {
                "account_id": "citic-main",
                "broker_code": "CITIC",
                "display_name": "中信证券",
                "currency": "CNY",
                "environment_prefix": "BAGHOLDER_CITIC_MAIN",
                "required_capabilities": ["live_orders"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BAGHOLDER_HOME", str(tmp_path / "runtime"))
    monkeypatch.setenv("BAGHOLDER_BROKER_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("BAGHOLDER_LIVE_ENABLED", "true")
    monkeypatch.setenv("BAGHOLDER_CITIC_MAIN_LIVE_ENABLED", "true")

    runtime = build_runtime()
    binding = runtime.broker_binding("citic-main")
    gate = runtime.live_gate_context(
        "citic-main",
        interactive_confirmation=False,
    )

    assert runtime.system_live_enabled is True
    assert binding.config.broker_code is BrokerCode.CITIC
    assert binding.api_state is BrokerApiState.API_UNAVAILABLE
    assert gate.account_live_enabled is True
    assert gate.broker_api_state is BrokerApiState.API_UNAVAILABLE
