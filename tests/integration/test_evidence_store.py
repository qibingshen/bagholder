import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest


def _store(tmp_path: Path):
    from bagholder.infrastructure.sqlite_store import SqlitePlatformStore

    return SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")


def test_保存证据时写入规范_json_和数据库索引(tmp_path: Path) -> None:
    store = _store(tmp_path)
    created_at = datetime(2026, 7, 25, 0, 30, tzinfo=UTC)
    payload = {
        "schema_version": "market-v1",
        "source": "sina HTTP (fallback)",
        "security_key": "CN:600519.SH",
        "records": [{"date": "2026-07-24", "close": "1297.41"}],
    }

    record = store.save_evidence(
        kind="MARKET",
        security_key="CN:600519.SH",
        payload=payload,
        created_at=created_at,
    )

    encoded = Path(record.path).read_bytes()
    assert json.loads(encoded) == payload
    assert record.sha256 == hashlib.sha256(encoded).hexdigest()
    assert record.path.endswith(f"market-{record.evidence_id}.json")
    assert store.load_evidence(record.evidence_id) == payload


def test_证据文件被修改后读取必须失败(tmp_path: Path) -> None:
    from bagholder.infrastructure.sqlite_store import EvidenceTamperedError

    store = _store(tmp_path)
    record = store.save_evidence(
        kind="MARKET",
        security_key="CN:600519.SH",
        payload={
            "schema_version": "market-v1",
            "source": "sina HTTP",
            "records": [{"close": "10.50"}],
        },
        created_at=datetime(2026, 7, 25, tzinfo=UTC),
    )
    Path(record.path).write_text('{"changed":true}', encoding="utf-8")

    with pytest.raises(EvidenceTamperedError, match="摘要"):
        store.load_evidence(record.evidence_id)


def test_证据路径按日期证券和类型隔离(tmp_path: Path) -> None:
    store = _store(tmp_path)

    record = store.save_evidence(
        kind="RESEARCH",
        security_key="CN:000001.SZ",
        payload={"schema_version": "research-v1", "reports": {}},
        created_at=datetime(2026, 7, 25, 8, tzinfo=UTC),
    )

    normalized = record.path.replace("\\", "/")
    assert "/2026-07-25/CN_000001_SZ/research-" in normalized
    assert record.source == "TradingAgents-Astock"
