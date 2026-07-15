# T041 审查包

## 提交

3b6a321 feat: block stale facts from current predictions

## 统计

 .superpowers/sdd/task-041-report.md | 50 +++++++++++++++++++++++++++++++++++++
 src/stock_agent/domain/freshness.py | 29 +++++++++++++++++++++
 2 files changed, 79 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-041-report.md b/.superpowers/sdd/task-041-report.md
new file mode 100644
index 0000000..3043bea
--- /dev/null
+++ b/.superpowers/sdd/task-041-report.md
@@ -0,0 +1,50 @@
+# T041 行情新鲜度与当前预测阻断规则报告
+
+## 实现说明
+
+在 `src/stock_agent/domain/freshness.py` 增加公开的
+`CurrentPredictionFreshnessFact` 事实模型，字段为 `state`、`market_time`、
+`collected_at` 与 `time_is_verifiable`。新增
+`is_usable_for_current_prediction(fact)` 作为当前预测入口规则：
+
+- 仅 `REALTIME` 与 `NEAR_REALTIME` 可进入当前预测；
+- `time_is_verifiable` 必须严格为 `True`；
+- 复用 `calculate_age_seconds` 校验两个时点均带时区且市场时间不晚于采集时间；
+- `DELAYED`、`STALE`、`CLOSED` 与未知状态返回 `False`；无效时间值抛出
+  `FreshnessClassificationError`。
+
+未修改既有 CN 5 秒、HK/US 15 秒、60 秒、900 秒、休市及微秒向上取整规则；未实现任何
+HTTP 数据源、券商、下单或交易功能。
+
+## TDD 红灯证据
+
+先执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v
+```
+
+结果为 66 项中 57 通过、9 失败。全部失败的直接原因一致：
+`AttributeError: module 'stock_agent.domain.freshness' has no attribute
+'is_usable_for_current_prediction'`。既有分类边界测试均通过，确认红灯仅缺少 T041
+规则入口。
+
+## 绿灯与质量验证
+
+实现后以相同命令复验，结果：`66 passed in 0.43s`。
+
+另执行：
+
+```powershell
+py -3.12 -m pytest
+py -3.12 -m ruff format --check src/stock_agent/domain/freshness.py
+py -3.12 -m ruff check src/stock_agent/domain/freshness.py tests/property/test_freshness_rules.py
+```
+
+- 全量 pytest 在收集阶段因缺少其他任务的模块而中断：
+  `stock_agent.desktop.pages.market_page` 与
+  `stock_agent.application.market_service`，与 T041 无关。
+- `freshness.py` 的 Ruff 格式检查通过；Ruff 静态检查通过。
+- 未修改测试文件；对该既有文件运行 Ruff 格式检查会提示它需要重格式化，属于本任务范围外
+  的既存格式问题。
+- 本次新增的文档字符串、报告与错误消息均为简体中文，符合项目语言规范。
diff --git a/src/stock_agent/domain/freshness.py b/src/stock_agent/domain/freshness.py
index b8d8bfd..605fefd 100644
--- a/src/stock_agent/domain/freshness.py
+++ b/src/stock_agent/domain/freshness.py
@@ -1,25 +1,54 @@
 """集中定义跨市场行情新鲜度的纯分类规则。"""
 
 from __future__ import annotations
 
 import math
 from datetime import datetime
+from typing import TypedDict
 
 from stock_agent.contracts.common import FreshnessState
 from stock_agent.domain.market import Market
 
 
 class FreshnessClassificationError(ValueError):
     """表示无法安全计算行情新鲜度的时间错误。"""
 
 
+class CurrentPredictionFreshnessFact(TypedDict):
+    """当前预测判断所需的行情状态与可验证时点。"""
+
+    state: FreshnessState
+    market_time: datetime
+    collected_at: datetime
+    time_is_verifiable: bool
+
+
+def is_usable_for_current_prediction(fact: CurrentPredictionFreshnessFact) -> bool:
+    """仅允许时点可验证的实时或近实时行情进入当前预测。"""
+
+    if fact.get("time_is_verifiable") is not True:
+        return False
+
+    state = fact.get("state")
+    if state not in {"REALTIME", "NEAR_REALTIME"}:
+        return False
+
+    market_time = fact.get("market_time")
+    collected_at = fact.get("collected_at")
+    if not isinstance(market_time, datetime) or not isinstance(collected_at, datetime):
+        raise FreshnessClassificationError("当前预测新鲜度事实必须包含有效的市场时间和采集时间")
+
+    calculate_age_seconds(market_time, collected_at)
+    return True
+
+
 def classify_freshness(
     market: Market,
     market_time: datetime,
     collected_at: datetime,
     is_open: bool,
 ) -> FreshnessState:
     """按市场时点、采集时点和开市状态返回兼容公共契约的新鲜度。"""
 
     _validate_times(market_time, collected_at)
 

```

