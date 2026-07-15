"""验证历史预测复盘和回测结果仓储。"""

from datetime import date
from decimal import Decimal


def test_回测仓储保存预测到期结果和回测结果版本() -> None:
    """仓储必须保留到期实际结果、历史快照引用和回测结果版本链。"""

    from stock_agent.adapters.storage.backtest_repository import InMemoryBacktestRepository
    from stock_agent.domain.backtest import BacktestResult

    repository = InMemoryBacktestRepository()
    repository.append_matured_outcome(
        snapshot_id="pred-1",
        actual_label="up",
        matured_at=date(2026, 7, 15),
        source_id="local-daily-close",
    )
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
    repository.append_backtest_result(result)

    assert repository.outcomes_for("pred-1")[0].actual_label == "up"
    assert repository.results_for("bt-CN-5d-baseline")[0].result_version == "bt-result-v1"
