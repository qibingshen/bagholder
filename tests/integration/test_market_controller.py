"""验证市场总览控制器只组合本地市场事实。"""

from __future__ import annotations

from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

import pytest

from stock_agent.application.market_service import (
    InstrumentCatalogEntry,
    MarketService,
    MarketStatus,
)
from stock_agent.contracts.common import Freshness
from stock_agent.domain.market import InstrumentIdentity, Market
from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar


def _主要指数身份() -> InstrumentIdentity:
    """构造市场总览使用的本地主要指数目录身份。"""

    return InstrumentIdentity(Market.CN, "SSE", "000001", "CNY")


def _市场状态(
    *,
    market: Market = Market.CN,
    calendar_status: str = "OPEN",
    freshness_state: str = "REALTIME",
    is_verified: bool = True,
) -> MarketStatus:
    """构造带完整来源、时点、版本的新鲜本地市场状态。"""

    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(market.timezone))
    return MarketStatus(
        market=market,
        market_timezone=market.timezone,
        trading_calendar_status=calendar_status,
        market_time=market_time,
        collected_at=market_time.astimezone(UTC),
        source_id="本地交易日历",
        data_version="日历版本-1",
        freshness=Freshness(state=freshness_state, age_seconds=0),
        is_verified=is_verified,
    )


def _历史日线() -> IngestedHistoricalDailyBar:
    """构造已持久化的历史日线，不包含任何实时数据。"""

    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(Market.CN.timezone))
    return IngestedHistoricalDailyBar(
        security_id=_主要指数身份(),
        trade_date=date(2026, 7, 13),
        market_time=market_time,
        open=3_500.0,
        high=3_520.0,
        low=3_480.0,
        close=3_510.0,
        volume=100_000_000,
        currency="CNY",
        adjustment_basis="none",
        source_id="sina",
        collected_at=market_time.astimezone(UTC),
        source_data_version="sina-历史响应-1",
        artifact_version_id="normalized-1",
    )


def _本地市场服务(status: MarketStatus | None = None) -> MarketService:
    """构造仅含主要指数目录与市场状态的本地查询服务。"""

    return MarketService(
        market_statuses=[] if status is None else [status],
        instrument_catalog=[
            InstrumentCatalogEntry(
                security_id=_主要指数身份(),
                source_id="本地主要指数目录",
                collected_at=datetime(2026, 7, 14, tzinfo=UTC),
                data_version="指数目录版本-1",
            )
        ],
    )


def test_控制器以本地目录和已持久化日线返回可追溯的市场准备模型() -> None:
    """所有可显示数值都必须保留来源、市场时点、采集时间、版本与历史新鲜度。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    controller = MarketController(
        market_service=_本地市场服务(_市场状态()),
        historical_daily_bars=[_历史日线()],
    )

    model = controller.build_market_overview(
        market=Market.CN,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert model.page_state.status == "READY"
    assert model.page_state.shows_realtime is True
    assert model.current_prediction_allowed is True
    assert model.market_status.source_id == "本地交易日历"
    assert model.market_status.market_time.tzinfo is not None
    assert model.market_status.collected_at.tzinfo is not None
    assert model.market_status.data_version == "日历版本-1"
    assert model.market_status.freshness.state == "REALTIME"
    assert model.primary_indexes[0].catalog.source_id == "本地主要指数目录"
    assert model.primary_indexes[0].catalog.data_version == "指数目录版本-1"
    assert model.primary_indexes[0].daily_bars[0].close == 3_510.0
    assert model.primary_indexes[0].daily_bars[0].source_id == "sina"
    assert model.primary_indexes[0].daily_bars[0].market_time.tzinfo is not None
    assert model.primary_indexes[0].daily_bars[0].collected_at.tzinfo is not None
    assert model.primary_indexes[0].daily_bars[0].source_data_version == "sina-历史响应-1"
    assert model.primary_indexes[0].daily_bars[0].artifact_version_id == "normalized-1"
    assert model.primary_indexes[0].daily_bars[0].freshness.state == "HISTORICAL"


@pytest.mark.parametrize(
    ("status", "permission_granted", "expected_status"),
    [
        (None, True, "EMPTY"),
        (_市场状态(calendar_status="CLOSED", freshness_state="CLOSED"), True, "CLOSED"),
        (_市场状态(calendar_status="HOLIDAY", freshness_state="CLOSED"), True, "CLOSED"),
        (_市场状态(freshness_state="DELAYED"), True, "STALE"),
        (_市场状态(freshness_state="STALE"), True, "STALE"),
        (_市场状态(), False, "PERMISSION_DENIED"),
        (_市场状态(is_verified=False), True, "STALE"),
    ],
)
def test_控制器在本地事实不足或不可用时选择降级状态(
    status: MarketStatus | None, permission_granted: bool, expected_status: str
) -> None:
    """降级页面不得显示实时数据或允许当前预测。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    controller = MarketController(
        market_service=_本地市场服务(status),
        historical_daily_bars=[_历史日线()],
    )

    model = controller.build_market_overview(
        market=Market.CN,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
        permission_granted=permission_granted,
    )

    assert model.page_state.status == expected_status
    assert model.page_state.shows_realtime is False
    assert model.current_prediction_allowed is False


