from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import pytest


class FakeResearchClient:
    def __init__(self, result) -> None:
        self.result = result
        self.requests: list[object] = []

    def run_research(self, request):
        self.requests.append(request)
        return self.result


def _market_evidence(store):
    from bagholder.contracts.market_data import MarketBar, MarketSnapshot

    snapshot = MarketSnapshot(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
        retrieved_at=datetime(2026, 7, 25, tzinfo=UTC),
        source="sina HTTP",
        records=[
            MarketBar(
                date=date(2026, 7, 24),
                open=Decimal("1305.00"),
                high=Decimal("1309.21"),
                low=Decimal("1286.20"),
                close=Decimal("1297.41"),
                volume=3569892,
            )
        ],
    )
    return store.save_evidence(
        kind="MARKET",
        security_key=snapshot.security_key,
        payload=snapshot.model_dump(mode="json"),
        created_at=snapshot.retrieved_at,
    )


def _result():
    from bagholder.contracts.market_data import ResearchProcessResult

    return ResearchProcessResult(
        action="BUY",
        confidence=Decimal("0.80"),
        model_version="ta-astock-test",
        as_of=datetime(2026, 7, 25, tzinfo=UTC),
        risk_flags=[],
        reports={"market_report": "测试研究报告"},
    )


def test_研究决策引用市场和研究两份有效证据(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bagholder.application.research_service import ResearchService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    monkeypatch.setenv("TRADINGAGENTS_API_KEY", "test-key")
    monkeypatch.setenv("TRADINGAGENTS_MODEL", "test-model")
    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    market = _market_evidence(store)
    client = FakeResearchClient(_result())

    decision = ResearchService(client, store).run(
        market_evidence_id=market.evidence_id,
        analysis_date=date(2026, 7, 24),
    )

    assert decision.evidence_ids[0] == market.evidence_id
    assert len(decision.evidence_ids) == 2
    research_payload = store.load_evidence(decision.evidence_ids[1])
    assert research_payload["reports"]["market_report"] == "测试研究报告"
    assert store.get_research_decision(str(decision.decision_id)) == decision


def test_缺少模型配置时不调用研究进程(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bagholder.application.research_service import (
        ResearchConfigurationError,
        ResearchService,
    )
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    monkeypatch.delenv("TRADINGAGENTS_API_KEY", raising=False)
    monkeypatch.delenv("TRADINGAGENTS_MODEL", raising=False)
    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    market = _market_evidence(store)
    client = FakeResearchClient(_result())

    with pytest.raises(ResearchConfigurationError) as captured:
        ResearchService(client, store).run(
            market_evidence_id=market.evidence_id,
            analysis_date=date(2026, 7, 24),
        )

    assert captured.value.error_code == "MODEL_NOT_CONFIGURED"
    assert client.requests == []
