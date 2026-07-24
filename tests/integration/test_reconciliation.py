from decimal import Decimal


def test_本地和券商持仓不一致时账户熔断() -> None:
    from bagholder.application.reconciliation_service import ReconciliationService
    from bagholder.domain.broker import BrokerApiState
    from bagholder.domain.position import AccountSnapshot, PositionSnapshot

    local = AccountSnapshot(
        account_id="citic-main",
        cash_available=Decimal("100000"),
        net_asset=Decimal("200000"),
        positions=(),
        active_order_ids=(),
        trade_ids=(),
    )
    broker = AccountSnapshot(
        account_id="citic-main",
        cash_available=Decimal("100000"),
        net_asset=Decimal("200000"),
        positions=(
            PositionSnapshot(
                security_key="CN:600000.SH",
                total_quantity=100,
                available_to_sell=100,
                average_cost=Decimal("10"),
            ),
        ),
        active_order_ids=(),
        trade_ids=(),
    )

    result = ReconciliationService().reconcile(local, broker)

    assert result.matched is False
    assert result.account_state is BrokerApiState.HALTED
    assert "POSITION_MISMATCH" in result.reasons


def test_四表一致时账户可进入就绪状态() -> None:
    from bagholder.application.reconciliation_service import ReconciliationService
    from bagholder.domain.broker import BrokerApiState
    from bagholder.domain.position import AccountSnapshot

    snapshot = AccountSnapshot(
        account_id="guotai-haitong-main",
        cash_available=Decimal("100000"),
        net_asset=Decimal("100000"),
        positions=(),
        active_order_ids=(),
        trade_ids=(),
    )

    result = ReconciliationService().reconcile(snapshot, snapshot)

    assert result.matched is True
    assert result.account_state is BrokerApiState.READY
