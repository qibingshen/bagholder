"""每日任务、日报快照和状态机契约。"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

DailyPhase = Literal["pre_open", "intraday", "post_close"]
DailyReportType = Literal["market_summary", "sector_rotation", "watchlist", "prediction_review"]
DailyTaskStatus = Literal[
    "pending", "running", "partial_success", "retrying", "cancelled", "failed", "success"
]
MarketCode = Literal["CN", "HK", "US"]

FIXED_INVESTMENT_DISCLAIMER = "研究参考，不构成投资建议"


class DailyTaskContract(BaseModel):
    """每日任务契约，保留市场阶段、报告类型、状态和数据版本。"""

    task_id: str = Field(min_length=1)
    market: MarketCode
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    phase: DailyPhase
    report_type: DailyReportType
    status: DailyTaskStatus
    data_version: str = Field(min_length=1)
    scheduled_for: datetime


class DailyReportSnapshot(BaseModel):
    """日报快照，显式记录缺失范围、降级影响、来源和风险提示。"""

    report_id: str = Field(min_length=1)
    market: MarketCode
    trade_date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    generated_at: datetime
    data_version: str = Field(min_length=1)
    source_ids: tuple[str, ...]
    missing_ranges: tuple[str, ...]
    degradation_impacts: tuple[str, ...]
    sections: tuple[str, ...]
    disclaimer: str

    @model_validator(mode="after")
    def 验证日报快照(self) -> DailyReportSnapshot:
        """日报必须保留来源、章节和固定风险提示。"""

        if not self.source_ids:
            raise ValueError("日报快照必须至少包含一个来源")
        if not self.sections:
            raise ValueError("日报快照必须至少包含一个章节")
        if self.disclaimer != FIXED_INVESTMENT_DISCLAIMER:
            raise ValueError("日报快照必须包含固定风险提示")
        return self


class DailyTaskStateMachine:
    """每日任务状态机，阻止终态任务重新运行。"""

    _terminal_statuses = frozenset({"cancelled", "failed", "success"})

    def __init__(self, status: DailyTaskStatus) -> None:
        """初始化当前状态。"""

        self.status: DailyTaskStatus = status

    def transition(self, next_status: DailyTaskStatus) -> DailyTaskStateMachine:
        """执行状态流转并返回自身，便于连续调用。"""

        if self.status in self._terminal_statuses and next_status == "running":
            raise ValueError("终态任务不能重新运行")
        self.status = next_status
        return self
