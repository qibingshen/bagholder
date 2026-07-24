"""本地记录与券商事实的启动及重连对账。"""

from dataclasses import dataclass

from bagholder.domain.broker import BrokerApiState
from bagholder.domain.position import AccountSnapshot


@dataclass(frozen=True, slots=True)
class ReconciliationResult:
    """对账结果和账户下一状态。"""

    matched: bool
    account_state: BrokerApiState
    reasons: tuple[str, ...]


class ReconciliationService:
    """比较资金、持仓、活动委托和成交四类事实。"""

    def reconcile(
        self,
        local: AccountSnapshot,
        broker: AccountSnapshot,
    ) -> ReconciliationResult:
        """无法解释的差异立即熔断账户。"""

        reasons: list[str] = []
        if local.account_id != broker.account_id:
            reasons.append("ACCOUNT_MISMATCH")
        if (
            local.cash_available != broker.cash_available
            or local.net_asset != broker.net_asset
        ):
            reasons.append("FUNDS_MISMATCH")
        if local.positions != broker.positions:
            reasons.append("POSITION_MISMATCH")
        if local.active_order_ids != broker.active_order_ids:
            reasons.append("ORDER_MISMATCH")
        if local.trade_ids != broker.trade_ids:
            reasons.append("TRADE_MISMATCH")

        return ReconciliationResult(
            matched=not reasons,
            account_state=BrokerApiState.READY if not reasons else BrokerApiState.HALTED,
            reasons=tuple(reasons),
        )
