"""验证原始行情与预测快照只能追加写入，失败暂存不会污染已验证版本。"""

from pathlib import Path

import pytest


def test_版本提交保留父版本且拒绝静默覆盖(local_data_root: Path) -> None:
    """同一版本标识不能覆盖既有事实，修订必须显式引用父版本。"""

    from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService

    service = VersioningService(local_data_root)
    original = service.commit_bytes(
        dataset="daily-bars",
        version_id="v1",
        content=b"first",
        source_id="test-source",
    )
    revised = service.commit_bytes(
        dataset="daily-bars",
        version_id="v2",
        content=b"revised",
        source_id="test-source",
        parent_version_id="v1",
        revision_reason="修订来源字段",
    )

    assert original.parent_version_id is None
    assert revised.parent_version_id == "v1"
    assert service.read_bytes("daily-bars", "v1") == b"first"

    with pytest.raises(ImmutableVersionError):
        service.commit_bytes(
            dataset="daily-bars", version_id="v1", content=b"overwrite", source_id="test-source"
        )


def test_暂存校验失败不产生可见版本(local_data_root: Path) -> None:
    """不完整暂存工件不能被登记为已提交版本。"""

    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)

    with pytest.raises(ValueError, match="哈希"):
        service.commit_bytes(
            dataset="daily-bars",
            version_id="v1",
            content=b"payload",
            source_id="test-source",
            expected_hash="0" * 64,
        )

    assert not service.version_exists("daily-bars", "v1")


def test_提交版本必须登记元数据并写入完成标记(local_data_root: Path) -> None:
    """版本链只有在工件完成与 DuckDB 元数据同时存在时才可供查询。"""

    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    committed = service.commit_bytes(
        dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
    )

    assert (local_data_root / "artifacts" / "daily-bars" / "v1" / "_COMPLETE").is_file()
    assert service.metadata_for("daily-bars", "v1")["content_hash"] == committed.content_hash


@pytest.mark.parametrize("损坏内容", ['{"entries":[', "{}"])
def test_启动恢复损坏批次日志时清理元数据和双方工件(local_data_root: Path, 损坏内容: str) -> None:
    """截断日志不得阻断初始化，已登记的未完成批次必须被安全清理。"""

    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    batch_id = "损坏日志批次"
    batch_directory = local_data_root / ".batches" / batch_id
    batch_directory.mkdir(parents=True)
    batch_directory.joinpath("manifest.json").write_text(损坏内容, encoding="utf-8")
    for dataset, version_id in (
        ("market-data-raw", "raw-1"),
        ("market-data-normalized", "normalized-1"),
    ):
        artifact = service._artifacts.write_artifact(
            dataset, version_id, b"payload", complete=False
        )
        service._metadata.register_batch_version(
            batch_id, dataset, version_id, artifact.content_hash, None
        )

    recovered = VersioningService(local_data_root)

    assert not batch_directory.exists()
    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
    assert recovered._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)
