"""验证模型发布指标门禁。"""

from decimal import Decimal


def test_模型发布必须达到基准改善和影子运行天数() -> None:
    """候选模型必须达到 Brier 5%、平衡准确率 2 个百分点和 30 交易日影子运行。"""

    from stock_agent.training.evaluation_pipeline import ModelReleaseGate

    decision = ModelReleaseGate().evaluate(
        brier_improvement=Decimal("0.051"),
        balanced_accuracy_improvement=Decimal("0.021"),
        shadow_trading_days=30,
        degraded_groups=(),
    )

    assert decision.allowed is True


def test_分市场或周期退化会阻断发布() -> None:
    """任一市场或预测周期退化都不能发布正式模型。"""

    from stock_agent.training.evaluation_pipeline import ModelReleaseGate

    decision = ModelReleaseGate().evaluate(
        brier_improvement=Decimal("0.060"),
        balanced_accuracy_improvement=Decimal("0.030"),
        shadow_trading_days=30,
        degraded_groups=("US:20d",),
    )

    assert decision.allowed is False
    assert decision.error_code == "GROUP_METRIC_DEGRADED"


def test_影子运行不足_30_交易日阻断发布() -> None:
    """影子运行证据不足时，只能保留候选状态。"""

    from stock_agent.training.evaluation_pipeline import ModelReleaseGate

    decision = ModelReleaseGate().evaluate(
        brier_improvement=Decimal("0.060"),
        balanced_accuracy_improvement=Decimal("0.030"),
        shadow_trading_days=29,
        degraded_groups=(),
    )

    assert decision.allowed is False
    assert decision.error_code == "SHADOW_RUN_TOO_SHORT"
