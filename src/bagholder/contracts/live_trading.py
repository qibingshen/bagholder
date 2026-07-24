"""定义研究、提案、风控、审批和执行的实盘交易契约。"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ExecutionMode(StrEnum):
    """订单执行模式。"""

    PAPER = "PAPER"
    LIVE = "LIVE"


class OrderSide(StrEnum):
    """A 股订单方向。"""

    BUY = "BUY"
    SELL = "SELL"


class ResearchDecision(BaseModel):
    """TradingAgents-Astock 产出的结构化研究决策。"""

    model_config = ConfigDict(frozen=True)

    decision_id: UUID
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    as_of: datetime
    action: Literal["BUY", "HOLD", "SELL"]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    evidence_ids: list[str] = Field(min_length=1)
    data_version: str = Field(min_length=1)
    model_version: str = Field(min_length=1)
    risk_flags: list[str] = Field(default_factory=list)


class OrderProposal(BaseModel):
    """等待风控和审批的不可变订单提案。"""

    model_config = ConfigDict(frozen=True)

    proposal_id: UUID
    decision_id: UUID
    account_id: str = Field(min_length=1)
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    side: OrderSide
    quantity: int = Field(gt=0)
    limit_price: Decimal = Field(gt=Decimal("0"))
    mode: ExecutionMode
    created_at: datetime
    expires_at: datetime

    @model_validator(mode="after")
    def 验证有效期(self) -> "OrderProposal":
        if self.expires_at <= self.created_at:
            raise ValueError("订单提案有效期必须晚于创建时间")
        return self


class RiskVerdict(BaseModel):
    """版本化事前风控结果。"""

    model_config = ConfigDict(frozen=True)

    verdict_id: UUID
    proposal_id: UUID
    allowed: bool
    rule_version: str = Field(min_length=1)
    blocked_reasons: list[str]
    checked_at: datetime


class OrderApproval(BaseModel):
    """本机用户或限时策略授权产生的审批。"""

    model_config = ConfigDict(frozen=True)

    approval_id: UUID
    proposal_id: UUID
    approver: Literal["LOCAL_USER", "AUTO_POLICY"]
    approved: bool
    approved_at: datetime
    expires_at: datetime


class ExecutionRequest(BaseModel):
    """提交到券商适配层的完整请求。"""

    model_config = ConfigDict(frozen=True)

    request_id: UUID
    idempotency_key: str = Field(min_length=16)
    proposal: OrderProposal
    risk_verdict: RiskVerdict
    approval: OrderApproval
    correlation_id: UUID

