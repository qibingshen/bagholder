"""验证 Finnhub 美股报价的本地事实边界。"""

from datetime import UTC, datetime


def test_finnhub报价先持久化再返回规范化事实(tmp_path) -> None:
    """有效报价必须保留来源、市场时间、采集时间和数据版本。"""

    from stock_agent.adapters.market_data.finnhub_adapter import (
        FinnhubHttpAdapter,
        FinnhubMarketDataFactRecorder,
    )
    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(tmp_path)
    adapter = FinnhubHttpAdapter(
        http_get=lambda _url: b'{"c":201.5,"t":1784160000}',
        api_key_provider=lambda: "test-key",
        fact_recorder=FinnhubMarketDataFactRecorder(service),
        versioning_service=service,
    )

    quote = adapter.fetch_quotes(["NASDAQ:AAPL"], datetime(2026, 7, 16, 0, 0, 5, tzinfo=UTC))[0]

    assert quote.security_id.display_code == "AAPL"
    assert quote.security_id.exchange == "NASDAQ"
    assert quote.source_id == "finnhub"
    assert quote.data_version.startswith("finnhub-")
    assert service.version_exists("market-data-raw", quote.data_version + "-raw")
