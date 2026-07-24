"""人工审批和当日自动授权。"""

from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from bagholder.contracts.live_trading import OrderApproval, OrderProposal, RiskVerdict


@dataclass(frozen=True, slots=True)
class StrategyAuthorization:
    """账户与策略绑定的限时自动授权。"""

    account_id: str
    strategy_id: str
    starts_at: datetime
    expires_at: datetime


class ApprovalService:
    """验证双开关后生成不可变审批。"""

    def approve_local(
        self,
        *,
        proposal: OrderProposal,
        verdict: RiskVerdict,
        approved: bool,
        now: datetime,
    ) -> OrderApproval:
        """生成与已通过风控提案严格绑定的本地人工审批。"""

        if verdict.proposal_id != proposal.proposal_id:
            raise PermissionError("风控结果与订单提案不匹配")
        if not verdict.allowed:
            raise PermissionError("订单未通过风控")
        if proposal.expires_at <= now:
            raise PermissionError("订单提案已过期")
        return OrderApproval(
            approval_id=uuid4(),
            proposal_id=proposal.proposal_id,
            approver="LOCAL_USER",
            approved=approved,
            approved_at=now,
            expires_at=proposal.expires_at,
        )

    def approve_auto(
        self,
        *,
        proposal: OrderProposal,
        verdict: RiskVerdict,
        strategy_id: str,
        account_live_enabled: bool,
        authorization: StrategyAuthorization,
        now: datetime,
    ) -> OrderApproval:
        """仅允许在同一交易日的有效授权窗口内自动审批。"""

        if not account_live_enabled:
            raise PermissionError("账户实盘开关未启用")
        if authorization.expires_at.date() != now.date():
            raise ValueError("自动授权必须在当日失效")
        if authorization.account_id != proposal.account_id:
            raise PermissionError("自动授权账户不匹配")
        if authorization.strategy_id != strategy_id:
            raise PermissionError("自动授权策略不匹配")
        if not authorization.starts_at <= now < authorization.expires_at:
            raise PermissionError("自动授权不在有效窗口")
        if not verdict.allowed or verdict.proposal_id != proposal.proposal_id:
            raise PermissionError("订单未通过匹配的风控")
        if proposal.expires_at <= now:
            raise PermissionError("订单提案已过期")

        return OrderApproval(
            approval_id=uuid4(),
            proposal_id=proposal.proposal_id,
            approver="AUTO_POLICY",
            approved=True,
            approved_at=now,
            expires_at=min(proposal.expires_at, authorization.expires_at),
        )
