"""回测中的交易摩擦、停牌和不可成交规则。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

ConstraintReason = Literal["suspended", "limit_up", "limit_down", "illiquid"]


@dataclass(frozen=True)
class TradingCostModel:
    """用手续费和滑点修正回测收益。"""

    commission_bps: Decimal
    slippage_bps: Decimal

    def apply_costs(self, raw_return: Decimal) -> Decimal:
        """从收益中扣除买卖两侧的手续费和滑点。"""

        total_bps = (self.commission_bps + self.slippage_bps) * Decimal("2")
        return raw_return - total_bps / Decimal("10000")


@dataclass(frozen=True)
class TradeConstraint:
    """单个证券在某交易日的不可成交约束。"""

    security_key: str
    trade_date: str
    reason: ConstraintReason


@dataclass(frozen=True)
class TradeDecision:
    """不可成交约束评估结果。"""

    allowed: bool
    error_code: str | None
    blocked_reasons: tuple[str, ...]


class TradingConstraintEvaluator:
    """评估停牌、涨跌停、流动性和缺失约束数据。"""

    def evaluate(self, constraints: list[TradeConstraint]) -> TradeDecision:
        """存在任何不可成交约束时拒绝交易。"""

        if constraints:
            return TradeDecision(
                allowed=False,
                error_code="NOT_TRADABLE",
                blocked_reasons=tuple(item.reason for item in constraints),
            )
        return TradeDecision(allowed=True, error_code=None, blocked_reasons=())

    def require_constraints_loaded(self, loaded: bool) -> None:
        """发布回测评估前必须加载不可成交约束数据。"""

        if not loaded:
            raise ValueError("缺少不可成交约束数据")
