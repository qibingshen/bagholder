"""独立训练进程入口，只能登记候选模型。"""

from __future__ import annotations

from datetime import date

from stock_agent.adapters.storage.model_registry import InMemoryModelRegistry
from stock_agent.domain.model_governance import CandidateModel


class TrainingRunner:
    """训练进程边界，明确不具备正式发布权限。"""

    def __init__(self, registry: InMemoryModelRegistry, can_release: bool = False) -> None:
        """注入模型注册表和发布权限标识。"""

        self._registry = registry
        self.can_release = can_release

    def register_candidate(
        self,
        model_version: str,
        artifact_sha256: str,
        code_version: str,
        train_start: date,
        train_end: date,
        feature_version: str,
        evaluation_report_id: str,
    ) -> CandidateModel:
        """登记候选模型，状态固定为 candidate。"""

        candidate = CandidateModel(
            model_version=model_version,
            artifact_sha256=artifact_sha256,
            code_version=code_version,
            train_start=train_start,
            train_end=train_end,
            feature_version=feature_version,
            evaluation_report_id=evaluation_report_id,
            status="candidate",
        )
        return self._registry.register_candidate(candidate)
