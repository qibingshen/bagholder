"""集中执行市场时间、版本与跨币种可比较性规则。"""

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal

from stock_agent.domain.market import InstrumentIdentity, Market


class PointInTimeViolation(ValueError):
    """表示数据在预测时点尚不可获得，必须停止相关计算。"""


class NotComparableError(ValueError):
    """表示缺少同一时点的汇率或市场规则版本，禁止输出跨市场比较数字。"""


@dataclass(frozen=True)
class TradingCalendar:
    """记录一个市场在指定版本中的交易日，避免历史查询混用后来修订的日历。"""

    market: str
    version_id: str
    trading_days: frozenset[date]

    def __post_init__(self) -> None:
        if not self.market.strip() or not self.version_id.strip():
            raise ValueError("交易日历必须包含市场与版本标识")
        object.__setattr__(self, "trading_days", frozenset(self.trading_days))

    def is_trading_day(self, day: date) -> bool:
        """判断日期是否属于该版本日历的有效交易日。"""
        return day in self.trading_days


@dataclass(frozen=True)
class CompanyAction:
    """保存公司行动的来源与版本，使复权和历史分析能按当时事实重建。"""

    action_id: str
    action_type: str
    effective_at: datetime
    version_id: str
    source_id: str
    adjustment_ratio: int | float | Decimal | None = None
    security_id: InstrumentIdentity | None = None
    market: Market | None = None

    def __post_init__(self) -> None:
        if not all(
            (
                self.action_id.strip(),
                self.action_type.strip(),
                self.version_id.strip(),
                self.source_id.strip(),
            )
        ):
            raise ValueError("公司行动必须包含标识、类型、来源和版本")
        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
            raise ValueError("公司行动生效时间必须带时区")
        if self.adjustment_ratio is not None:
            if (
                isinstance(self.adjustment_ratio, bool)
                or not isinstance(self.adjustment_ratio, (int, float, Decimal))
                or not math.isfinite(self.adjustment_ratio)
                or self.adjustment_ratio <= 0
            ):
                raise ValueError("公司行动复权比例必须为有限正数的真实数值")
        if (
            self.security_id is not None
            and self.market is not None
            and self.security_id.market is not self.market
        ):
            raise ValueError("公司行动证券与市场必须一致")


@dataclass(frozen=True)
class ExchangeRateQuote:
    """保存有可得时间的汇率快照，禁止以晚到汇率计算早期跨市场结果。"""

    base_currency: str
    quote_currency: str
    rate: float
    market_time: datetime
    available_at: datetime
    version_id: str

    def __post_init__(self) -> None:
        if not all(
            (self.base_currency.strip(), self.quote_currency.strip(), self.version_id.strip())
        ):
            raise ValueError("汇率必须包含币种与版本标识")
        if self.rate <= 0:
            raise ValueError("汇率必须为正数")
        if self.market_time.tzinfo is None or self.available_at.tzinfo is None:
            raise ValueError("汇率时间必须带时区")


def ensure_available_at(
    prediction_time: datetime, available_at: datetime, artifact_name: str
) -> None:
    """拒绝晚于预测时点的数据，防止训练、验证和回测泄漏未来信息。"""
    if available_at > prediction_time:
        raise PointInTimeViolation(f"{artifact_name} 在预测时点后才可获得")


def compare_currency_at(
    left: float,
    left_currency: str,
    right: float,
    right_currency: str,
    exchange_rate: ExchangeRateQuote | None,
    analysis_time: datetime | None = None,
) -> float:
    """仅在同币种或存在有效汇率时计算金额比较。"""
    if right == 0:
        raise NotComparableError("比较基准为零，结果不可比较")
    if left_currency == right_currency:
        return left / right
    if exchange_rate is None or analysis_time is None:
        raise NotComparableError("缺少同一时点可用汇率，跨市场结果不可比较")
    if (
        exchange_rate.base_currency != right_currency
        or exchange_rate.quote_currency != left_currency
    ):
        raise NotComparableError("汇率币种方向与比较对象不匹配，跨市场结果不可比较")
    ensure_available_at(analysis_time, exchange_rate.available_at, "汇率")
    return left / (right * exchange_rate.rate)


def effective_actions(
    actions: Sequence[CompanyAction], analysis_time: datetime
) -> list[CompanyAction]:
    """仅返回分析时点已生效的公司行动；未来行动会阻断计算。"""
    if any(action.effective_at > analysis_time for action in actions):
        raise PointInTimeViolation("公司行动在分析时点后才生效")
    return list(actions)


def require_company_actions_for_adjustment(
    security_id: InstrumentIdentity,
    analysis_time: datetime,
    actions: Sequence[CompanyAction],
) -> list[CompanyAction]:
    """要求复权历史研究提供公司行动记录，不猜测或补造缺失数据。"""

    if not actions:
        raise PointInTimeViolation("公司行动缺失，复权历史研究不可用")
    if any(action.security_id is None for action in actions):
        raise PointInTimeViolation("公司行动缺少证券归属，不能用于目标证券复权")
    if any(action.security_id != security_id for action in actions):
        raise PointInTimeViolation("公司行动证券与目标证券不一致，不能跨证券复权")
    return effective_actions(actions, analysis_time)
