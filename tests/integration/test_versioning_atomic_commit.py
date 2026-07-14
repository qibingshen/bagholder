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


def test_single_commit_marker_failure_is_invisible_and_recovered(
    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """元数据已登记但完成标记未公开时不得读取半提交。"""
    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    original_touch = Path.touch

    def reject_single_complete_marker(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "_COMPLETE" and ".batches" not in path.parts:
            raise OSError("单工件完成标记失败")
        original_touch(path, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", reject_single_complete_marker)
    with pytest.raises(OSError, match="完成标记"):
        service.commit_bytes(
            dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
        )

    assert not service.version_exists("daily-bars", "v1")
    with pytest.raises(KeyError):
        service.read_bytes("daily-bars", "v1")
    with pytest.raises(KeyError):
        service.metadata_for("daily-bars", "v1")

    recovered = VersioningService(local_data_root)
    assert not (local_data_root / "artifacts" / "daily-bars").exists()
    assert recovered._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)


def test_interrupted_single_commit_is_recovered_on_next_startup(
    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """进程在补偿前中断时，下一次启动仍能从暂存目录清理全部残留。"""
    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    original_touch = Path.touch

    def reject_single_complete_marker(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "_COMPLETE" and ".batches" not in path.parts:
            raise OSError("单工件完成标记失败")
        original_touch(path, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", reject_single_complete_marker)

    def reject_rollback(_batch_id: str) -> None:
        raise OSError("进程中断")

    monkeypatch.setattr(service, "rollback_batch", reject_rollback)
    with pytest.raises(OSError, match="完成标记"):
        service.commit_bytes(
            dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
        )

    assert not service.version_exists("daily-bars", "v1")
    recovered = VersioningService(local_data_root)
    assert not (local_data_root / "artifacts" / "daily-bars").exists()
    assert recovered._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)


def test_single_commit_is_invisible_until_its_batch_is_published(
    local_data_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """单工件自身完成且元数据已登记时，仍必须等待所属批次公开。"""
    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    original_touch = Path.touch

    def interrupt_before_batch_publication(path: Path, *args: object, **kwargs: object) -> None:
        if path.name == "_COMPLETE" and ".batches" in path.parts:
            raise OSError("进程在批次发布前中断")
        original_touch(path, *args, **kwargs)

    monkeypatch.setattr(Path, "touch", interrupt_before_batch_publication)
    monkeypatch.setattr(service, "rollback_batch", lambda _batch_id: None)

    with pytest.raises(OSError, match="批次发布前中断"):
        service.commit_bytes(
            dataset="daily-bars", version_id="v1", content=b"payload", source_id="test-source"
        )

    assert not service.version_exists("daily-bars", "v1")
    with pytest.raises(KeyError):
        service.read_bytes("daily-bars", "v1")
    with pytest.raises(KeyError):
        service.metadata_for("daily-bars", "v1")

    recovered = VersioningService(local_data_root)
    assert not (local_data_root / "artifacts" / "daily-bars").exists()
    assert recovered._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)


@pytest.mark.parametrize("damaged_journal", ["{}", '{"entries":[]}', '{"entries":['])
def test_damaged_or_empty_journal_without_batch_index_uses_staging_manifest_for_recovery(
    local_data_root: Path, damaged_journal: str
) -> None:
    """恢复以暂存目录中的原子清单为准，不能依赖已登记批次索引。"""
    import json

    from stock_agent.application.versioning_service import VersioningService

    service = VersioningService(local_data_root)
    batch_directory = local_data_root / ".batches" / "无索引损坏批次"
    batch_directory.mkdir(parents=True)
    entries = [
        {"dataset": "market-data-raw", "version_id": "raw-1", "parent_version_id": None},
        {
            "dataset": "market-data-normalized",
            "version_id": "normalized-1",
            "parent_version_id": "raw-1",
        },
    ]
    batch_directory.joinpath("recovery.json").write_text(
        json.dumps({"entries": entries}), encoding="utf-8"
    )
    batch_directory.joinpath("manifest.json").write_text(damaged_journal, encoding="utf-8")
    for entry in entries:
        service._artifacts.write_artifact(
            entry["dataset"], entry["version_id"], b"payload", complete=False
        )

    recovered = VersioningService(local_data_root)

    assert not batch_directory.exists()
    assert not (local_data_root / "artifacts" / "market-data-raw").exists()
    assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
    assert recovered._metadata._connection.execute(
        "SELECT COUNT(*) FROM dataset_versions"
    ).fetchone() == (0,)
