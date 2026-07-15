# T034 复审包

## 提交

ff8d4fb test: 补强市场与桌面状态契约
3552f21 test: 补充市场与桌面状态契约

## 统计

 .superpowers/sdd/task-034-report.md           |  49 +++++
 tests/contract/test_desktop_state_contract.py |  65 ++++++
 tests/contract/test_market_data_contract.py   | 279 ++++++++++++++++++++++++++
 3 files changed, 393 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-034-report.md b/.superpowers/sdd/task-034-report.md
new file mode 100644
index 0000000..ff50aa3
--- /dev/null
+++ b/.superpowers/sdd/task-034-report.md
@@ -0,0 +1,49 @@
+# T034 契约测试报告
+
+## 新增用例
+
+- 市场状态查询：覆盖 A 股、港股、美股；要求返回市场标识、市场时区、交易日历状态、市场时点、采集时点、来源和新鲜度。
+- 市场状态校验：缺少市场时点或采集时点时拒绝构造状态。
+- 历史日线：要求包含证券身份、交易日、开高低收、成交量、复权口径、币种、来源、市场时点、采集时点、数据版本和新鲜度；拒绝将历史数据标为实时。
+- 历史日线查询：拒绝倒置日期范围及跨市场不匹配的证券代码。
+- 桌面状态：市场页和个股页均覆盖空、加载、离线、权限受限、过期、可用和恢复状态，并要求中文用户说明；离线或过期时禁用实时数据及当前预测；恢复后标明可用。
+
+## 失败验证
+
+执行命令：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/contract/test_desktop_state_contract.py -v
+```
+
+结果：测试收集阶段以预期的接口缺失失败，未执行任何生产代码实现。
+
+- `tests/contract/test_market_data_contract.py:19`：`ModuleNotFoundError: No module named 'stock_agent.application.market_service'`
+- `tests/contract/test_desktop_state_contract.py:5`：`ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`
+
+pytest 摘要：`collected 0 items / 2 errors`，进程退出码为 `2`。
+
+## 范围确认
+
+仅新增或修改契约测试与本报告；未修改 `src/`，未引入任何数据源 HTTP、券商、下单或交易能力。
+
+## 审查补强（第 2 次失败验证）
+
+本次仅增强测试，未修改 `src/`：
+
+- 历史日线成功结果逐字段断言证券身份及市场、交易日、开高低收、成交量、复权口径、币种、来源、市场时点、采集时点、数据版本和新鲜度原样保留；另按字段覆盖缺失和空值拒绝。
+- 桌面状态断言状态标识原样保留，并分别要求空、加载、离线、权限、过期、可用、恢复的中文语义关键字。
+- 市场边界锁定 CN、HK、US 的期望时区和允许交易日历状态，并分别覆盖有效代码、无效代码以及交易所、币种、代码不匹配拒绝。
+
+执行命令：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py tests/contract/test_desktop_state_contract.py -v
+```
+
+结果仍按预期在收集阶段失败：
+
+- `tests/contract/test_market_data_contract.py:19`：`ModuleNotFoundError: No module named 'stock_agent.application.market_service'`
+- `tests/contract/test_desktop_state_contract.py:5`：`ModuleNotFoundError: No module named 'stock_agent.desktop.pages.market_page'`
+
+pytest 摘要：`collected 0 items / 2 errors`，进程退出码为 `2`。另已执行 `py -3.12 -m py_compile`，两份测试文件语法检查通过。
diff --git a/tests/contract/test_desktop_state_contract.py b/tests/contract/test_desktop_state_contract.py
new file mode 100644
index 0000000..3f281b8
--- /dev/null
+++ b/tests/contract/test_desktop_state_contract.py
@@ -0,0 +1,65 @@
+"""验证市场页和个股页在数据不可用时的用户可见状态契约。"""
+
+import pytest
+
+from stock_agent.desktop.pages.market_page import MarketPageState
+from stock_agent.desktop.pages.security_page import SecurityPageState
+
+
+@pytest.mark.parametrize(
+    "state", ["EMPTY", "LOADING", "OFFLINE", "PERMISSION_DENIED", "STALE", "READY", "RECOVERED"]
+)
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+def test_页面状态具有中文用户可见说明(page_state: type[MarketPageState] | type[SecurityPageState], state: str) -> None:
+    """市场页和个股页的所有约定状态均应向用户提供非空中文说明。"""
+
+    view_state = page_state(status=state)
+
+    assert view_state.user_message
+    assert any("\u4e00" <= character <= "\u9fff" for character in view_state.user_message)
+
+
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+@pytest.mark.parametrize("state", ["OFFLINE", "STALE"])
+def test_离线或过期状态不得展示实时数据或允许当前预测(
+    page_state: type[MarketPageState] | type[SecurityPageState], state: str
+) -> None:
+    """离线和过期数据必须显式禁用实时展示及基于当前数据的预测入口。"""
+
+    view_state = page_state(status=state)
+
+    assert view_state.show_realtime_data is False
+    assert view_state.allow_current_prediction is False
+
+
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+def test_恢复状态表示页面可重新使用(page_state: type[MarketPageState] | type[SecurityPageState]) -> None:
+    """恢复状态应明确告诉界面数据已可用，避免沿用故障态限制。"""
+
+    view_state = page_state(status="RECOVERED")
+
+    assert view_state.is_available is True
+
+
+@pytest.mark.parametrize(
+    ("state", "keywords"),
+    [
+        ("EMPTY", ("空", "暂无")),
+        ("LOADING", ("加载",)),
+        ("OFFLINE", ("离线",)),
+        ("PERMISSION_DENIED", ("权限",)),
+        ("STALE", ("过期",)),
+        ("READY", ("可用",)),
+        ("RECOVERED", ("恢复",)),
+    ],
+)
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+def test_页面状态保留标识并提供对应中文语义(
+    page_state: type[MarketPageState] | type[SecurityPageState], state: str, keywords: tuple[str, ...]
+) -> None:
+    """每种页面状态必须可识别，且中文说明应表达该状态自身语义而非通用提示。"""
+
+    view_state = page_state(status=state)
+
+    assert view_state.status == state
+    assert any(keyword in view_state.user_message for keyword in keywords)
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
index e4e9a82..b882fe5 100644
--- a/tests/contract/test_market_data_contract.py
+++ b/tests/contract/test_market_data_contract.py
@@ -9,20 +9,21 @@ from stock_agent.adapters.market_data.base import (
     MarketDataAdapter,
     NormalizedQuote,
     SourceCapability,
 )
 from stock_agent.adapters.market_data.registry import (
     DuplicateSourceError,
     MarketDataRegistry,
     SourceCapabilityViolationError,
     UnknownSourceError,
 )
