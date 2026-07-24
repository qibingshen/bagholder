from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest

NOW = datetime(2026, 7, 25, 1, tzinfo=UTC)


def _request(*, cash_amount: str = "10"):
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
        account_id="paper-main",
        security_key="CN:600000.SH",
        side=OrderSide.BUY,
        quantity=100,
        limit_price=Decimal(cash_amount),
        mode=ExecutionMode.PAPER,
        created_at=NOW,
        expires_at=NOW + timedelta(minutes=2),
    )
    return ExecutionRequest(
        request_id=uuid4(),
        idempotency_key="paper-0123456789abcdef",
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


def _service(tmp_path: Path):
    from bagholder.application.paper_execution_service import PaperExecutionService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    return store, PaperExecutionService(store)


def test_重复模拟订单只成交一次(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    service.create_account("paper-main", Decimal("100000"), NOW)
    request = _request()

    first = service.submit(request, NOW)
    second = service.submit(request, NOW)

    account = store.get_paper_account("paper-main")
    position = store.get_paper_position("paper-main", "CN:600000.SH")
    assert first == second
    assert store.count_fills(request.idempotency_key) == 1
    assert account.cash == Decimal("99000")
    assert position.total_quantity == 100
    assert position.available_to_sell == 0


def test_资金不足时订单成交和账户更新全部回滚(tmp_path: Path) -> None:
    store, service = _service(tmp_path)
    service.create_account("paper-main", Decimal("500"), NOW)
    request = _request()

    with pytest.raises(PermissionError, match="INSUFFICIENT_CASH"):
        service.submit(request, NOW)

    assert store.count_orders() == 0
    assert store.count_fills(request.idempotency_key) == 0
    assert store.get_paper_account("paper-main").cash == Decimal("500")
