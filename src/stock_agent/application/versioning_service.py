"""通过单一批次完成标记发布不可变版本，并在启动时恢复未完成批次。"""

from __future__ import annotations

import hashlib
import json
import shutil
import uuid
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
        """仅在所属批次完成公开后，才将版本视为可查询。"""
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
        batch_id = f"single-{uuid.uuid4().hex}"
        entries = [
            {
                "dataset": dataset,
                "version_id": version_id,
                "parent_version_id": parent_version_id,
                "content_hash": digest,
            }
        ]
        batch_directory = self._create_batch_directory(batch_id, entries)
        try:
            artifact = self._artifacts.write_artifact(dataset, version_id, content, complete=False)
            self._metadata.register_batch_version(
                batch_id, dataset, version_id, artifact.content_hash, parent_version_id
            )
            artifact.complete_marker.touch()
            (batch_directory / "_COMPLETE").touch()
        except Exception:
            try:
                self.rollback_batch(batch_id)
            except Exception:
                # 暂存清单会在下一次启动时清理，保留原始提交失败原因。
                pass
            raise
        return CommittedVersion(dataset, version_id, parent_version_id, digest)

    def commit_batch(self, *, batch_id: str, items: list[dict[str, Any]]) -> list[CommittedVersion]:
        """暂存整批工件，最后仅写一个批次完成标记以原子公开。"""
        if not batch_id or not items:
            raise ValueError("批次标识和工件不能为空")
        batch_directory = self._batch_directory(batch_id)
        journal = batch_directory / "manifest.json"
        if journal.exists() or (batch_directory / "_COMPLETE").exists():
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
        self._create_batch_directory(batch_id, entries)
        committed: list[CommittedVersion] = []
        try:
            for item, entry in zip(items, entries, strict=True):
                artifact = self._artifacts.write_artifact(
                    entry["dataset"], entry["version_id"], item["content"], complete=False
                )
                self._metadata.register_batch_version(
                    batch_id,
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
        batch_directory = self._batch_directory(batch_id)
        versions = set(self._metadata.batch_versions(batch_id))
        versions.update(self._journal_versions(batch_directory / "recovery.json"))
        versions.update(self._journal_versions(batch_directory / "manifest.json"))
        if versions:
            self.rollback_versions(*versions)
        self._metadata.delete_batch_versions(batch_id)
        shutil.rmtree(batch_directory, ignore_errors=False)
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
            if directory.is_dir() and (
                not (directory / "_COMPLETE").is_file()
                or not self._journal_is_valid(directory / "recovery.json")
            ):
                self.rollback_batch(directory.name)

    def _completed_batch_contains(self, dataset: str, version_id: str) -> bool:
        if not self._batches_root.exists():
            return False
        for directory in self._batches_root.iterdir():
            manifest = directory / "recovery.json"
            if (
                not (directory / "_COMPLETE").is_file()
                or not manifest.is_file()
                or not self._metadata.has_version(dataset, version_id)
            ):
                continue
            if not self._journal_is_valid(manifest):
                continue
            entries = self._journal_entries(manifest)
            if any(
                entry["dataset"] == dataset and entry["version_id"] == version_id
                for entry in entries
            ):
                if (
                    len(entries) == 1
                    and not (
                        self._root / "artifacts" / dataset / version_id / "_COMPLETE"
                    ).is_file()
                ):
                    continue
                return True
        return False

    def _batch_directory(self, batch_id: str) -> Path:
        return self._batches_root / batch_id

    def _create_batch_directory(self, batch_id: str, entries: list[dict[str, Any]]) -> Path:
        """先原子落盘完整恢复清单，再开始写入任何工件或元数据。"""
        batch_directory = self._batch_directory(batch_id)
        batch_directory.mkdir(parents=True, exist_ok=False)
        self._write_journal_atomically(batch_directory / "recovery.json", entries)
        self._write_journal_atomically(batch_directory / "manifest.json", entries)
        return batch_directory

    @staticmethod
    def _write_journal_atomically(journal: Path, entries: list[dict[str, Any]]) -> None:
        temporary = journal.with_name(f".{journal.name}.{uuid.uuid4().hex}.tmp")
        try:
            temporary.write_text(json.dumps({"entries": entries}, sort_keys=True), encoding="utf-8")
            temporary.replace(journal)
        finally:
            if temporary.exists():
                temporary.unlink()

    @classmethod
    def _journal_is_valid(cls, manifest: Path) -> bool:
        try:
            cls._journal_entries(manifest)
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return False
        return True

    @staticmethod
    def _journal_entries(manifest: Path) -> list[dict[str, Any]]:
        entries = json.loads(manifest.read_text(encoding="utf-8"))["entries"]
        if (
            not entries
            or not isinstance(entries, list)
            or any(
                not isinstance(entry, dict)
                or not isinstance(entry.get("dataset"), str)
                or not isinstance(entry.get("version_id"), str)
                for entry in entries
            )
        ):
            raise ValueError("批次日志条目无效")
        return entries

    @classmethod
    def _journal_versions(cls, manifest: Path) -> set[tuple[str, str]]:
        try:
            return {
                (entry["dataset"], entry["version_id"]) for entry in cls._journal_entries(manifest)
            }
        except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError):
            return set()

    @staticmethod
    def _validate_hash(content: bytes, expected_hash: str | None) -> str:
        digest = hashlib.sha256(content).hexdigest()
        if expected_hash is not None and expected_hash != digest:
            raise ValueError("暂存工件哈希校验失败")
        return digest
