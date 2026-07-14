# T046：US1 测试执行与结果记录

## 提交

- 验收文档：`docs/acceptance/us1-test-results.md`
- 本报告：`.superpowers/sdd/task-046-report.md`
- 本次仅刷新验收记录，未修改生产代码或测试代码。

## 当前复验证据

- `py -3.12 -m pytest`：退出码 0，`363 passed`，总覆盖率 `88.31%`，达到 80.0% 门槛。
- `py -3.12 -m ruff format --check src tests`：退出码 0，`69 files already formatted`。
- `py -3.12 -m ruff check src tests`：退出码 0，`All checks passed!`。
- `py -3.12 tools/check_chinese_project_text.py .`：退出码 0，检查说明通过。

## 历史快照说明

此前记录的 US1 四文件定向 pytest 为 `251 passed in 13.76s`，但因子集覆盖率 `76.03%` 低于全局 80.0% 门槛而退出码为 1。Ruff 格式检查和中文检查的未通过项同样是 T046 执行时的真实快照。

质量提交 `906ef97`（`style: fix project quality gates`）已修复格式和中文文本问题。本次已仅以本报告列出的命令重新验证当前状态；不得将历史快照伪造为当时通过，也不得把未执行的命令加入本报告。

## Concerns

无当前质量门禁未通过项。历史定向子集 pytest 的覆盖率退出码仍仅适用于该次子集执行，不代表当前全量质量门禁状态。
