# TradingAgents Unified External-Data Cache Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a local SQLite cache for external data used by both full and lightweight TradingAgents research, with a stable store contract for future PostgreSQL/MySQL adapters.

**Architecture:** A file-local cache module owns cache keys, TTL, integrity checks, SQLite persistence, stale fallback, and a cached vendor router. The runner installs that router into the installed TradingAgents tool modules before either graph is created, making both research modes share one cache. Per-request tracking adds a risk flag when a stale response is used.

**Tech Stack:** Python 3.12 standard library (`sqlite3`, `hashlib`, `json`, `contextvars`, `pathlib`), pytest, existing isolated TradingAgents runtime.

## Global Constraints

- SQLite is the default, stored below `TRADINGAGENTS_CACHE_DIR/external-data/`; do not add a third-party dependency.
- Cache `get_stock_data`, `get_indicators`, `get_fundamentals`, `get_balance_sheet`, `get_cashflow`, `get_income_statement`, `get_profit_forecast`, and `get_industry_comparison` for both FULL and LIGHTWEIGHT.
- Cache only JSON-serializable external-tool responses and metadata. Do not cache credentials, headers, prompts, model output, evidence, orders, or trading data.
- Key uses tool name, stock code, canonical arguments, and vendor version. TTL: 24h for market/indicator/financial data; 1h for forecast/industry comparison.
- Fresh data wins. Upstream success atomically replaces data; verified expired data can be used only when upstream fails and must be marked stale.
- The `ExternalDataCacheStore` interface is the only storage dependency of the router. PostgreSQL/MySQL are future adapters with identical semantics.

## File Structure

- Create: `integrations/tradingagents/external_data_cache.py` — protocol, SQLite store, cache router, and stale tracker.
- Modify: `integrations/tradingagents/runner.py` — install the router and append stale risk flags for both modes.
- Create: `tests/unit/test_external_data_cache.py` — SQLite and routing contract tests.
- Modify: `tests/unit/test_tradingagents_runner.py` — runner cache integration tests.
- Modify: `src/bagholder/integrations/tradingagents_client.py`, `.env.example`, `README.md`, `tests/unit/test_tradingagents_client.py` — safe configuration propagation and user guidance.

---

### Task 1: Build the store contract and SQLite implementation

**Files:**
- Create: `integrations/tradingagents/external_data_cache.py`
- Create: `tests/unit/test_external_data_cache.py`

**Interfaces:**
- Produces `ExternalDataCacheStore` with `get(cache_key: str, now: datetime) -> CacheLookup | None`, `put(entry: CacheEntry) -> None`, `delete(cache_key: str) -> None`.
- Produces `SqliteExternalDataCacheStore(database_path: Path)`, `CacheEntry.create(tool_name, args, vendor_version, payload, fetched_at, expires_at)`, `CacheLookup`, `cache_key_for(tool_name, args, vendor_version)`, and `ttl_for(tool_name)`.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_store_reads_a_fresh_entry(tmp_path: Path) -> None:
    store = cache.SqliteExternalDataCacheStore(tmp_path / "external-data" / "cache.sqlite3")
    now = datetime(2026, 7, 27, tzinfo=UTC)
    entry = cache.CacheEntry.create(
        tool_name="get_fundamentals", args=("603986", "2026-07-24"),
        vendor_version="astock-v1", payload="fundamentals",
        fetched_at=now, expires_at=now + timedelta(hours=24),
    )
    store.put(entry)
    lookup = store.get(entry.cache_key, now + timedelta(minutes=1))
    assert lookup is not None and lookup.payload == "fundamentals" and not lookup.stale

def test_store_deletes_a_tampered_entry(tmp_path: Path) -> None:
    store = cache.SqliteExternalDataCacheStore(tmp_path / "cache.sqlite3")
    entry = cache.CacheEntry.create(
        tool_name="get_profit_forecast", args=("603986",), vendor_version="astock-v1",
        payload="original", fetched_at=datetime.now(UTC), expires_at=datetime.now(UTC),
    )
    store.put(entry)
    store._connection.execute("UPDATE external_data_cache_entries SET payload_json = ?", ('"tampered"',))
    assert store.get(entry.cache_key, datetime.now(UTC)) is None
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/test_external_data_cache.py -q`

Expected: FAIL because the cache module does not exist.

- [ ] **Step 3: Implement minimal types and SQLite schema**

```python
class ExternalDataCacheStore(Protocol):
    def get(self, cache_key: str, now: datetime) -> CacheLookup | None:
        raise NotImplementedError
    def put(self, entry: CacheEntry) -> None:
        raise NotImplementedError
    def delete(self, cache_key: str) -> None:
        raise NotImplementedError

class SqliteExternalDataCacheStore:
    def get(self, cache_key: str, now: datetime) -> CacheLookup | None:
        row = self._connection.execute(
            "SELECT payload_json, payload_sha256, expires_at FROM external_data_cache_entries WHERE cache_key = ?",
            (cache_key,),
        ).fetchone()
        if row is None:
            return None
        if sha256(row["payload_json"].encode()).hexdigest() != row["payload_sha256"]:
            self.delete(cache_key)
            return None
        return CacheLookup(payload=json.loads(row["payload_json"]), stale=now >= _parse(row["expires_at"]))
