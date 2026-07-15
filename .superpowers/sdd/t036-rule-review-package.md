# T036 领域规则审查包

## 提交

61bb77a feat: 补充市场拒绝与公司行动规则

## 统计

 .../sdd/t036-rule-implementation-report.md         |  46 +++++++
 src/stock_agent/domain/freshness.py                |  21 +++
 src/stock_agent/domain/market_rules.py             | 146 +++++++++++++++++++++
 tests/failure/test_market_data_failures.py         |   6 +-
 4 files changed, 216 insertions(+), 3 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/t036-rule-implementation-report.md b/.superpowers/sdd/t036-rule-implementation-report.md
new file mode 100644
index 0000000..57886e7
--- /dev/null
+++ b/.superpowers/sdd/t036-rule-implementation-report.md
@@ -0,0 +1,46 @@
+# T036 后续市场规则实现报告
+
+## 实现说明
+
+- 保留 `is_usable_for_current_prediction` 的布尔返回契约；新增
+  `require_usable_for_current_prediction` 作为强制准入入口。该入口会对延迟、过期、休市、未知状态和时点不可验证的行情抛出
+  `FreshnessClassificationError`，并给出中文拒绝原因。
+- `CompanyAction` 增加可选的 `adjustment_ratio`、`security_id` 与 `market`，保持既有构造调用兼容；已校验复权比例为有限正数、有效时间带时区、证券身份与市场一致。
+- 新增 `require_company_actions_for_adjustment`。复权历史研究缺少公司行动记录时抛出
+  `PointInTimeViolation`，不会生成或猜测公司行动。
+- 失败用例改为调用严格准入入口，保留既有布尔接口的 T041 契约测试。
+
+## TDD 红灯证据
+
+先执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
+```
+
+结果为 `42 passed, 9 failed`。失败分别来自当前预测无法给出领域拒绝原因、公司行动新增字段缺失，以及
+`require_company_actions_for_adjustment` 不可导入，符合本任务的预期红灯范围。
+
+## 绿灯与质量验证
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
+py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/property/test_point_in_time_integrity.py -v
+py -3.12 -m ruff format --check src/stock_agent/domain/freshness.py src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py
+py -3.12 -m ruff check src/stock_agent/domain/freshness.py src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py
+py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain
+```
+
+- 失败用例：`51 passed`。
+- 新鲜度与公司行动相关属性测试：`71 passed`。
+- 改动范围 Ruff 格式与静态检查均通过。
+- 改动范围中文检查通过。
+
+## 仓库级验证与回滚
+
+- 全量 pytest 结果为 `338 passed, 1 failed`；失败为既有
+  `tests/property/test_market_rules.py::test_证券代码跨市场必须不同身份`，它构造六位港股代码，已被现有五位港股代码规则拒绝，与本任务改动无关。
+- 全仓 Ruff 格式检查仍报告既有 `src/stock_agent/desktop/pages/_recovery.py` 与
+  `tests/property/test_freshness_rules.py` 需要格式化；全仓 Ruff 静态检查在本任务改动后未报告新增问题。
+- 全仓中文检查仍报告既有 `tests/failure/test_market_data_failures.py:88` 的类型忽略注释缺少中文说明；本任务新增文字均为简体中文。
+- 如需回滚，仅回退本任务提交即可；无外部数据、预测数值、券商或交易副作用。
diff --git a/src/stock_agent/domain/freshness.py b/src/stock_agent/domain/freshness.py
index 605fefd..efdd284 100644
--- a/src/stock_agent/domain/freshness.py
+++ b/src/stock_agent/domain/freshness.py
@@ -35,20 +35,41 @@ def is_usable_for_current_prediction(fact: CurrentPredictionFreshnessFact) -> bo
 
     market_time = fact.get("market_time")
     collected_at = fact.get("collected_at")
     if not isinstance(market_time, datetime) or not isinstance(collected_at, datetime):
         raise FreshnessClassificationError("当前预测新鲜度事实必须包含有效的市场时间和采集时间")
 
     calculate_age_seconds(market_time, collected_at)
     return True
 
 
