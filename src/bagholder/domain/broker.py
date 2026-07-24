"""券商、账户、能力和回执的通用模型。"""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from typing import Protocol

from bagholder.contracts.live_trading import ExecutionRequest


class BrokerCode(StrEnum):
    """首批支持的券商。"""

    CITIC = "CITIC"
    GUOTAI_HAITONG = "GUOTAI_HAITONG"


class BrokerApiState(StrEnum):
    """券商 API 生命周期状态。"""

    API_UNAVAILABLE = "API_UNAVAILABLE"
    DISCONNECTED = "DISCONNECTED"
    CONNECTING = "CONNECTING"
    RECONCILING = "RECONCILING"
    READY = "READY"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class GatewayCapabilities:
    """Gateway 对外声明的能力。"""

    supports_live_orders: bool
    supports_cancel: bool
    supports_funds_query: bool
    supports_positions_query: bool
    supports_order_query: bool
    supports_trade_query: bool
    supports_market_data: bool


@dataclass(frozen=True, slots=True)
class BrokerAccount:
    """脱敏账户配置。"""

    account_id: str
    broker: BrokerCode
    api_state: BrokerApiState
    currency: str
    capabilities: GatewayCapabilities


@dataclass(frozen=True, slots=True)
class BrokerOrderReceipt:
    """券商订单受理回执。"""

    account_id: str
    broker_order_id: str
    accepted: bool
    status: str


class BrokerGateway(Protocol):
    """券商无关的交易网关。"""

    def health(self) -> dict[str, object]: ...

    def query_funds(self, account_id: str) -> dict[str, Decimal]: ...

    def query_positions(self, account_id: str) -> list[dict[str, object]]: ...

    def query_orders(self, account_id: str) -> list[dict[str, object]]: ...

    def query_trades(self, account_id: str) -> list[dict[str, object]]: ...

    def submit(self, request: ExecutionRequest) -> BrokerOrderReceipt: ...

    def cancel(self, account_id: str, broker_order_id: str) -> bool: ...