```

Create `external_data_cache_entries` with `cache_key` as primary key, canonical JSON payload, UTC timestamps, and payload SHA-256. Use a single SQLite `INSERT OR REPLACE` transaction for replacements. A JSON parse failure must delete the row and return a miss.

- [ ] **Step 4: Run focused tests and verify pass**

Run: `pytest tests/unit/test_external_data_cache.py -q`

Expected: PASS for fresh, expired, tampered, key and TTL behavior.

- [ ] **Step 5: Commit**

```bash
git add integrations/tradingagents/external_data_cache.py tests/unit/test_external_data_cache.py
git commit -m "feat: add SQLite external data cache store"
```

### Task 2: Add cached vendor routing and stale tracking

**Files:**
- Modify: `integrations/tradingagents/external_data_cache.py`
- Modify: `tests/unit/test_external_data_cache.py`

**Interfaces:**
- Consumes the Task 1 store contract.
- Produces `CachedVendorRouter(upstream, store, vendor_version)` callable as `router(tool_name: str, *args: object) -> str`.
- Produces `track_cache_usage() -> ContextManager[CacheUsageTracker]`; tracker exposes `stale_tool_names: set[str]`.

- [ ] **Step 1: Write failing routing tests**

```python
def test_router_uses_fresh_cache_without_a_second_call(tmp_path: Path) -> None:
    calls: list[tuple[object]] = []
    router = cache.CachedVendorRouter(
        lambda tool, *args: calls.append((tool, *args)) or "remote-result",
        cache.SqliteExternalDataCacheStore(tmp_path / "cache.sqlite3"), "astock-v1",
    )
    assert router("get_stock_data", "603986", "2026-07-01", "2026-07-24") == "remote-result"
    assert router("get_stock_data", "603986", "2026-07-01", "2026-07-24") == "remote-result"
    assert len(calls) == 1

def test_router_returns_stale_data_only_after_an_upstream_failure(tmp_path: Path) -> None:
    router = seeded_expired_router(tmp_path, upstream_error=TimeoutError())
    with cache.track_cache_usage() as tracker:
        assert router("get_profit_forecast", "603986") == "old-result"
    assert tracker.stale_tool_names == {"get_profit_forecast"}
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `pytest tests/unit/test_external_data_cache.py -q`

Expected: FAIL because `CachedVendorRouter` and `track_cache_usage` do not exist.

- [ ] **Step 3: Implement routing semantics**

```python
def __call__(self, tool_name: str, *args: object) -> str:
    if tool_name not in _CACHEABLE_TOOLS:
        return self._upstream(tool_name, *args)
    lookup = self._store.get(cache_key_for(tool_name, args, self._vendor_version), datetime.now(UTC))
    if lookup is not None and not lookup.stale:
        return cast(str, lookup.payload)
    try:
        result = self._upstream(tool_name, *args)
    except Exception:
        if lookup is None:
            raise
        _current_tracker().mark_stale(tool_name)
        return cast(str, lookup.payload)
    if isinstance(result, str):
        self._store.put(CacheEntry.create(
            tool_name=tool_name, args=args, vendor_version=self._vendor_version, payload=result,
            fetched_at=datetime.now(UTC), expires_at=datetime.now(UTC) + ttl_for(tool_name),
        ))
    return result
```

Serialize all arguments with canonical JSON (`ensure_ascii=False`, compact separators), derive stock code from the first argument for the approved tools, and bypass cache for unexpected non-string upstream outputs. Test no-cache failure propagation and both TTL classes.

- [ ] **Step 4: Run focused tests and verify pass**

Run: `pytest tests/unit/test_external_data_cache.py -q`

Expected: PASS for cache hit, refresh, stale fallback, upstream failure without cache, integrity, and TTL.

- [ ] **Step 5: Commit**

```bash
git add integrations/tradingagents/external_data_cache.py tests/unit/test_external_data_cache.py
git commit -m "feat: cache TradingAgents vendor responses"
```

### Task 3: Use the same cache in full and lightweight graphs

**Files:**
- Modify: `integrations/tradingagents/runner.py`
- Modify: `tests/unit/test_tradingagents_runner.py`

**Interfaces:**
- Consumes `CachedVendorRouter`, `SqliteExternalDataCacheStore`, and `track_cache_usage`.
- Produces `_install_external_data_cache() -> None` and `_append_stale_risk_flags(result: dict[str, object], stale_tool_names: set[str]) -> dict[str, object]`.

- [ ] **Step 1: Write failing runner tests**

