"""验证回测窗口、成本、版本和结果契约。"""

from datetime import date
from decimal import Decimal

import pytest
from pydantic import ValidationError


def test_回测配置必须声明窗口成本市场周期和版本() -> None:
    """回测配置必须可复现，包含窗口策略、手续费、滑点、市场、周期和数据版本。"""

    from stock_agent.domain.backtest import BacktestConfig

    config = BacktestConfig(
        backtest_id="bt-CN-5d-baseline",
        market="CN",
        horizon_days=5,
        window_mode="rolling",
        train_window_days=120,
        validation_window_days=20,
        commission_bps=Decimal("3.00"),
        slippage_bps=Decimal("5.00"),
        data_version="features-cn-v1",
        model_version="baseline-v1",
        feature_version="feature-v1",
    )

    assert config.window_mode == "rolling"
    assert config.horizon_days == 5

    with pytest.raises(ValidationError):
        BacktestConfig(
            backtest_id="bt-invalid",
            market="CN",
            horizon_days=5,
            window_mode="random",
            train_window_days=120,
            validation_window_days=20,
            commission_bps=Decimal("3.00"),
            slippage_bps=Decimal("5.00"),
            data_version="features-cn-v1",
            model_version="baseline-v1",
            feature_version="feature-v1",
        )


def test_回测结果必须包含概率指标基准比较和版本链() -> None:
    """历史验证必须能比较模型和简单基准，并保留结果版本。"""

    from stock_agent.domain.backtest import BacktestResult

    result = BacktestResult(
        backtest_id="bt-CN-5d-baseline",
        result_version="bt-result-v1",
        started_at=date(2026, 7, 1),
        ended_at=date(2026, 7, 15),
        brier_score=Decimal("0.2100"),
        calibration_error=Decimal("0.0400"),
        baseline_brier_score=Decimal("0.2500"),
        win_rate=Decimal("0.56"),
        trade_count=120,
        data_version="features-cn-v1",
        model_version="baseline-v1",
    )

    assert result.brier_score < result.baseline_brier_score
    assert result.trade_count == 120

    with pytest.raises(ValidationError):
        BacktestResult(
            backtest_id="bt-CN-5d-baseline",
            result_version="bt-result-v1",
            started_at=date(2026, 7, 15),
            ended_at=date(2026, 7, 1),
            brier_score=Decimal("0.2100"),
            calibration_error=Decimal("0.0400"),
            baseline_brier_score=Decimal("0.2500"),
            win_rate=Decimal("0.56"),
            trade_count=120,
            data_version="features-cn-v1",
            model_version="baseline-v1",
        )
