"""验证市场页和个股页在数据不可用时的用户可见状态契约。"""

import pytest

from stock_agent.desktop.pages.market_page import MarketPageState
from stock_agent.desktop.pages.security_page import SecurityPageState


@pytest.mark.parametrize(
    "state", ["EMPTY", "LOADING", "OFFLINE", "PERMISSION_DENIED", "STALE", "READY"]
)
@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_页面状态具有中文用户可见说明(
    page_state: type[MarketPageState] | type[SecurityPageState], state: str
) -> None:
    """市场页和个股页的所有约定状态均应向用户提供非空中文说明。"""

    view_state = page_state(status=state)

    assert view_state.user_message
    assert any("\u4e00" <= character <= "\u9fff" for character in view_state.user_message)


@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
@pytest.mark.parametrize("state", ["OFFLINE", "STALE"])
def test_离线或过期状态不得展示实时数据或允许当前预测(
    page_state: type[MarketPageState] | type[SecurityPageState], state: str
) -> None:
    """离线和过期数据必须显式禁用实时展示及基于当前数据的预测入口。"""

    view_state = page_state(status=state)

    assert view_state.show_realtime_data is False
    assert view_state.allow_current_prediction is False


@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_普通页面状态构造不能伪造恢复(
    page_state: type[MarketPageState] | type[SecurityPageState],
) -> None:
    """普通字符串状态没有已验证本地事实时，必须降级而不能恢复可用。"""

    view_state = page_state(status="RECOVERED")

    assert view_state.status == "STALE"
    assert view_state.is_available is False
    assert view_state.show_realtime_data is False
    assert view_state.allow_current_prediction is False


@pytest.mark.parametrize(
    ("state", "keywords"),
    [
        ("EMPTY", ("空", "暂无")),
        ("LOADING", ("加载",)),
        ("OFFLINE", ("离线",)),
        ("PERMISSION_DENIED", ("权限",)),
        ("STALE", ("过期",)),
        ("READY", ("可用",)),
    ],
)
@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_页面状态保留标识并提供对应中文语义(
    page_state: type[MarketPageState] | type[SecurityPageState],
    state: str,
    keywords: tuple[str, ...],
) -> None:
    """每种页面状态必须可识别，且中文说明应表达该状态自身语义而非通用提示。"""

    view_state = page_state(status=state)

    assert view_state.status == state
    assert any(keyword in view_state.user_message for keyword in keywords)


@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_恢复工厂拒绝未验证或未来的本地事实(
    page_state: type[MarketPageState] | type[SecurityPageState],
) -> None:
    """恢复仅接受已验证、带时区且时点不在未来的本地事实。"""

    from datetime import UTC, datetime, timedelta
    from zoneinfo import ZoneInfo

    from stock_agent.application.market_service import MarketStatus
    from stock_agent.contracts.common import Freshness
    from stock_agent.domain.market import Market

    now = datetime.now(tz=UTC)
    unverified = MarketStatus(
        market=Market.CN,
        market_timezone=Market.CN.timezone,
        trading_calendar_status="OPEN",
        market_time=now.astimezone(ZoneInfo(Market.CN.timezone)),
        collected_at=now,
        source_id="本地来源",
        data_version="版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=0),
        is_verified=False,
    )
    future = unverified.model_copy(
        update={
            "market_time": (now + timedelta(minutes=1)).astimezone(ZoneInfo(Market.CN.timezone)),
            "collected_at": now + timedelta(minutes=1),
            "is_verified": True,
        }
    )
    timezone_missing = MarketStatus.model_construct(
        market=Market.CN,
        market_timezone=Market.CN.timezone,
        trading_calendar_status="OPEN",
        market_time=now.replace(tzinfo=None),
        collected_at=now,
        source_id="本地来源",
        data_version="版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=0),
        is_verified=True,
    )

    assert page_state.from_market_status(None).status == "STALE"
    assert page_state.from_market_status(unverified).status == "STALE"
    assert page_state.from_market_status(future).status == "STALE"
    assert page_state.from_market_status(timezone_missing).status == "STALE"


@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_恢复工厂仅接受完整已验证的本地事实(
    page_state: type[MarketPageState] | type[SecurityPageState],
) -> None:
    """恢复状态必须保留来源、市场时间、采集时间、版本和验证标记。"""

    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    from stock_agent.application.market_service import MarketStatus
    from stock_agent.contracts.common import Freshness
    from stock_agent.domain.market import Market

    now = datetime.now(tz=UTC)
    market_status = MarketStatus(
        market=Market.CN,
        market_timezone=Market.CN.timezone,
        trading_calendar_status="OPEN",
        market_time=now.astimezone(ZoneInfo(Market.CN.timezone)),
        collected_at=now,
        source_id="本地来源",
        data_version="版本-1",
        freshness=Freshness(state="REALTIME", age_seconds=0),
        is_verified=True,
    )

    view_state = page_state.from_market_status(market_status)

    assert view_state.status == "RECOVERED"
    assert view_state.is_available is True
