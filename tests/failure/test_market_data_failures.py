"""验证新浪代码规则拒绝不安全或不受支持的身份。"""

from datetime import UTC, datetime

import pytest

from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
from stock_agent.adapters.market_data.sina_codes import (
    UnsupportedSinaCodeError,
    normalize_sina_code,
)
from stock_agent.domain.market import InstrumentIdentity, Market


class 忽略事实记录器:
    """隔离响应校验测试的记录端口，不替代持久化集成测试。"""

    def record(self, raw_response: bytes, quotes: list[object]) -> None:
        """响应校验失败路径不会调用该端口。"""


def 新浪响应(日期: str, 时间: str) -> bytes:
    """构造字段数量完整的单条新浪响应，供失败边界覆盖使用。"""

    fields = ["浦发银行", "10.00", "10.10", "10.25", *("0" for _ in range(26)), 日期, 时间, "00"]
    return f'var hq_str_sh600000="{",".join(fields)}";'.encode("gbk")


@pytest.mark.parametrize(
    ("exchange", "display_code", "expected"),
    [("SSE", "600000", "sh600000"), ("SZSE", "000001", "sz000001")],
)
def test_新浪代码规范化支持沪深交易所(exchange: str, display_code: str, expected: str) -> None:
    """新浪 A 股请求代码必须携带正确交易所前缀。"""

    identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")

    assert normalize_sina_code(identity) == expected


@pytest.mark.parametrize(
    "identity",
    [
        InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
        InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
        InstrumentIdentity(Market.CN, "BSE", "830000", "CNY"),
        InstrumentIdentity(Market.CN, "SSE", "60000", "CNY"),
        InstrumentIdentity(Market.CN, "SZSE", "0000A1", "CNY"),
        InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
    ],
)
def test_新浪代码规范化拒绝跨市场交易所和非法代码(
    identity: InstrumentIdentity,
) -> None:
    """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""

    with pytest.raises(UnsupportedSinaCodeError):
        normalize_sina_code(identity)


@pytest.mark.parametrize("codes", [[], ["600000"], ["sh60000"], ["xx600000"], ["sh６０００００"]])
def test_新浪适配器拒绝空或非法请求代码(codes: list[str]) -> None:
    """请求代码必须已是沪深前缀加六码 ASCII 数字，避免构造越界地址。"""

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(lambda _url: b"", 忽略事实记录器()).fetch_quotes(codes, datetime.now(UTC))


@pytest.mark.parametrize(
    "response",
    [
        RuntimeError("网络故障"),
        b"\xff",
        'var hq_str_sh600000="浦发银行,10.00";'.encode("gbk"),
        'var hq_str_sh600000="浦发银行,abc,10.10,无效";'.encode("gbk"),
        新浪响应("2026-02-30", "09:30:00"),
        新浪响应("2026-07-14", "25:30:00"),
    ],
)
def test_新浪适配器拒绝异常或不完整响应且不返回部分行情(response: bytes | Exception) -> None:
    """读取、解码、字段和市场时间任一异常都必须作为数据源错误整体失败。"""

    def 读取行情(_url: str) -> bytes:
        if isinstance(response, Exception):
            raise response
        return response

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(读取行情, 忽略事实记录器()).fetch_quotes(
            ["sh600000"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC)
        )


def test_新浪适配器响应缺少任一请求代码时拒绝全部行情() -> None:
    """多证券响应缺行时不能泄露已成功解析的部分结果。"""

    response = 新浪响应("2026-07-14", "09:30:00")

    with pytest.raises(SinaDataSourceError):
        SinaHttpAdapter(lambda _url: response, 忽略事实记录器()).fetch_quotes(
            ["sh600000", "sz000001"], datetime(2026, 7, 14, 1, 30, tzinfo=UTC)
        )
