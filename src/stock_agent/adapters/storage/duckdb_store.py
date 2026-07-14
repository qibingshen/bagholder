"""使用 DuckDB 追加登记已提交的数据版本。"""

from pathlib import Path

import duckdb


class DuckDbMetadataStore:
    """将版本元数据置于事务中，避免工件可见但版本链缺失。"""

    def __init__(self, database_path: Path) -> None:
        self._connection = duckdb.connect(str(database_path))
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS dataset_versions ("
            "dataset VARCHAR, version_id VARCHAR, content_hash VARCHAR, "
            "parent_version_id VARCHAR, PRIMARY KEY(dataset, version_id))"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS batch_versions ("
            "batch_id VARCHAR, dataset VARCHAR, version_id VARCHAR, "
            "PRIMARY KEY(batch_id, dataset, version_id))"
        )

    def register_version(
        self, dataset: str, version_id: str, content_hash: str, parent_version_id: str | None
    ) -> None:
        """原子登记一个不可覆盖的数据版本。"""
        self._connection.execute(
            "INSERT INTO dataset_versions VALUES (?, ?, ?, ?)",
            [dataset, version_id, content_hash, parent_version_id],
        )

    def register_batch_version(
        self,
        batch_id: str,
        dataset: str,
        version_id: str,
        content_hash: str,
        parent_version_id: str | None,
    ) -> None:
        """登记未完成批次成员，供损坏日志的启动恢复定位残留。"""
        self.register_version(dataset, version_id, content_hash, parent_version_id)
        self._connection.execute(
            "INSERT INTO batch_versions VALUES (?, ?, ?)",
            [batch_id, dataset, version_id],
        )

    def batch_versions(self, batch_id: str) -> list[tuple[str, str]]:
        """返回批次已登记成员，不依赖磁盘日志的可解析性。"""
        return [
            (row[0], row[1])
            for row in self._connection.execute(
                "SELECT dataset, version_id FROM batch_versions WHERE batch_id = ?",
                [batch_id],
            ).fetchall()
        ]

    def delete_batch_versions(self, batch_id: str) -> None:
        """删除已回滚批次的恢复索引。"""
        self._connection.execute("DELETE FROM batch_versions WHERE batch_id = ?", [batch_id])

    def get_version(self, dataset: str, version_id: str) -> dict[str, str | None]:
        """读取指定版本，不隐式返回最新版本。"""
        row = self._connection.execute(
            "SELECT content_hash, parent_version_id FROM dataset_versions "
            "WHERE dataset = ? AND version_id = ?",
            [dataset, version_id],
        ).fetchone()
        if row is None:
            raise KeyError(version_id)
        return {"content_hash": row[0], "parent_version_id": row[1]}

    def has_version(self, dataset: str, version_id: str) -> bool:
        """确认元数据已登记，避免仅凭完成标记暴露半提交工件。"""
        return (
            self._connection.execute(
                "SELECT 1 FROM dataset_versions WHERE dataset = ? AND version_id = ?",
                [dataset, version_id],
            ).fetchone()
            is not None
        )
