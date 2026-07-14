# 港股六位目录代码兼容修复报告

## 根因

`InstrumentIdentity` 的市场规则将港股显示代码硬编码为五位 ASCII 数字。HKEX 本地目录中存在六位显示代码时，合法的跨市场同显示代码身份会在领域校验阶段被拒绝。

## 最小修复

- 仅对 `Market.HK` 的 `InstrumentIdentity.display_code` 放宽为五位或六位 ASCII 数字。
- 保留五位港股标准显示格式。
- 未修改 Sina A 股映射；其边界仍要求 `Market.CN`、沪深交易所和六位 ASCII 数字。

## 测试证据

1. 修复前运行 `pytest tests/property/test_market_rules.py -q`：六位 HKEX 代码 `600000` 被拒绝，复现问题。
2. 补充属性测试：HKEX 接受五位和六位 ASCII 数字；拒绝其他长度、混合字符和全角数字；CN 五位数字和 US 六位纯数字仍被拒绝。
3. 修复后验证：
   - `pytest tests/property/test_market_rules.py --no-cov -q`：10 passed。
   - `pytest tests/failure/test_market_data_failures.py --no-cov -q`：67 passed，证明 Sina A 股映射边界未放宽。
   - `pytest tests/contract/test_market_data_contract.py --no-cov -q`：102 passed。
   - `pytest -q`：363 passed，覆盖率 88.31%。
   - `ruff check src/stock_agent/domain/market.py tests/property/test_market_rules.py`：通过。
   - `python tools/check_chinese_project_text.py`：发现既有的 `tests/failure/test_market_data_failures.py:89` 注释缺少简体中文说明；本次新增内容未触发该检查。

## 风险与边界

该兼容仅适用于 HKEX 本地目录身份；它不将六位代码解释为 A 股，也不会改变任何供应商的请求代码格式。
