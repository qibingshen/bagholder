"""编排真实行情、智能体研究、风控、审批和双通道执行。"""

from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import date, datetime
from uuid import uuid4

from bagholder.application.approval_service import ApprovalService
from bagholder.application.execution_service import (
    ExecutionRouter,
    LiveBlockedError,
    LiveGateContext,
)
from bagholder.application.market_data_service import MarketDataService
from bagholder.application.research_service import (
    ResearchConfigurationError,
    ResearchService,
)
from bagholder.application.risk_service import LiveRiskService
from bagholder.application.signal_to_order import SignalToOrderService
from bagholder.contracts.live_trading import (
    ExecutionMode,
    ExecutionRequest,
    OrderProposal,
    RiskVerdict,
)
from bagholder.contracts.market_data import MarketSnapshot
from bagholder.domain.pipeline import PipelineRun, PipelineState
from bagholder.domain.risk import LiveRiskContext
from bagholder.infrastructure.sqlite_store import SqlitePlatformStore


class PipelineService:
    """用显式状态机推进一次研究到执行流程。"""

    def __init__(
        self,
        *,
        store: SqlitePlatformStore,
        market_service: MarketDataService,
        research_service: ResearchService,
        signal_service: SignalToOrderService,
        risk_service: LiveRiskService,
        approval_service: ApprovalService,
        execution_router: ExecutionRouter,
    ) -> None:
        self._store = store
        self._market = market_service
        self._research = research_service
        self._signal = signal_service
        self._risk = risk_service
        self._approval = approval_service
        self._router = execution_router

    def run(
        self,
        *,
        security_key: str,
        account_id: str,
        analysis_date: date,
        start_date: date,
        mode: ExecutionMode,
        risk_context: LiveRiskContext,
        now: datetime,
    ) -> PipelineRun:
        """运行到人工审批、无动作或阻断终态。"""

        stored = self._store.create_pipeline_run(
            security_key=security_key,
            account_id=account_id,
            mode=mode,
            now=now,
        )
        if not isinstance(stored, PipelineRun):
            raise TypeError("管道仓储返回类型无效")
        created = stored
        try:
            market = self._market.fetch(
                security_key=security_key,
                start_date=start_date,
                end_date=analysis_date,
                as_of=analysis_date,
            )
        except Exception:
            return self._transition(
                created.run_id,
                PipelineState.DATA_FAILED,
                now,
                error_code="DATA_SOURCE_UNAVAILABLE",
            )
        self._transition(
            created.run_id,
            PipelineState.DATA_READY,
            now,
            market_evidence_id=market.evidence_id,
        )
        try:
            decision = self._research.run(
                market_evidence_id=market.evidence_id,
                analysis_date=analysis_date,
            )
        except ResearchConfigurationError as error:
            return self._transition(
                created.run_id,
                PipelineState.MODEL_NOT_CONFIGURED,
                now,
                error_code=error.error_code,
            )
        except TimeoutError:
            return self._transition(
                created.run_id,
                PipelineState.RESEARCH_FAILED,
                now,
                error_code="RESEARCH_TIMEOUT",
            )
        except Exception:
            return self._transition(
                created.run_id,
                PipelineState.RESEARCH_FAILED,
                now,
                error_code="RESEARCH_PROTOCOL_ERROR",
            )
        self._transition(
            created.run_id,
            PipelineState.RESEARCH_READY,
            now,
            research_decision_id=str(decision.decision_id),
        )
        snapshot = MarketSnapshot.model_validate(
            self._store.load_evidence(market.evidence_id)
        )
        current_market_value = (
            risk_context.current_security_exposure * risk_context.net_asset
        )
        proposal = self._signal.propose(
            decision=decision,
            account_id=account_id,
            net_asset=risk_context.net_asset,
            current_market_value=current_market_value,
            available_to_sell=risk_context.available_to_sell,
            last_price=snapshot.records[-1].close,
            mode=mode,
            now=now,
        )
        if proposal is None:
            return self._transition(
                created.run_id,
                PipelineState.NO_ACTION,
                now,
            )
        self._store.save_order_proposal(proposal)
        self._transition(
            created.run_id,
            PipelineState.PROPOSAL_READY,
            now,
            proposal_id=str(proposal.proposal_id),
        )
        verdict = self._risk.evaluate(proposal, risk_context)
        self._store.save_risk_verdict(verdict)
        if not verdict.allowed:
            return self._transition(
                created.run_id,
                PipelineState.RISK_BLOCKED,
                now,
                verdict_id=str(verdict.verdict_id),
                error_code="RISK_BLOCKED",
            )
        self._transition(
            created.run_id,
            PipelineState.RISK_PASSED,
            now,
            verdict_id=str(verdict.verdict_id),
        )
        return self._transition(
            created.run_id,
            PipelineState.WAITING_APPROVAL,
            now,
        )

    def approve(
        self,
        *,
        run_id: str,
        mode: ExecutionMode,
        interactive_confirmation: bool,
        now: datetime,
        live_context: LiveGateContext | None = None,
    ) -> PipelineRun:
        """本地审批后明确进入 PAPER 或 LIVE，重复调用返回原结果。"""

        run = self.show(run_id)
        completed = {
            PipelineState.PAPER_EXECUTED,
            PipelineState.LIVE_SUBMITTED,
            PipelineState.LIVE_BLOCKED,
            PipelineState.EXECUTION_FAILED,
            PipelineState.RECONCILIATION_REQUIRED,
            PipelineState.RECONCILED,
        }
        if run.state in completed:
            return run
        if run.state is not PipelineState.WAITING_APPROVAL:
            raise PermissionError("管道不在等待审批状态")
        if run.mode is not mode:
            raise PermissionError("审批模式与原订单模式不一致")
        if run.proposal_id is None or run.verdict_id is None:
            raise RuntimeError("管道缺少提案或风控记录")
        proposal = OrderProposal.model_validate(
            self._store.get_order_proposal(run.proposal_id)
        )
        verdict = RiskVerdict.model_validate(
            self._store.get_risk_verdict(run.verdict_id)
        )
        approval = self._approval.approve_local(
            proposal=proposal,
            verdict=verdict,
            approved=True,
            now=now,
        )
        self._store.save_approval(approval)
        request = ExecutionRequest(
            request_id=uuid4(),
            idempotency_key=self._idempotency_key(run_id, proposal),
            proposal=proposal,
            risk_verdict=verdict,
            approval=approval,
            correlation_id=uuid4(),
        )
        effective_live_context = (
            replace(
                live_context,
                interactive_confirmation=interactive_confirmation,
            )
            if live_context is not None
            else None
        )
        try:
            receipt = self._router.execute(
                request=request,
                now=now,
                live_context=effective_live_context,
            )
        except LiveBlockedError as error:
            return self._transition(
                run_id,
                PipelineState.LIVE_BLOCKED,
                now,
                approval_id=str(approval.approval_id),
                error_code=error.error_code,
            )
        if mode is ExecutionMode.PAPER:
            self._transition(
                run_id,
                PipelineState.PAPER_EXECUTED,
                now,
                approval_id=str(approval.approval_id),
                order_id=receipt.broker_order_id,
            )
            return self._transition(run_id, PipelineState.RECONCILED, now)
        submitted = self._transition(
            run_id,
            PipelineState.LIVE_SUBMITTED,
            now,
            approval_id=str(approval.approval_id),
            order_id=receipt.broker_order_id,
        )
        if receipt.status == "UNKNOWN":
            return self._transition(
                run_id,
                PipelineState.RECONCILIATION_REQUIRED,
                now,
                error_code="ORDER_STATE_UNKNOWN",
            )
        return submitted

    def show(self, run_id: str) -> PipelineRun:
        """查询持久化管道状态。"""

        stored = self._store.get_pipeline_run(run_id)
        if not isinstance(stored, PipelineRun):
            raise TypeError("管道仓储返回类型无效")
        return stored

    def _transition(
        self,
        run_id: str,
        target: PipelineState,
        now: datetime,
        **updates: str | None,
    ) -> PipelineRun:
        stored = self._store.transition_pipeline(run_id, target, now, **updates)
        if not isinstance(stored, PipelineRun):
            raise TypeError("管道仓储返回类型无效")
        return stored

    @staticmethod
    def _idempotency_key(run_id: str, proposal: OrderProposal) -> str:
        raw = f"{run_id}:{proposal.proposal_id}:{proposal.mode.value}".encode()
        return f"pipeline-{hashlib.sha256(raw).hexdigest()}"
