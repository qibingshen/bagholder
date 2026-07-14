"""验证新浪 A 股行情适配器的受控请求与规范化输出。"""

from datetime import UTC, datetime

from stock_agent.adapters.market_data.sina_adapter import SinaHttpAdapter
from stock_agent.domain.market import Market


class 忽略事实记录器:
    """该测试只覆盖 HTTP 解析，持久化由专门集成测试覆盖。"""

    def record(self, raw_response: bytes, quotes: list[object]) -> None:
        """不对解析测试写入共享本地目录。"""


def test_新浪适配器以精确地址读取_GBK_行情并保留完整溯源信息() -> None:
    """适配器只能使用约定地址，并将合法响应转为可量化使用的完整行情。"""

    requested_urls: list[str] = []
    response = (
        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";\n'
        'var hq_str_sz000001="平安银行,12.00,12.10,12.25,12.30,11.90,12.24,12.25,100,1000,'
        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
    ).encode("gbk")

    def 读取行情(url: str) -> bytes:
        requested_urls.append(url)
        return response

    collected_at = datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC)

    quotes = SinaHttpAdapter(读取行情, 忽略事实记录器()).fetch_quotes(
        ["sh600000", "sz000001"], collected_at
    )

    assert requested_urls == ["http://hq.sinajs.cn/list=sh600000,sz000001"]
    assert [quote.price for quote in quotes] == [10.25, 12.25]
    assert [quote.security_id.display_code for quote in quotes] == ["600000", "000001"]
    assert [quote.security_id.exchange for quote in quotes] == ["SSE", "SZSE"]
    assert all(quote.security_id.market is Market.CN for quote in quotes)
    assert all(quote.source_id == "sina" for quote in quotes)
    assert all(quote.market_time.tzinfo is not None for quote in quotes)
    assert all(quote.market_time.tzinfo.key == "Asia/Shanghai" for quote in quotes)
    assert all(quote.data_version.startswith("sina-") for quote in quotes)
    assert all(quote.freshness.state == "REALTIME" for quote in quotes)
    assert all(quote.freshness.age_seconds == 3 for quote in quotes)
