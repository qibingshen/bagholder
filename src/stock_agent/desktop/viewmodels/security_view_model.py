"""将本地已验证证券事实组装为桌面研究视图，不连接网络也不生成预测。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from stock_agent.application.market_service import HistoricalDailyBar, MarketStatus
from stock_agent.domain.freshness import is_usable_for_current_prediction
from stock_agent.domain.market import InstrumentIdentity


class _TraceableDerivedFact(BaseModel):
    """派生展示事实必须能定位到本地输入来源、时点和数据版本。"""

    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    input_data_version: str = Field(min_length=1)
    calculation_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def 验证可追溯字段(self) -> _TraceableDerivedFact:
        """拒绝缺少审计时点或版本的派生数值。"""

        _验证带时区时间(self.market_time, "市场时间")
        _验证带时区时间(self.collected_at, "采集时间")
        if self.market_time > self.collected_at:
            raise ValueError("市场时间不能晚于采集时间")
        return self


class IndicatorFact(_TraceableDerivedFact):
    """指标展示值及其输入、计算版本。"""

    name: str = Field(min_length=1)
    value: float


class RelativeStrengthFact(_TraceableDerivedFact):
    """相对强弱展示值及其输入、计算版本。"""

    value: float
    benchmark: str = Field(min_length=1)


class SectorMembershipFact(BaseModel):
    """证券板块归属及其本地来源事实。"""

    sector_name: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    data_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def 验证可追溯字段(self) -> SectorMembershipFact:
        """拒绝缺少审计时点或版本的板块归属。"""

        _验证带时区时间(self.market_time, "市场时间")
        _验证带时区时间(self.collected_at, "采集时间")
        if self.market_time > self.collected_at:
            raise ValueError("市场时间不能晚于采集时间")
        return self


class SecurityResearchViewModel(BaseModel):
    """桌面证券研究页的只读事实视图模型。"""

    security_id: InstrumentIdentity
    market_status: MarketStatus | None
    daily_bars: tuple[HistoricalDailyBar, ...] = ()
    indicators: tuple[IndicatorFact, ...] = ()
    sector_membership: SectorMembershipFact | None = None
    relative_strength: RelativeStrengthFact | None = None
    current_prediction_allowed: bool
    degradation_status_zh: str | None = None
    empty_state_zh: str | None = None

    @classmethod
    def assemble(
        cls,
        *,
        security_id: InstrumentIdentity,
        market_status: MarketStatus | None,
        daily_bars: list[HistoricalDailyBar] | tuple[HistoricalDailyBar, ...] = (),
        indicators: list[IndicatorFact] | tuple[IndicatorFact, ...] = (),
        sector_membership: SectorMembershipFact | None = None,
        relative_strength: RelativeStrengthFact | None = None,
    ) -> SecurityResearchViewModel:
        """只组合调用方提供的本地事实；缺失事实保持为空，不补造任何数值。"""

        bars = tuple(daily_bars)
        indicator_values = tuple(indicators)
        if any(bar.security_id != security_id for bar in bars):
            raise ValueError("日线证券身份必须与研究证券一致")

        if market_status is None:
            prediction_allowed = False
            degradation_status = "行情状态不可验证，已降级"
        else:
            prediction_allowed = is_usable_for_current_prediction(
                {
                    "state": market_status.freshness.state,
                    "market_time": market_status.market_time,
                    "collected_at": market_status.collected_at,
                    "time_is_verifiable": True,
                }
            )
            degradation_status = _降级状态(market_status) if not prediction_allowed else None

        empty_state = (
            "暂无本地日K线、板块和指标事实"
            if not bars and sector_membership is None and not indicator_values
            else None
        )

        return cls(
            security_id=security_id,
            market_status=market_status,
            daily_bars=bars,
            indicators=indicator_values,
            sector_membership=sector_membership,
            relative_strength=relative_strength,
            current_prediction_allowed=prediction_allowed,
            degradation_status_zh=degradation_status,
            empty_state_zh=empty_state,
        )


def _降级状态(market_status: MarketStatus) -> str:
    """将不可用于当前预测的行情状态转换为明确中文提示。"""

    labels = {
        "DELAYED": "行情延迟，已降级",
        "STALE": "行情过期，已降级",
        "CLOSED": "市场已闭市，已降级",
    }
    return labels.get(market_status.freshness.state, "行情状态不可验证，已降级")


def _验证带时区时间(value: datetime, label: str) -> None:
    """确保展示来源时点可跨市场审计。"""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}必须包含时区")
