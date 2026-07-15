"""定义预测详情页的本地展示状态模型，不发起网络或交易请求。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from stock_agent.application.prediction_presenter import PredictionPresentation
from stock_agent.domain.prediction import FIXED_RESEARCH_DISCLAIMER

_状态说明 = {
    "EMPTY": "暂无可显示的本地预测快照。",
    "LOADING": "正在加载已保存的本地预测快照。",
    "OFFLINE": "当前处于离线状态，仅可查看已保存的历史预测。",
    "PERMISSION_DENIED": "预测数据权限受限，当前快照不可读取。",
    "STALE": "当前数据已过期，不能作为当前预测展示。",
    "READY": "预测快照可用于研究展示。",
    "PENDING_VALIDATION": "预测到期结果待验证，不能提前判定实际方向。",
    "HISTORICAL_SNAPSHOT": "历史预测快照只读展示，原始数字不可修订。",
}


@dataclass(frozen=True, slots=True)
class PredictionPageState:
    """预测页状态只表达展示和权限，不改变预测快照事实。"""

    status: str
    user_message: str = field(init=False)
    allow_current_prediction: bool = field(init=False)
    is_readonly_history: bool = field(init=False)
    shows_prediction_numbers: bool = field(init=False)

    def __post_init__(self) -> None:
        """锁定状态语义，避免把过期或待验证结果误展示为当前预测。"""

        if self.status not in _状态说明:
            raise ValueError(f"不支持的预测页状态：{self.status}")
        object.__setattr__(self, "user_message", _状态说明[self.status])
        object.__setattr__(self, "allow_current_prediction", self.status == "READY")
        object.__setattr__(self, "is_readonly_history", self.status == "HISTORICAL_SNAPSHOT")
        object.__setattr__(
            self,
            "shows_prediction_numbers",
            self.status in {"READY", "STALE", "PENDING_VALIDATION", "HISTORICAL_SNAPSHOT"},
        )


@dataclass(frozen=True, slots=True)
class PredictionDetailView:
    """预测详情页展示模型，保留概率、风险、版本、历史标识和免责声明。"""

    page_state: PredictionPageState
    snapshot_id: str
    security_key: str
    horizon_trading_days: int
    probability_rows: tuple[tuple[str, Decimal], ...]
    confidence: Decimal
    primary_evidence: tuple[str, ...]
    risk_factors: tuple[str, ...]
    freshness_state: str
    version_summary: dict[str, str]
    disclaimer: str
    outcome_status: str | None
    show_history_badge: bool

    @classmethod
    def from_presentation(
        cls,
        presentation: PredictionPresentation,
        *,
        historical: bool = False,
        outcome_status: str | None = None,
    ) -> PredictionDetailView:
        """从应用展示结果生成页面模型，页面层不重算概率数字。"""

        if presentation.disclaimer != FIXED_RESEARCH_DISCLAIMER:
            raise ValueError("预测详情页必须显示固定风险提示")
        state = _state_from_presentation(
            presentation,
            historical=historical,
            outcome_status=outcome_status,
        )
        return cls(
            page_state=PredictionPageState(status=state),
            snapshot_id=presentation.snapshot_id,
            security_key=presentation.security_key,
            horizon_trading_days=presentation.horizon_trading_days,
            probability_rows=(
                ("上涨", presentation.probabilities["up"]),
                ("震荡", presentation.probabilities["flat"]),
                ("下跌", presentation.probabilities["down"]),
            ),
            confidence=presentation.confidence,
            primary_evidence=presentation.primary_evidence,
            risk_factors=presentation.risk_factors,
            freshness_state=presentation.freshness_state,
            version_summary=presentation.version_summary,
            disclaimer=presentation.disclaimer,
            outcome_status=outcome_status,
            show_history_badge=historical or presentation.display_state == "HISTORICAL_SNAPSHOT",
        )


def _state_from_presentation(
    presentation: PredictionPresentation,
    *,
    historical: bool,
    outcome_status: str | None,
) -> str:
    """把应用展示状态映射为页面状态，待验证和历史优先于当前可用状态。"""

    if outcome_status == "PENDING_VALIDATION":
        return "PENDING_VALIDATION"
    if historical or presentation.display_state == "HISTORICAL_SNAPSHOT":
        return "HISTORICAL_SNAPSHOT"
    if presentation.display_state == "CURRENT_UNAVAILABLE" or presentation.freshness_state in {
        "DELAYED",
        "STALE",
        "CLOSED",
    }:
        return "STALE"
    return "READY"
