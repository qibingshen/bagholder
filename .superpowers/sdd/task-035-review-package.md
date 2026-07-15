# T035 复审包

## 提交

8a00e9b test: 补强当前预测新鲜度事实
0811c62 test: 补充三市场新鲜度边界

## 统计

 .superpowers/sdd/task-035-report.md    |  38 +++++++
 tests/property/test_freshness_rules.py | 201 +++++++++++++++++++++++++++++++++
 2 files changed, 239 insertions(+)

## 差异

```diff
diff --git a/.superpowers/sdd/task-035-report.md b/.superpowers/sdd/task-035-report.md
new file mode 100644
index 0000000..429d290
--- /dev/null
+++ b/.superpowers/sdd/task-035-report.md
@@ -0,0 +1,38 @@
+# T035：三市场新鲜度边界数据测试报告
+
+## 修改范围
+
+- 新增 `tests/property/test_freshness_rules.py` 的三市场完整秒级边界断言：0 秒、各市场实时上限、上限后一秒、60 秒、61 秒、900 秒、901 秒。
+- 新增带微秒的年龄分级断言，覆盖 CN、HK、US 的实时、近实时、延迟和过期阈值，要求年龄向上取整。
+- 新增交易日历关闭时有效时间一律为 `CLOSED` 的跨市场用例，并验证休市不能绕过未来时间、无时区时间和负年龄的拒绝规则。
+- 新增当前预测可用性契约：仅 `REALTIME` 和 `NEAR_REALTIME` 可用，`DELAYED`、`STALE`、`CLOSED` 不可用。
+
+未修改 `src/` 下的生产代码。
+
+## 失败证据
+
+在新增测试后、未实现当前预测可用性规则前运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v
+```
+
+结果：共收集 62 项，57 项通过、5 项失败，退出码为 1。
+
+失败用例均为 `test_仅有效实时或近实时行情可用于当前预测` 的五个新参数场景（`REALTIME`、`NEAR_REALTIME`、`DELAYED`、`STALE`、`CLOSED`）。失败原因一致：`stock_agent.domain.freshness` 尚未提供 `is_usable_for_current_prediction`，报出 `AttributeError`。这证明新增测试没有被现有实现满足，且失败点是当前预测可用性规则尚未落地。
+
+同一命令中，新增的三市场秒级边界、微秒向上取整、休市优先级，以及既有的未来时间、无时区时间和负年龄拒绝用例均按预期通过。
+
+## 后续实现边界
+
+后续生产实现应在不放宽时间校验的前提下，提供当前预测可用性规则：仅经验证的 `REALTIME` 与 `NEAR_REALTIME` 可进入当前研究输入；`DELAYED`、`STALE` 与 `CLOSED` 必须被拒绝。
+
+## 审查补强
+
+本次将当前预测可用性测试的入参从裸状态字符串改为 `当前预测新鲜度事实`：该事实契约同时携带 `state`、`market_time`、`collected_at` 与 `time_is_verifiable`。新增断言覆盖：
+
+- 只有时间可验证的 `REALTIME` 与 `NEAR_REALTIME` 事实可用；
+- 即便状态被伪标为 `REALTIME` 或 `NEAR_REALTIME`，无时区时间或未来市场时间且 `time_is_verifiable=False` 时仍不可用；
+- `UNRECOGNIZED` 等未知状态必须返回不可用或显式拒绝，不能由默认分支放行。
+
+补强后再次运行相同命令：共收集 66 项，57 项通过、9 项失败，退出码为 1。9 个失败场景均因 `is_usable_for_current_prediction` 尚未实现而触发 `AttributeError`；其中包含 3 个不可验证市场时间和 1 个未知状态的新增保护场景。
diff --git a/tests/property/test_freshness_rules.py b/tests/property/test_freshness_rules.py
index 51c79de..67d5972 100644
--- a/tests/property/test_freshness_rules.py
+++ b/tests/property/test_freshness_rules.py
@@ -1,20 +1,30 @@
 """验证跨市场行情新鲜度的纯规则边界。"""
 
 from datetime import UTC, datetime, timedelta
