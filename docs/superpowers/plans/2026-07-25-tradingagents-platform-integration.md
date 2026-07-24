# TradingAgents 平台集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将真实 A 股数据、TradingAgents 研究、不可变证据、模拟交易和受控实盘执行整合到现有 `bagholder` 命令行平台。

**Architecture:** 主平台保持轻依赖，通过 JSON Lines 子进程调用独立 TradingAgents 环境；SQLite 保存状态和交易账本，不可变 JSON 保存市场与研究证据。研究、风控和审批完成后，由执行路由器明确分流到本地 PAPER 撮合或签名的 vn.py LIVE Gateway，实盘不可用时硬阻断且绝不降级。

**Tech Stack:** Python 3.12、Pydantic 2、SQLite 标准库、TradingAgents-Astock 0.3.0、vn.py 4.4.0、pytest、Ruff、mypy。

## Global Constraints

- 主平台、TradingAgents 和 vn.py 必须继续使用 `.venv`、`.runtime/tradingagents`、`.runtime/vnpy` 三个独立环境。
- 所有生产代码使用 Python 3.12；主项目不直接依赖 TradingAgents 或 vn.py 包。
- 模型和券商密钥不得进入命令参数、SQLite、证据文件、日志或 Git。
- `LIVE` 失败不得转成 `PAPER`；中信和国泰海通未安装授权 Gateway 时保持 `API_UNAVAILABLE`。
- 所有金额和价格使用 `Decimal`；JSON 中以字符串序列化交易数值。
- 每个新行为必须先看到对应测试因缺少该行为而失败，再实现最小代码。
- 保留并通过现有 21 项测试、Ruff 和 mypy strict。
- 运行数据只写入 `var/`；`var/` 和 `.superpowers/` 不进入 Git。

---

## 文件结构

### 新建

- `src/bagholder/contracts/market_data.py`：外部行情、证据和研究进程契约。
- `src/bagholder/domain/pipeline.py`：管道、订单生命周期和稳定错误码。
- `src/bagholder/integrations/tradingagents_client.py`：隔离进程调用、超时和 JSON 校验。
- `src/bagholder/infrastructure/sqlite_store.py`：SQLite 模式、证据索引、运行状态和账本。
- `src/bagholder/application/market_data_service.py`：证券代码、行情校验和证据固化。
- `src/bagholder/application/research_service.py`：证据校验、智能体研究和决策固化。
- `src/bagholder/application/paper_execution_service.py`：模拟账户与事务撮合。
- `src/bagholder/application/pipeline_service.py`：端到端状态推进和执行分流。
- `src/bagholder/integrations/vnpy_client.py`：主平台到 vn.py 节点的签名传输。
- `src/bagholder/adapters/broker/vnpy_gateway.py`：把 vn.py 响应映射为通用 Gateway。
- `tests/unit/test_market_contracts.py`
- `tests/unit/test_tradingagents_client.py`
- `tests/unit/test_market_data_service.py`
- `tests/unit/test_pipeline_state.py`
- `tests/integration/test_evidence_store.py`
- `tests/integration/test_research_service.py`
- `tests/integration/test_paper_execution.py`
- `tests/integration/test_live_execution_gate.py`
- `tests/integration/test_pipeline.py`
- `tests/contract/test_vnpy_gateway_contract.py`
- `tests/live/test_astock_market_data.py`

### 修改

- `integrations/tradingagents/runner.py`：增加 `FETCH_MARKET`、`RUN_RESEARCH` 白名单操作。
- `integrations/vnpy/server.py`：增加受信插件加载和单请求 JSON 模式。
- `src/bagholder/contracts/live_trading.py`：增加订单状态与本地人工审批辅助契约。
- `src/bagholder/domain/broker.py`：补齐健康、订单与成交查询接口。
- `src/bagholder/application/approval_service.py`：增加本地人工审批。
- `src/bagholder/bootstrap.py`：注册 doctor、paper、market、research、pipeline、order 命令。
- `src/bagholder/testing/fake_gateway.py`：覆盖查询、撤单和订单生命周期。
- `.env.example`：改为 OpenAI 兼容 TradingAgents 配置。
- `.gitignore`：排除 `var/` 与 `.superpowers/`。
- `README.md`：写入安装、配置、模拟、实盘和验收命令。

---

### Task 1: 市场数据契约与 TradingAgents 隔离客户端

**Files:**
- Create: `src/bagholder/contracts/market_data.py`
- Create: `src/bagholder/integrations/tradingagents_client.py`
- Modify: `integrations/tradingagents/runner.py`
- Test: `tests/unit/test_market_contracts.py`
- Test: `tests/unit/test_tradingagents_client.py`

**Interfaces:**
- Produces: `MarketBar`, `MarketSnapshot`, `FetchMarketRequest`, `ResearchProcessRequest`, `ResearchProcessResult`
- Produces: `TradingAgentsClient.fetch_market(request) -> MarketSnapshot`
- Produces: `TradingAgentsClient.run_research(request) -> ResearchProcessResult`
- Consumes: `TRADINGAGENTS_PYTHON`, `TRADINGAGENTS_API_KEY`, `TRADINGAGENTS_MODEL`, `TRADINGAGENTS_BACKEND_URL`

