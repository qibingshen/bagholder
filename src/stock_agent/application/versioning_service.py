"""通过暂存、校验和原子目录移动保存不可变版本。"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

from stock_agent.adapters.storage.duckdb_store import DuckDbMetadataStore
from stock_agent.adapters.storage.parquet_store import ParquetArtifactStore


class ImmutableVersionError(ValueError):
    """表示试图覆盖已经提交的量化事实版本。"""


@dataclass(frozen=True, slots=True)
class CommittedVersion:
    """描述已经校验并可被查询的版本链节点。"""

    dataset: str
    version_id: str
    parent_version_id: str | None
    content_hash: str


class VersioningService:
    """将暂存工件校验后一次性提交，失败时不改变任何已验证版本。"""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root
        self._artifacts = ParquetArtifactStore(data_root / "artifacts")
        self._metadata = DuckDbMetadataStore(data_root / "metadata.duckdb")

    def version_exists(self, dataset: str, version_id: str) -> bool:
        """判断指定版本是否已经提交。"""
        return (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file()

    def commit_bytes(
        self,
        *,
        dataset: str,
        version_id: str,
        content: bytes,
        source_id: str,
        parent_version_id: str | None = None,
        revision_reason: str | None = None,
        expected_hash: str | None = None,
    ) -> CommittedVersion:
        """校验暂存字节后提交新版本，禁止覆盖既有目录。"""
        if self.version_exists(dataset, version_id):
            raise ImmutableVersionError("已提交版本不允许静默覆盖")
        digest = hashlib.sha256(content).hexdigest()
        if expected_hash is not None and expected_hash != digest:
            raise ValueError("暂存工件哈希校验失败")
        artifact = self._artifacts.write_artifact(dataset, version_id, content)
        self._metadata.register_version(
            dataset, version_id, artifact.content_hash, parent_version_id
        )
        return CommittedVersion(dataset, version_id, parent_version_id, digest)

    def read_bytes(self, dataset: str, version_id: str) -> bytes:
        """读取指定不可变版本，不隐式改为当前版本。"""
        return (self._root / "artifacts" / dataset / version_id / "payload.parquet").read_bytes()

    def metadata_for(self, dataset: str, version_id: str) -> dict[str, str | None]:
        """读取与不可变工件关联的 DuckDB 元数据。"""
        return self._metadata.get_version(dataset, version_id)

    def rollback_versions(self, *versions: tuple[str, str]) -> None:
        """删除尚未对外返回的失败批次版本及其元数据。"""
        for dataset, version_id in versions:
            self._metadata._connection.execute(
                "DELETE FROM dataset_versions WHERE dataset = ? AND version_id = ?",
                [dataset, version_id],
            )
            directory = self._root / "artifacts" / dataset / version_id
            if directory.exists():
                for path in directory.iterdir():
                    path.unlink()
                directory.rmdir()
                dataset_directory = directory.parent
                if not any(dataset_directory.iterdir()):
                    dataset_directory.rmdir()
