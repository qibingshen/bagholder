"""验证桌面端只恢复已经提交的本地行情事实。"""

import json
from datetime import UTC, datetime

from stock_agent.application.versioning_service import VersioningService


def test_读取每只证券最新的已提交行情事实(tmp_path) -> None:
    """同一证券存在多个追加版本时，界面只能恢复采集时间最新的一份。"""

    service = VersioningService(tmp_path)
    older = _quote_payload("AAPL", 210.0, "version-old", "2026-07-16T01:00:00+00:00")
    latest = _quote_payload("AAPL", 211.5, "version-new", "2026-07-16T02:00:00+00:00")
    service.commit_batch(
        batch_id="quote-cache-batch",
        items=[
            {
                "dataset": "market-data-normalized",
                "version_id": "version-old-normalized",
                "content": older,
                "source_id": "finnhub",
            },
            {
                "dataset": "market-data-normalized",
                "version_id": "version-new-normalized",
                "content": latest,
                "source_id": "finnhub",
            },
        ],
    )

    from stock_agent.desktop.local_quote_cache import load_latest_quotes

    quotes = load_latest_quotes(tmp_path)

    assert len(quotes) == 1
    assert quotes[0].security_id.display_code == "AAPL"
    assert quotes[0].price == 211.5
    assert quotes[0].data_version == "version-new"


def test_忽略未提交或损坏的行情工件(tmp_path) -> None:
    """目录扫描不得让未提交文件或无效内容进入桌面行情表。"""

    invalid = tmp_path / "artifacts" / "market-data-normalized" / "orphan"
    invalid.mkdir(parents=True)
    (invalid / "payload.parquet").write_text("not-json", encoding="utf-8")

    from stock_agent.desktop.local_quote_cache import load_latest_quotes

    assert load_latest_quotes(tmp_path) == ()


def test_读取新浪批次包装中的行情事实(tmp_path) -> None:
    """新浪规范化批次的 quotes 包装不得导致已提交 A 股行情无法恢复。"""

    quote = json.loads(_quote_payload("600000", 10.25, "sina-version", "2026-07-16T02:00:00+00:00"))
    quote["security_id"] = {
        "market": "CN",
        "exchange": "SSE",
        "display_code": "600000",
        "currency": "CNY",
    }
    quote["source_id"] = "sina"
    content = json.dumps(
        {"data_version": "sina-version", "quotes": [quote], "source_id": "sina"},
        ensure_ascii=False,
    ).encode("utf-8")
    VersioningService(tmp_path).commit_bytes(
        dataset="market-data-normalized",
        version_id="sina-version-normalized",
        content=content,
        source_id="sina",
    )

    from stock_agent.desktop.local_quote_cache import load_latest_quotes

    quotes = load_latest_quotes(tmp_path)

    assert len(quotes) == 1
    assert quotes[0].security_id.display_code == "600000"
    assert quotes[0].source_id == "sina"


def _quote_payload(symbol: str, price: float, version: str, collected_at: str) -> bytes:
    return json.dumps(
        {
            "security_id": {
                "market": "US",
                "exchange": "NASDAQ",
                "display_code": symbol,
                "currency": "USD",
            },
            "price": price,
            "source_id": "finnhub",
            "market_time": datetime(2026, 7, 15, 20, 0, tzinfo=UTC).isoformat(),
            "collected_at": collected_at,
            "data_version": version,
            "freshness": {
                "state": "STALE",
                "age_seconds": int(
                    (
                        datetime.fromisoformat(collected_at)
                        - datetime(2026, 7, 15, 20, 0, tzinfo=UTC)
                    ).total_seconds()
                ),
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")
