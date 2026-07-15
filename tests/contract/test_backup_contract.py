"""验证备份清单、哈希、版本链和跨平台恢复契约。"""

import pytest
from pydantic import ValidationError


def test_备份清单必须包含文件哈希版本链和平台信息() -> None:
    """备份包必须能跨平台校验完整性和来源版本。"""

    from stock_agent.domain.backup import BackupManifest, BackupManifestItem

    manifest = BackupManifest(
        backup_id="backup-20260715-0001",
        created_on_platform="Windows",
        app_version="0.1.0",
        data_version="dataset-v1",
        parent_backup_id=None,
        items=(
            BackupManifestItem(path="duckdb/core.duckdb", sha256="a" * 64, size_bytes=1024),
            BackupManifestItem(
                path="parquet/daily/part-1.parquet", sha256="b" * 64, size_bytes=2048
            ),
        ),
    )

    assert manifest.total_size_bytes == 3072
    assert manifest.items[0].sha256 == "a" * 64

    with pytest.raises(ValidationError):
        BackupManifestItem(path="duckdb/core.duckdb", sha256="bad", size_bytes=1024)


def test_恢复计划必须声明隔离目录只读校验和原子切换() -> None:
    """恢复不得直接覆盖当前数据，必须先隔离校验再经用户确认切换。"""

    from stock_agent.domain.backup import RestorePlan

    plan = RestorePlan(
        backup_id="backup-20260715-0001",
        target_platform="Linux",
        staging_directory="/tmp/bagholder-restore",
        readonly_verified=True,
        requires_user_confirmation=True,
        atomic_switch=True,
    )

    assert plan.readonly_verified is True
    assert plan.atomic_switch is True

    with pytest.raises(ValidationError):
        RestorePlan(
            backup_id="backup-20260715-0001",
            target_platform="Linux",
            staging_directory="/tmp/bagholder-restore",
            readonly_verified=False,
            requires_user_confirmation=True,
            atomic_switch=True,
        )
