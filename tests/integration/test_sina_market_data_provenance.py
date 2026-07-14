"""验证新浪原始响应与规范化行情都追加保存到本地事实链。"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

from stock_agent.adapters.market_data.sina_adapter import (
    SinaDataSourceError,
    SinaHttpAdapter,
    SinaPersistenceProof,
)
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
        versioning_service=service,
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


def test_新浪记录器规范化工件写入失败时原始和规范化均不残留(
    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """真实记录器必须将一对工件作为同一批次发布，失败时不得留下半批次。"""

    service = VersioningService(local_data_root)
    原写入 = service._artifacts.write_artifact

    def 拒绝规范化工件(dataset: str, *参数: object, **关键字参数: object):
        if dataset == "market-data-normalized":
            raise OSError("规范化工件写入失败")
        return 原写入(dataset, *参数, **关键字参数)

    monkeypatch.setattr(service._artifacts, "write_artifact", 拒绝规范化工件)

    with pytest.raises(OSError, match="规范化工件写入失败"):
        SinaMarketDataFactRecorder(service).record(新浪响应(), b'{"quotes":[]}')

    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
    assert service._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)


def test_新浪事实保存失败时不返回未持久化行情(local_data_root: Path) -> None:
    """事实链提交失败必须使整批读取失败，不能把内存结果冒充事实。"""

    class 失败记录器:
        def record(self, raw_response: bytes, quotes: list[object]) -> None:
            raise RuntimeError("本地保存失败")

    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=失败记录器(),
        versioning_service=VersioningService(local_data_root),
    )

    with pytest.raises(SinaDataSourceError, match="保存"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))


def test_新浪适配器拒绝形态正确但未真实落盘的持久化证明(local_data_root: Path) -> None:
    """即使证明字段和原始响应哈希均正确，缺少真实工件也必须整批失败。"""

    raw_response = 新浪响应()
    proof = SinaPersistenceProof(
        raw_artifact_version_id="raw-1",
        normalized_artifact_version_id="normalized-1",
        parent_version_id="raw-1",
    )

    class 空记录器:
        def record(self, raw_response: bytes, quotes: list[object]) -> SinaPersistenceProof:
            return proof

    adapter = SinaHttpAdapter(
        lambda _url: raw_response,
        fact_recorder=空记录器(),
        versioning_service=VersioningService(local_data_root),
    )

    with pytest.raises(SinaDataSourceError, match="工件"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))


def test_新浪适配器拒绝父版本关联不匹配的真实工件(local_data_root: Path) -> None:
    """真实落盘后仍必须回读校验父版本关联。"""

    service = VersioningService(local_data_root)

    class 篡改证明记录器:
        def record(self, raw_response: bytes, normalized_content: bytes) -> SinaPersistenceProof:
            raw = service.commit_bytes(
                dataset="market-data-raw",
                version_id="raw-1",
                content=raw_response,
                source_id="sina",
            )
            normalized = service.commit_bytes(
                dataset="market-data-normalized",
                version_id="normalized-1",
                content=normalized_content,
                source_id="sina",
                parent_version_id="other-raw",
            )
            return SinaPersistenceProof(
                raw_artifact_version_id=raw.version_id,
                normalized_artifact_version_id=normalized.version_id,
                parent_version_id=raw.version_id,
            )

    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=篡改证明记录器(),
        versioning_service=service,
    )

    with pytest.raises(SinaDataSourceError, match="工件"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))


@pytest.mark.parametrize(
    "proof",
    [
        None,
        SinaPersistenceProof(
            raw_artifact_version_id="raw-1",
            normalized_artifact_version_id="normalized-1",
            parent_version_id="other-raw",
        ),
    ],
)
def test_新浪适配器拒绝缺失或不完整的持久化证明(
    proof: SinaPersistenceProof | None, local_data_root: Path
) -> None:
    """公共适配器不能信任空记录器；原始与规范化工件证明必须完整关联。"""

    class 返回证明的记录器:
        def record(
            self, raw_response: bytes, normalized_content: bytes
        ) -> SinaPersistenceProof | None:
            return proof

    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=返回证明的记录器(),
        versioning_service=VersioningService(local_data_root),
    )

    with pytest.raises(SinaDataSourceError, match="证明"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))


@pytest.mark.parametrize(
    "normalized_content",
    [
        b'{"source_id":"sina","quotes":[]}',
        b'{"source_id":"sina","quotes":[{"price":1.0}]}',
    ],
)
def test_新浪适配器拒绝父链正确但不属于当前报价批次的规范化工件(
    normalized_content: bytes, local_data_root: Path
) -> None:
    """规范化工件必须精确承载本次适配器生成的完整报价批次。"""

    service = VersioningService(local_data_root)

    class 写入旧批次的记录器:
        def record(self, raw_response: bytes, normalized_payload: bytes) -> SinaPersistenceProof:
            raw = service.commit_bytes(
                dataset="market-data-raw",
                version_id="raw-1",
                content=raw_response,
                source_id="sina",
            )
            normalized = service.commit_bytes(
                dataset="market-data-normalized",
                version_id="normalized-1",
                content=normalized_content,
                source_id="sina",
                parent_version_id=raw.version_id,
            )
            return SinaPersistenceProof(
                raw_artifact_version_id=raw.version_id,
                normalized_artifact_version_id=normalized.version_id,
                parent_version_id=raw.version_id,
            )

    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=写入旧批次的记录器(),
        versioning_service=service,
    )

    with pytest.raises(SinaDataSourceError, match="规范化"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
