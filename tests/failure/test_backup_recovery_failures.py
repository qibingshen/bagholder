"""验证备份恢复失败场景。"""

import pytest


def test_损坏备份包哈希不匹配时拒绝恢复() -> None:
    """哈希不匹配必须阻断恢复，不能尝试原地覆盖。"""

    from stock_agent.application.backup_service import BackupIntegrityService

    decision = BackupIntegrityService().verify_hash(
        expected_sha256="a" * 64, actual_sha256="b" * 64
    )

    assert decision.allowed is False
    assert decision.error_code == "BACKUP_HASH_MISMATCH"


def test_中断恢复只能从隔离目录继续() -> None:
    """恢复中断后只能从隔离目录继续校验，不能直接切换当前数据。"""

    from stock_agent.application.restore_service import RestoreSession

    session = RestoreSession(backup_id="backup-1", staging_directory="staging")
    session.mark_interrupted()

    assert session.status == "interrupted"
    assert session.can_atomic_switch is False
    assert session.can_resume_from_staging is True


def test_备份清单排除凭据和密钥文件() -> None:
    """备份不得包含凭据明文、密钥或环境文件。"""

    from stock_agent.application.backup_service import BackupManifestBuilder

    manifest = BackupManifestBuilder().build(paths=["data/core.duckdb", ".env", "finnhub.key"])

    assert "data/core.duckdb" in manifest.included_paths
    assert ".env" in manifest.excluded_paths
    assert "finnhub.key" in manifest.excluded_paths


def test_不可变工件删除必须拒绝() -> None:
    """原始行情和预测快照等不可变工件不能被备份清理静默删除。"""

    from stock_agent.application.backup_service import ImmutableArtifactPolicy

    with pytest.raises(ValueError, match="不可变工件不得删除"):
        ImmutableArtifactPolicy().assert_deletable("prediction_snapshots/pred-1.json")
