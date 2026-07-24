"""可重复的假券商 Gateway。"""

from decimal import Decimal

from bagholder.contracts.live_trading import ExecutionRequest
from bagholder.domain.broker import BrokerOrderReceipt


class FakeBrokerGateway:
    """记录调用次数并返回确定回执。"""

    def __init__(self) -> None:
        self.submit_call_count = 0

    def health(self) -> dict[str, object]:
        return {"status": "READY", "live_orders": True}

    def query_funds(self, account_id: str) -> dict[str, Decimal]:
        return {"cash_available": Decimal("1000000")}

    def query_positions(self, account_id: str) -> list[dict[str, object]]:
        return []

    def query_orders(self, account_id: str) -> list[dict[str, object]]:
        return []

    def query_trades(self, account_id: str) -> list[dict[str, object]]:
        return []

    def submit(self, request: ExecutionRequest) -> BrokerOrderReceipt:
        self.submit_call_count += 1
        return BrokerOrderReceipt(
            account_id=request.proposal.account_id,
            broker_order_id=f"FAKE-{self.submit_call_count}",
            accepted=True,
            status="SUBMITTED",
        )

    def cancel(self, account_id: str, broker_order_id: str) -> bool:
        return True
