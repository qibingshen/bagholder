"""提供只读 Finnhub 美股行情适配器，并强制追加保存事实快照。"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from urllib.parse import quote
from zoneinfo import ZoneInfo

from stock_agent.adapters.market_data.base import NormalizedQuote, SourceCapability
from stock_agent.application.versioning_service import VersioningService
from stock_agent.contracts.common import Freshness
from stock_agent.domain.freshness import calculate_age_seconds, classify_freshness
from stock_agent.domain.market import InstrumentIdentity, Market


class FinnhubDataSourceError(RuntimeError):
    """表示美股行情不可验证或未完成本地事实保存。"""


class FinnhubMarketDataFactRecorder:
    """将 Finnhub 原始响应和规范化响应以同一版本批次追加保存。"""

    def __init__(self, versioning_service: VersioningService) -> None:
        self._versioning_service = versioning_service

    def record(self, raw_response: bytes, normalized_content: bytes, data_version: str) -> None:
        """仅在原始和规范化工件同时可公开时返回。"""

        raw_version = f"{data_version}-raw"
        normalized_version = f"{data_version}-normalized"
        self._versioning_service.commit_batch(
            batch_id=f"{data_version}-batch",
            items=[
                {
                    "dataset": "market-data-raw",
                    "version_id": raw_version,
                    "content": raw_response,
                    "source_id": "finnhub",
                },
                {
                    "dataset": "market-data-normalized",
                    "version_id": normalized_version,
                    "content": normalized_content,
                    "source_id": "finnhub",
                    "parent_version_id": raw_version,
                },
            ],
        )


class FinnhubHttpAdapter:
    """读取用户授权的 Finnhub 行情；密钥只由注入提供方读取。"""

    capability = SourceCapability(
        source_id="finnhub", markets=("US",), credential_required=True, supports_realtime=True
    )

    def __init__(
        self,
        *,
        http_get: Callable[[str], bytes],
        api_key_provider: Callable[[], str],
        fact_recorder: FinnhubMarketDataFactRecorder,
        versioning_service: VersioningService,
    ) -> None:
        self._http_get = http_get
        self._api_key_provider = api_key_provider
        self._fact_recorder = fact_recorder
        self._versioning_service = versioning_service

    def fetch_quotes(
        self, codes: Sequence[str], collected_at: datetime
    ) -> Sequence[NormalizedQuote]:
        """拉取完整批次；任一代码失败则拒绝返回局部或未保存行情。"""

        if len(codes) != 1 or not codes[0].startswith(("NASDAQ:", "NYSE:", "AMEX:")):
            raise FinnhubDataSourceError("Finnhub 请求必须为单个交易所加冒号的美股代码")
        key = self._api_key_provider()
        if not key:
            raise FinnhubDataSourceError("Finnhub 未配置本机凭据")
        exchange, symbol = codes[0].split(":", 1)
        try:
            raw_response = self._http_get(
                f"https://finnhub.io/api/v1/quote?symbol={quote(symbol)}&token={quote(key)}"
            )
            payload = json.loads(raw_response.decode("utf-8"))
            price, timestamp = float(payload["c"]), int(payload["t"])
            market_time = datetime.fromtimestamp(timestamp, UTC).astimezone(
                ZoneInfo(Market.US.timezone)
            )
            if price <= 0 or market_time > collected_at:
                raise ValueError("报价价格或市场时间无效")
            suffix = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f%z")
            data_version = f"finnhub-{hashlib.sha256(raw_response).hexdigest()[:16]}-{suffix}"
            freshness = Freshness(
                state=classify_freshness(Market.US, market_time, collected_at, is_open=True),
                age_seconds=calculate_age_seconds(market_time, collected_at),
            )
            quote_fact = NormalizedQuote(
                security_id=InstrumentIdentity(Market.US, exchange, symbol, "USD"),
                price=price,
                source_id="finnhub",
                market_time=market_time,
                collected_at=collected_at,
                data_version=data_version,
                freshness=freshness,
            )
            normalized_content = json.dumps(
                quote_fact.model_dump(mode="json"), ensure_ascii=False, sort_keys=True
            ).encode("utf-8")
            self._fact_recorder.record(raw_response, normalized_content, data_version)
            if not self._versioning_service.version_exists(
                "market-data-raw", f"{data_version}-raw"
            ):
                raise FinnhubDataSourceError("Finnhub 原始行情未实际落盘")
            return (quote_fact,)
        except FinnhubDataSourceError:
            raise
        except Exception as error:
            raise FinnhubDataSourceError("Finnhub 行情响应或本地事实保存无效") from error
