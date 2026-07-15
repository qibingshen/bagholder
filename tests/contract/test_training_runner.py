"""验证独立训练进程只有候选登记权限。"""

from datetime import date


def test_训练运行器只能登记候选模型不能发布() -> None:
    """训练进程不得拥有正式发布权限。"""

    from stock_agent.adapters.storage.model_registry import InMemoryModelRegistry
    from stock_agent.training.runner import TrainingRunner

    registry = InMemoryModelRegistry()
    runner = TrainingRunner(registry=registry, can_release=False)

    candidate = runner.register_candidate(
        model_version="candidate-20260715-001",
        artifact_sha256="a" * 64,
        code_version="abc123",
        train_start=date(2025, 1, 1),
        train_end=date(2026, 6, 30),
        feature_version="feature-v1",
        evaluation_report_id="eval-1",
    )

    assert registry.get_candidate(candidate.model_version).status == "candidate"
    assert runner.can_release is False
