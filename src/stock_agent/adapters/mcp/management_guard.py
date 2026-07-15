"""MCP 管理动作权限守卫。"""

from __future__ import annotations

from dataclasses import dataclass

_默认拒绝管理动作 = frozenset(
    {
        "model.publish",
        "model.rollback",
        "model.delete",
        "data.delete",
        "broker.login",
        "trade.place_order",
    }
)


@dataclass(frozen=True, slots=True)
class MCPManagementDecision:
    """MCP 管理动作授权判定。"""

    allowed: bool
    error_code: str | None = None
    audit_reason: str | None = None


class MCPManagementGuard:
    """拒绝 MCP 发布、回滚、删除和交易类管理动作。"""

    def authorize(
        self,
        action: str,
        desktop_confirmation_id: str | None = None,
    ) -> MCPManagementDecision:
        """MCP 首个阶段保持只读研究边界，桌面确认不能被远程参数伪造。"""

        if action in _默认拒绝管理动作 or desktop_confirmation_id:
            return MCPManagementDecision(
                allowed=False,
                error_code="PERMISSION_DENIED",
                audit_reason="MCP 管理动作必须由桌面端本机流程执行",
            )
        return MCPManagementDecision(allowed=True)
