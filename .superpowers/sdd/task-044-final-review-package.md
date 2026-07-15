# T044 最终复审包

## 提交

983b2ba fix: gate market readiness on open calendar

## 统计

 .superpowers/sdd/task-044-fix-report.md            | 49 ++++++++++++++++++++++
 .../desktop/controllers/market_controller.py       |  2 +-
 tests/integration/test_market_controller.py        | 38 +++++++++++++++--
 3 files changed, 85 insertions(+), 4 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/task-044-fix-report.md b/.superpowers/sdd/task-044-fix-report.md
new file mode 100644
index 0000000..7237e2f
--- /dev/null
+++ b/.superpowers/sdd/task-044-fix-report.md
@@ -0,0 +1,49 @@
+# T044 日历状态门禁修复报告
+
+## 修复内容
+
+- 根因：`MarketController` 仅将 `CLOSED` 与 `HOLIDAY` 识别为交易日历降级状态，导致
+  `MIDDAY_BREAK`、`TYPHOON_SUSPENDED`、`PRE_MARKET` 和 `AFTER_HOURS` 在本地状态新鲜且
+  已验证时可能穿透至 `READY`。
+- 将日历门禁收紧为白名单：仅 `trading_calendar_status == "OPEN"` 可继续构造
+  `READY` 市场页；所有其他受控非开市状态均明确降级为 `CLOSED`，不显示实时数据且不允许
+  当前预测。
+- 新增跨市场参数化集成用例，覆盖中国市场 `MIDDAY_BREAK`、香港市场
+  `TYPHOON_SUSPENDED`、美国市场 `PRE_MARKET` 与 `AFTER_HOURS`。用例通过真实
+  `MarketController` 路径验证页面状态、实时展示和当前预测三个门禁结果。
+- 未修改本地事实来源、历史日线组合逻辑；未新增网络访问、预测数值或交易路径。
+
+## TDD 记录
+
+先在 `tests/integration/test_market_controller.py` 添加四种非 `OPEN` 日历状态的参数化测试，
+再运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py -q
+```
+
+红灯结果为 `4 failed, 10 passed`：四种状态均未得到预期的 `CLOSED`；其中
+`MIDDAY_BREAK` 错误进入 `READY`，其余三种因后续本地目录事实不足而落入 `EMPTY`。这证明
+日历门禁没有在组合本地目录之前统一阻断非开市状态。
+
+随后仅将降级判定改为 `trading_calendar_status != "OPEN"`，同一目标测试转绿为
+`14 passed`。
+
+## 验证
+
+- 控制器集成与页面契约：
+
+  ```powershell
+  py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py tests/contract/test_desktop_state_contract.py -q
+  ```
+
+  结果：`48 passed`。
+
+- 改动范围 Ruff：`ruff check` 通过；`ruff format --check` 显示两份文件均已格式化。
+- 改动范围中文检查：控制器目录与 `tests/integration` 均通过。
+- 全量 pytest：`323 passed, 10 failed`。失败均位于既有的
+  `tests/failure/test_market_data_failures.py`（当前预测拒绝、`CompanyAction` 参数及复权辅助函数）
+  和 `tests/property/test_market_rules.py`（港股六码规则），未涉及本次控制器日历门禁文件。
+- 全仓 Ruff：失败 2 项，均位于既有的 `tools/check_chinese_project_text.py`（导入排序与长行）。
+- 全仓中文检查：失败 1 项，位于既有的
+  `tests/failure/test_market_data_failures.py:88`，该注释缺少简体中文说明。
diff --git a/src/stock_agent/desktop/controllers/market_controller.py b/src/stock_agent/desktop/controllers/market_controller.py
index 289cd55..18e788c 100644
--- a/src/stock_agent/desktop/controllers/market_controller.py
+++ b/src/stock_agent/desktop/controllers/market_controller.py
@@ -140,15 +140,15 @@ class MarketController:
             primary_indexes=(),
             current_prediction_allowed=False,
         )
 
 
 def _degradation_status(market_status: MarketStatus) -> str | None:
     """按交易日历、新鲜度和验证证据确定市场页面降级边界。"""
 
     if not market_status.is_verified:
         return "STALE"
-    if market_status.trading_calendar_status in {"CLOSED", "HOLIDAY"}:
+    if market_status.trading_calendar_status != "OPEN":
         return "CLOSED"
     if market_status.freshness.state not in {"REALTIME", "NEAR_REALTIME"}:
         return "STALE"
     return None
diff --git a/tests/integration/test_market_controller.py b/tests/integration/test_market_controller.py
index caa110f..a491717 100644
--- a/tests/integration/test_market_controller.py
+++ b/tests/integration/test_market_controller.py
@@ -18,30 +18,31 @@ from stock_agent.workers.market_ingestion import IngestedHistoricalDailyBar
 
 
 def _主要指数身份() -> InstrumentIdentity:
     """构造市场总览使用的本地主要指数目录身份。"""
 
     return InstrumentIdentity(Market.CN, "SSE", "000001", "CNY")
 
 
 def _市场状态(
     *,
+    market: Market = Market.CN,
     calendar_status: str = "OPEN",
     freshness_state: str = "REALTIME",
     is_verified: bool = True,
 ) -> MarketStatus:
     """构造带完整来源、时点、版本的新鲜本地市场状态。"""
 
-    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(Market.CN.timezone))
+    market_time = datetime(2026, 7, 13, 15, 0, tzinfo=ZoneInfo(market.timezone))
     return MarketStatus(
-        market=Market.CN,
-        market_timezone=Market.CN.timezone,
+        market=market,
+        market_timezone=market.timezone,
         trading_calendar_status=calendar_status,
         market_time=market_time,
         collected_at=market_time.astimezone(UTC),
         source_id="本地交易日历",
         data_version="日历版本-1",
         freshness=Freshness(state=freshness_state, age_seconds=0),
         is_verified=is_verified,
     )
 
 
@@ -149,20 +150,51 @@ def test_控制器在本地事实不足或不可用时选择降级状态(
         start_date=date(2026, 7, 13),
         end_date=date(2026, 7, 13),
         permission_granted=permission_granted,
     )
 
     assert model.page_state.status == expected_status
     assert model.page_state.shows_realtime is False
     assert model.current_prediction_allowed is False
 
 
+@pytest.mark.parametrize(
+    ("market", "calendar_status"),
+    [
+        (Market.CN, "MIDDAY_BREAK"),
+        (Market.HK, "TYPHOON_SUSPENDED"),
+        (Market.US, "PRE_MARKET"),
+        (Market.US, "AFTER_HOURS"),
+    ],
+)
+def test_控制器仅在交易日历为_OPEN_时允许市场准备状态(market: Market, calendar_status: str) -> None:
+    """所有受控的非开市日历状态均不得显示实时数据或允许当前预测。"""
+
+    from stock_agent.desktop.controllers.market_controller import MarketController
+
+    controller = MarketController(
+        market_service=_本地市场服务(_市场状态(market=market, calendar_status=calendar_status)),
+        historical_daily_bars=[_历史日线()],
+    )
+
+    model = controller.build_market_overview(
+        market=market,
+        primary_index_codes=["000001"],
+        start_date=date(2026, 7, 13),
+        end_date=date(2026, 7, 13),
+    )
+
+    assert model.page_state.status == "CLOSED"
+    assert model.page_state.shows_realtime is False
+    assert model.current_prediction_allowed is False
+
+
 def test_历史日线不足时控制器返回明确空状态且不补造价格() -> None:
     """没有本地日线时必须保留目录事实并显示空状态，而不是虚构指数价格。"""
 
     from stock_agent.desktop.controllers.market_controller import MarketController
 
     controller = MarketController(
         market_service=_本地市场服务(_市场状态()), historical_daily_bars=[]
     )
 
     model = controller.build_market_overview(

```

