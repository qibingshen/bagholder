# US1 测试验收结果

## 验收范围

本记录对应 T046（用户故事 1：历史行情闭环）的测试执行。US1 的独立验收目标是：用户在不使用预测、板块或对话功能时，可选择市场与证券，查看主要指数、历史行情、来源、市场时间、采集时间、数据版本和新鲜度。

本阶段仅验证本地代码、测试夹具和本地持久化路径；不包含真实网络访问、券商连接、下单或自动交易。

## US1 覆盖的测试文件

| 类别 | 文件 | 已记录的定向执行结果 |
| --- | --- | --- |
| 契约 | `tests/contract/test_market_data_contract.py` | 包含在 251 个通过的测试断言中 |
| 属性 | `tests/property/test_freshness_rules.py` | 包含在 251 个通过的测试断言中 |
| 失败场景 | `tests/failure/test_market_data_failures.py` | 包含在 251 个通过的测试断言中 |
| 集成 | `tests/integration/test_single_market_daily_pipeline.py` | 包含在 251 个通过的测试断言中 |

此前的定向执行命令为：

```powershell
py -3.12 -m pytest tests/contract/test_market_data_contract.py tests/property/test_freshness_rules.py tests/failure/test_market_data_failures.py tests/integration/test_single_market_daily_pipeline.py
```

该次执行是当时的快照：251 个测试断言通过，但因只运行 US1 子集而使总覆盖率为 `76.03%`，低于全局 `fail-under = 80`，命令退出码为 1。该历史定向结果不应被表述为全绿，也不替代下列全量复验。

## 当前全量复验

执行命令：

```powershell
py -3.12 -m pytest
```

结果：退出码 0，`363 passed`；总覆盖率 `88.31%`，满足项目要求的 80.0% 覆盖率门槛。

## 当前质量检查

| 命令 | 结果 | 详情 |
| --- | --- | --- |
| `py -3.12 -m ruff format --check src tests` | 通过（退出码 0） | `69 files already formatted` |
| `py -3.12 -m ruff check src tests` | 通过（退出码 0） | `All checks passed!` |
| `py -3.12 tools/check_chinese_project_text.py .` | 通过（退出码 0） | 检查说明通过 |

## 记录刷新说明

此前本记录中的 Ruff 格式检查和全仓中文文本检查未通过，均为 T046 执行时的真实快照，不是当前状态。后续质量提交 `906ef97`（`style: fix project quality gates`）已修复相应问题；本次按上列命令重新验证，格式检查、静态检查和中文检查均通过。不得将此前快照改写为当时已通过，也不得伪造未执行的命令结果。

## 验收结论

US1 的目标契约、属性、失败与集成测试断言已通过；当前全量测试、覆盖率门槛、Ruff 格式检查、Ruff 静态检查和全仓中文文本检查均通过。历史定向子集命令的覆盖率退出码仅反映其执行时的子集覆盖率，不构成当前全量质量门禁的未通过项。
