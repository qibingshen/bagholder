# T041 行情新鲜度与当前预测阻断规则报告

## 实现说明

在 `src/stock_agent/domain/freshness.py` 增加公开的
`CurrentPredictionFreshnessFact` 事实模型，字段为 `state`、`market_time`、
`collected_at` 与 `time_is_verifiable`。新增
`is_usable_for_current_prediction(fact)` 作为当前预测入口规则：

- 仅 `REALTIME` 与 `NEAR_REALTIME` 可进入当前预测；
- `time_is_verifiable` 必须严格为 `True`；
- 复用 `calculate_age_seconds` 校验两个时点均带时区且市场时间不晚于采集时间；
- `DELAYED`、`STALE`、`CLOSED` 与未知状态返回 `False`；无效时间值抛出
  `FreshnessClassificationError`。

未修改既有 CN 5 秒、HK/US 15 秒、60 秒、900 秒、休市及微秒向上取整规则；未实现任何
HTTP 数据源、券商、下单或交易功能。

## TDD 红灯证据

先执行：

```powershell
py -3.12 -m pytest -o addopts='' tests/property/test_freshness_rules.py -v
```

结果为 66 项中 57 通过、9 失败。全部失败的直接原因一致：
`AttributeError: module 'stock_agent.domain.freshness' has no attribute
'is_usable_for_current_prediction'`。既有分类边界测试均通过，确认红灯仅缺少 T041
规则入口。

## 绿灯与质量验证

实现后以相同命令复验，结果：`66 passed in 0.43s`。

另执行：

```powershell
py -3.12 -m pytest
py -3.12 -m ruff format --check src/stock_agent/domain/freshness.py
py -3.12 -m ruff check src/stock_agent/domain/freshness.py tests/property/test_freshness_rules.py
```

- 全量 pytest 在收集阶段因缺少其他任务的模块而中断：
  `stock_agent.desktop.pages.market_page` 与
  `stock_agent.application.market_service`，与 T041 无关。
- `freshness.py` 的 Ruff 格式检查通过；Ruff 静态检查通过。
- 未修改测试文件；对该既有文件运行 Ruff 格式检查会提示它需要重格式化，属于本任务范围外
  的既存格式问题。
- 本次新增的文档字符串、报告与错误消息均为简体中文，符合项目语言规范。
