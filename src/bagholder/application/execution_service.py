"""幂等、审批受控的真实订单执行服务。"""

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from bagholder.contracts.live_trading import ExecutionMode, ExecutionRequest
from bagholder.domain.broker import BrokerApiState, BrokerGateway, BrokerOrderReceipt


class TradingRepository(Protocol):
    """执行服务所需的最小仓储接口。"""

    def find(self, idempotency_key: str) -> BrokerOrderReceipt | None: ...

    def save(self, idempotency_key: str, receipt: BrokerOrderReceipt) -> None: ...


class OrderExecutor(Protocol):
    """模拟和真实执行器的共同最小接口。"""

    def submit(
        self,
        request: ExecutionRequest,
        now: datetime,
    ) -> BrokerOrderReceipt: ...


@dataclass(frozen=True, slots=True)
class LiveGateContext:
    """进入真实执行器前必须同时满足的本地事实。"""

    system_live_enabled: bool
    account_live_enabled: bool
    broker_api_state: BrokerApiState
    supports_live_orders: bool
    reconciled: bool
    interactive_confirmation: bool


class LiveBlockedError(PermissionError):
    """真实执行被安全门阻断。"""

    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


class LiveExecutionGate:
    """按固定顺序检查真实执行额外安全门。"""

    def validate(self, context: LiveGateContext) -> None:
        if not context.system_live_enabled:
            raise LiveBlockedError("LIVE_DISABLED")
        if not context.account_live_enabled:
            raise LiveBlockedError("ACCOUNT_LIVE_DISABLED")
        if context.broker_api_state is not BrokerApiState.READY:
            raise LiveBlockedError("BROKER_API_UNAVAILABLE")
        if not context.supports_live_orders:
            raise LiveBlockedError("BROKER_CAPABILITY_MISSING")
        if not context.reconciled:
            raise LiveBlockedError("RECONCILIATION_REQUIRED")
        if not context.interactive_confirmation:
            raise LiveBlockedError("LIVE_CONFIRMATION_REQUIRED")


class ExecutionRouter:
    """按提案模式明确分流，真实失败绝不转成模拟。"""

    def __init__(
        self,
        *,
        paper: OrderExecutor,
        live: OrderExecutor,
        live_gate: LiveExecutionGate | None = None,
    ) -> None:
        self._paper = paper
        self._live = live
        self._live_gate = live_gate or LiveExecutionGate()

    def execute(
        self,
        *,
        request: ExecutionRequest,
        now: datetime,
        live_context: LiveGateContext | None = None,
    ) -> BrokerOrderReceipt:
        if request.proposal.mode is ExecutionMode.PAPER:
            return self._paper.submit(request, now)
        if live_context is None:
            raise LiveBlockedError("LIVE_CONFIRMATION_REQUIRED")
        self._live_gate.validate(live_context)
        return self._live.submit(request, now)


class LiveExecutionService:
    """验证审批和风控后，以幂等方式调用券商网关。"""

    def __init__(self, repository: TradingRepository, gateway: BrokerGateway) -> None:
        self._repository = repository
        self._gateway = gateway

    def submit(self, request: ExecutionRequest, now: datetime) -> BrokerOrderReceipt:
        """相同幂等键只允许产生一次券商调用。"""

        existing = self._repository.find(request.idempotency_key)
        if existing is not None:
            return existing
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

        receipt = self._gateway.submit(request)
        self._repository.save(request.idempotency_key, receipt)
        return receipt
