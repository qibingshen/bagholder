"""定义新浪 A 股请求代码的纯规范化规则。"""

from __future__ import annotations

from stock_agent.domain.market import InstrumentIdentity, Market


class UnsupportedSinaCodeError(ValueError):
    """表示证券身份不能安全转换为新浪 A 股请求代码。"""


def normalize_sina_code(identity: InstrumentIdentity) -> str:
    """将沪深 A 股六码数字代码转换为新浪请求前缀格式。"""

    if identity.market is not Market.CN:
        raise UnsupportedSinaCodeError("新浪代码规则只支持中国市场")
    if not identity.display_code.isdecimal() or len(identity.display_code) != 6:
        raise UnsupportedSinaCodeError("新浪代码必须是六位数字")

    prefix = {"SSE": "sh", "SZSE": "sz"}.get(identity.exchange)
    if prefix is None:
        raise UnsupportedSinaCodeError("新浪代码不支持该交易所")
    return f"{prefix}{identity.display_code}"
