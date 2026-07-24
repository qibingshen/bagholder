"""将研究决策确定性转换为订单提案。"""

from datetime import datetime, timedelta
from decimal import Decimal
from uuid import uuid4

from bagholder.contracts.live_trading import (
    ExecutionMode,
    OrderProposal,
    OrderSide,
    ResearchDecision,
)


class SignalToOrderService:
    """执行版本化、可复现的目标仓位映射。"""

    policy_version = "signal-policy-v1"

    def propose(
        self,
        *,
        decision: ResearchDecision,
        account_id: str,
        net_asset: Decimal,
        current_market_value: Decimal,
        available_to_sell: int,
        last_price: Decimal,
        mode: ExecutionMode,
        now: datetime,
    ) -> OrderProposal | None:
        """根据固定权重和 A 股整手规则生成订单提案。"""

        if net_asset <= 0 or last_price <= 0:
            raise ValueError("净资产和最新价格必须大于零")

        if decision.action == "BUY":
            if decision.confidence >= Decimal("0.70"):
                target_weight = Decimal("0.05")
            elif decision.confidence >= Decimal("0.55"):
                target_weight = Decimal("0.02")
            else:
                target_weight = Decimal("0")
        elif decision.action == "SELL":
            target_weight = Decimal("0")
        else:
            return None

        target_value = (net_asset * target_weight).quantize(Decimal("0.01"))
        delta_value = target_value - current_market_value
        if delta_value == 0:
            return None

        raw_quantity = int(abs(delta_value) / last_price)
        if delta_value > 0:
            quantity = raw_quantity // 100 * 100
            side = OrderSide.BUY
        else:
            quantity = min(raw_quantity, available_to_sell)
            side = OrderSide.SELL
        if quantity <= 0:
            return None

        return OrderProposal(
            proposal_id=uuid4(),
            decision_id=decision.decision_id,
            account_id=account_id,
            security_key=decision.security_key,
            side=side,
            quantity=quantity,
            limit_price=last_price,
            mode=mode,
            created_at=now,
            expires_at=now + timedelta(minutes=2),
        )
