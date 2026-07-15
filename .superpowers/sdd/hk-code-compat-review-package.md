# 港股目录码兼容审查包

## 提交

9316cd0 fix: accept hk six digit catalog codes

## 统计

 .superpowers/sdd/hk-code-compat-report.md | 27 +++++++++++++
 src/stock_agent/domain/market.py          |  7 +++-
 tests/property/test_market_rules.py       | 67 +++++++++++++++++++++++++++++++
 3 files changed, 99 insertions(+), 2 deletions(-)

## 差异

```diff
diff --git a/.superpowers/sdd/hk-code-compat-report.md b/.superpowers/sdd/hk-code-compat-report.md
new file mode 100644
index 0000000..80f616d
--- /dev/null
+++ b/.superpowers/sdd/hk-code-compat-report.md
@@ -0,0 +1,27 @@
+# 港股六位目录代码兼容修复报告
+
+## 根因
+
+`InstrumentIdentity` 的市场规则将港股显示代码硬编码为五位 ASCII 数字。HKEX 本地目录中存在六位显示代码时，合法的跨市场同显示代码身份会在领域校验阶段被拒绝。
+
+## 最小修复
+
+- 仅对 `Market.HK` 的 `InstrumentIdentity.display_code` 放宽为五位或六位 ASCII 数字。
+- 保留五位港股标准显示格式。
+- 未修改 Sina A 股映射；其边界仍要求 `Market.CN`、沪深交易所和六位 ASCII 数字。
+
+## 测试证据
+
+1. 修复前运行 `pytest tests/property/test_market_rules.py -q`：六位 HKEX 代码 `600000` 被拒绝，复现问题。
+2. 补充属性测试：HKEX 接受五位和六位 ASCII 数字；拒绝其他长度、混合字符和全角数字；CN 五位数字和 US 六位纯数字仍被拒绝。
+3. 修复后验证：
+   - `pytest tests/property/test_market_rules.py --no-cov -q`：10 passed。
+   - `pytest tests/failure/test_market_data_failures.py --no-cov -q`：67 passed，证明 Sina A 股映射边界未放宽。
+   - `pytest tests/contract/test_market_data_contract.py --no-cov -q`：102 passed。
+   - `pytest -q`：363 passed，覆盖率 88.31%。
+   - `ruff check src/stock_agent/domain/market.py tests/property/test_market_rules.py`：通过。
+   - `python tools/check_chinese_project_text.py`：发现既有的 `tests/failure/test_market_data_failures.py:89` 注释缺少简体中文说明；本次新增内容未触发该检查。
+
+## 风险与边界
+
+该兼容仅适用于 HKEX 本地目录身份；它不将六位代码解释为 A 股，也不会改变任何供应商的请求代码格式。
diff --git a/src/stock_agent/domain/market.py b/src/stock_agent/domain/market.py
index 5f44c54..337cc8b 100644
--- a/src/stock_agent/domain/market.py
+++ b/src/stock_agent/domain/market.py
@@ -131,22 +131,25 @@ def validate_instrument_identity(security_id: InstrumentIdentity) -> InstrumentI
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
-    if security_id.market is Market.HK and not _is_ascii_digits(security_id.display_code, 5):
-        raise MarketRuleError("香港市场证券代码必须为五位 ASCII 数字")
+    if security_id.market is Market.HK and not (
+        _is_ascii_digits(security_id.display_code, 5)
+        or _is_ascii_digits(security_id.display_code, 6)
+    ):
+        raise MarketRuleError("香港市场证券代码必须为五位或六位 ASCII 数字")
     if security_id.market is Market.US and not _is_us_code(security_id.display_code):
         raise MarketRuleError("美国市场证券代码格式无效")
     return security_id
 
 
 def _is_ascii_digits(value: str, length: int) -> bool:
     """限制固定长度 ASCII 数字，避免全角数字或混合字符造成歧义。"""
 
     return len(value) == length and value.isascii() and value.isdigit()
 
diff --git a/tests/property/test_market_rules.py b/tests/property/test_market_rules.py
new file mode 100644
index 0000000..34329b6
--- /dev/null
+++ b/tests/property/test_market_rules.py
@@ -0,0 +1,67 @@
+"""验证三市场身份、时区和币种比较的基础规则。"""
+
+import pytest
+
+
+def test_证券代码必须与市场共同构成身份() -> None:
+    """相同显示代码在不同市场不能被静默视为同一证券。"""
+
+    from stock_agent.domain.market import InstrumentIdentity, Market
+
+    cn = InstrumentIdentity(market=Market.CN, exchange="SSE", display_code="600000", currency="CNY")
+    hk = InstrumentIdentity(
+        market=Market.HK, exchange="HKEX", display_code="600000", currency="HKD"
+    )
+
+    assert cn != hk
+    assert cn.market_timezone == "Asia/Shanghai"
+    assert hk.market_timezone == "Asia/Hong_Kong"
+
+
+def test_跨币种比较没有同一时点汇率时必须拒绝() -> None:
+    """缺少可用汇率时不得输出伪精确的跨市场比较数字。"""
+
+    from stock_agent.domain.market import CurrencyComparison, MarketRuleError
+
+    with pytest.raises(MarketRuleError, match="汇率"):
+        CurrencyComparison.compare(100.0, "CNY", 10.0, "USD", exchange_rate=None)
+
+
+@pytest.mark.parametrize("display_code", ["00001", "600000"])
+def test_港股目录接受五位或六位_ascii_数字代码(display_code: str) -> None:
+    """港交所本地目录兼容六位编码，同时保留五位标准显示格式。"""
+
+    from stock_agent.domain.market import InstrumentIdentity, Market
+
+    identity = InstrumentIdentity(Market.HK, "HKEX", display_code, "HKD")
+
+    assert identity.display_code == display_code
+
+
+@pytest.mark.parametrize("display_code", ["0000", "0000000", "0000A", "００００１"])
+def test_港股目录拒绝非五或六位_ascii_数字代码(display_code: str) -> None:
+    """港股目录代码不能因兼容性要求而放宽长度或 ASCII 边界。"""
+
+    from stock_agent.domain.market import InstrumentIdentityInput, Market, MarketRuleError
+
+    with pytest.raises(MarketRuleError):
+        InstrumentIdentityInput(Market.HK, "HKEX", display_code, "HKD").to_identity()
+
+
+@pytest.mark.parametrize(
+    ("market", "exchange", "display_code", "currency"),
+    [
+        ("CN", "SSE", "00001", "CNY"),
+        ("US", "NASDAQ", "600000", "USD"),
+    ],
+)
+def test_港股目录兼容不放宽其他市场代码规则(
+    market: str, exchange: str, display_code: str, currency: str
+) -> None:
+    """仅港股目录可兼容六位数字，A 股和美股规则必须保持原有边界。"""
+
+    from stock_agent.domain.market import InstrumentIdentityInput, Market, MarketRuleError
+
+    actual_market = Market[market]
+    with pytest.raises(MarketRuleError):
+        InstrumentIdentityInput(actual_market, exchange, display_code, currency).to_identity()

```

