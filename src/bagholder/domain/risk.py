"""A 股实盘风控上下文。"""

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class LiveRiskContext(BaseModel):
    """一次事前风控所需的完整事实快照。"""

    model_config = ConfigDict(frozen=True)

    quote_age_seconds: Decimal = Field(ge=Decimal("0"))
    reconciled: bool
    halted: bool
    security_tradable: bool
    price_within_limit: bool
    cash_available: Decimal = Field(ge=Decimal("0"))
    available_to_sell: int = Field(ge=0)
    net_asset: Decimal = Field(gt=Decimal("0"))
    current_total_exposure: Decimal
    current_security_exposure: Decimal
    current_industry_exposure: Decimal
    daily_turnover: Decimal
    daily_pnl: Decimal
    peak_drawdown: Decimal
