"""验证新浪原始响应与规范化行情都追加保存到本地事实链。"""

import hashlib
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
        raw_content_hash=hashlib.sha256(raw_response).hexdigest(),
        normalized_artifact_version_id="normalized-1",
        normalized_content_hash="1" * 64,
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


@pytest.mark.parametrize("tamper", ["normalized_hash", "parent_version"])
def test_新浪适配器拒绝哈希或父版本关联不匹配的真实工件(local_data_root: Path, tamper: str) -> None:
    """真实落盘后仍必须回读校验规范化哈希和父版本关联。"""

    service = VersioningService(local_data_root)
    recorder = SinaMarketDataFactRecorder(service)

    class 篡改证明记录器:
        def record(self, raw_response: bytes, quotes: list[object]) -> SinaPersistenceProof:
            if tamper == "parent_version":
                raw = service.commit_bytes(
                    dataset="market-data-raw",
                    version_id="raw-1",
                    content=raw_response,
                    source_id="sina",
                )
                normalized_content = b'{"source_id":"sina"}'
                normalized = service.commit_bytes(
                    dataset="market-data-normalized",
                    version_id="normalized-1",
                    content=normalized_content,
                    source_id="sina",
                    parent_version_id="other-raw",
                )
                return SinaPersistenceProof(
                    raw_artifact_version_id=raw.version_id,
                    raw_content_hash=raw.content_hash,
                    normalized_artifact_version_id=normalized.version_id,
                    normalized_content_hash=normalized.content_hash,
                    parent_version_id=raw.version_id,
                )
            proof = recorder.record(raw_response, quotes)
            return SinaPersistenceProof(
                raw_artifact_version_id=proof.raw_artifact_version_id,
                raw_content_hash=proof.raw_content_hash,
                normalized_artifact_version_id=proof.normalized_artifact_version_id,
                normalized_content_hash="0" * 64,
                parent_version_id=proof.parent_version_id,
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
            raw_content_hash="0" * 64,
            normalized_artifact_version_id="normalized-1",
            normalized_content_hash="1" * 64,
            parent_version_id="other-raw",
        ),
    ],
)
def test_新浪适配器拒绝缺失或不完整的持久化证明(
    proof: SinaPersistenceProof | None, local_data_root: Path
) -> None:
    """公共适配器不能信任空记录器；原始与规范化工件证明必须完整关联。"""

    class 返回证明的记录器:
        def record(self, raw_response: bytes, quotes: list[object]) -> SinaPersistenceProof | None:
            return proof

    adapter = SinaHttpAdapter(
        lambda _url: 新浪响应(),
        fact_recorder=返回证明的记录器(),
        versioning_service=VersioningService(local_data_root),
    )

    with pytest.raises(SinaDataSourceError, match="证明"):
        adapter.fetch_quotes(["sh600000"], datetime(2026, 7, 14, 1, 30, 3, tzinfo=UTC))
