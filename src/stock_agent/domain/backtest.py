"""回测配置和结果契约。"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, model_validator

MarketCode = Literal["CN", "HK", "US"]
WindowMode = Literal["rolling", "expanding"]


class BacktestConfig(BaseModel):
    """可复现的时间序列回测配置。"""

    backtest_id: str = Field(min_length=1)
    market: MarketCode
    horizon_days: int = Field(gt=0)
    window_mode: WindowMode
    train_window_days: int = Field(gt=0)
    validation_window_days: int = Field(gt=0)
    commission_bps: Decimal = Field(ge=Decimal("0"))
    slippage_bps: Decimal = Field(ge=Decimal("0"))
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    feature_version: str = Field(min_length=1)


class BacktestResult(BaseModel):
    """回测结果，包含概率指标、简单基准比较和版本链。"""

    backtest_id: str = Field(min_length=1)
    result_version: str = Field(min_length=1)
    started_at: date
    ended_at: date
    brier_score: Decimal = Field(ge=Decimal("0"))
    calibration_error: Decimal = Field(ge=Decimal("0"))
    baseline_brier_score: Decimal = Field(ge=Decimal("0"))
    win_rate: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    trade_count: int = Field(ge=0)
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def 验证回测时间范围(self) -> BacktestResult:
        """回测结束日期不得早于开始日期。"""

        if self.ended_at < self.started_at:
            raise ValueError("回测结束日期不得早于开始日期")
        return self
