"""验证 DuckDB 元数据事务和 Parquet 工件清单。"""

from pathlib import Path


def test_元数据与工件清单在提交后可共同查询(local_data_root: Path) -> None:
    """仅完成标记和 DuckDB 登记同时存在时，版本才可被视为可读。"""

    from stock_agent.adapters.storage.duckdb_store import DuckDbMetadataStore
    from stock_agent.adapters.storage.parquet_store import ParquetArtifactStore

    metadata = DuckDbMetadataStore(local_data_root / "metadata.duckdb")
    artifacts = ParquetArtifactStore(local_data_root / "artifacts")
    artifact = artifacts.write_artifact("daily-bars", "v1", b"payload")
    metadata.register_version("daily-bars", "v1", artifact.content_hash, None)

    assert artifact.complete_marker.is_file()
    assert metadata.get_version("daily-bars", "v1")["content_hash"] == artifact.content_hash
