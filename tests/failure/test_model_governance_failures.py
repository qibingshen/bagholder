"""验证模型治理失败场景必须阻断发布。"""

import pytest


def test_严重故障和未来泄漏会永久阻断候选发布() -> None:
    """候选模型出现严重故障或未来数据泄漏时不得进入发布流程。"""

    from stock_agent.application.model_release_service import ModelReleaseGuard

    decision = ModelReleaseGuard().evaluate_preconditions(
        has_critical_failure=True,
        has_point_in_time_violation=False,
        approved=False,
    )

    assert decision.allowed is False
    assert decision.error_code == "CRITICAL_FAILURE"

    leak_decision = ModelReleaseGuard().evaluate_preconditions(
        has_critical_failure=False,
        has_point_in_time_violation=True,
        approved=True,
    )

    assert leak_decision.allowed is False
    assert leak_decision.error_code == "POINT_IN_TIME_VIOLATION"


def test_未经授权发布和_mcp_管理动作必须拒绝() -> None:
    """MCP 不得发布、回滚或删除模型；桌面端也必须二次确认。"""

    from stock_agent.adapters.mcp.management_guard import MCPManagementGuard

    decision = MCPManagementGuard().authorize("model.publish")

    assert decision.allowed is False
    assert decision.error_code == "PERMISSION_DENIED"


def test_mcp_回滚删除和数据删除管理动作默认拒绝() -> None:
    """MCP 管理动作即使传入伪造桌面确认参数，也不能绕过只读研究边界。"""

    from stock_agent.adapters.mcp.management_guard import MCPManagementGuard

    guard = MCPManagementGuard()

    for action in ("model.rollback", "model.delete", "data.delete"):
        decision = guard.authorize(
            action,
            desktop_confirmation_id="fake-confirmation",
        )
        assert decision.allowed is False
        assert decision.error_code == "PERMISSION_DENIED"


def test_原子切换失败时保留当前正式模型() -> None:
    """发布指针切换失败不得留下半发布状态。"""

    from stock_agent.application.model_release_service import ModelPointerSwitcher

    switcher = ModelPointerSwitcher(current_model_version="baseline-v1")

    with pytest.raises(RuntimeError, match="原子切换失败"):
        switcher.switch_to("candidate-v1", simulate_failure=True)

    assert switcher.current_model_version == "baseline-v1"


def test_回滚失败时记录审计并保留当前指针() -> None:
    """回滚失败必须保留审计记录，不能删除当前正式模型指针。"""

    from stock_agent.application.model_release_service import ModelRollbackService

    service = ModelRollbackService(current_model_version="candidate-v1")
    result = service.rollback(to_model_version="baseline-v1", simulate_failure=True)

    assert result.allowed is False
    assert result.error_code == "ROLLBACK_FAILED"
    assert service.current_model_version == "candidate-v1"
    assert service.audit_events[-1] == "ROLLBACK_FAILED"
