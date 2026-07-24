"""SQLite 平台仓储和不可变 JSON 证据存储。"""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast
from uuid import uuid4

if TYPE_CHECKING:
    from bagholder.contracts.live_trading import ExecutionRequest
    from bagholder.domain.broker import BrokerOrderReceipt


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


@dataclass(frozen=True, slots=True)
class PaperAccountRecord:
    """模拟账户资金快照。"""

    account_id: str
    cash: Decimal
    status: str
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class PaperPositionRecord:
    """模拟账户单证券持仓。"""

    account_id: str
    security_key: str
    total_quantity: int
    available_to_sell: int
    average_cost: Decimal


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

                CREATE TABLE IF NOT EXISTS research_decisions (
                    decision_id TEXT PRIMARY KEY,
                    security_key TEXT NOT NULL,
                    decision_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_accounts (
                    account_id TEXT PRIMARY KEY,
                    cash TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS paper_positions (
                    account_id TEXT NOT NULL,
                    security_key TEXT NOT NULL,
                    total_quantity INTEGER NOT NULL,
                    available_to_sell INTEGER NOT NULL,
                    average_cost TEXT NOT NULL,
                    PRIMARY KEY (account_id, security_key),
                    FOREIGN KEY (account_id) REFERENCES paper_accounts(account_id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    order_id TEXT PRIMARY KEY,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    account_id TEXT NOT NULL,
                    security_key TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK (mode IN ('PAPER', 'LIVE')),
                    side TEXT NOT NULL CHECK (side IN ('BUY', 'SELL')),
                    quantity INTEGER NOT NULL,
                    limit_price TEXT NOT NULL,
                    status TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS fills (
                    fill_id TEXT PRIMARY KEY,
                    order_id TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    price TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (order_id) REFERENCES orders(order_id)
                );

                CREATE TABLE IF NOT EXISTS order_proposals (
                    proposal_id TEXT PRIMARY KEY,
                    proposal_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS risk_verdicts (
                    verdict_id TEXT PRIMARY KEY,
                    verdict_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS approvals (
                    approval_id TEXT PRIMARY KEY,
                    approval_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS pipeline_runs (
                    run_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    security_key TEXT NOT NULL,
                    account_id TEXT NOT NULL,
                    mode TEXT NOT NULL CHECK (mode IN ('PAPER', 'LIVE')),
                    market_evidence_id TEXT,
                    research_decision_id TEXT,
                    proposal_id TEXT,
                    verdict_id TEXT,
                    approval_id TEXT,
                    order_id TEXT,
                    error_code TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS execution_receipts (
                    idempotency_key TEXT PRIMARY KEY,
                    account_id TEXT NOT NULL,
                    broker_order_id TEXT NOT NULL,
                    accepted INTEGER NOT NULL,
                    status TEXT NOT NULL
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

    def save_research_decision(self, decision: object) -> None:
        """保存经过 Pydantic 校验的结构化研究决策。"""

        from bagholder.contracts.live_trading import ResearchDecision

        validated = ResearchDecision.model_validate(decision)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO research_decisions (
                    decision_id, security_key, decision_json, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    str(validated.decision_id),
                    validated.security_key,
                    validated.model_dump_json(),
                    validated.as_of.astimezone(UTC).isoformat(),
                ),
            )

    def get_research_decision(self, decision_id: str) -> object:
        """读取结构化研究决策；返回类型延迟导入以避免基础设施循环。"""

        from bagholder.contracts.live_trading import ResearchDecision

        with self._connect() as connection:
            row = connection.execute(
                "SELECT decision_json FROM research_decisions WHERE decision_id = ?",
                (decision_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"研究决策不存在：{decision_id}")
        return ResearchDecision.model_validate_json(str(row["decision_json"]))

    def create_paper_account(
        self,
        account_id: str,
        cash: Decimal,
        now: datetime,
    ) -> None:
        """登记模拟账户；重复 ID 明确失败。"""

        if now.tzinfo is None:
            raise ValueError("模拟账户时间必须包含时区")
        timestamp = now.astimezone(UTC).isoformat()
        try:
            with self._connect() as connection:
                connection.execute(
                    """
                    INSERT INTO paper_accounts (
                        account_id, cash, status, created_at, updated_at
                    ) VALUES (?, ?, 'ACTIVE', ?, ?)
                    """,
                    (account_id, self._decimal_text(cash), timestamp, timestamp),
                )
        except sqlite3.IntegrityError as error:
            raise ValueError(f"模拟账户已存在：{account_id}") from error

    def get_paper_account(self, account_id: str) -> PaperAccountRecord:
        """读取模拟账户资金。"""

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM paper_accounts WHERE account_id = ?",
                (account_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"模拟账户不存在：{account_id}")
        return PaperAccountRecord(
            account_id=str(row["account_id"]),
            cash=Decimal(str(row["cash"])),
            status=str(row["status"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
            updated_at=datetime.fromisoformat(str(row["updated_at"])),
        )

    def get_paper_position(
        self,
        account_id: str,
        security_key: str,
    ) -> PaperPositionRecord:
        """读取模拟持仓。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM paper_positions
                WHERE account_id = ? AND security_key = ?
                """,
                (account_id, security_key),
            ).fetchone()
        if row is None:
            raise LookupError(f"模拟持仓不存在：{account_id}/{security_key}")
        return self._paper_position_from_row(row)

    def execute_paper_order(
        self,
        request: ExecutionRequest,
        now: datetime,
    ) -> BrokerOrderReceipt:
        """在单一数据库事务中撮合并更新资金和持仓。"""

        from bagholder.contracts.live_trading import ExecutionRequest, OrderSide
        from bagholder.domain.broker import BrokerOrderReceipt

        validated = ExecutionRequest.model_validate(request)
        proposal = validated.proposal
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """
                SELECT account_id, broker_order_id, status
                FROM orders WHERE idempotency_key = ?
                """,
                (validated.idempotency_key,),
            ).fetchone()
            if existing is not None:
                connection.rollback()
                return BrokerOrderReceipt(
                    account_id=str(existing["account_id"]),
                    broker_order_id=str(existing["broker_order_id"]),
                    accepted=True,
                    status=str(existing["status"]),
                )

            account = connection.execute(
                "SELECT * FROM paper_accounts WHERE account_id = ?",
                (proposal.account_id,),
            ).fetchone()
            if account is None:
                raise LookupError(f"模拟账户不存在：{proposal.account_id}")
            if str(account["status"]) != "ACTIVE":
                raise PermissionError("PAPER_ACCOUNT_NOT_ACTIVE")

            position = connection.execute(
                """
                SELECT * FROM paper_positions
                WHERE account_id = ? AND security_key = ?
                """,
                (proposal.account_id, proposal.security_key),
            ).fetchone()
            old_total = int(position["total_quantity"]) if position is not None else 0
            old_available = (
                int(position["available_to_sell"]) if position is not None else 0
            )
            old_cost = (
                Decimal(str(position["average_cost"]))
                if position is not None
                else Decimal("0")
            )
            cash = Decimal(str(account["cash"]))
            amount = proposal.limit_price * proposal.quantity

            if proposal.side is OrderSide.BUY:
                if amount > cash:
                    raise PermissionError("INSUFFICIENT_CASH")
                new_cash = cash - amount
                new_total = old_total + proposal.quantity
                new_available = old_available
                new_cost = (
                    (old_cost * old_total + amount) / new_total
                    if new_total
                    else Decimal("0")
                )
            else:
                if proposal.quantity > old_available:
                    raise PermissionError("INSUFFICIENT_POSITION")
                new_cash = cash + amount
                new_total = old_total - proposal.quantity
                new_available = old_available - proposal.quantity
                new_cost = old_cost if new_total else Decimal("0")

            order_id = str(uuid4())
            broker_order_id = f"PAPER-{uuid4().hex}"
            timestamp = now.astimezone(UTC).isoformat()
            connection.execute(
                """
                INSERT INTO orders (
                    order_id, idempotency_key, account_id, security_key,
                    mode, side, quantity, limit_price, status,
                    broker_order_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'FILLED', ?, ?)
                """,
                (
                    order_id,
                    validated.idempotency_key,
                    proposal.account_id,
                    proposal.security_key,
                    proposal.mode.value,
                    proposal.side.value,
                    proposal.quantity,
                    self._decimal_text(proposal.limit_price),
                    broker_order_id,
                    timestamp,
                ),
            )
            connection.execute(
                """
                INSERT INTO fills (
                    fill_id, order_id, quantity, price, created_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(uuid4()),
                    order_id,
                    proposal.quantity,
                    self._decimal_text(proposal.limit_price),
                    timestamp,
                ),
            )
            connection.execute(
                """
                UPDATE paper_accounts
                SET cash = ?, updated_at = ?
                WHERE account_id = ?
                """,
                (self._decimal_text(new_cash), timestamp, proposal.account_id),
            )
            connection.execute(
                """
                INSERT INTO paper_positions (
                    account_id, security_key, total_quantity,
                    available_to_sell, average_cost
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_id, security_key) DO UPDATE SET
                    total_quantity = excluded.total_quantity,
                    available_to_sell = excluded.available_to_sell,
                    average_cost = excluded.average_cost
                """,
                (
                    proposal.account_id,
                    proposal.security_key,
                    new_total,
                    new_available,
                    self._decimal_text(new_cost),
                ),
            )
            connection.commit()
            return BrokerOrderReceipt(
                account_id=proposal.account_id,
                broker_order_id=broker_order_id,
                accepted=True,
                status="FILLED",
            )
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def count_orders(self) -> int:
        """返回订单总数，供状态查询和验收使用。"""

        with self._connect() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM orders").fetchone()
        assert row is not None
        return int(row["count"])

    def count_fills(self, idempotency_key: str | None = None) -> int:
        """返回全部或指定幂等订单的成交数。"""

        with self._connect() as connection:
            if idempotency_key is None:
                row = connection.execute("SELECT COUNT(*) AS count FROM fills").fetchone()
            else:
                row = connection.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM fills
                    JOIN orders ON orders.order_id = fills.order_id
                    WHERE orders.idempotency_key = ?
                    """,
                    (idempotency_key,),
                ).fetchone()
        assert row is not None
        return int(row["count"])

    def list_paper_positions(self, account_id: str) -> tuple[PaperPositionRecord, ...]:
        """列出模拟账户全部持仓。"""

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT * FROM paper_positions
                WHERE account_id = ?
                ORDER BY security_key
                """,
                (account_id,),
            ).fetchall()
        return tuple(self._paper_position_from_row(row) for row in rows)

    def get_order(self, order_id: str) -> dict[str, object]:
        """按内部或券商订单号查询订单。"""

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM orders
                WHERE order_id = ? OR broker_order_id = ?
                """,
                (order_id, order_id),
            ).fetchone()
            if row is not None:
                return {key: row[key] for key in row.keys()}
            receipt = connection.execute(
                """
                SELECT * FROM execution_receipts
                WHERE broker_order_id = ? OR idempotency_key = ?
                """,
                (order_id, order_id),
            ).fetchone()
        if receipt is None:
            raise LookupError(f"订单不存在：{order_id}")
        return {
            "order_id": str(receipt["idempotency_key"]),
            "broker_order_id": str(receipt["broker_order_id"]),
            "account_id": str(receipt["account_id"]),
            "mode": "LIVE",
            "accepted": bool(receipt["accepted"]),
            "status": str(receipt["status"]),
        }

    def find(self, idempotency_key: str) -> BrokerOrderReceipt | None:
        """实现 LiveExecutionService 的持久化幂等查询。"""

        from bagholder.domain.broker import BrokerOrderReceipt

        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT * FROM execution_receipts
                WHERE idempotency_key = ?
                """,
                (idempotency_key,),
            ).fetchone()
        if row is None:
            return None
        return BrokerOrderReceipt(
            account_id=str(row["account_id"]),
            broker_order_id=str(row["broker_order_id"]),
            accepted=bool(row["accepted"]),
            status=str(row["status"]),
        )

    def save(
        self,
        idempotency_key: str,
        receipt: BrokerOrderReceipt,
    ) -> None:
        """保存真实执行回执；相同幂等键不可覆盖。"""

        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO execution_receipts (
                    idempotency_key, account_id, broker_order_id,
                    accepted, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    idempotency_key,
                    receipt.account_id,
                    receipt.broker_order_id,
                    int(receipt.accepted),
                    receipt.status,
                ),
            )

    def create_pipeline_run(
        self,
        *,
        security_key: str,
        account_id: str,
        mode: str,
        now: datetime,
    ) -> object:
        """创建 CREATED 管道并追加审计事件。"""

        from bagholder.contracts.live_trading import ExecutionMode
        from bagholder.domain.pipeline import PipelineRun, PipelineState

        execution_mode = ExecutionMode(mode)
        run_id = str(uuid4())
        timestamp = now.astimezone(UTC).isoformat()
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO pipeline_runs (
                    run_id, state, security_key, account_id, mode,
                    created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    run_id,
                    PipelineState.CREATED.value,
                    security_key,
                    account_id,
                    execution_mode.value,
                    timestamp,
                    timestamp,
                ),
            )
            self._insert_audit(
                connection,
                aggregate_type="PIPELINE",
                aggregate_id=run_id,
                event_type=PipelineState.CREATED.value,
                payload={},
                created_at=now,
            )
        return PipelineRun(
            run_id=run_id,
            state=PipelineState.CREATED,
            security_key=security_key,
            account_id=account_id,
            mode=execution_mode,
        )

    def transition_pipeline(
        self,
        run_id: str,
        target: str,
        now: datetime,
        **updates: str | None,
    ) -> object:
        """原子校验并推进管道状态。"""

        from bagholder.domain.pipeline import PipelineState, ensure_transition

        target_state = PipelineState(target)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
            if row is None:
                raise LookupError(f"管道不存在：{run_id}")
            ensure_transition(PipelineState(str(row["state"])), target_state)
            allowed_fields = {
                "market_evidence_id",
                "research_decision_id",
                "proposal_id",
                "verdict_id",
                "approval_id",
                "order_id",
                "error_code",
            }
            invalid = set(updates) - allowed_fields
            if invalid:
                raise ValueError(f"非法管道更新字段：{sorted(invalid)}")
            assignments = ["state = ?", "updated_at = ?"]
            values: list[object] = [target_state.value, now.astimezone(UTC).isoformat()]
            for key, value in updates.items():
                assignments.append(f"{key} = ?")
                values.append(value)
            values.append(run_id)
            connection.execute(
                f"UPDATE pipeline_runs SET {', '.join(assignments)} WHERE run_id = ?",
                values,
            )
            self._insert_audit(
                connection,
                aggregate_type="PIPELINE",
                aggregate_id=run_id,
                event_type=target_state.value,
                payload={key: value for key, value in updates.items() if value is not None},
                created_at=now,
            )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()
        return self.get_pipeline_run(run_id)

    def get_pipeline_run(self, run_id: str) -> object:
        """读取管道当前快照。"""

        from bagholder.contracts.live_trading import ExecutionMode
        from bagholder.domain.pipeline import PipelineRun, PipelineState

        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM pipeline_runs WHERE run_id = ?",
                (run_id,),
            ).fetchone()
        if row is None:
            raise LookupError(f"管道不存在：{run_id}")
        return PipelineRun(
            run_id=str(row["run_id"]),
            state=PipelineState(str(row["state"])),
            security_key=str(row["security_key"]),
            account_id=str(row["account_id"]),
            mode=ExecutionMode(str(row["mode"])),
            market_evidence_id=self._optional_text(row["market_evidence_id"]),
            research_decision_id=self._optional_text(row["research_decision_id"]),
            proposal_id=self._optional_text(row["proposal_id"]),
            verdict_id=self._optional_text(row["verdict_id"]),
            approval_id=self._optional_text(row["approval_id"]),
            order_id=self._optional_text(row["order_id"]),
            error_code=self._optional_text(row["error_code"]),
        )

    def save_order_proposal(self, proposal: object) -> None:
        """保存不可变订单提案。"""

        from bagholder.contracts.live_trading import OrderProposal

        validated = OrderProposal.model_validate(proposal)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO order_proposals (
                    proposal_id, proposal_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    str(validated.proposal_id),
                    validated.model_dump_json(),
                    validated.created_at.astimezone(UTC).isoformat(),
                ),
            )

    def get_order_proposal(self, proposal_id: str) -> object:
        """读取不可变订单提案。"""

        from bagholder.contracts.live_trading import OrderProposal

        payload = self._get_json("order_proposals", "proposal_id", proposal_id)
        return OrderProposal.model_validate_json(payload)

    def save_risk_verdict(self, verdict: object) -> None:
        """保存不可变风控结果。"""

        from bagholder.contracts.live_trading import RiskVerdict

        validated = RiskVerdict.model_validate(verdict)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO risk_verdicts (
                    verdict_id, verdict_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    str(validated.verdict_id),
                    validated.model_dump_json(),
                    validated.checked_at.astimezone(UTC).isoformat(),
                ),
            )

    def get_risk_verdict(self, verdict_id: str) -> object:
        """读取不可变风控结果。"""

        from bagholder.contracts.live_trading import RiskVerdict

        payload = self._get_json("risk_verdicts", "verdict_id", verdict_id)
        return RiskVerdict.model_validate_json(payload)

    def save_approval(self, approval: object) -> None:
        """保存人工或策略审批。"""

        from bagholder.contracts.live_trading import OrderApproval

        validated = OrderApproval.model_validate(approval)
        with self._connect() as connection:
            connection.execute(
                """
                INSERT INTO approvals (
                    approval_id, approval_json, created_at
                ) VALUES (?, ?, ?)
                """,
                (
                    str(validated.approval_id),
                    validated.model_dump_json(),
                    validated.approved_at.astimezone(UTC).isoformat(),
                ),
            )

    def _get_json(self, table: str, key: str, value: str) -> str:
        allowed = {
            ("order_proposals", "proposal_id"): "proposal_json",
            ("risk_verdicts", "verdict_id"): "verdict_json",
            ("approvals", "approval_id"): "approval_json",
        }
        payload_column = allowed.get((table, key))
        if payload_column is None:
            raise ValueError("不允许的 JSON 表查询")
        with self._connect() as connection:
            row = connection.execute(
                f"SELECT {payload_column} FROM {table} WHERE {key} = ?",
                (value,),
            ).fetchone()
        if row is None:
            raise LookupError(f"记录不存在：{value}")
        return str(row[payload_column])

    @staticmethod
    def _insert_audit(
        connection: sqlite3.Connection,
        *,
        aggregate_type: str,
        aggregate_id: str,
        event_type: str,
        payload: dict[str, object],
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO audit_events (
                event_id, aggregate_type, aggregate_id,
                event_type, payload_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                aggregate_type,
                aggregate_id,
                event_type,
                json.dumps(
                    payload,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                created_at.astimezone(UTC).isoformat(),
            ),
        )

    @staticmethod
    def _optional_text(value: object) -> str | None:
        return None if value is None else str(value)

    @staticmethod
    def _paper_position_from_row(row: sqlite3.Row) -> PaperPositionRecord:
        return PaperPositionRecord(
            account_id=str(row["account_id"]),
            security_key=str(row["security_key"]),
            total_quantity=int(row["total_quantity"]),
            available_to_sell=int(row["available_to_sell"]),
            average_cost=Decimal(str(row["average_cost"])),
        )

    @staticmethod
    def _decimal_text(value: Decimal) -> str:
        return format(value, "f")