```python
def test_full_research_marks_stale_data(monkeypatch) -> None:
    runner = _runner()
    monkeypatch.setattr(runner, "_install_external_data_cache", lambda: None)
    monkeypatch.setattr(runner, "track_cache_usage", fake_tracker_with({"get_industry_comparison"}))
    monkeypatch.setattr(runner, "TradingAgentsGraph", FakeFullGraph)
    result = runner._run_full_research(_payload())
    assert "外部数据过期回退：get_industry_comparison" in result["risk_flags"]

def test_lightweight_research_installs_the_shared_cache(monkeypatch) -> None:
    installed: list[bool] = []
    monkeypatch.setattr(runner, "_install_external_data_cache", lambda: installed.append(True))
    configure_fake_lightweight_graph(monkeypatch, runner)
    runner._run_lightweight_research(_payload())
    assert installed == [True]
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `pytest tests/unit/test_tradingagents_runner.py -q`

Expected: FAIL because cache installation and stale flag integration do not exist.

- [ ] **Step 3: Install the router before graph construction**

```python
def _install_external_data_cache() -> None:
    from tradingagents.agents.utils import core_stock_tools, fundamental_data_tools
    from tradingagents.agents.utils import signal_data_tools, technical_indicators_tools
    from tradingagents.dataflows.interface import route_to_vendor
    router = CachedVendorRouter(route_to_vendor, _cache_store(), _vendor_version())
    for module in (core_stock_tools, fundamental_data_tools, signal_data_tools, technical_indicators_tools):
        module.route_to_vendor = router
```

Make installation idempotent per subprocess, retaining the original vendor function to prevent wrapper-on-wrapper installation. Call it before `TradingAgentsGraph(debug=False, config=_model_config(payload))` in FULL and before `_build_lightweight_graph(payload)` in LIGHTWEIGHT. Scope each graph call in `track_cache_usage()`. Append one deterministic flag, `外部数据过期回退：<tool>`, per stale tool while retaining all existing flags and leaving action, confidence, model version and reports untouched.

- [ ] **Step 4: Run runner tests and verify pass**

Run: `pytest tests/unit/test_tradingagents_runner.py -q`

Expected: PASS; both modes use the same installer and stale use is visible in `risk_flags`.

- [ ] **Step 5: Commit**

```bash
git add integrations/tradingagents/runner.py tests/unit/test_tradingagents_runner.py
git commit -m "feat: share external cache across research modes"
```

### Task 4: Forward settings, document operation, and verify

**Files:**
- Modify: `src/bagholder/integrations/tradingagents_client.py`
- Modify: `.env.example`
- Modify: `README.md`
- Modify: `tests/unit/test_tradingagents_client.py`

**Interfaces:**
- Produces forwarded `TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND=sqlite` and `TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION=tradingagents-astock-0.3.0-d55820c` settings.

- [ ] **Step 1: Write the failing forwarding test**

```python
def test_safe_environment_forwards_cache_settings(monkeypatch) -> None:
    monkeypatch.setenv("TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND", "sqlite")
    monkeypatch.setenv("TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION", "astock-v1")
    environment = TradingAgentsClient._safe_environment()
    assert environment["TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND"] == "sqlite"
    assert environment["TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION"] == "astock-v1"
```

- [ ] **Step 2: Run focused test and verify failure**

Run: `pytest tests/unit/test_tradingagents_client.py::test_safe_environment_forwards_cache_settings -q`

Expected: FAIL because the fields are not allowlisted.

- [ ] **Step 3: Add settings and documentation**

```dotenv
TRADINGAGENTS_CACHE_DIR=
TRADINGAGENTS_EXTERNAL_DATA_CACHE_BACKEND=sqlite
TRADINGAGENTS_EXTERNAL_DATA_CACHE_VENDOR_VERSION=tradingagents-astock-0.3.0-d55820c
```

Validate only `sqlite` in this release. Explain that PostgreSQL/MySQL are future adapters behind the same store interface, not active connection options.

- [ ] **Step 4: Run complete verification**

Run: `pytest tests/unit/test_tradingagents_client.py tests/unit/test_external_data_cache.py tests/unit/test_tradingagents_runner.py -q`

Expected: PASS.

Run: `pytest -q`

Expected: PASS with only the existing live-data skip.

Run: `ruff check .`

Expected: `All checks passed!`.

Run: `mypy src`

Expected: `Success: no issues found`.

Run: `.runtime/tradingagents/Scripts/python.exe -m py_compile integrations/tradingagents/runner.py integrations/tradingagents/external_data_cache.py`

Expected: exit code 0.

Run: `git diff --check`

Expected: exit code 0.

- [ ] **Step 5: Commit**

```bash
git add .env.example README.md src/bagholder/integrations/tradingagents_client.py tests/unit/test_tradingagents_client.py
git commit -m "docs: configure TradingAgents external cache"
```

## Self-Review

- Tasks 1–2 cover SQLite, interface isolation, TTL, SHA-256, and stale fallback.
- Task 3 applies the router to both approved research modes and exposes stale use as risk data.
- Task 4 covers safe configuration propagation, documentation, isolated-runtime compilation, and full verification.
