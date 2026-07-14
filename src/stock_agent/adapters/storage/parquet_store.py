"""保存带哈希、清单和完成标记的不可变工件目录。"""

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class StoredArtifact:
    """描述已完成的不可变工件。"""

    content_hash: str
    complete_marker: Path


class ParquetArtifactStore:
    """为后续 Parquet 行情和特征文件提供版本目录及完成证据。"""

    def __init__(self, root: Path) -> None:
        self._root = root

    def write_artifact(
        self, dataset: str, version_id: str, content: bytes, *, complete: bool = True
    ) -> StoredArtifact:
        """写入工件；批次提交时由统一完成标记决定可见性。"""
        directory = self._root / dataset / version_id
        directory.mkdir(parents=True, exist_ok=False)
        digest = hashlib.sha256(content).hexdigest()
        (directory / "payload.parquet").write_bytes(content)
        (directory / "manifest.json").write_text(
            json.dumps({"content_hash": digest}), encoding="utf-8"
        )
        marker = directory / "_COMPLETE"
        if complete:
            marker.touch()
        return StoredArtifact(digest, marker)
