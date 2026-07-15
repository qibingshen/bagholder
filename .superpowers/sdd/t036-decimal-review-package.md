# T036 Decimal 复审包

## 提交

f3392ac fix: support Decimal company action ratios

## 统计

 .superpowers/sdd/t036-decimal-fix-report.md | 47 +++++++++++++++++++++++++++++
 src/stock_agent/domain/market_rules.py      |  6 ++--
 tests/failure/test_market_data_failures.py  | 36 ++++++++++++++++++++--
 3 files changed, 84 insertions(+), 5 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/t036-decimal-fix-report.md b/.superpowers/sdd/t036-decimal-fix-report.md
new file mode 100644
index 0000000..34d6a12
--- /dev/null
+++ b/.superpowers/sdd/t036-decimal-fix-report.md
@@ -0,0 +1,47 @@
+# T036 公司行动复权比例 Decimal 兼容修复报告
+
+## 修复范围
+
+- `CompanyAction.adjustment_ratio` 明确接受有限且大于零的 `int`、`float` 与
+  `Decimal`，并将类型注解同步为这三类数值。
+- 校验不再依赖 `numbers.Real`；该抽象不会将 `Decimal` 视为实数，导致合法精确比例被误拒。
+- `bool` 保持显式拒绝，字符串、复数、非有限值、零和负数均继续统一以中文 `ValueError` 拒绝。
+- 本次只变更领域模型和测试，未访问网络、未生成预测、未发起交易。
+
+## TDD 证据
+
+先新增 `Decimal("1.1")` 可接受的失败用例，并执行：
+
+```powershell
+py -3.12 -m pytest -o addopts='' tests/failure/test_market_data_failures.py -k decimal -v
+```
+
+实现前得到 `1 failed, 63 deselected`：`Decimal("1.1")` 因未通过 `Real` 类型判断而被拒绝。
+
+随后以显式类型白名单完成最小实现，失败用例文件复验为 `64 passed`。拒绝覆盖保留并扩展为：
+
+- `True`、`False`
+- 字符串和复数
+- `float("nan")`、`float("inf")`
+- `Decimal("NaN")`、`Decimal("Infinity")`
+- 整数与 `Decimal` 的零及负数
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
+- Pytest：`69 passed`。
+- Ruff 格式检查：4 个文件均已格式化。
+- Ruff 静态检查：通过。
+- 简体中文检查：通过。
+
+## 风险与回滚
+
+- 允许 `Decimal` 后，调用方可保留十进制比例精度；领域对象不会把它转换为 `float`。
+- 可接受类型仅限 `int`、`float`、`Decimal`，不会因泛化数值协议而放宽至自定义数值或复数。
+- 如需回滚，仅回退本次提交即可；该提交没有外部副作用。
diff --git a/src/stock_agent/domain/market_rules.py b/src/stock_agent/domain/market_rules.py
index 0e126bf..ba1d837 100644
--- a/src/stock_agent/domain/market_rules.py
+++ b/src/stock_agent/domain/market_rules.py
@@ -1,17 +1,17 @@
 """集中执行市场时间、版本与跨币种可比较性规则。"""
 
 import math
 from collections.abc import Sequence
 from dataclasses import dataclass
 from datetime import date, datetime
-from numbers import Real
+from decimal import Decimal
 
 from stock_agent.domain.market import InstrumentIdentity, Market
 
 
 class PointInTimeViolation(ValueError):
     """表示数据在预测时点尚不可获得，必须停止相关计算。"""
 
 
 class NotComparableError(ValueError):
     """表示缺少同一时点的汇率或市场规则版本，禁止输出跨市场比较数字。"""
@@ -37,40 +37,40 @@ class TradingCalendar:
 
 @dataclass(frozen=True)
 class CompanyAction:
     """保存公司行动的来源与版本，使复权和历史分析能按当时事实重建。"""
 
     action_id: str
     action_type: str
     effective_at: datetime
     version_id: str
     source_id: str
-    adjustment_ratio: float | None = None
+    adjustment_ratio: int | float | Decimal | None = None
     security_id: InstrumentIdentity | None = None
     market: Market | None = None
 
     def __post_init__(self) -> None:
         if not all(
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
         if self.adjustment_ratio is not None:
             if (
                 isinstance(self.adjustment_ratio, bool)
-                or not isinstance(self.adjustment_ratio, Real)
+                or not isinstance(self.adjustment_ratio, (int, float, Decimal))
                 or not math.isfinite(self.adjustment_ratio)
                 or self.adjustment_ratio <= 0
             ):
                 raise ValueError("公司行动复权比例必须为有限正数的真实数值")
         if (
             self.security_id is not None
             and self.market is not None
             and self.security_id.market is not self.market
         ):
             raise ValueError("公司行动证券与市场必须一致")
diff --git a/tests/failure/test_market_data_failures.py b/tests/failure/test_market_data_failures.py
index 4f4739e..a392dd1 100644
--- a/tests/failure/test_market_data_failures.py
+++ b/tests/failure/test_market_data_failures.py
@@ -1,13 +1,14 @@
 """验证新浪代码规则拒绝不安全或不受支持的身份。"""
 
 from datetime import UTC, datetime
+from decimal import Decimal
 from pathlib import Path
 
 import pytest
 
 from stock_agent.adapters.market_data.sina_adapter import SinaDataSourceError, SinaHttpAdapter
 from stock_agent.adapters.market_data.sina_codes import (
     UnsupportedSinaCodeError,
     normalize_sina_code,
 )
 from stock_agent.application.versioning_service import ImmutableVersionError, VersioningService
@@ -246,22 +247,53 @@ def test_未带市场标识的非唯一显示代码必须拒绝解析() -> None:
 
     候选证券 = [
         InstrumentIdentity(Market.CN, "SZSE", "000001", "CNY"),
         InstrumentIdentity(Market.CN, "SSE", "000001", "CNY"),
     ]
 
     with pytest.raises(MarketRuleError, match="市场|交易所|非唯一"):
         resolve_instrument_identity(display_code="000001", candidates=候选证券)
 
 
-@pytest.mark.parametrize("复权比例", [True, False, "1", float("nan"), float("inf"), 0, -1])
-def test_公司行动拒绝不合法复权比例(复权比例: float) -> None:
+def test_公司行动接受有限正数的_decimal_复权比例() -> None:
+    """Decimal 有限正数可作为精确复权比例，避免二进制浮点误差。"""
+
+    action = CompanyAction(
+        action_id="split-20260714",
+        action_type="split",
+        effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
+        version_id="v1",
+        source_id="test-source",
+        adjustment_ratio=Decimal("1.1"),
+    )
+
+    assert action.adjustment_ratio == Decimal("1.1")
+
+
+@pytest.mark.parametrize(
+    "复权比例",
+    [
+        True,
+        False,
+        "1",
+        1 + 0j,
+        float("nan"),
+        float("inf"),
+        Decimal("NaN"),
+        Decimal("Infinity"),
+        0,
+        Decimal("0"),
+        -1,
+        Decimal("-1"),
+    ],
+)
+def test_公司行动拒绝不合法复权比例(复权比例: object) -> None:
     """复权比例必须为有限正数，不能让无效公司行动进入历史价格计算。"""
 
     with pytest.raises(ValueError, match="复权比例"):
         CompanyAction(
             action_id="split-20260714",
             action_type="split",
             effective_at=datetime(2026, 7, 14, 9, 0, tzinfo=UTC),
             version_id="v1",
             source_id="test-source",
             adjustment_ratio=复权比例,

```

