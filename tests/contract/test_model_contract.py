"""验证模型状态、评估证据、批准和回滚契约。"""

from datetime import date

import pytest
from pydantic import ValidationError


def test_候选模型契约必须包含工件哈希训练范围和评估证据() -> None:
    """候选模型只能作为候选登记，必须保留工件哈希、数据范围和评估报告。"""

    from stock_agent.domain.model_governance import CandidateModel

    candidate = CandidateModel(
        model_version="candidate-20260715-001",
        artifact_sha256="a" * 64,
        code_version="abc123",
        train_start=date(2025, 1, 1),
        train_end=date(2026, 6, 30),
        feature_version="feature-v1",
        evaluation_report_id="eval-1",
        status="candidate",
    )

    assert candidate.status == "candidate"

    with pytest.raises(ValidationError):
        CandidateModel(
            model_version="candidate-20260715-001",
            artifact_sha256="bad",
            code_version="abc123",
            train_start=date(2025, 1, 1),
            train_end=date(2026, 6, 30),
            feature_version="feature-v1",
            evaluation_report_id="eval-1",
            status="released",
        )


def test_模型批准和回滚契约要求人工批准与审计原因() -> None:
    """正式发布和回滚必须有桌面端人工批准、原因和审计标识。"""

    from stock_agent.domain.model_governance import ModelReleaseApproval, ModelRollbackPlan

    approval = ModelReleaseApproval(
        model_version="candidate-20260715-001",
        approved_by="user",
        approved_at="2026-07-15T20:00:00+08:00",
        reason="影子运行和基准比较通过",
        desktop_confirmation_id="confirm-1",
    )
    rollback = ModelRollbackPlan(
        from_model_version="candidate-20260715-001",
        to_model_version="baseline-v1",
        reason="回滚演练",
        audit_id="audit-rollback-1",
    )

    assert approval.desktop_confirmation_id == "confirm-1"
    assert rollback.to_model_version == "baseline-v1"
