# T036 Decimal 有限性最终复审包

## 提交

581bda0 fix: validate Decimal ratio finite without float conversion

## 统计

 .superpowers/sdd/t036-decimal-finite-report.md | 37 ++++++++++++++++++++++++++
 src/stock_agent/domain/market_rules.py         | 16 ++++++-----
 tests/failure/test_market_data_failures.py     | 18 +++++++++++++
 3 files changed, 65 insertions(+), 6 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/t036-decimal-finite-report.md b/.superpowers/sdd/t036-decimal-finite-report.md
new file mode 100644
index 0000000..540c1b1
--- /dev/null
+++ b/.superpowers/sdd/t036-decimal-finite-report.md
@@ -0,0 +1,37 @@
+# T036 Decimal 复权比例有限性修复报告
+
+## 修复范围
+
+- `CompanyAction.adjustment_ratio` 对 `Decimal` 使用 `is_finite()` 判断有限性，随后仅接受大于零的值；不再将 `Decimal` 转换为 `float`。
+- `float` 保持使用 `math.isfinite()`；非布尔 `int` 直接按正值判断；`bool`、其他类型、非有限值、零和负值统一抛出 `ValueError`。
+- 未修改证券与市场身份绑定、公司行动缺失阻断或其他市场规则；未访问网络、未生成预测、未发起交易。
+
+## TDD 证据
+
+先新增极大但有限的 `Decimal("1E+999999")` 接受用例，以及 `Decimal("-Infinity")`、`Decimal("sNaN")` 拒绝用例；实现前运行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k '极大但有限的_decimal' -v
+```
+
+结果为 `1 failed, 66 deselected`：极大有限 Decimal 被原有 `math.isfinite()` 路径错误拒绝。完成按类型的最小校验实现后，Decimal 相关用例运行结果为 `16 passed, 51 deselected`。
+
+## 验证结果
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py tests/property/test_point_in_time_integrity.py -v
+py -3.12 -m ruff format --check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
+py -3.12 -m ruff check src/stock_agent/domain/market_rules.py tests/failure/test_market_data_failures.py tests/property/test_market_rules.py tests/property/test_point_in_time_integrity.py
+py -3.12 tools/check_chinese_project_text.py src/stock_agent/domain tests/failure/test_market_data_failures.py
+```
+
+- Pytest：`72 passed`。
+- Ruff 格式检查：4 个文件均已格式化。
+- Ruff 静态检查：通过。
+- 简体中文检查：通过。
+
+## 风险与回滚
+
+- 该实现保留 Decimal 的任意有限精度与数量级，不依赖可能溢出的浮点转换。
+- `sNaN` 先由 `is_finite()` 拒绝，避免对该值执行比较并触发 Decimal 上下文异常。
+- 如需回滚，仅回退本次提交；本次变更无外部副作用。
diff --git a/src/stock_agent/domain/market_rules.py b/src/stock_agent/domain/market_rules.py
index ba1d837..ffb4aef 100644
--- a/src/stock_agent/domain/market_rules.py
+++ b/src/stock_agent/domain/market_rules.py
@@ -54,26 +54,30 @@ class CompanyAction:
                 self.action_id.strip(),
                 self.action_type.strip(),
                 self.version_id.strip(),
                 self.source_id.strip(),
             )
         ):
             raise ValueError("公司行动必须包含标识、类型、来源和版本")
         if self.effective_at.tzinfo is None or self.effective_at.utcoffset() is None:
             raise ValueError("公司行动生效时间必须带时区")
         if self.adjustment_ratio is not None:
-            if (
-                isinstance(self.adjustment_ratio, bool)
-                or not isinstance(self.adjustment_ratio, (int, float, Decimal))
-                or not math.isfinite(self.adjustment_ratio)
-                or self.adjustment_ratio <= 0
-            ):
+            ratio = self.adjustment_ratio
+            if isinstance(ratio, Decimal):
+                is_valid_ratio = ratio.is_finite() and ratio > 0
+            elif isinstance(ratio, float):
+                is_valid_ratio = math.isfinite(ratio) and ratio > 0
+            elif isinstance(ratio, int) and not isinstance(ratio, bool):
+                is_valid_ratio = ratio > 0
+            else:
+                is_valid_ratio = False
+            if not is_valid_ratio:
                 raise ValueError("公司行动复权比例必须为有限正数的真实数值")
         if (
             self.security_id is not None
             and self.market is not None
             and self.security_id.market is not self.market
         ):
             raise ValueError("公司行动证券与市场必须一致")
 
 
 @dataclass(frozen=True)
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index a392dd1..681215b 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -262,31 +262,49 @@ def test_公司行动接受有限正数的_decimal_复权比例() -> None:
         action_type="split",
         effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
         version_id="v1",
         source_id="test-source",
         adjustment_ratio=Decimal("1.1"),
     )
 
     assert action.adjustment_ratio == Decimal("1.1")
 
 
+def test_公司行动接受极大但有限的_decimal_复权比例() -> None:
+    """有限 Decimal 不应因浮点转换溢出而被拒绝。"""
+
+    ratio = Decimal("1E+999999")
+    action = CompanyAction(
+        action_id="split-20260714",
+        action_type="split",
+        effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+        version_id="v1",
+        source_id="test-source",
+        adjustment_ratio=ratio,
+    )
+
+    assert action.adjustment_ratio == ratio
+
+
 @pytest.mark.parametrize(
     "复权比例",
     [
         True,
         False,
         "1",
         1 + 0j,
         float("nan"),
         float("inf"),
         Decimal("NaN"),
         Decimal("Infinity"),
+        Decimal("-Infinity"),
+        Decimal("sNaN"),
         0,
         Decimal("0"),
         -1,
         Decimal("-1"),
     ],
 )
 def test_公司行动拒绝不合法复权比例(复权比例: object) -> None:
     """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""
 
     with pytest.raises(ValueError, match="复权比例"):

```

