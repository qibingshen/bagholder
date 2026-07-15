# Task 3：新浪 HTTP 适配器与原始响应边界

先完整阅读本文件；这是唯一需求来源。

## 目标

实现只读新浪 A 股报价适配器。它只发起受控 HTTP GET 请求、解析新浪响应为既有 `NormalizedQuote`，并在不完整或异常数据时拒绝产出量化行情。

## 文件

- 创建 `src/stock_agent/adapters/market_data/sina_adapter.py`
- 创建或修改 `tests/integration/test_single_market_daily_pipeline.py`
- 创建或修改 `tests/failure/test_market_data_failures.py`

## 接口与精确行为

- `SinaHttpAdapter(http_get: Callable[[str], bytes])`；网络读取器由调用方注入，测试绝不访问公网。
- `fetch_quotes(codes: list[str], collected_at: datetime) -> list[NormalizedQuote]`。
- 仅允许使用 `http://hq.sinajs.cn/list={逗号分隔代码}`；代码必须已是 `sh`/`sz` 加六码 ASCII 数字格式，否则拒绝。
- 原始字节按 GBK 解码。解析的响应行必须具备证券名称、可转换价格、日期和时间；市场时间用 `Asia/Shanghai` 生成带时区时间。
- 每条返回报价：`source_id='sina'`，数据版本为非空新浪响应版本标识，新鲜度必须通过 Task 2 的 `classify_freshness` 计算，证券标识必须为 `Market.CN`。
- HTTP 读取器异常、GBK 解码失败、格式错误、缺字段、日期/时间不可解析或市场时间无效时，抛出项目定义的数据源错误；不得返回部分报价。

## 约束

- 项目代码、注释、文档字符串、测试说明全部用简体中文。
- 不使用真实网络、不实现历史日线、复权、公司行动、存储、凭据、券商、订单或自动交易。
- 必须先写失败测试并实际运行确认失败；再写最小实现。

## 测试

最少覆盖：请求 URL 精确值、GBK 样本成功解析、来源/市场时间/版本/新鲜度完整；空代码、非法代码、HTTP 异常、GBK 异常、字段缺失、无效时间均拒绝；异常时没有部分结果。

运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

## 报告

完成后可只提交本任务文件，建议提交信息 `feat: add sina a-share market data adapter`。完整报告写入 `.superpowers/sdd/task-3-report.md`，包含文件、失败/通过证据、命令、提交、自检和 concerns；最终仅回复状态、哈希、测试摘要、concerns。
