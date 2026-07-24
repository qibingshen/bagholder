from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

NOW = datetime(2026, 7, 25, 3, tzinfo=UTC)


class FakeMarketClient:
    def fetch_market(self, request):
        from bagholder.contracts.market_data import MarketBar, MarketSnapshot

        return MarketSnapshot(
            security_key=request.security_key,
            start_date=request.start_date,
            end_date=request.end_date,
            as_of=request.as_of,
            retrieved_at=NOW,
            source="controlled market fixture",
            records=[
                MarketBar(
                    date=request.end_date,
                    open=Decimal("100"),
                    high=Decimal("101"),
                    low=Decimal("99"),
                    close=Decimal("100"),
                    volume=100000,
                )
            ],
        )


class FakeResearchClient:
    def __init__(self, action: str, confidence: str) -> None:
        self.action = action
        self.confidence = confidence

    def run_research(self, request):
        from bagholder.contracts.market_data import ResearchProcessResult

        return ResearchProcessResult(
            action=self.action,
            confidence=Decimal(self.confidence),
            model_version="controlled-model-v1",
            as_of=NOW,
            risk_flags=[],
            reports={"market_report": "controlled"},
        )


class RejectingLiveExecutor:
    def __init__(self) -> None:
        self.calls = 0

    def submit(self, request, now):
        self.calls += 1
        raise AssertionError("安全门阻断时不能调用真实执行器")


def _risk_context():
    from bagholder.domain.risk import LiveRiskContext

    return LiveRiskContext(
        quote_age_seconds=Decimal("0"),
        reconciled=True,
        halted=False,
        security_tradable=True,
        price_within_limit=True,
        cash_available=Decimal("1000000"),
        available_to_sell=0,
        net_asset=Decimal("1000000"),
        current_total_exposure=Decimal("0"),
        current_security_exposure=Decimal("0"),
        current_industry_exposure=Decimal("0"),
        daily_turnover=Decimal("0"),
        daily_pnl=Decimal("0"),
        peak_drawdown=Decimal("0"),
    )


def _platform(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    action: str = "BUY",
    mode: str = "PAPER",
):
    from bagholder.application.approval_service import ApprovalService
    from bagholder.application.execution_service import ExecutionRouter
    from bagholder.application.market_data_service import MarketDataService
    from bagholder.application.paper_execution_service import PaperExecutionService
    from bagholder.application.pipeline_service import PipelineService
    from bagholder.application.research_service import ResearchService
    from bagholder.application.risk_service import LiveRiskService
    from bagholder.application.signal_to_order import SignalToOrderService
    from bagholder.contracts.live_trading import ExecutionMode
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    monkeypatch.setenv("TRADINGAGENTS_API_KEY", "test-key")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "test-model")
    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    paper = PaperExecutionService(store)
    if mode == "PAPER":
        paper.create_account("paper-main", Decimal("1000000"), NOW)
    live = RejectingLiveExecutor()
    pipeline = PipelineService(
        store=store,
        market_service=MarketDataService(FakeMarketClient(), store),
        research_service=ResearchService(
            FakeResearchClient(action, "0.80"),
            store,
        ),
        signal_service=SignalToOrderService(),
        risk_service=LiveRiskService(),
        approval_service=ApprovalService(),
        execution_router=ExecutionRouter(paper=paper, live=live),
    )
    return store, pipeline, live, ExecutionMode(mode)


def test_pipeline_完成研究风控后停在人工审批(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, pipeline, _, mode = _platform(tmp_path, monkeypatch)

    run = pipeline.run(
        security_key="CN:600519.SH",
        account_id="paper-main",
        analysis_date=date(2026, 7, 24),
        start_date=date(2026, 7, 24),
        mode=mode,
        risk_context=_risk_context(),
        now=NOW,
    )

    from bagholder.domain.pipeline import PipelineState

    assert run.state is PipelineState.WAITING_APPROVAL
    assert run.market_evidence_id
    assert run.research_decision_id
    assert store.count_orders() == 0


def test_pipeline_重复审批模拟单不会重复成交(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store, pipeline, _, mode = _platform(tmp_path, monkeypatch)
    waiting = pipeline.run(
        security_key="CN:600519.SH",
        account_id="paper-main",
        analysis_date=date(2026, 7, 24),
        start_date=date(2026, 7, 24),
        mode=mode,
        risk_context=_risk_context(),
        now=NOW,
    )

    first = pipeline.approve(
        run_id=waiting.run_id,
        mode=mode,
        interactive_confirmation=True,
        now=NOW,
    )
    second = pipeline.approve(
        run_id=waiting.run_id,
        mode=mode,
        interactive_confirmation=True,
        now=NOW,
    )

    from bagholder.domain.pipeline import PipelineState

    assert first.state is PipelineState.RECONCILED
    assert second.order_id == first.order_id
    assert store.count_fills() == 1


def test_pipeline_live_不可用时阻断且无模拟成交(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bagholder.application.execution_service import LiveGateContext
    from bagholder.domain.broker import BrokerApiState
    from bagholder.domain.pipeline import PipelineState

    store, pipeline, live, mode = _platform(
        tmp_path,
        monkeypatch,
        mode="LIVE",
    )
    waiting = pipeline.run(
        security_key="CN:600519.SH",
        account_id="citic-main",
        analysis_date=date(2026, 7, 24),
        start_date=date(2026, 7, 24),
        mode=mode,
        risk_context=_risk_context(),
        now=NOW,
    )

    blocked = pipeline.approve(
        run_id=waiting.run_id,
        mode=mode,
        interactive_confirmation=True,
        now=NOW,
        live_context=LiveGateContext(
            system_live_enabled=True,
            account_live_enabled=True,
            broker_api_state=BrokerApiState.API_UNAVAILABLE,
            supports_live_orders=False,
            reconciled=True,
            interactive_confirmation=True,
        ),
    )

    assert blocked.state is PipelineState.LIVE_BLOCKED
    assert blocked.error_code == "BROKER_API_UNAVAILABLE"
    assert live.calls == 0
    assert store.count_fills() == 0


def test_pipeline_hold_以_no_action_安全结束(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, pipeline, _, mode = _platform(
        tmp_path,
        monkeypatch,
        action="HOLD",
    )

    run = pipeline.run(
        security_key="CN:600519.SH",
        account_id="paper-main",
        analysis_date=date(2026, 7, 24),
        start_date=date(2026, 7, 24),
        mode=mode,
        risk_context=_risk_context(),
        now=NOW,
    )

    from bagholder.domain.pipeline import PipelineState

    assert run.state is PipelineState.NO_ACTION


def test_pipeline_缺少模型配置时保存明确状态(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, pipeline, _, mode = _platform(tmp_path, monkeypatch)
    monkeypatch.delenv("TRADINGAGENTS_API_KEY")
    monkeypatch.delenv("TRADINGAGENTS_MODEL")

    run = pipeline.run(
        security_key="CN:600519.SH",
        account_id="paper-main",
        analysis_date=date(2026, 7, 24),
        start_date=date(2026, 7, 24),
        mode=mode,
        risk_context=_risk_context(),
        now=NOW,
    )

    from bagholder.domain.pipeline import PipelineState

    assert run.state is PipelineState.MODEL_NOT_CONFIGURED
    assert run.error_code == "MODEL_NOT_CONFIGURED"
