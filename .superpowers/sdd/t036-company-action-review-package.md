# T036 公司行动复审包

## 提交

fcb0ba9 fix: 阻断跨证券公司行动复权

## 统计

 .superpowers/sdd/t036-company-action-fix-report.md | 45 ++++++++++++++
 src/stock_agent/domain/market_rules.py             | 17 ++++--
 tests/failure/test_market_data_failures.py         | 70 +++++++++++++++++++++-
 3 files changed, 127 insertions(+), 5 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/t036-company-action-fix-report.md b/.superpowers/sdd/t036-company-action-fix-report.md
new file mode 100644
index 0000000..3e25012
--- /dev/null
+++ b/.superpowers/sdd/t036-company-action-fix-report.md
@@ -0,0 +1,45 @@
+# T036 公司行动审查修复报告
+
+## 修复范围
+
+- `require_company_actions_for_adjustment` 现在逐条校验公司行动的 `security_id`。
+  缺少归属的兼容记录会被拒绝，不会作为目标证券的复权依据；任一行动属于其他证券时，
+  会以中文错误阻断混杂或全异证券的记录集。
+- `CompanyAction.adjustment_ratio` 仅接受有限且大于零的真实数值；显式拒绝 `bool`、
+  字符串、`NaN`、无穷大、零和负数，并统一返回中文 `ValueError`。
+- 未改变 `is_usable_for_current_prediction` 的布尔准入契约；未涉及视图层、网络请求、
+  预测交易或外部副作用。
+
+## TDD 证据
+
+先向失败用例增加以下覆盖并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -v
+```
+
+新增用例在实现前得到 `5 failed, 53 passed`：`True` 被错误接受，字符串触发了非领域
+`TypeError`，且未知归属、非目标证券、混杂证券行动集均未被阻断。
+
+最小实现后，同一失败用例文件为 `58 passed`；最终与时点完整性属性测试联合复验为
+`63 passed`。
+
+## 质量验证
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py tests/property/test_point_in_time_integrity.py -v
+py -3.12 -m ruff format --check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
+py -3.12 -m ruff check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
+py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain tests/failure/test_market_data_failures.py
+```
+
+- 最终失败用例与时点完整性属性测试：`63 passed`。
+- 指定范围 Ruff 格式检查和静态检查通过。
+- 指定范围简体中文检查通过。
+- 扩展运行 `tests/property/test_market_rules.py` 时仍有既有失败：其构造六码港股代码，
+  被既有五位港股代码规则拒绝；该失败与本修复无关。
+
+## 风险与回滚
+
+- 兼容的无 `security_id` 公司行动不再可用于目标证券复权；调用方须补齐可验证证券归属。
+- 如需回滚，仅回退本次提交即可；本次没有访问网络、生成预测或发起交易。
diff --git a/src/stock_agent/domain/market_rules.py b/src/stock_agent/domain/market_rules.py
index bf0c41b..0e126bf 100644
--- a/src/stock_agent/domain/market_rules.py
+++ b/src/stock_agent/domain/market_rules.py
@@ -1,16 +1,17 @@
 """集中执行市场时间、版本与跨币种可比较性规则。"""
 
 import math
 from collections.abc import Sequence
 from dataclasses import dataclass
 from datetime import date, datetime
+from numbers import Real
 
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
 class PointInTimeViolation(ValueError):
     """表示数据在预测时点尚不可获得，必须停止相关计算。"""
 
 
 class NotComparableError(ValueError):
     """表示缺少同一时点的汇率或市场规则版本，禁止输出跨市场比较数字。"""
@@ -52,24 +53,28 @@ class CompanyAction:
             (
                 self.action_id.strip(),
                 self.action_type.strip(),
                 self.version_id.strip(),
                 self.source_id.strip(),
             )
         ):
             raise ValueError("公司行动必须包含标识、类型、来源和版本")
         if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
             raise ValueError("公司行动生效时间必须带时区")
-        if self.adjustment_ratio is not None and (
-            not math.isfinite(self.adjustment_ratio) or self.adjustment_ratio <= 0
-        ):
-            raise ValueError("公司行动复权比例必须为有限正数")
+        if self.adjustment_ratio is not None:
+            if (
+                isinstance(self.adjustment_ratio, bool)
+                or not isinstance(self.adjustment_ratio, Real)
+                or not math.isfinite(self.adjustment_ratio)
+                or self.adjustment_ratio <= 0
+            ):
+                raise ValueError("公司行动复权比例必须为有限正数的真实数值")
         if (
             self.security_id is not None
             and self.market is not None
             and self.security_id.market is not self.market
         ):
             raise ValueError("公司行动证券与市场必须一致")
 
 
 @dataclass(frozen=True)
 class ExchangeRateQuote:
