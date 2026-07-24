"""SQLite 平台仓储和不可变 JSON 证据存储。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, cast
from uuid import uuid4


class EvidenceTamperedError(RuntimeError):
    """证据内容与登记摘要不一致。"""


@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    """SQLite 中登记的证据索引。"""

    evidence_id: str
    kind: Literal["MARKET", "RESEARCH"]
    security_key: str
    schema_version: str
    source: str
    path: str
    sha256: str
    created_at: datetime


class SqlitePlatformStore:
    """管理平台数据库和只新增的证据文件。"""

    _security_pattern = re.compile(r"^CN:\d{6}\.(SH|SZ|BJ)$")

    def __init__(self, database_path: str | Path, evidence_root: str | Path) -> None:
        self.database_path = Path(database_path).resolve()
        self.evidence_root = Path(evidence_root).resolve()
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.evidence_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.database_path, timeout=5)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=5000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS evidence_snapshots (
                    evidence_id TEXT PRIMARY KEY,
                    kind TEXT NOT NULL CHECK (kind IN ('MARKET', 'RESEARCH')),
                    security_key TEXT NOT NULL,
                    schema_version TEXT NOT NULL,
                    source TEXT NOT NULL,
                    path TEXT NOT NULL UNIQUE,
                    sha256 TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_events (
                    event_id TEXT PRIMARY KEY,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                """
            )

    def save_evidence(
        self,
        *,
        kind: Literal["MARKET", "RESEARCH"],
        security_key: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> EvidenceRecord:
        """规范化并排他写入证据，然后登记摘要。"""

        if kind not in {"MARKET", "RESEARCH"}:
            raise ValueError("证据类型必须是 MARKET 或 RESEARCH")
        if not self._security_pattern.fullmatch(security_key):
            raise ValueError("证券代码格式无效")
        if created_at.tzinfo is None:
            raise ValueError("证据时间必须包含时区")

        schema_version = str(payload.get("schema_version", "")).strip()
        if not schema_version:
            raise ValueError("证据必须包含 schema_version")
        default_source = "TradingAgents-Astock" if kind == "RESEARCH" else ""
        source = str(payload.get("source", default_source)).strip()
        if not source:
            raise ValueError("市场证据必须包含 source")

        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        evidence_id = str(uuid4())
        created_utc = created_at.astimezone(UTC)
        security_dir = security_key.replace(":", "_").replace(".", "_")
        directory = self.evidence_root / created_utc.date().isoformat() / security_dir
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{kind.lower()}-{evidence_id}.json"

        with path.open("xb") as stream:
            stream.write(encoded)
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO evidence_snapshots (
                        evidence_id, kind, security_key, schema_version,
                        source, path, sha256, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        evidence_id,
                        kind,
                        security_key,
                        schema_version,
                        source,
                        str(path),
                        digest,
                        created_utc.isoformat(),
                    ),
                )
        except Exception:
            path.unlink(missing_ok=True)
            raise

        return EvidenceRecord(
            evidence_id=evidence_id,
            kind=kind,
            security_key=security_key,
            schema_version=schema_version,
            source=source,
            path=str(path),
            sha256=digest,
            created_at=created_utc,
        )

    def get_evidence_record(self, evidence_id: str) -> EvidenceRecord:
        """按 ID 读取证据索引。"""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM evidence_snapshots WHERE evidence_id = ?",
                (evidence_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"证据不存在：{evidence_id}")
        return EvidenceRecord(
            evidence_id=str(row["evidence_id"]),
            kind=cast(Literal["MARKET", "RESEARCH"], str(row["kind"])),
            security_key=str(row["security_key"]),
            schema_version=str(row["schema_version"]),
            source=str(row["source"]),
            path=str(row["path"]),
            sha256=str(row["sha256"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def load_evidence(self, evidence_id: str) -> dict[str, object]:
        """复核路径和摘要后返回证据对象。"""

        record = self.get_evidence_record(evidence_id)
        path = Path(record.path).resolve()
        if not path.is_relative_to(self.evidence_root):
            raise EvidenceTamperedError("证据路径超出受信目录")
        try:
            encoded = path.read_bytes()
        except FileNotFoundError as error:
            raise EvidenceTamperedError("证据文件不存在") from error
        actual = hashlib.sha256(encoded).hexdigest()
        if actual != record.sha256:
            raise EvidenceTamperedError("证据文件摘要不匹配")
        try:
            payload = json.loads(encoded)
        except json.JSONDecodeError as error:
            raise EvidenceTamperedError("证据文件不是有效 JSON") from error
        if not isinstance(payload, dict):
            raise EvidenceTamperedError("证据根对象必须是 JSON 对象")
        return cast(dict[str, object], payload)

