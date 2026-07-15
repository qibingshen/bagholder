"""板块总览页面展示模型。"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

_状态说明 = {
    "EMPTY": "暂无可展示的板块数据。",
    "LOADING": "正在加载本地板块数据。",
    "READY": "板块数据可用于研究展示。",
    "INCOMPLETE": "板块数据覆盖率不足，不能展示强弱排名。",
    "NO_MEMBERS": "板块暂无有效成员。",
}


@dataclass(frozen=True, slots=True)
class SectorPageState:
    """板块页面状态控制排名展示和降级说明。"""

    status: str
    user_message: str = field(init=False)
    can_show_rankings: bool = field(init=False)

    def __post_init__(self) -> None:
        """覆盖率不足或无成员时不得展示误导性排名。"""

        if self.status not in _状态说明:
            raise ValueError(f"不支持的板块页面状态：{self.status}")
        object.__setattr__(self, "user_message", _状态说明[self.status])
        object.__setattr__(self, "can_show_rankings", self.status == "READY")


@dataclass(frozen=True, slots=True)
class SectorOverviewRow:
    """板块总览行，保留覆盖率和轮动依据。"""

    sector_id: str
    name: str
    return_pct: Decimal
    trend_strength: Decimal
    rotation_score: Decimal
    coverage_ratio: Decimal


@dataclass(frozen=True, slots=True)
class SectorOverviewView:
    """板块总览页面视图。"""

    page_state: SectorPageState
    rows: tuple[SectorOverviewRow, ...]
    ranking_allowed: bool

    def __post_init__(self) -> None:
        """排名开关必须与页面状态一致。"""

        if self.ranking_allowed and not self.page_state.can_show_rankings:
            raise ValueError("页面状态不允许展示板块排名")
