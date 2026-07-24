"""账户、持仓和对账快照。"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class PositionSnapshot:
    """单个证券的券商持仓事实。"""

    security_key: str
    total_quantity: int
    available_to_sell: int
    average_cost: Decimal


@dataclass(frozen=True, slots=True)
class AccountSnapshot:
    """资金、持仓、活动委托和成交的同一时点快照。"""

    account_id: str
    cash_available: Decimal
    net_asset: Decimal
    positions: tuple[PositionSnapshot, ...]
    active_order_ids: tuple[str, ...]
    trade_ids: tuple[str, ...]
