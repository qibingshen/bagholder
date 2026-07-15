"""备份清单、一致性快照和哈希验证服务。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BackupIntegrityDecision:
    """备份完整性校验结果。"""

    allowed: bool
    error_code: str | None


class BackupIntegrityService:
    """校验备份文件哈希。"""

    def verify_hash(self, expected_sha256: str, actual_sha256: str) -> BackupIntegrityDecision:
        """哈希不匹配时拒绝恢复。"""

        if expected_sha256 != actual_sha256:
            return BackupIntegrityDecision(allowed=False, error_code="BACKUP_HASH_MISMATCH")
        return BackupIntegrityDecision(allowed=True, error_code=None)


@dataclass(frozen=True)
class BuiltBackupManifest:
    """由清单构建器返回的包含和排除路径摘要。"""

    included_paths: tuple[str, ...]
    excluded_paths: tuple[str, ...]


class BackupManifestBuilder:
    """构建备份清单时排除凭据和密钥文件。"""

    def build(self, paths: list[str]) -> BuiltBackupManifest:
        """按路径后缀排除敏感文件。"""

        included: list[str] = []
        excluded: list[str] = []
        for path in paths:
            if _is_sensitive_path(path):
                excluded.append(path)
            else:
                included.append(path)
        return BuiltBackupManifest(included_paths=tuple(included), excluded_paths=tuple(excluded))


class ImmutableArtifactPolicy:
    """保护原始行情、预测快照和回测工件不被静默删除。"""

    def assert_deletable(self, path: str) -> None:
        """不可变工件路径必须拒绝删除。"""

        immutable_markers = ("prediction_snapshots/", "raw_market/", "backtest_results/")
        if any(marker in path for marker in immutable_markers):
            raise ValueError("不可变工件不得删除")


def _is_sensitive_path(path: str) -> bool:
    """识别凭据、密钥和环境文件。"""

    lowered = path.lower()
    return lowered.endswith(".env") or lowered.endswith(".key") or "credential" in lowered
