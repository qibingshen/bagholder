"""使用 SQLite 事务完成确定性模拟撮合。"""

from datetime import datetime
from decimal import Decimal

from bagholder.contracts.live_trading import ExecutionMode, ExecutionRequest
from bagholder.domain.broker import BrokerOrderReceipt
from bagholder.infrastructure.sqlite_store import SqlitePlatformStore


class PaperExecutionService:
    """模拟账户和订单执行入口。"""

    def __init__(self, store: SqlitePlatformStore) -> None:
        self._store = store

    def create_account(
        self,
        account_id: str,
        cash: Decimal,
        now: datetime,
    ) -> None:
        """创建具有明确初始现金的模拟账户。"""

        if not account_id.strip():
            raise ValueError("模拟账户 ID 不能为空")
        if cash <= 0:
            raise ValueError("模拟账户初始现金必须大于零")
        self._store.create_paper_account(account_id, cash, now)

    def submit(
        self,
        request: ExecutionRequest,
        now: datetime,
    ) -> BrokerOrderReceipt:
        """审批和风控有效时，以限价立即模拟成交。"""

        if request.proposal.mode is not ExecutionMode.PAPER:
            raise PermissionError("模拟执行器只接受 PAPER 订单")
        if not request.risk_verdict.allowed:
            raise PermissionError("订单未通过风控")
        if not request.approval.approved:
            raise PermissionError("订单未经批准")
        if request.approval.expires_at <= now or request.proposal.expires_at <= now:
            raise PermissionError("订单审批或提案已过期")
        if request.risk_verdict.proposal_id != request.proposal.proposal_id:
            raise PermissionError("风控结果与订单提案不匹配")
        if request.approval.proposal_id != request.proposal.proposal_id:
            raise PermissionError("审批与订单提案不匹配")
        return self._store.execute_paper_order(request, now)

