"""编排研究对话回答，并强制所有量化数字绑定 MCP 事实引用。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from stock_agent.application.numeric_provenance_guard import NumericProvenanceGuard

FIXED_INVESTMENT_DISCLAIMER = "研究参考，不构成投资建议"


@dataclass(frozen=True)
class ResearchChatAnswer:
    """研究对话回答结果。"""

    text: str
    allowed: bool
    fact_refs: tuple[str, ...]


class ResearchChatService:
    """在返回自然语言解释前执行数字溯源门禁。"""

    def __init__(self, guard: NumericProvenanceGuard | None = None) -> None:
        """注入数字溯源守卫。"""

        self._guard = guard or NumericProvenanceGuard()

    def build_answer(
        self,
        answer_text: str,
        numeric_claims: list[dict[str, Any]],
        available_fact_refs: list[str],
    ) -> ResearchChatAnswer:
        """构建回答；若数字缺少工具引用则返回安全拒绝。"""

        decision = self._guard.validate_llm_answer(
            answer_text=answer_text,
            numeric_claims=numeric_claims,
            available_fact_refs=available_fact_refs,
        )
        if not decision.allowed:
            return ResearchChatAnswer(
                text=f"{decision.safe_message_zh}{FIXED_INVESTMENT_DISCLAIMER}",
                allowed=False,
                fact_refs=(),
            )
        return ResearchChatAnswer(
            text=f"{answer_text}\n\n{FIXED_INVESTMENT_DISCLAIMER}",
            allowed=True,
            fact_refs=tuple(available_fact_refs),
        )
