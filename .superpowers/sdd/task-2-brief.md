# Task 2：新鲜度与新浪代码规则

先完整阅读本文件；这是唯一任务要求来源。

## 目标

实现跨市场新鲜度分类和新浪 A 股请求代码规范化，为后续新浪 HTTP 适配器提供安全、不可绕过的规则。

## 文件

- 创建 `src/stock_agent/domain/freshness.py`
- 创建 `src/stock_agent/adapters/market_data/sina_codes.py`
- 创建或修改 `tests/property/test_freshness_rules.py`
- 创建或修改 `tests/failure/test_market_data_failures.py`

## 接口与规则

- `classify_freshness(market, market_time, collected_at, is_open)` 返回与既有 `Freshness.state` 兼容的状态字符串。
- 休市时一律为 `CLOSED`。
- 交易时段：CN 年龄 `<=5` 秒为 `REALTIME`；HK/US 年龄 `<=15` 秒为 `REALTIME`；超过实时阈值至 `60` 秒为 `NEAR_REALTIME`；超过 `60` 秒至 `900` 秒为 `DELAYED`；超过 `900` 秒为 `STALE`。
- 市场时间晚于采集时间、无时区时间或负年龄属于错误，不能被归类为新鲜行情。
- `normalize_sina_code(InstrumentIdentity) -> str` 只允许 `Market.CN`：`SSE` 映射 `sh{六码}`，`SZSE` 映射 `sz{六码}`；代码不是六位数字、交易所不受支持、市场不是 CN 时抛出 `UnsupportedSinaCodeError`。

## 约束

- 所有项目文字、注释、文档字符串与测试说明使用简体中文。
- 禁止 HTTP、供应商响应解析、存储、凭据和任何券商/下单/自动交易能力；只实现纯规则。
- 必须 TDD：先新增失败测试并运行确认失败，再最小实现。

## 测试

至少覆盖 CN/HK/US 的实时精确边界与超限、60 秒、900 秒、休市、负年龄；SSE/SZSE 合法映射和跨市场/非法代码拒绝。

运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

## 报告

完成后可只提交本任务文件，建议提交信息 `feat: enforce freshness and sina code rules`。把详细报告写入 `.superpowers/sdd/task-2-report.md`，列出失败/通过证据、文件、提交哈希、自检和 concerns；最终回复仅给状态、哈希、测试摘要和 concerns。
