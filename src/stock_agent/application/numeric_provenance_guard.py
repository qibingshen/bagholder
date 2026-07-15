"""保护研究对话中的量化数字必须来自 MCP 工具结果。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from stock_agent.contracts.common import Freshness


@dataclass(frozen=True)
class NumericProvenanceDecision:
    """数字溯源校验结论。"""

    allowed: bool
    error_code: str | None
    safe_message_zh: str


class NumericProvenanceGuard:
    """校验当前预测输入和自然语言回答中的数字来源。"""

    def evaluate_current_prediction_inputs(
        self,
        tool_name: str,
        freshness: Freshness,
        data_as_of: datetime,
        requested_at: datetime,
        fact_refs: list[str],
    ) -> NumericProvenanceDecision:
        """阻断过期数据或缺少事实引用的当前预测。"""

        _ = tool_name, data_as_of, requested_at
        if freshness.state == "STALE":
            return NumericProvenanceDecision(
                allowed=False,
                error_code="STALE_DATA",
                safe_message_zh="数据已过期，不能生成当前预测。",
            )
        if not fact_refs:
            return NumericProvenanceDecision(
                allowed=False,
                error_code="NUMERIC_PROVENANCE_MISSING",
                safe_message_zh="不能脱离 MCP 工具结果生成量化数字。",
            )
        return NumericProvenanceDecision(allowed=True, error_code=None, safe_message_zh="")

    def validate_llm_answer(
        self,
        answer_text: str,
        numeric_claims: list[dict[str, Any]],
        available_fact_refs: list[str],
    ) -> NumericProvenanceDecision:
        """确保自然语言回答里的每个数字都绑定可用 MCP 事实引用。"""

        _ = answer_text
        available = set(available_fact_refs)
        for claim in numeric_claims:
            fact_ref = claim.get("fact_ref")
            if not fact_ref or fact_ref not in available:
                return NumericProvenanceDecision(
                    allowed=False,
                    error_code="NUMERIC_PROVENANCE_MISSING",
                    safe_message_zh="不能脱离 MCP 工具结果生成量化数字。",
                )
        return NumericProvenanceDecision(allowed=True, error_code=None, safe_message_zh="")
