"""版本化简单基准、概率指标和分市场/周期比较服务。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from stock_agent.domain.backtest import BacktestResult


@dataclass(frozen=True)
class BacktestComparison:
    """模型相对简单基准的比较结果。"""

    market: str
    horizon_days: int
    model_version: str
    beats_baseline: bool
    brier_improvement: Decimal


class BacktestComparisonService:
    """按市场和预测周期比较模型与简单基准。"""

    def compare(
        self,
        market: str,
        horizon_days: int,
        result: BacktestResult,
    ) -> BacktestComparison:
        """使用 Brier 分数衡量模型是否优于简单基准。"""

        improvement = result.baseline_brier_score - result.brier_score
        return BacktestComparison(
            market=market,
            horizon_days=horizon_days,
            model_version=result.model_version,
            beats_baseline=improvement > Decimal("0"),
            brier_improvement=improvement,
        )
