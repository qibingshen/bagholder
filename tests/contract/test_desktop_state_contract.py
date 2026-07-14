"""验证市场页和个股页在数据不可用时的用户可见状态契约。"""

import pytest

from stock_agent.desktop.pages.market_page import MarketPageState
from stock_agent.desktop.pages.security_page import SecurityPageState


@pytest.mark.parametrize(
    "state", ["EMPTY", "LOADING", "OFFLINE", "PERMISSION_DENIED", "STALE", "READY", "RECOVERED"]
)
@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_页面状态具有中文用户可见说明(page_state: type[MarketPageState] | type[SecurityPageState], state: str) -> None:
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
def test_恢复状态表示页面可重新使用(page_state: type[MarketPageState] | type[SecurityPageState]) -> None:
    """恢复状态应明确告诉界面数据已可用，避免沿用故障态限制。"""

    view_state = page_state(status="RECOVERED")

    assert view_state.is_available is True


@pytest.mark.parametrize(
    ("state", "keywords"),
    [
        ("EMPTY", ("空", "暂无")),
        ("LOADING", ("加载",)),
        ("OFFLINE", ("离线",)),
        ("PERMISSION_DENIED", ("权限",)),
        ("STALE", ("过期",)),
        ("READY", ("可用",)),
        ("RECOVERED", ("恢复",)),
    ],
)
@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
def test_页面状态保留标识并提供对应中文语义(
    page_state: type[MarketPageState] | type[SecurityPageState], state: str, keywords: tuple[str, ...]
) -> None:
    """每种页面状态必须可识别，且中文说明应表达该状态自身语义而非通用提示。"""

    view_state = page_state(status=state)

    assert view_state.status == state
    assert any(keyword in view_state.user_message for keyword in keywords)
