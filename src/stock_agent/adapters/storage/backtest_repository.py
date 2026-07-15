"""历史预测复盘和回测结果仓储。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from stock_agent.domain.backtest import BacktestResult


@dataclass(frozen=True)
class MaturedPredictionOutcome:
    """预测到期后的实际结果记录。"""

    snapshot_id: str
    actual_label: str
    matured_at: date
    source_id: str


@dataclass
class InMemoryBacktestRepository:
    """追加保存到期结果和回测结果版本。"""

    _outcomes: dict[str, list[MaturedPredictionOutcome]] = field(default_factory=dict)
    _results: dict[str, list[BacktestResult]] = field(default_factory=dict)

    def append_matured_outcome(
        self,
        snapshot_id: str,
        actual_label: str,
        matured_at: date,
        source_id: str,
    ) -> MaturedPredictionOutcome:
        """追加保存预测到期实际结果。"""

        outcome = MaturedPredictionOutcome(
            snapshot_id=snapshot_id,
            actual_label=actual_label,
            matured_at=matured_at,
            source_id=source_id,
        )
        self._outcomes.setdefault(snapshot_id, []).append(outcome)
        return outcome

    def outcomes_for(self, snapshot_id: str) -> tuple[MaturedPredictionOutcome, ...]:
        """读取预测快照关联的到期结果。"""

        return tuple(self._outcomes.get(snapshot_id, ()))

    def append_backtest_result(self, result: BacktestResult) -> BacktestResult:
        """追加保存回测结果版本。"""

        self._results.setdefault(result.backtest_id, []).append(result)
        return result

    def results_for(self, backtest_id: str) -> tuple[BacktestResult, ...]:
        """读取指定回测的全部结果版本。"""

        return tuple(self._results.get(backtest_id, ()))
