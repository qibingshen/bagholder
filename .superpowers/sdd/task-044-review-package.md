# T044 审查包

## 提交

cf3d83e feat: add local market overview controller

## 统计

 .superpowers/sdd/task-044-report.md                |  36 ++++
 src/stock_agent/desktop/controllers/__init__.py    |   1 +
 .../desktop/controllers/market_controller.py       | 154 ++++++++++++++++
 tests/integration/test_market_controller.py        | 204 +++++++++++++++++++++
 4 files changed, 395 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-044-report.md b/.superpowers/sdd/task-044-report.md
new file mode 100644
index 0000000..f151c4f
--- /dev/null
+++ b/.superpowers/sdd/task-044-report.md
@@ -0,0 +1,36 @@
+# T044 本地市场总览展示闭环报告
+
+## 交付内容
+
+- 新增 `MarketController`，只接收 `MarketService` 与调用方已持久化的
+  `IngestedHistoricalDailyBar`；没有网络客户端、行情适配器或凭据服务入口。
+- 新增市场总览模型，将市场状态、主要指数目录事实及其历史日线原样组合。
+  日线保留来源、市场时间、采集时间、上游版本、工件版本和 `HISTORICAL`
+  新鲜度，不生成指数价格、预测值或交易动作。
+- 本地日历缺失、闭市/休市、延迟/过期、权限受限、验证证据不足时，分别进入
+  `EMPTY`、`CLOSED`、`STALE`、`PERMISSION_DENIED` 或 `STALE`，且禁止实时展示
+  与当前预测。主要指数没有本地历史日线时保留目录事实并显示明确空状态。
+
+## TDD 记录
+
+先新增 `tests/integration/test_market_controller.py`，在控制器模块尚不存在时运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py -q
+```
+
+红灯为 `10 failed`，失败原因均为预期的
+`ModuleNotFoundError: No module named 'stock_agent.desktop.controllers'`。
+随后以最小控制器、页面模型组合和本地日线过滤实现通过测试。
+
+## 验证
+
+- 目标集成测试：`10 passed`。
+- 改动范围 Ruff：通过。
+- 改动范围中文检查：控制器目录与 `tests/integration` 均通过。
+- 全量 pytest：`319 passed, 10 failed`，失败均为既有的当前预测异常语义、
+  `CompanyAction` 参数/复权辅助函数以及港股六码规则，与本任务文件无关。
+- 全仓 Ruff：失败 2 项，均位于既有的
+  `tools/check_chinese_project_text.py`（导入排序和长行）。
+- 全仓中文检查：失败 1 项，位于既有的
+  `tests/failure/test_market_data_failures.py:88` 注释缺少简体中文说明。
diff --git a/src/stock_agent/desktop/controllers/__init__.py b/src/stock_agent/desktop/controllers/__init__.py
new file mode 100644
index 0000000..b02c7f4
--- /dev/null
+++ b/src/stock_agent/desktop/controllers/__init__.py
@@ -0,0 +1 @@
+"""桌面控制器仅协调本地事实与页面模型。"""
diff --git a/src/stock_agent/desktop/controllers/market_controller.py b/src/stock_agent/desktop/controllers/market_controller.py
new file mode 100644
index 0000000..289cd55
--- /dev/null
+++ b/src/stock_agent/desktop/controllers/market_controller.py
@@ -0,0 +1,154 @@
+"""将本地市场事实组装为市场总览页面模型，不访问外部依赖。"""
+
+from __future__ import annotations
+
+from collections.abc import Iterable
+from dataclasses import dataclass
+from datetime import date
+
+from stock_agent.application.market_service import (
+    InstrumentCatalogEntry,
+    MarketService,
+    MarketStatus,
+)
+from stock_agent.desktop.pages.market_page import MarketPageState
+from stock_agent.domain.market import Market
+from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar
+
+
+@dataclass(frozen=True, slots=True)
+class PrimaryIndexHistory:
+    """保留主要指数目录事实及其已持久化历史日线。"""
+
+    catalog: InstrumentCatalogEntry
+    daily_bars: tuple[IngestedHistoricalDailyBar, ...]
+
+
+@dataclass(frozen=True, slots=True)
+class MarketOverviewModel:
+    """市场页可渲染的本地事实模型，不包含预测或交易结果。"""
+
+    page_state: MarketPageState
+    market_status: MarketStatus | None
+    primary_indexes: tuple[PrimaryIndexHistory, ...]
+    current_prediction_allowed: bool
+    empty_state_zh: str | None = None
+
+
+class MarketController:
+    """只组合本地查询服务、目录事实和已持久化历史日线。"""
+
+    def __init__(
+        self,
+        *,
+        market_service: MarketService,
+        historical_daily_bars: Iterable[IngestedHistoricalDailyBar],
+    ) -> None:
+        """接收调用方已验证的本地依赖，不接收网络、适配器或凭据服务。"""
+
+        self._market_service = market_service
+        self._historical_daily_bars = tuple(historical_daily_bars)
+
+    def build_market_overview(
+        self,
+        *,
+        market: Market,
+        primary_index_codes: Iterable[str],
+        start_date: date,
+        end_date: date,
+        permission_granted: bool = True,
+    ) -> MarketOverviewModel:
+        """组装指定市场的本地总览；缺失或不可用事实一律降级。"""
+
+        if start_date > end_date:
+            raise ValueError("历史日线起始日期不能晚于结束日期")
+        if not permission_granted:
+            return self._degraded_model("PERMISSION_DENIED")
+
+        try:
+            market_status = self._market_service.get_market_status(market)
+        except ValueError:
+            return self._degraded_model("EMPTY")
+
+        degraded_status = _degradation_status(market_status)
+        if degraded_status is not None:
+            return self._degraded_model(degraded_status, market_status=market_status)
+
+        primary_indexes = self._primary_indexes(
+            market=market,
+            primary_index_codes=primary_index_codes,
+            start_date=start_date,
+            end_date=end_date,
+        )
+        if not primary_indexes or any(not item.daily_bars for item in primary_indexes):
+            return MarketOverviewModel(
+                page_state=MarketPageState(status="EMPTY"),
+                market_status=market_status,
+                primary_indexes=primary_indexes,
+                current_prediction_allowed=False,
+                empty_state_zh="暂无本地主要指数历史日线事实",
+            )
+
+        page_state = MarketPageState(status="READY")
+        return MarketOverviewModel(
+            page_state=page_state,
+            market_status=market_status,
+            primary_indexes=primary_indexes,
+            current_prediction_allowed=page_state.current_prediction_allowed,
+        )
+
+    def _primary_indexes(
+        self,
+        *,
+        market: Market,
+        primary_index_codes: Iterable[str],
+        start_date: date,
+        end_date: date,
+    ) -> tuple[PrimaryIndexHistory, ...]:
+        """从本地目录解析指数身份，再按日期过滤已持久化历史日线。"""
+
+        items: list[PrimaryIndexHistory] = []
+        for display_code in primary_index_codes:
+            try:
+                catalog = self._market_service.get_instrument_catalog_entry(
+                    display_code, market=market
+                )
+            except ValueError:
+                continue
+            daily_bars = tuple(
+                bar
+                for bar in self._historical_daily_bars
+                if bar.security_id == catalog.security_id
+                and start_date <= bar.trade_date <= end_date
+                and bar.freshness.state == "HISTORICAL"
+            )
+            items.append(PrimaryIndexHistory(catalog=catalog, daily_bars=daily_bars))
+        return tuple(items)
+
+    @staticmethod
+    def _degraded_model(
+        status: str,
+        *,
+        market_status: MarketStatus | None = None,
+    ) -> MarketOverviewModel:
+        """为不可用本地事实构造无实时、无当前预测的页面模型。"""
+
+        page_state = MarketPageState(status=status)
+        return MarketOverviewModel(
+            page_state=page_state,
+            market_status=market_status,
+            primary_indexes=(),
+            current_prediction_allowed=False,
+        )
+
+
+def _degradation_status(market_status: MarketStatus) -> str | None:
+    """按交易日历、新鲜度和验证证据确定市场页面降级边界。"""
+
+    if not market_status.is_verified:
+        return "STALE"
+    if market_status.trading_calendar_status in {"CLOSED", "HOLIDAY"}:
+        return "CLOSED"
+    if market_status.freshness.state not in {"REALTIME", "NEAR_REALTIME"}:
+        return "STALE"
+    return None
diff --git a/tests/integration/test_market_controller.py b/tests/integration/test_market_controller.py
new file mode 100644
index 0000000..caa110f
--- /dev/null
+++ b/tests/integration/test_market_controller.py
@@ -0,0 +1,204 @@
+"""验证市场总览控制器只组合本地市场事实。"""
+
+from __future__ import annotations
+
+from datetime import UTC, date, datetime
+from zoneinfo import ZoneInfo
+
+import pytest
+
+from stock_agent.application.market_service import (
+    InstrumentCatalogEntry,
+    MarketService,
+    MarketStatus,
+)
+from stock_agent.contracts.common import Freshness
+from stock_agent.domain.market import InstrumentIdentity, Market
+from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar
+
+
+def _主要指数身份() -> InstrumentIdentity:
+    """构造市场总览使用的本地主要指数目录身份。"""
+
+    return InstrumentIdentity(Market.CN, "SSE", "000001", "CNY")
+
+
+def _市场状态(
+    *,
+    calendar_status: str = "OPEN",
+    freshness_state: str = "REALTIME",
+    is_verified: bool = True,
+) -> MarketStatus:
+    """构造带完整来源、时点、版本的新鲜本地市场状态。"""
+
+    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(Market.CN.timezone))
+    return MarketStatus(
+        market=Market.CN,
+        market_timezone=Market.CN.timezone,
+        trading_calendar_status=calendar_status,
+        market_time=market_time,
+        collected_at=market_time.astimezone(UTC),
+        source_id="本地交易日历",
+        data_version="日历版本-1",
+        freshness=Freshness(state=freshness_state, age_seconds=0),
+        is_verified=is_verified,
+    )
+
+
+def _历史日线() -> IngestedHistoricalDailyBar:
+    """构造已持久化的历史日线，不包含任何实时数据。"""
+
+    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(Market.CN.timezone))
+    return IngestedHistoricalDailyBar(
+        security_id=_主要指数身份(),
+        trade_date=date(2026, 7, 13),
+        market_time=market_time,
+        open=3_500.0,
+        high=3_520.0,
+        low=3_480.0,
+        close=3_510.0,
+        volume=100_000_000,
+        currency="CNY",
+        adjustment_basis="none",
+        source_id="sina",
+        collected_at=market_time.astimezone(UTC),
+        source_data_version="sina-历史响应-1",
+        artifact_version_id="normalized-1",
+    )
+
+
+def _本地市场服务(status: MarketStatus | None = None) -> MarketService:
+    """构造仅含主要指数目录与市场状态的本地查询服务。"""
+
+    return MarketService(
+        market_statuses=[] if status is None else [status],
+        instrument_catalog=[
+            InstrumentCatalogEntry(
+                security_id=_主要指数身份(),
+                source_id="本地主要指数目录",
+                collected_at=datetime(2026, 7, 14, tzinfo=UTC),
+                data_version="指数目录版本-1",
+            )
+        ],
+    )
+
+
+def test_控制器以本地目录和已持久化日线返回可追溯的市场准备模型() -> None:
+    """所有可显示数值都必须保留来源、市场时点、采集时间、版本与历史新鲜度。"""
+
+    from stock_agent.desktop.controllers.market_controller import MarketController
+
+    controller = MarketController(
+        market_service=_本地市场服务(_市场状态()),
+        historical_daily_bars=[_历史日线()],
+    )
+
+    model = controller.build_market_overview(
+        market=Market.CN,
+        primary_index_codes=["000001"],
+        start_date=date(2026, 7, 13),
+        end_date=date(2026, 7, 13),
+    )
+
+    assert model.page_state.status == "READY"
+    assert model.page_state.shows_realtime is True
+    assert model.current_prediction_allowed is True
+    assert model.market_status.source_id == "本地交易日历"
+    assert model.market_status.market_time.tzinfo is not None
+    assert model.market_status.collected_at.tzinfo is not None
+    assert model.market_status.data_version == "日历版本-1"
+    assert model.market_status.freshness.state == "REALTIME"
+    assert model.primary_indexes[0].catalog.source_id == "本地主要指数目录"
+    assert model.primary_indexes[0].catalog.data_version == "指数目录版本-1"
+    assert model.primary_indexes[0].daily_bars[0].close == 3_510.0
+    assert model.primary_indexes[0].daily_bars[0].source_id == "sina"
+    assert model.primary_indexes[0].daily_bars[0].market_time.tzinfo is not None
+    assert model.primary_indexes[0].daily_bars[0].collected_at.tzinfo is not None
+    assert model.primary_indexes[0].daily_bars[0].source_data_version == "sina-历史响应-1"
+    assert model.primary_indexes[0].daily_bars[0].artifact_version_id == "normalized-1"
+    assert model.primary_indexes[0].daily_bars[0].freshness.state == "HISTORICAL"
+
+
+@pytest.mark.parametrize(
+    ("status", "permission_granted", "expected_status"),
+    [
+        (None, True, "EMPTY"),
+        (_市场状态(calendar_status="CLOSED", freshness_state="CLOSED"), True, "CLOSED"),
+        (_市场状态(calendar_status="HOLIDAY", freshness_state="CLOSED"), True, "CLOSED"),
+        (_市场状态(freshness_state="DELAYED"), True, "STALE"),
+        (_市场状态(freshness_state="STALE"), True, "STALE"),
+        (_市场状态(), False, "PERMISSION_DENIED"),
+        (_市场状态(is_verified=False), True, "STALE"),
+    ],
+)
+def test_控制器在本地事实不足或不可用时选择降级状态(
+    status: MarketStatus | None, permission_granted: bool, expected_status: str
+) -> None:
+    """降级页面不得显示实时数据或允许当前预测。"""
+
+    from stock_agent.desktop.controllers.market_controller import MarketController
+
+    controller = MarketController(
+        market_service=_本地市场服务(status),
+        historical_daily_bars=[_历史日线()],
+    )
+
+    model = controller.build_market_overview(
+        market=Market.CN,
+        primary_index_codes=["000001"],
+        start_date=date(2026, 7, 13),
+        end_date=date(2026, 7, 13),
+        permission_granted=permission_granted,
+    )
+
+    assert model.page_state.status == expected_status
+    assert model.page_state.shows_realtime is False
+    assert model.current_prediction_allowed is False
+
+
+def test_历史日线不足时控制器返回明确空状态且不补造价格() -> None:
+    """没有本地日线时必须保留目录事实并显示空状态，而不是虚构指数价格。"""
+
+    from stock_agent.desktop.controllers.market_controller import MarketController
+
+    controller = MarketController(
+        market_service=_本地市场服务(_市场状态()), historical_daily_bars=[]
+    )
+
+    model = controller.build_market_overview(
+        market=Market.CN,
+        primary_index_codes=["000001"],
+        start_date=date(2026, 7, 13),
+        end_date=date(2026, 7, 13),
+    )
+
+    assert model.page_state.status == "EMPTY"
+    assert model.primary_indexes[0].daily_bars == ()
+    assert model.empty_state_zh == "暂无本地主要指数历史日线事实"
+    assert model.current_prediction_allowed is False
+
+
+def test_控制器不访问网络适配器或凭据服务(monkeypatch: pytest.MonkeyPatch) -> None:
+    """控制器仅调用本地查询服务，任何外部访问尝试都应使测试失败。"""
+
+    from stock_agent.desktop.controllers.market_controller import MarketController
+
+    def _禁止外部调用(*_args: object, **_kwargs: object) -> None:
+        raise AssertionError("控制器不得调用外部依赖")
+
+    monkeypatch.setattr("socket.create_connection", _禁止外部调用)
+    monkeypatch.setattr("urllib.request.urlopen", _禁止外部调用)
+    monkeypatch.setattr("keyring.get_password", _禁止外部调用)
+    controller = MarketController(
+        market_service=_本地市场服务(_市场状态()),
+        historical_daily_bars=[_历史日线()],
+    )
+
+    model = controller.build_market_overview(
+        market=Market.CN,
+        primary_index_codes=["000001"],
+        start_date=date(2026, 7, 13),
+        end_date=date(2026, 7, 13),
+    )
+
+    assert model.page_state.status == "READY"

```

