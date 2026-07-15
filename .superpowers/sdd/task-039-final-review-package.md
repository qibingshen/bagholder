# T039 最终复审包

## 提交

92299f5 fix: strengthen market service fact boundaries

## 统计

 .superpowers/sdd/task-039-fix-report.md       |  57 ++++++++++++++
 src/stock_agent/application/market_service.py |  20 +++--
 src/stock_agent/domain/market.py              |  30 ++++++++
 tests/contract/test_market_data_contract.py   | 102 ++++++++++++++++++++++----
 tests/failure/test_market_data_failures.py    |  46 +++++++++---
 5 files changed, 224 insertions(+), 31 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-039-fix-report.md b/.superpowers/sdd/task-039-fix-report.md
new file mode 100644
index 0000000..de416ee
--- /dev/null
+++ b/.superpowers/sdd/task-039-fix-report.md
@@ -0,0 +1,57 @@
+# T039 独立审查修复报告
+
+## 修复范围
+
+- `resolve_security_identity` 改为返回 `InstrumentCatalogEntry`，保留 `InstrumentIdentity`、`source_id`、`collected_at` 与 `data_version`，不再把目录事实降级为裸身份。
+- `MarketStatus.market_time` 和 `HistoricalDailyBar.market_time` 必须使用所属市场的 IANA 时区：CN 为 `Asia/Shanghai`，HK 为 `Asia/Hong_Kong`，US 为 `America/New_York`。历史日线同时校验交易日等于该市场时间的本地日期。
+- `InstrumentIdentity` 在公开构造时执行完整市场、交易所、币种和代码格式校验；新增 `InstrumentIdentityInput` 作为原始输入 DTO，仅在失败场景收集后通过 `to_identity()` 转换并统一拒绝无效输入。
+- 显式传入空 `instruments` 时保持为空目录，解析返回明确的目录缺失错误，不回退内置样例。
+
+## TDD 记录
+
+先新增目录解析溯源、历史日线 IANA 时区、本地交易日和原始市场标识的失败测试。红灯命令与结果：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -k '目录解析入口 or IANA or 显式空证券目录' -v
+```
+
+结果为 2 项预期失败：解析入口返回 `InstrumentIdentity` 而非目录事实；历史日线接受 UTC 市场时间。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '证券身份拒绝市场交易所或币种不一致' -v
+```
+
+结果为 4 项预期失败：无效市场、交易所或币种组合可直接构造 `InstrumentIdentity`。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '非正式市场标识' -v
+```
+
+结果为 1 项预期失败：字符串 `"CN"` 可绕过 `Market` 枚举校验。
+
+## 验证结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
+```
+
+结果：`85 passed`。
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '新浪代码规范化拒绝不支持的有效市场 or 原始证券输入转换 or 证券身份拒绝市场交易所或币种不一致 or 未带市场标识的非唯一显示代码' -v
+```
+
+结果：`12 passed, 39 deselected`。
+
+```powershell
+py -3.12 -m ruff format --check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py
+py -3.12 -m ruff check src/stock_agent/application/market_service.py src/stock_agent/domain/market.py tests/contract/test_market_data_contract.py tests/failure/test_market_data_failures.py
+py -3.12 tools/check_chinese_project_text.py src
+git diff --check
+```
+
+结果：均通过。
+
+## 关注项
+
+完整运行 `tests/failure/test_market_data_failures.py` 的结果为 `42 passed, 9 failed`。失败项均位于当前预测可用性与公司行动/复权历史能力，涉及 `is_usable_for_current_prediction` 未拒绝不可用状态，以及 `CompanyAction`/`require_company_actions_for_adjustment` 尚未实现的接口；不属于本次 T039 市场目录、状态和日线查询修复范围。
diff --git a/src/stock_agent/application/market_service.py b/src/stock_agent/application/market_service.py
index edbb7fe..cbc0dea 100644
--- a/src/stock_agent/application/market_service.py
+++ b/src/stock_agent/application/market_service.py
@@ -36,20 +36,21 @@ class MarketStatus(BaseModel):
         allowed_statuses = {
             Market.CN: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY"},
             Market.HK: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY", "TYPHOON_SUSPENDED"},
             Market.US: {"OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS", "HOLIDAY"},
         }
         if self.market_timezone != self.market.timezone:
             raise ValueError("市场时区必须与所属市场一致")
         if self.trading_calendar_status not in allowed_statuses[self.market]:
             raise ValueError("交易日历状态不受该市场支持")
         _require_aware_time(self.market_time, "市场时间")
+        _require_market_timezone(self.market_time, self.market, "市场时间")
         _require_aware_time(self.collected_at, "采集时间")
         if self.market_time > self.collected_at:
             raise ValueError("市场时间不能晚于采集时间")
         return self
 
 
 class HistoricalDailyBar(BaseModel):
     """保存历史日线的价格、复权与溯源事实，明确禁止实时标签。"""
 
     security_id: InstrumentIdentity
@@ -65,25 +66,28 @@ class HistoricalDailyBar(BaseModel):
     market_time: datetime
     collected_at: datetime
     data_version: str = Field(min_length=1)
     freshness: Freshness
 
     @model_validator(mode="after")
     def 验证历史日线事实(self) -> HistoricalDailyBar:
         """拒绝缺乏可追溯性、币种错配或伪装为实时的历史数据。"""
 
         _require_aware_time(self.market_time, "市场时间")
+        _require_market_timezone(self.market_time, self.security_id.market, "市场时间")
         _require_aware_time(self.collected_at, "采集时间")
         if self.market_time > self.collected_at:
             raise ValueError("市场时间不能晚于采集时间")
         if self.currency != self.security_id.currency:
             raise ValueError("历史日线币种必须与证券身份一致")
+        if self.trade_date != self.market_time.date():
+            raise ValueError("交易日必须与市场时间的本地日期一致")
         if self.freshness.state == "REALTIME":
             raise ValueError("历史日线不得标记为实时行情")
         return self
 
 
 class InstrumentCatalogEntry(BaseModel):
     """保存证券目录身份的本地来源、采集时点和版本。"""
 
     security_id: InstrumentIdentity
     source_id: str = Field(min_length=1)
@@ -140,26 +144,24 @@ class MarketService:
             return self._market_statuses[market]
         except KeyError as error:
             raise ValueError("缺少该市场的本地日历状态或采集时间") from error
 
     def resolve_security_identity(
         self,
         display_code: str,
         *,
         market: Market | None = None,
         exchange: str | None = None,
-    ) -> InstrumentIdentity:
-        """从本地目录解析证券；显示代码不唯一时绝不猜测市场。"""
+    ) -> InstrumentCatalogEntry:
+        """从本地目录解析可追溯证券事实，显示代码不唯一时绝不猜测市场。"""
 
-        return self.get_instrument_catalog_entry(
-            display_code, market=market, exchange=exchange
-        ).security_id
+        return self.get_instrument_catalog_entry(display_code, market=market, exchange=exchange)
 
     def get_instrument_catalog_entry(
         self,
         display_code: str,
         *,
         market: Market | None = None,
         exchange: str | None = None,
     ) -> InstrumentCatalogEntry:
         """查询可追溯的本地证券目录事实，非唯一代码必须指定限定条件。"""
 
@@ -245,10 +247,18 @@ def _catalog_entries_from_instruments(
         )
         for security_id in instruments
     )
 
 
 def _require_aware_time(value: datetime, label: str) -> None:
     """确保审计时间含有时区，避免把不同市场本地时间混为同一时点。"""
 
     if value.tzinfo is None or value.utcoffset() is None:
         raise ValueError(f"{label}必须包含时区")
+
+
+def _require_market_timezone(value: datetime, market: Market, label: str) -> None:
+    """确保市场时点使用对应 IANA 时区，避免以相同偏移误解本地日期。"""
+
+    timezone = value.tzinfo
+    if not isinstance(timezone, ZoneInfo) or timezone.key != market.timezone:
+        raise ValueError(f"{label}必须使用 {market.timezone} 市场时区")
diff --git a/src/stock_agent/domain/market.py b/src/stock_agent/domain/market.py
index 389edea..5f44c54 100644
--- a/src/stock_agent/domain/market.py
+++ b/src/stock_agent/domain/market.py
@@ -35,28 +35,49 @@ class InstrumentIdentity:
     market: Market
     exchange: str
     display_code: str
     currency: str
 
     def __post_init__(self) -> None:
         """拒绝不完整身份，避免供应商代码直接混入业务主键。"""
 
         if not self.exchange or not self.display_code or not self.currency:
             raise MarketRuleError("证券身份必须包含交易所、显示代码和币种")
+        validate_instrument_identity(self)
 
     @property
     def market_timezone(self) -> str:
         """提供证券所属市场的时间边界。"""
 
         return self.market.timezone
 
 
+@dataclass(frozen=True, slots=True)
+class InstrumentIdentityInput:
+    """保存尚未通过市场规则校验的原始证券输入，仅供边界层收集失败原因。"""
+
+    market: Market
+    exchange: str
+    display_code: str
+    currency: str
+
+    def to_identity(self) -> InstrumentIdentity:
+        """将原始输入转换为已校验证券身份，不允许绕过正式构造规则。"""
+
+        return InstrumentIdentity(
+            market=self.market,
+            exchange=self.exchange,
+            display_code=self.display_code,
+            currency=self.currency,
+        )
+
+
 class CurrencyComparison:
     """只在同币种或给定预测时点可用汇率时计算跨市场金额比较。"""
 
     @staticmethod
     def compare(
         left: float,
         left_currency: str,
         right: float,
         right_currency: str,
         exchange_rate: float | None,
@@ -91,20 +112,29 @@ def resolve_instrument_identity(
     if not matched:
         raise MarketRuleError("本地证券目录不存在匹配身份")
     if len(matched) != 1:
         raise MarketRuleError("显示代码非唯一，必须提供市场或交易所")
     return validate_instrument_identity(matched[0])
 
 
 def validate_instrument_identity(security_id: InstrumentIdentity) -> InstrumentIdentity:
     """验证既有身份的市场、交易所、币种与代码格式组合。"""
 
+    if not isinstance(security_id, InstrumentIdentity):
+        raise MarketRuleError("证券身份无效")
+    if not isinstance(security_id.market, Market):
+        raise MarketRuleError("证券市场必须使用正式市场标识")
+    if not all(
+        isinstance(value, str) and value.strip()
+        for value in (security_id.exchange, security_id.display_code, security_id.currency)
+    ):
+        raise MarketRuleError("证券身份必须包含有效的交易所、显示代码和币种")
     rules = {
         Market.CN: ({"SSE", "SZSE"}, "CNY"),
         Market.HK: ({"HKEX"}, "HKD"),
         Market.US: ({"NASDAQ", "NYSE", "AMEX"}, "USD"),
     }
     exchanges, currency = rules[security_id.market]
     if security_id.exchange not in exchanges or security_id.currency != currency:
         raise MarketRuleError("证券市场、交易所或币种不一致")
     if security_id.market is Market.CN and not _is_ascii_digits(security_id.display_code, 6):
         raise MarketRuleError("中国市场证券代码必须为六码 ASCII 数字")
diff --git a/tests/contract/test_market_data_contract.py b/tests/contract/test_market_data_contract.py
index 85673b6..23e54dd 100644
--- a/tests/contract/test_market_data_contract.py
+++ b/tests/contract/test_market_data_contract.py
@@ -1,13 +1,14 @@
 """验证行情适配器协议与注册表不依赖具体供应商。"""
 
 from datetime import UTC, datetime, timedelta
+from zoneinfo import ZoneInfo
 
 import pytest
 from pydantic import ValidationError
 
 from stock_agent.adapters.market_data.base import (
     MarketDataAdapter,
     NormalizedQuote,
     SourceCapability,
 )
 from stock_agent.adapters.market_data.registry import (
@@ -16,35 +17,35 @@ from stock_agent.adapters.market_data.registry import (
     SourceCapabilityViolationError,
     UnknownSourceError,
 )
 from stock_agent.application.market_service import (
     HistoricalDailyBar,
     InstrumentCatalogEntry,
     MarketService,
     MarketStatus,
 )
 from stock_agent.contracts.common import Freshness
-from stock_agent.domain.market import InstrumentIdentity, Market
+from stock_agent.domain.market import InstrumentIdentity, InstrumentIdentityInput, Market
 
 
 def 市场证券身份(market: Market) -> InstrumentIdentity:
     """构造仅用于契约测试的完整证券身份。"""
 
-    exchange, currency = {
-        Market.CN: ("SSE", "CNY"),
-        Market.HK: ("HKEX", "HKD"),
-        Market.US: ("NASDAQ", "USD"),
+    exchange, display_code, currency = {
+        Market.CN: ("SSE", "600000", "CNY"),
+        Market.HK: ("HKEX", "00700", "HKD"),
+        Market.US: ("NASDAQ", "AAPL", "USD"),
     }[market]
     return InstrumentIdentity(
         market=market,
         exchange=exchange,
-        display_code="600000",
+        display_code=display_code,
         currency=currency,
     )
 
 
 class 演示行情适配器:
     """用于验证注册表的最小适配器，不连接任何外部服务。"""
 
     capability = SourceCapability(
         source_id="演示来源",
         markets=("CN",),
@@ -362,35 +363,100 @@ def test_证券目录查询返回身份来源时点和版本() -> None:
 
     entry = MarketService().get_instrument_catalog_entry("600000", market=Market.CN)
 
     assert isinstance(entry, InstrumentCatalogEntry)
     assert entry.security_id == 市场证券身份(Market.CN)
     assert entry.source_id
     assert entry.collected_at.tzinfo is not None
     assert entry.data_version
 
 
+def test_证券目录解析入口返回完整可追溯目录事实() -> None:
+    """解析入口不得将目录事实降级为无法审计的裸证券身份。"""
+
+    entry = MarketService().resolve_security_identity("600000", market=Market.CN)
+
+    assert isinstance(entry, InstrumentCatalogEntry)
+    assert entry.security_id == 市场证券身份(Market.CN)
+    assert entry.source_id
+    assert entry.collected_at.tzinfo is not None
+    assert entry.data_version
+
+
+@pytest.mark.parametrize("market", [Market.CN, Market.HK, Market.US])
+def test_市场状态市场时间绑定到对应的_IANA_时区(market: Market) -> None:
+    """市场状态的市场时间必须携带所属市场的 IANA 时区，而非仅相同 UTC 偏移。"""
+
+    status = MarketService().get_market_status(market)
+
+    assert isinstance(status.market_time.tzinfo, ZoneInfo)
+    assert status.market_time.tzinfo.key == market.timezone
+
+
+def test_市场状态拒绝仅有相同偏移的非市场_IANA_时区() -> None:
+    """市场状态不得用 UTC 或固定偏移替代所属市场 IANA 时区。"""
+
+    with pytest.raises(ValidationError, match="市场时间.*时区"):
+        MarketStatus(
+            market=Market.CN,
+            market_timezone="Asia/Shanghai",
+            trading_calendar_status="OPEN",
+            market_time=datetime(2026, 7, 14, 1, 30, tzinfo=UTC),
+            collected_at=datetime(2026, 7, 14, 1, 30, 1, tzinfo=UTC),
+            source_id="合同来源",
+            data_version="日历版本-1",
+            freshness=Freshness(state="REALTIME", age_seconds=1),
+        )
+
+
+def test_历史日线拒绝市场时间不是证券所属_IANA_时区() -> None:
+    """UTC 时间戳不能替代日线所属市场的本地交易时点。"""
+
+    payload = 历史日线有效载荷()
+    payload["market_time"] = datetime(2026, 7, 13, 7, 0, tzinfo=UTC)
+
+    with pytest.raises(ValidationError, match="市场时间.*时区"):
+        HistoricalDailyBar(**payload)
+
+
+def test_历史日线拒绝交易日与市场本地日期不一致() -> None:
+    """跨日 UTC 换算不得让日线交易日和所属市场本地日期错位。"""
+
+    payload = 历史日线有效载荷()
+    payload["market_time"] = datetime(2026, 7, 14, 0, 30, tzinfo=ZoneInfo("Asia/Shanghai"))
+
+    with pytest.raises(ValidationError, match="交易日.*市场时间"):
+        HistoricalDailyBar(**payload)
+
+
+def test_显式空证券目录不回退内置样例() -> None:
+    """调用方声明本地目录缺失时，查询必须返回明确缺失而不是样例证券。"""
+
+    with pytest.raises(ValueError, match="目录.*不存在|匹配"):
+        MarketService(instruments=[]).resolve_security_identity("600000", market=Market.CN)
+
+
 def test_历史日线包含可追溯字段且不得标为实时() -> None:
     """历史日线应保留身份、复权、币种、来源和版本信息，且不能伪装为实时行情。"""
 
     bar = HistoricalDailyBar(
         security_id=市场证券身份(Market.CN),
         trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
         open=10.0,
         high=10.5,
         low=9.8,
         close=10.2,
         volume=1_000_000,
         adjustment_basis="NONE",
         currency="CNY",
         source_id="契约来源",
-        market_time=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+        market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
         collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
         data_version="日线版本-1",
         freshness=Freshness(state="CLOSED", age_seconds=0),
     )
 
     assert bar.security_id.market is Market.CN
     assert bar.trade_date.isoformat() == "2026-07-13"
     assert bar.adjustment_basis == "NONE"
     assert bar.freshness.state != "REALTIME"
 
@@ -403,42 +469,42 @@ def test_历史日线拒绝实时新鲜度标记() -> None:
             security_id=市场证券身份(Market.CN),
             trade_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
             open=10.0,
             high=10.5,
             low=9.8,
             close=10.2,
             volume=1_000_000,
             adjustment_basis="NONE",
             currency="CNY",
             source_id="契约来源",
-            market_time=datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+            market_time=datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
             collected_at=datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
             data_version="日线版本-1",
             freshness=Freshness(state="REALTIME", age_seconds=0),
         )
 
 
 def test_历史日线查询拒绝倒置日期范围() -> None:
     """查询起始日期晚于结束日期时必须拒绝，避免返回含义不明的数据集。"""
 
     with pytest.raises(ValueError):
         MarketService().get_historical_daily_bars(
             市场证券身份(Market.CN),
             start_date=datetime(2026, 7, 14, tzinfo=UTC).date(),
             end_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
         )
 
 
 def test_历史日线查询拒绝跨市场不匹配证券代码() -> None:
     """美股身份不得使用A股六码代码，服务必须在查询边界拒绝跨市场代码。"""
 
-    cross_market_security = InstrumentIdentity(
+    cross_market_security = InstrumentIdentityInput(
         market=Market.US,
         exchange="NASDAQ",
         display_code="600000",
         currency="USD",
     )
 
     with pytest.raises(ValueError):
         MarketService().get_historical_daily_bars(
             cross_market_security,
             start_date=datetime(2026, 7, 13, tzinfo=UTC).date(),
@@ -453,21 +519,21 @@ def 历史日线有效载荷() -> dict[str, object]:
         "security_id": 市场证券身份(Market.CN),
         "trade_date": datetime(2026, 7, 13, tzinfo=UTC).date(),
         "open": 10.0,
         "high": 10.5,
         "low": 9.8,
         "close": 10.2,
         "volume": 1_000_000,
         "adjustment_basis": "NONE",
         "currency": "CNY",
         "source_id": "契约来源",
-        "market_time": datetime(2026, 7, 13, 7, 0, tzinfo=UTC),
+        "market_time": datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo("Asia/Shanghai")),
         "collected_at": datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
         "data_version": "日线版本-1",
         "freshness": Freshness(state="CLOSED", age_seconds=0),
     }
 
 
 def test_历史日线成功结果逐字段原样保留() -> None:
     """服务模型不得在规范化时丢失、重写或推断历史日线的审计字段。"""
 
     payload = 历史日线有效载荷()
@@ -584,43 +650,47 @@ def test_各市场状态锁定时区与允许交易日历状态(
 )
 def test_各市场接受匹配的证券代码(security_id: InstrumentIdentity) -> None:
     """A股、港股和美股的有效代码应通过市场服务的身份边界校验。"""
 
     assert MarketService().validate_security_identity(security_id) == security_id
 
 
 @pytest.mark.parametrize(
     "security_id",
     [
-        InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="AAPL", currency="CNY"),
-        InstrumentIdentity(
+        InstrumentIdentityInput(
+            market=Market.CN, exchange="SSE", display_code="AAPL", currency="CNY"
+        ),
+        InstrumentIdentityInput(
             market=Market.HK, exchange="HKEX", display_code="600000", currency="HKD"
         ),
-        InstrumentIdentity(
+        InstrumentIdentityInput(
             market=Market.US, exchange="NASDAQ", display_code="00700", currency="USD"
         ),
     ],
 )
 def test_各市场拒绝不符合本市场格式的证券代码(security_id: InstrumentIdentity) -> None:
     """不同市场不得接受另一市场的代码格式，以免跨市场查询串线。"""
 
     with pytest.raises(ValueError):
         MarketService().validate_security_identity(security_id)
 
 
 @pytest.mark.parametrize(
     "security_id",
     [
-        InstrumentIdentity(
+        InstrumentIdentityInput(
             market=Market.CN, exchange="HKEX", display_code="600000", currency="CNY"
         ),
-        InstrumentIdentity(market=Market.HK, exchange="HKEX", display_code="00700", currency="USD"),
-        InstrumentIdentity(
+        InstrumentIdentityInput(
+            market=Market.HK, exchange="HKEX", display_code="00700", currency="USD"
+        ),
+        InstrumentIdentityInput(
             market=Market.US, exchange="NASDAQ", display_code="600000", currency="USD"
         ),
     ],
 )
 def test_市场身份拒绝交易所币种或代码不匹配(security_id: InstrumentIdentity) -> None:
     """市场、交易所、币种和代码必须构成一致身份，任一不匹配均应拒绝。"""
 
     with pytest.raises(ValueError):
         MarketService().validate_security_identity(security_id)
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index 48e18a0..d96f625 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -8,21 +8,26 @@ import pytest
 from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
 from stock_agent.adapters.market_data.sina_codes import (
     UnsupportedSinaCodeError,
     normalize_sina_code,
 )
 from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
 from stock_agent.domain.freshness import (
     FreshnessClassificationError,
     is_usable_for_current_prediction,
 )
-from stock_agent.domain.market import InstrumentIdentity, Market
+from stock_agent.domain.market import (
+    InstrumentIdentity,
+    InstrumentIdentityInput,
+    Market,
+    MarketRuleError,
+)
 from stock_agent.domain.market_rules import CompanyAction
 
 
 class 忽略事实记录器:
     """隔离响应校验测试的记录端口，不替代持久化集成测试。"""
 
     def record(self, raw_response: bytes, quotes: list[object]) -> None:
         """响应校验失败路径不会调用该端口。"""
 
 
@@ -43,35 +48,56 @@ def test_新浪代码规范化支持沪深交易所(exchange: str, display_code:
     identity = InstrumentIdentity(Market.CN, exchange, display_code, "CNY")
 
     assert normalize_sina_code(identity) == expected
 
 
 @pytest.mark.parametrize(
     "identity",
     [
         InstrumentIdentity(Market.HK, "HKEX", "00001", "HKD"),
         InstrumentIdentity(Market.US, "NASDAQ", "AAPL", "USD"),
-        InstrumentIdentity(Market.CN, "BSE", "830000", "CNY"),
-        InstrumentIdentity(Market.CN, "SSE", "60000", "CNY"),
-        InstrumentIdentity(Market.CN, "SZSE", "0000A1", "CNY"),
-        InstrumentIdentity(Market.CN, "SSE", "１２３４５６", "CNY"),
     ],
 )
-def test_新浪代码规范化拒绝跨市场交易所和非法代码(
-    identity: InstrumentIdentity,
-) -> None:
-    """非中国市场、非沪深交易所或非六码数字代码一律拒绝。"""
+def test_新浪代码规范化拒绝不支持的有效市场(identity: InstrumentIdentity) -> None:
+    """其他市场的有效证券身份也不得进入仅支持 A 股的新浪代码边界。"""
 
     with pytest.raises(UnsupportedSinaCodeError):
         normalize_sina_code(identity)
 
 
+@pytest.mark.parametrize(
+    "raw_identity",
+    [
+        InstrumentIdentityInput(Market.CN, "BSE", "830000", "CNY"),
+        InstrumentIdentityInput(Market.CN, "SSE", "60000", "CNY"),
+        InstrumentIdentityInput(Market.CN, "SZSE", "0000A1", "CNY"),
+        InstrumentIdentityInput(Market.CN, "SSE", "１２３４５６", "CNY"),
+    ],
+)
+def test_原始证券输入转换拒绝跨市场交易所和非法代码(
+    raw_identity: InstrumentIdentityInput,
+) -> None:
+    """失败场景先以原始输入记录，转换为公开证券身份时再统一拒绝。"""
+
+    with pytest.raises(MarketRuleError):
+        raw_identity.to_identity()
+
+
+def test_原始证券输入转换拒绝非正式市场标识() -> None:
+    """原始接口的字符串市场标识不能绕过正式枚举和证券身份规则。"""
+
+    raw_identity = InstrumentIdentityInput("CN", "SSE", "600000", "CNY")  # type: ignore[arg-type]
+
+    with pytest.raises(MarketRuleError, match="市场"):
+        raw_identity.to_identity()
+
+
 @pytest.mark.parametrize("codes", [[], ["600000"], ["sh60000"], ["xx600000"], ["sh６０００００"]])
 def test_新浪适配器拒绝空或非法请求代码(codes: list[str], local_data_root: Path) -> None:
     """请求代码必须已是沪深前缀加六码 ASCII 数字，避免构造越界地址。"""
 
     with pytest.raises(SinaDataSourceError):
         SinaHttpAdapter(
             lambda _url: b"", 忽略事实记录器(), VersioningService(local_data_root)
         ).fetch_quotes(codes, datetime.now(UTC))
 
 
@@ -213,21 +239,21 @@ def test_证券身份拒绝市场交易所或币种不一致(
         InstrumentIdentity(market, exchange, display_code, currency)
 
 
 def test_未带市场标识的非唯一显示代码必须拒绝解析() -> None:
     """同一显示代码存在于多个市场时，查询必须要求调用方提供市场或交易所。"""
 
     from stock_agent.domain.market import MarketRuleError, resolve_instrument_identity
 
     候选证券 = [
         InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
-        InstrumentIdentity(Market.HK, "HKEX", "000001", "HKD"),
+        InstrumentIdentity(Market.CN, "SSE", "000001", "CNY"),
     ]
 
     with pytest.raises(MarketRuleError, match="市场|交易所|非唯一"):
         resolve_instrument_identity(display_code="000001", candidates=候选证券)
 
 
 @pytest.mark.parametrize("复权比例", [0, -1, float("inf")])
 def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
     """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""
 

```

