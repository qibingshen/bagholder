"""供测试和本地演示使用的内存仓储。"""

from dataclasses import dataclass, field

from bagholder.domain.broker import BrokerOrderReceipt


@dataclass
class InMemoryTradingRepository:
    """按幂等键保存交易回执。"""

    receipts: dict[str, BrokerOrderReceipt] = field(default_factory=dict)

    def find(self, idempotency_key: str) -> BrokerOrderReceipt | None:
        return self.receipts.get(idempotency_key)

    def save(self, idempotency_key: str, receipt: BrokerOrderReceipt) -> None:
        self.receipts[idempotency_key] = receipt
