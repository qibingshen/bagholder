# Task 3 新浪 HTTP 适配器报告

## 变更文件

- `src/stock_agent/adapters/market_data/sina_adapter.py`
- `tests/integration/test_single_market_daily_pipeline.py`
- `tests/failure/test_market_data_failures.py`

## 实现摘要

- 新增只读 `SinaHttpAdapter`，仅通过注入的 `http_get` 发起受控新浪 HTTP GET。
- 严格校验请求代码、GBK 响应、响应行、必要字段和日期时间；任一失败均抛出 `SinaDataSourceError`，不返回部分行情。
- 将沪深代码映射为 `Market.CN` 证券身份，以 `Asia/Shanghai` 构造市场时间，并调用 `classify_freshness` 生成新鲜度。
- 以原始响应的 SHA-256 生成非空新浪数据版本标识。

## TDD 证据

先新增适配器导入与边界测试，再运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
```

首次运行在收集阶段失败，原因是 `ModuleNotFoundError: No module named 'stock_agent.adapters.market_data.sina_adapter'`，证明测试覆盖了尚未实现的接口。完成最小实现后，同一命令通过 21 项测试。

## 验证命令

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_single_market_daily_pipeline.py tests/failure/test_market_data_failures.py -v
py -3.12 -m ruff format --check src tests
py -3.12 -m ruff check src tests
git diff --check
```

最终验证结果：21 passed；Ruff 格式检查通过；Ruff 静态检查通过；差异空白检查通过。

## 自检

- 未访问真实网络，测试读取器均为本地注入函数。
- 未实现历史日线、复权、公司行为、存储、凭据、券商、订单或自动交易能力。
- 未修改任务范围外的项目文件；工作区中既有的其他未提交变更未纳入本任务。

## 提交

本报告随提交 `feat: add sina a-share market data adapter` 一并提交；最终哈希以 Git 当前提交为准。

## Concerns

无。
