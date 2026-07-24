from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4


def _decision(action: str, confidence: str):
    from bagholder.contracts.live_trading import ResearchDecision

    return ResearchDecision(
        decision_id=uuid4(),
        security_key="CN:600000.SH",
        as_of=datetime.now(UTC),
        action=action,
        confidence=Decimal(confidence),
        evidence_ids=["quote-v1"],
        data_version="cn-v1",
        model_version="ta-v1",
    )


def test_高置信买入按百分之五目标仓位和整手生成() -> None:
    from bagholder.application.signal_to_order import SignalToOrderService
    from bagholder.contracts.live_trading import ExecutionMode

    proposal = SignalToOrderService().propose(
        decision=_decision("BUY", "0.80"),
        account_id="citic-main",
        net_asset=Decimal("1000000"),
        current_market_value=Decimal("0"),
        available_to_sell=0,
        last_price=Decimal("10.20"),
        mode=ExecutionMode.LIVE,
        now=datetime.now(UTC),
    )

    assert proposal is not None
    assert proposal.quantity == 4900
    assert proposal.quantity % 100 == 0


def test_低置信买入不产生订单() -> None:
    from bagholder.application.signal_to_order import SignalToOrderService
    from bagholder.contracts.live_trading import ExecutionMode

    proposal = SignalToOrderService().propose(
        decision=_decision("BUY", "0.54"),
        account_id="citic-main",
        net_asset=Decimal("1000000"),
        current_market_value=Decimal("0"),
        available_to_sell=0,
        last_price=Decimal("10.20"),
        mode=ExecutionMode.LIVE,
        now=datetime.now(UTC),
    )

    assert proposal is None
