# Task 1：行情适配器协议与注册表

这是“新浪与 Finnhub 多数据源行情接入”计划的第一项。你必须先阅读本文件，再开始工作。

## 目标

建立独立于供应商的行情适配器协议与注册表。核心服务不能依赖新浪、Finnhub 或其他供应商的字段。

## 文件

- 创建 `src/stock_agent/adapters/market_data/base.py`
- 创建 `src/stock_agent/adapters/market_data/registry.py`
- 创建 `src/stock_agent/adapters/market_data/__init__.py`
- 创建或修改 `tests/contract/test_market_data_contract.py`

## 所需接口

- `SourceCapability(source_id, markets, credential_required, supports_realtime)`。
- `NormalizedQuote` 必须带规范化证券身份、价格、来源、带时区市场时间、带时区采集时间和非空数据版本。
- `MarketDataAdapter` 协议暴露 `capability` 和 `fetch_quotes(codes, collected_at)`。
- `MarketDataRegistry.register(adapter)`：来源标识重复时抛出 `DuplicateSourceError`；`get(source_id)`：未知来源抛出明确错误。

## 强制约束

- 代码、文档字符串、注释、测试说明使用简体中文。
- 行情溯源字段缺失不得构造 `NormalizedQuote`。
- 不实现 HTTP、供应商解析、数据持久化、券商能力、交易能力或 Finnhub 调用。
- 必须先写失败测试并实际运行确认失败，再写最小实现。

## 测试要求

最少覆盖：注册并获取适配器；重复来源被拒绝；未知来源被拒绝；市场时间、采集时间或数据版本缺失被拒绝。

运行命令：

```powershell
py -3.12 -m pytest -o addopts='' tests/contract/test_market_data_contract.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
```

## 提交与报告

可只提交本任务涉及的文件，提交信息为 `feat: add market data adapter registry`。
将完整报告写入 `.superpowers/sdd/task-1-report.md`：列出新增/修改文件、失败测试证据、通过测试命令与结果、提交哈希、自检结论和未解决问题。最终回复仅返回 `DONE`、提交哈希、测试摘要和 concerns。
