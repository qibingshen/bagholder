# T044 本地市场总览展示闭环报告

## 交付内容

- 新增 `MarketController`，只接收 `MarketService` 与调用方已持久化的
  `IngestedHistoricalDailyBar`；没有网络客户端、行情适配器或凭据服务入口。
- 新增市场总览模型，将市场状态、主要指数目录事实及其历史日线原样组合。
  日线保留来源、市场时间、采集时间、上游版本、工件版本和 `HISTORICAL`
  新鲜度，不生成指数价格、预测值或交易动作。
- 本地日历缺失、闭市/休市、延迟/过期、权限受限、验证证据不足时，分别进入
  `EMPTY`、`CLOSED`、`STALE`、`PERMISSION_DENIED` 或 `STALE`，且禁止实时展示
  与当前预测。主要指数没有本地历史日线时保留目录事实并显示明确空状态。

## TDD 记录

先新增 `tests/integration/test_market_controller.py`，在控制器模块尚不存在时运行：

```powershell
py -3.12 -m pytest -o addopts='' tests/integration/test_market_controller.py -q
```

红灯为 `10 failed`，失败原因均为预期的
`ModuleNotFoundError: No module named 'stock_agent.desktop.controllers'`。
随后以最小控制器、页面模型组合和本地日线过滤实现通过测试。

## 验证

- 目标集成测试：`10 passed`。
- 改动范围 Ruff：通过。
- 改动范围中文检查：控制器目录与 `tests/integration` 均通过。
- 全量 pytest：`319 passed, 10 failed`，失败均为既有的当前预测异常语义、
  `CompanyAction` 参数/复权辅助函数以及港股六码规则，与本任务文件无关。
- 全仓 Ruff：失败 2 项，均位于既有的
  `tools/check_chinese_project_text.py`（导入排序和长行）。
- 全仓中文检查：失败 1 项，位于既有的
  `tests/failure/test_market_data_failures.py:88` 注释缺少简体中文说明。
