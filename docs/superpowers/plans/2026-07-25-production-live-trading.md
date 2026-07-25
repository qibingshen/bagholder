# Production Live Trading Closure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the broker-independent production safety loop for LIVE A-share orders, including pre-submit broker facts, deterministic state handling, order lifecycle, cancellation, reconciliation, restart recovery, installable runtime assets, and a common contract suite ready for CITIC-first sandbox integration.

**Architecture:** Keep research, proposal generation, approval, broker routing, live order lifecycle, and reconciliation as separate boundaries. A LIVE approval validates the confirmation channel and explicit user limit price, refreshes quote/account facts from the proposal account, persists a second risk verdict, requires exact final-terms confirmation, and submits through exactly one account Gateway. All broker outcomes become persisted state events; uncertain outcomes freeze new openings until reconciliation resolves them.

**Tech Stack:** Python 3.12, Pydantic 2, SQLite WAL, vn.py 4.4 isolated subprocess, pytest, pytest-cov, Hypothesis, Ruff, mypy strict, Windows PowerShell.

## Global Constraints

- Follow strict RED-GREEN-REFACTOR: add one failing test, observe the expected failure, implement the smallest behavior, then rerun focused and affected suites.
- Deterministic tests must not access public market data, a real LLM, a broker SDK, or a production account.
- LIVE failure must never fall back to PAPER or another account.
- A timeout or ambiguous submit result must never trigger an automatic second submit.
- Public daily bars remain research evidence only; a LIVE limit price and tradability facts must come from the selected broker account.
- The CLI validates `--confirm-live` and an interactive terminal before broker fact refresh, then requires exact confirmation of broker, account, security, side, quantity, and final limit price after refresh.
- LIVE approval requires an explicit `--limit-price`; the platform never derives a production limit price from public daily bars.
- Refreshed facts, final limit-price confirmation, and the final risk verdict expire together.
- Global and account LIVE switches remain false by default.
- No credential, session token, raw SDK exception, plugin digest, or plugin path may be persisted or returned by status/query commands.
- CITIC and Guotai Haitong use the same public contracts and contract suite; vendor SDK code remains in private plugins.
- Existing SQLite records must survive every migration; migrations must be ordered and idempotent.
- Every task ends in a focused commit and leaves `pytest`, Ruff, mypy, and `git diff --check` green for its affected scope.
- The absence of official SDKs means Tasks 1-14 can deliver “platform safety closure complete”; vendor sandbox enablement remains behind the external gates at the end of this plan.

---

## File and Responsibility Map

### New domain files

- `src/bagholder/domain/live_order.py`: LIVE order status, acknowledgements, updates, fills, transition rules.
- `src/bagholder/domain/broker_facts.py`: security quote and account fact snapshots returned by a Gateway.
- `src/bagholder/domain/account_runtime.py`: persisted account lifecycle and freeze reasons.

### New application files

- `src/bagholder/application/pre_submit_risk_service.py`: refreshed broker facts and final risk verdict.
- `src/bagholder/application/live_order_service.py`: idempotent submit and strict acknowledgement validation.
- `src/bagholder/application/order_lifecycle_service.py`: order updates, fills, and legal transitions.
- `src/bagholder/application/live_order_monitor.py`: continuously refresh non-terminal orders without submitting.
- `src/bagholder/application/cancel_order_service.py`: safe cancellation.
- `src/bagholder/application/broker_query_service.py`: read-only funds, positions, orders, and trades.
- `src/bagholder/application/account_reconciliation_service.py`: account comparison, freeze, and recovery.
- `src/bagholder/application/live_recovery_service.py`: restart recovery for non-terminal orders.

### New infrastructure files

- `src/bagholder/infrastructure/sqlite_migrations.py`: ordered schema migrations.
- `src/bagholder/infrastructure/sqlite_live_order_store.py`: LIVE order, event, fill, cancel, risk, and account-state repositories.
- `src/bagholder/runtime_assets/`: packaged broker profiles and isolated runner/server scripts.

### Existing integration files changed

- `src/bagholder/domain/broker.py`: extend `BrokerGateway` with security quote and single-order query.
- `src/bagholder/adapters/broker/vnpy_gateway.py`: map new vn.py commands to domain objects.
- `src/bagholder/adapters/broker/broker_runtime_registry.py`: require new capabilities and persisted account readiness.
- `integrations/vnpy/server.py`: dispatch quote and single-order queries.
- `integrations/vnpy/bagholder_vnpy_fake.py`: controlled non-production implementation for contract tests.
- `src/bagholder/application/pipeline_service.py`: terminal outcome mapping and final risk binding.
- `src/bagholder/bootstrap.py`: broker query, cancel, and reconciliation CLI.
- `src/bagholder/runtime.py`: assemble the new services using one account binding.

---

### Task 1: Correct Pipeline Terminal Outcomes

**Files:**
- Modify: `src/bagholder/domain/pipeline.py`
- Modify: `src/bagholder/application/approval_service.py`
- Modify: `src/bagholder/application/pipeline_service.py`
- Modify: `tests/integration/test_pipeline.py`

**Interfaces:**
- Consumes: existing `BrokerOrderReceipt.accepted`, `BrokerOrderReceipt.status`
- Produces: stable pipeline errors `BROKER_ORDER_REJECTED`, `APPROVAL_EXPIRED`, `LIVE_EXECUTION_FAILED`
- Produces: rejected and exceptional execution paths that never remain `WAITING_APPROVAL`

- [ ] **Step 1: Add failing regression tests for rejected, expired, and exceptional approvals**

Add executors to `tests/integration/test_pipeline.py`:

```python
class ReceiptLiveExecutor:
    def __init__(self, *, accepted: bool, status: str) -> None:
        self.accepted = accepted
        self.status = status

    def submit(self, request, now):
        from bagholder.domain.broker import BrokerOrderReceipt

        return BrokerOrderReceipt(
            account_id=request.proposal.account_id,
            broker_order_id="BROKER-REJECT-1",
            accepted=self.accepted,
            status=self.status,
        )


class FailingLiveExecutor:
    def submit(self, request, now):
        raise ConnectionError("controlled executor failure")
```

Add tests asserting:

```python
def test_live_明确拒单不能标记为已提交(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pipeline, mode = _platform(
        tmp_path,
        monkeypatch,
        mode="LIVE",
        live_executor=ReceiptLiveExecutor(
            accepted=False,
            status="REJECTED",
        ),
    )
    waiting = _run_waiting_pipeline(pipeline, mode, "citic-main")
    result = _approve_ready_live(pipeline, waiting.run_id, mode)
    assert result.state is PipelineState.EXECUTION_FAILED
    assert result.error_code == "BROKER_ORDER_REJECTED"


def test_审批过期必须保存终态(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pipeline, mode = _platform(tmp_path, monkeypatch)
    waiting = _run_waiting_pipeline(pipeline, mode, "paper-main")
    result = pipeline.approve(
        run_id=waiting.run_id,
        mode=mode,
        interactive_confirmation=True,
        now=NOW + timedelta(minutes=3),
    )
    assert result.state is PipelineState.APPROVAL_EXPIRED
    assert result.error_code == "APPROVAL_EXPIRED"


def test_live_执行异常必须保存终态(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, pipeline, mode = _platform(
        tmp_path,
        monkeypatch,
        mode="LIVE",
        live_executor=FailingLiveExecutor(),
    )
    waiting = _run_waiting_pipeline(pipeline, mode, "citic-main")
    result = _approve_ready_live(pipeline, waiting.run_id, mode)
    assert result.state is PipelineState.EXECUTION_FAILED
    assert result.error_code == "LIVE_EXECUTION_FAILED"
```

