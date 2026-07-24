"""真实行情获取、校验和证据固化。"""

from datetime import date
from typing import Protocol

from bagholder.contracts.market_data import FetchMarketRequest, MarketSnapshot
from bagholder.infrastructure.sqlite_store import EvidenceRecord, SqlitePlatformStore


class MarketDataClient(Protocol):
    """行情服务所需的隔离客户端能力。"""

    def fetch_market(self, request: FetchMarketRequest) -> MarketSnapshot: ...


class MarketDataService:
    """将外部行情转换为已登记的不可变证据。"""

    def __init__(
        self,
        client: MarketDataClient,
        store: SqlitePlatformStore,
    ) -> None:
        self._client = client
        self._store = store

    def fetch(
        self,
        *,
        security_key: str,
        start_date: date,
        end_date: date,
        as_of: date,
    ) -> EvidenceRecord:
        """拉取指定 A 股日线并在校验后保存。"""

        symbol = security_key.removeprefix("CN:").split(".", maxsplit=1)[0]
        request = FetchMarketRequest(
            symbol=symbol,
            security_key=security_key,
            start_date=start_date,
            end_date=end_date,
            as_of=as_of,
        )
        snapshot = self._client.fetch_market(request)
        if snapshot.security_key != security_key:
            raise ValueError("行情响应证券与请求证券不一致")
        if (
            snapshot.start_date != start_date
            or snapshot.end_date != end_date
            or snapshot.as_of != as_of
        ):
            raise ValueError("行情响应时间范围与请求不一致")
        return self._store.save_evidence(
            kind="MARKET",
            security_key=security_key,
            payload=snapshot.model_dump(mode="json"),
            created_at=snapshot.retrieved_at,
        )

