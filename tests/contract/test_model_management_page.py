"""验证模型中心页面状态契约。"""


def test_模型中心展示门禁证据并要求发布确认() -> None:
    """候选模型只有在门禁通过且人工批准后才允许显示发布确认动作。"""

    from stock_agent.desktop.pages.model_management_page import (
        ModelGateEvidenceView,
        ModelManagementPageState,
    )

    evidence = ModelGateEvidenceView(
        model_version="model-20260715",
        gate_status="PASS",
        shadow_trading_days=30,
        baseline_comparison="优于简单基准",
        approval_status="APPROVED",
    )

    page_state = ModelManagementPageState.from_evidence(evidence)

    assert page_state.status == "READY_TO_RELEASE"
    assert page_state.show_release_confirmation is True
    assert page_state.show_rollback_confirmation is False
    assert "研究参考，不构成投资建议" in page_state.disclaimer


def test_模型中心在门禁未通过时阻止发布并展示原因() -> None:
    """门禁未通过时页面必须禁用发布确认，并保留可检查的阻断原因。"""

    from stock_agent.desktop.pages.model_management_page import (
        ModelGateEvidenceView,
        ModelManagementPageState,
    )

    evidence = ModelGateEvidenceView(
        model_version="model-20260715",
        gate_status="BLOCKED",
        shadow_trading_days=12,
        baseline_comparison="未达到简单基准",
        approval_status="PENDING",
        blocking_reasons=("SHADOW_RUN_TOO_SHORT", "APPROVAL_REQUIRED"),
    )

    page_state = ModelManagementPageState.from_evidence(evidence)

    assert page_state.status == "BLOCKED"
    assert page_state.show_release_confirmation is False
    assert page_state.blocking_reasons == ("SHADOW_RUN_TOO_SHORT", "APPROVAL_REQUIRED")


def test_模型中心回滚必须单独确认() -> None:
    """已发布模型的回滚动作必须进入独立确认状态，避免误操作。"""

    from stock_agent.desktop.pages.model_management_page import ModelManagementPageState

    page_state = ModelManagementPageState.rollback_confirmation(
        current_model_version="model-20260715",
        target_model_version="model-20260701",
        reason="最新模型出现严重故障",
    )

    assert page_state.status == "ROLLBACK_CONFIRM_REQUIRED"
    assert page_state.show_rollback_confirmation is True
    assert page_state.show_release_confirmation is False
    assert page_state.rollback_target == "model-20260701"
