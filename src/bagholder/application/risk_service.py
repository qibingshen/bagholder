"""执行固定顺序的 A 股事前风险检查。"""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from bagholder.contracts.live_trading import OrderProposal, OrderSide, RiskVerdict
from bagholder.domain.risk import LiveRiskContext


class LiveRiskService:
    """账户级事前风控；任一关键事实异常都关闭交易。"""

    rule_version = "live-risk-v1"

    def evaluate(
        self,
        proposal: OrderProposal,
        context: LiveRiskContext,
    ) -> RiskVerdict:
        """返回完整阻断原因，而不是只返回第一条。"""

        reasons: list[str] = []
        if context.quote_age_seconds > Decimal("5"):
            reasons.append("STALE_QUOTE")
        if not context.reconciled:
            reasons.append("ACCOUNT_NOT_RECONCILED")
        if context.halted:
            reasons.append("ACCOUNT_HALTED")
        if not context.security_tradable:
            reasons.append("SECURITY_NOT_TRADABLE")
        if not context.price_within_limit:
            reasons.append("PRICE_LIMIT_VIOLATION")

        amount = proposal.limit_price * proposal.quantity
        if proposal.side is OrderSide.BUY and amount > context.cash_available:
            reasons.append("INSUFFICIENT_CASH")
        if proposal.side is OrderSide.SELL and proposal.quantity > context.available_to_sell:
            reasons.append("T1_SELL_LIMIT")

        proposed_weight = amount / context.net_asset
        if proposal.side is OrderSide.BUY:
            if context.current_security_exposure + proposed_weight > Decimal("0.05"):
                reasons.append("SECURITY_WEIGHT_LIMIT")
            if context.current_industry_exposure + proposed_weight > Decimal("0.20"):
                reasons.append("INDUSTRY_WEIGHT_LIMIT")
            if context.current_total_exposure + proposed_weight > Decimal("0.60"):
                reasons.append("GROSS_EXPOSURE_LIMIT")
            if context.daily_turnover + proposed_weight > Decimal("0.20"):
                reasons.append("DAILY_TURNOVER_LIMIT")
        if context.daily_pnl <= Decimal("-0.02"):
            reasons.append("DAILY_LOSS_LIMIT")
        if context.peak_drawdown >= Decimal("0.08"):
            reasons.append("DRAWDOWN_LIMIT")

        return RiskVerdict(
            verdict_id=uuid4(),
            proposal_id=proposal.proposal_id,
            allowed=not reasons,
            rule_version=self.rule_version,
            blocked_reasons=reasons,
            checked_at=datetime.now(UTC),
        )
