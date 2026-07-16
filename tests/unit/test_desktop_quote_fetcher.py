"""验证桌面行情入口按用户选择调用真实适配器。"""

from datetime import UTC, datetime

import pytest


def test_新浪选项读取并持久化上交所行情(tmp_path) -> None:
    """A 股入口必须使用新浪代码规则，并返回已落盘的规范化事实。"""

    requested_urls: list[str] = []
    response = (
        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-16,09:30:00,00";'
    ).encode("gbk")

    from stock_agent.desktop.quote_fetcher import fetch_quote

    quote = fetch_quote(
        source_id="sina",
        exchange="SSE",
        display_code="600000",
        root=tmp_path,
        collected_at=datetime(2026, 7, 16, 1, 30, 3, tzinfo=UTC),
        http_get=lambda url: requested_urls.append(url) or response,
    )

    assert requested_urls == ["http://hq.sinajs.cn/list=sh600000"]
    assert quote.security_id.display_code == "600000"
    assert quote.source_id == "sina"
    assert (tmp_path / "artifacts" / "market-data-raw").is_dir()
    assert (tmp_path / "artifacts" / "market-data-normalized").is_dir()


def test_桌面行情入口拒绝未知数据源(tmp_path) -> None:
    """未知来源不能被静默改用其他供应商。"""

    from stock_agent.desktop.quote_fetcher import fetch_quote

    with pytest.raises(ValueError, match="不支持"):
        fetch_quote(
            source_id="unknown",
            exchange="SSE",
            display_code="600000",
            root=tmp_path,
        )