- [ ] **Step 1: 写入会失败的行情契约测试**

```python
from datetime import date, datetime, UTC
from decimal import Decimal
import pytest
from pydantic import ValidationError

from bagholder.contracts.market_data import MarketBar, MarketSnapshot


def test_行情日期必须递增且不能重复() -> None:
    bar = MarketBar(
        date=date(2026, 7, 24),
        open=Decimal("10"),
        high=Decimal("11"),
        low=Decimal("9"),
        close=Decimal("10.5"),
        volume=1000,
    )
    with pytest.raises(ValidationError, match="日期"):
        MarketSnapshot(
            security_key="CN:600519.SH",
            start_date=date(2026, 7, 23),
            end_date=date(2026, 7, 24),
            as_of=date(2026, 7, 24),
            retrieved_at=datetime.now(UTC),
            source="sina HTTP",
            records=[bar, bar],
            schema_version="market-v1",
        )
```

- [ ] **Step 2: 运行契约测试并确认因模块不存在而失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_market_contracts.py -q
```

Expected: `ModuleNotFoundError: bagholder.contracts.market_data`

- [ ] **Step 3: 实现最小行情与研究进程契约**

```python
class MarketBar(BaseModel):
    model_config = ConfigDict(frozen=True)
    date: date
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: int = Field(ge=0)

    @model_validator(mode="after")
    def validate_range(self) -> "MarketBar":
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC 价格范围无效")
        return self


class MarketSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    start_date: date
    end_date: date
    as_of: date
    retrieved_at: datetime
    source: str = Field(min_length=1)
    records: list[MarketBar] = Field(min_length=1)
    schema_version: Literal["market-v1"] = "market-v1"

    @model_validator(mode="after")
    def validate_dates(self) -> "MarketSnapshot":
        dates = [row.date for row in self.records]
        if dates != sorted(set(dates)):
            raise ValueError("行情日期必须严格递增且不能重复")
        if dates[0] < self.start_date or dates[-1] > self.end_date:
            raise ValueError("行情日期超出请求范围")
        if self.end_date > self.as_of:
            raise ValueError("行情结束日期不能晚于分析时点")
        return self
```

同文件增加以下冻结契约：

```python
class FetchMarketRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str = Field(pattern=r"^\d{6}$")
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    start_date: date
    end_date: date
    as_of: date


class ResearchProcessRequest(BaseModel):
    model_config = ConfigDict(frozen=True)
    symbol: str = Field(pattern=r"^\d{6}$")
    security_key: str = Field(pattern=r"^CN:\d{6}\.(SH|SZ|BJ)$")
    analysis_date: date
    as_of: datetime
    evidence_ids: list[str] = Field(min_length=1)
    data_version: str = Field(min_length=64, max_length=64)
    model_config_payload: dict[str, object]


class ResearchProcessResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    action: Literal["BUY", "HOLD", "SELL"]
    confidence: Decimal = Field(ge=Decimal("0"), le=Decimal("1"))
    model_version: str = Field(min_length=1)
    as_of: datetime
    risk_flags: list[str] = Field(default_factory=list)
    reports: dict[str, object]
```

- [ ] **Step 4: 运行契约测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_market_contracts.py -q`  
Expected: PASS

- [ ] **Step 5: 写入会失败的隔离进程协议测试**

```python
def test_客户端拒绝标准输出中的额外文本(tmp_path: Path) -> None:
    runner = tmp_path / "bad_runner.py"
    runner.write_text(
        "import sys\nsys.stdin.readline()\nprint('debug')\nprint('{}')\n",
        encoding="utf-8",
    )
    client = TradingAgentsClient(
        python_executable=sys.executable,
        runner_path=runner,
        timeout_seconds=2,
    )
    with pytest.raises(TradingAgentsProtocolError):
        client.request({"operation": "FETCH_MARKET"})
```

- [ ] **Step 6: 运行客户端测试并确认因客户端不存在而失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_tradingagents_client.py -q`  
Expected: FAIL with missing `TradingAgentsClient`

- [ ] **Step 7: 实现单请求子进程客户端**

```python
class TradingAgentsProtocolError(RuntimeError):
    pass