+def require_usable_for_current_prediction(fact: CurrentPredictionFreshnessFact) -> None:
+    """强制校验行情能否用于当前预测，并给出不可用的领域原因。"""
+
+    if fact.get("time_is_verifiable") is not True:
+        raise FreshnessClassificationError("市场时间不可验证，当前预测不可用")
+
+    market_time = fact.get("market_time")
+    collected_at = fact.get("collected_at")
+    if not isinstance(market_time, datetime) or not isinstance(collected_at, datetime):
+        raise FreshnessClassificationError("当前预测新鲜度事实必须包含有效的市场时间和采集时间")
+    calculate_age_seconds(market_time, collected_at)
+
+    state = fact.get("state")
+    if state in {"DELAYED", "STALE"}:
+        raise FreshnessClassificationError("市场行情过期，当前预测不可用")
+    if state == "CLOSED":
+        raise FreshnessClassificationError("市场休市，当前预测不可用")
+    if state not in {"REALTIME", "NEAR_REALTIME"}:
+        raise FreshnessClassificationError("市场行情状态不可用，当前预测不可用")
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
 
diff --git a/src/stock_agent/domain/market_rules.py b/src/stock_agent/domain/market_rules.py
new file mode 100644
index 0000000..bf0c41b
--- /dev/null
+++ b/src/stock_agent/domain/market_rules.py
@@ -0,0 +1,146 @@
+"""集中执行市场时间、版本与跨币种可比较性规则。"""
+
+import math
+from collections.abc import Sequence
+from dataclasses import dataclass
+from datetime import date, datetime
+
+from stock_agent.domain.market import InstrumentIdentity, Market
+
+
+class PointInTimeViolation(ValueError):
+    """表示数据在预测时点尚不可获得，必须停止相关计算。"""
+
+
+class NotComparableError(ValueError):
+    """表示缺少同一时点的汇率或市场规则版本，禁止输出跨市场比较数字。"""
+
+
+@dataclass(frozen=True)
+class TradingCalendar:
+    """记录一个市场在指定版本中的交易日，避免历史查询混用后来修订的日历。"""
+
+    market: str
+    version_id: str
+    trading_days: frozenset[date]
+
+    def __post_init__(self) -> None:
+        if not self.market.strip() or not self.version_id.strip():
+            raise ValueError("交易日历必须包含市场与版本标识")
+        object.__setattr__(self, "trading_days", frozenset(self.trading_days))
+
+    def is_trading_day(self, day: date) -> bool:
+        """判断日期是否属于该版本日历的有效交易日。"""
+        return day in self.trading_days
+
+
+@dataclass(frozen=True)
+class CompanyAction:
+    """保存公司行动的来源与版本，使复权和历史分析能按当时事实重建。"""
+
+    action_id: str
+    action_type: str
+    effective_at: datetime
+    version_id: str
+    source_id: str
+    adjustment_ratio: float | None = None
+    security_id: InstrumentIdentity | None = None
+    market: Market | None = None
+
+    def __post_init__(self) -> None:
+        if not all(
+            (
+                self.action_id.strip(),
+                self.action_type.strip(),
+                self.version_id.strip(),
+                self.source_id.strip(),
+            )
+        ):
+            raise ValueError("公司行动必须包含标识、类型、来源和版本")
+        if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
+            raise ValueError("公司行动生效时间必须带时区")
+        if self.adjustment_ratio is not None and (
+            not math.isfinite(self.adjustment_ratio) or self.adjustment_ratio <= 0
+        ):
+            raise ValueError("公司行动复权比例必须为有限正数")
+        if (
+            self.security_id is not None
+            and self.market is not None
+            and self.security_id.market is not self.market
+        ):
+            raise ValueError("公司行动证券与市场必须一致")
+
+
+@dataclass(frozen=True)
+class ExchangeRateQuote:
+    """保存有可得时间的汇率快照，禁止以晚到汇率计算早期跨市场结果。"""
+
+    base_currency: str
+    quote_currency: str
+    rate: float
+    market_time: datetime
+    available_at: datetime
+    version_id: str
+
+    def __post_init__(self) -> None:
+        if not all(
+            (self.base_currency.strip(), self.quote_currency.strip(), self.version_id.strip())
+        ):
+            raise ValueError("汇率必须包含币种与版本标识")
+        if self.rate <= 0:
+            raise ValueError("汇率必须为正数")
+        if self.market_time.tzinfo is None or self.available_at.tzinfo is None:
+            raise ValueError("汇率时间必须带时区")
+
+
+def ensure_available_at(
+    prediction_time: datetime, available_at: datetime, artifact_name: str
+) -> None:
+    """拒绝晚于预测时点的数据，防止训练、验证和回测泄漏未来信息。"""
+    if available_at > prediction_time:
+        raise PointInTimeViolation(f"{artifact_name} 在预测时点后才可获得")
+
+
+def compare_currency_at(
+    left: float,
+    left_currency: str,
+    right: float,
+    right_currency: str,
+    exchange_rate: ExchangeRateQuote | None,
+    analysis_time: datetime | None = None,
+) -> float:
+    """仅在同币种或存在有效汇率时计算金额比较。"""
+    if right == 0:
+        raise NotComparableError("比较基准为零，结果不可比较")
+    if left_currency == right_currency:
+        return left / right
+    if exchange_rate is None or analysis_time is None:
+        raise NotComparableError("缺少同一时点可用汇率，跨市场结果不可比较")
+    if (
+        exchange_rate.base_currency != right_currency
+        or exchange_rate.quote_currency != left_currency
+    ):
+        raise NotComparableError("汇率币种方向与比较对象不匹配，跨市场结果不可比较")
+    ensure_available_at(analysis_time, exchange_rate.available_at, "汇率")
+    return left / (right * exchange_rate.rate)
+
+
+def effective_actions(
+    actions: Sequence[CompanyAction], analysis_time: datetime
+) -> list[CompanyAction]:
+    """仅返回分析时点已生效的公司行动；未来行动会阻断计算。"""
+    if any(action.effective_at > analysis_time for action in actions):
+        raise PointInTimeViolation("公司行动在分析时点后才生效")
+    return list(actions)
+
+
+def require_company_actions_for_adjustment(
+    security_id: InstrumentIdentity,
+    analysis_time: datetime,
+    actions: Sequence[CompanyAction],
+) -> list[CompanyAction]:
+    """要求复权历史研究提供公司行动记录，不猜测或补造缺失数据。"""
+
+    if not actions:
+        raise PointInTimeViolation("公司行动缺失，复权历史研究不可用")
+    return effective_actions(actions, analysis_time)
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index d96f625..5fa2c5d 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -6,21 +6,21 @@ from pathlib import Path
 import pytest
 
 from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
 from stock_agent.adapters.market_data.sina_codes import (
     UnsupportedSinaCodeError,
     normalize_sina_code,
 )
 from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
 from stock_agent.domain.freshness import (
     FreshnessClassificationError,
-    is_usable_for_current_prediction,
+    require_usable_for_current_prediction,
 )
 from stock_agent.domain.market import (
     InstrumentIdentity,
     InstrumentIdentityInput,
     Market,
     MarketRuleError,
 )
 from stock_agent.domain.market_rules import CompanyAction
 
 
