# T046：US1 测试执行与结果记录

## 提交

- 验收文档：`docs/acceptance/us1-test-results.md`
- 本报告：`.superpowers/sdd/task-046-report.md`
- 本任务未修改生产代码或测试代码。

## 测试摘要

- `py -3.12 -m pytest`：退出码 0，`363 passed in 22.90s`，总覆盖率 `88.31%`，达到 80.0% 门槛。
- US1 四文件定向 pytest：测试断言 `251 passed in 13.76s`，但退出码 1；定向运行的总覆盖率为 `76.03%`，低于项目全局 80.0% 门槛。
- `py -3.12 -m ruff check src tests`：退出码 0，全部静态检查通过。
- 本阶段未包含真实网络、券商、下单或自动交易。

## Concerns

1. `py -3.12 -m ruff format --check src tests` 未通过：`src/stock_agent/desktop/pages/_recovery.py`、`tests/property/test_freshness_rules.py` 需要格式化。
2. `py -3.12 tools/check_chinese_project_text.py .` 未通过：`tests/failure/test_market_data_failures.py:89` 的注释缺少简体中文说明。
3. US1 定向 pytest 的断言通过，但因覆盖率门槛导致命令退出码为 1；不可将 T046 记录为全绿。
