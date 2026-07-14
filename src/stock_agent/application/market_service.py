"""提供仅基于本地受控事实的市场、证券目录和历史日线查询。"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, model_validator

from stock_agent.contracts.common import Freshness
from stock_agent.domain.market import (
    InstrumentIdentity,
    Market,
    resolve_instrument_identity,
    validate_instrument_identity,
)


class MarketStatus(BaseModel):
    """表示可追溯的单市场日历状态，不包含外部数据拉取能力。"""

    market: Market
    market_timezone: str = Field(min_length=1)
    trading_calendar_status: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    source_id: str = Field(min_length=1)
    data_version: str = Field(min_length=1)
    freshness: Freshness
    is_verified: bool = False

    @model_validator(mode="after")
    def 验证市场状态事实(self) -> MarketStatus:
        """锁定市场时区、状态集合与可比较的事实时间。"""

        allowed_statuses = {
            Market.CN: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY"},
            Market.HK: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY", "TYPHOON_SUSPENDED"},
            Market.US: {"OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS", "HOLIDAY"},
        }
        if self.market_timezone != self.market.timezone:
            raise ValueError("市场时区必须与所属市场一致")
        if self.trading_calendar_status not in allowed_statuses[self.market]:
            raise ValueError("交易日历状态不受该市场支持")
        _require_aware_time(self.market_time, "市场时间")
        _require_market_timezone(self.market_time, self.market, "市场时间")
        _require_aware_time(self.collected_at, "采集时间")
        if self.market_time > self.collected_at:
            raise ValueError("市场时间不能晚于采集时间")
        return self


class HistoricalDailyBar(BaseModel):
    """保存历史日线的价格、复权与溯源事实，明确禁止实时标签。"""

    security_id: InstrumentIdentity
    trade_date: date
    open: float
    high: float
    low: float
    close: float
    volume: int
    adjustment_basis: str = Field(min_length=1)
    currency: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    market_time: datetime
    collected_at: datetime
    data_version: str = Field(min_length=1)
    freshness: Freshness

    @model_validator(mode="after")
    def 验证历史日线事实(self) -> HistoricalDailyBar:
        """拒绝缺乏可追溯性、币种错配或伪装为实时的历史数据。"""

        _require_aware_time(self.market_time, "市场时间")
        _require_market_timezone(self.market_time, self.security_id.market, "市场时间")
        _require_aware_time(self.collected_at, "采集时间")
        if self.market_time > self.collected_at:
            raise ValueError("市场时间不能晚于采集时间")
        if self.currency != self.security_id.currency:
            raise ValueError("历史日线币种必须与证券身份一致")
        if self.trade_date != self.market_time.date():
            raise ValueError("交易日必须与市场时间的本地日期一致")
        if self.freshness.state == "REALTIME":
            raise ValueError("历史日线不得标记为实时行情")
        return self


class InstrumentCatalogEntry(BaseModel):
    """保存证券目录身份的本地来源、采集时点和版本。"""

    security_id: InstrumentIdentity
    source_id: str = Field(min_length=1)
    collected_at: datetime
    data_version: str = Field(min_length=1)

    @model_validator(mode="after")
    def 验证目录溯源事实(self) -> InstrumentCatalogEntry:
        """目录条目必须可审计，且证券身份不能绕过市场规则。"""

        _require_aware_time(self.collected_at, "采集时间")
        validate_instrument_identity(self.security_id)
        return self


class MarketService:
    """查询传入或内置的本地受控市场事实，不连接外部数据源。"""

    def __init__(
        self,
        *,
        market_statuses: Iterable[MarketStatus] | None = None,
        instruments: Iterable[InstrumentIdentity] | None = None,
        instrument_catalog: Iterable[InstrumentCatalogEntry] | None = None,
        historical_daily_bars: Iterable[HistoricalDailyBar] | None = None,
    ) -> None:
        """接收已验证本地事实；默认目录和日历仅用于离线查询演示。"""

        status_facts = _default_market_statuses() if market_statuses is None else market_statuses
        if instrument_catalog is not None and instruments is not None:
            raise ValueError("证券目录事实与裸证券身份不能同时提供")
        if instrument_catalog is not None:
            catalog_facts = tuple(instrument_catalog)
        elif instruments is None:
            catalog_facts = _default_instrument_catalog()
        else:
            catalog_facts = _catalog_entries_from_instruments(instruments)
        history_facts = () if historical_daily_bars is None else historical_daily_bars
        self._market_statuses = {status.market: status for status in status_facts}
        self._instrument_catalog = tuple(catalog_facts)
        self._instruments = tuple(entry.security_id for entry in self._instrument_catalog)
        self._historical_daily_bars = tuple(history_facts)
        for security_id in self._instruments:
            self.validate_security_identity(security_id)
        for bar in self._historical_daily_bars:
            self.validate_security_identity(bar.security_id)

    def get_market_status(self, market: Market) -> MarketStatus:
        """返回指定市场的本地受控日历状态，缺失时明确拒绝。"""

        if not isinstance(market, Market):
            raise ValueError("市场必须为 CN、HK 或 US")
        try:
            return self._market_statuses[market]
        except KeyError as error:
            raise ValueError("缺少该市场的本地日历状态或采集时间") from error

    def resolve_security_identity(
        self,
        display_code: str,
        *,
        market: Market | None = None,
        exchange: str | None = None,
    ) -> InstrumentCatalogEntry:
        """从本地目录解析可追溯证券事实，显示代码不唯一时绝不猜测市场。"""

        return self.get_instrument_catalog_entry(display_code, market=market, exchange=exchange)

    def get_instrument_catalog_entry(
        self,
        display_code: str,
        *,
        market: Market | None = None,
        exchange: str | None = None,
    ) -> InstrumentCatalogEntry:
        """查询可追溯的本地证券目录事实，非唯一代码必须指定限定条件。"""

        security_id = resolve_instrument_identity(
            display_code,
            [entry.security_id for entry in self._instrument_catalog],
            market=market,
            exchange=exchange,
        )
        return next(entry for entry in self._instrument_catalog if entry.security_id == security_id)

    def validate_security_identity(self, security_id: InstrumentIdentity) -> InstrumentIdentity:
        """校验三市场的代码、交易所和币种组合，拒绝跨市场串线。"""

        if not isinstance(security_id, InstrumentIdentity):
            raise ValueError("证券身份无效")
        return validate_instrument_identity(security_id)

    def get_historical_daily_bars(
        self, security_id: InstrumentIdentity, *, start_date: date, end_date: date
    ) -> list[HistoricalDailyBar]:
        """从传入的本地历史事实筛选日线，不补数、不预测也不拉取数据。"""

        self.validate_security_identity(security_id)
        if start_date > end_date:
            raise ValueError("历史日线起始日期不能晚于结束日期")
        return [
            bar
            for bar in self._historical_daily_bars
            if bar.security_id == security_id and start_date <= bar.trade_date <= end_date
        ]


def _default_market_statuses() -> tuple[MarketStatus, ...]:
    """返回随代码版本发布的离线日历样例，避免默认服务访问网络。"""

    collected_at = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    return tuple(
        MarketStatus(
            market=market,
            market_timezone=market.timezone,
            trading_calendar_status="CLOSED",
            market_time=collected_at.astimezone(ZoneInfo(market.timezone)),
            collected_at=collected_at,
            source_id="本地受控交易日历",
            data_version="内置日历规则-1",
            freshness=Freshness(state="CLOSED", age_seconds=0),
        )
        for market in Market
    )


def _default_instruments() -> tuple[InstrumentIdentity, ...]:
    """提供最小离线证券目录，调用方可用已验证本地目录替换。"""

    return (
        InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
        InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
        InstrumentIdentity(Market.HK, "HKEX", "00700", "HKD"),
        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
    )


def _default_instrument_catalog() -> tuple[InstrumentCatalogEntry, ...]:
    """为内置离线目录补齐可审计的来源、采集时点和版本。"""

    return _catalog_entries_from_instruments(_default_instruments())


def _catalog_entries_from_instruments(
    instruments: Iterable[InstrumentIdentity],
) -> tuple[InstrumentCatalogEntry, ...]:
    """将兼容入口的本地身份列表封装为有版本的目录事实。"""

    collected_at = datetime(2026, 7, 14, 0, 0, tzinfo=UTC)
    return tuple(
        InstrumentCatalogEntry(
            security_id=security_id,
            source_id="本地受控证券目录",
            collected_at=collected_at,
            data_version="内置目录规则-1",
        )
        for security_id in instruments
    )


def _require_aware_time(value: datetime, label: str) -> None:
    """确保审计时间含有时区，避免把不同市场本地时间混为同一时点。"""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{label}必须包含时区")


def _require_market_timezone(value: datetime, market: Market, label: str) -> None:
    """确保市场时点使用对应 IANA 时区，避免以相同偏移误解本地日期。"""

    timezone = value.tzinfo
    if not isinstance(timezone, ZoneInfo) or timezone.key != market.timezone:
        raise ValueError(f"{label}必须使用 {market.timezone} 市场时区")
