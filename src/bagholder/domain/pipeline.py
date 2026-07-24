"""平台管道和订单生命周期状态。"""

from dataclasses import dataclass
from enum import StrEnum

from bagholder.contracts.live_trading import ExecutionMode


class PipelineState(StrEnum):
    """一次研究到执行流程的稳定状态。"""

    CREATED = "CREATED"
    DATA_READY = "DATA_READY"
    DATA_FAILED = "DATA_FAILED"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    RESEARCH_READY = "RESEARCH_READY"
    RESEARCH_FAILED = "RESEARCH_FAILED"
    PROPOSAL_READY = "PROPOSAL_READY"
    RISK_PASSED = "RISK_PASSED"
    RISK_BLOCKED = "RISK_BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    PAPER_EXECUTED = "PAPER_EXECUTED"
    LIVE_SUBMITTED = "LIVE_SUBMITTED"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECONCILED = "RECONCILED"


class PipelineErrorCode(StrEnum):
    """对 CLI 和审计稳定暴露的失败代码。"""

    DATA_SOURCE_UNAVAILABLE = "DATA_SOURCE_UNAVAILABLE"
    DATA_INVALID = "DATA_INVALID"
    EVIDENCE_TAMPERED = "EVIDENCE_TAMPERED"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    RESEARCH_TIMEOUT = "RESEARCH_TIMEOUT"
    RESEARCH_PROTOCOL_ERROR = "RESEARCH_PROTOCOL_ERROR"
    RISK_BLOCKED = "RISK_BLOCKED"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    LIVE_DISABLED = "LIVE_DISABLED"
    BROKER_API_UNAVAILABLE = "BROKER_API_UNAVAILABLE"
    ORDER_STATE_UNKNOWN = "ORDER_STATE_UNKNOWN"
    DUPLICATE_REQUEST = "DUPLICATE_REQUEST"


class ExecutionOrderStatus(StrEnum):
    """模拟和实盘共用的订单状态。"""

    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PipelineRun:
    """管道查询使用的不可变快照。"""

    run_id: str
    state: PipelineState
    security_key: str
    account_id: str
    mode: ExecutionMode
    market_evidence_id: str | None = None
    research_decision_id: str | None = None
    proposal_id: str | None = None
    verdict_id: str | None = None
    order_id: str | None = None
    error_code: str | None = None


ALLOWED_TRANSITIONS: dict[PipelineState, frozenset[PipelineState]] = {
    PipelineState.CREATED: frozenset(
        {PipelineState.DATA_READY, PipelineState.DATA_FAILED}
    ),
    PipelineState.DATA_READY: frozenset(
        {
            PipelineState.RESEARCH_READY,
            PipelineState.MODEL_NOT_CONFIGURED,
            PipelineState.RESEARCH_FAILED,
        }
    ),
    PipelineState.RESEARCH_READY: frozenset({PipelineState.PROPOSAL_READY}),
    PipelineState.PROPOSAL_READY: frozenset(
        {PipelineState.RISK_PASSED, PipelineState.RISK_BLOCKED}
    ),
    PipelineState.RISK_PASSED: frozenset({PipelineState.WAITING_APPROVAL}),
    PipelineState.WAITING_APPROVAL: frozenset(
        {
            PipelineState.PAPER_EXECUTED,
            PipelineState.LIVE_SUBMITTED,
            PipelineState.APPROVAL_REJECTED,
            PipelineState.APPROVAL_EXPIRED,
            PipelineState.LIVE_BLOCKED,
            PipelineState.EXECUTION_FAILED,
        }
    ),
    PipelineState.PAPER_EXECUTED: frozenset({PipelineState.RECONCILED}),
    PipelineState.LIVE_SUBMITTED: frozenset(
        {PipelineState.RECONCILED, PipelineState.RECONCILIATION_REQUIRED}
    ),
}


def ensure_transition(current: PipelineState, target: PipelineState) -> None:
    """拒绝跳过安全节点或修改终态。"""

    if target not in ALLOWED_TRANSITIONS.get(current, frozenset()):
        raise ValueError(f"非法状态转移：{current.value} -> {target.value}")

