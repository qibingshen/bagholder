"""MCP 最小权限守卫。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from stock_agent.mcp.contracts import READONLY_RESEARCH_TOOLS

LOCAL_CALLERS = {"localhost", "127.0.0.1", "::1"}
DESTRUCTIVE_TOOLS = {
    "model.publish",
    "model.rollback",
    "data.delete",
    "prediction.delete",
    "backup.replace",
}
FORBIDDEN_TOOLS = {"credential.get", "credential.set", "broker.login", "trade.place_order"}


@dataclass(frozen=True)
class MCPPermissionAuditEvent:
    """MCP 权限判定的脱敏审计事件。"""

    request_id: UUID
    tool_name: str
    reason: str
    sanitized_params: str


@dataclass(frozen=True)
class MCPPermissionDecision:
    """MCP 工具调用权限判定。"""

    allowed: bool
    error_code: str | None
    audit_event: MCPPermissionAuditEvent


class MCPPermissionGuard:
    """默认只允许本机只读研究工具。"""

    @classmethod
    def local_only(cls) -> MCPPermissionGuard:
        """创建仅允许本机调用的权限守卫。"""

        return cls()

    def authorize(
        self,
        request_id: UUID,
        tool_name: str,
        caller_host: str,
        params: dict[str, Any],
    ) -> MCPPermissionDecision:
        """在执行 MCP 工具前做最小权限判定和脱敏审计。"""

        sanitized = _sanitize_params(params)
        if caller_host not in LOCAL_CALLERS:
            return _deny(
                request_id, tool_name, "NON_LOCAL_CALLER", "PERMISSION_DENIED", sanitized=""
            )
        if tool_name in DESTRUCTIVE_TOOLS:
            return _deny(
                request_id,
                tool_name,
                "DESTRUCTIVE_TOOL_REQUIRES_DESKTOP_CONFIRMATION",
                "PERMISSION_DENIED",
                sanitized=sanitized,
            )
        if tool_name in FORBIDDEN_TOOLS:
            return _deny(
                request_id,
                tool_name,
                "FORBIDDEN_STAGE_ONE_TOOL",
                "TOOL_NOT_AVAILABLE",
                sanitized=sanitized,
            )
        if tool_name not in READONLY_RESEARCH_TOOLS:
            return _deny(
                request_id,
                tool_name,
                "UNREGISTERED_TOOL",
                "TOOL_NOT_AVAILABLE",
                sanitized=sanitized,
            )
        return MCPPermissionDecision(
            allowed=True,
            error_code=None,
            audit_event=MCPPermissionAuditEvent(
                request_id=request_id,
                tool_name=tool_name,
                reason="ALLOWED_READONLY_RESEARCH_TOOL",
                sanitized_params=sanitized,
            ),
        )


def _deny(
    request_id: UUID,
    tool_name: str,
    reason: str,
    error_code: str,
    sanitized: str,
) -> MCPPermissionDecision:
    """生成统一拒绝结果。"""

    return MCPPermissionDecision(
        allowed=False,
        error_code=error_code,
        audit_event=MCPPermissionAuditEvent(
            request_id=request_id,
            tool_name=tool_name,
            reason=reason,
            sanitized_params=sanitized,
        ),
    )


def _sanitize_params(params: dict[str, Any]) -> str:
    """保留最小可审计摘要，隐藏证券、凭据和明文敏感字段。"""

    parts: list[str] = []
    for key in sorted(params):
        value = params[key]
        if key in {"api_key", "token", "password"}:
            parts.append("<sensitive>=<redacted>")
            continue
        if key in {"symbol", "symbols", "target", "broker"}:
            value = "<redacted>"
        parts.append(f"{key}={value}")
    return ";".join(parts)
