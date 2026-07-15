# T043 最终复审包

## 提交

d578768 fix: gate desktop recovered states

## 统计

 .superpowers/sdd/task-043-fix-report.md        |  37 +++++++++
 src/stock_agent/application/market_service.py  |   1 +
 src/stock_agent/desktop/pages/_recovery.py     |  45 +++++++++++
 src/stock_agent/desktop/pages/market_page.py   |  34 ++++++--
 src/stock_agent/desktop/pages/security_page.py |  33 ++++++--
 tests/contract/test_desktop_state_contract.py  | 104 +++++++++++++++++++++++--
 6 files changed, 236 insertions(+), 18 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-043-fix-report.md b/.superpowers/sdd/task-043-fix-report.md
new file mode 100644
index 0000000..c68efeb
--- /dev/null
+++ b/.superpowers/sdd/task-043-fix-report.md
@@ -0,0 +1,37 @@
+# T043 恢复状态阻断修复报告
+
+## 根因与修复
+
+- 根因：`MarketPageState` 与 `SecurityPageState` 将普通字符串
+  `status="RECOVERED"` 直接视为可用状态，未要求任何本地事实证据。
+- 新增 `MarketStatus.is_verified`，默认值为 `False`，作为本地事实的显式验证标记。
+- 页面恢复仅经 `from_market_status` 受控工厂创建；工厂只接受完整的
+  `MarketStatus`，并校验 `source_id`、市场时间、采集时间、数据版本、
+  `is_verified`、时区、时间顺序和非未来时点。
+- 缺少事实、未验证、无时区、未来或时间顺序异常的证据均降级为 `STALE`。
+  普通 `status="RECOVERED"` 构造同样降级，不能伪造恢复。
+- 恢复状态仍不展示实时数据，也不允许当前预测；页面未引入网络访问、预测值
+  生成或交易能力。移除了未使用的 `_不可实时状态` 常量。
+
+## TDD 记录
+
+先修改 `tests/contract/test_desktop_state_contract.py`，再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/contract/test_desktop_state_contract.py -q
+```
+
+红灯结果：6 项失败。直接构造仍得到 `RECOVERED`，且两个页面均没有
+`from_market_status` 受控工厂。随后进行最小实现，再运行同一页面契约。
+
+## 验证
+
+- 页面状态契约：`34 passed`。
+- 改动范围 Ruff：`All checks passed!`。
+- 改动范围中文检查：通过。
+- 全量 pytest：`309 passed, 10 failed`；失败均位于既有的市场新鲜度拒绝、
+  `CompanyAction` 参数/辅助函数和港股六码规则，不涉及本次页面恢复状态代码。
+- 全仓 Ruff：失败 2 项，均位于既有
+  `tools/check_chinese_project_text.py` 的导入排序与长行。
+- 全仓中文检查：失败 1 项，位于既有
+  `tests/failure/test_market_data_failures.py:88` 的注释缺少简体中文解释。
diff --git a/src/stock_agent/application/market_service.py b/src/stock_agent/application/market_service.py
index cbc0dea..7c116c6 100644
--- a/src/stock_agent/application/market_service.py
+++ b/src/stock_agent/application/market_service.py
@@ -21,20 +21,21 @@ class MarketStatus(BaseModel):
     """表示可追溯的单市场日历状态，不包含外部数据拉取能力。"""
 
     market: Market
     market_timezone: str = Field(min_length=1)
     trading_calendar_status: str = Field(min_length=1)
     market_time: datetime
     collected_at: datetime
     source_id: str = Field(min_length=1)
     data_version: str = Field(min_length=1)
     freshness: Freshness
+    is_verified: bool = False
 
     @model_validator(mode="after")
     def 验证市场状态事实(self) -> MarketStatus:
         """锁定市场时区、状态集合与可比较的事实时间。"""
 
         allowed_statuses = {
             Market.CN: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY"},
             Market.HK: {"OPEN", "CLOSED", "MIDDAY_BREAK", "HOLIDAY", "TYPHOON_SUSPENDED"},
             Market.US: {"OPEN", "CLOSED", "PRE_MARKET", "AFTER_HOURS", "HOLIDAY"},
         }
diff --git a/src/stock_agent/desktop/pages/_recovery.py b/src/stock_agent/desktop/pages/_recovery.py
new file mode 100644
index 0000000..46732ea
--- /dev/null
+++ b/src/stock_agent/desktop/pages/_recovery.py
@@ -0,0 +1,45 @@
+"""校验页面恢复所需的本地事实，禁止普通状态字符串伪造恢复。"""
+
+from __future__ import annotations
+
+from datetime import UTC, datetime
+
+from stock_agent.application.market_service import MarketStatus
+
+
+def is_trusted_recovery_fact(market_status: MarketStatus | None) -> bool:
+    """仅接受字段完整、已验证、带时区且未指向未来的本地市场事实。"""
+
+    if not isinstance(market_status, MarketStatus) or not market_status.is_verified:
+        return False
+
+    try:
+        source_id = market_status.source_id.strip()
+        data_version = market_status.data_version.strip()
+        market_time = market_status.market_time
+        collected_at = market_status.collected_at
+    except (AttributeError, TypeError):
+        return False
+
+    if (
+        not source_id
+        or not data_version
+        or not _is_aware(market_time)
+        or not _is_aware(collected_at)
+    ):
+        return False
+    if market_time > collected_at:
+        return False
+
+    now = datetime.now(tz=UTC)
+    return market_time.astimezone(UTC) <= now and collected_at.astimezone(UTC) <= now
+
+
+def _is_aware(value: object) -> bool:
+    """判断时间是否带有可审计的时区信息。"""
+
+    return (
+        isinstance(value, datetime)
+        and value.tzinfo is not None
+        and value.utcoffset() is not None
+    )
diff --git a/src/stock_agent/desktop/pages/market_page.py b/src/stock_agent/desktop/pages/market_page.py
index c680aef..fd00cdf 100644
--- a/src/stock_agent/desktop/pages/market_page.py
+++ b/src/stock_agent/desktop/pages/market_page.py
@@ -1,51 +1,73 @@
 """定义市场总览页面的本地事实状态模型，不发起网络访问。"""
 
 from __future__ import annotations
 
 from dataclasses import dataclass, field
 
+from stock_agent.application.market_service import MarketStatus
+from stock_agent.desktop.pages._recovery import is_trusted_recovery_fact
+
 _状态说明 = {
     "EMPTY": "暂无可显示的本地市场事实。",
     "LOADING": "正在加载已选择范围内的本地市场事实。",
     "OFFLINE": "当前处于离线状态，无法显示实时数据。",
     "PERMISSION_DENIED": "数据源权限受限，当前范围不可读取。",
     "STALE": "本地市场事实已过期，不能作为实时数据使用。",
     "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
     "READY": "本地市场事实可用。",
     "RECOVERED": "已恢复：本地市场事实已重新验证并可用。",
 }
 
-_不可实时状态 = frozenset({"OFFLINE", "PERMISSION_DENIED", "STALE", "CLOSED"})
 _可用状态 = frozenset({"READY", "RECOVERED"})
 
 
 @dataclass(frozen=True, slots=True)
 class MarketPageState:
     """市场总览仅渲染脱敏状态或已验证的本地市场事实。"""
 
     status: str
     user_message: str = field(init=False)
     shows_realtime: bool = field(init=False)
     current_prediction_allowed: bool = field(init=False)
     is_available: bool = field(init=False)
 
+    @classmethod
+    def from_market_status(cls, market_status: MarketStatus | None) -> MarketPageState:
+        """仅从完整且已验证的本地市场事实创建恢复状态。"""
+
+        if not is_trusted_recovery_fact(market_status):
+            return cls(status="STALE")
+        return cls._from_trusted_recovery_fact()
+
+    @classmethod
+    def _from_trusted_recovery_fact(cls) -> MarketPageState:
+        """受控工厂在事实校验完成后才写入恢复标识。"""
+
+        view_state = cls(status="STALE")
+        object.__setattr__(view_state, "status", "RECOVERED")
+        object.__setattr__(view_state, "user_message", _状态说明["RECOVERED"])
+        object.__setattr__(view_state, "is_available", True)
+        return view_state
+
     def __post_init__(self) -> None:
         """锁定状态语义，避免将降级状态误标为实时或可预测。"""
 
-        if self.status not in _状态说明:
+        status = "STALE" if self.status == "RECOVERED" else self.status
+        if status not in _状态说明:
             raise ValueError(f"不支持的市场页面状态：{self.status}")
-        object.__setattr__(self, "user_message", _状态说明[self.status])
-        available = self.status in _可用状态
+        object.__setattr__(self, "status", status)
+        object.__setattr__(self, "user_message", _状态说明[status])
+        available = status in _可用状态
         object.__setattr__(self, "is_available", available)
-        object.__setattr__(self, "shows_realtime", self.status == "READY")
-        object.__setattr__(self, "current_prediction_allowed", self.status == "READY")
+        object.__setattr__(self, "shows_realtime", status == "READY")
+        object.__setattr__(self, "current_prediction_allowed", status == "READY")
 
     @property
     def show_realtime_data(self) -> bool:
         """兼容页面渲染层对实时展示开关的既有命名。"""
 
         return self.shows_realtime
 
     @property
     def allow_current_prediction(self) -> bool:
         """兼容页面渲染层对当前预测入口开关的既有命名。"""
diff --git a/src/stock_agent/desktop/pages/security_page.py b/src/stock_agent/desktop/pages/security_page.py
index dab44a9..b394a01 100644
--- a/src/stock_agent/desktop/pages/security_page.py
+++ b/src/stock_agent/desktop/pages/security_page.py
@@ -1,16 +1,19 @@
 """定义个股研究页面的本地事实状态模型，不发起网络访问。"""
 
 from __future__ import annotations
 
 from dataclasses import dataclass, field
 
+from stock_agent.application.market_service import MarketStatus
+from stock_agent.desktop.pages._recovery import is_trusted_recovery_fact
+
 _状态说明 = {
     "EMPTY": "暂无可显示的本地证券研究事实。",
     "LOADING": "正在加载已选择证券的本地研究事实。",
     "OFFLINE": "当前处于离线状态，无法显示实时数据。",
     "PERMISSION_DENIED": "数据源权限受限，当前证券事实不可读取。",
     "STALE": "本地证券研究事实已过期，不能作为实时数据使用。",
     "CLOSED": "市场已闭市，不能显示实时数据或进行当前预测。",
     "READY": "本地证券研究事实可用。",
     "RECOVERED": "已恢复：本地证券研究事实已重新验证并可用。",
 }
@@ -21,30 +24,50 @@ _可用状态 = frozenset({"READY", "RECOVERED"})
 @dataclass(frozen=True, slots=True)
 class SecurityPageState:
     """个股研究页面仅接受脱敏状态或本地研究视图模型。"""
 
     status: str
     user_message: str = field(init=False)
     shows_realtime: bool = field(init=False)
     current_prediction_allowed: bool = field(init=False)
     is_available: bool = field(init=False)
 
+    @classmethod
+    def from_market_status(cls, market_status: MarketStatus | None) -> SecurityPageState:
+        """仅从完整且已验证的本地市场事实创建恢复状态。"""
+
+        if not is_trusted_recovery_fact(market_status):
+            return cls(status="STALE")
+        return cls._from_trusted_recovery_fact()
+
+    @classmethod
+    def _from_trusted_recovery_fact(cls) -> SecurityPageState:
+        """受控工厂在事实校验完成后才写入恢复标识。"""
+
+        view_state = cls(status="STALE")
+        object.__setattr__(view_state, "status", "RECOVERED")
+        object.__setattr__(view_state, "user_message", _状态说明["RECOVERED"])
+        object.__setattr__(view_state, "is_available", True)
+        return view_state
+
     def __post_init__(self) -> None:
         """锁定降级页面的展示与预测权限，禁止伪装为实时。"""
 
-        if self.status not in _状态说明:
+        status = "STALE" if self.status == "RECOVERED" else self.status
+        if status not in _状态说明:
             raise ValueError(f"不支持的证券页面状态：{self.status}")
-        object.__setattr__(self, "user_message", _状态说明[self.status])
-        available = self.status in _可用状态
+        object.__setattr__(self, "status", status)
+        object.__setattr__(self, "user_message", _状态说明[status])
+        available = status in _可用状态
         object.__setattr__(self, "is_available", available)
-        object.__setattr__(self, "shows_realtime", self.status == "READY")
-        object.__setattr__(self, "current_prediction_allowed", self.status == "READY")
+        object.__setattr__(self, "shows_realtime", status == "READY")
+        object.__setattr__(self, "current_prediction_allowed", status == "READY")
 
     @property
     def show_realtime_data(self) -> bool:
         """兼容页面渲染层对实时展示开关的既有命名。"""
 
         return self.shows_realtime
 
     @property
     def allow_current_prediction(self) -> bool:
         """兼容页面渲染层对当前预测入口开关的既有命名。"""
diff --git a/tests/contract/test_desktop_state_contract.py b/tests/contract/test_desktop_state_contract.py
index 3f281b8..1eebb45 100644
--- a/tests/contract/test_desktop_state_contract.py
+++ b/tests/contract/test_desktop_state_contract.py
@@ -1,23 +1,25 @@
 """验证市场页和个股页在数据不可用时的用户可见状态契约。"""
 
 import pytest
 
 from stock_agent.desktop.pages.market_page import MarketPageState
 from stock_agent.desktop.pages.security_page import SecurityPageState
 
 
 @pytest.mark.parametrize(
-    "state", ["EMPTY", "LOADING", "OFFLINE", "PERMISSION_DENIED", "STALE", "READY", "RECOVERED"]
+    "state", ["EMPTY", "LOADING", "OFFLINE", "PERMISSION_DENIED", "STALE", "READY"]
 )
 @pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
-def test_页面状态具有中文用户可见说明(page_state: type[MarketPageState] | type[SecurityPageState], state: str) -> None:
+def test_页面状态具有中文用户可见说明(
+    page_state: type[MarketPageState] | type[SecurityPageState], state: str
+) -> None:
     """市场页和个股页的所有约定状态均应向用户提供非空中文说明。"""
 
     view_state = page_state(status=state)
 
     assert view_state.user_message
     assert any("\u4e00" <= character <= "\u9fff" for character in view_state.user_message)
 
 
 @pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
 @pytest.mark.parametrize("state", ["OFFLINE", "STALE"])
@@ -26,40 +28,128 @@ def test_离线或过期状态不得展示实时数据或允许当前预测(
 ) -> None:
     """离线和过期数据必须显式禁用实时展示及基于当前数据的预测入口。"""
 
     view_state = page_state(status=state)
 
     assert view_state.show_realtime_data is False
     assert view_state.allow_current_prediction is False
 
 
 @pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
-def test_恢复状态表示页面可重新使用(page_state: type[MarketPageState] | type[SecurityPageState]) -> None:
-    """恢复状态应明确告诉界面数据已可用，避免沿用故障态限制。"""
+def test_普通页面状态构造不能伪造恢复(
+    page_state: type[MarketPageState] | type[SecurityPageState],
+) -> None:
+    """普通字符串状态没有已验证本地事实时，必须降级而不能恢复可用。"""
 
     view_state = page_state(status="RECOVERED")
 
-    assert view_state.is_available is True
+    assert view_state.status == "STALE"
+    assert view_state.is_available is False
+    assert view_state.show_realtime_data is False
+    assert view_state.allow_current_prediction is False
 
 
 @pytest.mark.parametrize(
     ("state", "keywords"),
     [
         ("EMPTY", ("空", "暂无")),
         ("LOADING", ("加载",)),
         ("OFFLINE", ("离线",)),
         ("PERMISSION_DENIED", ("权限",)),
         ("STALE", ("过期",)),
         ("READY", ("可用",)),
-        ("RECOVERED", ("恢复",)),
     ],
 )
 @pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
 def test_页面状态保留标识并提供对应中文语义(
-    page_state: type[MarketPageState] | type[SecurityPageState], state: str, keywords: tuple[str, ...]
+    page_state: type[MarketPageState] | type[SecurityPageState],
+    state: str,
+    keywords: tuple[str, ...],
 ) -> None:
     """每种页面状态必须可识别，且中文说明应表达该状态自身语义而非通用提示。"""
 
     view_state = page_state(status=state)
 
     assert view_state.status == state
     assert any(keyword in view_state.user_message for keyword in keywords)
+
+
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+def test_恢复工厂拒绝未验证或未来的本地事实(
+    page_state: type[MarketPageState] | type[SecurityPageState],
+) -> None:
+    """恢复仅接受已验证、带时区且时点不在未来的本地事实。"""
+
+    from datetime import UTC, datetime, timedelta
+    from zoneinfo import ZoneInfo
+
+    from stock_agent.application.market_service import MarketStatus
+    from stock_agent.contracts.common import Freshness
+    from stock_agent.domain.market import Market
+
+    now = datetime.now(tz=UTC)
+    unverified = MarketStatus(
+        market=Market.CN,
+        market_timezone=Market.CN.timezone,
+        trading_calendar_status="OPEN",
+        market_time=now.astimezone(ZoneInfo(Market.CN.timezone)),
+        collected_at=now,
+        source_id="本地来源",
+        data_version="版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=0),
+        is_verified=False,
+    )
+    future = unverified.model_copy(
+        update={
+            "market_time": (now + timedelta(minutes=1)).astimezone(ZoneInfo(Market.CN.timezone)),
+            "collected_at": now + timedelta(minutes=1),
+            "is_verified": True,
+        }
+    )
+    timezone_missing = MarketStatus.model_construct(
+        market=Market.CN,
+        market_timezone=Market.CN.timezone,
+        trading_calendar_status="OPEN",
+        market_time=now.replace(tzinfo=None),
+        collected_at=now,
+        source_id="本地来源",
+        data_version="版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=0),
+        is_verified=True,
+    )
+
+    assert page_state.from_market_status(None).status == "STALE"
+    assert page_state.from_market_status(unverified).status == "STALE"
+    assert page_state.from_market_status(future).status == "STALE"
+    assert page_state.from_market_status(timezone_missing).status == "STALE"
+
+
+@pytest.mark.parametrize("page_state", [MarketPageState, SecurityPageState])
+def test_恢复工厂仅接受完整已验证的本地事实(
+    page_state: type[MarketPageState] | type[SecurityPageState],
+) -> None:
+    """恢复状态必须保留来源、市场时间、采集时间、版本和验证标记。"""
+
+    from datetime import UTC, datetime
+    from zoneinfo import ZoneInfo
+
+    from stock_agent.application.market_service import MarketStatus
+    from stock_agent.contracts.common import Freshness
+    from stock_agent.domain.market import Market
+
+    now = datetime.now(tz=UTC)
+    market_status = MarketStatus(
+        market=Market.CN,
+        market_timezone=Market.CN.timezone,
+        trading_calendar_status="OPEN",
+        market_time=now.astimezone(ZoneInfo(Market.CN.timezone)),
+        collected_at=now,
+        source_id="本地来源",
+        data_version="版本-1",
+        freshness=Freshness(state="REALTIME", age_seconds=0),
+        is_verified=True,
+    )
+
+    view_state = page_state.from_market_status(market_status)
+
+    assert view_state.status == "RECOVERED"
+    assert view_state.is_available is True

```

