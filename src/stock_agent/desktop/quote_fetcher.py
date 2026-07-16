"""把桌面端行情选择转换为可审计的数据源适配器调用。"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from urllib.request import Request, urlopen

from stock_agent.adapters.market_data.base import NormalizedQuote
from stock_agent.adapters.market_data.finnhub_adapter import (
    FinnhubHttpAdapter,
    FinnhubMarketDataFactRecorder,
)
from stock_agent.adapters.market_data.sina_adapter import SinaHttpAdapter
from stock_agent.adapters.market_data.sina_provenance import SinaMarketDataFactRecorder
from stock_agent.application.versioning_service import VersioningService


def fetch_quote(
    *,
    source_id: str,
    exchange: str,
    display_code: str,
    root: Path,
    collected_at: datetime | None = None,
    http_get: Callable[[str], bytes] | None = None,
    api_key_provider: Callable[[], str] | None = None,
) -> NormalizedQuote:
    """读取并持久化单只证券行情，禁止在数据源间静默切换。"""

    service = VersioningService(root)
    reader = http_get or _read_http_bytes
    collected = collected_at or datetime.now(UTC)
    code = display_code.strip().upper()
    if source_id == "sina":
        prefix = {"SSE": "sh", "SZSE": "sz"}.get(exchange)
        if prefix is None:
            raise ValueError("新浪不支持所选交易所")
        adapter = SinaHttpAdapter(
            reader,
            fact_recorder=SinaMarketDataFactRecorder(service),
            versioning_service=service,
        )
        return adapter.fetch_quotes([f"{prefix}{code}"], collected)[0]
    if source_id == "finnhub":
        adapter = FinnhubHttpAdapter(
            http_get=reader,
            api_key_provider=api_key_provider or _finnhub_api_key,
            fact_recorder=FinnhubMarketDataFactRecorder(service),
            versioning_service=service,
        )
        return adapter.fetch_quotes((f"{exchange}:{code}",), collected)[0]
    raise ValueError("不支持所选行情数据源")


def _read_http_bytes(url: str) -> bytes:
    """使用供应商要求的只读请求头拉取响应，不在日志中记录凭据 URL。"""

    request = Request(
        url,
        headers={
            "Referer": "https://finance.sina.com.cn/",
            "User-Agent": "LocalStockAgent/1.0",
        },
    )
    return urlopen(request, timeout=15).read()


def _finnhub_api_key() -> str:
    """仅从系统钥匙串读取 Finnhub 密钥，不写入配置、日志或事实工件。"""

    import keyring

    return keyring.get_password("local-stock-agent", "finnhub-live") or ""
