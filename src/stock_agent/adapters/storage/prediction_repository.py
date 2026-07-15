"""使用 DuckDB 追加保存预测快照和到期结果索引。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import duckdb

from stock_agent.domain.prediction import (
    ActualOutcome,
    PredictionSnapshot,
    PredictionSnapshotStore,
)


class PredictionRepositoryError(ValueError):
    """表示预测仓储追加或查询违反不可覆盖规则。"""


@dataclass(frozen=True, slots=True)
class PredictionSnapshotRecord:
    """用于查询预测快照版本关联的轻量记录。"""

    snapshot_id: str
    security_key: str
    predicted_at: datetime
    horizon_trading_days: int
    data_version: str
    feature_version: str
    model_version: str
    label_rule_version: str
    trading_calendar_version: str


class PredictionRepository:
    """预测快照仓储边界，写入前复用领域追加规则。"""

    def __init__(self, database_path: Path) -> None:
        self._connection = duckdb.connect(str(database_path))
        self._domain_store = PredictionSnapshotStore()
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS prediction_snapshots ("
            "snapshot_id VARCHAR PRIMARY KEY, security_key VARCHAR, predicted_at TIMESTAMP, "
            "horizon_trading_days INTEGER, data_version VARCHAR, feature_version VARCHAR, "
            "model_version VARCHAR, label_rule_version VARCHAR, trading_calendar_version VARCHAR, "
            "payload_json VARCHAR, created_at TIMESTAMP)"
        )
        self._connection.execute(
            "CREATE TABLE IF NOT EXISTS prediction_outcomes ("
            "snapshot_id VARCHAR, outcome_index INTEGER, status VARCHAR, label VARCHAR, "
            "validated_at TIMESTAMP, payload_json VARCHAR, "
            "PRIMARY KEY(snapshot_id, outcome_index))"
        )

    def append_snapshot(self, snapshot: PredictionSnapshot) -> PredictionSnapshotRecord:
        """追加保存预测快照索引和完整 JSON 负载，拒绝同标识覆盖。"""

        if self._exists_snapshot(snapshot.snapshot_id):
            raise PredictionRepositoryError("预测快照只能追加，不能覆盖或重复写入")
        self._domain_store._snapshots[snapshot.snapshot_id] = snapshot
        record = _snapshot_record(snapshot)
        payload_json = json.dumps(_snapshot_payload(snapshot), ensure_ascii=False, sort_keys=True)
        self._connection.execute(
            "INSERT INTO prediction_snapshots VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                record.snapshot_id,
                record.security_key,
                record.predicted_at,
                record.horizon_trading_days,
                record.data_version,
                record.feature_version,
                record.model_version,
                record.label_rule_version,
                record.trading_calendar_version,
                payload_json,
                datetime.now(UTC),
            ],
        )
        return record

    def get_snapshot_record(self, snapshot_id: str) -> PredictionSnapshotRecord:
        """读取已保存快照的版本关联，缺失时显式报错。"""

        row = self._connection.execute(
            "SELECT snapshot_id, security_key, predicted_at, horizon_trading_days, "
            "data_version, feature_version, model_version, label_rule_version, "
            "trading_calendar_version FROM prediction_snapshots WHERE snapshot_id = ?",
            [snapshot_id],
        ).fetchone()
        if row is None:
            raise KeyError(snapshot_id)
        return PredictionSnapshotRecord(
            snapshot_id=row[0],
            security_key=row[1],
            predicted_at=_with_utc(row[2]),
            horizon_trading_days=row[3],
            data_version=row[4],
            feature_version=row[5],
            model_version=row[6],
            label_rule_version=row[7],
            trading_calendar_version=row[8],
        )

    def append_actual_outcome(self, outcome: ActualOutcome) -> ActualOutcome:
        """回填到期结果；只有领域快照复验通过后才写入仓储。"""

        if not self._exists_snapshot(outcome.prediction_snapshot_id):
            raise PredictionRepositoryError("到期结果必须关联已保存预测快照")
        stored = self._domain_store.append_actual_outcome(outcome)
        payload_json = json.dumps(stored.__dict__, default=_json_default, ensure_ascii=False)
        outcome_index = len(self.actual_outcomes_for(outcome.prediction_snapshot_id))
        self._connection.execute(
            "INSERT INTO prediction_outcomes VALUES (?, ?, ?, ?, ?, ?)",
            [
                stored.prediction_snapshot_id,
                outcome_index,
                stored.status.value,
                stored.label.value if stored.label is not None else None,
                stored.validated_at,
                payload_json,
            ],
        )
        return stored

    def actual_outcomes_for(self, snapshot_id: str) -> tuple[ActualOutcome, ...]:
        """返回当前进程已通过领域复验的到期结果。"""

        return self._domain_store.actual_outcomes_for(snapshot_id)

    def _exists_snapshot(self, snapshot_id: str) -> bool:
        return (
            self._connection.execute(
                "SELECT 1 FROM prediction_snapshots WHERE snapshot_id = ?",
                [snapshot_id],
            ).fetchone()
            is not None
        )


def _snapshot_record(snapshot: PredictionSnapshot) -> PredictionSnapshotRecord:
    output = snapshot.prediction_output
    input_fact = snapshot.prediction_input
    return PredictionSnapshotRecord(
        snapshot_id=snapshot.snapshot_id,
        security_key=_security_key(input_fact.security_id),
        predicted_at=input_fact.predicted_at,
        horizon_trading_days=output.horizon_trading_days,
        data_version=input_fact.data_version,
        feature_version=input_fact.feature_version,
        model_version=input_fact.model_version,
        label_rule_version=input_fact.prediction_label_rule_version or "",
        trading_calendar_version=input_fact.trading_calendar_version or "",
    )


def _snapshot_payload(snapshot: PredictionSnapshot) -> dict[str, Any]:
    return {
        "snapshot_id": snapshot.snapshot_id,
        "prediction_input": snapshot.prediction_input.model_dump(mode="json"),
        "prediction_output": snapshot.prediction_output.model_dump(mode="json"),
        "generated_at": snapshot.generated_at.isoformat(),
        "trading_calendar_fact_value": snapshot.trading_calendar_fact_value,
        "label_rule_fact_value": snapshot.label_rule_fact_value,
    }


def _security_key(security_id: object) -> str:
    market = _security_market_value(security_id)
    exchange = getattr(security_id, "exchange", "")
    display_code = getattr(security_id, "display_code", "")
    return f"{market}:{exchange}:{display_code}"


def _security_market_value(security_id: object) -> str:
    market = getattr(security_id, "market", "")
    return getattr(market, "value", str(market))


def _json_default(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)


def _with_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
