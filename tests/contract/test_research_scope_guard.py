"""验证第一阶段只允许研究与模拟能力，拒绝券商和交易入口。"""

import pytest


def test_范围守卫拒绝券商登录下单自动交易和越权工具注册() -> None:
    """任何试图引入真实交易能力的注册都必须在服务启动前被阻止。"""

    from stock_agent.application.research_scope_guard import (
        ResearchScopeGuard,
        ResearchScopeViolation,
    )

    guard = ResearchScopeGuard()

    assert guard.assert_allowed("market.read") == "market.read"
    for prohibited in ("broker.login", "order.submit", "trade.auto_execute", "credential.broker"):
        with pytest.raises(ResearchScopeViolation):
            guard.assert_allowed(prohibited)
