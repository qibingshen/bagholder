"""集中定义 A 股、港股和美股的证券身份、时区与币种比较边界。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Market(StrEnum):
    """项目正式支持的三个市场。"""

    CN = "CN"
    HK = "HK"
    US = "US"

    @property
    def timezone(self) -> str:
        """返回交易日历和市场时间使用的 IANA 时区。"""

        return {
            Market.CN: "Asia/Shanghai",
            Market.HK: "Asia/Hong_Kong",
            Market.US: "America/New_York",
        }[self]


class MarketRuleError(ValueError):
    """表示会导致量化比较不可信的市场规则错误。"""


@dataclass(frozen=True, slots=True)
class InstrumentIdentity:
    """用市场、交易所和显示代码共同定位证券，避免跨市场代码歧义。"""

    market: Market
    exchange: str
    display_code: str
    currency: str

    def __post_init__(self) -> None:
        """拒绝不完整身份，避免供应商代码直接混入业务主键。"""

        if not self.exchange or not self.display_code or not self.currency:
            raise MarketRuleError("证券身份必须包含交易所、显示代码和币种")

    @property
    def market_timezone(self) -> str:
        """提供证券所属市场的时间边界。"""

        return self.market.timezone


class CurrencyComparison:
    """只在同币种或给定预测时点可用汇率时计算跨市场金额比较。"""

    @staticmethod
    def compare(
        left: float,
        left_currency: str,
        right: float,
        right_currency: str,
        exchange_rate: float | None,
    ) -> float:
        """返回左值相对右值的比率，缺失汇率时明确拒绝。"""

        if right == 0:
            raise MarketRuleError("比较基准不能为零")
        if left_currency != right_currency:
            if exchange_rate is None or exchange_rate <= 0:
                raise MarketRuleError("跨币种比较缺少同一时点可用汇率")
            right *= exchange_rate
        return left / right


def resolve_instrument_identity(
    display_code: str,
    candidates: list[InstrumentIdentity],
    *,
    market: Market | None = None,
    exchange: str | None = None,
) -> InstrumentIdentity:
    """在调用方提供的本地目录中解析证券，非唯一显示代码绝不猜测。"""

    if not display_code:
        raise MarketRuleError("显示代码不能为空")
    matched = [item for item in candidates if item.display_code == display_code]
    if market is not None:
        matched = [item for item in matched if item.market is market]
    if exchange is not None:
        matched = [item for item in matched if item.exchange == exchange]
    if not matched:
        raise MarketRuleError("本地证券目录不存在匹配身份")
    if len(matched) != 1:
        raise MarketRuleError("显示代码非唯一，必须提供市场或交易所")
    return validate_instrument_identity(matched[0])


def validate_instrument_identity(security_id: InstrumentIdentity) -> InstrumentIdentity:
    """验证既有身份的市场、交易所、币种与代码格式组合。"""

    rules = {
        Market.CN: ({"SSE", "SZSE"}, "CNY"),
        Market.HK: ({"HKEX"}, "HKD"),
        Market.US: ({"NASDAQ", "NYSE", "AMEX"}, "USD"),
    }
    exchanges, currency = rules[security_id.market]
    if security_id.exchange not in exchanges or security_id.currency != currency:
        raise MarketRuleError("证券市场、交易所或币种不一致")
    if security_id.market is Market.CN and not _is_ascii_digits(security_id.display_code, 6):
        raise MarketRuleError("中国市场证券代码必须为六码 ASCII 数字")
    if security_id.market is Market.HK and not _is_ascii_digits(security_id.display_code, 5):
        raise MarketRuleError("香港市场证券代码必须为五位 ASCII 数字")
    if security_id.market is Market.US and not _is_us_code(security_id.display_code):
        raise MarketRuleError("美国市场证券代码格式无效")
    return security_id


def _is_ascii_digits(value: str, length: int) -> bool:
    """限制固定长度 ASCII 数字，避免全角数字或混合字符造成歧义。"""

    return len(value) == length and value.isascii() and value.isdigit()


def _is_us_code(value: str) -> bool:
    """接受常见大写美股代码和类别后缀，拒绝纯数字代码。"""

    parts = value.split(".")
    return len(parts) in {1, 2} and all(
        1 <= len(part) <= 5 and part.isascii() and part.isalpha() and part.isupper()
        for part in parts
    )
