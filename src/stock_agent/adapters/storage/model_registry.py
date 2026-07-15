"""候选模型注册、工件哈希和评估证据仓储。"""

from __future__ import annotations

from dataclasses import dataclass, field

from stock_agent.domain.model_governance import CandidateModel


@dataclass
class InMemoryModelRegistry:
    """追加保存候选模型和评估证据引用。"""

    _candidates: dict[str, CandidateModel] = field(default_factory=dict)

    def register_candidate(self, candidate: CandidateModel) -> CandidateModel:
        """登记候选模型，拒绝覆盖同一版本。"""

        if candidate.model_version in self._candidates:
            raise ValueError("候选模型版本不能重复登记")
        self._candidates[candidate.model_version] = candidate
        return candidate

    def get_candidate(self, model_version: str) -> CandidateModel:
        """读取候选模型登记信息。"""

        return self._candidates[model_version]
