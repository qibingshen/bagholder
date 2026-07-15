"""验证 MCP 权限边界默认拒绝破坏性和越权能力。"""

from uuid import uuid4

import pytest


def test_mcp_拒绝非本机调用并写入脱敏审计() -> None:
    """MCP 只能接受本机调用，远程来源必须拒绝且审计记录不得泄露请求明文。"""

    from stock_agent.mcp.permissions import MCPPermissionGuard

    guard = MCPPermissionGuard.local_only()

    decision = guard.authorize(
        request_id=uuid4(),
        tool_name="market.get_quotes",
        caller_host="192.168.1.8",
        params={"market": "CN", "symbols": ["600000.SH"]},
    )

    assert decision.allowed is False
    assert decision.error_code == "PERMISSION_DENIED"
    assert decision.audit_event.tool_name == "market.get_quotes"
    assert decision.audit_event.reason == "NON_LOCAL_CALLER"
    assert "600000.SH" not in decision.audit_event.sanitized_params


@pytest.mark.parametrize(
    "tool_name",
    [
        "model.publish",
        "model.rollback",
        "data.delete",
        "prediction.delete",
        "backup.replace",
    ],
)
def test_mcp_拒绝发布回滚删除和替换备份(tool_name: str) -> None:
    """发布、回滚、删除和替换备份需要桌面端确认，不得作为默认 MCP 工具暴露。"""

    from stock_agent.mcp.permissions import MCPPermissionGuard

    decision = MCPPermissionGuard.local_only().authorize(
        request_id=uuid4(),
        tool_name=tool_name,
        caller_host="127.0.0.1",
        params={"target": "candidate-v1"},
    )

    assert decision.allowed is False
    assert decision.error_code in {"PERMISSION_DENIED", "TOOL_NOT_AVAILABLE"}
    assert decision.audit_event.reason == "DESTRUCTIVE_TOOL_REQUIRES_DESKTOP_CONFIRMATION"


@pytest.mark.parametrize(
    "tool_name, params",
    [
        ("credential.get", {"source_id": "finnhub"}),
        ("credential.set", {"source_id": "finnhub", "api_key": "secret"}),
        ("broker.login", {"broker": "demo", "password": "secret"}),
        ("trade.place_order", {"symbol": "600000.SH", "quantity": 100}),
    ],
)
def test_mcp_拒绝凭据管理券商登录和交易工具(tool_name: str, params: dict[str, object]) -> None:
    """首个阶段不允许 MCP 触达凭据明文、券商登录或真实交易能力。"""

    from stock_agent.mcp.permissions import MCPPermissionGuard

    decision = MCPPermissionGuard.local_only().authorize(
        request_id=uuid4(),
        tool_name=tool_name,
        caller_host="localhost",
        params=params,
    )

    assert decision.allowed is False
    assert decision.error_code in {"PERMISSION_DENIED", "TOOL_NOT_AVAILABLE"}
    assert "secret" not in decision.audit_event.sanitized_params
    assert "password" not in decision.audit_event.sanitized_params


def test_mcp_允许本机只读研究工具并保留最小审计摘要() -> None:
    """合法的本机只读研究查询可以放行，但审计只保存最小参数摘要。"""

    from stock_agent.mcp.permissions import MCPPermissionGuard

    decision = MCPPermissionGuard.local_only().authorize(
        request_id=uuid4(),
        tool_name="prediction.get",
        caller_host="localhost",
        params={"market": "CN", "symbol": "600000.SH", "horizon": "5d"},
    )

    assert decision.allowed is True
    assert decision.error_code is None
    assert decision.audit_event.reason == "ALLOWED_READONLY_RESEARCH_TOOL"
    assert "market=CN" in decision.audit_event.sanitized_params
    assert "symbol=<redacted>" in decision.audit_event.sanitized_params
