"""通过单一批次完成标记发布不可变版本，并在启动时恢复未完成批次。"""

from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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
    """以批次日志和唯一完成标记保证多工件不会独立对外可见。"""

    def __init__(self, data_root: Path) -> None:
        self._root = data_root
        self._artifacts = ParquetArtifactStore(data_root / "artifacts")
        self._metadata = DuckDbMetadataStore(data_root / "metadata.duckdb")
        self._batches_root = data_root / ".batches"
        self._recover_incomplete_batches()

    def version_exists(self, dataset: str, version_id: str) -> bool:
        """只把单版本完成标记或已完成批次中的版本视为可查询。"""
        if (self._root / "artifacts" / dataset / version_id / "_COMPLETE").is_file():
            return True
        return self._completed_batch_contains(dataset, version_id)

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
        """提交单个既有工件；多工件必须改用 ``commit_batch``。"""
        if self.version_exists(dataset, version_id):
            raise ImmutableVersionError("已提交版本不允许静默覆盖")
        digest = self._validate_hash(content, expected_hash)
        artifact = self._artifacts.write_artifact(dataset, version_id, content)
        try:
            self._metadata.register_version(
                dataset, version_id, artifact.content_hash, parent_version_id
            )
        except Exception:
            self.rollback_versions((dataset, version_id))
            raise
        return CommittedVersion(dataset, version_id, parent_version_id, digest)

    def commit_batch(self, *, batch_id: str, items: list[dict[str, Any]]) -> list[CommittedVersion]:
        """暂存整批工件，最后仅写一个批次完成标记以原子公开。"""
        if not batch_id or not items:
            raise ValueError("批次标识和工件不能为空")
        journal = self._batch_directory(batch_id) / "manifest.json"
        if journal.exists() or (self._batch_directory(batch_id) / "_COMPLETE").exists():
            raise ImmutableVersionError("批次标识不允许重复使用")
        entries = []
        for item in items:
            dataset, version_id, content = item["dataset"], item["version_id"], item["content"]
            if (
                self.version_exists(dataset, version_id)
                or (self._root / "artifacts" / dataset / version_id).exists()
            ):
                raise ImmutableVersionError("批次包含已存在版本")
            entries.append(
                {
                    "dataset": dataset,
                    "version_id": version_id,
                    "parent_version_id": item.get("parent_version_id"),
                    "content_hash": self._validate_hash(content, item.get("expected_hash")),
                }
            )
        batch_directory = self._batch_directory(batch_id)
        batch_directory.mkdir(parents=True, exist_ok=False)
        journal.write_text(json.dumps({"entries": entries}, sort_keys=True), encoding="utf-8")
        committed: list[CommittedVersion] = []
        try:
            for item, entry in zip(items, entries, strict=True):
                artifact = self._artifacts.write_artifact(
                    entry["dataset"], entry["version_id"], item["content"], complete=False
                )
                self._metadata.register_version(
                    entry["dataset"],
                    entry["version_id"],
                    artifact.content_hash,
                    entry["parent_version_id"],
                )
                committed.append(
                    CommittedVersion(
                        entry["dataset"],
                        entry["version_id"],
                        entry["parent_version_id"],
                        entry["content_hash"],
                    )
                )
            (batch_directory / "_COMPLETE").touch()
        except Exception:
            try:
                self.rollback_batch(batch_id)
            except Exception:
                # 日志保留给下一次服务启动恢复；不会形成可查询版本。
                pass
            raise
        return committed

    def read_bytes(self, dataset: str, version_id: str) -> bytes:
        """只读取已经公开的版本。"""
        if not self.version_exists(dataset, version_id):
            raise KeyError(version_id)
        return (self._root / "artifacts" / dataset / version_id / "payload.parquet").read_bytes()

    def metadata_for(self, dataset: str, version_id: str) -> dict[str, str | None]:
        """只读取已经公开版本的元数据。"""
        if not self.version_exists(dataset, version_id):
            raise KeyError(version_id)
        return self._metadata.get_version(dataset, version_id)

    def rollback_batch(self, batch_id: str) -> None:
        """删除未完成批次的工件和元数据；失败日志留待下次启动继续恢复。"""
        manifest = self._batch_directory(batch_id) / "manifest.json"
        if manifest.exists():
            for entry in json.loads(manifest.read_text(encoding="utf-8"))["entries"]:
                self.rollback_versions((entry["dataset"], entry["version_id"]))
        shutil.rmtree(self._batch_directory(batch_id), ignore_errors=False)
        if self._batches_root.exists() and not any(self._batches_root.iterdir()):
            self._batches_root.rmdir()

    def rollback_versions(self, *versions: tuple[str, str]) -> None:
        """删除尚未公开的失败版本及其元数据。"""
        for dataset, version_id in versions:
            self._metadata._connection.execute(
                "DELETE FROM dataset_versions WHERE dataset = ? AND version_id = ?",
                [dataset, version_id],
            )
            directory = self._root / "artifacts" / dataset / version_id
            if directory.exists():
                shutil.rmtree(directory)
            dataset_directory = directory.parent
            if dataset_directory.exists() and not any(dataset_directory.iterdir()):
                dataset_directory.rmdir()

    def _recover_incomplete_batches(self) -> None:
        """启动时幂等清理未写唯一完成标记的中断批次。"""
        if not self._batches_root.exists():
            return
        for directory in list(self._batches_root.iterdir()):
            if directory.is_dir() and not (directory / "_COMPLETE").is_file():
                self.rollback_batch(directory.name)

    def _completed_batch_contains(self, dataset: str, version_id: str) -> bool:
        if not self._batches_root.exists():
            return False
        for directory in self._batches_root.iterdir():
            manifest = directory / "manifest.json"
            if not (directory / "_COMPLETE").is_file() or not manifest.is_file():
                continue
            entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
            if any(
                entry["dataset"] == dataset and entry["version_id"] == version_id
                for entry in entries
            ):
                return True
        return False

    def _batch_directory(self, batch_id: str) -> Path:
        return self._batches_root / batch_id

    @staticmethod
    def _validate_hash(content: bytes, expected_hash: str | None) -> str:
        digest = hashlib.sha256(content).hexdigest()
        if expected_hash is not None and expected_hash != digest:
            raise ValueError("暂存工件哈希校验失败")
        return digest