Extend the existing `_platform` helper with
`live_executor: object | None = None`; pass that executor to
`ExecutionRouter`, defaulting to the current `RejectingLiveExecutor`. Add
`_run_waiting_pipeline(pipeline, mode, account_id)` using the existing
`FakeMarketClient`, `FakeResearchClient`, `_risk_context`, and `NOW`. Add
`_approve_ready_live` that calls `pipeline.approve` with:

```python
LiveGateContext(
    system_live_enabled=True,
    account_live_enabled=True,
    broker_api_state=BrokerApiState.READY,
    supports_live_orders=True,
    reconciled=True,
    interactive_confirmation=True,
)
```

- [ ] **Step 2: Run the three tests and verify RED**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_pipeline.py `
  -k "明确拒单 or 审批过期 or 执行异常" -q
```

Expected: the rejected receipt is `LIVE_SUBMITTED`; expiry and executor errors escape while the stored run remains `WAITING_APPROVAL`.

- [ ] **Step 3: Add stable error codes and terminal mapping**

Add to `PipelineErrorCode`:

```python
BROKER_ORDER_REJECTED = "BROKER_ORDER_REJECTED"
APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
LIVE_EXECUTION_FAILED = "LIVE_EXECUTION_FAILED"
```

Define a typed error in `approval_service.py`:

```python
class ApprovalExpiredError(PermissionError):
    error_code = "APPROVAL_EXPIRED"
```

`ApprovalService` raises this type when `proposal.expires_at <= now`.
In `PipelineService.approve`, catch it before saving an approval:

```python
try:
    approval = self._approval.approve_local(
        proposal=proposal,
        verdict=verdict,
        approved=True,
        now=now,
    )
except ApprovalExpiredError:
    return self._transition(
        run_id,
        PipelineState.APPROVAL_EXPIRED,
        now,
        error_code="APPROVAL_EXPIRED",
    )
```

After `LiveBlockedError`, add a fail-closed executor branch:

```python
except Exception:
    return self._transition(
        run_id,
        PipelineState.EXECUTION_FAILED,
        now,
        approval_id=str(approval.approval_id),
        error_code="LIVE_EXECUTION_FAILED",
    )
```

Before `UNKNOWN`, map explicit rejection:

```python
if receipt.accepted is False or receipt.status == "REJECTED":
    return self._transition(
        run_id,
        PipelineState.EXECUTION_FAILED,
        now,
        approval_id=str(approval.approval_id),
        order_id=receipt.broker_order_id,
        error_code="BROKER_ORDER_REJECTED",
    )
```

- [ ] **Step 4: Run focused and state-machine suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_pipeline.py `
  tests\unit\test_pipeline_state.py -q
.\.venv\Scripts\python.exe -m ruff check `
  src\bagholder\domain\pipeline.py `
  src\bagholder\application\pipeline_service.py `
  tests\integration\test_pipeline.py
.\.venv\Scripts\python.exe -m mypy src
```

Expected: all commands exit 0.

- [ ] **Step 5: Commit**

```powershell
git add src/bagholder/domain/pipeline.py `
  src/bagholder/application/approval_service.py `
  src/bagholder/application/pipeline_service.py `
  tests/integration/test_pipeline.py
git commit -m "fix: persist live approval terminal outcomes"
```

---

### Task 2: Define a Strict LIVE Order Domain

**Files:**
- Create: `src/bagholder/domain/live_order.py`
- Create: `src/bagholder/domain/account_runtime.py`
- Modify: `src/bagholder/domain/broker.py`
- Modify: `src/bagholder/testing/fake_gateway.py`
- Modify: `tests/contract/test_live_order_domain.py`
- Modify: existing Gateway tests that construct `BrokerOrderReceipt`

**Interfaces:**
- Produces: `LiveOrderStatus`, `BrokerOrderAck`, `BrokerOrderUpdate`, `TradeFill`, `LiveOrderRecord`, `CancelRequestRecord`
- Produces: `AccountRuntimeState`, `AccountRuntimeRecord`
- Produces: `ensure_live_order_transition(current, target) -> None`
- Changes: `BrokerGateway.submit(request) -> BrokerOrderAck`
- Changes: `BrokerGateway.query_order(account_id, broker_order_id) -> BrokerOrderUpdate`

- [ ] **Step 1: Write failing domain contract tests**

Create `tests/contract/test_live_order_domain.py`:

```python
from datetime import UTC, datetime
from decimal import Decimal

import pytest


def test_rejected_ack_必须明确未受理() -> None:
    from bagholder.domain.live_order import BrokerOrderAck, LiveOrderStatus

    ack = BrokerOrderAck(
        account_id="citic-main",
        security_key="CN:600000.SH",
        side="BUY",
        quantity=100,
        broker_order_id="CITIC-1",
        accepted=False,
        status=LiveOrderStatus.REJECTED,
        error_code="BROKER_PRICE_INVALID",
        occurred_at=datetime(2026, 7, 25, tzinfo=UTC),
    )
    assert ack.accepted is False


def test_accepted_false_不能声明_submitted() -> None:
    from bagholder.domain.live_order import BrokerOrderAck

    with pytest.raises(ValueError, match="accepted"):
        BrokerOrderAck(
            account_id="citic-main",
            security_key="CN:600000.SH",
            side="BUY",
            quantity=100,
            broker_order_id="CITIC-1",
            accepted=False,
            status="SUBMITTED",
            error_code=None,
            occurred_at=datetime(2026, 7, 25, tzinfo=UTC),
        )


def test_filled_不能回退到_submitted() -> None:
    from bagholder.domain.live_order import (
        LiveOrderStatus,
        ensure_live_order_transition,
    )

    with pytest.raises(ValueError, match="非法实盘订单状态转换"):
        ensure_live_order_transition(
            LiveOrderStatus.FILLED,
            LiveOrderStatus.SUBMITTED,
        )
```

