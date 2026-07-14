# US1 测试验收结果

## 验收范围

本记录对应 T046（用户故事 1：历史行情闭环）的测试执行。US1 的独立验收目标是：用户在不使用预测、板块或对话功能时，可选择市场与证券，查看主要指数、历史行情、来源、市场时间、采集时间、数据版本和新鲜度。

本阶段仅验证本地代码、测试夹具和本地持久化路径；不包含真实网络访问、券商连接、下单或自动交易。

## US1 覆盖的测试文件

| 类别 | 文件 | 本次定向执行结果 |
| --- | --- | --- |
| 契约 | `tests/contract/test_market_data_contract.py` | 已执行，包含在 251 个通过的测试中 |
| 属性 | `tests/property/test_freshness_rules.py` | 已执行，包含在 251 个通过的测试中 |
| 失败场景 | `tests/failure/test_market_data_failures.py` | 已执行，包含在 251 个通过的测试中 |
| 集成 | `tests/integration/test_single_market_daily_pipeline.py` | 已执行，包含在 251 个通过的测试中 |

定向命令：

```powershell
py -3.12 -m pytest tests/contract/test_market_data_contract.py tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py tests/integration/test_single_market_daily_pipeline.py
```

测试断言结果为 `251 passed in 13.76s`。但该命令的退出码为 1：项目全局覆盖率门槛为 80%，而只运行上述四个 US1 文件时的总覆盖率为 `76.03%`，因此 pytest 将本次定向执行标记为失败。不得将其记为全绿。

## 全量测试与覆盖率

执行命令：

```powershell
py -3.12 -m pytest
```

结果：退出码 0，`363 passed in 22.90s`；总覆盖率 `88.31%`，满足项目要求的 80.0% 覆盖率门槛。

## 质量检查

| 命令 | 结果 | 详情 |
| --- | --- | --- |
| `py -3.12 -m ruff format --check src tests` | 未通过（退出码 1） | 67 个文件已格式化；`src/stock_agent/desktop/pages/_recovery.py` 与 `tests/property/test_freshness_rules.py` 共 2 个文件需要格式化。 |
| `py -3.12 -m ruff check src tests` | 通过（退出码 0） | `All checks passed!` |
| `py -3.12 tools/check_chinese_project_text.py .` | 未通过（退出码 1） | `tests/failure/test_market_data_failures.py:89`：注释缺少简体中文的说明。 |

## 非通过项及影响

1. US1 定向 pytest 的 251 个测试断言均通过，但因为只运行该子集导致总覆盖率为 76.03%，未达到全局 `fail-under = 80`，命令退出码为 1。
2. Ruff 格式检查有 2 个待格式化文件，未在本任务中修改；本任务禁止修改生产代码和测试。
3. 全仓中文文本检查有 1 个既有非通过项：`tests/failure/test_market_data_failures.py:89` 的注释未含简体中文说明。该项是文本规范问题，不影响全量业务测试 `363 passed`、US1 四个测试文件的 251 个断言通过，亦不影响 Ruff 静态规则检查通过；但它仍使全仓中文文本检查未通过。

## 验收结论

US1 的目标契约、属性、失败与集成测试断言已全部通过，且全量测试与全量覆盖率门槛通过。由于定向子集覆盖率门槛、Ruff 格式检查和全仓中文文本检查存在上述非通过项，T046 的质量门禁不能表述为全部通过，须在修复并重新验证后才能获得全绿结论。
