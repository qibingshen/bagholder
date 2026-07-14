"""验证新浪原始响应与规范化行情都追加保存到本地事实链。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
from stock_agent.adapters.market_data.sina_provenance import SinaMarketDataFactRecorder
from stock_agent.application.versioning_service import VersioningService


def 新浪响应() -> bytes:
    """构造一条与新浪公开格式一致的 GBK 响应。"""

    return (
        'var hq_str_sh600000="浦发银行,10.00,10.10,10.25,10.30,9.90,10.24,10.25,100,1000,'
        '0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,2026-07-14,09:30:00,00";'
    ).encode("gbk")


def test_新浪响应和规范化结果以同一版本关联追加保存(local_data_root: Path) -> None:
    """原始字节与规范化结果必须各有不可变工件，并由版本和哈希关联。"""

    service = VersioningService(local_data_root)
    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=SinaMarketDataFactRecorder(service),
    )
    collected_at = datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC)

    quotes = adapter.fetch_quotes(["sh600000"], collected_at)

    raw_versions = list((local_data_root / "artifacts" / "market-data-raw").iterdir())
    normalized_versions = list((local_data_root / "artifacts" / "market-data-normalized").iterdir())
    assert len(raw_versions) == len(normalized_versions) == 1
    normalized = service.read_bytes("market-data-normalized", normalized_versions[0].name)
    assert quotes[0].data_version.encode() in normalized
    assert b'"source_id":"sina"' in normalized
    assert b'"market_time"' in normalized
    assert b'"collected_at"' in normalized
    assert (
        service.metadata_for("market-data-normalized", normalized_versions[0].name)[
            "parent_version_id"
        ]
        == raw_versions[0].name
    )


def test_新浪事实保存失败时不返回未持久化行情() -> None:
    """事实链提交失败必须使整批读取失败，不能把内存结果冒充事实。"""

    class 失败记录器:
        def record(self, raw_response: bytes, quotes: list[object]) -> None:
            raise RuntimeError("本地保存失败")

    adapter = SinaHttpAdapter(lambda _url: 新浪响应(), fact_recorder=失败记录器())

    with pytest.raises(SinaDataSourceError, match="保存"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
