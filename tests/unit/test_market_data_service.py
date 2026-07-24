import hashlib
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path


class FakeMarketClient:
    def __init__(self, snapshot) -> None:
        self.snapshot = snapshot
        self.requests: list[object] = []

    def fetch_market(self, request):
        self.requests.append(request)
        return self.snapshot


def _snapshot():
    from bagholder.contracts.market_data import MarketBar, MarketSnapshot

    return MarketSnapshot(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
        retrieved_at=datetime(2026, 7, 25, tzinfo=UTC),
        source="sina HTTP (fallback)",
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


def test_市场服务保存真实响应并生成稳定数据版本(tmp_path: Path) -> None:
    from bagholder.application.market_data_service import MarketDataService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    client = FakeMarketClient(_snapshot())
    service = MarketDataService(client, store)

    record = service.fetch(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 24),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
    )

    payload = store.load_evidence(record.evidence_id)
    assert payload["records"][-1]["close"] == "1297.41"
    assert record.sha256 == hashlib.sha256(Path(record.path).read_bytes()).hexdigest()
    assert client.requests[0].symbol == "600519"


def test_数据响应证券与请求不一致时拒绝固化(tmp_path: Path) -> None:
    import pytest

    from bagholder.application.market_data_service import MarketDataService
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    client = FakeMarketClient(_snapshot())
    service = MarketDataService(client, store)

    with pytest.raises(ValueError, match="证券"):
        service.fetch(
            security_key="CN:000001.SZ",
            start_date=date(2026, 7, 24),
            end_date=date(2026, 7, 24),
            as_of=date(2026, 7, 24),
        )