@pytest.mark.parametrize(
    ("market", "calendar_status"),
    [
        (Market.CN, "MIDDAY_BREAK"),
        (Market.HK, "TYPHOON_SUSPENDED"),
        (Market.US, "PRE_MARKET"),
        (Market.US, "AFTER_HOURS"),
    ],
)
def test_控制器仅在交易日历为_OPEN_时允许市场准备状态(market: Market, calendar_status: str) -> None:
    """所有受控的非开市日历状态均不得显示实时数据或允许当前预测。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    controller = MarketController(
        market_service=_本地市场服务(_市场状态(market=market, calendar_status=calendar_status)),
        historical_daily_bars=[_历史日线()],
    )

    model = controller.build_market_overview(
        market=market,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert model.page_state.status == "CLOSED"
    assert model.page_state.shows_realtime is False
    assert model.current_prediction_allowed is False


@pytest.mark.parametrize(
    ("market", "calendar_status"),
    [
        (Market.CN, "CLOSED"),
        (Market.CN, "HOLIDAY"),
        (Market.CN, "MIDDAY_BREAK"),
        (Market.HK, "TYPHOON_SUSPENDED"),
        (Market.US, "PRE_MARKET"),
        (Market.US, "AFTER_HOURS"),
    ],
)
def test_控制器优先将未验证的非开市日历状态降级为关闭(market: Market, calendar_status: str) -> None:
    """非开市日历状态即使未验证也必须关闭页面，避免显示实时数据或允许当前预测。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    controller = MarketController(
        market_service=_本地市场服务(
            _市场状态(
                market=market,
                calendar_status=calendar_status,
                is_verified=False,
            )
        ),
        historical_daily_bars=[_历史日线()],
    )

    model = controller.build_market_overview(
        market=market,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert model.page_state.status == "CLOSED"
    assert model.page_state.shows_realtime is False
    assert model.current_prediction_allowed is False


def test_历史日线不足时控制器返回明确空状态且不补造价格() -> None:
    """没有本地日线时必须保留目录事实并显示空状态，而不是虚构指数价格。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    controller = MarketController(
        market_service=_本地市场服务(_市场状态()), historical_daily_bars=[]
    )

    model = controller.build_market_overview(
        market=Market.CN,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert model.page_state.status == "EMPTY"
    assert model.primary_indexes[0].daily_bars == ()
    assert model.empty_state_zh == "暂无本地主要指数历史日线事实"
    assert model.current_prediction_allowed is False


def test_控制器不访问网络适配器或凭据服务(monkeypatch: pytest.MonkeyPatch) -> None:
    """控制器仅调用本地查询服务，任何外部访问尝试都应使测试失败。"""

    from stock_agent.desktop.controllers.market_controller import MarketController

    def _禁止外部调用(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("控制器不得调用外部依赖")

    monkeypatch.setattr("socket.create_connection", _禁止外部调用)
    monkeypatch.setattr("urllib.request.urlopen", _禁止外部调用)
    monkeypatch.setattr("keyring.get_password", _禁止外部调用)
    controller = MarketController(
        market_service=_本地市场服务(_市场状态()),
        historical_daily_bars=[_历史日线()],
    )

    model = controller.build_market_overview(
        market=Market.CN,
        primary_index_codes=["000001"],
        start_date=date(2026, 7, 13),
        end_date=date(2026, 7, 13),
    )

    assert model.page_state.status == "READY"
