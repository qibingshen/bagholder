"""定义研究对话页面的安全展示状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stock_agent.application.research_chat_service import FIXED_INVESTMENT_DISCLAIMER

_状态说明 = {
    "EMPTY": "请输入研究问题，回答仅基于本地 MCP 工具结果。",
    "LOADING": "正在调用本地 MCP 工具并校验数字溯源。",
    "READY": "研究回答已生成，所有量化数字均绑定工具事实引用。",
    "TOOL_ERROR": "工具调用失败，不能展示量化回答。",
    "NO_DATA": "暂无可用本地数据，不能生成研究回答。",
    "PERMISSION_DENIED": "权限不足，当前工具或数据不可访问。",
    "OFFLINE": "当前处于离线状态，仅可查看已保存且可追溯的历史回答。",
}


@dataclass(frozen=True, slots=True)
class ResearchChatPageState:
    """研究对话页面状态只控制展示，不生成或修改量化事实。"""

    status: str
    user_message: str = field(init=False)
    can_show_answer: bool = field(init=False)

    def __post_init__(self) -> None:
        """锁定降级语义，避免工具失败时渲染未溯源数字。"""

        if self.status not in _状态说明:
            raise ValueError(f"不支持的研究对话页面状态：{self.status}")
        object.__setattr__(self, "user_message", _状态说明[self.status])
        object.__setattr__(self, "can_show_answer", self.status == "READY")


@dataclass(frozen=True, slots=True)
class ResearchChatView:
    """研究对话页面展示模型。"""

    page_state: ResearchChatPageState
    answer_text: str
    fact_refs: tuple[str, ...]
    disclaimer: str = FIXED_INVESTMENT_DISCLAIMER
    can_show_answer: bool = field(init=False)

    def __post_init__(self) -> None:
        """READY 回答必须带事实引用；降级状态不得携带答案。"""

        if self.page_state.status == "READY" and not self.fact_refs:
            raise ValueError("研究回答必须至少包含一个 MCP 工具事实引用")
        if self.page_state.status != "READY" and (self.answer_text or self.fact_refs):
            raise ValueError("降级状态不得展示研究回答或事实引用")
        object.__setattr__(self, "can_show_answer", self.page_state.can_show_answer)

    @classmethod
    def ready(cls, answer_text: str, fact_refs: tuple[str, ...]) -> ResearchChatView:
        """创建可展示的研究回答。"""

        return cls(
            page_state=ResearchChatPageState(status="READY"),
            answer_text=answer_text,
            fact_refs=fact_refs,
        )

    @classmethod
    def blocked(cls, state: ResearchChatPageState) -> ResearchChatView:
        """创建工具失败、无数据、权限拒绝或离线时的降级视图。"""

        if state.status == "READY":
            raise ValueError("READY 状态必须使用 ready() 创建")
        return cls(page_state=state, answer_text="", fact_refs=())