+from typing import TypedDict
 
 import pytest
 
 from stock_agent.domain.freshness import FreshnessClassificationError, classify_freshness
 from stock_agent.domain.market import Market
 
 
+class 当前预测新鲜度事实(TypedDict):
+    """当前预测入口必须同时接收状态、时点和时间可验证结论。"""
+
+    state: str
+    market_time: datetime
+    collected_at: datetime
+    time_is_verifiable: bool
+
+
 @pytest.mark.parametrize(
     ("market", "realtime_limit"),
     [
         (Market.CN, 0),
         (Market.HK, 0),
         (Market.US, 0),
         (Market.CN, 5),
         (Market.HK, 15),
         (Market.US, 15),
     ],
@@ -47,20 +57,81 @@ def test_交易时段超过各市场实时边界为近实时(market: Market, age
 )
 def test_交易时段通用时效边界(age_seconds: int, expected: str) -> None:
     """一分钟与十五分钟边界必须保持与公共新鲜度契约一致。"""
 
     collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
     market_time = collected_at - timedelta(seconds=age_seconds)
 
     assert classify_freshness(Market.CN, market_time, collected_at, is_open=True) == expected
 
 
+@pytest.mark.parametrize(
+    ("market", "realtime_limit"),
+    [(Market.CN, 5), (Market.HK, 15), (Market.US, 15)],
+)
+@pytest.mark.parametrize(
+    ("age_seconds", "expected"),
+    [
+        (0, "REALTIME"),
+        ("realtime_limit", "REALTIME"),
+        ("realtime_limit_plus_one", "NEAR_REALTIME"),
+        (60, "NEAR_REALTIME"),
+        (61, "DELAYED"),
+        (900, "DELAYED"),
+        (901, "STALE"),
+    ],
+)
+def test_三市场完整新鲜度边界严格转换(
+    market: Market, realtime_limit: int, age_seconds: int | str, expected: str
+) -> None:
+    """三市场在全部公共阈值和各自实时阈值处必须精确分级。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    resolved_age_seconds = {
+        "realtime_limit": realtime_limit,
+        "realtime_limit_plus_one": realtime_limit + 1,
+    }.get(age_seconds, age_seconds)
+    assert isinstance(resolved_age_seconds, int)
+
+    market_time = collected_at - timedelta(seconds=resolved_age_seconds)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == expected
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds", "expected"),
+    [
+        (Market.CN, 4.000001, "REALTIME"),
+        (Market.CN, 5.000001, "NEAR_REALTIME"),
+        (Market.CN, 60.000001, "DELAYED"),
+        (Market.CN, 900.000001, "STALE"),
+        (Market.HK, 14.000001, "REALTIME"),
+        (Market.HK, 15.000001, "NEAR_REALTIME"),
+        (Market.HK, 60.000001, "DELAYED"),
+        (Market.HK, 900.000001, "STALE"),
+        (Market.US, 14.000001, "REALTIME"),
+        (Market.US, 15.000001, "NEAR_REALTIME"),
+        (Market.US, 60.000001, "DELAYED"),
+        (Market.US, 900.000001, "STALE"),
+    ],
+)
+def test_带微秒年龄向上取整后不得跨越新鲜度阈值(
+    market: Market, age_seconds: float, expected: str
+) -> None:
+    """超过任一秒级阈值的微秒部分必须向上取整，不能被截断为更高新鲜度。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=True) == expected
+
+
 def test_休市时忽略时间年龄并返回休市() -> None:
     """休市行情不能被标为可实时使用。"""
 
     collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
 
     assert (
         classify_freshness(Market.US, collected_at - timedelta(days=1), collected_at, is_open=False)
         == "CLOSED"
     )
 
@@ -88,10 +159,140 @@ def test_休市时未来市场时间仍被拒绝() -> None:
             datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
             datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
         ),
     ],
 )
 def test_拒绝无时区或负年龄的时间(market_time: datetime, collected_at: datetime) -> None:
     """无时区和未来市场时间都不能伪装成新鲜行情。"""
 
     with pytest.raises(FreshnessClassificationError):
         classify_freshness(Market.CN, market_time, collected_at, is_open=True)