- [ ] **Step 2: Run the contract and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_live_order_domain.py -q
```

Expected: import failure because `bagholder.domain.live_order` does not exist.

- [ ] **Step 3: Implement immutable models and transition rules**

Create `src/bagholder/domain/live_order.py` with:

```python
class LiveOrderStatus(StrEnum):
    CREATED = "CREATED"
    PRECHECK_PASSED = "PRECHECK_PASSED"
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
```

Implement frozen Pydantic models:

```python
class BrokerOrderAck(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str = Field(min_length=1)
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    side: OrderSide
    quantity: int = Field(gt=0)
    broker_order_id: str = Field(min_length=1)
    accepted: bool
    status: LiveOrderStatus
    error_code: str | None
    occurred_at: datetime
```

The model validator must enforce:

```python
if not self.accepted and self.status is not LiveOrderStatus.REJECTED:
    raise ValueError("accepted=false 时状态必须是 REJECTED")
if self.accepted and self.status is LiveOrderStatus.REJECTED:
    raise ValueError("REJECTED 回执不能声明 accepted=true")
```

Define `TradeFill` with `account_id`, `broker_order_id`, `broker_trade_id`,
`security_key`, `side`, `quantity`, `price`, and `occurred_at`. Define
`BrokerOrderUpdate` with:

```python
account_id: str
security_key: str
side: OrderSide
quantity: int
broker_order_id: str
broker_event_id: str
filled_quantity: int
remaining_quantity: int
average_fill_price: Decimal | None
status: LiveOrderStatus
fills: Sequence[TradeFill]
occurred_at: datetime
```

Its validator requires `filled_quantity + remaining_quantity == quantity`.

Define immutable `LiveOrderRecord` with:

```python
order_id: UUID
idempotency_key: str
account_id: str
broker_code: BrokerCode
broker_order_id: str | None
proposal_id: UUID
security_key: str
side: OrderSide
quantity: int
filled_quantity: int
limit_price: Decimal
average_fill_price: Decimal | None
status: LiveOrderStatus
error_code: str | None
created_at: datetime
updated_at: datetime
```

Define immutable `CancelRequestRecord` with `cancel_id`, `order_id`,
`idempotency_key`, `status`, `error_code`, `created_at`, and `updated_at`.

Create `domain/account_runtime.py`:

```python
class AccountRuntimeState(StrEnum):
    API_UNAVAILABLE = "API_UNAVAILABLE"
    RECONCILING = "RECONCILING"
    READY = "READY"
    HALTED = "HALTED"


@dataclass(frozen=True, slots=True)
class AccountRuntimeRecord:
    account_id: str
    broker_code: BrokerCode
    state: AccountRuntimeState
    freeze_reason: str | None
    session_id: str | None
    last_reconciled_at: datetime | None
    updated_at: datetime
```

- [ ] **Step 4: Change the Gateway protocol and controlled fakes**

In `domain/broker.py`:

```python
def submit(self, request: ExecutionRequest) -> BrokerOrderAck:
    raise NotImplementedError

def query_order(
    self,
    account_id: str,
    broker_order_id: str,
) -> BrokerOrderUpdate:
    raise NotImplementedError
```

Update every fake and test acknowledgement to echo account, security, side,
quantity, and occurred time. Do not supply defaults that allow a private
plugin to omit identity fields.

- [ ] **Step 5: Run contracts and type checks**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_live_order_domain.py `
  tests\integration\test_execution.py `
  tests\integration\test_multi_broker_routing.py -q
.\.venv\Scripts\python.exe -m ruff check src tests
.\.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 6: Commit**

```powershell
git add src/bagholder/domain/live_order.py `
  src/bagholder/domain/account_runtime.py `
  src/bagholder/domain/broker.py `
  src/bagholder/testing/fake_gateway.py `
  tests
git commit -m "feat: define strict live order domain"
```

---

### Task 3: Add Versioned SQLite Migrations and LIVE Repositories

**Files:**
- Create: `src/bagholder/infrastructure/sqlite_migrations.py`
- Create: `src/bagholder/infrastructure/sqlite_live_order_store.py`
- Modify: `src/bagholder/infrastructure/sqlite_store.py`
- Create: `tests/integration/test_sqlite_migrations.py`
- Create: `tests/integration/test_live_order_store.py`

**Interfaces:**
- Produces: `apply_migrations(connection: sqlite3.Connection) -> None`
- Produces: `SqliteLiveOrderStore`
- Produces repository methods for orders, events, fills, cancels, risk checks, reconciliation, and account runtime states

- [ ] **Step 1: Write a failing legacy-database migration test**

Create a version-1 SQLite database containing the existing
`execution_receipts` row, then initialize the new store:

```python
def test_v1_数据库升级后保留旧实盘回执(tmp_path: Path) -> None:
    database = tmp_path / "platform.db"
    create_v1_database_with_receipt(database)

    SqlitePlatformStore(database, tmp_path / "evidence")

    with sqlite3.connect(database) as connection:
        version = connection.execute(
            "SELECT MAX(version) FROM schema_migrations"
        ).fetchone()[0]
        receipt = connection.execute(
            "SELECT broker_order_id FROM execution_receipts"
        ).fetchone()
    assert version == 2
    assert receipt == ("LEGACY-1",)
```

Also add an idempotency test that initializes the same database twice.

- [ ] **Step 2: Run the migration tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_sqlite_migrations.py -q
```

Expected: `schema_migrations` does not exist.

- [ ] **Step 3: Implement ordered migration 2**

Move the current `_initialize` schema SQL into migration 1. On an empty
database, apply migrations 1 then 2. On a legacy database that already has
`execution_receipts` but no `schema_migrations`, create the migration table,
record version 1 without recreating or deleting tables, then apply version 2.
Each version runs in one transaction and records its version only after the SQL
succeeds.

Migration 2 creates:

```sql
CREATE TABLE live_orders (
    order_id TEXT PRIMARY KEY,
    idempotency_key TEXT NOT NULL UNIQUE,
    account_id TEXT NOT NULL,
    broker_code TEXT NOT NULL,
    broker_order_id TEXT UNIQUE,
    proposal_id TEXT NOT NULL,
    security_key TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    filled_quantity INTEGER NOT NULL,
    limit_price TEXT NOT NULL,
    average_fill_price TEXT,
    status TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE order_events (
    event_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    previous_status TEXT,
    new_status TEXT NOT NULL,
    broker_event_id TEXT,
    payload_json TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    recorded_at TEXT NOT NULL,
    UNIQUE(order_id, broker_event_id),
    FOREIGN KEY(order_id) REFERENCES live_orders(order_id)
);

CREATE TABLE trade_fills (
    fill_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    broker_trade_id TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    price TEXT NOT NULL,
    occurred_at TEXT NOT NULL,
    UNIQUE(order_id, broker_trade_id),
    FOREIGN KEY(order_id) REFERENCES live_orders(order_id)
);

CREATE TABLE cancel_requests (
    cancel_id TEXT PRIMARY KEY,
    order_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    error_code TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    FOREIGN KEY(order_id) REFERENCES live_orders(order_id)
);

CREATE TABLE risk_checks (
    check_id TEXT PRIMARY KEY,
    proposal_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    check_kind TEXT NOT NULL,
    verdict_json TEXT NOT NULL,
    facts_sha256 TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    expires_at TEXT NOT NULL
);

CREATE TABLE account_reconciliations (
    reconciliation_id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    broker_code TEXT NOT NULL,
    matched INTEGER NOT NULL,
    reasons_json TEXT NOT NULL,
    started_at TEXT NOT NULL,
    completed_at TEXT NOT NULL
);

CREATE TABLE account_runtime_states (
    account_id TEXT PRIMARY KEY,
    broker_code TEXT NOT NULL,
    state TEXT NOT NULL,
    freeze_reason TEXT,
    session_id TEXT,
    last_reconciled_at TEXT,
    updated_at TEXT NOT NULL
);
```

- [ ] **Step 4: Write store tests before repository methods**

Test:

- creating `SUBMITTING` order and first event in one transaction;
- duplicate idempotency returns the existing order;
- duplicate broker trade ID does not create a second fill;
- event insertion and current snapshot update commit together;
- secrets named `secret`, `token`, `password`, or `plugin_sha256` are rejected
  from event payloads.

- [ ] **Step 5: Implement `SqliteLiveOrderStore`**

Expose typed methods:

```python
def create_submitting_order(
    request: ExecutionRequest,
    broker_code: BrokerCode,
    now: datetime,
) -> LiveOrderRecord:
    raise NotImplementedError

def find_by_idempotency_key(
    key: str,
) -> LiveOrderRecord | None:
    raise NotImplementedError

def get_order(order_id: str) -> LiveOrderRecord:
    raise NotImplementedError

def get_by_broker_order_id(
    account_id: str,
    broker_order_id: str,
) -> LiveOrderRecord:
    raise NotImplementedError

def apply_order_update(
    order_id: str,
    update: BrokerOrderUpdate,
) -> LiveOrderRecord:
    raise NotImplementedError

def add_fill(order_id: str, fill: TradeFill) -> None:
    raise NotImplementedError

def list_open_orders(
    account_id: str | None = None,
) -> Sequence[LiveOrderRecord]:
    raise NotImplementedError

def create_cancel_request(
    order_id: str,
    idempotency_key: str,
    now: datetime,
) -> CancelRequestRecord:
    raise NotImplementedError

def set_account_runtime_state(record: AccountRuntimeRecord) -> None:
    raise NotImplementedError

def get_account_runtime_state(
    account_id: str,
) -> AccountRuntimeRecord | None:
    raise NotImplementedError
```

Risk-check and reconciliation repository methods are added with their domain
types in Tasks 5 and 10; Task 3 creates those tables but does not introduce
forward references to later application types.

- [ ] **Step 6: Run migration, repository, and existing SQLite suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_sqlite_migrations.py `
  tests\integration\test_live_order_store.py `
  tests\integration\test_paper_execution.py `
  tests\integration\test_evidence_store.py -q
.\.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/infrastructure `
  tests/integration/test_sqlite_migrations.py `
  tests/integration/test_live_order_store.py
git commit -m "feat: persist live order lifecycle with migrations"
```

---

### Task 4: Add Security-Specific Broker Facts

**Files:**
- Create: `src/bagholder/domain/broker_facts.py`
- Modify: `src/bagholder/domain/broker.py`
- Modify: `src/bagholder/adapters/broker/vnpy_gateway.py`
- Modify: `integrations/vnpy/server.py`
- Modify: `integrations/vnpy/bagholder_vnpy_fake.py`
- Modify: `src/bagholder/adapters/broker/broker_config.py`
- Modify: both `config/brokers/*.json`
- Modify: `tests/contract/test_vnpy_gateway_contract.py`
- Modify: `tests/unit/test_broker_runtime_registry.py`

**Interfaces:**
- Produces: `BrokerQuote`, `BrokerFunds`, `BrokerPosition`, `BrokerAccountFacts`
- Changes: `BrokerGateway.query_quote(account_id, security_key) -> BrokerQuote`
- Adds vn.py command: `QUERY_QUOTE`

- [ ] **Step 1: Write failing quote validation tests**

Create tests that reject:

- quote for a different security;
- future quote timestamp;
- `last_price` outside daily low/high limit;
- non-positive tick size;
- stale quote older than five seconds at validation time.

The valid fixture is:

```python
BrokerQuote(
    account_id="citic-main",
    security_key="CN:600000.SH",
    last_price=Decimal("10.00"),
    bid_price_1=Decimal("9.99"),
    ask_price_1=Decimal("10.00"),
    upper_limit=Decimal("11.00"),
    lower_limit=Decimal("9.00"),
    tick_size=Decimal("0.01"),
    tradable=True,
    halted=False,
    market_time=NOW,
    received_at=NOW,
    session_id="citic-session-1",
)
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_broker_facts.py `
  tests\contract\test_vnpy_gateway_contract.py -q
```

Expected: `BrokerQuote` and `QUERY_QUOTE` are missing.

- [ ] **Step 3: Implement immutable fact models**

`BrokerFunds` must include `account_id`, `cash_available`, `buying_power`,
`frozen_cash`, `net_asset`, `as_of`, and `session_id`.

`BrokerPosition` must include `account_id`, `security_key`, total and
available-to-sell quantity, average cost, market value, and `as_of`.

`BrokerAccountFacts` has:

```python
account_id: str
session_id: str
quote: BrokerQuote
funds: BrokerFunds
positions: Sequence[BrokerPosition]
orders: Sequence[BrokerOrderUpdate]
trades: Sequence[TradeFill]
account_state: BrokerApiState
observed_at: datetime
```

A model validator rejects mixed accounts, mixed sessions, or facts with
different observation windows.

- [ ] **Step 4: Extend Gateway, vn.py client mapping, and node dispatch**

Add:

```python
def query_quote(
    self,
    account_id: str,
    security_key: str,
) -> BrokerQuote:
    result = self._client.request(
        "QUERY_QUOTE",
        {"account_id": account_id, "security_key": security_key},
    )
    return BrokerQuote.model_validate(result)
```

The node dispatch calls `gateway.query_quote(account_id, security_key)`.
The controlled fake returns the exact requested identity and keeps
`test_plugin=True`.

- [ ] **Step 5: Require `market_data` and `single_order_query` capabilities**

Add `single_order_query` to `CAPABILITY_NAMES` and both default profiles.
Registry health remains unavailable if either capability is missing.

- [ ] **Step 6: Run Gateway contracts and fake-production rejection**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_vnpy_gateway_contract.py `
  tests\unit\test_broker_runtime_registry.py `
  tests\contract\test_broker_profiles.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/domain `
  src/bagholder/adapters/broker `
  integrations/vnpy `
  config/brokers `
  tests
git commit -m "feat: query security-specific broker facts"
```

---

### Task 5: Implement Final Limit-Price Confirmation and Pre-Submit Risk

**Files:**
- Create: `src/bagholder/application/pre_submit_risk_service.py`
- Modify: `src/bagholder/contracts/live_trading.py`
- Modify: `src/bagholder/application/execution_service.py`
- Modify: `src/bagholder/runtime.py`
- Modify: `src/bagholder/bootstrap.py`
- Create: `tests/integration/test_pre_submit_risk.py`
- Modify: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Produces: `PreSubmitRiskResult`
- Produces: `PreSubmitRiskService.evaluate(proposal: OrderProposal, facts: BrokerAccountFacts, now: datetime) -> PreSubmitRiskResult`
- Adds: `ExecutionRequest.execution_limit_price: Decimal | None`
- Adds: `ExecutionRequest.pre_submit_risk_verdict: RiskVerdict | None`
- Adds: `PlatformRuntime.prepare_live_submission(run_id, execution_limit_price, now) -> PreSubmitRiskResult`

- [ ] **Step 1: Write failing tests for refreshed facts**

Test that a proposal that passed initial risk is blocked when refreshed facts
show:

- stale quote;
- insufficient cash;
- reduced T+1 sell availability;
- halted security;
- limit price outside current upper/lower limits;
- mismatched account or security;
- fact session changed during refresh.
- the user limit price is absent, has an invalid tick, or is outside the
  refreshed daily limits.

Add a success assertion:

```python
result = service.evaluate(
    proposal=proposal,
    execution_limit_price=Decimal("10.00"),
    facts=fresh_facts,
    now=NOW,
)
assert result.verdict.allowed is True
assert result.expires_at == NOW + timedelta(seconds=5)
assert len(result.facts_sha256) == 64
```

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_pre_submit_risk.py -q
```

Expected: service does not exist.

- [ ] **Step 3: Implement deterministic final risk evaluation**

Define:

```python
@dataclass(frozen=True, slots=True)
class PreSubmitRiskResult:
    verdict: RiskVerdict
    execution_limit_price: Decimal
    facts_sha256: str
    checked_at: datetime
    expires_at: datetime
```

The service reuses exposure rules from `LiveRiskService` but adds:

```python
if facts.quote.account_id != proposal.account_id:
    reasons.append("BROKER_ACCOUNT_MISMATCH")
if facts.quote.security_key != proposal.security_key:
    reasons.append("BROKER_SECURITY_MISMATCH")
if now - facts.quote.market_time > timedelta(seconds=5):
    reasons.append("STALE_QUOTE")
if execution_limit_price % facts.quote.tick_size != 0:
    reasons.append("INVALID_PRICE_TICK")
if not facts.quote.lower_limit <= execution_limit_price <= facts.quote.upper_limit:
    reasons.append("PRICE_LIMIT_VIOLATION")
```

Hash a canonical, secret-free JSON representation of the facts and persist the
hash plus verdict and expiry.

Add these methods to `SqliteLiveOrderStore`:

```python
def save_risk_check(self, result: PreSubmitRiskResult) -> None:
    raise NotImplementedError

def get_risk_check(self, verdict_id: UUID) -> PreSubmitRiskResult:
    raise NotImplementedError
```

- [ ] **Step 4: Require final verdict in LIVE execution**

Add to `ExecutionRequest`:

```python
execution_limit_price: Decimal | None = None
pre_submit_risk_verdict: RiskVerdict | None = None
```

`LiveExecutionService` rejects LIVE requests unless the final verdict:

- exists;
- is allowed;
- references the same proposal;
- is no older than five seconds;
- matches the stored fact hash record.
- has the same `execution_limit_price` as the stored risk result.

Extend the LIVE executor repository protocol with
`get_risk_check(verdict_id: UUID) -> PreSubmitRiskResult`; validation loads the
stored record, compares the proposal ID, and requires
`now < stored.expires_at`. It never accepts a verdict supplied only in memory.

PAPER requests continue without a second verdict.

- [ ] **Step 5: Validate the channel, refresh facts, then confirm exact terms**

In `bootstrap._execute` LIVE approval:

```python
_require_live_confirmation_channel(args.confirm_live)
prepared = runtime.prepare_live_submission(
    args.run_id,
    Decimal(args.limit_price),
    now,
)
confirmed = _confirm_live_terms(
    binding.config.broker_code,
    run,
    prepared.execution_limit_price,
)
live_context = runtime.live_gate_context(
    run.account_id,
    interactive_confirmation=confirmed,
)
return runtime.pipeline.approve(
    run_id=args.run_id,
    mode=mode,
    interactive_confirmation=confirmed,
    live_context=live_context,
    execution_limit_price=prepared.execution_limit_price,
    pre_submit_risk_verdict=prepared.verdict,
    now=now,
)
```

Register `--limit-price` for LIVE approval and reject it for PAPER. The exact
confirmation text is:

```text
<BROKER> <ACCOUNT_ID> <SECURITY_KEY> <SIDE> <QUANTITY> @ <LIMIT_PRICE>
```

The broker query must not run when `--confirm-live`, `--limit-price`, or an
interactive terminal is absent. If the prepared result expires while waiting
for exact input, return `PRE_SUBMIT_FACTS_EXPIRED`; do not submit or
automatically refresh.

- [ ] **Step 6: Run final-risk, CLI, and live-gate suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_pre_submit_risk.py `
  tests\integration\test_live_execution_gate.py `
  tests\unit\test_bootstrap.py -q
.\.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/application/pre_submit_risk_service.py `
  src/bagholder/contracts/live_trading.py `
  src/bagholder/application/execution_service.py `
  src/bagholder/runtime.py `
  src/bagholder/bootstrap.py `
  tests
git commit -m "feat: recheck broker facts before live submit"
```

---

### Task 6: Implement Idempotent LIVE Submission and Ack Validation

**Files:**
- Create: `src/bagholder/application/live_order_service.py`
- Modify: `src/bagholder/application/execution_service.py`
- Modify: `src/bagholder/application/pipeline_service.py`
- Modify: `src/bagholder/runtime.py`
- Create: `tests/integration/test_live_order_submission.py`

**Interfaces:**
- Produces: `LiveOrderService.submit(request, binding, now) -> LiveOrderRecord`
- Consumes: `SqliteLiveOrderStore`, `BrokerRuntimeBinding`, `BrokerOrderAck`
- Replaces: direct `LiveExecutionService` receipt persistence

- [ ] **Step 1: Write failing submit tests**

Cover:

- `SUBMITTING` is persisted before Gateway invocation;
- matching accepted acknowledgement becomes `SUBMITTED`;
- explicit rejection becomes `REJECTED`;
- persisted order and Gateway request use `execution_limit_price`, not the
  proposal's public-data reference price;
- timeout becomes `UNKNOWN`;
- account/security/side/quantity mismatch becomes `UNKNOWN` and halts account;
- repeated idempotency returns the existing record without a second submit;
- an unavailable account never invokes another Gateway.

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_order_submission.py -q
```

Expected: `LiveOrderService` does not exist.

- [ ] **Step 3: Implement submit sequence**

The method order is fixed:

```python
existing = repository.find_by_idempotency_key(request.idempotency_key)
if existing is not None:
    return existing
order = repository.create_submitting_order(request, binding.config.broker_code, now)
try:
    ack = binding.gateway.submit(request)
except TimeoutError:
    return repository.mark_unknown(order.order_id, "BROKER_SUBMIT_TIMEOUT", now)
except Exception:
    return repository.mark_unknown(order.order_id, "BROKER_SUBMIT_FAILED", now)
validate_ack_identity(request, ack)
return repository.apply_ack(order.order_id, ack, now)
```

`validate_ack_identity` compares every echoed field. Mismatch triggers
`AccountRuntimeState.HALTED` with `BROKER_ACK_IDENTITY_MISMATCH`.
`create_submitting_order` requires `request.execution_limit_price` for LIVE and
stores that value as `live_orders.limit_price`.

- [ ] **Step 4: Route by account without constructing fallback services**

`AccountRoutedLiveExecutionService` resolves exactly one binding and delegates
to one shared `LiveOrderService`. It must not scan `registry.bindings()`.

- [ ] **Step 5: Map order record to pipeline state**

`REJECTED` maps to `EXECUTION_FAILED/BROKER_ORDER_REJECTED`.
`UNKNOWN` maps to `RECONCILIATION_REQUIRED/ORDER_STATE_UNKNOWN`.
`SUBMITTED` or later accepted status maps to `LIVE_SUBMITTED`.

- [ ] **Step 6: Run submission, pipeline, and routing suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_order_submission.py `
  tests\integration\test_pipeline.py `
  tests\integration\test_multi_broker_routing.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/application `
  src/bagholder/runtime.py `
  tests
git commit -m "feat: submit live orders with strict persistence"
```

---

### Task 7: Apply Order Updates, Partial Fills, and Terminal Events

**Files:**
- Create: `src/bagholder/application/order_lifecycle_service.py`
- Modify: `src/bagholder/infrastructure/sqlite_live_order_store.py`
- Create: `tests/integration/test_order_lifecycle.py`

**Interfaces:**
- Produces: `OrderLifecycleService.apply_update(order_id, update, now) -> LiveOrderRecord`
- Produces: `OrderLifecycleService.refresh(order_id, gateway, now) -> LiveOrderRecord`

- [ ] **Step 1: Write failing lifecycle tests**

Test:

- `SUBMITTED → PARTIALLY_FILLED → FILLED`;
- duplicate broker event and trade IDs are idempotent;
- total fill quantity cannot exceed order quantity;
- average fill price is recomputed from fills;
- terminal states reject later non-identical updates;
- `FILLED → SUBMITTED` is rejected and records a security event;
- a broker-reported account/order identity mismatch halts the account.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_order_lifecycle.py -q
```

- [ ] **Step 3: Implement transactional update application**

In one transaction:

1. load the current order;
2. validate identity and status transition;
3. insert previously unseen fills;
4. calculate aggregate filled quantity and weighted average;
5. update current order snapshot;
6. append an immutable event.

Use broker event/trade IDs for deduplication. Do not deduplicate by timestamp.

- [ ] **Step 4: Implement single-order refresh**

```python
update = gateway.query_order(order.account_id, order.broker_order_id)
return self.apply_update(order.order_id, update, now)
```

An ambiguous query error leaves the order unchanged and returns a stable
`BROKER_ORDER_QUERY_FAILED` error to the caller.

- [ ] **Step 5: Run lifecycle and repository suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_order_lifecycle.py `
  tests\integration\test_live_order_store.py -q
.\.venv\Scripts\python.exe -m mypy src
```

- [ ] **Step 6: Commit**

```powershell
git add src/bagholder/application/order_lifecycle_service.py `
  src/bagholder/infrastructure/sqlite_live_order_store.py `
  tests/integration/test_order_lifecycle.py
git commit -m "feat: persist live order updates and fills"
```

---

### Task 8: Monitor Non-Terminal Orders Without Resubmission

**Files:**
- Create: `src/bagholder/application/live_order_monitor.py`
- Modify: `src/bagholder/bootstrap.py`
- Modify: `src/bagholder/runtime.py`
- Create: `tests/integration/test_live_order_monitor.py`

**Interfaces:**
- Produces: `LiveOrderMonitor.run_once(account_id: str | None, now: datetime) -> MonitorReport`
- Produces: `LiveOrderMonitor.run_forever(account_id: str | None, poll_interval_seconds: float, stop: Event) -> None`
- Adds CLI: `live monitor --account <account_id> --once`
- Never calls `BrokerGateway.submit`

- [ ] **Step 1: Write failing bounded-monitor tests**

Cover:

- one pass queries every non-terminal order exactly once;
- terminal orders are never queried;
- update and fill events flow through `OrderLifecycleService`;
- an order query timeout keeps the order non-terminal and records a stable
  monitor error;
- `UNKNOWN` appears in `MonitorReport.reconciliation_required_accounts` and
  never calls submit;
- CITIC query failure does not stop Guotai Haitong refresh;
- a supplied stop event exits `run_forever` without waiting for another full
  interval.

Use an injected clock and wait function; tests must not use real sleeps.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_order_monitor.py -q
```

Expected: `LiveOrderMonitor` does not exist.

- [ ] **Step 3: Implement one bounded monitoring pass**

`run_once`:

1. loads open orders from `SqliteLiveOrderStore`;
2. groups them by account;
3. resolves exactly one binding per account;
4. calls `OrderLifecycleService.refresh` for each order;
5. records per-order success/error without aborting other accounts;
6. includes unresolved `UNKNOWN` accounts in the returned reconciliation list;
7. returns counts and stable error codes in `MonitorReport`.

The monitor receives no `ExecutionRequest` and has no reference to
`LiveOrderService.submit`.

- [ ] **Step 4: Implement condition-based continuous monitoring**

`run_forever` calls `run_once`, then waits on `stop.wait(poll_interval_seconds)`.
Validate the interval is between `0.5` and `60` seconds. On account disconnect,
use bounded exponential backoff per account with a maximum of 60 seconds; other
accounts retain their normal interval.

- [ ] **Step 5: Add the operator CLI**

Add:

```text
live monitor --once
live monitor --account citic-main --once
live monitor --account citic-main --poll-interval 2
```

Continuous mode requires a terminal and handles `Ctrl+C` by setting the stop
event. JSON output is available only with `--once`; continuous mode emits
one-line, secret-free operational summaries.

- [ ] **Step 6: Run monitor, lifecycle, and multi-account suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_order_monitor.py `
  tests\integration\test_order_lifecycle.py `
  tests\integration\test_multi_broker_routing.py `
  tests\unit\test_bootstrap.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/application/live_order_monitor.py `
  src/bagholder/bootstrap.py `
  src/bagholder/runtime.py `
  tests/integration/test_live_order_monitor.py `
  tests/unit/test_bootstrap.py
git commit -m "feat: monitor live order lifecycle"
```

---

### Task 9: Add Safe Cancellation and Broker Query CLI

**Files:**
- Create: `src/bagholder/application/cancel_order_service.py`
- Create: `src/bagholder/application/broker_query_service.py`
- Modify: `src/bagholder/bootstrap.py`
- Modify: `src/bagholder/runtime.py`
- Create: `tests/integration/test_cancel_order.py`
- Modify: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Produces: `CancelOrderService.cancel(order_id, now) -> CancelRequestRecord`
- Produces read-only query methods for quote, funds, positions, orders, and trades
- Adds CLI commands defined in the approved design

- [ ] **Step 1: Write failing cancellation tests**

Cover:

- only `SUBMITTED` and `PARTIALLY_FILLED` can enter `CANCEL_PENDING`;
- a halted account may cancel an existing open order;
- a cancelled or filled order cannot be cancelled;
- duplicate cancel idempotency makes one Gateway call;
- cancel timeout leaves `CANCEL_PENDING` and requests reconciliation;
- partial fill remains persisted after cancellation.

- [ ] **Step 2: Write failing CLI tests**

Assert parser and JSON behavior for:

```text
broker account show citic-main
broker quote citic-main CN:600000.SH
broker funds citic-main
broker positions citic-main
broker orders citic-main
broker trades citic-main
order cancel <order-id> --broker CITIC --confirm-live
order reconcile <order-id>
account reconcile citic-main
```

Missing or mismatched `--broker` must fail before a Gateway call. Query output
must not contain plugin path, digest, secret, token, or raw exception text.

- [ ] **Step 3: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_cancel_order.py `
  tests\unit\test_bootstrap.py -k "broker or 撤单 or 对账" -q
```

- [ ] **Step 4: Implement cancellation**

Persist the cancel request before the Gateway call. The exact confirmation
string is:

```text
<BROKER> <ACCOUNT_ID> CANCEL <BROKER_ORDER_ID> <REMAINING_QUANTITY>
```

On a positive response, refresh the order rather than assuming it is already
`CANCELLED`.

- [ ] **Step 5: Implement read-only query service and CLI**

Every query resolves one account binding and calls only that Gateway. Queries
may run in `HALTED`; modifying commands remain gated and audited.

- [ ] **Step 6: Run CLI, cancellation, and routing suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_cancel_order.py `
  tests\integration\test_multi_broker_routing.py `
  tests\unit\test_bootstrap.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/application/cancel_order_service.py `
  src/bagholder/application/broker_query_service.py `
  src/bagholder/bootstrap.py `
  src/bagholder/runtime.py `
  tests
git commit -m "feat: query and cancel live broker orders"
```

---

### Task 10: Persist Account Runtime State and Reconcile

**Files:**
- Modify: `src/bagholder/domain/account_runtime.py`
- Create: `src/bagholder/application/account_reconciliation_service.py`
- Modify: `src/bagholder/application/reconciliation_service.py`
- Modify: `src/bagholder/application/live_order_monitor.py`
- Modify: `src/bagholder/adapters/broker/broker_runtime_registry.py`
- Modify: `src/bagholder/runtime.py`
- Create: `tests/integration/test_account_reconciliation_runtime.py`

**Interfaces:**
- Consumes: `AccountRuntimeState`, `AccountRuntimeRecord` from Task 2
- Produces: `ReconciliationRecord`
- Produces: `AccountReconciliationService.reconcile(account_id, now) -> ReconciliationRecord`
- Consumes: broker funds, positions, orders, trades and local LIVE store

- [ ] **Step 1: Write failing reconciliation tests**

Cover:

- matching funds/positions/orders/trades enters `READY`;
- any unexplained difference enters `HALTED`;
- `UNKNOWN` order freezes new openings;
- a new Gateway session ID invalidates prior reconciliation;
- one halted account does not change another account;
- status exposes only stable freeze reason and last reconciliation time;
- query and cancellation remain available while halted.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_account_reconciliation_runtime.py -q
```

- [ ] **Step 3: Implement the reconciliation record and repository**

Add to `domain/account_runtime.py`:

```python
@dataclass(frozen=True, slots=True)
class ReconciliationRecord:
    reconciliation_id: UUID
    account_id: str
    broker_code: BrokerCode
    matched: bool
    reasons: Sequence[str]
    started_at: datetime
    completed_at: datetime
```

Add to `SqliteLiveOrderStore`:

```python
def save_reconciliation(self, record: ReconciliationRecord) -> None:
    raise NotImplementedError
```

Only a successful reconciliation for the current session may enter `READY`.

- [ ] **Step 4: Implement reconciliation collection and comparison**

Collect all broker facts from the same binding and session. Compare:

- cash, buying power, frozen cash, net asset;
- positions by security and available-to-sell quantity;
- all local non-terminal broker order IDs;
- all locally persisted broker trade IDs.

Persist the reconciliation batch even when it fails. Do not persist raw SDK
payloads.

- [ ] **Step 5: Make LIVE gates consume persisted account state**

Extend `BrokerRuntimeRegistry.build` with:

```python
runtime_state_provider: Callable[
    [str],
    AccountRuntimeRecord | None,
] | None = None
```

`build_runtime` passes `live_order_store.get_account_runtime_state`. Gateway
health success alone yields `RECONCILING`, not `READY`, when the session lacks
a successful reconciliation. `LiveGateContext` requires the persisted state to
be `READY`.

Inject `AccountReconciliationService` into `LiveOrderMonitor`. After each
bounded pass, reconcile every account in
`MonitorReport.reconciliation_required_accounts`; a failure remains isolated
to that account.

- [ ] **Step 6: Run reconciliation, registry, and gate suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_account_reconciliation_runtime.py `
  tests\integration\test_reconciliation.py `
  tests\unit\test_broker_runtime_registry.py `
  tests\integration\test_live_execution_gate.py -q
```

- [ ] **Step 7: Commit**

```powershell
git add src/bagholder/domain/account_runtime.py `
  src/bagholder/application/account_reconciliation_service.py `
  src/bagholder/application/reconciliation_service.py `
  src/bagholder/application/live_order_monitor.py `
  src/bagholder/adapters/broker/broker_runtime_registry.py `
  src/bagholder/runtime.py `
  tests
git commit -m "feat: reconcile and freeze live broker accounts"
```

---

### Task 11: Recover Non-Terminal Orders After Restart

**Files:**
- Create: `src/bagholder/application/live_recovery_service.py`
- Modify: `src/bagholder/runtime.py`
- Modify: `src/bagholder/bootstrap.py`
- Create: `tests/integration/test_live_restart_recovery.py`

**Interfaces:**
- Produces: `LiveRecoveryService.recover_account(account_id, now) -> RecoveryReport`
- Produces: `LiveRecoveryService.recover_order(order_id, now) -> LiveOrderRecord`
- Never calls `submit`

- [ ] **Step 1: Write a two-process-style restart test**

The first store instance persists an order as `UNKNOWN`, then closes. A new
store/runtime instance uses a Gateway reporting the same broker order as
`FILLED`.

Assertions:

```python
assert second_gateway.submit_call_count == 0
assert recovered.status is LiveOrderStatus.FILLED
assert store.count_fills(order.order_id) == 1
assert account.state is AccountRuntimeState.READY
```

Also test an unresolved `UNKNOWN` remains halted.

- [ ] **Step 2: Run tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_restart_recovery.py -q
```

- [ ] **Step 3: Implement recovery without submit**

Recovery:

1. scans local non-terminal orders;
2. queries each broker order by account and broker order ID;
3. applies updates and fills through `OrderLifecycleService`;
4. runs account reconciliation;
5. leaves unresolved orders in `RECONCILIATION_REQUIRED`;
6. never reconstructs or sends `ExecutionRequest`.

- [ ] **Step 4: Wire explicit recovery entry points**

`account reconcile` and `order reconcile` call the recovery service. Do not run
automatic recovery from `status`; `status` remains a health/read-only command.
A later constant process may invoke the same service on startup.

- [ ] **Step 5: Run restart, idempotency, and CLI tests**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\integration\test_live_restart_recovery.py `
  tests\integration\test_execution.py `
  tests\unit\test_bootstrap.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/bagholder/application/live_recovery_service.py `
  src/bagholder/runtime.py `
  src/bagholder/bootstrap.py `
  tests/integration/test_live_restart_recovery.py `
  tests/unit/test_bootstrap.py
git commit -m "feat: recover live orders without resubmission"
```

---

### Task 12: Build the Common Broker Plugin Contract Suite

**Files:**
- Create: `tests/contract/broker_plugin_suite.py`
- Create: `tests/fixtures/scriptable_vnpy_gateway.py`
- Create: `tests/contract/test_scriptable_broker_plugin.py`
- Modify: `tests/contract/test_vnpy_gateway_contract.py`
- Create: `docs/broker-plugin-contract.md`

**Interfaces:**
- Produces: `BrokerPluginBehaviorContract` and `ProductionCandidateContract`
- Produces: a scriptable non-production Gateway for deterministic failure injection
- Produces: a documented private plugin factory `create_gateway()`

- [ ] **Step 1: Define contract cases as failing tests**

The behavior contract covers:

- health identity and account list;
- security quote identity and freshness;
- funds and positions identity;
- submit accepted, rejected, timeout, and duplicate scenarios;
- single-order query;
- partial fills and trade deduplication;
- cancellation;
- disconnect and session change;
- no cross-account access;
- no secret-bearing response keys.

`ProductionCandidateContract` runs the full behavior contract and additionally
requires `test_plugin is False`, a trusted file digest, a declared vendor
version, and a sandbox-environment identity. The repository scriptable fixture
must keep `test_plugin=True`: it passes the behavior contract and has a separate
test proving the production-candidate contract rejects it.

- [ ] **Step 2: Run contract tests and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract\test_scriptable_broker_plugin.py -q
```

- [ ] **Step 3: Implement the scriptable Gateway**

The fixture reads a deterministic scenario JSON from a pytest temporary
directory. Allowed scenarios are exact enum values:

```text
ACCEPTED
REJECTED
TIMEOUT_BEFORE_ACCEPT
TIMEOUT_AFTER_ACCEPT
PARTIAL_FILL
FILLED
CANCELLED
DISCONNECTED
SESSION_CHANGED
IDENTITY_MISMATCH
```

It records call counts and request identities but never accesses a network.

- [ ] **Step 4: Publish the private plugin contract**

`docs/broker-plugin-contract.md` defines the exact module-level factory
signature `create_gateway() -> BrokerGateway`. Its implementation constructs
the private vendor Gateway after reading credentials from the operating-system
credential store; the public contract never defines vendor credential fields.
The document includes all required methods and response schemas. It explicitly
forbids:

- embedding credentials in the plugin module;
- logging full requests;
- returning raw SDK exceptions;
- selecting a default account when the request account is unknown;
- retrying submit after an ambiguous timeout.

- [ ] **Step 5: Run all Gateway and contract suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\contract `
  tests\integration\test_live_order_submission.py `
  tests\integration\test_order_lifecycle.py `
  tests\integration\test_cancel_order.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add tests/contract `
  tests/fixtures `
  docs/broker-plugin-contract.md
git commit -m "test: define common private broker plugin contract"
```

---

### Task 13: Package Runtime Assets and Verify Installed Execution

**Files:**
- Create: `src/bagholder/runtime_assets/__init__.py`
- Move: `integrations/tradingagents/runner.py` to `src/bagholder/runtime_assets/tradingagents_runner.py`
- Move: `integrations/vnpy/server.py` to `src/bagholder/runtime_assets/vnpy_server.py`
- Move: default broker JSON to `src/bagholder/runtime_assets/brokers/`
- Modify: `src/bagholder/runtime.py`
- Modify: `src/bagholder/bootstrap.py`
- Modify: `pyproject.toml`
- Create: `tests/packaging/test_installed_wheel.py`

**Interfaces:**
- Produces: packaged default broker profiles and subprocess entry scripts
- Produces: `materialize_runtime_asset(name: str, home: Path) -> Path`
- Removes: dependency on `Path.cwd()` for required runtime assets

- [ ] **Step 1: Write a failing installed-wheel smoke test**

The test:

1. builds a wheel into `tmp_path`;
2. installs it into an isolated target;
3. runs from an empty directory;
4. imports the installed package;
5. runs `status --json` and `doctor --json`;
6. asserts both broker profiles appear;
7. asserts packaged runner and server files exist.

It must fail if the source checkout satisfies a missing installed asset, so
clear `PYTHONPATH` and run outside the repository.

- [ ] **Step 2: Run and verify RED**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\packaging\test_installed_wheel.py -q
```

Expected: installed status reports `CONFIG_DIRECTORY_MISSING` and the runner
and server assets are absent.

- [ ] **Step 3: Package and materialize assets with `importlib.resources`**

Add package data configuration:

```toml
[tool.hatch.build.targets.wheel]
packages = ["src/bagholder"]

[tool.hatch.build.targets.wheel.force-include]
"src/bagholder/runtime_assets" = "bagholder/runtime_assets"
```

`materialize_runtime_asset` reads bytes through
`importlib.resources.files("bagholder.runtime_assets")`, computes SHA-256, and
writes atomically to:

```text
<BAGHOLDER_HOME>/runtime-assets/<package-version>/<sha256>/<asset-name>
```

It returns the stable materialized path and reuses an existing file only when
its digest matches. This keeps subprocess paths valid after `build_runtime`
returns, including zip-based importers. User-supplied absolute environment
paths continue to override packaged assets.

Materialize both broker profile JSON files into one directory before calling
`BrokerConfigLoader`.

- [ ] **Step 4: Make doctor account-aware**

Doctor reports:

- main package;
- TradingAgents runtime and packaged runner;
- each broker account's configured vn.py Python and packaged server;
- configuration error codes;
- no sensitive values.

- [ ] **Step 5: Run packaging and local CLI suites**

```powershell
.\.venv\Scripts\python.exe -m pytest `
  tests\packaging\test_installed_wheel.py `
  tests\unit\test_bootstrap.py `
  tests\contract\test_broker_profiles.py -q
```

- [ ] **Step 6: Commit**

```powershell
git add src/bagholder/runtime_assets `
  src/bagholder/runtime.py `
  src/bagholder/bootstrap.py `
  pyproject.toml `
  tests/packaging `
  integrations `
  config/brokers
git commit -m "build: package broker and subprocess runtime assets"
```

---

### Task 14: Production Safety Acceptance and Operator Documentation

**Files:**
- Modify: `README.md`
- Modify: `.env.example`
- Create: `docs/live-trading-runbook.md`
- Create: `docs/citic-sandbox-acceptance.md`
- Create: `docs/guotai-haitong-sandbox-acceptance.md`
- Create: `tests/security/test_status_redaction.py`
- Create: `tests/security/test_live_fail_closed.py`

**Interfaces:**
- Produces: operator runbook, vendor-neutral acceptance evidence, and final fail-closed verification

- [ ] **Step 1: Add security acceptance tests**

Test:

- status and doctor never emit secret, token, password, plugin path, or digest;
- no broker configuration still yields safe unavailable accounts;
- global/account switches true without a reconciled Gateway remain blocked;
- the scriptable test Gateway is rejected for production;
- one unavailable account cannot route to the other;
- rejected, unknown, expired, halted, and stale-fact cases create no PAPER fill;
- a credential-pattern scan returns no tracked secret.

- [ ] **Step 2: Run and verify any missing acceptance behavior**

```powershell
.\.venv\Scripts\python.exe -m pytest tests\security -q
```

Expected: tests expose any remaining redaction or fail-closed gaps. Fix only a
reproduced gap, one RED-GREEN cycle at a time.

- [ ] **Step 3: Write the operator runbook**

Document exact procedures for:

- installing the three Python environments;
- configuring two accounts independently;
- checking status and doctor;
- reconciling an account;
- running LIVE research and proposal generation;
- interactive approval and final risk refresh;
- querying and cancelling orders;
- resolving `UNKNOWN`;
- halting an account;
- backing up and restoring SQLite;
- rotating the node HMAC secret and plugin digest;
- emergency shutdown by disabling global and account switches.

- [ ] **Step 4: Write sandbox acceptance matrices**

Both documents use the same cases. CITIC is executed first when official SDK
and sandbox access arrive. Guotai Haitong is executed second without changing
core order code.

Each case records:

- test environment identity;
- plugin version and digest;
- account ID;
- operation;
- expected stable platform state;
- observed broker state;
- evidence IDs;
- operator and review date.

- [ ] **Step 5: Run full verification**

```powershell
.\.venv\Scripts\python.exe -m pytest -q `
  --cov=bagholder --cov-report=term-missing
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\python.exe -m pip check
.\.runtime\tradingagents\Scripts\python.exe -m pip check
.\.runtime\vnpy\Scripts\python.exe -m pip check
git diff --check
```

Run explicit public-data smoke with LIVE switches unset:

```powershell
$env:RUN_LIVE_DATA_TESTS = "1"
try {
  .\.venv\Scripts\python.exe -m pytest `
    tests\live\test_astock_market_data.py -q
} finally {
  Remove-Item Env:RUN_LIVE_DATA_TESTS -ErrorAction SilentlyContinue
}
```

Build and install the wheel from an empty directory, then run:

```powershell
bagholder doctor --json
bagholder status --json
```

Expected before official SDKs: both accounts are present, disabled, and
`API_UNAVAILABLE`; all platform tests and packaging smoke tests pass.

- [ ] **Step 6: Scan for credentials**

```powershell
$matches = rg -n --hidden `
  -g "!/.git/**" -g "!/.venv/**" -g "!/.runtime/**" -g "!/var/**" `
  -e "AKIA[0-9A-Z]{16}" `
  -e "sk-[A-Za-z0-9_-]{20,}" `
  -e "-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----" `
  .
if ($LASTEXITCODE -eq 0) {
  $matches
  throw "发现疑似凭据"
}
if ($LASTEXITCODE -ne 1) {
  exit $LASTEXITCODE
}
```

- [ ] **Step 7: Commit**

```powershell
git add README.md .env.example docs tests/security
git commit -m "docs: add production live trading operations"
```

---

## External Gate A: CITIC Official Sandbox

Tasks 1-14 must finish before vendor integration. CITIC work starts only after
the user supplies all of:

- the official programmatic trading product name;
- SDK installer/package and version;
- official API documentation;
- sandbox endpoint and test account;
- market-data entitlement;
- order, cancel, funds, positions, order, trade, and reconnect specifications;
- credential-injection method approved for the workstation;
- written confirmation that the account is a non-production test account.

At that point, create a separate private-plugin design and plan from
`docs/broker-plugin-contract.md`. The CITIC plugin must pass the entire common
contract suite and `docs/citic-sandbox-acceptance.md`. No public repository
commit may contain the SDK, credentials, endpoint secrets, or account password.

## External Gate B: Guotai Haitong Official Sandbox

Guotai Haitong begins only after CITIC sandbox acceptance is complete and the
equivalent official resources are supplied. Its private plugin must pass the
same contract and `docs/guotai-haitong-sandbox-acceptance.md`.

Acceptance fails if Guotai Haitong requires:

- a core `if broker == GUOTAI_HAITONG` branch;
- a weaker health or identity check;
- skipping real-time quote, cancel, order, trade, timeout, or reconnect cases;
- routing through the CITIC account or Gateway;
- a different idempotency policy.

## Final Milestones

1. **Platform correctness:** Tasks 1-6 complete; rejected, expired, failed,
   timeout, and identity-mismatch behavior is deterministic and persisted.
2. **Lifecycle and recovery:** Tasks 7-11 complete; update, fill, monitoring,
   cancel, freeze, reconciliation, and restart recovery are green.
3. **Vendor-ready platform:** Tasks 12-14 complete; common contract, packaging,
   security acceptance, and operator documentation are green.
4. **CITIC sandbox ready:** External Gate A resources supplied and CITIC
   private plugin acceptance signed.
5. **Guotai Haitong sandbox ready:** External Gate B resources supplied and
   Guotai Haitong private plugin acceptance signed without core branching.
6. **Production release candidate:** a separate production-readiness review
   confirms credentials, rollback, backups, monitoring, regulatory approval,
   and explicit account enablement.