class TradingAgentsClient:
    def __init__(
        self,
        python_executable: str | Path,
        runner_path: str | Path,
        timeout_seconds: float = 120,
    ) -> None:
        self._command = [str(python_executable), str(runner_path)]
        self._timeout_seconds = timeout_seconds

    def request(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            completed = subprocess.run(
                self._command,
                input=json.dumps(payload, ensure_ascii=False) + "\n",
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=self._timeout_seconds,
                check=False,
                env=self._safe_environment(),
            )
        except subprocess.TimeoutExpired as error:
            raise TimeoutError("TradingAgents 子进程超时") from error
        lines = [line for line in completed.stdout.splitlines() if line.strip()]
        if completed.returncode != 0:
            raise RuntimeError("TradingAgents 子进程执行失败")
        if len(lines) != 1:
            raise TradingAgentsProtocolError("TradingAgents 必须只输出一条 JSON")
        try:
            result = json.loads(lines[0])
        except json.JSONDecodeError as error:
            raise TradingAgentsProtocolError("TradingAgents 返回非法 JSON") from error
        if not isinstance(result, dict):
            raise TradingAgentsProtocolError("TradingAgents 响应必须是对象")
        return cast(dict[str, object], result)
```

`_safe_environment()` 从当前环境白名单复制 `PATH`、系统临时目录和四个 `TRADINGAGENTS_*` 配置，不复制其他潜在密钥。

- [ ] **Step 8: 扩展 runner 白名单操作**

`FETCH_MARKET` 使用 `tradingagents.dataflows.a_stock.get_stock_data()`，解析 CSV 为结构化记录并保留 `# Data source:`；`RUN_RESEARCH` 调用现有 `TradingAgentsGraph.propagate()`。任何诊断写入 `stderr`，`stdout` 只写最终 JSON。未知操作返回非零退出码。

- [ ] **Step 9: 运行 Task 1 测试和静态检查**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_market_contracts.py tests\unit\test_tradingagents_client.py -q
.\.venv\Scripts\python.exe -m ruff check src tests integrations\tradingagents\runner.py
.\.venv\Scripts\python.exe -m mypy src
```

Expected: all pass

- [ ] **Step 10: 提交 Task 1**

```powershell
git add src/bagholder/contracts/market_data.py src/bagholder/integrations/tradingagents_client.py integrations/tradingagents/runner.py tests/unit/test_market_contracts.py tests/unit/test_tradingagents_client.py
git commit -m "feat: add isolated TradingAgents market client"
```

---

### Task 2: SQLite 与不可变证据存储

**Files:**
- Create: `src/bagholder/infrastructure/sqlite_store.py`
- Create: `tests/integration/test_evidence_store.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `MarketSnapshot`, `ResearchProcessResult`
- Produces: `EvidenceRecord`
- Produces: `SqlitePlatformStore.save_evidence(kind, security_key, payload, created_at) -> EvidenceRecord`
- Produces: `SqlitePlatformStore.load_evidence(evidence_id) -> dict[str, object]`

- [ ] **Step 1: 写入篡改检测失败测试**

```python
def test_证据文件被修改后读取必须失败(tmp_path: Path) -> None:
    store = SqlitePlatformStore(tmp_path / "platform.db", tmp_path / "evidence")
    record = store.save_evidence(
        kind="MARKET",
        security_key="CN:600519.SH",
        payload={"schema_version": "market-v1", "records": [{"close": "10.50"}]},
        created_at=datetime(2026, 7, 25, tzinfo=UTC),
    )
    Path(record.path).write_text('{"changed":true}', encoding="utf-8")
    with pytest.raises(EvidenceTamperedError):
        store.load_evidence(record.evidence_id)
```

- [ ] **Step 2: 运行测试并确认因仓储不存在而失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_evidence_store.py -q`  
Expected: FAIL with missing `SqlitePlatformStore`

- [ ] **Step 3: 实现数据库初始化和证据表**

先定义返回类型：

```python
@dataclass(frozen=True, slots=True)
class EvidenceRecord:
    evidence_id: str
    kind: Literal["MARKET", "RESEARCH"]
    security_key: str
    schema_version: str
    source: str
    path: str
    sha256: str
    created_at: datetime


class EvidenceTamperedError(RuntimeError):
    pass
```

```sql
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
```

连接初始化时执行 `PRAGMA foreign_keys=ON`、`PRAGMA journal_mode=WAL` 和 `PRAGMA busy_timeout=5000`。

- [ ] **Step 4: 实现规范 JSON、排他写入和摘要复核**

```python
encoded = json.dumps(
    payload,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
digest = hashlib.sha256(encoded).hexdigest()
with path.open("xb") as stream:
    stream.write(encoded)
```

数据库写入失败时删除本次尚未登记的新文件；读取时重新计算摘要，不一致抛出 `EvidenceTamperedError`。

- [ ] **Step 5: 排除运行目录**

在 `.gitignore` 增加：

```gitignore
var/
.superpowers/
```

- [ ] **Step 6: 运行证据测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_evidence_store.py -q`  
Expected: PASS

- [ ] **Step 7: 提交 Task 2**

```powershell
git add .gitignore src/bagholder/infrastructure/sqlite_store.py tests/integration/test_evidence_store.py
git commit -m "feat: add immutable evidence store"
```

---

### Task 3: 市场与研究应用服务

**Files:**
- Create: `src/bagholder/application/market_data_service.py`
- Create: `src/bagholder/application/research_service.py`
- Test: `tests/unit/test_market_data_service.py`
- Test: `tests/integration/test_research_service.py`

**Interfaces:**
- Consumes: `TradingAgentsClient`, `SqlitePlatformStore`
- Produces: `MarketDataService.fetch(...) -> EvidenceRecord`
- Produces: `ResearchService.run(...) -> ResearchDecision`

- [ ] **Step 1: 写入证券代码和数据版本失败测试**

```python
def test_市场服务保存真实响应并生成稳定数据版本(fake_client, store) -> None:
    service = MarketDataService(fake_client, store)
    record = service.fetch(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
    )
    payload = store.load_evidence(record.evidence_id)
    assert payload["security_key"] == "CN:600519.SH"
    assert payload["records"][-1]["close"] == "1297.41"
    assert record.sha256 == hashlib.sha256(Path(record.path).read_bytes()).hexdigest()
```

- [ ] **Step 2: 运行测试并确认因服务不存在而失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_market_data_service.py -q`  
Expected: FAIL with missing `MarketDataService`

- [ ] **Step 3: 实现 MarketDataService**

服务必须：

```python
symbol = security_key.removeprefix("CN:").split(".", maxsplit=1)[0]
snapshot = self._client.fetch_market(
    FetchMarketRequest(
        symbol=symbol,
        security_key=security_key,
        start_date=start_date,
        end_date=end_date,
        as_of=as_of,
    )
)
return self._store.save_evidence(
    kind="MARKET",
    security_key=security_key,
    payload=snapshot.model_dump(mode="json"),
    created_at=snapshot.retrieved_at,
)
```

Pydantic 校验必须发生在写文件之前。

- [ ] **Step 4: 写入研究证据绑定失败测试**

```python
def test_研究决策引用市场和研究两份有效证据(fake_client, store) -> None:
    market = save_market_fixture(store)
    decision = ResearchService(fake_client, store).run(
        market_evidence_id=market.evidence_id,
        analysis_date=date(2026, 7, 24),
    )
    assert decision.evidence_ids[0] == market.evidence_id
    assert len(decision.evidence_ids) == 2
    store.load_evidence(decision.evidence_ids[1])
```

- [ ] **Step 5: 运行研究测试并确认因服务不存在而失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_research_service.py -q`  
Expected: FAIL with missing `ResearchService`

- [ ] **Step 6: 实现 ResearchService**

读取并验证市场证据后构造 `ResearchProcessRequest`。若 `TRADINGAGENTS_API_KEY` 为空，抛出带 `MODEL_NOT_CONFIGURED` 代码的平台异常。研究成功后先保存完整研究响应，再创建：

```python
ResearchDecision(
    decision_id=uuid4(),
    security_key=market_payload["security_key"],
    as_of=result.as_of,
    action=result.action,
    confidence=result.confidence,
    evidence_ids=[market_record.evidence_id, research_record.evidence_id],
    data_version=market_record.sha256,
    model_version=result.model_version,
    risk_flags=result.risk_flags,
)
```

- [ ] **Step 7: 运行 Task 3 测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_market_data_service.py tests\integration\test_research_service.py -q
```

Expected: PASS

- [ ] **Step 8: 提交 Task 3**

```powershell
git add src/bagholder/application/market_data_service.py src/bagholder/application/research_service.py tests/unit/test_market_data_service.py tests/integration/test_research_service.py
git commit -m "feat: bind research decisions to market evidence"
```

---

### Task 4: 管道状态与 SQLite 模拟交易账本

**Files:**
- Create: `src/bagholder/domain/pipeline.py`
- Create: `src/bagholder/application/paper_execution_service.py`
- Modify: `src/bagholder/infrastructure/sqlite_store.py`
- Test: `tests/unit/test_pipeline_state.py`
- Test: `tests/integration/test_paper_execution.py`

**Interfaces:**
- Produces: `PipelineState`, `PipelineErrorCode`, `ExecutionOrderStatus`, `PipelineRun`
- Produces: `PaperExecutionService.create_account(account_id, cash, now)`
- Produces: `PaperExecutionService.submit(request, now) -> BrokerOrderReceipt`

- [ ] **Step 1: 写入非法状态转移测试**

```python
def test_不能从等待审批跳过执行直接对账() -> None:
    with pytest.raises(ValueError, match="非法状态转移"):
        ensure_transition(PipelineState.WAITING_APPROVAL, PipelineState.RECONCILED)
```

- [ ] **Step 2: 运行状态测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_pipeline_state.py -q`  
Expected: FAIL with missing pipeline module

- [ ] **Step 3: 实现枚举和显式转移表**

```python
class PipelineState(StrEnum):
    CREATED = "CREATED"
    DATA_READY = "DATA_READY"
    DATA_FAILED = "DATA_FAILED"
    MODEL_NOT_CONFIGURED = "MODEL_NOT_CONFIGURED"
    RESEARCH_READY = "RESEARCH_READY"
    RESEARCH_FAILED = "RESEARCH_FAILED"
    PROPOSAL_READY = "PROPOSAL_READY"
    RISK_PASSED = "RISK_PASSED"
    RISK_BLOCKED = "RISK_BLOCKED"
    WAITING_APPROVAL = "WAITING_APPROVAL"
    APPROVAL_REJECTED = "APPROVAL_REJECTED"
    APPROVAL_EXPIRED = "APPROVAL_EXPIRED"
    PAPER_EXECUTED = "PAPER_EXECUTED"
    LIVE_SUBMITTED = "LIVE_SUBMITTED"
    LIVE_BLOCKED = "LIVE_BLOCKED"
    EXECUTION_FAILED = "EXECUTION_FAILED"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    RECONCILED = "RECONCILED"


class ExecutionOrderStatus(StrEnum):
    SUBMITTING = "SUBMITTING"
    SUBMITTED = "SUBMITTED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCEL_PENDING = "CANCEL_PENDING"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class PipelineRun:
    run_id: str
    state: PipelineState
    security_key: str
    account_id: str
    mode: ExecutionMode
    market_evidence_id: str | None = None
    research_decision_id: str | None = None
    proposal_id: str | None = None
    verdict_id: str | None = None
    order_id: str | None = None
    error_code: str | None = None


ALLOWED_TRANSITIONS: dict[PipelineState, frozenset[PipelineState]] = {
    PipelineState.CREATED: frozenset({PipelineState.DATA_READY, PipelineState.DATA_FAILED}),
    PipelineState.DATA_READY: frozenset({
        PipelineState.RESEARCH_READY,
        PipelineState.MODEL_NOT_CONFIGURED,
        PipelineState.RESEARCH_FAILED,
    }),
    PipelineState.RESEARCH_READY: frozenset({PipelineState.PROPOSAL_READY}),
    PipelineState.PROPOSAL_READY: frozenset({
        PipelineState.RISK_PASSED,
        PipelineState.RISK_BLOCKED,
    }),
    PipelineState.RISK_PASSED: frozenset({PipelineState.WAITING_APPROVAL}),
    PipelineState.WAITING_APPROVAL: frozenset({
        PipelineState.PAPER_EXECUTED,
        PipelineState.LIVE_SUBMITTED,
        PipelineState.APPROVAL_REJECTED,
        PipelineState.APPROVAL_EXPIRED,
        PipelineState.LIVE_BLOCKED,
        PipelineState.EXECUTION_FAILED,
    }),
    PipelineState.PAPER_EXECUTED: frozenset({PipelineState.RECONCILED}),
    PipelineState.LIVE_SUBMITTED: frozenset({
        PipelineState.RECONCILED,
        PipelineState.RECONCILIATION_REQUIRED,
    }),
}
```

- [ ] **Step 4: 写入模拟幂等与事务测试**

```python
def test_重复模拟订单只成交一次(tmp_path: Path) -> None:
    store = initialized_store(tmp_path)
    service = PaperExecutionService(store)
    service.create_account("paper-main", Decimal("100000"), NOW)
    request = approved_request(account_id="paper-main", mode=ExecutionMode.PAPER)
    first = service.submit(request, NOW)
    second = service.submit(request, NOW)
    assert first == second
    assert store.count_fills(request.idempotency_key) == 1
    assert store.get_paper_account("paper-main").cash == Decimal("99000")
```

- [ ] **Step 5: 运行模拟测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_paper_execution.py -q`  
Expected: FAIL with missing `PaperExecutionService`

- [ ] **Step 6: 增加账本表**

在单次迁移中创建 `paper_accounts`、`paper_positions`、`orders`、`fills`、`approvals`、`pipeline_runs` 和 `pipeline_attempts`。`orders.idempotency_key` 必须唯一；所有外键开启。

- [ ] **Step 7: 实现事务模拟撮合**

`submit()` 使用 `BEGIN IMMEDIATE`。若幂等键已存在，返回原回执。买入时：

```python
amount = proposal.limit_price * proposal.quantity
if amount > account.cash:
    raise PermissionError("INSUFFICIENT_CASH")
new_cash = account.cash - amount
```

成交价等于已审批限价；新增买入数量不增加当日 `available_to_sell`。卖出校验可卖数量并增加现金。订单、成交、账户和持仓必须在同一事务提交。

- [ ] **Step 8: 运行 Task 4 测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit\test_pipeline_state.py tests\integration\test_paper_execution.py -q
```

Expected: PASS

- [ ] **Step 9: 提交 Task 4**

```powershell
git add src/bagholder/domain/pipeline.py src/bagholder/application/paper_execution_service.py src/bagholder/infrastructure/sqlite_store.py tests/unit/test_pipeline_state.py tests/integration/test_paper_execution.py
git commit -m "feat: add pipeline states and paper ledger"
```

---

### Task 5: 本地审批与真实 vn.py Gateway

**Files:**
- Modify: `src/bagholder/contracts/live_trading.py`
- Modify: `src/bagholder/domain/broker.py`
- Modify: `src/bagholder/application/approval_service.py`
- Modify: `src/bagholder/application/execution_service.py`
- Create: `src/bagholder/integrations/vnpy_client.py`
- Create: `src/bagholder/adapters/broker/vnpy_gateway.py`
- Modify: `integrations/vnpy/server.py`
- Modify: `src/bagholder/testing/fake_gateway.py`
- Test: `tests/integration/test_live_execution_gate.py`
- Test: `tests/contract/test_vnpy_gateway_contract.py`

**Interfaces:**
- Produces: `ApprovalService.approve_local(...) -> OrderApproval`
- Produces: `LiveExecutionGate.validate(...)`
- Produces: `ExecutionRouter.execute(request, live_context, now) -> BrokerOrderReceipt`
- Produces: `VnpyClient.request(command, payload) -> dict[str, object]`
- Produces: `VnpyBrokerGateway.submit(request) -> BrokerOrderReceipt`

- [ ] **Step 1: 写入实盘硬阻断测试**

```python
def test_live_不可用时绝不调用模拟执行器() -> None:
    paper = RecordingPaperExecutor()
    live = RecordingLiveExecutor()
    router = ExecutionRouter(paper=paper, live=live)
    with pytest.raises(LiveBlockedError, match="BROKER_API_UNAVAILABLE"):
        router.execute(
            request=approved_live_request(),
            live_context=LiveGateContext(
                system_live_enabled=True,
                account_live_enabled=True,
                broker_api_state=BrokerApiState.API_UNAVAILABLE,
                supports_live_orders=False,
                reconciled=True,
                interactive_confirmation=True,
            ),
        )
    assert paper.calls == 0
    assert live.calls == 0
```

- [ ] **Step 2: 运行实盘门测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_live_execution_gate.py -q`  
Expected: FAIL with missing `ExecutionRouter`

- [ ] **Step 3: 实现本地审批和实盘门**

`approve_local()` 必须校验风控、提案有效期和匹配 ID。`LiveGateContext` 同时要求：

```python
if not context.system_live_enabled:
    raise LiveBlockedError("LIVE_DISABLED")
if not context.account_live_enabled:
    raise LiveBlockedError("ACCOUNT_LIVE_DISABLED")
if context.broker_api_state is not BrokerApiState.READY:
    raise LiveBlockedError("BROKER_API_UNAVAILABLE")
if not context.supports_live_orders:
    raise LiveBlockedError("BROKER_CAPABILITY_MISSING")
if not context.reconciled:
    raise LiveBlockedError("RECONCILIATION_REQUIRED")
if not context.interactive_confirmation:
    raise LiveBlockedError("LIVE_CONFIRMATION_REQUIRED")
```

分流只按 `request.proposal.mode`；不包含 fallback 分支。

- [ ] **Step 4: 写入 vn.py 签名与插件分发契约测试**

测试启动 `integrations/vnpy/server.py --request-once --gateway-plugin bagholder.testing.fake_gateway:create_gateway`，发送 HMAC 签名 `SUBMIT_ORDER`，断言返回固定券商订单号；重复 nonce 必须被拒绝。

- [ ] **Step 5: 运行 vn.py 契约测试并确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\contract\test_vnpy_gateway_contract.py -q`  
Expected: FAIL because `--request-once` is unsupported

- [ ] **Step 6: 实现 VnpyClient 与 VnpyBrokerGateway**

`VnpyClient` 使用现有 `AuthenticatedProtocol.sign()`，通过注入的传输发送 JSON。`VnpyBrokerGateway` 将 `SUBMIT_ORDER`、`CANCEL_ORDER`、`QUERY_FUNDS`、`QUERY_POSITIONS`、`QUERY_ORDERS` 和 `QUERY_TRADES` 映射为通用领域模型。

- [ ] **Step 7: 实现 vn.py 单请求节点**

节点只接受：

```text
HEALTH
SUBMIT_ORDER
CANCEL_ORDER
QUERY_FUNDS
QUERY_POSITIONS
QUERY_ORDERS
QUERY_TRADES
```

插件参数格式固定为 `允许的模块名:create_gateway`。加载前校验模块前缀白名单；私有生产插件必须通过配置声明包名、版本和 SHA-256。节点验证签名后才调用插件，响应 JSON 不包含凭据。

- [ ] **Step 8: 运行 Task 5 测试和原有执行测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\integration\test_live_execution_gate.py tests\contract\test_vnpy_gateway_contract.py tests\integration\test_execution.py tests\unit\test_vnpy_protocol.py -q
```

Expected: PASS

- [ ] **Step 9: 提交 Task 5**

```powershell
git add src/bagholder/contracts/live_trading.py src/bagholder/domain/broker.py src/bagholder/application/approval_service.py src/bagholder/application/execution_service.py src/bagholder/integrations/vnpy_client.py src/bagholder/adapters/broker/vnpy_gateway.py integrations/vnpy/server.py src/bagholder/testing/fake_gateway.py tests/integration/test_live_execution_gate.py tests/contract/test_vnpy_gateway_contract.py
git commit -m "feat: add gated vnpy live execution"
```

---

### Task 6: 端到端 PipelineService

**Files:**
- Create: `src/bagholder/application/pipeline_service.py`
- Modify: `src/bagholder/infrastructure/sqlite_store.py`
- Test: `tests/integration/test_pipeline.py`

**Interfaces:**
- Consumes: market, research, signal, risk, approval, paper and live services
- Produces: `PipelineService.run(...) -> PipelineRun`
- Produces: `PipelineService.approve(run_id, mode, confirmation, now) -> PipelineRun`
- Produces: `PipelineService.show(run_id) -> PipelineRun`

- [ ] **Step 1: 写入端到端等待审批测试**

```python
def test_pipeline_完成研究风控后停在人工审批(tmp_path: Path) -> None:
    platform = build_test_platform(tmp_path, action="BUY", confidence="0.80")
    platform.paper.create_account("paper-main", Decimal("1000000"), NOW)
    run = platform.pipeline.run(
        security_key="CN:600519.SH",
        account_id="paper-main",
        analysis_date=date(2026, 7, 24),
        mode=ExecutionMode.PAPER,
        now=NOW,
    )
    assert run.state is PipelineState.WAITING_APPROVAL
    assert run.market_evidence_id
    assert run.research_decision_id
    assert platform.store.count_orders() == 0
```

- [ ] **Step 2: 运行测试并确认因 PipelineService 不存在而失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_pipeline.py -q`  
Expected: FAIL with missing `PipelineService`

- [ ] **Step 3: 实现 run() 状态推进**

顺序固定：

```python
run = store.create_pipeline_run(...)
market = market_service.fetch(...)
store.transition(run.id, PipelineState.DATA_READY, market_evidence_id=market.evidence_id)
decision = research_service.run(...)
store.transition(run.id, PipelineState.RESEARCH_READY, decision_id=str(decision.decision_id))
proposal = signal_service.propose(...)
store.transition(run.id, PipelineState.PROPOSAL_READY, proposal_id=str(proposal.proposal_id))
verdict = risk_service.evaluate(proposal, context)
if not verdict.allowed:
    return store.transition(run.id, PipelineState.RISK_BLOCKED, error_code="RISK_BLOCKED")
store.transition(run.id, PipelineState.RISK_PASSED, verdict_id=str(verdict.verdict_id))
return store.transition(run.id, PipelineState.WAITING_APPROVAL)
```

每次转移和外部尝试都追加审计记录；异常映射到设计文档定义的稳定状态。

- [ ] **Step 4: 写入审批后模拟成交和实盘阻断测试**

```python
def test_pipeline_审批后模拟成交且重复审批不重复下单(platform) -> None:
    waiting = create_waiting_run(platform, ExecutionMode.PAPER)
    first = platform.pipeline.approve(waiting.run_id, ExecutionMode.PAPER, True, NOW)
    second = platform.pipeline.approve(waiting.run_id, ExecutionMode.PAPER, True, NOW)
    assert first.order_id == second.order_id
    assert platform.store.count_fills_for_order(first.order_id) == 1


def test_pipeline_live_不可用时进入阻断且无模拟成交(platform) -> None:
    waiting = create_waiting_run(platform, ExecutionMode.LIVE)
    blocked = platform.pipeline.approve(waiting.run_id, ExecutionMode.LIVE, True, NOW)
    assert blocked.state is PipelineState.LIVE_BLOCKED
    assert platform.store.count_fills() == 0
```

- [ ] **Step 5: 实现 approve() 与恢复幂等**

审批模式必须等于原提案模式。PAPER 调用 `PaperExecutionService`；LIVE 调用执行路由器和 `LiveExecutionService`。重复审批返回已保存终态，不重新调用执行器。未知实盘状态写入 `RECONCILIATION_REQUIRED`。

- [ ] **Step 6: 运行 Task 6 测试**

Run: `.\.venv\Scripts\python.exe -m pytest tests\integration\test_pipeline.py -q`  
Expected: PASS

- [ ] **Step 7: 提交 Task 6**

```powershell
git add src/bagholder/application/pipeline_service.py src/bagholder/infrastructure/sqlite_store.py tests/integration/test_pipeline.py
git commit -m "feat: orchestrate research to approved execution"
```

---

### Task 7: CLI、配置、真实数据冒烟与文档

**Files:**
- Modify: `src/bagholder/bootstrap.py`
- Modify: `.env.example`
- Modify: `README.md`
- Create: `tests/live/test_astock_market_data.py`
- Modify: `tests/unit/test_bootstrap.py`

**Interfaces:**
- Produces: `bagholder doctor`
- Produces: `bagholder paper account create|show`
- Produces: `bagholder market fetch`
- Produces: `bagholder research run`
- Produces: `bagholder pipeline run|approve|show`
- Produces: `bagholder order show`

- [ ] **Step 1: 写入 CLI 失败测试**

```python
def test_market_fetch_json_输出证据版本(tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("BAGHOLDER_HOME", str(tmp_path))
    monkeypatch.setenv("TRADINGAGENTS_PYTHON", sys.executable)
    monkeypatch.setenv("TRADINGAGENTS_RUNNER", str(FIXTURE_RUNNER))
    code = main([
        "market", "fetch", "CN:600519.SH",
        "--start", "2026-07-01",
        "--end", "2026-07-24",
        "--json",
    ])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["security_key"] == "CN:600519.SH"
    assert len(payload["sha256"]) == 64
```

- [ ] **Step 2: 运行 CLI 测试并确认命令不存在**

Run: `.\.venv\Scripts\python.exe -m pytest tests\unit\test_bootstrap.py -q`  
Expected: argparse rejects `market`

- [ ] **Step 3: 拆分 CLI 注册和依赖装配**

`bootstrap.py` 保留 `main()`，增加小型 `_build_parser()` 和 `_build_platform()`。运行目录：

```python
def _platform_home() -> Path:
    configured = os.getenv("BAGHOLDER_HOME")
    return Path(configured) if configured else Path.cwd() / "var"


def _build_store() -> SqlitePlatformStore:
    home = _platform_home()
    return SqlitePlatformStore(home / "platform.db", home / "evidence")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="bagholder")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("status")
    commands.add_parser("doctor")
    paper = commands.add_parser("paper").add_subparsers(dest="paper_command", required=True)
    paper.add_parser("account")
    market = commands.add_parser("market").add_subparsers(dest="market_command", required=True)
    market.add_parser("fetch")
    research = commands.add_parser("research").add_subparsers(
        dest="research_command", required=True
    )
    research.add_parser("run")
    pipeline = commands.add_parser("pipeline").add_subparsers(
        dest="pipeline_command", required=True
    )
    pipeline.add_parser("run")
    pipeline.add_parser("approve")
    pipeline.add_parser("show")
    order = commands.add_parser("order").add_subparsers(dest="order_command", required=True)
    order.add_parser("show")
    return parser
```

所有带 `--json` 的命令只向 stdout 输出一条 JSON；人类诊断写 stderr。`pipeline approve --mode LIVE --confirm-live` 必须检测 `sys.stdin.isatty()` 并要求用户输入完整账户、证券和数量；输入不匹配返回 `LIVE_CONFIRMATION_REQUIRED`。

- [ ] **Step 4: 更新环境示例**

```dotenv
TRADINGAGENTS_PYTHON=.runtime/tradingagents/Scripts/python.exe
TRADINGAGENTS_RUNNER=integrations/tradingagents/runner.py
TRADINGAGENTS_LLM_PROVIDER=openai
TRADINGAGENTS_MODEL=
TRADINGAGENTS_API_KEY=
TRADINGAGENTS_BACKEND_URL=
BAGHOLDER_HOME=var
BAGHOLDER_LIVE_ENABLED=false
TRADING_NODE_SECRET_REFERENCE=bagholder/vnpy-node
```

- [ ] **Step 5: 添加显式真实数据冒烟测试**

```python
pytestmark = pytest.mark.skipif(
    os.getenv("RUN_LIVE_DATA_TESTS") != "1",
    reason="仅在明确启用时访问公共 A 股数据源",
)


def test_600519_真实日线能固化为有效证据(tmp_path: Path) -> None:
    platform = build_live_data_platform(tmp_path)
    record = platform.market.fetch(
        security_key="CN:600519.SH",
        start_date=date(2026, 7, 1),
        end_date=date(2026, 7, 24),
        as_of=date(2026, 7, 24),
    )
    payload = platform.store.load_evidence(record.evidence_id)
    assert payload["records"]
    assert len(record.sha256) == 64
```

- [ ] **Step 6: 更新 README**

README 必须包含：

- 三个环境的安装命令；
- 模型环境变量；
- 模拟账户、行情、研究、管道、审批和查询示例；
- `RUN_LIVE_DATA_TESTS=1` 冒烟命令；
- 实盘双开关、二次确认、禁止降级；
- 中信和国泰海通当前 `API_UNAVAILABLE` 的原因；
- 接入私有 Gateway 所需 SDK、测试账户和验收清单。

- [ ] **Step 7: 运行全部自动测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: all deterministic tests pass; one live test skipped unless explicitly enabled

- [ ] **Step 8: 运行真实数据冒烟**

Run:

```powershell
$env:RUN_LIVE_DATA_TESTS='1'
.\.venv\Scripts\python.exe -m pytest tests\live\test_astock_market_data.py -q
Remove-Item Env:RUN_LIVE_DATA_TESTS
```

Expected: `600519` snapshot stored and test passes

- [ ] **Step 9: 运行静态检查和命令验收**

Run:

```powershell
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
.\.venv\Scripts\bagholder.exe doctor --json
.\.venv\Scripts\bagholder.exe status --json
```

Expected:

- Ruff all checks passed
- mypy no issues
- doctor reports main, TradingAgents and vn.py environments
- both live broker accounts remain `API_UNAVAILABLE`

- [ ] **Step 10: 提交 Task 7**

```powershell
git add src/bagholder/bootstrap.py .env.example README.md tests/live/test_astock_market_data.py tests/unit/test_bootstrap.py
git commit -m "feat: expose platform integration CLI"
```

---

### Task 8: 最终安全回归和交付检查

**Files:**
- Modify only files required by discovered failing tests

**Interfaces:**
- Consumes all prior tasks
- Produces verified installable project and evidence-backed status report

- [ ] **Step 1: 运行完整回归**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src
git diff --check
```

Expected: all pass

- [ ] **Step 2: 验证没有密钥泄漏**

```powershell
rg -n "(sk-[A-Za-z0-9_-]{16,}|API_KEY\\s*=\\s*[^\\s]|password\\s*=|broker.*token)" . `
  -g "!.git/**" -g "!.venv/**" -g "!.runtime/**" -g "!var/**"
```

Expected: only empty examples,字段名或测试占位符；无真实密钥。

- [ ] **Step 3: 验证安全阻断**

```powershell
.\.venv\Scripts\bagholder.exe status --json
.\.venv\Scripts\bagholder.exe pipeline approve 00000000-0000-0000-0000-000000000000 --mode LIVE --confirm-live --json
```

Expected: two brokers show `API_UNAVAILABLE`; invalid/nonexistent run cannot call Gateway or create PAPER fill.

- [ ] **Step 4: 检查提交范围**

```powershell
git status --short
git log --oneline --decorate -10
```

Expected: implementation commits contain only project integration files; no `.env`、`var/`、`.runtime/` 或 `.superpowers/`。

- [ ] **Step 5: 保持回归检查只读**

Task 8 不创建计划外提交。若发现失败，回到引入失败的对应任务，先补失败测试，再修复并使用该任务列出的精确文件清单提交；随后重新执行 Task 8 全部步骤。