@@ -136,11 +141,15 @@ def effective_actions(
 
 def require_company_actions_for_adjustment(
     security_id: InstrumentIdentity,
     analysis_time: datetime,
     actions: Sequence[CompanyAction],
 ) -> list[CompanyAction]:
     """要求复权历史研究提供公司行动记录，不猜测或补造缺失数据。"""
 
     if not actions:
         raise PointInTimeViolation("公司行动缺失，复权历史研究不可用")
+    if any(action.security_id is None for action in actions):
+        raise PointInTimeViolation("公司行动缺少证券归属，不能用于目标证券复权")
+    if any(action.security_id != security_id for action in actions):
+        raise PointInTimeViolation("公司行动证券与目标证券不一致，不能跨证券复权")
     return effective_actions(actions, analysis_time)
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index 5fa2c5d..4f4739e 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -246,21 +246,21 @@ def test_未带市场标识的非唯一显示代码必须拒绝解析() -> None:
 
     候选证券 = [
         InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
         InstrumentIdentity(Market.CN, "SSE", "000001", "CNY"),
     ]
 
     with pytest.raises(MarketRuleError, match="市场|交易所|非唯一"):
         resolve_instrument_identity(display_code="000001", candidates=候选证券)
 
 
-@pytest.mark.parametrize("复权比例", [0, -1, float("inf")])
+@pytest.mark.parametrize("复权比例", [True, False, "1", float("nan"), float("inf"), 0, -1])
 def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
     """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""
 
     with pytest.raises(ValueError, match="复权比例"):
         CompanyAction(
             action_id="split-20260714",
             action_type="split",
             effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
             version_id="v1",
             source_id="test-source",
@@ -312,20 +312,88 @@ def test_复权历史研究在公司行动记录缺失时明确拒绝() -> None:
     )
 
     with pytest.raises(PointInTimeViolation, match="公司行动.*缺失|不可用"):
         require_company_actions_for_adjustment(
             security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
             analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
             actions=[],
         )
 
 
+@pytest.mark.parametrize(
+    "行动证券",
+    [
+        None,
+        InstrumentIdentity(Market.CN, "SSE", "600519", "CNY"),
+    ],
+)
+def test_复权历史研究拒绝未知或不属于目标证券的公司行动(
+    行动证券: InstrumentIdentity | None,
+) -> None:
+    """未知归属和其他证券的行动都不能充当目标证券的复权依据。"""
+
+    from stock_agent.domain.market_rules import (
+        PointInTimeViolation,
+        require_company_actions_for_adjustment,
+    )
+
+    with pytest.raises(PointInTimeViolation, match="证券|归属|不一致|缺失"):
+        require_company_actions_for_adjustment(
+            security_id=InstrumentIdentity(Market.CN, "SSE", "600000", "CNY"),
+            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
+            actions=[
+                CompanyAction(
+                    action_id="split-20260714",
+                    action_type="split",
+                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                    version_id="v1",
+                    source_id="test-source",
+                    security_id=行动证券,
+                )
+            ],
+        )
+
+
+def test_复权历史研究拒绝混入其他证券行动的记录集() -> None:
+    """混杂行动集不能借由一条目标证券记录绕过跨证券归属审查。"""
+
+    from stock_agent.domain.market_rules import (
+        PointInTimeViolation,
+        require_company_actions_for_adjustment,
+    )
+
+    目标证券 = InstrumentIdentity(Market.CN, "SSE", "600000", "CNY")
+    with pytest.raises(PointInTimeViolation, match="证券|不一致"):
+        require_company_actions_for_adjustment(
+            security_id=目标证券,
+            analysis_time=datetime(2026, 7, 14, 15, 0, tzinfo=UTC),
+            actions=[
+                CompanyAction(
+                    action_id="split-target",
+                    action_type="split",
+                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                    version_id="v1",
+                    source_id="test-source",
+                    security_id=目标证券,
+                ),
+                CompanyAction(
+                    action_id="split-other",
+                    action_type="split",
+                    effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+                    version_id="v1",
+                    source_id="test-source",
+                    security_id=InstrumentIdentity(Market.CN, "SSE", "600519", "CNY"),
+                ),
+            ],
+        )
+
+
 @pytest.mark.parametrize("dataset", ["market-data-raw", "prediction-snapshots"])
 def test_原始行情和预测快照拒绝静默覆盖(dataset: str, local_data_root: Path) -> None:
     """相同版本标识重写必须失败，保留可追溯的既有事实。"""
 
     service = VersioningService(local_data_root)
     service.commit_bytes(
         dataset=dataset,
         version_id="v1",
         content=b"first",
         source_id="test-source",

```

