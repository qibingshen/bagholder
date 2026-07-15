"""验证回测中的交易摩擦和不可成交约束。"""

from decimal import Decimal

import pytest


def test_手续费和滑点必须降低可交易收益() -> None:
    """回测收益必须扣除手续费和滑点，不能用无成本收益冒充结果。"""

    from stock_agent.domain.trading_constraints import TradingCostModel

    model = TradingCostModel(commission_bps=Decimal("3"), slippage_bps=Decimal("5"))

    assert model.apply_costs(Decimal("0.0200")) == Decimal("0.0184")


@pytest.mark.parametrize(
    "reason",
    ["suspended", "limit_up", "limit_down", "illiquid"],
)
def test_停牌涨跌停和流动性不足时拒绝成交(reason: str) -> None:
    """不可成交约束必须阻断交易，而不是继续生成虚假回测成交。"""

    from stock_agent.domain.trading_constraints import TradeConstraint, TradingConstraintEvaluator

    evaluator = TradingConstraintEvaluator()
    decision = evaluator.evaluate(
        constraints=[
            TradeConstraint(security_key="CN:600000.SH", trade_date="2026-07-15", reason=reason)
        ]
    )

    assert decision.allowed is False
    assert decision.error_code == "NOT_TRADABLE"
    assert reason in decision.blocked_reasons


def test_缺少成交约束数据时拒绝回测发布() -> None:
    """没有停牌、涨跌停或流动性数据时，回测结果不能作为可发布评估。"""

    from stock_agent.domain.trading_constraints import TradingConstraintEvaluator

    with pytest.raises(ValueError, match="缺少不可成交约束数据"):
        TradingConstraintEvaluator().require_constraints_loaded(loaded=False)
