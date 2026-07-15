"""验证研究对话页面的安全展示状态。"""

import pytest


def test_研究对话页面展示可追溯回答和固定风险提示() -> None:
    """页面只能展示已通过数字溯源守卫的回答。"""

    from stock_agent.desktop.pages.research_chat_page import ResearchChatPageState, ResearchChatView

    view = ResearchChatView.ready(
        answer_text="上涨概率来自 prediction.get 的本地结果。",
        fact_refs=("tool://prediction.get/result-1",),
    )

    assert view.page_state == ResearchChatPageState(status="READY")
    assert view.can_show_answer is True
    assert view.fact_refs == ("tool://prediction.get/result-1",)
    assert "研究参考，不构成投资建议" in view.disclaimer


@pytest.mark.parametrize(
    "status, message_fragment",
    [
        ("TOOL_ERROR", "工具调用失败"),
        ("NO_DATA", "暂无可用本地数据"),
        ("PERMISSION_DENIED", "权限不足"),
        ("OFFLINE", "离线"),
    ],
)
def test_研究对话页面降级状态不展示量化答案(status: str, message_fragment: str) -> None:
    """工具失败、无数据、权限拒绝和离线状态不得展示可能误导的量化回答。"""

    from stock_agent.desktop.pages.research_chat_page import ResearchChatPageState, ResearchChatView

    state = ResearchChatPageState(status=status)
    view = ResearchChatView.blocked(state=state)

    assert message_fragment in state.user_message
    assert view.can_show_answer is False
    assert view.answer_text == ""
    assert view.fact_refs == ()


def test_研究对话页面拒绝没有事实引用的就绪回答() -> None:
    """READY 状态必须携带至少一个工具事实引用，防止页面渲染补造数字。"""

    from stock_agent.desktop.pages.research_chat_page import ResearchChatView

    with pytest.raises(ValueError):
        ResearchChatView.ready(answer_text="上涨概率为 62%。", fact_refs=())
