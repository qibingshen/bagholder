"""仅供本地契约测试的 vn.py Gateway 插件，不连接真实券商。"""

from __future__ import annotations

from uuid import uuid4


class FakeVnpyGateway:
    """实现私有 Gateway 插件需要提供的原始字典接口。"""

    def health(self) -> dict[str, object]:
        return {
            "status": "READY",
            "broker_code": "CITIC",
            "account_ids": ["citic-main"],
            "live_orders": True,
            "capabilities": [
                "live_orders",
                "cancel",
                "funds_query",
                "positions_query",
                "orders_query",
                "trades_query",
                "market_data",
            ],
            "reconciled": True,
            "market_data_ready": True,
            "test_plugin": True,
        }

    def submit_order(self, request: dict[str, object]) -> dict[str, object]:
        proposal = request["proposal"]
        if not isinstance(proposal, dict):
            raise ValueError("proposal 必须是对象")
        return {
            "account_id": str(proposal["account_id"]),
            "broker_order_id": f"FAKE-LIVE-{uuid4().hex}",
            "accepted": True,
            "status": "SUBMITTED",
        }

    def cancel_order(
        self,
        account_id: str,
        broker_order_id: str,
    ) -> dict[str, object]:
        return {
            "account_id": account_id,
            "broker_order_id": broker_order_id,
            "cancelled": True,
        }

    def query_funds(self, account_id: str) -> dict[str, object]:
        return {
            "account_id": account_id,
            "cash_available": "1000000.00",
            "net_asset": "1000000.00",
        }

    def query_positions(self, account_id: str) -> dict[str, object]:
        return {"account_id": account_id, "positions": []}

    def query_orders(self, account_id: str) -> dict[str, object]:
        return {"account_id": account_id, "orders": []}

    def query_trades(self, account_id: str) -> dict[str, object]:
        return {"account_id": account_id, "trades": []}


def create_gateway() -> FakeVnpyGateway:
    """创建无外部状态的契约测试 Gateway。"""

    return FakeVnpyGateway()