+from stock_agent.application.market_service import HistoricalDailyBar, MarketService, MarketStatus
 from stock_agent.contracts.common import Freshness
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
 def 市场证券身份(market: Market) -> InstrumentIdentity:
     """构造仅用于契约测试的完整证券身份。"""
 
     exchange, currency = {
         Market.CN: ("SSE", "CNY"),
         Market.HK: ("HKEX", "HKD"),
@@ -300,10 +301,288 @@ def test_注册表拒绝与所选来源能力不一致的整批行情(
                 )
             ]
 
     registry = MarketDataRegistry()
     registry.register(越界适配器())
 
     with pytest.raises(SourceCapabilityViolationError):
         registry.fetch_quotes(
             "演示来源", ["600000"], datetime(2026, 7, 14, 9, 30, tzinfo=UTC), Market.CN
         )
+
+
+@pytest.mark.parametrize("market", [Market.CN, Market.HK, Market.US])
+def test_市场状态查询返回跨市场必填时点与来源字段(market: Market) -> None:
+    """A股、港股和美股状态均应包含可审计的市场时点、采集时点、来源及新鲜度。"""
+
+    status = MarketService().get_market_status(market)
+
+    assert isinstance(status, MarketStatus)
+    assert status.market is market
+    assert status.market_timezone
+    assert status.trading_calendar_status
+    assert status.market_time.tzinfo is not None
+    assert status.collected_at.tzinfo is not None
+    assert status.source_id
+    assert status.freshness is not None
+
+
+@pytest.mark.parametrize("field", ["market_time", "collected_at"])
+def test_市场状态拒绝缺失市场时点或采集时点(field: str) -> None:
+    """缺少市场时点或采集时点的状态不可用于展示或后续决策。"""
+
+    payload = {
+        "market": Market.CN,
+        "market_timezone": "Asia/Shanghai",
+        "trading_calendar_status": "OPEN",
+        "market_time": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+        "source_id": "契约来源",
+        "freshness": Freshness(state="REALTIME", age_seconds=1),
+    }
+    payload[field] = None
+
+    with pytest.raises(ValidationError):
+        MarketStatus(**payload)
+
+
+def test_历史日线包含可追溯字段且不得标为实时() -> None:
+    """历史日线应保留身份、复权、币种、来源和版本信息，且不能伪装为实时行情。"""
+
+    bar = HistoricalDailyBar(
+        security_id=市场证券身份(Market.CN),
+        trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+        open=10.0,
+        high=10.5,
+        low=9.8,
+        close=10.2,
+        volume=1_000_000,
+        adjustment_basis="NONE",
+        currency="CNY",
+        source_id="契约来源",
+        market_time=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+        collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        data_version="日线版本-1",
+        freshness=Freshness(state="CLOSED", age_seconds=0),
+    )
+
+    assert bar.security_id.market is Market.CN
+    assert bar.trade_date.isoformat() == "2026-07-13"
+    assert bar.adjustment_basis == "NONE"
+    assert bar.freshness.state != "REALTIME"
+
+
+def test_历史日线拒绝实时新鲜度标记() -> None:
+    """历史日线不得以实时新鲜度状态绕过数据时点边界。"""
+
+    with pytest.raises(ValidationError):
+        HistoricalDailyBar(
+            security_id=市场证券身份(Market.CN),
+            trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+            open=10.0,
+            high=10.5,
+            low=9.8,
+            close=10.2,
+            volume=1_000_000,
+            adjustment_basis="NONE",
+            currency="CNY",
+            source_id="契约来源",
+            market_time=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            data_version="日线版本-1",
+            freshness=Freshness(state="REALTIME", age_seconds=0),
+        )
+
+
+def test_历史日线查询拒绝倒置日期范围() -> None:
+    """查询起始日期晚于结束日期时必须拒绝，避免返回含义不明的数据集。"""
+
+    with pytest.raises(ValueError):
+        MarketService().get_historical_daily_bars(
+            市场证券身份(Market.CN),
+            start_date=datetime(2026, 7, 14, tzinfo=UTC).date(),
+            end_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+        )
+
+
+def test_历史日线查询拒绝跨市场不匹配证券代码() -> None:
+    """美股身份不得使用A股六码代码，服务必须在查询边界拒绝跨市场代码。"""
+
+    cross_market_security = InstrumentIdentity(
+        market=Market.US,
+        exchange="NASDAQ",
+        display_code="600000",
+        currency="USD",
+    )
+
+    with pytest.raises(ValueError):
+        MarketService().get_historical_daily_bars(
+            cross_market_security,
+            start_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
+            end_date=datetime(2026, 7, 14, tzinfo=UTC).date(),
+        )
+
+
+def 历史日线有效载荷() -> dict[str, object]:
+    """构造完整历史日线载荷，供字段保留和拒绝场景共用。"""
+
+    return {
+        "security_id": 市场证券身份(Market.CN),
+        "trade_date": datetime(2026, 7, 13, tzinfo=UTC).date(),
+        "open": 10.0,
+        "high": 10.5,
+        "low": 9.8,
+        "close": 10.2,
+        "volume": 1_000_000,
+        "adjustment_basis": "NONE",
+        "currency": "CNY",
+        "source_id": "契约来源",
+        "market_time": datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+        "collected_at": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        "data_version": "日线版本-1",
+        "freshness": Freshness(state="CLOSED", age_seconds=0),
+    }
+
+
+def test_历史日线成功结果逐字段原样保留() -> None:
+    """服务模型不得在规范化时丢失、重写或推断历史日线的审计字段。"""
+
+    payload = 历史日线有效载荷()
+    bar = HistoricalDailyBar(**payload)
+
+    assert bar.security_id == payload["security_id"]
+    assert bar.security_id.market is Market.CN
+    assert bar.trade_date == payload["trade_date"]
+    assert bar.open == payload["open"]
+    assert bar.high == payload["high"]
+    assert bar.low == payload["low"]
+    assert bar.close == payload["close"]
+    assert bar.volume == payload["volume"]
+    assert bar.adjustment_basis == payload["adjustment_basis"]
+    assert bar.currency == payload["currency"]
+    assert bar.source_id == payload["source_id"]
+    assert bar.market_time == payload["market_time"]
+    assert bar.collected_at == payload["collected_at"]
+    assert bar.data_version == payload["data_version"]
+    assert bar.freshness == payload["freshness"]
+
+
+@pytest.mark.parametrize(
+    "field",
+    [
+        "security_id",
+        "trade_date",
+        "open",
+        "high",
+        "low",
+        "close",
+        "volume",
+        "adjustment_basis",
+        "currency",
+        "source_id",
+        "market_time",
+        "collected_at",
+        "data_version",
+        "freshness",
+    ],
+)
+def test_历史日线拒绝缺失任何必填字段(field: str) -> None:
+    """历史日线的每个审计、价格和时点字段均为必填，不能使用默认值补齐。"""
+
+    payload = 历史日线有效载荷()
+    payload.pop(field)
+
+    with pytest.raises(ValidationError):
+        HistoricalDailyBar(**payload)
+
+
+@pytest.mark.parametrize(
+    ("field", "invalid_value"),
+    [
+        ("security_id", None),
+        ("trade_date", None),
+        ("open", None),
+        ("high", None),
+        ("low", None),
+        ("close", None),
+        ("volume", None),
+        ("adjustment_basis", ""),
+        ("currency", ""),
+        ("source_id", ""),
+        ("market_time", None),
+        ("collected_at", None),
+        ("data_version", ""),
+        ("freshness", None),
+    ],
+)
+def test_历史日线拒绝必填字段空值(field: str, invalid_value: object) -> None:
+    """空值不能替代历史日线的必填字段，确保结果可追溯且可比较。"""
+
+    payload = 历史日线有效载荷()
+    payload[field] = invalid_value
+
+    with pytest.raises(ValidationError):
+        HistoricalDailyBar(**payload)
+
+
+@pytest.mark.parametrize(
+    ("market", "expected_timezone", "allowed_calendar_statuses"),
+    [
+        (Market.CN, "Asia/Shanghai", {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY"}),
+        (Market.HK, "Asia/Hong_Kong", {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY", "TYPHOON_SUSPENDED"}),
+        (Market.US, "America/New_York", {"OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS", "HOLIDAY"}),
+    ],
+)
+def test_各市场状态锁定时区与允许交易日历状态(
+    market: Market, expected_timezone: str, allowed_calendar_statuses: set[str]
+) -> None:
+    """市场状态必须按所属市场返回明确时区和受控的交易日历状态集合。"""
+
+    status = MarketService().get_market_status(market)
+
+    assert status.market is market
+    assert status.market_timezone == expected_timezone
+    assert status.trading_calendar_status in allowed_calendar_statuses
+
+
+@pytest.mark.parametrize(
+    "security_id",
+    [
+        InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="600000", currency="CNY"),
+        InstrumentIdentity(market=Market.HK, exchange="HKEX", display_code="00700", currency="HKD"),
+        InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="AAPL", currency="USD"),
+    ],
+)
+def test_各市场接受匹配的证券代码(security_id: InstrumentIdentity) -> None:
+    """A股、港股和美股的有效代码应通过市场服务的身份边界校验。"""
+
+    assert MarketService().validate_security_identity(security_id) == security_id
+
+
+@pytest.mark.parametrize(
+    "security_id",
+    [
+        InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="AAPL", currency="CNY"),
+        InstrumentIdentity(market=Market.HK, exchange="HKEX", display_code="600000", currency="HKD"),
+        InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="00700", currency="USD"),
+    ],
+)
+def test_各市场拒绝不符合本市场格式的证券代码(security_id: InstrumentIdentity) -> None:
+    """不同市场不得接受另一市场的代码格式，以免跨市场查询串线。"""
+
+    with pytest.raises(ValueError):
+        MarketService().validate_security_identity(security_id)
+
+
+@pytest.mark.parametrize(
+    "security_id",
+    [
+        InstrumentIdentity(market=Market.CN, exchange="HKEX", display_code="600000", currency="CNY"),
+        InstrumentIdentity(market=Market.HK, exchange="HKEX", display_code="00700", currency="USD"),
+        InstrumentIdentity(market=Market.US, exchange="NASDAQ", display_code="600000", currency="USD"),
+    ],
+)
+def test_市场身份拒绝交易所币种或代码不匹配(security_id: InstrumentIdentity) -> None:
+    """市场、交易所、币种和代码必须构成一致身份，任一不匹配均应拒绝。"""
+
+    with pytest.raises(ValueError):
+        MarketService().validate_security_identity(security_id)

```