@@ -190,35 +190,35 @@ def test_标准化历史日线缺少任一契约字段时整批拒绝且不产
 
     assert not (local_data_root / "artifacts" / "market-data-raw").exists()
     assert not (local_data_root / "artifacts" / "market-data-normalized").exists()
 
 
 @pytest.mark.parametrize("状态", ["DELAYED", "STALE", "CLOSED"])
 def test_当前预测拒绝过期或休市行情并给出不可用原因(状态: str) -> None:
     """当前预测入口必须把不可用原因显式反馈给调用方，不能只返回裸布尔值。"""
 
     with pytest.raises(FreshnessClassificationError, match="过期|不可用"):
-        is_usable_for_current_prediction(
+        require_usable_for_current_prediction(
             {
                 "state": 状态,
                 "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                 "collected_at": datetime(2026, 7, 14, 9, 16, tzinfo=UTC),
                 "time_is_verifiable": True,
             }
         )
 
 
 def test_当前预测拒绝市场时间不可验证行情并给出不可用原因() -> None:
     """即使状态标为实时，市场时间不可验证也必须明确拒绝当前预测。"""
 
     with pytest.raises(FreshnessClassificationError, match="不可验证|不可用"):
-        is_usable_for_current_prediction(
+        require_usable_for_current_prediction(
             {
                 "state": "REALTIME",
                 "market_time": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                 "collected_at": datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
                 "time_is_verifiable": False,
             }
         )
 
 
 @pytest.mark.parametrize(

```

