# 新浪与 Finnhub 多数据源行情接入 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立可注册的行情数据源能力，实现新浪 A 股 HTTP 行情适配器，并为 Finnhub 美股密钥配置预留安全边界。

**Architecture:** 核心服务只依赖 `MarketDataAdapter` 返回的规范化行情。新浪适配器只负责 HTTP 读取、代码映射和响应解析；存储、版本、新鲜度与桌面降级仍由本地服务统一负责。Finnhub 仅先登记为美股候选数据源，密钥只进入系统钥匙串。

**Tech Stack:** Python 3.12、标准库 `urllib`、Pydantic、DuckDB、Pytest、Hypothesis、PySide6。

## Global Constraints

- 项目代码、注释、文档字符串与说明使用简体中文。
- 任何行情均包含来源、市场时间、采集时间、数据版本和新鲜度。
- 新浪数据仅在市场时间可验证且 A 股数据年龄不超过 5 秒时标为实时；否则明确降级。
- 凭据仅存系统钥匙串；日志、备份、MCP、页面和普通导出不得暴露明文。
- 原始响应与规范化结果追加保存；第一阶段不连接券商、不下单、不自动交易。

---

### Task 1: 行情适配器协议与注册表

**Files:**
- Create: `src/stock_agent/adapters/market_data/base.py`
- Create: `src/stock_agent/adapters/market_data/registry.py`
- Test: `tests/contract/test_market_data_contract.py`

**Interfaces:** `SourceCapability(source_id, markets, credential_required, supports_realtime)`；`NormalizedQuote(..., source_id, market_time, collected_at, data_version)`；`MarketDataRegistry.register(adapter)`。

- [ ] **Step 1: 写失败测试**

```python
registry.register(FakeAdapter())
with pytest.raises(DuplicateSourceError):
    registry.register(FakeAdapter())
with pytest.raises(ValueError):
    NormalizedQuote(..., market_time=None)
```

- [ ] **Step 2: 运行并确认失败**

Run: `py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v`

Expected: `ModuleNotFoundError: stock_agent.adapters.market_data`。

- [ ] **Step 3: 最小实现**

```python
def register(self, adapter: MarketDataAdapter) -> None:
    source_id = adapter.capability.source_id
    if source_id in self._adapters:
        raise DuplicateSourceError(source_id)
    self._adapters[source_id] = adapter
```

- [ ] **Step 4: 运行并确认通过**

Run: `py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v`

- [ ] **Step 5: 提交**

Run: `git add src/stock_agent/adapters/market_data tests/contract/test_market_data_contract.py; git commit -m "feat: add market data adapter registry"`

### Task 2: 新鲜度与新浪代码规则

**Files:**
- Create: `src/stock_agent/domain/freshness.py`
- Create: `src/stock_agent/adapters/market_data/sina_codes.py`
- Test: `tests/property/test_freshness_rules.py`
- Test: `tests/failure/test_market_data_failures.py`

**Interfaces:** `classify_freshness(market, market_time, collected_at, is_open)`；`normalize_sina_code(instrument) -> str`。

- [ ] **Step 1: 写失败测试**

```python
assert classify_freshness(Market.CN, at, at + timedelta(seconds=5), True) == "REALTIME"
assert classify_freshness(Market.US, at, at + timedelta(seconds=16), True) == "NEAR_REALTIME"
with pytest.raises(UnsupportedSinaCodeError):
    normalize_sina_code(InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"))
```

- [ ] **Step 2: 运行并确认失败**

Run: `py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v`

- [ ] **Step 3: 最小实现**

```python
age = (collected_at - market_time).total_seconds()
limit = 5 if market is Market.CN else 15
return "REALTIME" if age <= limit else "NEAR_REALTIME"
```

补足 60 秒、15 分钟和 `CLOSED` 分支；仅接受 `CN` 的 `SSE`/`SZSE` 代码，并映射为 `sh`/`sz` 前缀。