+
+
+@pytest.mark.parametrize(
+    ("market", "age_seconds"),
+    [(Market.CN, 0), (Market.HK, 86_400), (Market.US, 900)],
+)
+def test_交易日历关闭时有效时间无论年龄均为休市(
+    market: Market, age_seconds: int
+) -> None:
+    """交易日历关闭优先于有效年龄的任何新鲜度分级。"""
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    market_time = collected_at - timedelta(seconds=age_seconds)
+
+    assert classify_freshness(market, market_time, collected_at, is_open=False) == "CLOSED"
+
+
+@pytest.mark.parametrize(
+    ("market", "market_time", "collected_at"),
+    [
+        (
+            Market.CN,
+            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+        (
+            Market.HK,
+            datetime(2026, 7, 14, 9, 30),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+        (
+            Market.US,
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30),
+        ),
+    ],
+)
+def test_交易日历关闭时仍拒绝未来无时区或负年龄时间(
+    market: Market, market_time: datetime, collected_at: datetime
+) -> None:
+    """休市状态不能绕过未来时间、无时区和负年龄的基本时间校验。"""
+
+    with pytest.raises(FreshnessClassificationError):
+        classify_freshness(market, market_time, collected_at, is_open=False)
+
+
+@pytest.mark.parametrize(
+    ("state", "age_seconds", "expected"),
+    [
+        ("REALTIME", 5, True),
+        ("NEAR_REALTIME", 60, True),
+        ("DELAYED", 61, False),
+        ("STALE", 901, False),
+        ("CLOSED", 0, False),
+    ],
+)
+def test_仅有效时点的实时或近实时事实可用于当前预测(
+    state: str, age_seconds: int, expected: bool
+) -> None:
+    """延迟、过期和休市事实不得进入当前预测，裸状态字符串不是可用输入。"""
+
+    from stock_agent.domain import freshness
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    fact: 当前预测新鲜度事实 = {
+        "state": state,
+        "market_time": collected_at - timedelta(seconds=age_seconds),
+        "collected_at": collected_at,
+        "time_is_verifiable": True,
+    }
+
+    assert freshness.is_usable_for_current_prediction(fact) is expected
+
+
+@pytest.mark.parametrize(
+    ("state", "market_time", "collected_at"),
+    [
+        (
+            "REALTIME",
+            datetime(2026, 7, 14, 9, 30),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+        (
+            "NEAR_REALTIME",
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30),
+        ),
+        (
+            "REALTIME",
+            datetime(2026, 7, 14, 9, 30, 1, tzinfo=UTC),
+            datetime(2026, 7, 14, 9, 30, tzinfo=UTC),
+        ),
+    ],
+)
+def test_市场时间不可验证时实时状态也不得用于当前预测(
+    state: str, market_time: datetime, collected_at: datetime
+) -> None:
+    """无时区或未来市场时间即便被伪标为实时，也必须在研究入口被阻断。"""
+
+    from stock_agent.domain import freshness
+
+    fact: 当前预测新鲜度事实 = {
+        "state": state,
+        "market_time": market_time,
+        "collected_at": collected_at,
+        "time_is_verifiable": False,
+    }
+
+    assert freshness.is_usable_for_current_prediction(fact) is False
+
+
+def test_未知新鲜度状态不得用于当前预测() -> None:
+    """未知状态必须显式拒绝或返回不可用，不能被默认分支放行。"""
+
+    from stock_agent.domain import freshness
+
+    collected_at = datetime(2026, 7, 14, 9, 30, tzinfo=UTC)
+    fact: 当前预测新鲜度事实 = {
+        "state": "UNRECOGNIZED",
+        "market_time": collected_at,
+        "collected_at": collected_at,
+        "time_is_verifiable": True,
+    }
+
+    try:
+        usable = freshness.is_usable_for_current_prediction(fact)
+    except FreshnessClassificationError:
+        return
+
+    assert usable is False

```

