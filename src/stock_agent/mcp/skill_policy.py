"""限制 Skill 只能调用清单内 MCP 工具。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SkillAuditEvent:
    """记录 Skill 工具调用授权结果的脱敏审计摘要。"""

    skill_name: str
    tool_name: str
    reason: str
    sanitized_params: str


@dataclass(frozen=True)
class SkillToolDecision:
    """Skill 工具调用授权结论。"""

    allowed: bool
    error_code: str | None
    audit_event: SkillAuditEvent


class SkillToolPolicy:
    """为单个 Skill 固定允许调用的 MCP 工具集合。"""

    def __init__(self, skill_name: str, allowed_tools: set[str]) -> None:
        """保存 Skill 名称与工具白名单。"""

        self._skill_name = skill_name
        self._allowed_tools = frozenset(allowed_tools)

    @classmethod
    def for_skill(cls, skill_name: str, allowed_tools: set[str]) -> SkillToolPolicy:
        """创建 Skill 工具策略。"""

        return cls(skill_name=skill_name, allowed_tools=allowed_tools)

    def authorize_tool_call(self, tool_name: str, params: dict[str, Any]) -> SkillToolDecision:
        """在执行前拒绝清单之外的工具调用。"""

        if tool_name not in self._allowed_tools:
            return SkillToolDecision(
                allowed=False,
                error_code="PERMISSION_DENIED",
                audit_event=SkillAuditEvent(
                    skill_name=self._skill_name,
                    tool_name=tool_name,
                    reason="SKILL_TOOL_NOT_ALLOWED",
                    sanitized_params=_sanitize_params(params),
                ),
            )
        return SkillToolDecision(
            allowed=True,
            error_code=None,
            audit_event=SkillAuditEvent(
                skill_name=self._skill_name,
                tool_name=tool_name,
                reason="SKILL_TOOL_ALLOWED",
                sanitized_params=_sanitize_params(params),
            ),
        )


def _sanitize_params(params: dict[str, Any]) -> str:
    """生成不暴露证券明细、凭据或模型内部路径的参数摘要。"""

    parts: list[str] = []
    for key in sorted(params):
        value = params[key]
        if key in {"symbol", "symbols", "token", "api_key", "password", "model_version"}:
            value = "<redacted>"
        parts.append(f"{key}={value}")
    return ";".join(parts)