- [ ] **Step 4: 运行并确认通过**

Run: `py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v`

- [ ] **Step 5: 提交**

Run: `git add src/stock_agent/domain/freshness.py src/stock_agent/adapters/market_data/sina_codes.py tests/property tests/failure; git commit -m "feat: enforce freshness and sina code rules"`

### Task 3: 新浪 HTTP 适配器与原始响应边界

**Files:**
- Create: `src/stock_agent/adapters/market_data/sina_adapter.py`
- Test: `tests/integration/test_single_market_daily_pipeline.py`
- Test: `tests/failure/test_market_data_failures.py`

**Interfaces:** `SinaHttpAdapter(http_get)`；`fetch_quotes(codes, collected_at)`；只请求 `http://hq.sinajs.cn/list={代码列表}`。

- [ ] **Step 1: 写失败测试**

```python
adapter = SinaHttpAdapter(lambda _: SAMPLE_SINA_RESPONSE.encode("gbk"))
quote = adapter.fetch_quotes(["sh600000"], collected_at)[0]
assert quote.source_id == "sina"
assert quote.market_time.tzinfo is not None
```

- [ ] **Step 2: 运行并确认失败**

Run: `py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py -v`

- [ ] **Step 3: 最小实现**

```python
url = f"http://hq.sinajs.cn/list={','.join(codes)}"
raw_text = self._http_get(url).decode("gbk")
return [self._parse_line(line, collected_at) for line in raw_text.splitlines() if line]
```

解析时拒绝缺名称、价格、日期或时间的行；市场时间必须使用 `Asia/Shanghai`，异常响应不生成报价。

- [ ] **Step 4: 运行并确认通过**

Run: `py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v`

- [ ] **Step 5: 提交**

Run: `git add src/stock_agent/adapters/market_data/sina_adapter.py tests/integration tests/failure; git commit -m "feat: add sina a-share market data adapter"`

### Task 4: 新浪/Finnhub 配置与证据

**Files:**
- Modify: `src/stock_agent/application/data_source_credential_service.py`
- Modify: `src/stock_agent/desktop/pages/data_source_page.py`
- Create: `docs/acceptance/data-source-selection.md`
- Test: `tests/contract/test_data_source_credentials.py`

**Interfaces:** 新浪是公开只读 A 股来源；Finnhub 是需钥匙串授权的美股候选来源；页面只展示来源状态、市场范围和降级说明。

- [ ] **Step 1: 写失败测试**

```python
authorization = service.configure(CredentialRegistration("finnhub", "test-secret"))
state = DataSourcePageState.from_authorization(authorization)
assert authorization.is_authorized
assert "test-secret" not in state.summary
```

- [ ] **Step 2: 运行并确认失败**

Run: `py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py -v`

- [ ] **Step 3: 最小实现与记录**

新增来源元数据；选择记录说明新浪不保证实时、Finnhub 未配置密钥时美股保持受限，且任何来源失去新鲜度时停止当前预测。

- [ ] **Step 4: 运行验证**

Run: `py -3.12 -m pytest -o addopts='' tests/contract/test_data_source_credentials.py tests/failure/test_credential_exposure.py -v`

- [ ] **Step 5: 全量门禁与提交**

Run: `py -3.12 -m pytest; py -3.12 -m ruff format --check src tests; py -3.12 -m ruff check src tests; py -3.12 tools/check_chinese_project_text.py .`

Expected: 全部通过，覆盖率不低于 80%。随后只勾选实际完成的 T034–T038 并提交：`git add specs/001-local-stock-agent/tasks.md docs/acceptance src tests; git commit -m "feat: configure sina and finnhub market sources"`。

## 自检

- 新浪供应商字段不会泄漏到核心服务或页面模型。
- 不存在把市场时间缺失的数据标为实时的路径。
- Finnhub 密钥只经 `KeyringCredentialStore` 保存，未配置时美股不显示为可用。
- 所有新代码均先有失败测试，且不包含券商或交易能力。
