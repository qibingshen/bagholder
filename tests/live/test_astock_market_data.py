import os
from datetime import date
from pathlib import Path

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATA_TESTS") != "1",
    reason="仅在明确启用时访问公共 A 股数据源",
)


def test_600519_真实日线能固化为有效证据(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from bagholder.application.market_data_service import MarketDataService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore
    from bagholder.integrations.tradingagents_client import TradingAgentsClient

    root = Path(__file__).parents[2]
    python = Path(
        os.getenv(
            "TRADINGAGENTS_PYTHON",
            root / ".runtime" / "tradingagents" / "Scripts" / "python.exe",
        )
    )
    runner = root / "integrations" / "tradingagents" / "runner.py"
    if not python.exists():
        pytest.skip("TradingAgents 独立环境不存在")
    monkeypatch.setenv("TRADINGAGENTS_PYTHON", str(python))
    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    service = MarketDataService(
        TradingAgentsClient(python, runner, timeout_seconds=45),
        store,
    )

    record = service.fetch(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
    )

    payload = store.load_evidence(record.evidence_id)
    assert payload["records"]
    assert len(record.sha256) == 64

