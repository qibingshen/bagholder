"""时间序列评估、简单基准和分组指标发布门禁。"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ModelReleaseGateDecision:
    """模型发布门禁判定。"""

    allowed: bool
    error_code: str | None = None


class ModelReleaseGate:
    """执行候选模型发布前的最低指标门槛。"""

    def evaluate(
        self,
        brier_improvement: Decimal,
        balanced_accuracy_improvement: Decimal,
        shadow_trading_days: int,
        degraded_groups: tuple[str, ...],
    ) -> ModelReleaseGateDecision:
        """检查 Brier、平衡准确率、影子运行天数和分组退化。"""

        if degraded_groups:
            return ModelReleaseGateDecision(allowed=False, error_code="GROUP_METRIC_DEGRADED")
        if shadow_trading_days < 30:
            return ModelReleaseGateDecision(allowed=False, error_code="SHADOW_RUN_TOO_SHORT")
        if brier_improvement < Decimal("0.05"):
            return ModelReleaseGateDecision(allowed=False, error_code="BRIER_IMPROVEMENT_TOO_LOW")
        if balanced_accuracy_improvement < Decimal("0.02"):
            return ModelReleaseGateDecision(
                allowed=False,
                error_code="BALANCED_ACCURACY_IMPROVEMENT_TOO_LOW",
            )
        return ModelReleaseGateDecision(allowed=True)
