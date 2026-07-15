"""模型中心页面状态。"""

from __future__ import annotations

from dataclasses import dataclass, field

投资风险提示 = "研究参考，不构成投资建议"


@dataclass(frozen=True, slots=True)
class ModelGateEvidenceView:
    """模型发布门禁证据摘要。"""

    model_version: str
    gate_status: str
    shadow_trading_days: int
    baseline_comparison: str
    approval_status: str
    blocking_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ModelManagementPageState:
    """模型中心用于绑定 PySide6 页面控件的状态。"""

    status: str
    model_version: str
    disclaimer: str = 投资风险提示
    blocking_reasons: tuple[str, ...] = ()
    show_release_confirmation: bool = False
    show_rollback_confirmation: bool = False
    rollback_target: str | None = None
    user_message: str = field(init=False)

    def __post_init__(self) -> None:
        """发布和回滚确认必须互斥，防止用户误把回滚当作发布。"""

        if self.show_release_confirmation and self.show_rollback_confirmation:
            raise ValueError("发布确认和回滚确认不能同时显示")
        object.__setattr__(self, "user_message", self._build_user_message())

    @classmethod
    def from_evidence(cls, evidence: ModelGateEvidenceView) -> ModelManagementPageState:
        """根据门禁证据生成候选模型发布状态。"""

        ready_to_release = (
            evidence.gate_status == "PASS"
            and evidence.approval_status == "APPROVED"
            and evidence.shadow_trading_days >= 30
        )
        if ready_to_release:
            return cls(
                status="READY_TO_RELEASE",
                model_version=evidence.model_version,
                show_release_confirmation=True,
            )
        return cls(
            status="BLOCKED",
            model_version=evidence.model_version,
            blocking_reasons=evidence.blocking_reasons,
        )

    @classmethod
    def rollback_confirmation(
        cls,
        current_model_version: str,
        target_model_version: str,
        reason: str,
    ) -> ModelManagementPageState:
        """生成回滚确认状态，原因必须在审计链路中另行保存。"""

        if not reason.strip():
            raise ValueError("模型回滚必须提供原因")
        return cls(
            status="ROLLBACK_CONFIRM_REQUIRED",
            model_version=current_model_version,
            show_rollback_confirmation=True,
            rollback_target=target_model_version,
        )

    def _build_user_message(self) -> str:
        """生成页面顶部可读状态说明。"""

        if self.status == "READY_TO_RELEASE":
            return "候选模型已通过门禁，等待桌面端最终发布确认。"
        if self.status == "ROLLBACK_CONFIRM_REQUIRED":
            return "模型回滚需要单独确认，确认后将记录审计事件。"
        if self.blocking_reasons:
            return "候选模型暂不可发布：" + "、".join(self.blocking_reasons)
        return "候选模型暂不可发布。"
