"""把 vn.py 节点响应映射为通用券商 Gateway。"""

from decimal import Decimal
from typing import cast

from bagholder.contracts.live_trading import ExecutionRequest
from bagholder.domain.broker import BrokerOrderReceipt
from bagholder.integrations.vnpy_client import VnpyClient


class VnpyBrokerGateway:
    """通过签名 vn.py 节点执行真实券商操作。"""

    def __init__(self, client: VnpyClient) -> None:
        self._client = client

    def health(self) -> dict[str, object]:
        return self._client.request("HEALTH", {})

    def query_funds(self, account_id: str) -> dict[str, Decimal]:
        result = self._client.request("QUERY_FUNDS", {"account_id": account_id})
        numeric_fields = ("cash_available", "net_asset", "frozen_cash", "buying_power")
        funds = {
            key: Decimal(str(result[key]))
            for key in numeric_fields
            if key in result
        }
        if "cash_available" not in funds or "net_asset" not in funds:
            raise ValueError("vn.py 资金响应缺少必要字段")
        return funds

    def query_positions(self, account_id: str) -> list[dict[str, object]]:
        result = self._client.request("QUERY_POSITIONS", {"account_id": account_id})
        return self._items(result, "positions")

    def query_orders(self, account_id: str) -> list[dict[str, object]]:
        result = self._client.request("QUERY_ORDERS", {"account_id": account_id})
        return self._items(result, "orders")

    def query_trades(self, account_id: str) -> list[dict[str, object]]:
        result = self._client.request("QUERY_TRADES", {"account_id": account_id})
        return self._items(result, "trades")

    def submit(self, request: ExecutionRequest) -> BrokerOrderReceipt:
        result = self._client.request(
            "SUBMIT_ORDER",
            {"request": request.model_dump(mode="json")},
        )
        return BrokerOrderReceipt(
            account_id=str(result["account_id"]),
            broker_order_id=str(result["broker_order_id"]),
            accepted=bool(result["accepted"]),
            status=str(result["status"]),
        )

    def cancel(self, account_id: str, broker_order_id: str) -> bool:
        result = self._client.request(
            "CANCEL_ORDER",
            {"account_id": account_id, "broker_order_id": broker_order_id},
        )
        return bool(result["cancelled"])

    @staticmethod
    def _items(result: dict[str, object], key: str) -> list[dict[str, object]]:
        items = result.get(key)
        if not isinstance(items, list) or not all(isinstance(item, dict) for item in items):
            raise ValueError(f"vn.py {key} 响应格式无效")
        return cast(list[dict[str, object]], items)
