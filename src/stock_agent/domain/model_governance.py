"""候选模型、人工批准和回滚契约。"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ModelStatus = Literal["candidate", "shadow", "released", "rejected", "rolled_back"]


class CandidateModel(BaseModel):
    """候选模型登记信息。"""

    model_version: str = Field(min_length=1)
    artifact_sha256: str = Field(pattern=r"^[a-fA-F0-9]{64}$")
    code_version: str = Field(min_length=1)
    train_start: date
    train_end: date
    feature_version: str = Field(min_length=1)
    evaluation_report_id: str = Field(min_length=1)
    status: ModelStatus

    @model_validator(mode="after")
    def 验证候选模型边界(self) -> CandidateModel:
        """训练结束日期不得早于开始日期，首登状态必须为候选。"""

        if self.train_end < self.train_start:
            raise ValueError("训练结束日期不得早于开始日期")
        if self.status != "candidate":
            raise ValueError("模型首次登记必须保持候选状态")
        return self


class ModelReleaseApproval(BaseModel):
    """桌面端人工批准记录。"""

    model_version: str = Field(min_length=1)
    approved_by: str = Field(min_length=1)
    approved_at: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    desktop_confirmation_id: str = Field(min_length=1)


class ModelRollbackPlan(BaseModel):
    """模型回滚计划和审计原因。"""

    from_model_version: str = Field(min_length=1)
    to_model_version: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    audit_id: str = Field(min_length=1)
