"""模型发布批准、原子指针切换和回滚审计。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelReleaseDecision:
    """模型发布或回滚判定。"""

    allowed: bool
    error_code: str | None


class ModelReleaseGuard:
    """发布前严重故障、未来泄漏和人工批准门禁。"""

    def evaluate_preconditions(
        self,
        has_critical_failure: bool,
        has_point_in_time_violation: bool,
        approved: bool,
    ) -> ModelReleaseDecision:
        """任何严重故障、未来泄漏或未批准都必须阻断发布。"""

        if has_critical_failure:
            return ModelReleaseDecision(allowed=False, error_code="CRITICAL_FAILURE")
        if has_point_in_time_violation:
            return ModelReleaseDecision(allowed=False, error_code="POINT_IN_TIME_VIOLATION")
        if not approved:
            return ModelReleaseDecision(allowed=False, error_code="APPROVAL_REQUIRED")
        return ModelReleaseDecision(allowed=True, error_code=None)


@dataclass
class ModelPointerSwitcher:
    """正式模型指针原子切换器。"""

    current_model_version: str

    def switch_to(self, model_version: str, simulate_failure: bool = False) -> str:
        """模拟原子切换；失败时保留当前指针。"""

        original = self.current_model_version
        if simulate_failure:
            self.current_model_version = original
            raise RuntimeError("原子切换失败")
        self.current_model_version = model_version
        return self.current_model_version


@dataclass
class ModelRollbackService:
    """模型回滚服务，失败时保留当前指针并记录审计。"""

    current_model_version: str
    audit_events: list[str] = field(default_factory=list)

    def rollback(
        self, to_model_version: str, simulate_failure: bool = False
    ) -> ModelReleaseDecision:
        """回滚到指定模型版本。"""

        if simulate_failure:
            self.audit_events.append("ROLLBACK_FAILED")
            return ModelReleaseDecision(allowed=False, error_code="ROLLBACK_FAILED")
        self.current_model_version = to_model_version
        self.audit_events.append("ROLLBACK_SUCCEEDED")
        return ModelReleaseDecision(allowed=True, error_code=None)
