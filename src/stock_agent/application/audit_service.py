"""将安全事件和数字溯源追加写入 DuckDB，禁止覆盖历史审计记录。"""

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import duckdb

from stock_agent.application.observability import sanitize_fields


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """可展示的审计记录；负载已脱敏且关联标识可连接到任务、工具或桌面操作。"""

    event_id: UUID
    event_name: str
    correlation_id: UUID
    occurred_at: datetime
    payload: dict[str, object]


class AuditService:
    """提供只追加审计与数字溯源记录，不暴露修改或删除历史事件的接口。"""

    def __init__(self, database_path: Path) -> None:
        self._connection = duckdb.connect(str(database_path))
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id VARCHAR PRIMARY KEY,
                event_name VARCHAR NOT NULL,
                correlation_id VARCHAR NOT NULL,
                occurred_at TIMESTAMPTZ NOT NULL,
                payload_json VARCHAR NOT NULL
            )
            """
        )

    def append(
        self, event_name: str, payload: dict[str, object], correlation_id: UUID
    ) -> AuditEvent:
        """脱敏后追加一条事件；同名事件也保留独立记录，不覆盖此前事实。"""

        if not event_name.strip():
            raise ValueError("审计事件名称不能为空")
        event = AuditEvent(
            uuid4(), event_name, correlation_id, datetime.now(UTC), sanitize_fields(payload)
        )
        self._connection.execute(
            "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?)",
            [
                str(event.event_id),
                event.event_name,
                str(event.correlation_id),
                event.occurred_at,
                json.dumps(event.payload, ensure_ascii=False, sort_keys=True),
            ],
        )
        return event

    def record_numeric_provenance(
        self,
        result_id: str,
        tool_name: str,
        data_version: str,
        artifact_ids: list[str],
        correlation_id: UUID,
    ) -> AuditEvent:
        """记录量化数字的工具、数据版本与工件引用，禁止大模型脱离工具结果编造数字。"""

        if not result_id or not tool_name or not data_version or not artifact_ids:
            raise ValueError("数字溯源必须包含结果、工具、数据版本和至少一个工件引用")
        return self.append(
            "numeric_provenance_recorded",
            {
                "result_id": result_id,
                "tool_name": tool_name,
                "data_version": data_version,
                "artifact_ids": artifact_ids,
            },
            correlation_id,
        )

    def list_events(self) -> list[AuditEvent]:
        """按产生顺序读取审计事件，仅用于查询和验证，不提供改写路径。"""

        rows = self._connection.execute(
            "SELECT event_id, event_name, correlation_id, occurred_at, payload_json "
            "FROM audit_events ORDER BY occurred_at, event_id"
        ).fetchall()
        return [
            AuditEvent(UUID(row[0]), row[1], UUID(row[2]), row[3], json.loads(row[4]))
            for row in rows
        ]
