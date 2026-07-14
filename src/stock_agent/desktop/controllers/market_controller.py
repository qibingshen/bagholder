"""将本地市场事实组装为市场总览页面模型，不访问外部依赖。"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date

from stock_agent.application.market_service import (
    InstrumentCatalogEntry,
    MarketService,
    MarketStatus,
)
from stock_agent.desktop.pages.market_page import MarketPageState
from stock_agent.domain.market import Market
from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar


@dataclass(frozen=True, slots=True)
class PrimaryIndexHistory:
    """保留主要指数目录事实及其已持久化历史日线。"""

    catalog: InstrumentCatalogEntry
    daily_bars: tuple[IngestedHistoricalDailyBar, ...]


@dataclass(frozen=True, slots=True)
class MarketOverviewModel:
    """市场页可渲染的本地事实模型，不包含预测或交易结果。"""

    page_state: MarketPageState
    market_status: MarketStatus | None
    primary_indexes: tuple[PrimaryIndexHistory, ...]
    current_prediction_allowed: bool
    empty_state_zh: str | None = None


class MarketController:
    """只组合本地查询服务、目录事实和已持久化历史日线。"""

    def __init__(
        self,
        *,
        market_service: MarketService,
        historical_daily_bars: Iterable[IngestedHistoricalDailyBar],
    ) -> None:
        """接收调用方已验证的本地依赖，不接收网络、适配器或凭据服务。"""

        self._market_service = market_service
        self._historical_daily_bars = tuple(historical_daily_bars)

    def build_market_overview(
        self,
        *,
        market: Market,
        primary_index_codes: Iterable[str],
        start_date: date,
        end_date: date,
        permission_granted: bool = True,
    ) -> MarketOverviewModel:
        """组装指定市场的本地总览；缺失或不可用事实一律降级。"""

        if start_date > end_date:
            raise ValueError("历史日线起始日期不能晚于结束日期")
        if not permission_granted:
            return self._degraded_model("PERMISSION_DENIED")

        try:
            market_status = self._market_service.get_market_status(market)
        except ValueError:
            return self._degraded_model("EMPTY")

        degraded_status = _degradation_status(market_status)
        if degraded_status is not None:
            return self._degraded_model(degraded_status, market_status=market_status)

        primary_indexes = self._primary_indexes(
            market=market,
            primary_index_codes=primary_index_codes,
            start_date=start_date,
            end_date=end_date,
        )
        if not primary_indexes or any(not item.daily_bars for item in primary_indexes):
            return MarketOverviewModel(
                page_state=MarketPageState(status="EMPTY"),
                market_status=market_status,
                primary_indexes=primary_indexes,
                current_prediction_allowed=False,
                empty_state_zh="暂无本地主要指数历史日线事实",
            )

        page_state = MarketPageState(status="READY")
        return MarketOverviewModel(
            page_state=page_state,
            market_status=market_status,
            primary_indexes=primary_indexes,
            current_prediction_allowed=page_state.current_prediction_allowed,
        )

    def _primary_indexes(
        self,
        *,
        market: Market,
        primary_index_codes: Iterable[str],
        start_date: date,
        end_date: date,
    ) -> tuple[PrimaryIndexHistory, ...]:
        """从本地目录解析指数身份，再按日期过滤已持久化历史日线。"""

        items: list[PrimaryIndexHistory] = []
        for display_code in primary_index_codes:
            try:
                catalog = self._market_service.get_instrument_catalog_entry(
                    display_code, market=market
                )
            except ValueError:
                continue
            daily_bars = tuple(
                bar
                for bar in self._historical_daily_bars
                if bar.security_id == catalog.security_id
                and start_date <= bar.trade_date <= end_date
                and bar.freshness.state == "HISTORICAL"
            )
            items.append(PrimaryIndexHistory(catalog=catalog, daily_bars=daily_bars))
        return tuple(items)

    @staticmethod
    def _degraded_model(
        status: str,
        *,
        market_status: MarketStatus | None = None,
    ) -> MarketOverviewModel:
        """为不可用本地事实构造无实时、无当前预测的页面模型。"""

        page_state = MarketPageState(status=status)
        return MarketOverviewModel(
            page_state=page_state,
            market_status=market_status,
            primary_indexes=(),
            current_prediction_allowed=False,
        )


def _degradation_status(market_status: MarketStatus) -> str | None:
    """按交易日历、新鲜度和验证证据确定市场页面降级边界。"""

    if not market_status.is_verified:
        return "STALE"
    if market_status.trading_calendar_status != "OPEN":
        return "CLOSED"
    if market_status.freshness.state not in {"REALTIME", "NEAR_REALTIME"}:
        return "STALE"
    return None
