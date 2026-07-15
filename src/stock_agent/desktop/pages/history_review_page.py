"""历史预测复盘页面。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class HistoryReviewRow:
    """单条历史预测复盘行。"""

    snapshot_id: str
    outcome_status: str
    model_brier: Decimal | None
    baseline_brier: Decimal | None
    beats_baseline: bool = field(init=False)
    show_pending_badge: bool = field(init=False)

    def __post_init__(self) -> None:
        """待验证预测不显示基准胜负，已验证预测才比较指标。"""

        pending = self.outcome_status == "pending_validation"
        beats = (
            self.model_brier is not None
            and self.baseline_brier is not None
            and self.model_brier < self.baseline_brier
        )
        object.__setattr__(self, "beats_baseline", beats)
        object.__setattr__(self, "show_pending_badge", pending)


@dataclass(frozen=True, slots=True)
class HistoryReviewView:
    """历史预测复盘视图。"""

    rows: tuple[HistoryReviewRow, ...]
    has_pending_validation: bool = field(init=False)

    def __post_init__(self) -> None:
        """汇总是否存在待验证预测。"""

        object.__setattr__(
            self,
            "has_pending_validation",
            any(row.show_pending_badge for row in self.rows),
        )
