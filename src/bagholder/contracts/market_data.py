"""真实行情和 TradingAgents 隔离进程契约。"""

from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class MarketBar(BaseModel):
    """标准化的 A 股日线记录。"""

    model_config = ConfigDict(frozen=True)

    date: date
    open: Decimal = Field(gt=Decimal("0"))
    high: Decimal = Field(gt=Decimal("0"))
    low: Decimal = Field(gt=Decimal("0"))
    close: Decimal = Field(gt=Decimal("0"))
    volume: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_ohlc_range(self) -> "MarketBar":
        """确保最高价和最低价覆盖开盘、收盘价。"""

        if (
            self.high < self.low
            or self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
        ):
            raise ValueError("OHLC 价格范围无效")
        return self


class MarketSnapshot(BaseModel):
    """一次可版本化的真实行情快照。"""

    model_config = ConfigDict(frozen=True)

    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    start_date: date
    end_date: date
    as_of: date
    retrieved_at: datetime
    source: str = Field(min_length=1)
    records: list[MarketBar] = Field(min_length=1)
    schema_version: Literal["market-v1"] = "market-v1"

    @model_validator(mode="after")
    def validate_dates(self) -> "MarketSnapshot":
        """拒绝重复、乱序、越界或未来数据。"""

        if self.start_date > self.end_date:
            raise ValueError("行情开始日期不能晚于结束日期")
        dates = [row.date for row in self.records]
        if dates != sorted(set(dates)):
            raise ValueError("行情日期必须严格递增且不能重复")
        if dates[0] < self.start_date or dates[-1] > self.end_date:
            raise ValueError("行情日期超出请求范围")
        if self.end_date > self.as_of:
            raise ValueError("行情结束日期不能晚于分析时点")
        return self


class FetchMarketRequest(BaseModel):
    """主平台发往数据隔离进程的行情请求。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^\d{6}$")
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    start_date: date
    end_date: date
    as_of: date

    @model_validator(mode="after")
    def validate_range(self) -> "FetchMarketRequest":
        """请求不得跨越分析时点。"""

        if self.start_date > self.end_date:
            raise ValueError("行情开始日期不能晚于结束日期")
        if self.end_date > self.as_of:
            raise ValueError("行情结束日期不能晚于分析时点")
        return self


class ResearchProcessRequest(BaseModel):
    """主平台发往 TradingAgents 的研究请求。"""

    model_config = ConfigDict(frozen=True)

    symbol: str = Field(pattern=r"^\d{6}$")
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    analysis_date: date
    as_of: datetime
    evidence_ids: list[str] = Field(min_length=1)
    data_version: str = Field(pattern=r"^[0-9a-f]{64}$")
    model_config_payload: dict[str, object]


class ResearchProcessResult(BaseModel):
    """TradingAgents 白名单化后的研究结果。"""

    model_config = ConfigDict(frozen=True)

    action: Literal["BUY", "HOLD", "SELL"]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    model_version: str = Field(min_length=1)
    as_of: datetime
    risk_flags: list[str] = Field(default_factory=list)
    reports: dict[str, object]

