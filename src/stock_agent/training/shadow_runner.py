"""候选模型与正式模型并行影子运行证据。"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class ShadowRunDay:
    """单个交易日的影子运行结果引用。"""

    trade_date: date
    result_id: str


@dataclass
class ShadowRunEvidence:
    """候选模型影子运行证据累积。"""

    candidate_model_version: str
    active_model_version: str
    _days: list[ShadowRunDay] = field(default_factory=list)

    def record_day(self, trade_date: date, result_id: str) -> None:
        """记录一个交易日的影子运行结果。"""

        self._days.append(ShadowRunDay(trade_date=trade_date, result_id=result_id))

    @property
    def trading_days(self) -> int:
        """返回已累积的唯一交易日数量。"""

        return len({day.trade_date for day in self._days})

    @property
    def ready_for_release_gate(self) -> bool:
        """是否达到 30 个交易日的最低影子运行门槛。"""

        return self.trading_days >= 30
